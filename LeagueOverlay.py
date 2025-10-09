import sys
import threading
import time
import json
import os
import urllib.request
from datetime import datetime
from packaging import version

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QGridLayout, QMenu,
    QDialog, QSlider, QCheckBox, QFileDialog, QMessageBox, QColorDialog,
    QSizeGrip, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QSize
from PySide6.QtGui import QColor, QPalette, QFont, QCursor, QPainter, QMouseEvent

import irsdk

VERSION = "0.9.6"  # Easy to find and update

class DataUpdateSignal(QObject):
    """Signal emitter for thread-safe GUI updates"""
    update_data = Signal(list)
    update_status = Signal(str, str)  # text, color
    refresh_colors = Signal()

class CustomSizeGrip(QSizeGrip):
    """Custom size grip with conditional visibility and icon"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = None
        # Make the widget background transparent
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_parent_window(self, window):
        """Set reference to parent window for focus checking"""
        self.parent_window = window

    def paintEvent(self, event):
        """Custom paint to show diagonal arrows when focused with transparent background"""
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
        """Custom paint to show diagonal arrows when focused"""
        super().paintEvent(event)

        if self.parent_window and self.parent_window.hasFocus():
            painter = QPainter(self)
            painter.setPen(QColor("#888888"))

            # Draw diagonal double arrow pattern
            # Bottom-right pointing arrows
            size = self.width()
            spacing = 4

            # Draw three diagonal lines to create arrow effect
            for i in range(3):
                offset = i * spacing
                painter.drawLine(size - 3 - offset, offset + 3, offset + 3, size - 3 - offset)

class LeagueOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.ir = irsdk.IRSDK()
        self.is_connected = False
        self.running = True
        
        # Signals for thread-safe updates
        self.signals = DataUpdateSignal()
        self.signals.update_data.connect(self.display_race_data)
        self.signals.update_status.connect(self.update_status_label)
        self.signals.refresh_colors.connect(self.refresh_driver_colors)
        
        # Auto-centering variables
        self.player_car_idx = None
        self.last_manual_scroll = 0
        self.manual_scroll_timeout = 5
        self.auto_center_enabled = True
        self.refresh_rate = 2.0
        
        # Settings
        self.show_only_my_division = False
        self.opacity = 1.0
        self.width = 350
        self.height = 320
        self.x = 100
        self.y = 100
        self.hide_headers = False
        self.center_drivers = False
        self.bold_drivers = False
        self.top_elements_visible = True
        self.current_division_filter = None
        self.division_cycle_order = ["Pro", "ProAm", "Am", "Rookie", "All"]
        
        # Data tracking
        self.driver_snapshots = {}
        self.session_info = ""
        self.update_check_done = False
        self.latest_version = None
        self.leader_finished = False
        self.finished_drivers = set()
        self.leader_car_idx = None
        self.leader_last_lap = None
        self.player_car_class_id = None
        self.final_gaps = {}  # Store final gaps for finished drivers
        
        # Color configuration
        self.color_config_file = "league_divisions.json"
        self.settings_file = "LeagueOverlay.config"
        self.driver_colors = self.load_color_config()
        self.load_settings()
        
        # Division colors
        self.default_colors = {
            "Pro": "#FF8C00",
            "ProAm": "#9370DB",
            "Am": "#45B3E0",
            "Rookie": "#FF2000",
            "Default": "#FFFFFF"
        }
        self.available_colors = self.load_division_colors()
        
        # Data
        self.race_data = []
        self.displayed_data = []
        self.data_widgets = {}
        
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
        """Convert color to RGBA with current opacity"""
        # Parse hex color
        if base_color.startswith('#'):
            r = int(base_color[1:3], 16)
            g = int(base_color[3:5], 16)
            b = int(base_color[5:7], 16)
            return f"rgba({r}, {g}, {b}, {self.opacity})"
        return base_color

    def update_all_backgrounds(self):
        """Update all background colors with current opacity"""
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
            self.size_grip.setStyleSheet(f"""
                QSizeGrip {{
                    background-color: {self.get_bg_color('#000000')};
                    border: none;
                    image: none;
                }}
            """)
        # Recreate headers with new opacity
        if hasattr(self, 'header_layout'):
            self.create_headers()
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
        self.setMinimumSize(300, 200)
        
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
        self.scroll_layout.setSpacing(2)
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
                font-size: 9pt;
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
        self.title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 10pt;
            }
        """)
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        
        # Division filter button
        self.division_btn = QPushButton("All Divisions")
        self.division_btn.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                padding: 4px 6px;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #666666;
            }
        """)
        self.division_btn.clicked.connect(self.toggle_division_filter)
        title_layout.addWidget(self.division_btn)

        # Settings button
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #555555;
                color: white;
                border: none;
                padding: 4px 6px;
                font-size: 8.5pt;
            }
            QPushButton:hover {
                background-color: #666666;
            }
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
                    font-size: 9pt;
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
        """Toggle division filter"""
        player_on_track = self.player_car_idx is not None and any(
            d['car_idx'] == self.player_car_idx for d in self.race_data
        )
        
        if player_on_track:
            self.show_only_my_division = not self.show_only_my_division
            self.current_division_filter = None
            button_text = "My Division" if self.show_only_my_division else "All Divisions"
            button_color = "#0FC436" if self.show_only_my_division else '#555555'
        else:
            self.show_only_my_division = False
            
            divisions_with_drivers = set()
            for driver_data in self.race_data:
                driver_color = self.get_driver_color(driver_data['driver_info'])
                for div_name, div_color in self.available_colors.items():
                    if div_color == driver_color and div_name not in ["Default", "All"]:
                        divisions_with_drivers.add(div_name)
            
            available_options = [div for div in self.division_cycle_order 
                               if div == "All" or div in divisions_with_drivers]
            
            if self.current_division_filter is None:
                next_filter = available_options[0] if available_options else "All"
            else:
                try:
                    current_name = "All" if self.current_division_filter == "All" else self.current_division_filter
                    current_idx = available_options.index(current_name)
                    next_idx = (current_idx + 1) % len(available_options)
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
                font-size: 8.5pt;
            }}
            QPushButton:hover {{
                background-color: {button_color};
            }}
        """)
        self.scroll_area.verticalScrollBar().setValue(0)
        
    def on_manual_scroll(self):
        """Track manual scrolling"""
        self.last_manual_scroll = time.time()

    def resizeEvent(self, event):
        """Handle window resize to reposition size grip"""
        super().resizeEvent(event)
        # Position size grip at bottom right corner
        if hasattr(self, 'size_grip'):
            rect = self.rect()
            self.size_grip.move(
                rect.width() - self.size_grip.width(),
                rect.height() - self.size_grip.height()
            )
        
    def load_color_config(self):
        """Load division color configuration"""
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
        """Load settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    data = json.load(f)
                    league_config = data.get('league_config')
                    if league_config and os.path.exists(league_config):
                        self.color_config_file = league_config
                        self.driver_colors = self.load_color_config()
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
        """Save settings to file"""
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
                'bold_drivers': self.bold_drivers
            }
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            print(f"Failed to save settings: {e}")
            
    def save_color_config(self):
        """Save color configuration"""
        try:
            with open(self.color_config_file, 'w') as f:
                json.dump(self.driver_colors, f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save color config: {e}")
            
    def get_driver_division(self, driver_info):
        """Get division for driver"""
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')
        
        if 'drivers' not in self.driver_colors:
            return None
        
        if user_id:
            for driver in self.driver_colors['drivers']:
                driver_id = driver.get('id', '')
                if driver_id and driver_id == user_id:
                    return driver.get('division')
        
        if user_name:
            for driver in self.driver_colors['drivers']:
                if driver.get('name') == user_name:
                    return driver.get('division')
        
        return None
        
    def set_driver_division(self, driver_info, division_name):
        """Set driver division"""
        user_id = driver_info.get('UserID', '')
        user_name = driver_info.get('UserName', '')
        
        if 'drivers' not in self.driver_colors:
            self.driver_colors['drivers'] = []
        
        existing_entry = None
        for i, driver in enumerate(self.driver_colors['drivers']):
            driver_id = driver.get('id', '')
            driver_name = driver.get('name', '')
            
            if (user_id and driver_id == user_id) or (user_name and driver_name == user_name):
                existing_entry = i
                break
        
        if division_name == "Default":
            if existing_entry is not None:
                self.driver_colors['drivers'].pop(existing_entry)
        else:
            entry = {'division': division_name}
            if user_name:
                entry['name'] = user_name
            if user_id:
                entry['id'] = user_id
            
            if existing_entry is not None:
                old_entry = self.driver_colors['drivers'][existing_entry]
                if not user_id and 'id' in old_entry:
                    entry['id'] = old_entry['id']
                if not user_name and 'name' in old_entry:
                    entry['name'] = old_entry['name']
                self.driver_colors['drivers'][existing_entry] = entry
            else:
                self.driver_colors['drivers'].append(entry)
        
        self.save_color_config()
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
        """Main telemetry loop"""
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
        """Calculate real-time positions"""
        car_idx_lap = live_data['CarIdxLap']
        car_idx_lap_dist_pct = live_data['CarIdxLapDistPct']
        car_idx_class_position = live_data['CarIdxClassPosition']
        
        if not car_idx_lap or not car_idx_lap_dist_pct or not car_idx_class_position:
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
            
            current_lap = car_idx_lap[car_idx]
            lap_pct = car_idx_lap_dist_pct[car_idx]
            
            if current_lap < 0:
                continue
            
            if lap_pct < 0 or lap_pct > 1:
                lap_pct = 0
            
            total_track_position = current_lap + lap_pct
            
            active_drivers.append({
                'car_idx': car_idx,
                'driver_info': driver_info,
                'total_track_position': total_track_position,
                'current_lap': current_lap,
                'lap_pct': lap_pct,
                'official_position': car_idx_class_position[car_idx]
            })
        
        active_drivers.sort(key=lambda x: x['total_track_position'], reverse=True)
        
        for i, driver in enumerate(active_drivers):
            driver['real_time_position'] = i + 1
        
        return active_drivers
        
    def get_official_positions(self, drivers, live_data):
        """Get official positions"""
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
        """Update finish status"""
        if self.ir['SessionState'] < 5:
            return
        
        car_idx_lap = live_data['CarIdxLap']
        
        if self.leader_car_idx is None:
            try:
                for driver in current_session['ResultsPositions']:
                    if self.player_car_class_id is not None:
                        driver_class_id = None
                        try:
                            drivers = self.ir['DriverInfo']['Drivers']
                            for d in drivers:
                                if d.get('CarIdx') == driver.get('CarIdx'):
                                    driver_class_id = d.get('CarClassID')
                                    break
                        except (KeyError, TypeError):
                            continue
                        
                        if driver_class_id != self.player_car_class_id:
                            continue
                    
                    if driver.get('ClassPosition') == 1:
                        self.leader_car_idx = driver.get('CarIdx')
                        self.leader_last_lap = car_idx_lap[self.leader_car_idx] if self.leader_car_idx < len(car_idx_lap) else 0
                        break
            except (KeyError, TypeError, IndexError):
                pass
        
        if self.leader_car_idx is not None and not self.leader_finished:
            if self.leader_car_idx < len(car_idx_lap):
                current_leader_lap = car_idx_lap[self.leader_car_idx]
                if current_leader_lap > self.leader_last_lap:
                    self.leader_finished = True
        
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
                
                if current_lap > prev_lap:
                    self.finished_drivers.add(car_idx)
                    
    def get_position_from_results(self, current_session, car_idx):
        """Get position from results"""
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'ClassPosition' in driver:
                        return driver['ClassPosition'] + 1
        except (KeyError, TypeError, IndexError):
            pass
        return -1
        
    def get_fastest_lap_time(self, current_session):
        """Get fastest lap time"""
        fastest_time = float('inf')
        for driver in current_session['ResultsPositions']:
            best_lap = driver['FastestTime']
            if 0 < best_lap < fastest_time:
                fastest_time = best_lap
        return fastest_time if fastest_time != float('inf') else 90
        
    def get_best_lap_from_session_info(self, current_session, car_idx):
        """Get best lap from session info"""
        try:
            if 'ResultsPositions' in current_session:
                for driver in current_session['ResultsPositions']:
                    if driver.get('CarIdx') == car_idx and 'FastestTime' in driver:
                        return driver['FastestTime']
        except (KeyError, TypeError, IndexError):
            pass
        return 90
        
    def process_telemetry(self):
        """Process telemetry data"""
        try:
            try:
                drivers = self.ir['DriverInfo']['Drivers']
                if not drivers:
                    return
            except (KeyError, TypeError) as e:
                print(f"Error getting driver info: {e}")
                return
            
            try:
                session_info = self.ir['SessionInfo']
                current_session = session_info['Sessions'][self.ir['SessionNum']]
                session_type = current_session['SessionType']
                is_race = session_type.lower() == 'race'
            except (KeyError, TypeError, IndexError):
                is_race = False
                
            if self.session_info != f"{self.ir['SessionNum']}|{session_type}":
                self.driver_snapshots = {}
                self.leader_finished = False
                self.finished_drivers = set()
                self.leader_car_idx = None
                self.leader_last_lap = None
                self.session_info = f"{self.ir['SessionNum']}|{session_type}"
                self.player_car_idx = None
                self.player_car_class_id = None
                self.final_gaps = {}
            
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
            
            if is_race:
                active_drivers = self.calculate_real_time_positions(drivers, live_data)
                # Only use official positions after leader has actually finished, not just when checkered is shown
                position_key = 'real_time_position' if not self.leader_finished else 'official_position'
                
                if active_drivers:
                    for driver_data in active_drivers:
                        self.driver_snapshots[driver_data['car_idx']] = driver_data.copy()
                        self.driver_snapshots[driver_data['car_idx']]['disconnected'] = False
                    
                    active_car_indices = {d['car_idx'] for d in active_drivers}
                    for car_idx, snapshot in self.driver_snapshots.items():
                        if car_idx not in active_car_indices:
                            if self.ir['SessionState'] < 5:
                                snapshot['official_position'] = -1
                            disconnected_driver = snapshot.copy()
                            disconnected_driver['disconnected'] = True
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
                    'position': driver[position_key],
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
                
                if current_color_position == 1:
                    gap = "Leader"
                elif car_idx in self.finished_drivers:
                    gap = self.final_gaps.get(car_idx, "")
                elif is_race:
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
                    
                    current_pos_index = None
                    for i, temp_driver in enumerate(same_color_drivers):
                        if temp_driver['car_idx'] == car_idx:
                            current_pos_index = i
                            break
                    
                    if current_pos_index is not None and current_pos_index > 0:
                        car_ahead_idx = same_color_drivers[current_pos_index - 1]['car_idx']

                        if car_ahead_idx in self.finished_drivers:
                            gap = self.final_gaps.get(car_idx, "")
                        else:
                            car_idx_est_time = live_data['CarIdxEstTime']
                            current_est_time = car_idx_est_time[car_idx]
                            ahead_est_time = car_idx_est_time[car_ahead_idx]

                            time_gap = 0.0
                            if current_est_time > 0 and ahead_est_time > 0 and same_color_drivers[current_pos_index - 1]['current_lap'] == driver['current_lap']:
                                time_gap = ahead_est_time - current_est_time
                            else:
                                time_gap = (same_color_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']) * self.get_fastest_lap_time(current_session)

                            lap_difference = same_color_drivers[current_pos_index - 1]['total_track_position'] - driver['total_track_position']

                            if lap_difference > 1:
                                gap = f"{int(lap_difference)}L"
                            elif self.ir['SessionState'] < 5:
                                if time_gap < 0:
                                    time_gap *= -1
                                if time_gap < 60:
                                    gap = f"{time_gap:.1f}"
                                else:
                                    minutes = int(time_gap // 60)
                                    seconds = time_gap % 60
                                    gap = f"{minutes}:{seconds:04.1f}"
                            else:
                                if time_gap < 0:
                                    time_gap *= -1
                                if time_gap < 60:
                                    gap = f"{time_gap:.1f}"
                                else:
                                    minutes = int(time_gap // 60)
                                    seconds = time_gap % 60
                                    gap = f"{minutes}:{seconds:04.1f}"

                            # Store the gap continuously for all non-leaders
                            if gap and gap != "":
                                self.final_gaps[car_idx] = gap
                    else:
                        gap = ""
                else:
                    same_color_drivers = [d for d in all_drivers_with_colors if d['color'] == current_driver_color]
                    same_color_drivers.sort(key=lambda x: x['position'])
                    
                    if len(same_color_drivers) >= current_color_position - 1:
                        car_ahead_idx = same_color_drivers[current_color_position - 2]['car_idx']
                        current_best = self.get_best_lap_from_session_info(current_session, car_idx)
                        ahead_best = self.get_best_lap_from_session_info(current_session, car_ahead_idx)
                        if current_best > 0 and ahead_best > 0:
                            time_gap = current_best - ahead_best
                            gap = f"{time_gap:.3f}"
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
                    'gap': gap if not driver.get('disconnected', False) or gap == "Leader" or gap == "" else "(DC)",
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
        """Center view on player"""
        if not current_data or self.player_car_idx is None:
            return
        
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
            # Everything fits, no need to scroll
            return
        
        # Calculate height per item
        item_height = total_height / total_items
        
        # Calculate position to center player
        # We want player to be at (viewport_height / 2)
        player_top_position = player_index * item_height
        target_scroll = player_top_position - (viewport_height / 2) + (item_height / 2)
        
        # Clamp to valid scroll range
        target_scroll = max(0, min(target_scroll, scrollbar.maximum()))
        
        scrollbar.setValue(int(target_scroll))
        
    def create_driver_row(self, driver_data):
        """Create a driver row widget"""
        row_widget = QWidget()
        base_bg = "#1a1a1a" if driver_data.get('is_player', False) else "#000000"
        bg_color = self.get_bg_color(base_bg)
        row_widget.setStyleSheet(f"background-color: {bg_color};")
        
        layout = QGridLayout(row_widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        layout.setColumnStretch(0, 11)
        layout.setColumnStretch(1, 11)
        layout.setColumnStretch(2, 13)
        layout.setColumnStretch(3, 46)
        layout.setColumnStretch(4, 19)
        
        color = self.get_driver_color(driver_data.get('driver_info', {}))
        font_weight = "bold" if driver_data.get('is_player', False) or self.bold_drivers else "normal"
        
        # Position
        pos_label = QLabel(str(driver_data.get('position', '')))
        pos_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg_color};
                font-size: 9pt;
                font-weight: {font_weight};
            }}
        """)
        pos_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(pos_label, 0, 0)
        
        # Division Position
        div_pos_label = QLabel(str(driver_data.get('division_position', '')))
        div_pos_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg_color};
                font-size: 9pt;
                font-weight: {font_weight};
            }}
        """)
        div_pos_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(div_pos_label, 0, 1)
        
        # Car Number
        car_label = QLabel(str(driver_data.get('car_number', '')))
        car_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg_color};
                font-size: 9pt;
                font-weight: {font_weight};
            }}
        """)
        car_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(car_label, 0, 2)
        
        # Driver Name
        name_align = Qt.AlignCenter if self.center_drivers else Qt.AlignLeft
        name_label = QLabel(driver_data.get('driver_name', ''))
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                background-color: {bg_color};
                font-size: 9pt;
                font-weight: {font_weight};
            }}
        """)
        name_label.setAlignment(name_align | Qt.AlignVCenter)
        # Prevent name from expanding beyond allocated width
        name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_label.setWordWrap(False)
        layout.addWidget(name_label, 0, 3)
        
        # Gap
        gap_label = QLabel(driver_data.get('gap', ''))
        gap_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                background-color: {bg_color};
                font-size: 9pt;
                font-weight: {font_weight};
            }}
        """)
        gap_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(gap_label, 0, 4)
        
        # Context menu
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda pos, data=driver_data, w=row_widget: self.show_context_menu(pos, data, w)
        )
        
        return row_widget
        
    def show_context_menu(self, pos, driver_data, widget):
        """Show context menu for division assignment"""
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

        # Map position from widget to global coordinates
        global_pos = widget.mapToGlobal(pos)
        menu.exec(global_pos)
        
    def update_status_label(self, text, color):
        """Update status label (thread-safe slot)"""
        self.status_label.setText(text)
        self.update_status_style(color)
        
    # Mouse events for dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Check if in title bar for dragging
            if event.position().y() < 30:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            if not self.drag_position.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_position)
                event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = QPoint()
        # Save settings when user finishes moving/resizing
        if event.button() == Qt.LeftButton:
            self.save_settings()


