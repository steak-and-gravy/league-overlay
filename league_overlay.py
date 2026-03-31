"""
BB's League Overlay - Real-time iRacing race position overlay

This application provides a floating, semi-transparent overlay that shows:
- Real-time race positions (using lap distances during race)
- Division-based color coding (Pro, ProAm, Am, Rookie)
- Live time gaps to cars ahead (within same division)
- Division-specific filtering
- Multi-class race support (always only show cars within same class)
- Class refers to different types of cars (LMP2, GT3, GT4, etc), Divisions refers to groupings of drivers within the same class
- Uses irsdk to read telemetry data from iRacing
"""

import sys
import threading
import time
import os
import re
import json
import math
from typing import Dict, List, Optional, Any
import irsdk

# Import from modular structure
from config.constants import (
    UI_CONFIG, FILE_CONFIG, VERSION,
    UI_COLORS, UI_DIMENSIONS, COLUMN_LAYOUT, COLUMN_MIN_WIDTHS, TIMING, TELEMETRY_CONFIG
)
from config.settings import SettingsManager
from config.logging_config import setup_logging, get_logger
from core.driver_state import DriverState
from core.gap_calculator import GapCalculator
from core.division_manager import DivisionManager
from core.division_filter import DivisionFilter
from core.race_state_tracker import RaceStateTracker
from core.position_calculator import PositionCalculator
from core.telemetry_processor import TelemetryProcessor
from core.update_checker import UpdateChecker
from ui.widgets import DataUpdateSignal, CustomSizeGrip
from ui.driver_row_renderer import DriverRowRenderer
from ui.settings_dialog import SettingsDialog
from ui.auto_center_controller import AutoCenterController
from ui.broadcast_header import BroadcastHeaderWidget

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QGridLayout, QMenu,
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPalette, QCursor

# Get logger for this module
logger = get_logger(__name__)

DEFAULT_BROADCAST_ACCENT_COLOR = "#FF8C00"
DEFAULT_BROADCAST_TITLE = "BB's League Overlay"
DEFAULT_BROADCAST_LOGO_URL = "https://leagueoverlay.com/assets/img/BBLeagueOverlay96.png"


def lighten_hex_color(hex_color: str, factor: float = 0.2) -> str:
    """Lighten a hex color by a given factor.

    Args:
        hex_color: Hex color string (e.g., "#FF0000")
        factor: Amount to lighten (0.0 to 1.0, where 0.2 = 20% lighter)

    Returns:
        Lightened hex color string
    """
    # Remove '#' if present
    hex_color = hex_color.lstrip('#')

    # Convert hex to RGB
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Lighten by moving towards white (255, 255, 255)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)

    # Ensure values are in valid range
    r = min(255, max(0, r))
    g = min(255, max(0, g))
    b = min(255, max(0, b))

    # Convert back to hex
    return f"#{r:02X}{g:02X}{b:02X}"


