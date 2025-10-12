"""
BB's League Overlay - Real-time iRacing race position overlay

This application provides a floating, semi-transparent overlay that shows:
- Real-time race positions (updates before crossing start/finish line)
- Division-based color coding (Pro, ProAm, Am, Rookie)
- Live time gaps to cars ahead (within same division)
- Division-specific filtering for spectators
- Multi-class race support (always only show cars within same class)
- Class refers to different types of cars (LMP2, GT3, GT4, etc), Divisions refers to groupings of drivers within the same class
- Uses irsdk to read telemetry data from iRacing

KEY CONCEPTS:
1. REAL-TIME vs OFFICIAL POSITIONS
   - Official: Only updates when crossing start/finish line (iRacing default)
   - Real-time: Updates constantly based on track position (lap + lap%)
   - This overlay uses real-time during race, official after finish (and best lap time during practice or qualifying)

2. DIVISION SYSTEM
   - Drivers are assigned to divisions via league_divisions.json config file
   - Each division has a color (customizable in settings)
   - Gaps are calculated within divisions (Pro only competes with Pro, etc.)
   - Right-click any driver to change their division

3. FINISH TRACKING
   - Checkered flag waves when leader approaches the finish line, but race isn't over
   - Tracks when each car completes their current lap after checkered
   - Locks positions and gaps at the moment each car finishes
   - Prevents position changes after individual cars finish

4. UI FEATURES
   - Frameless, always-on-top window
   - Auto-hide headers on mouse leave (optional)
   - Auto-center on player (allows manual scroll but auto-centers again after 5 seconds)
   - Three color styles: Default, Alternate, Outline
   - Adjustable opacity, refresh rate, and font sizes
   - Opacity setting affects background but text stays at full opacity
"""

import sys
import threading
import time
import json
import os
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Set
import irsdk
import urllib.request
from packaging import version

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QGridLayout, QMenu,
    QDialog, QSlider, QCheckBox, QFileDialog, QMessageBox, QColorDialog,
    QSizeGrip, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QSize
from PySide6.QtGui import QColor, QPalette, QFont, QCursor, QPainter, QMouseEvent

VERSION = "0.9.7.5"


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

class SessionType(Enum):
    """iRacing session types."""
    PRACTICE = "Practice"
    QUALIFY = "Qualify"
    RACE = "Race"


class SessionState(Enum):
    """iRacing session states."""
    INVALID = 0
    GET_IN_CAR = 1
    WARMUP = 2
    PARADE_LAPS = 3
    RACING = 4
    CHECKERED = 5
    COOL_DOWN = 6


class ColorStyle(Enum):
    """Available color styles for driver rows."""
    DEFAULT = "Default"
    ALTERNATE = "Alternate"
    OUTLINE = "Outline"


@dataclass(frozen=True)
class UIConfig:
    """UI configuration constants."""
    # Font size configurations
    FONT_SIZES: Dict[str, Dict[str, Any]] = None

    # Default division colors
    DEFAULT_COLORS: Dict[str, str] = None

    # Auto-center settings
    MANUAL_SCROLL_TIMEOUT: float = 5.0  # seconds
    GUI_UPDATE_INTERVAL: int = 250  # milliseconds

    # Column proportions
    POSITION_COL_PROPORTION: float = 0.12
    DRIVER_COL_PROPORTION: float = 0.65
    GAP_COL_PROPORTION: float = 0.23

    def __post_init__(self):
        if self.FONT_SIZES is None:
            object.__setattr__(self, 'FONT_SIZES', {
                "Small": {
                    "title": "8.5pt",
                    "button": "8pt",
                    "status": "8pt",
                    "header": "8pt",
                    "data": "8pt",
                    "spacing": 2
                },
                "Medium": {
                    "title": "9.5pt",
                    "button": "8.5pt",
                    "status": "9pt",
                    "header": "9pt",
                    "data": "9pt",
                    "spacing": 3
                },
                "Large": {
                    "title": "10.5pt",
                    "button": "9pt",
                    "status": "10pt",
                    "header": "10pt",
                    "data": "10pt",
                    "spacing": 4
                },
                "Extra Large": {
                    "title": "11.5pt",
                    "button": "9.5pt",
                    "status": "11pt",
                    "header": "11pt",
                    "data": "11pt",
                    "spacing": 5
                }
            })

        if self.DEFAULT_COLORS is None:
            object.__setattr__(self, 'DEFAULT_COLORS', {
                "Pro": "#FF8C00",
                "ProAm": "#9370DB",
                "Am": "#45B3E0",
                "Rookie": "#FF2000",
                "Default": "#FFFFFF"
            })


@dataclass(frozen=True)
class FileConfig:
    """File path configuration constants."""
    SETTINGS_FILE: str = "LeagueOverlay.config"
    DIVISIONS_FILE: str = "league_divisions.json"


@dataclass(frozen=True)
class TelemetryConfig:
    """Telemetry configuration constants."""
    DEFAULT_REFRESH_RATE: float = 2.0  # seconds
    MIN_REFRESH_RATE: float = 0.25
    MAX_REFRESH_RATE: float = 5.0

    # iRacing SDK constants
    MAX_CARS: int = 64
    INACTIVE_POSITION: int = 0
    INVALID_LAP: int = -1
    INVALID_LAP_PCT: float = -1.0


# Global configuration instances
UI_CONFIG = UIConfig()
FILE_CONFIG = FileConfig()
TELEMETRY_CONFIG = TelemetryConfig()


@dataclass
class DriverData:
    """Data structure for a single driver's information."""
    position: int
    division_position: int
    car_number: str
    driver_name: str
    driver_info: Dict[str, str]
    gap: str
    car_idx: int
    is_player: bool
    division: Optional[str] = None

# ═══════════════════════════════════════════════════════════════════════════
# CRITICAL iRACING SDK VARIABLES USED IN THIS APPLICATION
# ═══════════════════════════════════════════════════════════════════════════
"""
The irsdk library provides access to iRacing telemetry through a dict-like interface.
Access variables like: ir['VariableName']

KEY TELEMETRY VARIABLES USED:
─────────────────────────────────────────────────────────────────────────────

SESSION INFO (from ir['SessionInfo'] - YAML structure):
    SessionInfo['Sessions'][session_num]['SessionType']
        - Type: string - "Practice", "Qualify", "Race"
        - Purpose: Determine if we use real-time or official positions

    SessionInfo['Sessions'][session_num]['ResultsPositions']
        - Type: list[dict] with 'CarIdx', 'ClassPosition', 'FastestTime'
        - When: Only after session ends (checkered flag)
        - Purpose: Get final results and lap times

    DriverInfo['Drivers']
        - Type: list[dict] with 'CarIdx', 'UserID', 'UserName', 'CarClassID', 'CarNumber'
        - When: Always available
        - Purpose: Map car indices to driver info for display

LIVE TELEMETRY VARIABLES (from ir['VariableName'] - updated each tick):
    SessionNum: int
        - Current session number (0=practice, 1=qualify, 2=race typically)
        - Purpose: Detect session changes to reset state

    SessionState: int
        - 0=Invalid, 1=GetInCar, 2=Warmup, 3=ParadeLaps, 4=Racing, 5=Checkered, 6=CoolDown
        - CRITICAL: SessionState >= 5 means checkered flag has waved
        - Purpose: Trigger race finish tracking

    PlayerCarIdx: int
        - Index of player's car (0-63)
        - Purpose: Auto-centering and "My Division" filter

    CarIdxLap: list[int] - Array indexed by car_idx
        - Current lap number for each car
        - CRITICAL: Used to detect when cars complete finish lap
        - Edge case: Can be -1 if car not on track

    CarIdxLapDistPct: list[float] - Array indexed by car_idx
        - Percentage through current lap (0.0 to 1.0)
        - CRITICAL: Used for real-time position calculation
        - Edge case: Can be -1.0 if car not on track, >1.0 rarely (glitch)

    CarIdxClassPosition: list[int] - Array indexed by car_idx
        - Official class position (updated at start/finish line)
        - Value 0 = car not participating/active
        - Purpose: Get official positions, filter active cars

    CarIdxEstTime: list[float] - Array indexed by car_idx
        - iRacing's estimated time (for time-based gap calculation)
        - More accurate than distance when cars on same lap
        - Value 0 = no estimate available

EDGE CASES & ASSUMPTIONS:
─────────────────────────────────────────────────────────────────────────────
1. Car indices (car_idx) range from 0-63, even in small fields
2. Arrays are always length 64, even with fewer cars
3. Position 0 in CarIdxClassPosition means "not active" (DNF, spectator, etc.)
4. Lap numbers can be -1 (car in pits, not on track yet)
5. LapDistPct should be 0.0-1.0 but can exceed (treat as 0 if invalid)
6. SessionState transitions: Racing(4) -> Checkered(5) -> CoolDown(6)
7. ResultsPositions only populated AFTER checkered, not during racing
8. Driver list is static per session (doesn't update if someone joins mid-race)
"""

# ═══════════════════════════════════════════════════════════════════════════
# RACE FINISH STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════
"""
PROBLEM: iRacing waves checkered flag when leader crosses line, but other cars
haven't finished yet. We need to track when EACH car finishes their current lap.

STATE MACHINE FLOW:
─────────────────────────────────────────────────────────────────────────────

STATE 0: RACING (SessionState < 5)
    Variables: All finish tracking vars are None/False/empty
    Exit condition: SessionState >= 5 (checkered flag)
    → Transition to STATE 1

STATE 1: CHECKERED WAVED, IDENTIFYING FINISH LAP
    leader_last_lap = None
    leader_finished = False

    Action: Find P1 car, record their current lap number
    Variables set:
        - leader_last_lap = current lap of P1
        - leader_car_idx = car_idx of P1

    Purpose: This lap number is the "finish lap" - when it increments,
             that car has crossed the finish line and completed the race

    Exit condition: leader_last_lap is set
    → Transition to STATE 2

STATE 2: WAITING FOR LEADER TO COMPLETE FINISH LAP
    leader_last_lap = <lap number>
    leader_finished = False

    Action: Every tick, check if current P1's lap > leader_last_lap
    Purpose: Leader might change due to last-lap pass

    Exit condition: Current P1's lap increments
    Variables set:
        - leader_finished = True
        - finished_drivers.add(leader_car_idx)
        - driver_snapshots[leader]['official_position'] = final position

    → Transition to STATE 3

STATE 3: LEADER DONE, TRACKING OTHER DRIVERS FINISHING
    leader_finished = True
    finished_drivers = {leader_car_idx, ...}

    Action: For each car NOT in finished_drivers:
        - Check if their lap incremented (compared to snapshot)
        - If yes: Add to finished_drivers, capture official_position
        - final_gaps[car_idx] preserved from last update before finish

    Purpose: Each car finishes when their lap counter increments
    Exit condition: All cars finish or session ends
    → Stay in STATE 3 until session change (resets to STATE 0)

KEY INVARIANTS:
─────────────────────────────────────────────────────────────────────────────
1. Once in finished_drivers, a car never leaves (until session reset)
2. Gaps are continuously updated for racing cars, frozen on finish
3. leader_last_lap never changes after initial set (even if P1 changes)
4. States only progress forward, reset only on session change

CRITICAL EDGE CASES:
─────────────────────────────────────────────────────────────────────────────
1. Last-lap pass: P1 at checkered might not be P1 at finish
   → Track "current P1" each update, not "P1 when checkered waved"

2. Disconnected cars: May finish based on ResultsPositions, not lap increment
   → Handle separately in disconnected driver logic

3. Multi-class: Only track cars in player's class
   → Filter by CarClassID before processing
"""


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: RACING DOMAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════════
#
# These classes handle racing-specific logic independent of UI:
# - DivisionManager: Driver-to-division assignments and colors
# - GapCalculator: Time/distance gap calculations
# - RaceStateTracker: Race finish state machine
#
# TO SPLIT: Move this entire section to racing_logic.py
# ═══════════════════════════════════════════════════════════════════════════