class SettingsDialog(QDialog):
    """Settings dialog"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_overlay = parent
        self.setWindowTitle("BB's League Overlay - Settings")
        self.setModal(True)
        self.setFixedSize(300, 670)
        
        self.original_opacity = parent.opacity
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup settings UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Config section
        config_group = QFrame()
        config_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 5px; background-color: #333333; }")
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
        window_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 5px; background-color: #333333; }")
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(8)
        
        window_title = QLabel("Window Settings")
        window_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        window_layout.addWidget(window_title)
        
        # Opacity with value display - 0.05 increments (20 steps per 1.0 = 2000 steps for 0-100)
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
        
        # Refresh rate with value display - 0.25 increments (4 steps per 1.0 = 40 steps for 0-10)
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
        colors_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 5px; background-color: #333333; }")
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
        """Preview opacity change"""
        opacity = value / 20.0
        self.parent_overlay.opacity = opacity
        self.parent_overlay.update_all_backgrounds()
        
    def choose_color(self, division):
        """Choose color for division"""
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
            self.opacity_slider.setValue(20)  # 1.0
            self.refresh_slider.setValue(8)  # 2.0 seconds (8 * 0.25)
            self.hide_headers_cb.setChecked(False)
            self.center_drivers_cb.setChecked(False)
            self.bold_drivers_cb.setChecked(False)
            
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
            
            self.parent_overlay.opacity = 1.0
            self.parent_overlay.update_all_backgrounds()

    def apply_settings(self):
        """Apply all settings"""
        try:
            self.parent_overlay.opacity = self.opacity_slider.value() / 20.0
            self.parent_overlay.refresh_rate = self.refresh_slider.value() / 4.0  # Changed from /10 to /4
            self.parent_overlay.hide_headers = self.hide_headers_cb.isChecked()
            self.parent_overlay.center_drivers = self.center_drivers_cb.isChecked()
            self.parent_overlay.bold_drivers = self.bold_drivers_cb.isChecked()

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