class LeagueOverlay(QMainWindow):
    """Main application window for iRacing race position overlay."""

    def __init__(self):
        super().__init__()
        self.ir = irsdk.IRSDK()  # iRacing SDK connection object
        self.is_connected = False  # Connection status flag
        self.running = True  # Thread control flag
        self.connection_time = None  # Timestamp when connection is established

        # Thread-safe communication (telemetry thread -> UI thread)
        self.signals = DataUpdateSignal()
        self.signals.update_data.connect(self.display_race_data)
        self.signals.update_status.connect(self.update_status_label)
        self.signals.refresh_colors.connect(self.refresh_driver_colors)
        self.signals.update_footer.connect(self.update_footer_display)

        self.player_car_idx = None  # Player's car (from iRacing API)
        self.spectated_car_idx = None  # Car currently being viewed by spectator camera
        self.class_leader_lap: Optional[int] = None  # Cached class leader lap for status display

        # Auto-centering controller
        self.auto_center = AutoCenterController(timeout=UI_CONFIG.MANUAL_SCROLL_TIMEOUT)

        # Update checker
        self.update_checker = UpdateChecker(
            repo_api_url="https://api.github.com/repos/steak-and-gravy/league-overlay",
            current_version=VERSION
        )

        # ═══════════════════════════════════════════════════════════
        # SETTINGS MANAGEMENT
        # ═══════════════════════════════════════════════════════════
        self.settings_manager = SettingsManager(FILE_CONFIG.SETTINGS_FILE)
        self.settings = self.settings_manager.load()

        # Load official leagues (from cache or fallback)
        from config.official_leagues import load_official_leagues_from_json, OFFICIAL_LEAGUES
        OFFICIAL_LEAGUES.clear()
        OFFICIAL_LEAGUES.extend(load_official_leagues_from_json())
        logger.info(f"Loaded {len(OFFICIAL_LEAGUES)} official leagues")

        # Color config file (defaults to first official league if not specified in settings)
        if self.settings.league_config:
            self.color_config_file = self.settings.league_config
        else:
            # Default to first official league
            if OFFICIAL_LEAGUES:
                self.color_config_file = f"official:{OFFICIAL_LEAGUES[0].name}"
            else:
                self.color_config_file = "league_divisions.json"
        self.broadcast_header_title = DEFAULT_BROADCAST_TITLE
        self.broadcast_header_logo = DEFAULT_BROADCAST_LOGO_URL
        self.broadcast_header_accent_color = DEFAULT_BROADCAST_ACCENT_COLOR
        self.apply_official_league_broadcast_metadata()

        # User preferences not in settings (runtime state)
        self.top_elements_visible = True  # Current visibility of title/status
        self._update_counter = 0  # Counter for forcing periodic UI updates (for gap changes)

        # Font size mappings (use UI_CONFIG)
        self.font_sizes = UI_CONFIG.FONT_SIZES

        # ═══════════════════════════════════════════════════════════
        # HELPER CLASSES - Extracted responsibilities
        # ═══════════════════════════════════════════════════════════
        # Initialize DivisionManager with league config
        division_config = self.color_config_file
        self.division_manager = DivisionManager(division_config)
        self.division_filter = DivisionFilter(self.division_manager)
        self.race_state_tracker = RaceStateTracker(self.ir)
        self.gap_calculator = GapCalculator()
        self.position_calculator = PositionCalculator(self.ir)
        self.row_renderer = DriverRowRenderer(self)

        # TelemetryProcessor - handles all telemetry processing logic
        self.telemetry_processor = TelemetryProcessor(
            self.ir,
            self.division_manager,
            self.race_state_tracker,
            self.gap_calculator,
            self.position_calculator
        )

        # Session tracking (now managed by TelemetryProcessor, kept for compatibility)
        self.current_session_id: Optional[int] = None
        self.current_session_type: Optional[str] = None
        self.player_car_class_id: Optional[int] = None

        # Update checking
        self.update_check_done: bool = False
        self.latest_version: Optional[str] = None

        self.race_data = []  # Unfiltered - all drivers from telemetry
        self.displayed_data = []  # Filtered - what's currently shown in UI
        self._last_emitted_data = []  # Track last data sent to UI to avoid redundant updates
        self.broadcast_roll_page_index = 0

        self.startup_time = time.time()
        
        # Setup UI
        self.setup_ui()
        
        # Start telemetry thread
        self.telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        self.telemetry_thread.start()
        
        # Status update timer (checks connection status and session type)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_gui)
        self.update_timer.start(UI_CONFIG.STATUS_UPDATE_INTERVAL)  # status updates don't need to be instant

        # Auto-center check timer (checks if auto-center should re-engage after manual scroll)
        # This timer is started when user manually scrolls, and stops once auto-center re-engages
        self.auto_center_timer = QTimer()
        self.auto_center_timer.timeout.connect(self.check_auto_center)
        self.auto_center_timer.setInterval(TIMING.AUTO_CENTER_CHECK_INTERVAL)

        # Broadcast rolling standings timer (rotates the bottom group)
        self.broadcast_roll_timer = QTimer()
        self.broadcast_roll_timer.timeout.connect(self.advance_broadcast_roll_window)
        self._update_broadcast_roll_mode()

        # Show version
        self.show_version_on_startup()

        # Focus tracking for auto-hide
        self.hide_timer = None
        self.setMouseTracking(True)

        # Initial auto-hide check - if hide_headers is enabled, hide immediately
        if self.settings.hide_headers:
            self.hide_top_elements()

    def get_bg_color(self, base_color):
        """Convert a hex color to RGBA format with current window opacity."""
        # Parse hex color
        if base_color.startswith('#'):
            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)
            return f"rgba({r}, {g}, {b}, {self.settings.opacity})"
        return base_color

    def get_font_size(self, element_type):
        """Get the appropriate font size or spacing for a UI element.
        Purpose: Centralizes font sizing to make the entire UI scale together
        when user changes font size setting (Small/Medium/Large/Extra Large).
        """
        if element_type == "spacing":
            return self.font_sizes.get(self.settings.font_size, self.font_sizes["Medium"]).get(element_type, 3)
        return self.font_sizes.get(self.settings.font_size, self.font_sizes["Medium"]).get(element_type, "9pt")
    
    def blend_color_with_black(self, color_hex, amount=0.15):
        """Blend a division color with black to create a subtle tinted background."""
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
        """Create a horizontal gradient that creates a subtle "glow" effect for player row."""
        tinted = self.blend_color_with_black(color_hex, self.settings.highlight)
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {tinted}, stop:0.5 #1a1a1a, stop:1 {tinted})"
    
    def update_all_backgrounds(self):
        """Refresh all UI backgrounds, fonts, and styling after settings change.

        Note: Settings are accessed via self.settings object.
        """
        if hasattr(self, 'main_widget'):
            self.main_widget.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
        if hasattr(self, 'title_bar'):
            self.title_bar.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
        if hasattr(self, 'header_frame'):
            self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
            # Update header text when column visibility changes
            self._update_header_labels()
        if hasattr(self, 'scroll_area'):
            self._update_broadcast_roll_mode()
            self.update_scroll_area_style()
        if hasattr(self, 'scroll_content'):
            self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
        if hasattr(self, 'size_grip'):
            # Don't set background in stylesheet - let paintEvent handle it
            self.size_grip.setStyleSheet("""
                QSizeGrip {
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
                    background-color: transparent;
                }}
            """)
        if hasattr(self, 'division_btn'):
            # Get current color from the button
            current_style = self.division_btn.styleSheet()
            if "background-color:" in current_style:
                # Extract background color
                color_match = re.search(r'background-color:\s*([^;]+)', current_style)
                button_color = color_match.group(1).strip() if color_match else UI_COLORS.BUTTON_GRAY
            else:
                button_color = UI_COLORS.BUTTON_GRAY

            # Calculate hover color
            hover_color = lighten_hex_color(button_color, factor=0.15)

            self.division_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {button_color};
                    color: white;
                    border: none;
                    padding: 4px 4px;
                    font-size: {self.get_font_size('button')};
                }}
                QPushButton:hover {{
                    background-color: {hover_color};
                }}
            """)
        if hasattr(self, 'settings_btn'):
            self.settings_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {UI_COLORS.BUTTON_GRAY};
                    color: white;
                    border: none;
                    padding: 4px 4px;
                    font-size: {self.get_font_size('button')};
                }}
                QPushButton:hover {{
                    background-color: {UI_COLORS.BUTTON_HOVER_GRAY};
                }}
            """)
        # Update status label font
        if hasattr(self, 'status_label'):
            if 'green' in self.status_label.styleSheet().lower():
                self.update_status_style('green')
            elif 'yellow' in self.status_label.styleSheet().lower():
                self.update_status_style('yellow')
            elif 'orange' in self.status_label.styleSheet().lower():
                self.update_status_style('orange')
            else:
                self.update_status_style('white')
            self.status_label.setVisible(not self.settings.show_broadcast_header)
        if hasattr(self, 'broadcast_header'):
            self.broadcast_header.settings = self.settings
            self.broadcast_header.refresh_styles()
            self.broadcast_header.setVisible(self.settings.show_broadcast_header)
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
        self.setGeometry(self.settings.x, self.settings.y, self.settings.width, self.settings.height)

        # Frameless but stay on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Set minimum size for resizing
        self.setMinimumSize(UI_DIMENSIONS.WINDOW_MIN_WIDTH, UI_DIMENSIONS.WINDOW_MIN_HEIGHT)
        
        # Main widget and layout
        main_widget = QWidget()
        main_widget.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
        self.setCentralWidget(main_widget)
        self.main_widget = main_widget
        
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # Title bar
        self.create_title_bar()

        # Broadcast header (optional, for broadcast/spectator use)
        self.broadcast_header = BroadcastHeaderWidget(
            settings=self.settings,
            get_bg_color_fn=self.get_bg_color,
            get_font_size_fn=self.get_font_size,
            get_broadcast_title_fn=lambda: self.broadcast_header_title,
            get_broadcast_logo_fn=lambda: self.broadcast_header_logo,
            get_broadcast_accent_fn=lambda: self.broadcast_header_accent_color,
        )
        self.broadcast_header.setVisible(self.settings.show_broadcast_header)
        self.main_layout.addWidget(self.broadcast_header)

        # Status label (hidden when broadcast header is active)
        self.status_label = QLabel("Connecting to iRacing...")
        self.update_status_style("orange")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setVisible(not self.settings.show_broadcast_header)
        self.main_layout.addWidget(self.status_label)

        # Header frame
        self.header_frame = QWidget()
        self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
        self.header_layout = QGridLayout(self.header_frame)
        # Force header to match scroll area width by setting size policy
        from PySide6.QtWidgets import QSizePolicy
        self.header_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.create_headers()
        self.main_layout.addWidget(self.header_frame)
        
        # Scrollable area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)  # Remove any frame that might affect width
        self.update_scroll_area_style()

        # Scrollable content
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        # Use 5px margins - scrollbar will reduce viewport by 6px, giving same content width as header
        # Header: W - 16px (5+11 margins), Scroll: (W - 6px scrollbar) - 10px (5+5 margins) = W - 16px ✓
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_layout.setSpacing(self.get_font_size('spacing'))
        self.scroll_layout.addStretch()
        
        self.scroll_area.setWidget(self.scroll_content)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.on_manual_scroll)
        self.main_layout.addWidget(self.scroll_area)

        # Footer (optional)
        self.footer_frame = QWidget()
        self.footer_frame.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
        self.footer_layout = QHBoxLayout(self.footer_frame)
        self.footer_layout.setContentsMargins(5, 5, 5, 5)
        self.footer_layout.setSpacing(10)

        # Left: Strength of Field
        self.sof_label = QLabel("SoF: ----")
        self.sof_label.setStyleSheet(f"color: white; font-size: {self.get_font_size('status')}pt; font-weight: bold;")
        self.sof_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.footer_layout.addWidget(self.sof_label)

        # Center: Incidents
        self.incidents_label = QLabel("--x")
        self.incidents_label.setStyleSheet(f"color: white; font-size: {self.get_font_size('status')}pt; font-weight: bold;")
        self.incidents_label.setAlignment(Qt.AlignCenter)
        self.footer_layout.addWidget(self.incidents_label)

        # Right: Track temperature
        self.track_temp_label = QLabel("🛣️ --°F / --°C")
        self.track_temp_label.setStyleSheet(f"color: white; font-size: {self.get_font_size('status')}pt; font-weight: bold;")
        self.track_temp_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.footer_layout.addWidget(self.track_temp_label)

        # Initially hidden based on settings
        self.footer_frame.setVisible(self.settings.show_footer)
        self.main_layout.addWidget(self.footer_frame)

        # Add size grip for resizing
        self.size_grip = CustomSizeGrip(main_widget)
        self.size_grip.set_parent_window(self)
        self.size_grip.setFixedSize(UI_DIMENSIONS.SIZE_GRIP_SIZE, UI_DIMENSIONS.SIZE_GRIP_SIZE)
        # Don't set background in stylesheet - let paintEvent handle it
        self.size_grip.setStyleSheet("""
            QSizeGrip {
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
                background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};
            }}
            QScrollBar:vertical {{
                background: {self.get_bg_color(UI_COLORS.SCROLLBAR_GRAY)};
                width: 6px;
                margin: 0px 0px 0px 0px;
                subcontrol-position: right;
                subcontrol-origin: margin;
            }}
            QScrollBar::handle:vertical {{
                background: {UI_COLORS.BUTTON_GRAY};
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {UI_COLORS.BUTTON_HOVER_GRAY};
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
                background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};
                padding: 5px;
                font-size: {self.get_font_size('status')};
                font-weight: bold;
            }}
        """)
    
    def update_status_label(self, text, color):
        """Display connection status and session type at top of overlay.
        Examples: "Connecting...", "Connected - Live Data (Race)", "Update available"
        """
        self.status_label.setText(text)
        self.update_status_style(color)
        if self.settings.show_broadcast_header and hasattr(self, 'broadcast_header'):
            normalized_color = color
            if isinstance(color, str) and color.startswith('#'):
                if color.lower() in ('#ffa500', '#ff8c00'):
                    normalized_color = 'orange'
                elif color.lower() in ('#ffff00', '#ffd700'):
                    normalized_color = 'yellow'
                else:
                    normalized_color = 'green'
            self.broadcast_header.update_session_info({
                'session_status': text,
                'status_color': normalized_color,
            })

    def update_footer_display(self, footer_data: Dict[str, Any]):
        """Update footer display with track temp, incidents, and SoF.

        Args:
            footer_data: Dictionary containing:
                - track_temp: Track temperature in Celsius (float or None)
                - incidents: Player's current incident count (int or None)
                - incident_limit: Session incident limit (int or None, None = unlimited)
                - sof: Strength of Field (average iRating, int or None)
        """
        if not self.settings.show_footer:
            return

        # Track temperature (convert to F and C, display as integers)
        track_temp = footer_data.get('track_temp')
        if track_temp is not None:
            temp_f = int((track_temp * 9/5) + 32)
            temp_c = int(track_temp)
            self.track_temp_label.setText(f"🛣️ {temp_f}°F / {temp_c}°C")
        else:
            self.track_temp_label.setText("🛣️ --°F / --°C")

        # Incidents (with limit if available)
        incidents = footer_data.get('incidents')
        incident_limit = footer_data.get('incident_limit')
        if incidents is not None:
            if incident_limit is not None and incident_limit != "unlimited":
                self.incidents_label.setText(f"{incidents}x/{incident_limit}")
            else:
                self.incidents_label.setText(f"{incidents}x/∞")
        else:
            self.incidents_label.setText("--x")

        # Strength of Field (format as 2.4k)
        sof = footer_data.get('sof')
        if sof is not None:
            sof_k = sof / 1000.0
            self.sof_label.setText(f"SoF: {sof_k:.1f}k")
        else:
            self.sof_label.setText("SoF: ----")

    def create_title_bar(self):
        """Create custom title bar"""
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(UI_DIMENSIONS.TITLE_BAR_HEIGHT)
        self.title_bar.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(5, 2, 5, 2)
        
        # Title label
        self.title_label = QLabel("BB's League Overlay")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: {self.get_font_size('title')};
                background-color: transparent;
            }}
        """)
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        
        # Division filter button
        self.division_btn = QPushButton("All Divisions")
        # Calculate hover color for initial state
        initial_hover = lighten_hex_color(UI_COLORS.BUTTON_GRAY, factor=0.15)
        self.division_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {UI_COLORS.BUTTON_GRAY};
                color: white;
                border: none;
                padding: 4px 4px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: {initial_hover};
            }}
        """)
        self.division_btn.clicked.connect(self.toggle_division_filter)
        title_layout.addWidget(self.division_btn)

        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {UI_COLORS.BUTTON_GRAY};
                color: white;
                border: none;
                padding: 4px 4px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: {UI_COLORS.BUTTON_HOVER_GRAY};
            }}
        """)
        self.settings_btn.clicked.connect(self.open_settings)
        title_layout.addWidget(self.settings_btn)

        # Close button
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(UI_DIMENSIONS.CLOSE_BUTTON_WIDTH)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {UI_COLORS.CLOSE_BUTTON_RED};
                color: white;
                border: none;
                padding: 5px;
                font-size: 12pt;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {UI_COLORS.CLOSE_BUTTON_HOVER_RED};
            }}
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

        # Set base margins - will be dynamically adjusted based on scrollbar visibility
        self.header_layout.setContentsMargins(5, 2, 5, 2)
        self.header_layout.setSpacing(2)

        # Reset all column stretches first (clear old values from hidden columns)
        for col_idx in range(14):  # Max possible columns (5 base + 9 optional)
            self.header_layout.setColumnStretch(col_idx, 0)

        # Build column configuration based on settings
        # Column order: Pos | [+/-] | [Mfr] | C-Pos | Driver | [Rating] | Car# | [Gap] | [C-Gap] | [Int] | [C-Int] | [Best] | [Last] | [Delta] | [Pit]
        # Columns in brackets are optional

        headers = ["Pos"]
        stretches = [COLUMN_LAYOUT.POS]

        # Optional: Positions Gained
        if self.settings.show_positions_gained:
            headers.append("+/-")
            stretches.append(COLUMN_LAYOUT.POSITIONS_GAINED)

        # Optional: Car Manufacturer
        if self.settings.show_car_manufacturer:
            headers.append("Mfr")
            stretches.append(COLUMN_LAYOUT.CAR_MANUFACTURER)

        # C-Pos (always shown)
        headers.append("C-Pos")
        stretches.append(COLUMN_LAYOUT.DIV_POS)

        # Driver (always shown)
        headers.append("Driver")
        stretches.append(COLUMN_LAYOUT.DRIVER_NAME)

        # Optional: Combined Rating (iRating + Safety Rating)
        if self.settings.show_rating:
            headers.append("Rating")
            stretches.append(COLUMN_LAYOUT.RATING)

        # Car# (moved to after Rating)
        headers.append("Car#")
        stretches.append(COLUMN_LAYOUT.CAR_NUM)

        # Gap to overall leader (optional)
        if self.settings.show_gap:
            headers.append("Gap")
            stretches.append(COLUMN_LAYOUT.GAP)

        # Gap to division leader (optional)
        if self.settings.show_division_gap:
            headers.append("C-Gap")
            stretches.append(COLUMN_LAYOUT.DIV_GAP)

        # Interval to car ahead overall (optional)
        if self.settings.show_interval:
            headers.append("Int")
            stretches.append(COLUMN_LAYOUT.INTERVAL)

        # Interval to car ahead in division (optional)
        if self.settings.show_division_interval:
            headers.append("C-Int")
            stretches.append(COLUMN_LAYOUT.DIV_INTERVAL)

        # Optional: Best Lap
        if self.settings.show_best_lap:
            headers.append("Best Lap")
            stretches.append(COLUMN_LAYOUT.BEST_LAP)

        # Optional: Last Lap
        if self.settings.show_last_lap:
            headers.append("Last Lap")
            stretches.append(COLUMN_LAYOUT.LAST_LAP)

        # Optional: Delta
        if self.settings.show_delta:
            headers.append("Delta")
            stretches.append(COLUMN_LAYOUT.DELTA)

        # Optional: Pit Lap (combined Last Pit + Out Lap)
        if self.settings.show_pit_lap:
            headers.append("Pit")
            stretches.append(COLUMN_LAYOUT.PIT_LAP)

        # Apply column stretches
        for col_idx, stretch in enumerate(stretches):
            self.header_layout.setColumnStretch(col_idx, stretch)

        # Define minimum widths mapping from header text to constant
        min_width_map = {
            "Pos": COLUMN_MIN_WIDTHS.POS,
            "+/-": COLUMN_MIN_WIDTHS.POSITIONS_GAINED,
            "Mfr": COLUMN_MIN_WIDTHS.CAR_MANUFACTURER,
            "C-Pos": COLUMN_MIN_WIDTHS.DIV_POS,
            "Driver": COLUMN_MIN_WIDTHS.DRIVER_NAME,
            "Rating": COLUMN_MIN_WIDTHS.RATING,
            "Car#": COLUMN_MIN_WIDTHS.CAR_NUM,
            "Gap": COLUMN_MIN_WIDTHS.GAP,
            "C-Gap": COLUMN_MIN_WIDTHS.DIV_GAP,
            "Int": COLUMN_MIN_WIDTHS.INTERVAL,
            "C-Int": COLUMN_MIN_WIDTHS.DIV_INTERVAL,
            "Best Lap": COLUMN_MIN_WIDTHS.BEST_LAP,
            "Last Lap": COLUMN_MIN_WIDTHS.LAST_LAP,
            "Delta": COLUMN_MIN_WIDTHS.DELTA,
            "Pit": COLUMN_MIN_WIDTHS.PIT_LAP
        }

        # Create header labels
        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};
                    font-weight: bold;
                    font-size: {self.get_font_size('header')};
                }}
                QToolTip {{
                    color: white;
                }}
            """)
            label.setAlignment(Qt.AlignCenter)

            # Add tooltips for gap and interval headers
            if header == "Gap":
                label.setToolTip("Gap to overall leader")
            elif header == "C-Gap":
                label.setToolTip("Gap to division leader")
            elif header == "Int":
                label.setToolTip("Interval to car ahead in overall standings")
            elif header == "C-Int":
                label.setToolTip("Interval to car ahead in your division")

            # Set same minimum widths as detail rows for consistent column sizing
            if header in min_width_map:
                label.setMinimumWidth(min_width_map[header])
            self.header_layout.addWidget(label, 0, i)

    def _update_header_labels(self):
        """Update header labels when column visibility settings change."""
        # Rebuild headers to reflect current visibility settings
        if hasattr(self, 'header_layout'):
            self.create_headers()

    def show_version_on_startup(self):
        """Show version on startup"""
        self.status_label.setText(f"BB's League Overlay v{VERSION}")
        self.update_status_style("orange")
        if self.settings.show_broadcast_header and hasattr(self, 'broadcast_header'):
            self.broadcast_header.update_session_info({
                'session_status': f"BB's League Overlay v{VERSION}",
                'status_color': 'orange',
            })
        threading.Thread(target=self.check_and_notify_updates, daemon=True).start()
        
    def check_and_notify_updates(self):
        """Check for updates"""
        if self.update_check_done:
            return
        time.sleep(TIMING.UPDATE_CHECK_DELAY)
        result = self.update_checker.check_for_update()
        self.update_check_done = True

        if result.get('update_available'):
            self.latest_version = result['latest_version']
            msg = f"Update available: v{result['latest_version']}"
            self.signals.update_status.emit(msg, '#00FF00')

    def toggle_division_filter(self):
        """Toggle division filter - cycles through different division views.
        Two modes:
        1. Player is on track: Toggle between "All Divisions" and "My Division"
        2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)
        """
        # Cycle to next filter state
        self.division_filter.cycle_filter(
            self.race_data,
            self.player_car_idx,
            self.division_manager.get_driver_color
        )

        # Get button state from filter
        button_state = self.division_filter.get_button_state()

        # Calculate hover color (slightly lighter shade of the button color)
        hover_color = lighten_hex_color(button_state['color'], factor=0.15)

        # Update button appearance
        self.division_btn.setText(button_state['text'])
        self.division_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {button_state['color']};
                color: white;
                border: none;
                padding: 4px 4px;
                font-size: {self.get_font_size('button')};
            }}
            QPushButton:hover {{
                background-color: {hover_color};
            }}
        """)
        self.scroll_area.verticalScrollBar().setValue(0)

        # Immediately apply the filter and update UI
        # Force update even if data unchanged (filter criteria changed)
        if self.race_data:
            current_data = self.division_filter.apply_filter(
                self.race_data,
                self.player_car_idx,
                self.division_manager.get_driver_color
            )
            self._last_emitted_data = current_data.copy()
            self.signals.update_data.emit(current_data)
        
    def on_manual_scroll(self):
        """Record when user manually scrolls, to temporarily disable auto-centering."""
        if self._is_broadcast_roll_active():
            return
        self.auto_center.on_manual_interaction()
        # Start the auto-center check timer (restarts if already running)
        if not self.auto_center_timer.isActive():
            self.auto_center_timer.start()

    def resizeEvent(self, event):
        """Qt event handler: Window was resized by user or programmatically.
        Why this exists: The size grip is a widget that must be manually positioned.
        Qt doesn't auto-anchor it, so we must move it on every resize.
        """
        super().resizeEvent(event)
        # Position size grip at bottom right corner
        if hasattr(self, 'size_grip'):
            rect = self.rect()
            self.size_grip.move(
                rect.width() - self.size_grip.width(),
                rect.height() - self.size_grip.height()
            )

        # Adjust header margins based on scrollbar visibility (may change during resize)
        if hasattr(self, 'header_layout'):
            self.adjust_header_margins()

        # Re-evaluate broadcast rolling state on resize (visible row capacity changes).
        self._update_broadcast_roll_mode()

    def load_settings(self):
        """Load user preferences from disk."""
        self.settings = self.settings_manager.load()

        # Handle league config file if specified
        if self.settings.league_config and os.path.exists(self.settings.league_config):
            self.color_config_file = self.settings.league_config

            # Reload DivisionManager with custom config
            self.division_manager = DivisionManager(self.settings.league_config)

    def save_settings(self):
        """Persist current settings - delegates to SettingsManager."""
        # Update settings object with current window geometry and config
        self.settings.league_config = self.color_config_file
        self.settings.division_colors = self.division_manager.division_colors
        self.settings.x = self.geometry().x()
        self.settings.y = self.geometry().y()
        self.settings.height = self.geometry().height()
        self.settings.width = self.geometry().width()

        # Delegate to settings manager (all other settings already in self.settings)
        self.settings_manager.save(self.settings)

    def apply_official_league_broadcast_metadata(self):
        """Apply broadcast branding rules based on selected league source.

        Official leagues provide title/logo metadata. Local leagues use defaults.
        Accent color is fixed and not user-configurable.
        """
        # Accent is fixed globally.
        self.broadcast_header_accent_color = DEFAULT_BROADCAST_ACCENT_COLOR

        # Defaults for non-official sources.
        default_title = DEFAULT_BROADCAST_TITLE
        default_logo = DEFAULT_BROADCAST_LOGO_URL
        self.broadcast_header_title = default_title
        self.broadcast_header_logo = default_logo

        if isinstance(self.color_config_file, str) and self.color_config_file.startswith("official:"):
            from config.official_leagues import get_official_league

            league_name = self.color_config_file.replace("official:", "")
            try:
                league = get_official_league(league_name)
                self.broadcast_header_title = getattr(league, 'title', None) or default_title
                self.broadcast_header_logo = getattr(league, 'logo', None) or default_logo
            except ValueError:
                logger.warning(f"Could not apply broadcast metadata: official league not found ({league_name})")

        # Keep header widget in sync if UI already exists.
        if hasattr(self, 'broadcast_header'):
            self.broadcast_header.refresh_styles()
            

    def set_driver_division(self, driver_info: Dict[str, str], division_name: str) -> None:
        """Assign a driver to a division - delegates to DivisionManager.
        Immediately refreshes the display to show the new division assignment.
        """
        # Delegate to DivisionManager for assignment logic
        self.division_manager.set_driver_division(driver_info, division_name)

        # Save configuration
        self.division_manager.save_config()

        # Immediately refresh display to show new division assignment
        self.refresh_driver_colors()

    def refresh_driver_colors(self):
        """Refresh all driver colors"""
        if self.displayed_data:
            # Force update even if data unchanged (colors changed)
            self._last_emitted_data = []
            self.signals.update_data.emit(self.displayed_data.copy())

        # Update footer visibility based on settings
        if hasattr(self, 'footer_frame'):
            self.footer_frame.setVisible(self.settings.show_footer)

    def reload_division_config(self, config_file_path: str) -> None:
        """Reload division configuration from a different config file.

        This method updates the division manager with a new config file and
        refreshes all related state (driver colors, available divisions, UI).
        Called by SettingsDialog when user creates or loads a new config.

        Args:
            config_file_path: Path to the new division config JSON file
        """
        self.color_config_file = config_file_path

        # Reload DivisionManager with the new config file
        self.division_manager = DivisionManager(config_file_path)

        # Refresh the UI to show new colors (reset change tracking to force update)
        self._last_emitted_data = []
        self.signals.refresh_colors.emit()

    def add_to_recent_files(self, file_path: str):
        """Add a file to recent list, maintaining MRU order.

        Args:
            file_path: Absolute path to the config file
        """
        # Remove if exists (avoid duplicates)
        if file_path in self.settings.recent_local_configs:
            self.settings.recent_local_configs.remove(file_path)

        # Add to front
        self.settings.recent_local_configs.insert(0, file_path)

        # Limit to 5 most recent
        self.settings.recent_local_configs = self.settings.recent_local_configs[:5]

        # Clean up non-existent files
        self.settings.recent_local_configs = [
            f for f in self.settings.recent_local_configs
            if os.path.exists(f)
        ]

    def refresh_official_league(self):
        """Refresh current official league from remote.

        Returns:
            tuple: (success: bool, message: str, driver_count: int)
        """
        if not self.color_config_file.startswith("official:"):
            logger.warning("Cannot refresh - not an official league")
            return (False, "Cannot refresh - not an official league", 0)

        from config.official_leagues import get_official_league, get_full_league_url
        import requests

        league_name = self.color_config_file.replace("official:", "")

        try:
            league = get_official_league(league_name)

            # Fetch from remote
            league_url = get_full_league_url(league)
            response = requests.get(league_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Save to cache
            cache_path = os.path.join(os.path.dirname(__file__), league.cache_file)
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)

            # Count drivers
            driver_count = len(data.get('drivers', []))

            # Reload config
            self.division_manager.load_driver_config()

            # Update UI
            self.signals.refresh_colors.emit()

            logger.info(f"Successfully refreshed {league.name}")
            return (True, f"Successfully refreshed {league.name}", driver_count)

        except Exception as e:
            error_msg = f"Failed to refresh {league.name}: {e}"
            logger.error(error_msg)
            return (False, error_msg, 0)

    def open_settings(self):
        """Open settings dialog"""
        dialog = SettingsDialog(self)
        result = dialog.exec()

        # After settings closed, update auto-hide behavior
        if self.settings.hide_headers:
            if not self.hasFocus():
                self.hide_top_elements()
        else:
            self.show_top_elements()
            
    def hide_top_elements(self):
        """Hide title bar"""
        if self.top_elements_visible:
            self.title_bar.hide()
            self.top_elements_visible = False
            
    def show_top_elements(self):
        """Show title bar"""
        if not self.top_elements_visible:
            self.title_bar.show()
            self.top_elements_visible = True
            
    def enterEvent(self, event):
        """Mouse entered window"""
        if self.settings.hide_headers:
            # Cancel hide timer if active
            if self.hide_timer:
                self.killTimer(self.hide_timer)
                self.hide_timer = None
            self.show_top_elements()
        # Show resize grip when mouse enters
        if hasattr(self, 'size_grip'):
            self.size_grip.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Mouse left window"""
        if self.settings.hide_headers:
            # Start hide timer
            if self.hide_timer:
                self.killTimer(self.hide_timer)
            self.hide_timer = self.startTimer(TIMING.AUTO_HIDE_DELAY)
        # Hide resize grip when mouse leaves
        if hasattr(self, 'size_grip'):
            self.size_grip.set_hovered(False)
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
            if self.settings.hide_headers:
                self.hide_top_elements()
        
    def close_application(self):
        """Close application"""
        self.save_settings()
        self.running = False
        QApplication.quit()
        
    def telemetry_loop(self):
        """Background thread that continuously reads data from iRacing SDK."""
        while self.running:
            try:
                if not self.is_connected:
                    if self.ir.startup():
                        self.is_connected = True
                        self.connection_time = time.time()  # Record connection timestamp

                if self.is_connected:
                    if self.ir.is_connected and self.ir.is_initialized:
                        # Delegate to TelemetryProcessor
                        race_data = self.telemetry_processor.process_telemetry(
                            get_driver_color_fn=self.division_manager.get_driver_color
                        )

                        # Handle the telemetry update (session sync, data update)
                        self._handle_telemetry_update(race_data)
                    else:
                        self.is_connected = False
                        self.connection_time = None  # Reset connection time on disconnect
                        self.ir.shutdown()

                time.sleep(self.settings.refresh_rate)

            except Exception as e:
                logger.error(f"Telemetry error: {e}", exc_info=True)
                time.sleep(1)

    # ═══════════════════════════════════════════════════════════════════════════
    # TELEMETRY PROCESSING METHODS (now in core.telemetry_processor)
    # ═══════════════════════════════════════════════════════════════════════════
    # All telemetry processing logic has been extracted to TelemetryProcessor:
    # - process_telemetry, calculate_real_time_positions, get_official_positions
    # - update_finish_status, _get_session_info, _detect_session_change
    # - _identify_player, _calculate_division_positions, _build_race_data_entry
    # - _update_race_snapshots, _handle_disconnected_drivers, _calculate_gap
    # - _calculate_live_race_gap, _calculate_practice_gap, reset_fields
    # The telemetry_loop above now delegates to telemetry_processor.process_telemetry()

    def _handle_telemetry_update(self, race_data: Optional[List[DriverState]]) -> None:
        """Handle telemetry update and sync state from processor.

        Extracted from telemetry_loop for testability. Updates race data,
        detects session changes, and syncs player information.

        Args:
            race_data: Processed race data from TelemetryProcessor, or None if unavailable
        """
        if race_data is None:
            return

        # Detect session change by comparing with processor's session info
        session_changed = (
            self.current_session_id != self.telemetry_processor.current_session_id or
            self.current_session_type != self.telemetry_processor.current_session_type
        )

        # Check if starting positions were updated (qualifying results loaded)
        starting_positions_updated = self.race_state_tracker.consume_starting_positions_update()

        # Sync session info from telemetry processor
        self.current_session_id = self.telemetry_processor.current_session_id
        self.current_session_type = self.telemetry_processor.current_session_type

        # Clear old data on session change (only if we have a valid session)
        if session_changed and self.current_session_id is not None:
            # Don't clear standings when transitioning from qualifying to race
            # so that starting position data displays correctly
            prev_type = self.telemetry_processor.previous_session_type
            curr_type = self.telemetry_processor.current_session_type
            is_qual_to_race = (
                prev_type is not None
                and prev_type.lower() == 'qualifying'
                and curr_type is not None
                and curr_type.lower() == 'race'
            )
            if not is_qual_to_race:
                self.race_data = []
                self._last_emitted_data = []  # Reset change tracking on session change
            # Note: Division filter state is intentionally preserved across session changes

        # Update race data and player info
        self.race_data = race_data
        self.player_car_idx = self.telemetry_processor.position_calculator.player_car_idx
        self.spectated_car_idx = self.telemetry_processor.position_calculator.spectated_car_idx

        # Immediately emit UI update with new data (event-driven)
        # Only update if data has actually changed to avoid redundant widget rebuilds
        if race_data:
            current_data = self.division_filter.apply_filter(
                            race_data,
                            self.player_car_idx,
                            self.division_manager.get_driver_color)

            # Cache class leader lap for status display (use first entry after filtering)
            if current_data:
                self.class_leader_lap = current_data[0].current_lap
            else:
                self.class_leader_lap = None

            # Check if data changed structurally
            data_changed = self._has_data_changed(current_data)

            if data_changed or starting_positions_updated:
                self._last_emitted_data = current_data.copy()
                self.signals.update_data.emit(current_data)
        else:
            self.class_leader_lap = None

        # Emit footer data if footer is enabled
        if self.settings.show_footer:
            footer_data = self.telemetry_processor.get_footer_data()
            self.signals.update_footer.emit(footer_data)

    def _has_data_changed(self, new_data: List[DriverState]) -> bool:
        """Check if the new data is different from the last emitted data.

        Compares key fields that would affect display to avoid unnecessary
        widget rebuilds when data hasn't meaningfully changed.

        Args:
            new_data: New filtered data to compare

        Returns:
            True if data has changed and UI should be updated
        """
        if len(new_data) != len(self._last_emitted_data):
            return True

        # Compare key fields for each driver
        for new_driver, old_driver in zip(new_data, self._last_emitted_data):
            # Check fields that affect display structure
            new_position = new_driver.position
            old_position = old_driver.position

            # Build comparison based on visible columns
            changes = (new_driver.car_idx != old_driver.car_idx or
                       new_driver.gap_to_leader != old_driver.gap_to_leader or
                       new_driver.interval != old_driver.interval or
                       new_position != old_position or
                       new_driver.division_position != old_driver.division_position or
                       new_driver.car_number != old_driver.car_number or
                       new_driver.driver_name != old_driver.driver_name or
                       new_driver.is_player != old_driver.is_player or
                       new_driver.is_spectated != old_driver.is_spectated or
                       new_driver.is_finished != old_driver.is_finished or
                       new_driver.division_name != old_driver.division_name)

            # Check optional columns only if they're enabled
            if self.settings.show_delta:
                changes = changes or (new_driver.delta != old_driver.delta)

            if self.settings.show_last_lap:
                changes = changes or (new_driver.last_lap != old_driver.last_lap)

            # Note: Combined Rating (iRating + Safety Rating) doesn't change during a session, so we skip checking it
            # This saves ~0.02ms per frame when the rating column is enabled

            if self.settings.show_pit_lap:
                changes = changes or (new_driver.pit_lap != old_driver.pit_lap)

            if changes:
                return True

        return False

    def check_auto_center(self):
        """Check if auto-center timeout has elapsed and re-engage if needed.

        Called by auto_center_timer every second after user manually scrolls.
        This ensures auto-centering resumes after the timeout period even if
        the race data hasn't changed (event-driven updates wouldn't trigger).
        """
        if self._is_broadcast_roll_active():
            return
        if self.auto_center.should_auto_center():
            # Timeout has elapsed, try to center on player or spectated car
            if (self.player_car_idx is not None or self.spectated_car_idx is not None) and self.displayed_data:
                self.center_on_player(self.displayed_data)
            # Stop the timer since auto-center is now re-engaged
            self.auto_center_timer.stop()

    def _should_show_connection_message(self) -> bool:
        """Check if we should still show initial connection message.

        Returns:
            True if within CONNECTION_MESSAGE_DURATION of initial connection
        """
        return (self.connection_time and
                (time.time() - self.connection_time) < TIMING.CONNECTION_MESSAGE_DURATION)

    def _get_session_state_name(self, session_type: str, session_state: int) -> str:
        """Map session type and state to display name.

        Args:
            session_type: Type of session ("Race", "Practice", "Qualifying", etc.)
            session_state: iRacing session state (0-6)
                0=Invalid, 1=GetInCar, 2=Warmup, 3=ParadeLaps,
                4=Racing, 5=Checkered, 6=CoolDown

        Returns:
            Human-readable state name (includes FCY detection)
        """
        if session_type != "Race":
            return session_type

        # Map session states (some take precedence over FCY)
        state_map = {
            2: "Warmup",
            3: "Pacing",
            5: "Checkered",
            6: "Cool Down"
        }

        # Checkered (5) and Cool Down (6) take precedence over FCY
        # Once race is over, FCY doesn't matter
        if session_state >= 5:
            return state_map.get(session_state, "Race")

        # Check for Full Course Yellow during active racing states
        try:
            session_flags = self.ir['SessionFlags']
            is_fcy = (session_flags & TELEMETRY_CONFIG.FLAG_CAUTION) != 0
            is_fcy_waving = (session_flags & TELEMETRY_CONFIG.FLAG_CAUTION_WAVING) != 0

            if is_fcy or is_fcy_waving:
                return "CAUTION"
        except (KeyError, TypeError):
            pass  # SessionFlags not available, continue with normal state mapping

        return state_map.get(session_state, "Race")

    def _format_time_duration(self, total_seconds: int) -> str:
        """Format time duration as H:MM:SS or M:SS.

        Args:
            total_seconds: Total seconds to format

        Returns:
            Formatted time string
        """
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def _format_lap_based_status(self, state_name: str, session_state: int,
                                 session_laps_total: str, session_type: str,
                                 current_session: Optional[Dict] = None) -> str:
        """Format status text for lap-based sessions.

        Args:
            state_name: Display name of the session state
            session_state: iRacing session state (0-6)
            session_laps_total: Total laps scheduled

        Returns:
            Formatted status text
        """
        try:
            laps_total = int(session_laps_total)
            try:
                race_laps = self.ir['RaceLaps']
            except (KeyError, TypeError):
                race_laps = 0

            # During pacing (negative laps) or before race starts
            if race_laps <= 0 or session_state in [2, 3]:
                # Show total laps scheduled
                status = f"{state_name} - {laps_total} Lap{'s' if laps_total != 1 else ''}"
            else:
                # During racing, show current/total
                current_lap = race_laps
                status = f"{state_name} - Lap {current_lap}/{laps_total}"

            # Solo qualifying: append time remaining when available
            if session_type and "qual" in session_type.lower():
                session_time_remain = None
                try:
                    session_time_remain = self.ir['SessionTimeRemain']
                except (KeyError, TypeError):
                    session_time_remain = None

                if (session_time_remain is None or session_time_remain <= 0) and current_session:
                    session_time_remain = current_session.get('SessionTimeRemain')

                if session_time_remain is not None and session_time_remain > 0:
                    total_seconds = int(session_time_remain)
                    status = f"{status} ({self._format_time_duration(total_seconds)})"

            return status
        except (ValueError, TypeError):
            return state_name

    def _format_time_based_status(self, state_name: str, session_state: int,
                                  current_session: Dict) -> str:
        """Format status text for time-based sessions.

        Args:
            state_name: Display name of the session state
            session_state: iRacing session state (0-6)
            current_session: Current session data

        Returns:
            Formatted status text
        """
        session_time_remain = self.ir['SessionTimeRemain']

        # During pacing or warmup, show scheduled session time
        if session_state in [2, 3]:
            session_time_total = current_session.get('SessionTime', 'unlimited')
            if session_time_total != 'unlimited' and session_time_total not in [0, '0']:
                try:
                    total_seconds_val = int(float(session_time_total.replace(' sec', '')))
                    return f"{state_name} - {self._format_time_duration(total_seconds_val)}"
                except (ValueError, TypeError, AttributeError):
                    return state_name
            else:
                return state_name
        elif session_time_remain is not None and session_time_remain > 0:
            # During active session, show remaining time
            total_seconds = int(session_time_remain)
            class_leader_lap = getattr(self, "class_leader_lap", None)
            lap_suffix = f" (Lap {class_leader_lap})" if state_name == "Race" and class_leader_lap is not None else ""
            return f"{state_name} - {self._format_time_duration(total_seconds)}{lap_suffix}"
        else:
            return state_name

    def _get_session_status_text(self) -> str:
        """Get formatted session status text based on current session info.

        Returns:
            Formatted status string (e.g., "Race - Lap 5/20", "Practice - 5:30")
        """
        try:
            session_info = self.ir['SessionInfo']
            current_session = session_info['Sessions'][self.ir['SessionNum']]
            session_type = current_session['SessionType']

            # Get session state with fallback
            try:
                session_state = self.ir['SessionState']
            except (KeyError, TypeError):
                session_state = 4  # Default to Racing

            # Map session state to display name
            state_name = self._get_session_state_name(session_type, session_state)

            # Check if session is lap-based or time-based
            session_laps_total = current_session.get('SessionLaps', 'unlimited')
            is_lap_based = (session_laps_total != 'unlimited' and
                           session_laps_total not in [0, '0'])

            if is_lap_based:
                return self._format_lap_based_status(
                    state_name, session_state, session_laps_total, session_type, current_session
                )
            else:
                return self._format_time_based_status(state_name, session_state, current_session)

        except (KeyError, TypeError, IndexError, AttributeError) as e:
            logger.debug(f"Status display error: {e}")
            return "Connected - Live Data"

    def update_gui(self):
        """Update GUI status (called by timer).

        Note: This only updates the status label, not the driver list.
        Driver list updates are now event-driven via telemetry thread
        and division filter button clicks.
        """
        try:
            # Skip GUI updates during startup grace period
            if time.time() - self.startup_time < TIMING.STARTUP_GRACE_PERIOD:
                return

            if not self.is_connected:
                self.signals.update_status.emit("Connecting to iRacing...", 'orange')
                return

            # Show initial connection message for a few seconds
            if self._should_show_connection_message():
                self.signals.update_status.emit("Connected - Live Race Data", 'green')
                return

            # Show detailed session status
            status_text = self._get_session_status_text()
            # Use yellow color for CAUTION state, green otherwise
            status_color = 'yellow' if 'CAUTION' in status_text else 'green'
            self.signals.update_status.emit(status_text, status_color)

        except Exception as e:
            logger.error(f"GUI update error: {e}", exc_info=True)
            
    def display_race_data(self, data: List[DriverState]):
        """Display race data (thread-safe slot)"""
        if not data:
            return

        render_data = data
        blank_rows = 0
        separator_index = None
        if self._is_broadcast_roll_active():
            render_data, blank_rows, separator_index = self._get_broadcast_roll_render_data(data)
        else:
            self.broadcast_roll_page_index = 0

        # Clear existing widgets
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new driver rows
        for idx, driver in enumerate(render_data):
            if separator_index is not None and idx == separator_index:
                self.scroll_layout.insertWidget(
                    self.scroll_layout.count() - 1,
                    self._create_broadcast_roll_separator_line()
                )
            row = self.row_renderer.create_row(driver)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row)

        for _ in range(blank_rows):
            self.scroll_layout.insertWidget(
                self.scroll_layout.count() - 1,
                self._create_empty_row_placeholder()
            )

        # Auto-center on player or spectated car
        if (not self._is_broadcast_roll_active()
                and (self.player_car_idx is not None or self.spectated_car_idx is not None)
                and self.auto_center.should_auto_center()):
            self.center_on_player(data)

        self.displayed_data = data.copy()
        self._update_broadcast_roll_mode()

        # Adjust header margins to match scroll area width (accounting for scrollbar)
        self.adjust_header_margins()

    @staticmethod
    def _calculate_broadcast_roll_window(total_drivers: int, visible_rows: int,
                                         roll_rows: int, page_index: int) -> Dict[str, int]:
        """Calculate locked and rolling slices for broadcast standings mode."""
        if total_drivers <= 0 or visible_rows <= 0:
            return {
                'locked_count': 0,
                'roll_start': 0,
                'roll_end': 0,
                'blank_rows': 0,
                'total_pages': 1,
            }

        if visible_rows <= roll_rows and total_drivers > visible_rows:
            total_pages = max(1, math.ceil(total_drivers / visible_rows))
            page = page_index % total_pages
            roll_start = page * visible_rows
            roll_end = min(total_drivers, roll_start + visible_rows)
            blank_rows = max(0, visible_rows - (roll_end - roll_start))
            return {
                'locked_count': 0,
                'roll_start': roll_start,
                'roll_end': roll_end,
                'blank_rows': blank_rows,
                'total_pages': total_pages,
            }

        if total_drivers <= visible_rows:
            return {
                'locked_count': total_drivers,
                'roll_start': min(total_drivers, visible_rows),
                'roll_end': min(total_drivers, visible_rows),
                'blank_rows': 0,
                'total_pages': 1,
            }

        locked_count = max(0, visible_rows - roll_rows)
        rolling_pool = max(0, total_drivers - locked_count)
        total_pages = max(1, math.ceil(rolling_pool / roll_rows))
        page = page_index % total_pages
        roll_start = locked_count + (page * roll_rows)
        roll_end = min(total_drivers, roll_start + roll_rows)
        blank_rows = max(0, roll_rows - (roll_end - roll_start))

        return {
            'locked_count': locked_count,
            'roll_start': roll_start,
            'roll_end': roll_end,
            'blank_rows': blank_rows,
            'total_pages': total_pages,
        }

    @staticmethod
    def _calculate_broadcast_focus_window(total_drivers: int, visible_rows: int,
                                          roll_rows: int, target_index: int) -> Dict[str, int]:
        """Calculate a temporary rolling window centered on a selected off-screen driver."""
        base_window = LeagueOverlay._calculate_broadcast_roll_window(
            total_drivers=total_drivers,
            visible_rows=visible_rows,
            roll_rows=roll_rows,
            page_index=0
        )

        if total_drivers <= 0 or visible_rows <= 0 or not (0 <= target_index < total_drivers):
            return base_window

        locked_count = base_window['locked_count']
        rolling_capacity = visible_rows if locked_count == 0 else roll_rows
        rolling_capacity = max(1, rolling_capacity)
        min_roll_start = locked_count
        max_roll_start = max(min_roll_start, total_drivers - rolling_capacity)
        centered_start = target_index - (rolling_capacity // 2)
        roll_start = max(min_roll_start, min(centered_start, max_roll_start))
        roll_end = min(total_drivers, roll_start + rolling_capacity)
        blank_rows = max(0, rolling_capacity - (roll_end - roll_start))

        return {
            'locked_count': locked_count,
            'roll_start': roll_start,
            'roll_end': roll_end,
            'blank_rows': blank_rows,
            'total_pages': base_window['total_pages'],
        }

    def _is_broadcast_roll_active(self) -> bool:
        show_broadcast_header = (getattr(self.settings, 'show_broadcast_header', False) is True)
        broadcast_roll_enabled = (getattr(self.settings, 'broadcast_roll_enabled', False) is True)
        return show_broadcast_header and broadcast_roll_enabled

    def _estimate_visible_row_capacity(self) -> int:
        if not hasattr(self, 'scroll_area'):
            return len(self.displayed_data) if self.displayed_data else 0

        viewport_height = self.scroll_area.viewport().height()
        margins = self.scroll_layout.contentsMargins()
        spacing = self.scroll_layout.spacing()
        available_height = max(0, viewport_height - margins.top() - margins.bottom())

        sample_row = self.row_renderer.create_row(DriverState(
            car_idx=0,
            driver_info={"CarNumber": "0", "UserName": "Sample"},
            position=1,
            division_position=1,
            division_name="Default",
            division_color="#FFFFFF",
            gap_to_leader="",
            interval="",
            delta="",
            last_lap="",
            best_lap="",
            positions_gained="",
            combined_rating="",
            pit_lap="",
            is_player=False,
            is_finished=False,
            current_lap=0,
            lap_pct=0.0,
        ))
        row_height = sample_row.sizeHint().height()
        sample_row.deleteLater()

        if row_height <= 0:
            return len(self.displayed_data) if self.displayed_data else 0

        per_row = row_height + max(0, spacing)
        if per_row <= 0:
            return len(self.displayed_data) if self.displayed_data else 0

        return max(1, available_height // per_row)

    def _get_broadcast_roll_rows(self) -> int:
        try:
            value = int(getattr(self.settings, 'broadcast_roll_rows', TIMING.BROADCAST_ROLL_ROWS))
        except (TypeError, ValueError):
            value = TIMING.BROADCAST_ROLL_ROWS
        return max(1, min(20, value))

    def _get_broadcast_roll_interval_seconds(self) -> int:
        try:
            value = int(getattr(self.settings, 'broadcast_roll_interval_seconds', TIMING.BROADCAST_ROLL_INTERVAL_SECONDS))
        except (TypeError, ValueError):
            value = TIMING.BROADCAST_ROLL_INTERVAL_SECONDS
        return max(1, min(60, value))

    def _get_broadcast_roll_locked_window(self, data: List[DriverState]) -> Optional[Dict[str, int]]:
        """Return a focused rolling window when the selected driver is off-screen."""
        if not data:
            return None

        selected_car_idx = self.spectated_car_idx
        if selected_car_idx is None:
            return None

        visible_rows = self._estimate_visible_row_capacity()
        roll_rows = self._get_broadcast_roll_rows()
        current_window = self._calculate_broadcast_roll_window(
            total_drivers=len(data),
            visible_rows=visible_rows,
            roll_rows=roll_rows,
            page_index=self.broadcast_roll_page_index
        )

        if current_window['total_pages'] <= 1:
            return None

        target_index = next(
            (index for index, driver in enumerate(data) if driver.car_idx == selected_car_idx),
            None
        )
        if target_index is None:
            return None

        if target_index < current_window['locked_count']:
            return None

        if current_window['roll_start'] <= target_index < current_window['roll_end']:
            return None

        return self._calculate_broadcast_focus_window(
            total_drivers=len(data),
            visible_rows=visible_rows,
            roll_rows=roll_rows,
            target_index=target_index
        )

    def _get_broadcast_roll_render_data(self, data: List[DriverState]) -> tuple[List[DriverState], int, Optional[int]]:
        locked_window = self._get_broadcast_roll_locked_window(data)
        if locked_window is not None:
            window = locked_window
        else:
            visible_rows = self._estimate_visible_row_capacity()
            roll_rows = self._get_broadcast_roll_rows()
            window = self._calculate_broadcast_roll_window(
                total_drivers=len(data),
                visible_rows=visible_rows,
                roll_rows=roll_rows,
                page_index=self.broadcast_roll_page_index
            )
        self.broadcast_roll_page_index %= window['total_pages']
        locked = data[:window['locked_count']]
        rolling = data[window['roll_start']:window['roll_end']]
        separator_index: Optional[int] = len(locked) if locked and rolling else None
        return (locked + rolling, window['blank_rows'], separator_index)

    def _create_empty_row_placeholder(self) -> QWidget:
        spacer = QWidget()
        spacer.setFixedHeight(self.get_font_size('spacing') + 18)
        spacer.setStyleSheet("background-color: transparent; border: none;")
        return spacer

    def _create_broadcast_roll_separator_line(self) -> QWidget:
        separator = QWidget()
        separator.setFixedHeight(1)
        separator.setStyleSheet(
            f"background-color: {self.broadcast_header_accent_color}; border: none;"
        )
        return separator

    def _update_broadcast_roll_mode(self) -> None:
        if not hasattr(self, 'scroll_area'):
            return

        rerender_needed = False

        if self._is_broadcast_roll_active():
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            interval_ms = int(self._get_broadcast_roll_interval_seconds() * 1000)
            if self.broadcast_roll_timer.interval() != interval_ms:
                self.broadcast_roll_timer.setInterval(interval_ms)

            should_roll = False
            locked_window = None
            if self.displayed_data:
                locked_window = self._get_broadcast_roll_locked_window(self.displayed_data)
                roll_rows = self._get_broadcast_roll_rows()
                window = self._calculate_broadcast_roll_window(
                    total_drivers=len(self.displayed_data),
                    visible_rows=self._estimate_visible_row_capacity(),
                    roll_rows=roll_rows,
                    page_index=self.broadcast_roll_page_index
                )
                should_roll = window['total_pages'] > 1 and locked_window is None

            if should_roll:
                if not self.broadcast_roll_timer.isActive():
                    self.broadcast_roll_timer.start()
            else:
                preserve_page_index = locked_window is not None
                was_rolling = self.broadcast_roll_timer.isActive() or (
                    self.broadcast_roll_page_index != 0 and not preserve_page_index
                )
                self.broadcast_roll_timer.stop()
                if not preserve_page_index:
                    self.broadcast_roll_page_index = 0
                rerender_needed = was_rolling
        else:
            was_rolling = self.broadcast_roll_timer.isActive() or self.broadcast_roll_page_index != 0
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.broadcast_roll_timer.stop()
            self.broadcast_roll_page_index = 0
            rerender_needed = was_rolling

        if rerender_needed and self.displayed_data:
            self.display_race_data(self.displayed_data.copy())

    def advance_broadcast_roll_window(self) -> None:
        if not self._is_broadcast_roll_active() or not self.displayed_data:
            self.broadcast_roll_timer.stop()
            return

        if self._get_broadcast_roll_locked_window(self.displayed_data) is not None:
            self.broadcast_roll_timer.stop()
            self.display_race_data(self.displayed_data.copy())
            return

        roll_rows = self._get_broadcast_roll_rows()
        window = self._calculate_broadcast_roll_window(
            total_drivers=len(self.displayed_data),
            visible_rows=self._estimate_visible_row_capacity(),
            roll_rows=roll_rows,
            page_index=self.broadcast_roll_page_index
        )
        if window['total_pages'] <= 1:
            self.broadcast_roll_timer.stop()
            self.broadcast_roll_page_index = 0
            return

        self.broadcast_roll_page_index = (self.broadcast_roll_page_index + 1) % window['total_pages']
        self.display_race_data(self.displayed_data.copy())

    def adjust_header_margins(self):
        """Adjust header right margin based on scrollbar visibility to maintain column alignment."""
        # Check if vertical scrollbar is visible
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar_visible = scrollbar.isVisible()

        # Base margins: (5, 2, 5, 2)
        # When scrollbar is visible (6px wide), add 6px to right margin to match reduced viewport
        # Header: (5, 2, 11, 2) = W - 16px content
        # Scroll: (W - 6px scrollbar) - 10px (5+5 margins) = W - 16px content
        right_margin = 11 if scrollbar_visible else 5
        self.header_layout.setContentsMargins(5, 2, right_margin, 2)

    def show_context_menu(self, driver: DriverState):
        """Display right-click menu to assign driver to a division."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {UI_COLORS.HEADER_DARK_GRAY};
                color: white;
                border: 1px solid {UI_COLORS.BUTTON_GRAY};
            }}
            QMenu::item:selected {{
                background-color: {UI_COLORS.BUTTON_GRAY};
            }}
        """)

        menu.addAction("Change Division").setEnabled(False)
        menu.addSeparator()

        driver_info = driver.driver_info

        for division_name in self.division_manager.division_colors.keys():
            action = menu.addAction(division_name)
            action.triggered.connect(
                lambda checked, d=division_name, info=driver_info:
                self.set_driver_division(info, d)
            )

        # Use cursor position directly to avoid coordinate mapping issues
        menu.exec(QCursor.pos())
        
    def center_on_player(self, current_data: List[DriverState]):
        """Auto-center the scroll view on the target driver's position.

        Centers on the spectated car (CamCarIdx) when spectating, otherwise
        on the player's own car. Only activates if the user hasn't manually
        scrolled recently (see manual_scroll_timeout).
        """
        if not current_data:
            return

        # Prefer spectated car, fall back to player car
        target_car_idx = self.spectated_car_idx if self.spectated_car_idx is not None else self.player_car_idx
        if target_car_idx is None:
            return

        # Find the target driver in the current display data
        target_index = None
        for i, driver in enumerate(current_data):
            if driver.car_idx == target_car_idx:
                target_index = i
                break

        if target_index is None:
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

        # Calculate scroll position to center target driver vertically in viewport
        target_top_position = target_index * item_height
        target_scroll = target_top_position - (viewport_height / 2) + (item_height / 2)

        # Clamp to valid scroll range [0, maximum]
        target_scroll = max(0, min(target_scroll, scrollbar.maximum()))

        scrollbar.setValue(int(target_scroll))

    # Mouse events for dragging the frameless window
    def mousePressEvent(self, event):
        """Enable dragging the frameless window by its title bar.
        Why this exists: With Qt.FramelessWindowHint, we lose the default OS
        window dragging. This reimplements it for the title bar area.
        """
        if event.button() == Qt.LeftButton:
            # Check if in title bar for dragging
            if event.position().y() < UI_DIMENSIONS.TITLE_BAR_HEIGHT:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        """Update window position during drag operation."""
        if event.buttons() == Qt.LeftButton:
            if not self.drag_position.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

    def mouseReleaseEvent(self, _event):
        """End drag operation."""
        self.drag_position = QPoint()


def main():
    # Load settings first to get log level
    import logging
    from config.settings import SettingsManager

    settings_manager = SettingsManager()
    settings = settings_manager.load()

    # Map string log level to logging constant
    log_level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR
    }
    log_level = log_level_map.get(settings.log_level, logging.INFO)

    # Setup logging with user's configured level
    log_file_path = setup_logging(log_level=log_level)
    logger.info("="*60)
    logger.info(f"BB's League Overlay v{VERSION} - Starting")
    logger.info(f"Log level: {settings.log_level}")
    logger.info("="*60)

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
    
    try:
        overlay = LeagueOverlay()
        overlay.show()
        logger.debug("Application window displayed successfully")

        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Fatal error during application startup: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