class DivisionManager:
    """Manages driver-to-division assignments and color configuration.

    Responsibilities:
    - Load/save division configuration from/to JSON file
    - Assign drivers to divisions (Pro, ProAm, Am, Rookie)
    - Provide division colors for UI rendering
    - Handle default division colors
    """

    def __init__(self, config_file: str = FILE_CONFIG.DIVISIONS_FILE, settings_file: str = FILE_CONFIG.SETTINGS_FILE):
        """Initialize division manager.

        Args:
            config_file: Path to JSON file containing driver-division mappings
        """
        self.config_file = config_file
        self.settings_file = settings_file
        self.driver_colors: dict[str, list] = {'drivers': []}
        self.division_colors: dict[str, str] = UI_CONFIG.DEFAULT_COLORS.copy()
        self.load_driver_config()
        self.load_division_config()

    def load_driver_config(self) -> None:
        """Load driver-division mappings from config file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    if 'drivers' in data:
                        self.driver_colors = data
                    else:
                        self.driver_colors = {'drivers': []}
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading division config: {e}")
                self.driver_colors = {'drivers': []}
        else:
            self.driver_colors = {'drivers': []}

    def load_division_config(self) -> None:
        """Load division colors"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    division_colors = data.get('division_colors', {})
                    self.division_colors.update(division_colors)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading division colors: {e}")
                self.division_colors = UI_CONFIG.DEFAULT_COLORS.copy()
        else:
            self.division_colors = UI_CONFIG.DEFAULT_COLORS.copy()
 
    def save_config(self) -> None:
        """Save driver-division mappings to config file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.driver_colors, f, indent=2)
        except IOError as e:
            print(f"Error saving division config: {e}")

    def get_driver_division(self, driver_info: Dict[str, str]) -> Optional[str]:
        """Get the division assigned to a driver.

        Args:
            driver_info: Dictionary with 'UserID' and 'UserName' keys

        Returns:
            Division name (e.g., "Pro", "ProAm") or None if not assigned
        """
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')

        for driver in self.driver_colors['drivers']:
            driver_id = driver.get('id', '')
            if driver_id and driver_id == user_id:
                return driver.get('division')
            if driver.get('name') == user_name:
                return driver.get('division')

        return None

    def set_driver_division(self, driver_info: Dict[str, str], division: str) -> None:
        """Assign a driver to a division or remove assignment.

        Args:
            driver_info: Dictionary with 'UserID' and 'UserName' keys
            division: Division name to assign (e.g., "Pro", "ProAm", "Am", "Rookie")
                     or "Default" to remove the driver from config

        Note:
            Setting division to "Default" removes the driver from the config,
            causing them to display with the default white color.
        """
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')

        if 'drivers' not in self.driver_colors:
            self.driver_colors['drivers'] = []

        # Check if driver already has an entry
        existing_entry = None
        for i, driver in enumerate(self.driver_colors['drivers']):
            driver_id = driver.get('id', '')
            driver_name = driver.get('name', '')

            if (user_id and driver_id == user_id) or (user_name and driver_name == user_name):
                existing_entry = i
                break

        if division == "Default":
            # Remove driver from config (they'll get default white color)
            if existing_entry is not None:
                self.driver_colors['drivers'].pop(existing_entry)
        else:
            # Add or update driver's division assignment
            entry = {'division': division}
            if user_id:
                entry['id'] = user_id
            if user_name:
                entry['name'] = user_name
            
            if existing_entry is not None:
                old_entry = self.driver_colors['drivers'][existing_entry]
                if not user_id and 'id' in old_entry:
                    entry['id'] = old_entry['id']
                if not user_name and 'name' in old_entry:
                    entry['name'] = old_entry['name']
                self.driver_colors['drivers'][existing_entry] = entry
            else:
                self.driver_colors['drivers'].append(entry)

            self.save_config()

    def get_division_color(self, division: Optional[str]) -> str:
        """Get the color hex code for a division.

        Args:
            division: Division name (e.g., "Pro", "ProAm")

        Returns:
            Hex color code (e.g., "#FF8C00")
        """
        if division and division in self.division_colors:
            return self.division_colors[division]
        return self.division_colors.get("Default", "#FFFFFF")

    def set_division_color(self, division: str, color: str) -> None:
        """Set the color for a division.

        Args:
            division: Division name
            color: Hex color code
        """
        self.division_colors[division] = color
        self.save_config()


class GapCalculator:
    """Calculates and formats time/distance gaps between cars.

    Responsibilities:
    - Calculate time-based gaps using iRacing telemetry
    - Calculate lap-based gaps for cars on different laps
    - Format gap strings for display (e.g., "5.3", "2L", "Leader")
    - Handle edge cases (disconnected cars, invalid data)
    """

    @staticmethod
    def calculate_time_gap(est_time_ahead: float, est_time_behind: float) -> Optional[float]:
        """Calculate time gap in seconds between two cars.

        Args:
            est_time_ahead: Estimated time for car ahead (from CarIdxEstTime)
            est_time_behind: Estimated time for car behind (from CarIdxEstTime)

        Returns:
            Time gap in seconds, or None if data invalid
        """
        if est_time_ahead > 0 and est_time_behind > 0:
            gap = est_time_ahead - est_time_behind
            return gap if gap >= 0 else gap * -1
        return None

    @staticmethod
    def calculate_lap_gap(lap_ahead, lap_behind) -> int:
        """Calculate lap difference between two cars based on lap + possibly distance.

        Args:
            lap_ahead: Lap number + optionally current lap distance of car ahead
            lap_behind: Lap number + optionally current lap distance of car behind

        Returns:
            Number of laps behind (always >= 0)
        """
        gap = lap_ahead - lap_behind
        return int(gap) if gap > 0 else 0

    @staticmethod
    def format_gap_display(time_gap: Optional[float] = None,
                          lap_gap: int = 0,
                          is_leader: bool = False,
                          is_disconnected: bool = False) -> str:
        """Format gap for display in UI.

        Args:
            time_gap: Time gap in seconds (None if not on same lap)
            lap_gap: Number of laps behind
            is_leader: Whether this is the race leader
            is_disconnected: Whether driver is disconnected

        Returns:
            Formatted gap string (e.g., "Leader", "5.3", "2L", "(DC)")
        """
        if is_disconnected:
            return "(DC)"

        if is_leader:
            return "Leader"

        if lap_gap > 0:
            return f"{lap_gap}L"

        if time_gap is not None:
            if time_gap < 60:
                return f"{time_gap:.1f}"
            else:
                minutes = int(time_gap // 60)
                seconds = time_gap % 60
                return f"{minutes}:{seconds:04.1f}"

        return "-"


class RaceStateTracker:
    """Tracks race finish state machine and completed laps after checkered flag.

    State Machine:
    - RACING: Normal racing, no checkered flag yet
    - CHECKERED_WAVED: Checkered flag shown, waiting for leader to finish
    - LEADER_FINISHED: Leader completed, tracking other cars finishing

    Responsibilities:
    - Track when checkered flag waves
    - Detect when each car completes their finish lap
    - Freeze positions and gaps when cars finish
    - Handle disconnected drivers in final results
    """

    def __init__(self):
        """Initialize race state tracker."""
        self.reset()

    def reset(self) -> None:
        """Reset all finish tracking state (called on session change)."""
        self.leader_finished: bool = False
        self.finished_drivers: Set[int] = set()
        self.leader_car_idx: Optional[int] = None
        self.leader_last_lap: Optional[int] = None
        self.final_gaps: Dict[int, str] = {}
        self.driver_snapshots: Dict[int, Dict[str, Any]] = {}

    def is_racing(self) -> bool:
        """Check if race is still in progress (not finished).

        Returns:
            True if race is ongoing, False if checkered flag waved
        """
        return self.leader_last_lap is None

    def set_checkered_flag(self, leader_car_idx: int, leader_lap: int) -> None:
        """Mark checkered flag as waved and record leader state.

        Args:
            leader_car_idx: Car index of current leader
            leader_lap: Current lap number of leader
        """
        if self.leader_last_lap is None:
            self.leader_car_idx = leader_car_idx
            self.leader_last_lap = leader_lap

    def mark_driver_finished(self, car_idx: int, gap: str, official_position: int) -> None:
        """Mark a driver as having completed their finish lap.

        Args:
            car_idx: Car index of finished driver
            gap: Final gap string to freeze
            official_position: Final official position
        """
        if car_idx not in self.finished_drivers:
            self.finished_drivers.add(car_idx)
            self.final_gaps[car_idx] = gap

            if car_idx == self.leader_car_idx:
                self.leader_finished = True

            # Store final position in snapshot
            if car_idx in self.driver_snapshots:
                self.driver_snapshots[car_idx]['official_position'] = official_position

    def is_driver_finished(self, car_idx: int) -> bool:
        """Check if a driver has finished their race.

        Args:
            car_idx: Car index to check

        Returns:
            True if driver has completed their finish lap
        """
        return car_idx in self.finished_drivers

    def get_final_gap(self, car_idx: int) -> Optional[str]:
        """Get the frozen gap for a finished driver.

        Args:
            car_idx: Car index

        Returns:
            Frozen gap string, or None if not finished
        """
        return self.final_gaps.get(car_idx)

    def update_snapshot(self, car_idx: int, snapshot_data: Dict[str, Any]) -> None:
        """Update or create driver snapshot with current state.

        Args:
            car_idx: Car index
            snapshot_data: Dictionary with driver state (lap, position, etc.)
        """
        self.driver_snapshots[car_idx] = snapshot_data

    def get_snapshot(self, car_idx: int) -> Optional[Dict[str, Any]]:
        """Get stored snapshot for a driver.

        Args:
            car_idx: Car index

        Returns:
            Snapshot dictionary or None if not found
        """
        return self.driver_snapshots.get(car_idx)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: UI COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════
#
# These classes provide UI-specific functionality:
# - DataUpdateSignal: Thread-safe signals for telemetry → UI communication
# - CustomSizeGrip: Custom resize grip for frameless window
# - SettingsDialog: Settings/preferences dialog (defined later in file)
#
# TO SPLIT: Move this section (and SettingsDialog below) to ui_components.py
# ═══════════════════════════════════════════════════════════════════════════

class DataUpdateSignal(QObject):
    """Signal emitter for thread-safe GUI updates.

    Emits signals from telemetry thread to UI thread for safe updates.
    """
    update_data = Signal(list)
    update_status = Signal(str, str)  # text, color
    refresh_colors = Signal()

class CustomSizeGrip(QSizeGrip):
    """Custom size grip widget with transparent background and conditional visibility.

    Shows diagonal arrow pattern when parent window has focus, allows window resizing.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize custom size grip.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.parent_window: Optional[QMainWindow] = None
        # Make the widget background transparent
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_parent_window(self, window: QMainWindow) -> None:
        """Set reference to parent window for focus checking.

        Args:
            window: Parent main window reference
        """
        self.parent_window = window

    def paintEvent(self, event) -> None:
        """Custom paint to show diagonal arrows when focused with transparent background.

        Args:
            event: Paint event
        """
        # Don't call super().paintEvent() to avoid default rendering

        if self.parent_window and self.parent_window.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Make background fully transparent
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw diagonal arrows
            painter.setPen(QColor("#888888"))

            # Draw diagonal double arrow pattern
            size = self.width()
            spacing = 4

            # Draw three diagonal lines to create arrow effect
            for i in range(3):
                offset = i * spacing
                painter.drawLine(
                    size - 3 - offset, offset + 3,
                    offset + 3, size - 3 - offset
                )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: MAIN APPLICATION CLASS
# ═══════════════════════════════════════════════════════════════════════════
#
# This is the main application window that orchestrates everything:
# - LeagueOverlay: Main window, telemetry processing, UI rendering
#
# TO SPLIT: Keep this in league_overlay.py (main file)
# Import: from racing_logic import DivisionManager, GapCalculator, RaceStateTracker
# Import: from ui_components import DataUpdateSignal, CustomSizeGrip, SettingsDialog
# ═══════════════════════════════════════════════════════════════════════════

