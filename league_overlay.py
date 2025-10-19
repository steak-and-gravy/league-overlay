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
import json
import os
import re
from typing import Dict, List, Optional
import irsdk

# Import from modular structure
from config.constants import UI_CONFIG, FILE_CONFIG, VERSION
from config.settings import SettingsManager
from config.logging_config import setup_logging, get_logger
from core.gap_calculator import GapCalculator
from core.division_manager import DivisionManager
from core.race_state_tracker import RaceStateTracker
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


class LeagueOverlay(QMainWindow):
    """Main application window for iRacing race position overlay."""

    def __init__(self):
        super().__init__()
        self.ir = irsdk.IRSDK()  # iRacing SDK connection object
        self.is_connected = False  # Connection status flag
        self.running = True  # Thread control flag

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
        self.font_size = self.settings.font_size
        self.row_color_style = self.settings.row_color_style
        self.refresh_rate = self.settings.refresh_rate
        self.color_config_file = self.settings.league_config or "league_divisions.json"

        # User preferences not in settings (runtime state)
        self.show_only_my_division = False  # Filter to player's division only
        self.top_elements_visible = True  # Current visibility of title/status
        self.current_division_filter = None  # Active spectator division filter
        self.division_cycle_order = ["Pro", "ProAm", "Am", "Rookie", "All"]

        # Font size mappings (use UI_CONFIG)
        self.font_sizes = UI_CONFIG.FONT_SIZES

        # ═══════════════════════════════════════════════════════════
        # HELPER CLASSES - Extracted responsibilities
        # ═══════════════════════════════════════════════════════════
        # Initialize DivisionManager with league config if specified
        division_config = self.settings.league_config if self.settings.league_config else FILE_CONFIG.DIVISIONS_FILE
        self.division_manager = DivisionManager(division_config)
        self.race_state_tracker = RaceStateTracker()
        self.gap_calculator = GapCalculator()
        self.row_renderer = DriverRowRenderer(self)

        # TelemetryProcessor - handles all telemetry processing logic
        self.telemetry_processor = TelemetryProcessor(
            self.ir,
            self.division_manager,
            self.race_state_tracker,
            self.gap_calculator
        )

        # Session tracking (now managed by TelemetryProcessor, kept for compatibility)
        self.current_session_id: Optional[int] = None
        self.current_session_type: Optional[str] = None
        self.player_car_class_id: Optional[int] = None

        # Update checking
        self.update_check_done: bool = False
        self.latest_version: Optional[str] = None

        # Legacy compatibility - keep references for backward compatibility
        # These delegate to the helper classes
        self.driver_colors = self.division_manager.driver_colors
        self.available_colors = self.division_manager.division_colors

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
        tinted = self.blend_color_with_black(color_hex, 0.25)
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {tinted}, stop:0.5 #1a1a1a, stop:1 {tinted})"

    def update_all_backgrounds(self):
        """Refresh all UI backgrounds, fonts, and styling after settings change.
        Assumptions:
            - self.opacity and self.font_size are already updated with new values
        """
        # TODO: set opacity and font_size here for consistency then update comment above
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
                    background-color: transparent;
                }}
            """)
        if hasattr(self, 'division_btn'):
            # Get current color from the button
            current_style = self.division_btn.styleSheet()
            if "background-color:" in current_style:
                # Extract background color
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
    
    def update_status_label(self, text, color):
        """Display connection status and session type at top of overlay.
        Examples: "Connecting...", "Connected - Live Data (Race)", "Update available"
        """
        self.status_label.setText(text)
        self.update_status_style(color)

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
                background-color: transparent;
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
        """Check GitHub for updates using the UpdateChecker."""
        return self.update_checker.check_for_update()
            
    def toggle_division_filter(self):
        """Toggle division filter - cycles through different division views.
        Two modes:
        1. Player is on track: Toggle between "All Divisions" and "My Division"
        2. Player spectating: Cycle through each division (Pro -> ProAm -> Am -> Rookie -> All)
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

        # Immediately apply the filter and update UI
        # Force update even if data unchanged (filter criteria changed)
        if self.race_data:
            current_data = self._filter_by_division(self.race_data)
            self._last_emitted_data = current_data.copy()
            self.signals.update_data.emit(current_data)
        
    def on_manual_scroll(self):
        """Record when user manually scrolls, to temporarily disable auto-centering."""
        self.auto_center.on_manual_interaction()

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
        
    def load_color_config(self):
        """Load the driver-to-division mapping from JSON config file.
        Returns:
            Dict with 'drivers' key containing list of driver entries:
            {'drivers': [
                {'id': '12345', 'name': 'John Doe', 'division': 'Pro'},
                ...
            ]}
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
                logger.error(f"Error loading color config: {e}", exc_info=True)
                print(f"Error loading color config: {e}")
        return {'drivers': []}
        
    def load_settings(self):
        """Load user preferences - delegates to SettingsManager.

        This method is kept for backward compatibility but now delegates
        to the SettingsManager for all persistence logic.
        """
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
        self.font_size = self.settings.font_size
        self.row_color_style = self.settings.row_color_style
        self.refresh_rate = self.settings.refresh_rate

        # Handle league config file if specified
        if self.settings.league_config and os.path.exists(self.settings.league_config):
            self.color_config_file = self.settings.league_config
            self.driver_colors = self.load_color_config()

            # Reload DivisionManager with custom config
            self.division_manager = DivisionManager(self.settings.league_config)
            self.available_colors = self.division_manager.division_colors

    def save_settings(self):
        """Persist current settings - delegates to SettingsManager.

        This method is kept for backward compatibility but now delegates
        to the SettingsManager for all persistence logic.
        """
        # Update settings object with current values
        self.settings.league_config = self.color_config_file
        self.settings.division_colors = self.available_colors
        self.settings.x = self.geometry().x()
        self.settings.y = self.geometry().y()
        self.settings.height = self.geometry().height()
        self.settings.width = self.geometry().width()
        self.settings.opacity = self.opacity
        self.settings.refresh_rate = self.refresh_rate
        self.settings.hide_headers = self.hide_headers
        self.settings.center_drivers = self.center_drivers
        self.settings.bold_drivers = self.bold_drivers
        self.settings.font_size = self.font_size
        self.settings.row_color_style = self.row_color_style

        # Delegate to settings manager
        self.settings_manager.save(self.settings)
            

    def set_driver_division(self, driver_info: Dict[str, str], division_name: str) -> None:
        """Assign a driver to a division - delegates to DivisionManager."""
        # Delegate to DivisionManager for assignment logic
        self.division_manager.set_driver_division(driver_info, division_name)

        # Update legacy self.driver_colors reference for backward compatibility
        self.driver_colors = self.division_manager.driver_colors

        # Save configuration
        self.division_manager.save_config()

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
                # Trigger full refresh (force update even if data unchanged)
                self._last_emitted_data = []
                self.signals.update_data.emit(self.displayed_data.copy())
                break
                
    def get_driver_color(self, driver_info):
        """Get color for driver"""
        division_name = self.division_manager.get_driver_division(driver_info)
        if division_name:
            return self.available_colors.get(division_name, self.available_colors["Default"])
        return self.available_colors["Default"]
        
    def refresh_driver_colors(self):
        """Refresh all driver colors"""
        self.driver_colors = self.load_color_config()
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
        self.driver_colors = self.load_color_config()

        # Reload DivisionManager with the new config file
        self.division_manager = DivisionManager(config_file_path)
        self.available_colors = self.division_manager.division_colors

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
        """Background thread that continuously reads data from iRacing SDK."""
        while self.running:
            try:
                if not self.is_connected:
                    if self.ir.startup():
                        self.is_connected = True
                        
                if self.is_connected:
                    if self.ir.is_connected and self.ir.is_initialized:
                        # Delegate to TelemetryProcessor
                        race_data = self.telemetry_processor.process_telemetry(
                            get_driver_color_fn=self.get_driver_color
                        )
                        # Handle the telemetry update (session sync, data update)
                        self._handle_telemetry_update(race_data)
                    else:
                        self.is_connected = False
                        self.ir.shutdown()

                if self.race_state_tracker.is_checkered():
                    time.sleep(0.125)  # refresh more often to track finish times
                else:
                    time.sleep(self.refresh_rate)

            except Exception as e:
                logger.error(f"Telemetry error: {e}", exc_info=True)
                print(f"Telemetry error: {e}")
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

    def _handle_telemetry_update(self, race_data: Optional[List[Dict]]) -> None:
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

        # Sync session info from telemetry processor
        self.current_session_id = self.telemetry_processor.current_session_id
        self.current_session_type = self.telemetry_processor.current_session_type

        # Clear old data on session change (only if we have a valid session)
        if session_changed and self.current_session_id is not None:
            self.race_data = []
            self._last_emitted_data = []  # Reset change tracking on session change

        # Update race data and player info
        self.race_data = race_data
        self.player_car_idx = self.telemetry_processor.player_car_idx

        # Immediately emit UI update with new data (event-driven)
        # Only update if data has actually changed to avoid redundant widget rebuilds
        if race_data:
            current_data = self._filter_by_division(race_data)
            if self._has_data_changed(current_data):
                self._last_emitted_data = current_data.copy()
                self.signals.update_data.emit(current_data)

    def _has_data_changed(self, new_data: List[Dict]) -> bool:
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
            # Check fields that affect display
            if (new_driver.get('car_idx') != old_driver.get('car_idx') or
                new_driver.get('position') != old_driver.get('position') or
                new_driver.get('division_position') != old_driver.get('division_position') or
                new_driver.get('car_number') != old_driver.get('car_number') or
                new_driver.get('driver_name') != old_driver.get('driver_name') or
                new_driver.get('gap') != old_driver.get('gap') or
                new_driver.get('is_player') != old_driver.get('is_player')):
                return True

            # Check if driver division changed (affects color)
            new_info = new_driver.get('driver_info', {})
            old_info = old_driver.get('driver_info', {})
            if (new_info.get('UserID') != old_info.get('UserID') or
                new_info.get('UserName') != old_info.get('UserName')):
                return True

        return False

    def _filter_by_division(self, race_data: List[Dict]) -> List[Dict]:
        """Filter race data based on division filter settings.

        Handles three filtering modes:
        1. Show only player's division (if show_only_my_division is True)
        2. Show specific division (if current_division_filter is set)
        3. Show all divisions (default)

        Args:
            race_data: Full list of driver data to filter

        Returns:
            Filtered list of driver data
        """
        if not race_data:
            return race_data

        # Filter to player's division only
        if self.show_only_my_division and self.player_car_idx is not None:
            player_color = None
            for driver_data in race_data:
                if driver_data['car_idx'] == self.player_car_idx:
                    player_color = self.get_driver_color(driver_data['driver_info'])
                    break

            if player_color:
                return [d for d in race_data if self.get_driver_color(d['driver_info']) == player_color]
            return race_data

        # Filter to specific division (spectator mode)
        if self.current_division_filter is not None:
            division_color = self.available_colors.get(self.current_division_filter)
            if division_color:
                return [d for d in race_data if self.get_driver_color(d['driver_info']) == division_color]
            return race_data

        # No filter - show all
        return race_data

    def update_gui(self):
        """Update GUI status (called by timer).

        Note: This only updates the status label, not the driver list.
        Driver list updates are now event-driven via telemetry thread
        and division filter button clicks.
        """
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
            else:
                self.signals.update_status.emit("Connecting to iRacing...", 'orange')

        except Exception as e:
            logger.error(f"GUI update error: {e}", exc_info=True)
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
            row = self.row_renderer.create_row(driver_data)
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row)
        
        # Auto-center on player
        if self.player_car_idx is not None and self.auto_center.should_auto_center():
            self.center_on_player(data)
        
        self.displayed_data = data.copy()
    
    def show_context_menu(self, driver_data):
        """Display right-click menu to assign driver to a division."""
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

        driver_info = driver_data['driver_info'] if 'driver_info' in driver_data else {}

        for division_name in self.available_colors.keys():
            action = menu.addAction(division_name)
            action.triggered.connect(
                lambda checked, d=division_name, info=driver_info:
                self.set_driver_division(info, d)
            )

        # Use cursor position directly to avoid coordinate mapping issues
        menu.exec(QCursor.pos())
        
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

    # Mouse events for dragging the frameless window
    def mousePressEvent(self, event):
        """Enable dragging the frameless window by its title bar.
        Why this exists: With Qt.FramelessWindowHint, we lose the default OS
        window dragging. This reimplements it for the title bar area.
        """
        if event.button() == Qt.LeftButton:
            # Check if in title bar for dragging
            if event.position().y() < 30:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        """Update window position during drag operation."""
        if event.buttons() == Qt.LeftButton:
            if not self.drag_position.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

    def mouseReleaseEvent(self, event):
        """End drag operation and save new window position to config."""
        self.drag_position = QPoint()
        # Save settings when user finishes moving/resizing
        if event.button() == Qt.LeftButton:
            self.save_settings()


def main():
    # Setup logging first
    log_file_path = setup_logging()
    logger.info("="*60)
    logger.info(f"BB's League Overlay v{VERSION} - Starting")
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
        print(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
