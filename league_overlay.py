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
from typing import Dict, List, Optional
import irsdk

# Import from modular structure
from config.constants import (
    UI_CONFIG, FILE_CONFIG, VERSION,
    UI_COLORS, UI_DIMENSIONS, COLUMN_LAYOUT, TIMING
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

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QGridLayout, QMenu,
)
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPalette, QCursor

# Get logger for this module
logger = get_logger(__name__)


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

        self.player_car_idx = None  # Player's car (from iRacing API)

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

        # Apply loaded settings to instance variables
        # (These are maintained for backward compatibility with existing code)
        self.opacity = self.settings.opacity
        self.width = self.settings.width
        self.height = self.settings.height
        self.x = self.settings.x
        self.y = self.settings.y
        self.hide_headers = self.settings.hide_headers
        self.center_drivers = self.settings.center_drivers
        self.bold_drivers = self.settings.bold_drivers
        self.show_division_gap = self.settings.show_division_gap
        self.font_size = self.settings.font_size
        self.row_color_style = self.settings.row_color_style
        self.refresh_rate = self.settings.refresh_rate
        self.color_config_file = self.settings.league_config or "league_divisions.json"

        # User preferences not in settings (runtime state)
        self.top_elements_visible = True  # Current visibility of title/status
        self._update_counter = 0  # Counter for forcing periodic UI updates (for gap changes)

        # Font size mappings (use UI_CONFIG)
        self.font_sizes = UI_CONFIG.FONT_SIZES

        # ═══════════════════════════════════════════════════════════
        # HELPER CLASSES - Extracted responsibilities
        # ═══════════════════════════════════════════════════════════
        # Initialize DivisionManager with league config if specified
        division_config = self.settings.league_config if self.settings.league_config else FILE_CONFIG.DIVISIONS_FILE
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

        # Show version
        self.show_version_on_startup()

        # Focus tracking for auto-hide
        self.hide_timer = None
        self.setMouseTracking(True)

    def get_bg_color(self, base_color):
        """Convert a hex color to RGBA format with current window opacity."""
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
        """
        if element_type == "spacing":
            return self.font_sizes.get(self.font_size, self.font_sizes["Medium"]).get(element_type, 3)
        return self.font_sizes.get(self.font_size, self.font_sizes["Medium"]).get(element_type, "9pt")

    def update_all_backgrounds(self):
        """Refresh all UI backgrounds, fonts, and styling after settings change.
        Assumptions:
            - self.opacity and self.font_size are already updated with new values
        """
        # TODO: set opacity and font_size here for consistency then update comment above
        if hasattr(self, 'main_widget'):
            self.main_widget.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
        if hasattr(self, 'title_bar'):
            self.title_bar.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
        if hasattr(self, 'header_frame'):
            self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
            # Update header text when show_division_gap changes
            self._update_header_labels()
        if hasattr(self, 'scroll_area'):
            self.update_scroll_area_style()
        if hasattr(self, 'scroll_content'):
            self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
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
        
        # Status label
        self.status_label = QLabel("Connecting to iRacing...")
        self.update_status_style("orange")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.status_label)

        # Header frame
        self.header_frame = QWidget()
        self.header_frame.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};")
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
        self.scroll_content.setStyleSheet(f"background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};")
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
        self.size_grip.setFixedSize(UI_DIMENSIONS.SIZE_GRIP_SIZE, UI_DIMENSIONS.SIZE_GRIP_SIZE)
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
                background-color: {self.get_bg_color(UI_COLORS.BACKGROUND_BLACK)};
            }}
            QScrollBar:vertical {{
                background: {self.get_bg_color(UI_COLORS.SCROLLBAR_GRAY)};
                width: 6px;
                margin: 0px;
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

        # Add padding on right to account for scrollbar (6px scrollbar + 5px margin)
        self.header_layout.setContentsMargins(5, 2, 11, 2)
        self.header_layout.setSpacing(2)
        
        # Column proportions - adjust based on style
        is_stream_style = self.row_color_style == "Stream"

        self.header_layout.setColumnStretch(0, COLUMN_LAYOUT.POS)
        self.header_layout.setColumnStretch(1, COLUMN_LAYOUT.DIV_POS)
        if is_stream_style:
            # Stream: Position | Div Pos | Driver Name | Car Number | Gap
            self.header_layout.setColumnStretch(2, COLUMN_LAYOUT.DRIVER_NAME)
            self.header_layout.setColumnStretch(3, COLUMN_LAYOUT.CAR_NUM)
        else:
            # Default: Position | Div Pos | Car Number | Driver Name | Gap
            self.header_layout.setColumnStretch(2, COLUMN_LAYOUT.CAR_NUM)
            self.header_layout.setColumnStretch(3, COLUMN_LAYOUT.DRIVER_NAME)
        self.header_layout.setColumnStretch(4, COLUMN_LAYOUT.GAP)

        # Set gap header based on show_division_gap setting
        gap_header = "Div Gap" if self.show_division_gap else "Gap"

        # Set header labels based on style
        if is_stream_style:
            headers = ["Pos", "D-Pos", "Driver", "Car#", gap_header]
        else:
            headers = ["Pos", "D-Pos", "Car#", "Driver", gap_header]

        for i, header in enumerate(headers):
            label = QLabel(header)
            label.setStyleSheet(f"""
                QLabel {{
                    color: white;
                    background-color: {self.get_bg_color(UI_COLORS.HEADER_DARK_GRAY)};
                    font-weight: bold;
                    font-size: {self.get_font_size('header')};
                }}
            """)
            label.setAlignment(Qt.AlignCenter)
            self.header_layout.addWidget(label, 0, i)

    def _update_header_labels(self):
        """Update header labels when settings change (e.g., show_division_gap toggle)."""
        if not hasattr(self, 'header_layout'):
            return

        # Get the 5th column (index 4) which is the gap header
        gap_label_widget = self.header_layout.itemAtPosition(0, 4)
        if gap_label_widget:
            gap_label = gap_label_widget.widget()
            if gap_label:
                gap_header = "Div Gap" if self.show_division_gap else "Gap"
                gap_label.setText(gap_header)

    def show_version_on_startup(self):
        """Show version on startup"""
        self.status_label.setText(f"BB's League Overlay v{VERSION}")
        self.update_status_style("orange")
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
        self.division_filter.cycle_filter(self.race_data, self.player_car_idx)

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
            current_data = self.division_filter.apply_filter(self.race_data, self.player_car_idx)
            self._last_emitted_data = current_data.copy()
            self.signals.update_data.emit(current_data)
        
    def on_manual_scroll(self):
        """Record when user manually scrolls, to temporarily disable auto-centering."""
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

    def load_settings(self):
        """Load user preferences from disk and apply to instance variables."""
        self.settings = self.settings_manager.load()

        # Apply settings to instance variables
        self.opacity = self.settings.opacity
        self.width = self.settings.width
        self.height = self.settings.height
        self.x = self.settings.x
        self.y = self.settings.y
        self.hide_headers = self.settings.hide_headers
        self.center_drivers = self.settings.center_drivers
        self.bold_drivers = self.settings.bold_drivers
        self.show_division_gap = self.settings.show_division_gap
        self.font_size = self.settings.font_size
        self.row_color_style = self.settings.row_color_style
        self.refresh_rate = self.settings.refresh_rate

        # Handle league config file if specified
        if self.settings.league_config and os.path.exists(self.settings.league_config):
            self.color_config_file = self.settings.league_config

            # Reload DivisionManager with custom config
            self.division_manager = DivisionManager(self.settings.league_config)

    def save_settings(self):
        """Persist current settings - delegates to SettingsManager."""
        # Update settings object with current values
        self.settings.league_config = self.color_config_file
        self.settings.division_colors = self.division_manager.division_colors
        self.settings.x = self.geometry().x()
        self.settings.y = self.geometry().y()
        self.settings.height = self.geometry().height()
        self.settings.width = self.geometry().width()
        self.settings.opacity = self.opacity
        self.settings.refresh_rate = self.refresh_rate
        self.settings.hide_headers = self.hide_headers
        self.settings.center_drivers = self.center_drivers
        self.settings.bold_drivers = self.bold_drivers
        self.settings.show_division_gap = self.show_division_gap
        self.settings.font_size = self.font_size
        self.settings.row_color_style = self.row_color_style

        # Delegate to settings manager
        self.settings_manager.save(self.settings)
            

    def set_driver_division(self, driver_info: Dict[str, str], division_name: str) -> None:
        """Assign a driver to a division - delegates to DivisionManager.

        The telemetry processor will pick up the new division assignment
        on the next update cycle and refresh the UI automatically.
        """
        # Delegate to DivisionManager for assignment logic
        self.division_manager.set_driver_division(driver_info, division_name)

        # Save configuration
        self.division_manager.save_config()

    def refresh_driver_colors(self):
        """Refresh all driver colors"""
        if self.displayed_data:
            # Force update even if data unchanged (colors changed)
            self._last_emitted_data = []
            self.signals.update_data.emit(self.displayed_data.copy())

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
            # Start hide timer
            if self.hide_timer:
                self.killTimer(self.hide_timer)
            self.hide_timer = self.startTimer(TIMING.AUTO_HIDE_DELAY)
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
                            show_division_gap=self.show_division_gap
                        )

                        # Debug logging for checkered flag
                        if self.race_state_tracker.is_checkered():
                            logger.debug(f"TELEMETRY LOOP - Got race_data: {race_data is not None}, count: {len(race_data) if race_data else 0}")

                        # Handle the telemetry update (session sync, data update)
                        self._handle_telemetry_update(race_data)
                    else:
                        self.is_connected = False
                        self.connection_time = None  # Reset connection time on disconnect
                        self.ir.shutdown()

                if self.race_state_tracker.is_checkered():
                    time.sleep(TIMING.CHECKERED_REFRESH)  # refresh more often to track finish times
                else:
                    time.sleep(self.refresh_rate)

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
        # Debug logging for checkered flag
        if self.race_state_tracker.is_checkered():
            logger.debug(f"HANDLE_UPDATE - Entered _handle_telemetry_update, race_data is None: {race_data is None}")

        if race_data is None:
            if self.race_state_tracker.is_checkered():
                logger.debug("HANDLE_UPDATE - race_data is None during checkered flag! Returning early.")
            return

        # Detect session change by comparing with processor's session info
        session_changed = (
            self.current_session_id != self.telemetry_processor.current_session_id or
            self.current_session_type != self.telemetry_processor.current_session_type
        )

        # Sync session info from telemetry processor
        self.current_session_id = self.telemetry_processor.current_session_id
        self.current_session_type = self.telemetry_processor.current_session_type

        # Clear old data on session change (only if we have a valid session)
        if session_changed and self.current_session_id is not None:
            self.race_data = []
            self._last_emitted_data = []  # Reset change tracking on session change
            self.division_filter.reset()  # Reset division filter on session change

        # Update race data and player info
        self.race_data = race_data
        self.player_car_idx = self.telemetry_processor.position_calculator.player_car_idx

        # Immediately emit UI update with new data (event-driven)
        # Only update if data has actually changed to avoid redundant widget rebuilds
        if race_data:
            current_data = self._filter_by_division(race_data)

            # Debug logging for checkered flag issues
            if self.race_state_tracker.is_checkered():
                logger.debug(f"CHECKERED FLAG - Race data count: {len(race_data)}, Filtered data count: {len(current_data)}")
                logger.debug(f"CHECKERED FLAG - Filter state: show_only_my_division={self.division_filter.show_only_my_division}, current_division_filter={self.division_filter.current_division_filter}")
                if len(current_data) != len(race_data):
                    logger.debug(f"CHECKERED FLAG - Data was filtered! Original: {len(race_data)} -> Filtered: {len(current_data)}")

            # Check if data changed structurally
            data_changed = self._has_data_changed(current_data)

            # During checkered flag: Force update every 5 cycles to refresh gaps (5 × 0.1s = 0.5s)
            # During normal racing: Always update (gaps trigger immediate updates)
            force_update = False
            if self.race_state_tracker.is_checkered():
                self._update_counter += 1
                force_update = self._update_counter >= 5
                if force_update:
                    self._update_counter = 0
            else:
                # Not checkered - always allow updates (reset counter for consistency)
                self._update_counter = 0
                force_update = True

            if data_changed or force_update:
                self._last_emitted_data = current_data.copy()
                self.signals.update_data.emit(current_data)

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
            # Check fields that affect display structure (NOT gap - it changes constantly)
            if (new_driver.get('car_idx') != old_driver.get('car_idx') or
                new_driver.get('position') != old_driver.get('position') or
                new_driver.get('division_position') != old_driver.get('division_position') or
                new_driver.get('car_number') != old_driver.get('car_number') or
                new_driver.get('driver_name') != old_driver.get('driver_name') or
                new_driver.get('is_player') != old_driver.get('is_player')):
                return True

            # Check if driver division changed (affects color)
            new_info = new_driver.get('driver_info', {})
            old_info = old_driver.get('driver_info', {})
            if (new_info.get('UserID') != old_info.get('UserID') or
                new_info.get('UserName') != old_info.get('UserName')):
                return True

        return False

    def _filter_by_division(self, race_data: List[DriverState]) -> List[DriverState]:
        """Filter race data based on division filter settings.

        Delegates to DivisionFilter for actual filtering logic.

        Args:
            race_data: Full list of driver data to filter

        Returns:
            Filtered list of driver data
        """
        filtered_data = self.division_filter.apply_filter(race_data, self.player_car_idx)

        # Debug logging for checkered flag issues
        if self.race_state_tracker.is_checkered() and len(filtered_data) != len(race_data):
            logger.debug(f"FILTER - Applied division filter: {len(race_data)} -> {len(filtered_data)} drivers")
            logger.debug(f"FILTER - player_car_idx: {self.player_car_idx}")
            filtered_indices = [d.car_idx for d in filtered_data]
            removed_indices = [d.car_idx for d in race_data if d.car_idx not in filtered_indices]
            logger.debug(f"FILTER - Removed car indices: {removed_indices}")

        return filtered_data

    def check_auto_center(self):
        """Check if auto-center timeout has elapsed and re-engage if needed.

        Called by auto_center_timer every second after user manually scrolls.
        This ensures auto-centering resumes after the timeout period even if
        the race data hasn't changed (event-driven updates wouldn't trigger).
        """
        if self.auto_center.should_auto_center():
            # Timeout has elapsed, try to center on player
            if self.player_car_idx is not None and self.displayed_data:
                self.center_on_player(self.displayed_data)
            # Stop the timer since auto-center is now re-engaged
            self.auto_center_timer.stop()

    def update_gui(self):
        """Update GUI status (called by timer).

        Note: This only updates the status label, not the driver list.
        Driver list updates are now event-driven via telemetry thread
        and division filter button clicks.
        """
        try:
            if time.time() - self.startup_time < TIMING.STARTUP_GRACE_PERIOD:
                return

            if self.is_connected:
                # Show initial connection message for 5 seconds
                if self.connection_time and (time.time() - self.connection_time) < 5.0:
                    self.signals.update_status.emit("Connected - Live Race Data", 'green')
                else:
                    # After 5 seconds, show session type and time/lap info
                    try:
                        session_info = self.ir['SessionInfo']
                        current_session = session_info['Sessions'][self.ir['SessionNum']]
                        session_type = current_session['SessionType']

                        # Get session state (0=Invalid, 1=GetInCar, 2=Warmup, 3=ParadeLaps, 4=Racing, 5=Checkered, 6=CoolDown)
                        try:
                            session_state = self.ir['SessionState']
                        except (KeyError, TypeError):
                            session_state = 4

                        # Determine display state
                        state_name = session_type  # Default to session type
                        if session_type == "Race":
                            if session_state == 2:
                                state_name = "Warmup"
                            elif session_state == 3:
                                state_name = "Pacing"
                            elif session_state == 5:
                                state_name = "Checkered"
                            elif session_state == 6:
                                state_name = "Cool Down"
                            # else session_state == 4 (Racing), keep "Race"

                        # Check if session is lap-based or time-based
                        session_laps_total = current_session.get('SessionLaps', 'unlimited')
                        is_lap_based = session_laps_total != 'unlimited' and session_laps_total not in [0, '0']

                        if is_lap_based:
                            # Lap-based session
                            try:
                                laps_total = int(session_laps_total)
                                try:
                                    race_laps = self.ir['RaceLaps']
                                except (KeyError, TypeError):
                                    race_laps = 0

                                # During pacing (negative laps) or before race starts
                                if race_laps <= 0 or session_state in [2, 3]:
                                    # Show total laps scheduled
                                    status_text = f"{state_name} - {laps_total} Lap{'s' if laps_total != 1 else ''}"
                                else:
                                    # During racing, show current/total
                                    current_lap = race_laps
                                    status_text = f"{state_name} - Lap {current_lap}/{laps_total}"
                            except (ValueError, TypeError):
                                status_text = state_name
                        else:
                            # Time-based session
                            session_time_remain = self.ir['SessionTimeRemain']

                            # During pacing or warmup, show scheduled session time
                            if session_state in [2, 3]:
                                session_time_total = current_session.get('SessionTime', 'unlimited')
                                if session_time_total != 'unlimited' and session_time_total not in [0, '0']:
                                    try:
                                        total_seconds_val = int(float(session_time_total.replace(' sec', '')))
                                        hours = total_seconds_val // 3600
                                        minutes = (total_seconds_val % 3600) // 60
                                        seconds = total_seconds_val % 60

                                        if hours > 0:
                                            status_text = f"{state_name} - {hours}:{minutes:02d}:{seconds:02d}"
                                        else:
                                            status_text = f"{state_name} - {minutes}:{seconds:02d}"
                                    except (ValueError, TypeError, AttributeError):
                                        status_text = state_name
                                else:
                                    status_text = state_name
                            elif session_time_remain is not None and session_time_remain > 0:
                                # During active session, show remaining time
                                total_seconds = int(session_time_remain)
                                hours = total_seconds // 3600
                                minutes = (total_seconds % 3600) // 60
                                seconds = total_seconds % 60

                                if hours > 0:
                                    status_text = f"{state_name} - {hours}:{minutes:02d}:{seconds:02d}"
                                else:
                                    status_text = f"{state_name} - {minutes}:{seconds:02d}"
                            else:
                                status_text = state_name

                    except (KeyError, TypeError, IndexError, AttributeError) as e:
                        logger.debug(f"Status display error: {e}")
                        status_text = "Connected - Live Data"

                    self.signals.update_status.emit(status_text, 'green')
            else:
                self.signals.update_status.emit("Connecting to iRacing...", 'orange')

        except Exception as e:
            logger.error(f"GUI update error: {e}", exc_info=True)
            
    def display_race_data(self, data: List[DriverState]):
        """Display race data (thread-safe slot)"""
        if not data:
            logger.debug("display_race_data called with empty data")
            return

        # Debug logging for checkered flag issues
        if self.race_state_tracker.is_checkered():
            logger.debug(f"DISPLAY - Checkered flag active, displaying {len(data)} drivers")
            driver_list = [f"P{d.real_time_position or d.official_position} {d.driver_info.get('UserName', 'Unknown')} (idx:{d.car_idx})" for d in data]
            logger.debug(f"DISPLAY - Driver list: {driver_list}")

        # Clear existing widgets
        while self.scroll_layout.count() > 1:
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add new driver rows
        for driver in data:
            row = self.row_renderer.create_row(driver)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row)

        # Auto-center on player
        if self.player_car_idx is not None and self.auto_center.should_auto_center():
            self.center_on_player(data)

        self.displayed_data = data.copy()
    
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
        """Auto-center the scroll view on the player's position.
        This only activates if the user hasn't manually scrolled recently
        (see manual_scroll_timeout). Helps keep player visible during races
        without fighting manual scrolling.
        """
        if not current_data or self.player_car_idx is None:
            return

        # Find the player in the current display data
        player_index = None
        for i, driver in enumerate(current_data):
            if driver.car_idx == self.player_car_idx:
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
        logger.info("Application window displayed successfully")

        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Fatal error during application startup: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