class LeagueOverlay(QMainWindow):
    """
    Main application window for iRacing race position overlay.

    KEY INSTANCE VARIABLES - DATA STRUCTURES & THEIR LIFECYCLE
    ============================================================

    IRSDK CONNECTION:
        self.ir: irsdk.IRSDK instance - Connection to iRacing simulator
            - Provides telemetry data via self.ir['VariableName']
            - Must call startup() before use, shutdown() on disconnect
            - Access like dict: self.ir['SessionState'], self.ir['CarIdxLap']

        self.is_connected: bool - Whether currently connected to iRacing
            - Set True when ir.startup() succeeds
            - Set False when ir.is_connected fails (iRacing closed)

        self.running: bool - Main loop control flag
            - Set False to stop telemetry thread (on app close)

    SESSION STATE TRACKING (cleared on session change):
        self.driver_snapshots: dict[int, dict] - Last known state of each car
            - Key: car_idx (iRacing's car index, 0-63)
            - Value: Full driver data with position, lap, lap_pct, etc.
            - Used to track disconnected drivers and finish status
            - CLEARED: On session number or type change

        self.current_session_num: int | None - iRacing's session number
            - 0 = practice, 1 = qualify, 2 = race (typically)
            - Used to detect session changes and reset state

        self.current_session_type: str | None - "Race", "Practice", "Qualify"
            - Used with session_num to detect transitions

    RACE FINISH STATE MACHINE (see detailed diagram below):
        self.leader_finished: bool - Has the race leader completed their finish lap?
            - False: Still racing or waiting for leader
            - True: Leader done, now tracking other drivers finishing

        self.finished_drivers: set[int] - Car indices that have finished
            - Added when car's lap increments after checkered flag
            - Prevents re-processing the same finish

        self.leader_car_idx: int | None - Car index of the race leader
            - Set when checkered flag waves (SessionState >= 5)

        self.leader_last_lap: int | None - Lap number leader was on at checkered
            - When this lap increments, leader has truly finished
            - CRITICAL: Used to determine "finish lap" for all drivers

        self.final_gaps: dict[int, str] - Frozen gap strings for finished drivers
            - Key: car_idx
            - Value: Gap string like "5.3", "2L", "Leader"
            - Continuously updated during race, frozen on finish

    PLAYER IDENTIFICATION:
        self.player_car_idx: int | None - iRacing index of player's car
            - From self.ir['PlayerCarIdx']
            - Used for auto-centering and "My Division" filter
            - CLEARED: On session change (re-detected)

        self.player_car_class_id: int | None - Player's car class (multi-class)
            - Used to filter overlay to only player's class
            - CLEARED: On session change

    UI DATA:
        self.race_data: list[dict] - All drivers from telemetry (unfiltered)
            - Updated by telemetry thread, filtered in update_gui()

        self.displayed_data: list[dict] - Filtered data currently shown in UI
            - Copy of race_data after division filtering applied
            - Used to preserve context for UI updates
    """

    def __init__(self):
        super().__init__()

        # ═══════════════════════════════════════════════════════════
        # IRSDK CONNECTION
        # ═══════════════════════════════════════════════════════════
        self.ir = irsdk.IRSDK()  # iRacing SDK connection object
        self.is_connected = False  # Connection status flag
        self.running = True  # Thread control flag

        # ═══════════════════════════════════════════════════════════
        # THREAD-SAFE COMMUNICATION (telemetry thread -> UI thread)
        # ═══════════════════════════════════════════════════════════
        self.signals = DataUpdateSignal()
        self.signals.update_data.connect(self.display_race_data)
        self.signals.update_status.connect(self.update_status_label)
        self.signals.refresh_colors.connect(self.refresh_driver_colors)

        # ═══════════════════════════════════════════════════════════
        # AUTO-CENTERING STATE
        # ═══════════════════════════════════════════════════════════
        self.player_car_idx = None  # Player's car (from iRacing API)
        self.last_manual_scroll = 0  # Timestamp of last manual scroll
        self.manual_scroll_timeout = 5  # Seconds before re-enabling auto-center
        self.auto_center_enabled = True  # Master switch (currently unused)
        self.refresh_rate = 2.0  # Seconds between telemetry polls

        # ═══════════════════════════════════════════════════════════
        # USER PREFERENCES (persisted to LeagueOverlay.config)
        # ═══════════════════════════════════════════════════════════
        self.show_only_my_division = False  # Filter to player's division only
        self.opacity = 0.5  # Window transparency (0.1 to 1.0)
        self.width = 320  # Window width in pixels
        self.height = 350  # Window height in pixels
        self.x = 100  # Window X position
        self.y = 100  # Window Y position
        self.hide_headers = False  # Auto-hide title bar on mouse leave
        self.center_drivers = False  # Center driver names in column
        self.bold_drivers = True  # Bold all driver names
        self.font_size = "Medium"  # Small, Medium, Large, Extra Large
        self.row_color_style = "Default"  # Default, Alternate, Outline
        self.top_elements_visible = True  # Current visibility of title/status
        self.current_division_filter = None  # Active spectator division filter
        self.division_cycle_order = ["Pro", "ProAm", "Am", "Rookie", "All"]

        # Font size mappings (use UI_CONFIG)
        self.font_sizes = UI_CONFIG.FONT_SIZES

        # ═══════════════════════════════════════════════════════════
        # HELPER CLASSES - Extracted responsibilities
        # ═══════════════════════════════════════════════════════════
        self.division_manager = DivisionManager(FILE_CONFIG.DIVISIONS_FILE)
        self.race_state_tracker = RaceStateTracker()
        self.gap_calculator = GapCalculator()

        # Session tracking
        self.current_session_num: Optional[int] = None
        self.current_session_type: Optional[str] = None
        self.player_car_class_id: Optional[int] = None

        # Update checking
        self.update_check_done: bool = False
        self.latest_version: Optional[str] = None

        # Configuration files
        self.color_config_file = "league_divisions.json"
        self.settings_file = FILE_CONFIG.SETTINGS_FILE
        self.load_settings()

        # Legacy compatibility - keep references for backward compatibility
        # These delegate to the helper classes
        self.driver_colors = self.division_manager.driver_colors
        self.available_colors = self.division_manager.division_colors
        self.default_colors = UI_CONFIG.DEFAULT_COLORS

        # Race state tracking - maintain direct references for compatibility
        # These are also tracked in race_state_tracker, but kept here for legacy code
        self.driver_snapshots: Dict[int, Dict[str, Any]] = {}
        self.leader_finished: bool = False
        self.finished_drivers: Set[int] = set()
        self.leader_car_idx: Optional[int] = None
        self.leader_last_lap: Optional[int] = None
        self.final_gaps: Dict[int, str] = {}

        # ═══════════════════════════════════════════════════════════
        # DATA STRUCTURES - What race_data and displayed_data contain
        # ═══════════════════════════════════════════════════════════
        # Both are list[dict] with this structure per driver:
        # {
        #     'position': int,              # Overall class position (1-based)
        #     'division_position': int,     # Position within division (1-based)
        #     'car_number': str,            # Car number from iRacing
        #     'driver_name': str,           # UserName from iRacing
        #     'driver_info': {              # Subset for division lookup
        #         'UserID': str,            # iRacing user ID
        #         'UserName': str           # iRacing username
        #     },
        #     'gap': str,                   # "Leader", "5.3", "2L", "(DC)"
        #     'car_idx': int,               # iRacing car index (0-63)
        #     'is_player': bool             # True if this is the player's car
        # }
        self.race_data = []  # Unfiltered - all drivers from telemetry
        self.displayed_data = []  # Filtered - what's currently shown in UI
        self.data_widgets = {}  # Currently unused legacy variable
        
        self.startup_time = time.time()
        
        # Setup UI
        self.setup_ui()
        
        # Start telemetry thread
        self.telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        self.telemetry_thread.start()
        
        # Auto-update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_gui)
        self.update_timer.start(250)
        
        # Show version
        self.show_version_on_startup()

        # Focus tracking for auto-hide
        self.hide_timer = None
        self.setMouseTracking(True)
        
        # Initial state for auto-hide
        if self.hide_headers:
            # Don't hide on startup, let user see the interface first
            pass

    def get_bg_color(self, base_color):
        """Convert a hex color to RGBA format with current window opacity.

        Purpose: All background colors must respect the user's opacity setting for
        the semi-transparent overlay effect. This centralizes that conversion.

        Args:
            base_color: Hex color string like "#FF8C00" or "rgba(...)" already

        Returns:
            RGBA string like "rgba(255, 140, 0, 0.5)" for use in stylesheets

        Assumptions:
            - self.opacity is a float between 0.0 and 1.0
            - Input is either hex format or already rgba (passed through unchanged)
        """
        # Parse hex color
        if base_color.startswith('#'):
            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)
            return f"rgba({r}, {g}, {b}, {self.opacity})"
        return base_color

    def get_font_size(self, element_type):
        """Get the appropriate font size or spacing for a UI element.

        Purpose: Centralizes font sizing to make the entire UI scale together
        when user changes font size setting (Small/Medium/Large/Extra Large).

        Args:
            element_type: One of "title", "button", "status", "header", "data", "spacing"

        Returns:
            For font elements: String like "9pt", "10pt", etc.
            For "spacing": Integer pixel value (2, 3, 4, 5)

        Why this exists: Different UI elements need different sizes, but they
        should all scale proportionally when user adjusts the font size setting.
        """
        if element_type == "spacing":
            return self.font_sizes.get(self.font_size, self.font_sizes["Medium"]).get(element_type, 3)
        return self.font_sizes.get(self.font_size, self.font_sizes["Medium"]).get(element_type, "9pt")

    def blend_color_with_black(self, color_hex, amount=0.15):
        """Blend a division color with black to create a subtle tinted background.

        Purpose: Used for gradient backgrounds on player rows. We want a hint of
        the division color without being too bright or distracting. This creates
        a "glow" effect that's visible but doesn't overpower the text.

        Args:
            color_hex: Division color like "#FF8C00" (orange for Pro)
            amount: How much of the color to keep (0.0 = pure black, 1.0 = full color)
                   Default 0.15 gives a subtle tint, 0.25 is more visible

        Returns:
            Hex color string like "#261500" (very dark orange)

        Why this exists: Pure division colors are too bright for backgrounds.
        We need darkened versions that still convey the division color.
        """
        # Remove the # if present
        color_hex = color_hex.lstrip('#')

        # Convert hex to RGB
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)

        # Blend with black (reduce intensity)
        r = int(r * amount)
        g = int(g * amount)
        b = int(b * amount)

        return f"#{r:02x}{g:02x}{b:02x}"

    def create_gradient_background(self, color_hex):
        """Create a horizontal gradient that creates a subtle "glow" effect for player row.

        Purpose: Makes the player's row stand out without being overpowering.
        The gradient goes from tinted color on edges to dark gray in the middle.

        Args:
            color_hex: Division color like "#FF8C00"

        Returns:
            Qt gradient string for stylesheet backgrounds

        Why this exists: A solid colored background would be too bright and
        distracting. A gradient gives a nice subtle highlight that draws the eye
        to the player without overwhelming the data.

        Visual effect: [dark orange] -> [dark gray] -> [dark orange]
        """
        tinted = self.blend_color_with_black(color_hex, 0.25)
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {tinted}, stop:0.5 #1a1a1a, stop:1 {tinted})"

    def get_inverse_color(self, color_hex):
        """Calculate the inverse/complementary color for maximum contrast.

        Purpose: Currently unused, but intended for future features that might
        need high contrast text on colored backgrounds (like Alternate color style).

        Args:
            color_hex: Hex color like "#FF8C00"

        Returns:
            Inverted hex color like "#0073FF"

        How it works: Inverts each RGB channel (255 - value)
        Example: Orange #FF8C00 -> Blue #0073FF

        Assumptions: Input is a valid 6-character hex color
        """
        # Remove the # if present
        color_hex = color_hex.lstrip('#')

        # Convert hex to RGB
        r = int(color_hex[0:2], 16)
        g = int(color_hex[2:4], 16)
        b = int(color_hex[4:6], 16)

        # Invert the RGB values
        inv_r = 255 - r
        inv_g = 255 - g
        inv_b = 255 - b

        return f"#{inv_r:02x}{inv_g:02x}{inv_b:02x}"

    def update_all_backgrounds(self):
        """Refresh all UI backgrounds, fonts, and styling after settings change.

        Purpose: When user changes opacity, font size, or color style in settings,
        we need to update all existing UI elements to reflect the new values.

        Why this exists: Qt doesn't automatically update stylesheets when variables
        change. We must manually reapply styles to all widgets that depend on
        opacity or font settings.

        Called by:
            - Settings dialog when user changes opacity slider
            - Settings dialog when applying changes
            - On startup after loading saved settings

        Assumptions:
            - All UI widgets have been created (checks with hasattr)
            - self.opacity and self.font_size are already updated with new values
        """
        if hasattr(self, 'main_widget'):
            self.main_widget.setStyleSheet(f"background-color: {self.get_bg_color('#000000')};")
        if hasattr(self, 'title_bar'):
            self.title_bar.setStyleSheet(f"background-color: {self.get_bg_color('#333333')};")
        if hasattr(self, 'header_frame'):
            self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color('#333333')};")
        if hasattr(self, 'scroll_area'):
            self.update_scroll_area_style()
        if hasattr(self, 'scroll_content'):
            self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color('#000000')};")
        if hasattr(self, 'size_grip'):
            self.size_grip.setStyleSheet("""
                QSizeGrip {
                    background-color: transparent;
                    border: none;
                    image: none;
                }
            """)
        # Recreate headers with new opacity and font size
        if hasattr(self, 'header_layout'):
            self.create_headers()
        # Update title bar fonts
        if hasattr(self, 'title_label'):
            self.title_label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    font-weight: bold;
                    font-size: {self.get_font_size('title')};
                }}
            """)
        if hasattr(self, 'division_btn'):
            # Get current color from the button
            current_style = self.division_btn.styleSheet()
            if "background-color:" in current_style:
                # Extract background color
                import re
                color_match = re.search(r'background-color:\s*([^;]+)', current_style)
                button_color = color_match.group(1).strip() if color_match else '#555555'
            else:
                button_color = '#555555'

            self.division_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {button_color};
                    color: white;
                    border: none;
                    padding: 4px 4px;
                    font-size: {self.get_font_size('button')};
                }}
                QPushButton:hover {{
                    background-color: {button_color};
                }}
            """)
        if hasattr(self, 'settings_btn'):
            self.settings_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #555555;
                    color: white;
                    border: none;
                    padding: 4px 4px;
                    font-size: {self.get_font_size('button')};
                }}
                QPushButton:hover {{
                    background-color: #666666;
                }}
            """)
        # Update status label font
        if hasattr(self, 'status_label'):
            if 'green' in self.status_label.styleSheet().lower():
                self.update_status_style('green')
            elif 'orange' in self.status_label.styleSheet().lower():
                self.update_status_style('orange')
            else:
                self.update_status_style('white')
        # Update scroll layout spacing
        if hasattr(self, 'scroll_layout'):
            self.scroll_layout.setSpacing(self.get_font_size('spacing'))
        # Refresh displayed data to update driver rows
        if hasattr(self, 'displayed_data') and self.displayed_data:
            self.display_race_data(self.displayed_data.copy())

    def setup_ui(self):
        """Setup the main user interface"""
        # Window setup
        self.setWindowTitle("BB's League Overlay")
        self.setGeometry(self.x, self.y, self.width, self.height)

        # Frameless but stay on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Set minimum size for resizing
        self.setMinimumSize(250, 200)
        
        # Main widget and layout
        main_widget = QWidget()
        main_widget.setStyleSheet(f"background-color: {self.get_bg_color('#000000')};")
        self.setCentralWidget(main_widget)
        self.main_widget = main_widget
        
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Title bar
        self.create_title_bar()
        
        # Status label
        self.status_label = QLabel("Connecting to iRacing...")
        self.update_status_style("orange")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.status_label)

        # Header frame
        self.header_frame = QWidget()
        self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color('#333333')};")
        self.header_layout = QGridLayout(self.header_frame)
        self.create_headers()
        self.main_layout.addWidget(self.header_frame)
        
        # Scrollable area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.update_scroll_area_style()

        # Scrollable content
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color('#000000')};")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_layout.setSpacing(self.get_font_size('spacing'))
        self.scroll_layout.addStretch()
        
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_manual_scroll)
        self.main_layout.addWidget(self.scroll_area)

        # Add size grip for resizing
        self.size_grip = CustomSizeGrip(main_widget)
        self.size_grip.set_parent_window(self)
        self.size_grip.setFixedSize(20, 20)
        self.size_grip.setStyleSheet("""
            QSizeGrip {
                background-color: transparent;
                border: none;
                image: none;
            }
        """)
        # Position it at bottom right
        self.size_grip.raise_()

        # Mouse tracking
        self.setMouseTracking(True)
        self.drag_position = QPoint()
        
    def update_scroll_area_style(self):
        """Update scroll area style with current opacity"""
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {self.get_bg_color('#000000')};
            }}
            QScrollBar:vertical {{
                background: {self.get_bg_color('#222222')};
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #555555;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #666666;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def update_status_style(self, color):
        """Update status label style with current opacity"""
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {self.get_bg_color('#000000')};
                padding: 5px;
                font-size: {self.get_font_size('status')};
            }}
        """)

    def create_title_bar(self):
        """Create custom title bar"""
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet(f"background-color: {self.get_bg_color('#333333')};")
        
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(5, 2, 5, 2)
        
        # Title label
        self.title_label = QLabel("BB's League Overlay")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: {self.get_font_size('title')};
            }}
        """)
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        
        # Division filter button
        self.division_btn = QPushButton("All Divisions")
        self.division_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #555555;
                color: white;
                border: none;
                padding: 4px 4px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: #666666;
            }}
        """)
        self.division_btn.clicked.connect(self.toggle_division_filter)
        title_layout.addWidget(self.division_btn)

        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #555555;
                color: white;
                border: none;
                padding: 4px 4px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: #666666;
            }}
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        title_layout.addWidget(self.settings_btn)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(25)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #cc0000;
                color: white;
                border: none;
                padding: 5px;
                font-size: 12pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff0000;
            }
        """)
        close_btn.clicked.connect(self.close_application)
        title_layout.addWidget(close_btn)
        
        self.main_layout.addWidget(self.title_bar)
        
    def create_headers(self):
        """Create column headers"""
        # Clear existing
        while self.header_layout.count():
            item = self.header_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add padding on right to account for scrollbar (6px scrollbar + 5px margin)
        self.header_layout.setContentsMargins(5, 2, 11, 2)
        self.header_layout.setSpacing(2)
        
        # Column proportions
        self.header_layout.setColumnStretch(0, 11)
        self.header_layout.setColumnStretch(1, 11)
        self.header_layout.setColumnStretch(2, 13)
        self.header_layout.setColumnStretch(3, 46)
        self.header_layout.setColumnStretch(4, 19)
        
        headers = ["Pos", "D-Pos", "Car#", "Driver", "Div Gap"]
        
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    background-color: {self.get_bg_color('#333333')};
                    font-weight: bold;
                    font-size: {self.get_font_size('header')};
                }}
            """)
            label.setAlignment(Qt.AlignCenter)
            self.header_layout.addWidget(label, 0, i)
            
    def show_version_on_startup(self):
        """Show version on startup"""
        self.status_label.setText(f"BB's League Overlay v{VERSION}")
        self.update_status_style("orange")
        threading.Thread(target=self.check_and_notify_updates, daemon=True).start()
        
    def check_and_notify_updates(self):
        """Check for updates"""
        if self.update_check_done:
            return
        time.sleep(1)
        result = self.check_for_updates()
        self.update_check_done = True
        
        if result.get('update_available'):
            self.latest_version = result['latest_version']
            msg = f"Update available: v{result['latest_version']}"
            self.signals.update_status.emit(msg, '#00FF00')
            
    def check_for_updates(self):
        """Check GitHub for updates"""
        try:
            url = "https://api.github.com/repos/steak-and-gravy/league-overlay/releases/latest"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest = data['tag_name'].lstrip('v')
                current = VERSION
                
                return {
                    'update_available': version.parse(latest) > version.parse(current),
                    'latest_version': latest,
                    'current_version': current,
                    'download_url': data.get('html_url', '')
                }
        except Exception as e:
            return {'update_available': False, 'error': str(e)}
            
    def toggle_division_filter(self):
        """Toggle division filter - cycles through different division views.

        Two modes:
        1. Player is on track: Toggle between "All Divisions" and "My Division"
        2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)

        This allows spectators to focus on specific divisions, while active racers
        can quickly filter to just their competition.
        """
        player_on_track = self.player_car_idx is not None and any(
            d['car_idx'] == self.player_car_idx for d in self.race_data
        )

        if player_on_track:
            # Simple toggle for active racers: show my division or all
            self.show_only_my_division = not self.show_only_my_division
            self.current_division_filter = None
            button_text = "My Division" if self.show_only_my_division else "All Divisions"
            button_color = "#0FC436" if self.show_only_my_division else '#555555'
        else:
            # Spectator mode: cycle through divisions that have active drivers
            self.show_only_my_division = False

            # Build a list of divisions that currently have drivers in the session
            divisions_with_drivers = set()
            for driver_data in self.race_data:
                driver_color = self.get_driver_color(driver_data['driver_info'])
                for div_name, div_color in self.available_colors.items():
                    if div_color == driver_color and div_name not in ["Default", "All"]:
                        divisions_with_drivers.add(div_name)

            # Only show divisions that exist in this session, plus "All"
            available_options = [div for div in self.division_cycle_order
                               if div == "All" or div in divisions_with_drivers]

            # Cycle to the next division in order
            if self.current_division_filter is None:
                next_filter = available_options[0] if available_options else "All"
            else:
                try:
                    current_name = "All" if self.current_division_filter == "All" else self.current_division_filter
                    current_idx = available_options.index(current_name)
                    next_idx = (current_idx + 1) % len(available_options)  # Wrap around to start
                    next_filter = available_options[next_idx]
                except (ValueError, IndexError):
                    next_filter = available_options[0] if available_options else "All"
            
            if next_filter == "All":
                self.current_division_filter = None
                button_text = "All Divisions"
                button_color = '#555555'
            else:
                self.current_division_filter = next_filter
                button_text = next_filter
                button_color = self.available_colors[next_filter]
        
        self.division_btn.setText(button_text)
        self.division_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {button_color};
                color: white;
                border: none;
                padding: 4px 6px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: {button_color};
            }}
        """)
        self.scroll_area.verticalScrollBar().setValue(0)
        
    def on_manual_scroll(self):
        """Record when user manually scrolls, to temporarily disable auto-centering.

        Purpose: When user manually scrolls to look at other drivers, we don't
        want auto-center immediately yanking the view back to the player.

        Why this exists: Auto-centering is helpful but shouldn't fight user input.
        By recording scroll time, center_on_player() can check if enough time has
        passed (manual_scroll_timeout, default 5 seconds) before re-enabling.

        How it works:
            1. User scrolls -> this sets last_manual_scroll = now
            2. Auto-center checks: if (now - last_manual_scroll < 5s), skip centering
            3. After 5s of no scrolling, auto-center resumes

        Assumptions:
            - Connected to scroll_area.verticalScrollBar().valueChanged signal
        """
        self.last_manual_scroll = time.time()

    def resizeEvent(self, event):
        """Qt event handler: Window was resized by user or programmatically.

        Purpose: Keep the resize grip (bottom-right corner handle) positioned
        correctly as window size changes.

        Why this exists: The size grip is a widget that must be manually positioned.
        Qt doesn't auto-anchor it, so we must move it on every resize.

        Args:
            event: QResizeEvent from Qt (unused, but required by Qt signature)

        Assumptions:
            - size_grip widget exists (checked with hasattr)
            - Called automatically by Qt framework
        """
        super().resizeEvent(event)
        # Position size grip at bottom right corner
        if hasattr(self, 'size_grip'):
            rect = self.rect()
            self.size_grip.move(
                rect.width() - self.size_grip.width(),
                rect.height() - self.size_grip.height()
            )
        
    def load_color_config(self):
        """Load the driver-to-division mapping from JSON config file.

        Purpose: Each league maintains a JSON file that maps drivers to divisions
        (Pro, ProAm, Am, Rookie). This file is shared among league members so
        everyone sees consistent division colors.

        Returns:
            Dict with 'drivers' key containing list of driver entries:
            {'drivers': [
                {'id': '12345', 'name': 'John Doe', 'division': 'Pro'},
                ...
            ]}

        Why this exists: Different leagues have different division structures.
        Using a config file allows customization per league without code changes.

        File migration: Automatically converts old format (dict of drivers) to
        new format (drivers list) if needed.

        Assumptions:
            - File is valid JSON or doesn't exist (returns empty structure)
            - File path is set in self.color_config_file
        """
        if os.path.exists(self.color_config_file):
            try:
                with open(self.color_config_file, 'r') as f:
                    data = json.load(f)
                    
                    if isinstance(data, dict):
                        if 'drivers' in data:
                            return data
                        else:
                            # Migrate old format
                            migrated = {'drivers': []}
                            for key, division in data.items():
                                entry = {'division': division}
                                if key.isdigit():
                                    entry['id'] = key
                                    entry['name'] = ''
                                else:
                                    entry['name'] = key
                                migrated['drivers'].append(entry)
                            
                            with open(self.color_config_file, 'w') as f:
                                json.dump(migrated, f, indent=2)
                            return migrated
                    elif isinstance(data, list):
                        return {'drivers': []}
            except Exception as e:
                print(f"Error loading color config: {e}")
        return {'drivers': []}
        
    def load_settings(self):
        """Load user preferences from LeagueOverlay.config JSON file.

        Purpose: Persists window position, size, opacity, colors, and all user
        preferences between application sessions.

        Why this exists: Users want the overlay to remember their settings,
        especially window position and opacity, so they don't have to reconfigure
        every time they start the app.

        Settings loaded:
            - Window position (x, y) and size (width, height)
            - Opacity and refresh rate
            - Font size and color style
            - UI preferences (hide_headers, center_drivers, bold_drivers)
            - Division color customizations
            - Path to league-specific driver config file

        Assumptions:
            - File may not exist on first run (silently ignored)
            - Invalid JSON or missing keys are handled gracefully
            - Settings are validated elsewhere (e.g., opacity clamped to 0-1)
        """
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    league_config = data.get('league_config')
                    if league_config and os.path.exists(league_config):
                        self.color_config_file = league_config
                        self.driver_colors = self.load_color_config()

                        # IMPORTANT: Also reload the DivisionManager with the custom config
                        self.division_manager = DivisionManager(league_config)
                        self.available_colors = self.division_manager.division_colors
                    if data.get('opacity'):
                        self.opacity = data.get('opacity')
                    if data.get('refresh_rate'):
                        self.refresh_rate = data.get('refresh_rate')
                    if data.get('x'):
                        self.x = data.get('x')
                    if data.get('y'):
                        self.y = data.get('y')
                    if data.get('height'):
                        self.height = data.get('height')
                    if data.get('width'):
                        self.width = data.get('width')
                    if data.get('hide_headers'):
                        self.hide_headers = data.get('hide_headers')
                    if data.get('center_drivers'):
                        self.center_drivers = data.get('center_drivers')
                    if data.get('bold_drivers'):
                        self.bold_drivers = data.get('bold_drivers')
                    if data.get('font_size'):
                        self.font_size = data.get('font_size')
                    if data.get('row_color_style'):
                        self.row_color_style = data.get('row_color_style')
            except:
                pass
                
    def load_division_colors(self):
        """Load division colors"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    division_colors = data.get('division_colors', {})
                    colors = self.default_colors.copy()
                    colors.update(division_colors)
                    return colors
            except:
                pass
        return self.default_colors.copy()
        
    def save_settings(self):
        """Persist current settings to LeagueOverlay.config JSON file.

        Purpose: Automatically called when user moves/resizes window, closes app,
        or applies settings changes. Ensures preferences survive between sessions.

        Why this exists: Paired with load_settings() to provide persistent config.
        Called frequently (on window move, resize, close) to minimize data loss.

        Saves:
            - Current window geometry (position and size)
            - All user preferences (opacity, fonts, colors, etc.)
            - Path to active league config file

        Assumptions:
            - Write permissions exist in current directory
            - Failures are non-fatal (prints error, continues)
        """
        try:
            settings = {
                'league_config': self.color_config_file,
                'division_colors': self.available_colors,
                'x': self.geometry().x(),
                'y': self.geometry().y(),
                'height': self.geometry().height(),
                'width': self.geometry().width(),
                'opacity': self.opacity,
                'refresh_rate': self.refresh_rate,
                'hide_headers': self.hide_headers,
                'center_drivers': self.center_drivers,
                'bold_drivers': self.bold_drivers,
                'font_size': self.font_size,
                'row_color_style': self.row_color_style
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")
            
    def save_color_config(self) -> None:
        """Save color configuration - delegates to DivisionManager.

        Purpose: Called when user changes driver division assignments via
        right-click context menu. Ensures changes are persisted.

        Note: This method delegates to DivisionManager.save_config() to maintain
        single source of truth for division persistence logic.
        """
        try:
            self.division_manager.save_config()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save color config: {e}")

    def get_driver_division(self, driver_info: Dict[str, str]) -> Optional[str]:
        """Get the assigned division for a driver - delegates to DivisionManager.

        Lookup priority:
        1. Match by UserID (most reliable, survives name changes)
        2. Match by UserName (fallback)
        3. Return None if not found (will use "Default" color)

        Args:
            driver_info: Dictionary with 'UserID' and 'UserName' keys

        Returns:
            Division name ("Pro", "ProAm", "Am", "Rookie") or None

        Note:
            This method now delegates to DivisionManager to avoid duplicate logic.
            The division name maps to a color in available_colors.
        """
        return self.division_manager.get_driver_division(driver_info)

    def set_driver_division(self, driver_info: Dict[str, str], division_name: str) -> None:
        """Assign a driver to a division - delegates to DivisionManager.

        This is called from the right-click context menu on driver rows.
        Changes are immediately saved to the config file and UI refreshes.

        Args:
            driver_info: Dict with 'UserID' and 'UserName'
            division_name: "Pro", "ProAm", "Am", "Rookie", or "Default"
                          "Default" removes the driver from the config

        Note:
            This method now delegates to DivisionManager for the actual assignment,
            then triggers UI refresh. Single source of truth for division logic.
        """
        # Delegate to DivisionManager for assignment logic
        self.division_manager.set_driver_division(driver_info, division_name)

        # Update legacy self.driver_colors reference for backward compatibility
        self.driver_colors = self.division_manager.driver_colors

        # Save configuration
        self.save_color_config()

        # Refresh UI to show new color
        self.update_driver_row_color(driver_info)
        
    def update_driver_row_color(self, driver_info):
        """Update driver row color"""
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')
        
        for driver_data in self.displayed_data:
            data_info = driver_data.get('driver_info', {})
            data_id = data_info.get('UserID', '')
            data_name = data_info.get('UserName', '')
            
            if (user_id and data_id == user_id) or (user_name and data_name == user_name):
                # Trigger full refresh
                self.signals.update_data.emit(self.displayed_data.copy())
                break
                
    def get_driver_color(self, driver_info):
        """Get color for driver"""
        division_name = self.get_driver_division(driver_info)
        if division_name:
            return self.available_colors.get(division_name, self.available_colors["Default"])
        return self.available_colors["Default"]
        
    def refresh_driver_colors(self):
        """Refresh all driver colors"""
        self.driver_colors = self.load_color_config()
        if self.displayed_data:
            self.signals.update_data.emit(self.displayed_data.copy())
            
    def open_settings(self):
        """Open settings dialog"""
        dialog = SettingsDialog(self)
        result = dialog.exec()
        
        # After settings closed, update auto-hide behavior
        if self.hide_headers:
            if not self.hasFocus():
                self.hide_top_elements()
        else:
            self.show_top_elements()
            
    def hide_top_elements(self):
        """Hide title bar and status label"""
        if self.top_elements_visible:
            self.title_bar.hide()
            self.status_label.hide()
            self.top_elements_visible = False
            
    def show_top_elements(self):
        """Show title bar and status label"""
        if not self.top_elements_visible:
            self.title_bar.show()
            self.status_label.show()
            self.top_elements_visible = True
            
    def enterEvent(self, event):
        """Mouse entered window"""
        if self.hide_headers:
            # Cancel hide timer if active
            if self.hide_timer:
                self.killTimer(self.hide_timer)
                self.hide_timer = None
            self.show_top_elements()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Mouse left window"""
        if self.hide_headers:
            # Start hide timer (500ms delay)
            if self.hide_timer:
                self.killTimer(self.hide_timer)
            self.hide_timer = self.startTimer(500)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        """Window gained focus - update size grip"""
        super().focusInEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.update()

    def focusOutEvent(self, event):
        """Window lost focus - update size grip"""
        super().focusOutEvent(event)
        if hasattr(self, 'size_grip'):
            self.size_grip.update()
            
    def timerEvent(self, event):
        """Handle timer events for auto-hide"""
        if self.hide_timer and event.timerId() == self.hide_timer:
            self.killTimer(self.hide_timer)
            self.hide_timer = None
            if self.hide_headers:
                self.hide_top_elements()
        
    def close_application(self):
        """Close application"""
        self.save_settings()
        self.running = False
        QApplication.quit()
        
    def telemetry_loop(self):
        """Background thread that continuously reads data from iRacing SDK.

        Purpose: Runs in a separate thread to avoid blocking the UI. Continuously
        polls iRacing for telemetry data at the configured refresh rate.

        Why this exists: The iRacing SDK requires continuous polling. Running in
        a thread keeps the UI responsive while we wait for data.

        Flow:
            1. Try to connect to iRacing if not connected
            2. If connected, process telemetry data
            3. Sleep for refresh_rate seconds
            4. Repeat until self.running = False

        Thread safety: Uses self.signals (Qt signals) to communicate updates
        back to the main UI thread safely.

        Assumptions:
            - irsdk library is properly installed
            - Runs as daemon thread (dies when main thread exits)
            - self.refresh_rate is a positive float (seconds)
        """
        while self.running:
            try:
                if not self.is_connected:
                    if self.ir.startup():
                        self.is_connected = True
                        
                if self.is_connected:
                    if self.ir.is_connected and self.ir.is_initialized:
                        self.process_telemetry()
                    else:
                        self.is_connected = False
                        self.ir.shutdown()
                        
                time.sleep(self.refresh_rate)
                
            except Exception as e:
                print(f"Telemetry error: {e}")
                time.sleep(1)
                
    def calculate_real_time_positions(self, drivers, live_data):
        """Calculate real-time positions based on actual track position.

        This provides more accurate positioning than iRacing's official positions,
        which only update at the start/finish line. Real-time positions update
        constantly based on where each car is on track.

        Formula: total_track_position = current_lap + lap_distance_percentage
        Example: Car on lap 5, 30% through = 5.30
                 Car on lap 5, 90% through = 5.90 (ahead of the 30% car)
        """
        car_idx_lap = live_data['CarIdxLap']
        car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']
        car_idx_class_position = live_data['CarIdxClassPosition']

        if not car_idx_lap or not car_idx_lap_dist_pct or not car_idx_class_position:
            return []

        active_drivers = []

        for car_idx in range(len(car_idx_class_position)):
            # Position 0 means car is not active/participating
            if car_idx_class_position[car_idx] == 0:
                continue
            
            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break
            
            if not driver_info:
                continue

            # Multi-class support: only show cars in the player's class
            if self.player_car_class_id is not None:
                if driver_info.get('CarClassID') != self.player_car_class_id:
                    continue

            current_lap = car_idx_lap[car_idx]
            lap_pct = car_idx_lap_dist_pct[car_idx]

            if current_lap < 0:
                continue

            # Sanity check - percentage should be 0.0 to 1.0
            if lap_pct < 0 or lap_pct > 1:
                lap_pct = 0

            # Total track position: lap number + progress through current lap
            total_track_position = current_lap + lap_pct
            
            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'total_track_position': total_track_position,
                'current_lap': current_lap,
                'lap_pct': lap_pct,
                'official_position': car_idx_class_position[car_idx]
            })

        # Sort by track position (highest first = furthest ahead)
        active_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)

        # Assign real-time positions based on sorted order
        for i, driver in enumerate(active_drivers):
            driver['real_time_position'] = i + 1

        return active_drivers
        
    def get_official_positions(self, drivers, live_data):
        """Get positions from iRacing's official timing system (updates at start/finish line).

        Purpose: Used during practice/qualifying sessions where real-time position
        tracking isn't needed. Simpler than calculate_real_time_positions() since
        we just use iRacing's official positions directly.

        Why this exists: Practice/qualifying don't need the complexity of real-time
        tracking. Official positions are sufficient and more stable.

        Returns:
            List of driver dicts with 'official_position' sorted by that position

        Differences from calculate_real_time_positions():
            - No track position calculation (lap + lap%)
            - Uses official positions directly from iRacing
            - Faster, simpler, less CPU intensive

        Assumptions:
            - CarIdxClassPosition is available in live_data
            - Position 0 means not active/participating
        """
        car_idx_class_position = live_data['CarIdxClassPosition']
        
        if not car_idx_class_position:
            return []
        
        active_drivers = []
        
        for car_idx in range(len(car_idx_class_position)):
            if car_idx_class_position[car_idx] == 0:
                continue
            
            driver_info = None
            for driver in drivers:
                if driver.get('CarIdx') == car_idx:
                    driver_info = driver
                    break
            
            if not driver_info:
                continue
            
            if self.player_car_class_id is not None:
                if driver_info.get('CarClassID') != self.player_car_class_id:
                    continue
            
            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'official_position': car_idx_class_position[car_idx]
            })
        
        active_drivers.sort(key=lambda x: x['official_position'])
        
        return active_drivers
        
    def update_finish_status(self, live_data, current_session):
        """Track which drivers have finished the race after the checkered flag.

        IMPORTANT: iRacing shows the checkered flag when the leader crosses the line,
        but other drivers haven't finished yet. We need to track when each driver
        completes their current lap after the checkered to know their final position.

        This method:
        1. Identifies what lap the leader is on when checkered waves
        2. Waits for the leader to complete that lap (true finish)
        3. Tracks each subsequent driver as they finish their current lap
        4. Stores their official position at the moment they finish
        """
        # SessionState < 5 means race hasn't reached checkered flag yet
        if self.ir['SessionState'] < 5:
            return

        car_idx_lap = live_data['CarIdxLap']
        car_idx_class_position = live_data['CarIdxClassPosition']

        # PHASE 1: Identify the "finish lap" - the lap number the leader needs to complete
        if self.leader_last_lap is None:
            # First time after checkered - determine what lap needs to be completed
            for car_idx in range(len(car_idx_class_position)):
                if car_idx_class_position[car_idx] == 1:
                    # Verify this car is in player's class (multi-class racing support)
                    if self.player_car_class_id is not None:
                        try:
                            drivers = self.ir['DriverInfo']['Drivers']
                            driver_class_id = None
                            for d in drivers:
                                if d.get('CarIdx') == car_idx:
                                    driver_class_id = d.get('CarClassID')
                                    break
                            if driver_class_id != self.player_car_class_id:
                                continue
                        except (KeyError, TypeError):
                            continue

                    # Store the lap the leader is on - this is the lap that needs to finish
                    # When this lap increments, the leader has truly finished
                    self.leader_last_lap = car_idx_lap[car_idx] if car_idx < len(car_idx_lap) else 0
                    break

        # PHASE 2: Wait for the leader to complete their finish lap
        if self.leader_last_lap is not None and not self.leader_finished:
            # Find whoever is currently in P1 (might have changed due to a last-lap pass)
            current_leader_idx = None
            for car_idx in range(len(car_idx_class_position)):
                if car_idx_class_position[car_idx] == 1:
                    # Verify this car is in player's class (multi-class racing support)
                    if self.player_car_class_id is not None:
                        try:
                            drivers = self.ir['DriverInfo']['Drivers']
                            driver_class_id = None
                            for d in drivers:
                                if d.get('CarIdx') == car_idx:
                                    driver_class_id = d.get('CarClassID')
                                    break
                            if driver_class_id != self.player_car_class_id:
                                continue
                        except (KeyError, TypeError):
                            continue

                    current_leader_idx = car_idx
                    break

            # Check if the current leader has completed the lap (lap counter incremented)
            if current_leader_idx is not None and current_leader_idx < len(car_idx_lap):
                current_leader_lap = car_idx_lap[current_leader_idx]
                if current_leader_lap > self.leader_last_lap:
                    self.leader_finished = True
                    # Add the leader to finished drivers and capture their position
                    self.finished_drivers.add(current_leader_idx)
                    if current_leader_idx < len(car_idx_class_position):
                        if current_leader_idx in self.driver_snapshots:
                            self.driver_snapshots[current_leader_idx]['official_position'] = car_idx_class_position[current_leader_idx]

        # PHASE 3: Once leader is done, track all other drivers as they complete their laps
        if self.leader_finished:
            for car_idx in range(len(car_idx_lap)):
                if car_idx in self.finished_drivers:
                    continue

                if self.player_car_class_id is not None:
                    try:
                        drivers = self.ir['DriverInfo']['Drivers']
                        driver_class_id = None
                        for d in drivers:
                            if d.get('CarIdx') == car_idx:
                                driver_class_id = d.get('CarClassID')
                                break

                        if driver_class_id != self.player_car_class_id:
                            continue
                    except (KeyError, TypeError):
                        continue

                if car_idx not in self.driver_snapshots:
                    continue

                prev_lap = self.driver_snapshots[car_idx].get('current_lap', 0)
                current_lap = car_idx_lap[car_idx]

                # When lap counter increments, driver has crossed finish line and completed race
                if current_lap > prev_lap:
                    self.finished_drivers.add(car_idx)
                    # Capture the official position at the moment they finish
                    # This locks in their final result and prevents position changes
                    if car_idx < len(car_idx_class_position):
                        self.driver_snapshots[car_idx]['official_position'] = car_idx_class_position[car_idx]
                    
    def get_position_from_results(self, current_session, car_idx):
        """Look up a car's final position from session results.

        Purpose: After race ends, iRacing provides complete results in SessionInfo.
        This extracts the final class position for a specific car.

        Why this exists: Used for:
            - Finished drivers (to lock in their final position)
            - Disconnected drivers after checkered (to show where they finished)

        Args:
            current_session: Session dict from SessionInfo['Sessions'][session_num]
            car_idx: The car index to look up

        Returns:
            1-based position (int) or -1 if not found

        Assumptions:
            - Session has ResultsPositions array (only after session ends)
            - ClassPosition is 0-based, so we add 1
        """
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'ClassPosition' in driver:
                        return driver['ClassPosition'] + 1
        except (KeyError, TypeError, IndexError):
            pass
        return -1
        
    def get_fastest_lap_time(self, current_session):
        """Find the fastest lap time in the session for gap estimation.

        Purpose: When cars are on different laps, we estimate time gaps by
        multiplying lap difference by average lap time. This finds the fastest
        lap as a reasonable estimate.

        Why this exists: Estimating gaps between cars on different laps requires
        knowing typical lap time. Fastest lap is used as a baseline (assumes
        cars lap at similar pace to the fastest).

        Returns:
            Fastest lap time in seconds (float), or 90 if none found

        Why 90 seconds: Fallback for when no laps recorded yet (session start).
        90s is a reasonable default that won't cause divide-by-zero or absurd gaps.

        Assumptions:
            - ResultsPositions exists and has FastestTime field
            - FastestTime of 0 means no lap recorded (skipped)
        """
        fastest_time = float('inf')
        for driver in current_session['ResultsPositions']:
            best_lap = driver['FastestTime']
            if 0 < best_lap < fastest_time:
                fastest_time = best_lap
        return fastest_time if fastest_time != float('inf') else 90
        
    def get_best_lap_from_session_info(self, current_session, car_idx):
        """Look up a specific car's fastest lap time from session results.

        Purpose: In practice/qualifying, gaps are shown as delta to best lap
        times, not real-time gaps. This retrieves a car's personal best.

        Why this exists: Practice/qualifying use different gap logic than racing.
        Instead of "5.3s behind," it shows "+0.234" (delta to car ahead's best lap).

        Args:
            current_session: Session dict from SessionInfo
            car_idx: Which car to look up

        Returns:
            Best lap time in seconds (float), or 90 if not found/no laps

        Why 90 seconds: Same reason as get_fastest_lap_time() - safe fallback.

        Assumptions:
            - ResultsPositions exists (practice/qualifying sessions)
            - FastestTime field is present
        """
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'FastestTime' in driver:
                        return driver['FastestTime']
        except (KeyError, TypeError, IndexError):
            pass
        return 90
    
    def reset_fields(self) -> None:
        """Clear all session-specific tracking data.

        Purpose: Called when switching sessions (practice->qualify->race) or when
        session number changes. Ensures we start fresh with no stale data.

        Why this exists: Data from one session (like finish tracking) should not
        carry over to the next session. Each session needs clean state.

        Clears:
            - Race state tracker (finish tracking, snapshots, gaps)
            - Player identification (car_idx and class_id)
            - Legacy state variables for backward compatibility

        Called by:
            - Session number change detection in process_telemetry()
            - Session type change (practice -> qualifying -> race)

        Assumptions: None - safe to call at any time
        """
        # Clear legacy state variables (still used by existing code)
        self.driver_snapshots = {}
        self.leader_finished = False
        self.finished_drivers = set()
        self.leader_car_idx = None
        self.leader_last_lap = None
        self.final_gaps = {}

        # Also reset the race state tracker for consistency
        self.race_state_tracker.reset()

        # Clear player identification
        self.player_car_idx = None
        self.player_car_class_id = None
        
    def process_telemetry(self):
        """Process telemetry data"""
        try:
            if self.current_session_num and self.current_session_num != self.ir['SessionNum']:
                self.reset_fields()
                self.current_session_num = self.ir['SessionNum']
                
            try:
                drivers = self.ir['DriverInfo']['Drivers']
                if not drivers:
                    return
            except (KeyError, TypeError) as e:
                print(f"Error getting driver info: {e}")
                return
            
            try:
                session_info = self.ir['SessionInfo']
                session_num = self.ir['SessionNum']
                current_session = session_info['Sessions'][session_num]
                session_type = current_session['SessionType']
                is_race = session_type.lower() == 'race'
            except (KeyError, TypeError, IndexError):
                is_race = False
                
            if self.current_session_num != session_num or self.current_session_type != session_type:
                self.reset_fields()
                self.current_session_num = session_num
                self.current_session_type = session_type
            
            if self.player_car_idx is None:
                try:
                    self.player_car_idx = self.ir['PlayerCarIdx']
                except (KeyError, TypeError):
                    self.player_car_idx = None
                    
            if self.player_car_idx is not None and self.player_car_class_id is None:
                try:
                    for driver in drivers:
                        if driver.get('CarIdx') == self.player_car_idx:
                            self.player_car_class_id = driver.get('CarClassID')
                            break
                except (KeyError, TypeError):
                    pass
            
            live_data = self.ir
            if not live_data:
                return

            if is_race:
                self.update_finish_status(live_data, current_session)
                active_drivers = self.calculate_real_time_positions(drivers, live_data)
                position_key = 'real_time_position' #if not self.leader_finished else 'official_position'
                
                if active_drivers:
                    # Update snapshots for all actively racing cars
                    for driver_data in active_drivers:
                        self.driver_snapshots[driver_data['car_idx']] = driver_data.copy()
                        self.driver_snapshots[driver_data['car_idx']]['disconnected'] = False

                    # DISCONNECTED DRIVER HANDLING
                    # If a driver was racing but is no longer in active_drivers, they've disconnected
                    # Keep them in the list so spectators can see who DNF'd
                    active_car_indices = {d['car_idx'] for d in active_drivers}
                    for car_idx, snapshot in self.driver_snapshots.items():
                        if car_idx not in active_car_indices:
                            # This driver disconnected or retired
                            if self.ir['SessionState'] < 5:
                                # Still racing - mark as DC, position unknown
                                snapshot['official_position'] = -1
                            else:
                                # After checkered - get their final position from results
                                snapshot['official_position'] = self.get_position_from_results(current_session, car_idx)
                            disconnected_driver = snapshot.copy()
                            if self.ir['SessionState'] < 5:
                                disconnected_driver['disconnected'] = True  # Shows "(DC)" in gap column
                            # Only show disconnected drivers if they have a valid position or race is ongoing
                            if self.ir['SessionState'] < 5 or disconnected_driver['official_position'] >= 0:
                                active_drivers.append(disconnected_driver)
                    
                    active_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)
                    
                    for i, driver in enumerate(active_drivers):
                        driver['real_time_position'] = i + 1
            else:
                active_drivers = self.get_official_positions(drivers, live_data)
                position_key = 'official_position'
                
            if not active_drivers:
                return
            
            all_drivers_with_colors = []
            for driver in active_drivers:
                driver_color = self.get_driver_color(driver['driver_info'])
                all_drivers_with_colors.append({
                    'car_idx': driver['car_idx'],
                    'position': driver[position_key] if position_key == 'official_position' or driver['car_idx'] not in self.finished_drivers else driver['official_position'],
                    'color': driver_color,
                    'official_position': driver.get('official_position', driver[position_key])
                })
            
            division_positions = {}
            for color in set(d['color'] for d in all_drivers_with_colors):
                same_color = [d for d in all_drivers_with_colors if d['color'] == color]
                same_color.sort(key=lambda x: x['position'])
                for i, driver in enumerate(same_color):
                    division_positions[driver['car_idx']] = i + 1
            
            self.race_data = []
            
            for driver in active_drivers:
                car_idx = driver['car_idx']
                driver_info = driver['driver_info']
                
                if car_idx in self.finished_drivers:
                    position = self.get_position_from_results(current_session, car_idx)
                else:
                    position = driver[position_key]
                
                current_driver_color = self.get_driver_color(driver_info)
                current_color_position = division_positions.get(car_idx, position)
                
                # GAP CALCULATION: Show time/distance behind the car ahead in the same division
                # Now uses GapCalculator for consistent formatting
                if current_color_position == 1:
                    gap = GapCalculator.format_gap_display(is_leader=True)
                elif car_idx in self.finished_drivers:
                    # Once finished, gap is frozen from the last update before crossing the line
                    gap = self.final_gaps.get(car_idx, "")
                elif is_race:
                    # LIVE GAP CALCULATION during race
                    # Find all drivers in the same division/color to calculate gap within division
                    same_color_drivers = []
                    for temp_driver in active_drivers:
                        temp_color = self.get_driver_color(temp_driver['driver_info'])
                        if temp_color == current_driver_color:
                            same_color_drivers.append({
                                'car_idx': temp_driver['car_idx'],
                                'position': temp_driver[position_key],
                                'total_track_position': temp_driver['total_track_position'],
                                'current_lap': temp_driver['current_lap'],
                                'lap_pct': temp_driver['lap_pct']
                            })

                    same_color_drivers.sort(key=lambda x: x['position'])

                    # Find this driver's position within their division
                    current_pos_index = None
                    for i, temp_driver in enumerate(same_color_drivers):
                        if temp_driver['car_idx'] == car_idx:
                            current_pos_index = i
                            break

                    # Calculate gap to the car ahead in the same division
                    if current_pos_index is not None and current_pos_index > 0:
                        car_ahead_idx = same_color_drivers[current_pos_index - 1]['car_idx']

                        if car_ahead_idx in self.finished_drivers:
                            # Car ahead has finished, use frozen gap
                            gap = self.final_gaps.get(car_idx, "")
                        else:
                            # Both cars still racing - calculate live time gap using GapCalculator
                            car_idx_est_time = live_data['CarIdxEstTime']
                            current_est_time = car_idx_est_time[car_idx]
                            ahead_est_time = car_idx_est_time[car_ahead_idx]

                            time_gap_raw = None
                            # If both cars on same lap, use iRacing's estimated time (most accurate)
                            if current_est_time > 0 and ahead_est_time > 0 and same_color_drivers[current_pos_index - 1]['current_lap'] == driver['current_lap']:
                                # Use GapCalculator for time gap calculation
                                time_gap_raw = GapCalculator.calculate_time_gap(ahead_est_time, current_est_time)
                            else:
                                # Different laps - estimate gap based on track position difference
                                position_diff = same_color_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']
                                time_gap_raw = position_diff * self.get_fastest_lap_time(current_session)

                            # Calculate exact lap distance difference for lap-based gaps
                            lap_difference = same_color_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']
                            lap_gap = GapCalculator.calculate_lap_gap(same_color_drivers[current_pos_index - 1]['total_track_position'], driver['total_track_position'])

                            # Use GapCalculator to format the gap display
                            # Handle negative time gaps (shouldn't happen but be safe)
                            if time_gap_raw is not None and time_gap_raw < 0:
                                time_gap_raw = abs(time_gap_raw)

                            # Use GapCalculator for standard formatting
                            gap = GapCalculator.format_gap_display(
                                time_gap=time_gap_raw,
                                lap_gap=lap_gap
                            )

                            # Store gap continuously - used when driver finishes to freeze the display
                            if gap and gap != "":
                                self.final_gaps[car_idx] = gap
                    else:
                        gap = ""
                else:
                    # Practice/Qualifying: Calculate gap based on best lap times
                    same_color_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
                    same_color_drivers.sort(key=lambda x: x['position'])

                    if len(same_color_drivers) >= current_color_position - 1:
                        car_ahead_idx = same_color_drivers[current_color_position - 2]['car_idx']
                        current_best = self.get_best_lap_from_session_info(current_session, car_idx)
                        ahead_best = self.get_best_lap_from_session_info(current_session, car_ahead_idx)
                        if current_best > 0 and ahead_best > 0:
                            # Calculate gap (current - ahead, so positive = behind)
                            time_gap_raw = current_best - ahead_best
                            # Format to 3 decimal places for practice/quali precision
                            gap = f"{time_gap_raw:.3f}"
                        else:
                            gap = ""
                    else:
                        gap = ""
                
                is_player = (car_idx == self.player_car_idx)

                self.race_data.append({
                    'position': position,
                    'division_position': current_color_position,
                    'car_number': driver_info.get('CarNumber', ''),
                    'driver_name': driver_info.get('UserName', ''),
                    'driver_info': {
                        'UserID': driver_info.get('UserID', ''),
                        'UserName': driver_info.get('UserName', '')
                    },
                    'gap': gap if not driver.get('disconnected', False) else "(DC)",
                    'car_idx': car_idx,
                    'is_player': is_player
                })
            
            self.race_data.sort(key=lambda x: x['position'])
            
        except Exception as e:
            print(f"Processing error: {e}")
            
    def update_gui(self):
        """Update GUI (called by timer)"""
        try:
            if time.time() - self.startup_time < 3.0:
                return
            
            if self.is_connected:
                try:
                    session_info = self.ir['SessionInfo']
                    current_session = session_info['Sessions'][self.ir['SessionNum']]
                    session_type = current_session['SessionType']
                    status_text = f"Connected - Live Data ({session_type})"
                except (KeyError, TypeError, IndexError, AttributeError):
                    status_text = "Connected - Live Data"
                
                self.signals.update_status.emit(status_text, 'green')
                
                # Filter and emit data
                if self.race_data:
                    if self.show_only_my_division and self.player_car_idx is not None:
                        player_color = None
                        for driver_data in self.race_data:
                            if driver_data['car_idx'] == self.player_car_idx:
                                player_color = self.get_driver_color(driver_data['driver_info'])
                                break
                        
                        if player_color:
                            current_data = [d for d in self.race_data if self.get_driver_color(d['driver_info']) == player_color]
                        else:
                            current_data = self.race_data
                    elif self.current_division_filter is not None:
                        division_color = self.available_colors.get(self.current_division_filter)
                        if division_color:
                            current_data = [d for d in self.race_data if self.get_driver_color(d['driver_info']) == division_color]
                        else:
                            current_data = self.race_data
                    else:
                        current_data = self.race_data
                    
                    self.signals.update_data.emit(current_data)
            else:
                self.signals.update_status.emit("Connecting to iRacing...", 'orange')
                
        except Exception as e:
            print(f"GUI update error: {e}")
            
    def display_race_data(self, data):
        """Display race data (thread-safe slot)"""
        if not data:
            return
        
        # Clear existing widgets
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new driver rows
        for driver_data in data:
            row = self.create_driver_row(driver_data)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row)
        
        # Auto-center on player
        if (self.player_car_idx is not None and 
            time.time() - self.last_manual_scroll > self.manual_scroll_timeout):
            self.center_on_player(data)
        
        self.displayed_data = data.copy()
        
    def center_on_player(self, current_data):
        """Auto-center the scroll view on the player's position.

        This only activates if the user hasn't manually scrolled recently
        (see manual_scroll_timeout). Helps keep player visible during races
        without fighting manual scrolling.
        """
        if not current_data or self.player_car_idx is None:
            return

        # Find the player in the current display data
        player_index = None
        for i, driver_data in enumerate(current_data):
            if driver_data['car_idx'] == self.player_car_idx:
                player_index = i
                break

        if player_index is None:
            return

        # Force update to ensure proper calculation
        self.scroll_area.verticalScrollBar().update()
        QApplication.processEvents()

        scrollbar = self.scroll_area.verticalScrollBar()

        # Calculate the height per item
        total_items = len(current_data)
        if total_items == 0:
            return

        # Get the visible height and total scrollable height
        viewport_height = self.scroll_area.viewport().height()
        total_height = scrollbar.maximum() + viewport_height

        if total_height <= viewport_height:
            # Everything fits in the viewport, no need to scroll
            return

        # Calculate height per item (including spacing)
        item_height = total_height / total_items

        # Calculate scroll position to center player vertically in viewport
        # We want player row to be at (viewport_height / 2)
        player_top_position = player_index * item_height
        target_scroll = player_top_position - (viewport_height / 2) + (item_height / 2)

        # Clamp to valid scroll range [0, maximum]
        target_scroll = max(0, min(target_scroll, scrollbar.maximum()))

        scrollbar.setValue(int(target_scroll))
        
    def create_driver_row(self, driver_data):
        """Create a driver row widget with styling based on color style.

        Three color styles supported:
        1. Default: Black background, colored text, player gets gradient glow
        2. Alternate: Colored background, black text, player gets white border
        3. Outline: Black background, colored border and text, player gets gradient glow
        """
        driver_color = self.get_driver_color(driver_data.get('driver_info', {}))

        # Determine styling based on selected color style
        is_player = driver_data.get('is_player', False)

        if self.row_color_style == "Alternate":
            # ALTERNATE SCHEME: Division color fills the entire row background
            # Alternate: colored background, black text
            base_bg = driver_color
            bg_style = f"background-color: {self.get_bg_color(base_bg)};"
            text_color = "#000000"
            gap_color = "#000000"
            # Player gets white outline with colored cell borders
            if is_player:
                # Create container for white border
                container_widget = QWidget()
                container_widget.setStyleSheet("background-color: white; padding: 2px;")
                container_layout = QVBoxLayout(container_widget)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)

                # Inner row widget with division color background
                row_widget = QWidget()
                row_widget.setStyleSheet(bg_style)
                row_widget.setAttribute(Qt.WA_Hover, True)
                container_layout.addWidget(row_widget)
                border_style = ""
            else:
                row_widget = QWidget()
                row_widget.setStyleSheet(bg_style)
                container_widget = None
                border_style = ""

        elif self.row_color_style == "Outline":
            # OUTLINE SCHEME: Black background with colored border and text
            base_bg = "#000000"
            text_color = driver_color
            gap_color = "white"
            # Player gets gradient glow instead of border
            if is_player:
                border_style = ""  # No border for player
                bg_style = f"background: {self.create_gradient_background(driver_color)};"
            else:
                border_style = f"border: 1px solid {driver_color};"
                bg_style = f"background-color: {self.get_bg_color(base_bg)};"
            row_widget = QWidget()
            row_widget.setStyleSheet(f"{bg_style} {border_style}")
            container_widget = None
        else:
            # DEFAULT SCHEME: Black background with colored text
            text_color = driver_color
            gap_color = "white"
            border_style = ""
            # Player gets gradient glow effect
            if is_player:
                bg_style = f"background: {self.create_gradient_background(driver_color)};"
            else:
                bg_style = f"background-color: {self.get_bg_color('#000000')};"
            row_widget = QWidget()
            row_widget.setStyleSheet(f"{bg_style} {border_style}")
            container_widget = None

        layout = QGridLayout(row_widget)
        if self.row_color_style == "Outline":
            # No spacing for outline mode to avoid inner cell borders
            layout.setContentsMargins(3, 2, 3, 2)
            layout.setSpacing(0)
            layout.setHorizontalSpacing(0)
            layout.setVerticalSpacing(0)
        elif self.row_color_style == "Alternate" and is_player:
            # Same spacing as non-player rows to show cell borders
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)
        else:
            layout.setContentsMargins(2, 2, 2, 2)
            layout.setSpacing(2)

        layout.setColumnStretch(0, 11)
        layout.setColumnStretch(1, 11)
        layout.setColumnStretch(2, 13)
        layout.setColumnStretch(3, 46)
        layout.setColumnStretch(4, 19)

        font_weight = "bold" if driver_data.get('is_player', False) or self.bold_drivers else "normal"

        # Handle label backgrounds and borders
        if self.row_color_style == "Outline":
            # Outline mode: transparent labels, no borders
            label_bg = "transparent"
            label_border = "border: none;"
        elif self.row_color_style == "Alternate" and is_player:
            # Alternate player row: with cell borders
            label_bg = self.get_bg_color(base_bg) if 'base_bg' in locals() else self.get_bg_color('#000000')
            label_border = ""
        elif is_player and self.row_color_style == "Default":
            # For gradient background in Default, use tinted color for labels
            label_bg = self.blend_color_with_black(driver_color, 0.25)
            label_border = ""
        else:
            # Normal backgrounds
            label_bg = self.get_bg_color(base_bg) if 'base_bg' in locals() else self.get_bg_color('#000000')
            label_border = ""

        # Position
        pos_label = QLabel(str(driver_data.get('position', '')))
        pos_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        pos_label.setAlignment(Qt.AlignCenter)
        pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        pos_label.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )
        layout.addWidget(pos_label, 0, 0)

        # Division Position
        div_pos_label = QLabel(str(driver_data.get('division_position', '')))
        div_pos_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        div_pos_label.setAlignment(Qt.AlignCenter)
        div_pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        div_pos_label.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )
        layout.addWidget(div_pos_label, 0, 1)

        # Car Number
        car_label = QLabel(str(driver_data.get('car_number', '')))
        car_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        car_label.setAlignment(Qt.AlignCenter)
        car_label.setContextMenuPolicy(Qt.CustomContextMenu)
        car_label.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )
        layout.addWidget(car_label, 0, 2)

        # Driver Name
        name_align = Qt.AlignCenter if self.center_drivers else Qt.AlignLeft
        name_label = QLabel(driver_data.get('driver_name', ''))
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.get_font_size('data')};
                font-weight: {font_weight};
                padding-left: 0.5px;
                {label_border}
            }}
        """)
        name_label.setAlignment(name_align | Qt.AlignVCenter)
        # Prevent name from expanding beyond allocated width
        name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_label.setWordWrap(False)
        name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        name_label.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )
        layout.addWidget(name_label, 0, 3)

        # Gap
        gap_label = QLabel(driver_data.get('gap', ''))
        gap_label.setStyleSheet(f"""
            QLabel {{
                color: {gap_color};
                background-color: {label_bg};
                font-size: {self.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        gap_label.setAlignment(Qt.AlignCenter)
        gap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        gap_label.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )
        layout.addWidget(gap_label, 0, 4)

        # Context menu
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda: self.show_context_menu(driver_data)
        )

        # If container exists, also add context menu to it
        if container_widget:
            container_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            container_widget.customContextMenuRequested.connect(
                lambda: self.show_context_menu(driver_data)
            )

        return container_widget if container_widget else row_widget
        
    def show_context_menu(self, driver_data):
        """Display right-click menu to assign driver to a division.

        Purpose: Provides quick UI to change a driver's division without opening
        settings or editing JSON files manually.

        Why this exists: During a race, league admins can quickly assign new
        drivers to divisions by right-clicking their name.

        Flow:
            1. User right-clicks any part of a driver row
            2. Menu shows: Pro, ProAm, Am, Rookie, Default
            3. User clicks division -> set_driver_division() -> saves to JSON
            4. UI refreshes with new color

        Args:
            driver_data: Dict with 'driver_info' containing UserID and UserName

        Assumptions:
            - available_colors dict has all division names
            - Called from driver row widgets' customContextMenuRequested signal
        """
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #333333;
                color: white;
                border: 1px solid #555555;
            }
            QMenu::item:selected {
                background-color: #555555;
            }
        """)

        menu.addAction("Change Division").setEnabled(False)
        menu.addSeparator()

        driver_info = driver_data.get('driver_info', {})

        for division_name in self.available_colors.keys():
            action = menu.addAction(division_name)
            action.triggered.connect(
                lambda checked, d=division_name, info=driver_info:
                self.set_driver_division(info, d)
            )

        # Use cursor position directly to avoid coordinate mapping issues
        menu.exec(QCursor.pos())
        
    def update_status_label(self, text, color):
        """Update the status message and color (thread-safe Qt slot).

        Purpose: Display connection status and session type at top of overlay.
        Examples: "Connecting...", "Connected - Live Data (Race)", "Update available"

        Why this exists: Telemetry thread needs to communicate status to UI thread.
        Qt requires slots to be called from signals for thread safety.

        Args:
            text: Status message to display
            color: "green" (connected), "orange" (connecting), or hex like "#00FF00"

        Thread safety: This is a Qt slot connected to self.signals.update_status,
        so it's safe to call from the telemetry background thread.

        Assumptions:
            - status_label widget exists
            - update_status_style() handles color setting
        """
        self.status_label.setText(text)
        self.update_status_style(color)
        
    # Mouse events for dragging the frameless window
    def mousePressEvent(self, event):
        """Qt event handler: Mouse button pressed in window.

        Purpose: Enable dragging the frameless window by its title bar.

        Why this exists: With Qt.FramelessWindowHint, we lose the default OS
        window dragging. This reimplements it for the title bar area.

        How it works: Stores the click position offset, used in mouseMoveEvent()
        to calculate new window position while dragging.

        Assumptions:
            - Title bar height is 30 pixels
            - Only left-click drags
        """
        if event.button() == Qt.LeftButton:
            # Check if in title bar for dragging
            if event.position().y() < 30:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        """Qt event handler: Mouse moved while button held.

        Purpose: Update window position during drag operation.

        Why this exists: Completes the drag functionality started in mousePressEvent().

        Assumptions:
            - drag_position was set in mousePressEvent()
            - Left button is still held
        """
        if event.buttons() == Qt.LeftButton:
            if not self.drag_position.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

    def mouseReleaseEvent(self, event):
        """Qt event handler: Mouse button released.

        Purpose: End drag operation and save new window position to config.

        Why this exists: Ensures window position is persisted immediately after
        user moves the window, not just on app close (in case of crash).

        Assumptions: Left button release ends drag
        """
        self.drag_position = QPoint()
        # Save settings when user finishes moving/resizing
        if event.button() == Qt.LeftButton:
            self.save_settings()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: SETTINGS DIALOG (UI Component)
