"""Driver state dataclass for unified driver data management.

This module provides a single source of truth for driver data during a session,
eliminating the need for multiple parallel data structures (active_drivers,
driver_snapshots, all_drivers_with_colors, etc.).
"""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class DriverState:
    """Single source of truth for all driver data during a session.

    This dataclass consolidates what was previously spread across multiple
    data structures:
    - active_drivers (List[Dict]) - telemetry and position data
    - driver_snapshots (Dict) - race state tracking
    - all_drivers_with_colors (List[Dict]) - division color mapping
    - comparison_drivers (List[Dict]) - temporary gap calculation data

    Benefits:
    - Single state container instead of 6+ different lists/dicts
    - Update in place, no copying or rebuilding
    - Clear type hints for all fields
    - Easy querying: drivers[car_idx].is_finished
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # IDENTITY
    # ═══════════════════════════════════════════════════════════════════════════

    car_idx: int
    """iRacing car index (0-63)"""

    driver_info: Dict = field(default_factory=dict)
    """Raw driver info from iRacing SDK.

    Contains: UserID, UserName, CarNumber, CarClassID, etc.
    Kept as dict because many systems (division_manager) expect this format.
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # DIVISION
    # ═══════════════════════════════════════════════════════════════════════════

    division_name: Optional[str] = None
    """Division name: "Pro", "ProAm", "Am", "Rookie", or None for default"""

    division_color: str = "#FFFFFF"
    """Hex color code for division (e.g., "#FF0000" for red)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # TELEMETRY (updated every frame)
    # ═══════════════════════════════════════════════════════════════════════════

    current_lap: int = 0
    """Current lap number (from CarIdxLap)"""

    lap_pct: float = 0.0
    """Progress through current lap, 0.0 to 1.0 (from CarIdxLapDistPct)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # POSITIONS (calculated)
    # ═══════════════════════════════════════════════════════════════════════════

    official_position: int = 0
    """Official position from iRacing (updates at start/finish line)"""

    real_time_position: int = 0
    """Real-time position based on track position (continuous updates)"""

    division_position: int = 0
    """Position within driver's division (1 = division leader)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # STATE FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    is_finished: bool = False
    """True if driver has completed the race (crossed line after checkered)"""

    is_disconnected: bool = False
    """True if driver has disconnected or retired from the race"""

    is_player: bool = False
    """True if this is the player's car"""

    # ═══════════════════════════════════════════════════════════════════════════
    # FINISH TRACKING
    # ═══════════════════════════════════════════════════════════════════════════

    finish_time: Optional[float] = None
    """SessionTime when driver crossed finish line (for gap calculations)"""

    finish_lap: Optional[int] = None
    """Lap number when driver finished"""

    # ═══════════════════════════════════════════════════════════════════════════
    # GAP DISPLAY
    # ═══════════════════════════════════════════════════════════════════════════

    gap: str = ""
    """Formatted gap string for display (e.g., "+2.5s", "1 Lap", "Leader")"""

    finish_gap: Optional[float] = None
    """Time gap at finish (in seconds) for finished drivers"""

    finish_lap_gap: Optional[int] = None
    """Lap gap at finish for finished drivers (e.g., car was lapped)"""

    # ═══════════════════════════════════════════════════════════════════════════
    # COMPUTED PROPERTIES
    # ═══════════════════════════════════════════════════════════════════════════

    @property
    def total_track_position(self) -> float:
        """Total track position for sorting (lap + progress through current lap).

        Example: Lap 25, 50% through = 25.5
        Higher value = further ahead on track
        """
        return self.current_lap + self.lap_pct

    @property
    def car_number(self) -> str:
        """Car number from driver info."""
        return self.driver_info.get('CarNumber', '')

    @property
    def driver_name(self) -> str:
        """Driver name from driver info."""
        return self.driver_info.get('UserName', '')

    @property
    def car_class_id(self) -> Optional[int]:
        """Car class ID from driver info (for multi-class filtering)."""
        return self.driver_info.get('CarClassID')

    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════════

    def update_telemetry(self, current_lap: int, lap_pct: float, official_position: int) -> None:
        """Update telemetry data from iRacing SDK.

        Args:
            current_lap: Current lap number
            lap_pct: Progress through current lap (0.0 to 1.0)
            official_position: Official class position from iRacing
        """
        self.current_lap = current_lap
        self.lap_pct = lap_pct
        self.official_position = official_position

    def mark_finished(self, finish_time: float, finish_lap: int) -> None:
        """Mark driver as finished.

        Args:
            finish_time: SessionTime when driver crossed finish line
            finish_lap: Lap number when driver finished
        """
        self.is_finished = True
        self.finish_time = finish_time
        self.finish_lap = finish_lap

    def to_ui_dict(self) -> Dict:
        """Convert to dictionary format expected by UI.

        Returns:
            Dict with keys: position, division_position, car_number, driver_name,
                           driver_info, gap, car_idx, is_player
        """
        return {
            'position': self.real_time_position if not self.is_finished else self.official_position,
            'division_position': self.division_position,
            'car_number': self.car_number,
            'driver_name': self.driver_name,
            'driver_info': self.driver_info,
            'gap': self.gap,
            'car_idx': self.car_idx,
            'is_player': self.is_player,
        }