# ═══════════════════════════════════════════════════════════════════════════
#
# Settings dialog for user preferences and configuration:
# - SettingsDialog: Modal dialog for overlay configuration
#
# TO SPLIT: Move this section to ui_components.py (with Section 2 components)
# ═══════════════════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    """Modal settings dialog for configuring overlay appearance and behavior.

    Purpose: Provides a user-friendly GUI for all configurable options without
    editing JSON files or using command-line arguments.

    Settings provided:
        - Driver color config file (create new or load existing)
        - Window opacity (0.10 to 1.00 in 0.05 increments)
        - Refresh rate (0.25 to 5.0 seconds in 0.25 increments)
        - Font size (Small/Medium/Large/Extra Large)
        - Row color style (Default/Alternate/Outline)
        - UI preferences (auto-hide headers, center names, bold rows)
        - Division colors (customize Pro/ProAm/Am/Rookie colors)

    Why this exists: Users shouldn't need to manually edit config files.
    This provides safe, validated, live-preview access to all settings.

    Features:
        - Live opacity preview (changes as you drag slider)
        - Cancel reverts opacity changes
        - Reset to defaults button
        - Shows update notification if new version available
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_overlay = parent
        self.setWindowTitle("BB's League Overlay - Settings")
        self.setModal(True)
        self.setFixedSize(300, 705)

        self.original_opacity = parent.opacity  # For canceling changes

        self.setup_ui()
        
    def setup_ui(self):
        """Setup settings UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Config section
        config_group = QFrame()
        config_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(8)
        
        config_title = QLabel("Driver Color Configuration")
        config_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        config_layout.addWidget(config_title)
        
        # Current config row
        config_file_layout = QHBoxLayout()
        config_file_label = QLabel("Current config file:")
        config_file_label.setStyleSheet("font-size: 9pt; color: white; border: none;")
        config_file_layout.addWidget(config_file_label)
        
        self.current_config_label = QLabel(os.path.basename(self.parent_overlay.color_config_file))
        self.current_config_label.setStyleSheet("""
            font-size: 8pt; 
            color: white; 
            border: none; 
            background-color: #404040;
            padding: 2px 6px;
        """)
        config_file_layout.addWidget(self.current_config_label, 1)
        config_layout.addLayout(config_file_layout)
        
        config_btn_layout = QHBoxLayout()
        config_btn_layout.setSpacing(5)
        
        new_config_btn = QPushButton("Create New")
        new_config_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: white;
                padding: 4px 8px;
                border: none;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        new_config_btn.clicked.connect(self.create_new_config)
        config_btn_layout.addWidget(new_config_btn)
        
        load_config_btn = QPushButton("Load")
        load_config_btn.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: white;
                padding: 4px 8px;
                border: none;
                font-size: 8pt;
            }
            QPushButton:hover {
                background-color: #505050;
            }
        """)
        load_config_btn.clicked.connect(self.load_config)
        config_btn_layout.addWidget(load_config_btn)
        
        config_layout.addLayout(config_btn_layout)
        layout.addWidget(config_group)
        
        # Window settings
        window_group = QFrame()
        window_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(8)
        
        window_title = QLabel("Window Settings")
        window_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        window_layout.addWidget(window_title)
        
        # Opacity with value display
        opacity_row = QHBoxLayout()
        opacity_label = QLabel("Opacity:")
        opacity_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 100px;")
        opacity_row.addWidget(opacity_label)
        
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setMinimum(2)  # 0.10
        self.opacity_slider.setMaximum(20)  # 1.00
        self.opacity_slider.setSingleStep(1)  # 0.05 increment
        self.opacity_slider.setPageStep(1)
        self.opacity_slider.setValue(int(self.parent_overlay.opacity * 20))
        self.opacity_slider.valueChanged.connect(self.on_opacity_change)
        opacity_row.addWidget(self.opacity_slider)
        
        self.opacity_value_label = QLabel(f"{self.parent_overlay.opacity:.2f}")
        self.opacity_value_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 35px;")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value_label.setText(f"{v/20:.2f}")
        )
        opacity_row.addWidget(self.opacity_value_label)
        window_layout.addLayout(opacity_row)
        
        # Refresh rate with value display
        refresh_row = QHBoxLayout()
        refresh_label = QLabel("Refresh Rate (sec):")
        refresh_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 100px;")
        refresh_row.addWidget(refresh_label)
        
        self.refresh_slider = QSlider(Qt.Horizontal)
        self.refresh_slider.setMinimum(1)  # 0.25 seconds
        self.refresh_slider.setMaximum(20)  # 5.0 seconds
        self.refresh_slider.setSingleStep(1)  # 0.25 increment
        self.refresh_slider.setPageStep(1)
        self.refresh_slider.setValue(int(self.parent_overlay.refresh_rate * 4))
        refresh_row.addWidget(self.refresh_slider)
        
        self.refresh_value_label = QLabel(f"{self.parent_overlay.refresh_rate:.2f}")
        self.refresh_value_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 35px;")
        self.refresh_slider.valueChanged.connect(
            lambda v: self.refresh_value_label.setText(f"{v/4:.2f}")
        )
        refresh_row.addWidget(self.refresh_value_label)
        window_layout.addLayout(refresh_row)

        # Font size selector
        font_size_row = QHBoxLayout()
        font_size_label = QLabel("Font Size:")
        font_size_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 100px;")
        font_size_row.addWidget(font_size_label)

        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems(["Small", "Medium", "Large", "Extra Large"])
        self.font_size_combo.setCurrentText(self.parent_overlay.font_size)
        self.font_size_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: white;
                border: 1px solid #555555;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QComboBox:hover {
                background-color: #505050;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: white;
                selection-background-color: #505050;
                border: 1px solid #555555;
            }
        """)
        font_size_row.addWidget(self.font_size_combo)
        window_layout.addLayout(font_size_row)

        # Row color style selector
        color_style_row = QHBoxLayout()
        color_style_label = QLabel("Row Color Style:")
        color_style_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 100px;")
        color_style_row.addWidget(color_style_label)

        self.color_style_combo = QComboBox()
        self.color_style_combo.addItems(["Default", "Alternate", "Outline"])
        self.color_style_combo.setCurrentText(self.parent_overlay.row_color_style)
        self.color_style_combo.setStyleSheet("""
            QComboBox {
                background-color: #404040;
                color: white;
                border: 1px solid #555555;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QComboBox:hover {
                background-color: #505050;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid white;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #404040;
                color: white;
                selection-background-color: #505050;
                border: 1px solid #555555;
            }
        """)
        color_style_row.addWidget(self.color_style_combo)
        window_layout.addLayout(color_style_row)

        # Checkboxes
        self.hide_headers_cb = QCheckBox("Auto-hide headers")
        self.hide_headers_cb.setStyleSheet("border: none; color: white; font-size: 9pt;")
        self.hide_headers_cb.setChecked(self.parent_overlay.hide_headers)
        window_layout.addWidget(self.hide_headers_cb)

        self.center_drivers_cb = QCheckBox("Center driver names")
        self.center_drivers_cb.setStyleSheet("border: none; color: white; font-size: 9pt;")
        self.center_drivers_cb.setChecked(self.parent_overlay.center_drivers)
        window_layout.addWidget(self.center_drivers_cb)

        self.bold_drivers_cb = QCheckBox("Bold all driver rows")
        self.bold_drivers_cb.setStyleSheet("border: none; color: white; font-size: 9pt;")
        self.bold_drivers_cb.setChecked(self.parent_overlay.bold_drivers)
        window_layout.addWidget(self.bold_drivers_cb)

        layout.addWidget(window_group)
        
        # Division colors
        colors_group = QFrame()
        colors_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        colors_layout = QVBoxLayout(colors_group)
        colors_layout.setSpacing(8)
        
        colors_title = QLabel("Division Colors")
        colors_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        colors_layout.addWidget(colors_title)
        
        self.color_buttons = {}
        self.color_value_labels = {}
        
        for division in ["Pro", "ProAm", "Am", "Rookie"]:
            if division not in self.parent_overlay.available_colors:
                continue
                
            color = self.parent_overlay.available_colors[division]
            
            color_row = QHBoxLayout()
            color_row.setSpacing(5)
            
            div_label = QLabel(f"{division}:")
            div_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 50px;")
            color_row.addWidget(div_label)
            
            color_btn = QPushButton()
            color_btn.setFixedSize(80, 30)
            color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 2px solid #555555;
                }}
                QPushButton:hover {{
                    border: 2px solid #777777;
                }}
            """)
            color_btn.clicked.connect(lambda checked, d=division: self.choose_color(d))
            self.color_buttons[division] = color_btn
            color_row.addWidget(color_btn)
            
            color_value = QLabel(color)
            color_value.setStyleSheet("""
                border: none; 
                color: white; 
                font-size: 9pt; 
                background-color: #404040;
                padding: 2px 4px;
                min-width: 60px;
            """)
            self.color_value_labels[division] = color_value
            color_row.addWidget(color_value)
            
            color_row.addStretch()
            colors_layout.addLayout(color_row)
        
        layout.addWidget(colors_group)
        
        layout.addStretch()
        
        # Buttons - Top row with Cancel and Apply
        top_button_layout = QHBoxLayout()
        top_button_layout.setSpacing(5)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 6px 12px;
                border: none;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        cancel_btn.clicked.connect(self.on_cancel)
        top_button_layout.addWidget(cancel_btn)
        
        apply_btn = QPushButton("Apply Settings")
        apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 6px 12px;
                border: none;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        apply_btn.clicked.connect(self.apply_settings)
        top_button_layout.addWidget(apply_btn)
        
        layout.addLayout(top_button_layout)
        
        # Reset button centered below
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                padding: 6px 12px;
                border: none;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
        """)
        reset_btn.clicked.connect(self.reset_to_defaults)
        layout.addWidget(reset_btn)
        
        # Version with update link if available
        if hasattr(self.parent_overlay, 'latest_version') and self.parent_overlay.latest_version:
            version_text = f"Version {VERSION} | <a href='https://leagueoverlay.com/download.php' style='color: #4CAF50;'>Update to v{self.parent_overlay.latest_version}</a>"
            version_label = QLabel(version_text)
            version_label.setOpenExternalLinks(True)
        else:
            version_label = QLabel(f"Version {VERSION}")

        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: #888888; font-size: 8pt;")
        layout.addWidget(version_label)
        
        # Overall styling
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
            }
            QSlider::groove:horizontal {
                background: #444444;
                height: 4px;
            }
            QSlider::handle:horizontal {
                background: white;
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #e0e0e0;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #404040;
                border: 1px solid #666666;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 1px solid #4CAF50;
            }
        """)
        
    def on_opacity_change(self, value):
        """Live preview of opacity changes as user drags slider.

        Purpose: Lets user see exactly how transparent/opaque the overlay will be
        before committing the change with "Apply Settings."

        Why this exists: Opacity is hard to judge from a number. Live preview
        lets users find the perfect transparency for their setup.

        Args:
            value: Slider value (2-20), divided by 20 to get 0.10-1.00 opacity

        Note: Changes are temporary until "Apply Settings" clicked. "Cancel"
        reverts to original_opacity stored in __init__.
        """
        opacity = value / 20.0
        self.parent_overlay.opacity = opacity
        self.parent_overlay.update_all_backgrounds()
        
    def choose_color(self, division):
        """Open color picker to customize a division's color.

        Purpose: Allows leagues to customize division colors to match their
        branding or preferences.

        Why this exists: Default colors might not work for all leagues. Some
        might want different colors for better visibility or aesthetics.

        Args:
            division: "Pro", "ProAm", "Am", or "Rookie"

        Flow:
            1. Opens Qt color picker dialog with current division color
            2. If user selects new color, updates:
               - available_colors dict
               - Color button preview
               - Hex code label
            3. Changes saved when "Apply Settings" clicked

        Note: Changes affect ALL drivers in that division immediately after apply.
        """
        current_color = self.parent_overlay.available_colors[division]
        color = QColorDialog.getColor(QColor(current_color), self, f"Choose {division} Color")

        if color.isValid():
            new_color = color.name()
            self.parent_overlay.available_colors[division] = new_color
            self.color_buttons[division].setStyleSheet(f"""
                QPushButton {{
                    background-color: {new_color};
                    border: 2px solid #555555;
                }}
                QPushButton:hover {{
                    border: 2px solid #777777;
                }}
            """)
            self.color_value_labels[division].setText(new_color)
            
    def create_new_config(self):
        """Create new config file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Create New League Config File",
            ".",
            "JSON files (*.json);;All files (*.*)"
        )
        
        if file_path:
            try:
                empty_config = {'drivers': []}
                with open(file_path, 'w') as f:
                    json.dump(empty_config, f, indent=2)
                
                self.parent_overlay.color_config_file = file_path
                self.parent_overlay.driver_colors = empty_config
                self.current_config_label.setText(os.path.basename(file_path))

                # IMPORTANT: Also reload the DivisionManager with the custom config
                self.parent_overlay.division_manager = DivisionManager(file_path)
                self.parent_overlay.available_colors = self.parent_overlay.division_manager.division_colors
                self.parent_overlay.signals.refresh_colors.emit()
                
                QMessageBox.information(self, "Success", "Config file created successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create config file: {e}")
                
    def load_config(self):
        """Load different config file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Division Color Config File",
            ".",
            "JSON files (*.json);;All files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    config_data = json.load(f)
                
                self.parent_overlay.color_config_file = file_path
                self.parent_overlay.driver_colors = config_data
                self.current_config_label.setText(os.path.basename(file_path))

                # IMPORTANT: Also reload the DivisionManager with the custom config
                self.parent_overlay.division_manager = DivisionManager(file_path)
                self.parent_overlay.available_colors = self.parent_overlay.division_manager.division_colors
                self.parent_overlay.signals.refresh_colors.emit()
                
                QMessageBox.information(self, "Success", "Config file loaded successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load config file: {e}")
                
    def reset_to_defaults(self):
        """Reset to default settings"""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all settings to their default values?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.opacity_slider.setValue(10)  # 0.5
            self.refresh_slider.setValue(8)  # 2.0 seconds (8 * 0.25)
            self.hide_headers_cb.setChecked(False)
            self.center_drivers_cb.setChecked(False)
            self.bold_drivers_cb.setChecked(True)
            self.font_size_combo.setCurrentText("Medium")
            self.color_style_combo.setCurrentText("Default")
            
            default_colors = {
                "Pro": "#FF8C00",
                "ProAm": "#9370DB",
                "Am": "#45B3E0",
                "Rookie": "#FF2000"
            }
            
            for division, color in default_colors.items():
                if division in self.color_buttons:
                    self.parent_overlay.available_colors[division] = color
                    self.color_buttons[division].setStyleSheet(f"""
                        QPushButton {{
                            background-color: {color};
                            border: 2px solid #555555;
                        }}
                        QPushButton:hover {{
                            border: 2px solid #777777;
                        }}
                    """)
                    self.color_value_labels[division].setText(color)
            
            self.parent_overlay.opacity = 0.5
            self.parent_overlay.update_all_backgrounds()

    def apply_settings(self):
        """Apply all settings"""
        try:
            self.parent_overlay.opacity = self.opacity_slider.value() / 20.0
            self.parent_overlay.refresh_rate = self.refresh_slider.value() / 4.0  # Changed from /10 to /4
            self.parent_overlay.hide_headers = self.hide_headers_cb.isChecked()
            self.parent_overlay.center_drivers = self.center_drivers_cb.isChecked()
            self.parent_overlay.bold_drivers = self.bold_drivers_cb.isChecked()
            self.parent_overlay.font_size = self.font_size_combo.currentText()
            self.parent_overlay.row_color_style = self.color_style_combo.currentText()

            self.parent_overlay.update_all_backgrounds()

            # Save and refresh
            self.parent_overlay.save_settings()
            self.parent_overlay.signals.refresh_colors.emit()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {e}")
            
    def on_cancel(self):
        """Cancel settings"""
        self.parent_overlay.opacity = self.original_opacity
        self.parent_overlay.update_all_backgrounds()
        self.reject()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: APPLICATION ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
#
# Main function to start the application:
# - main(): Initialize Qt application and show main window
# - if __name__ == '__main__': Entry point when run as script
#
# TO SPLIT: Keep this in league_overlay.py (main file)
# ═══════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Dark palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(43, 43, 43))
    palette.setColor(QPalette.WindowText, Qt.white)
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(43, 43, 43))
    palette.setColor(QPalette.Text, Qt.white)
    palette.setColor(QPalette.Button, QColor(43, 43, 43))
    palette.setColor(QPalette.ButtonText, Qt.white)
    palette.setColor(QPalette.Highlight, QColor(85, 85, 85))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)
    
    overlay = LeagueOverlay()
    overlay.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()