"""Settings dialog for configuring overlay appearance and behavior."""

import os
import json
import shutil
import re
from typing import TYPE_CHECKING
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QCheckBox, QFileDialog, QMessageBox, QColorDialog, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from config.constants import VERSION, UI_DIMENSIONS, TelemetryConfig
from config.logging_config import set_log_level, get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class SettingsDialog(QDialog):
    """Modal settings dialog for configuring overlay appearance and behavior. Shows update link if new version available."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_overlay = parent
        self.setWindowTitle("BB's League Overlay - Settings")
        self.setModal(True)
        self.setFixedSize(UI_DIMENSIONS.SETTINGS_DIALOG_WIDTH, UI_DIMENSIONS.SETTINGS_DIALOG_HEIGHT)

        self.setup_ui()
        
    def setup_ui(self):
        """Setup settings UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # Create two-column layout
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)

        # LEFT COLUMN
        left_column = QVBoxLayout()
        left_column.setSpacing(5)

        # Config section
        config_group = QFrame()
        config_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        config_group.setMinimumWidth(300)
        config_group.setMaximumWidth(300)
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(8)

        config_title = QLabel("Driver Color Configuration")
        config_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        config_layout.addWidget(config_title)

        # League selector dropdown
        league_row = QHBoxLayout()
        league_label = QLabel("Active League:")
        league_label.setStyleSheet("font-size: 9pt; color: white; border: none;")
        league_row.addWidget(league_label)

        self.league_combo = QComboBox()
        self.league_combo.setStyleSheet("""
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
        self.populate_league_dropdown()
        league_row.addWidget(self.league_combo, 1)
        config_layout.addLayout(league_row)

        # Buttons row for refresh and save local copy
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(5)

        # Refresh button (only enabled for official leagues)
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_league)
        buttons_row.addWidget(self.refresh_btn)

        # Save local copy button (only enabled for official leagues)
        self.save_local_btn = QPushButton("💾 Save Local Copy...")
        self.save_local_btn.setStyleSheet("""
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
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #666666;
            }
        """)
        self.save_local_btn.clicked.connect(self.save_local_copy)
        buttons_row.addWidget(self.save_local_btn)

        config_layout.addLayout(buttons_row)

        # Now connect the league dropdown signal handler and update button states
        self.league_combo.currentIndexChanged.connect(self.on_league_selected)
        self._update_refresh_button()
        left_column.addWidget(config_group)

        # Division colors (moved to left column)
        colors_group = QFrame()
        colors_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        colors_group.setMinimumWidth(300)
        colors_group.setMaximumWidth(300)
        colors_layout = QVBoxLayout(colors_group)
        colors_layout.setSpacing(8)

        colors_title = QLabel("Division Colors")
        colors_title.setStyleSheet("font-weight: bold; font-size: 11pt; border: none; color: white;")
        colors_layout.addWidget(colors_title)

        self.color_buttons = {}
        self.color_value_labels = {}

        for division in ["Pro", "ProAm", "Am", "Rookie"]:
            if division not in self.parent_overlay.division_manager.division_colors:
                continue

            color = self.parent_overlay.division_manager.division_colors[division]

            color_row = QHBoxLayout()
            color_row.setSpacing(5)

            div_label = QLabel(f"{division}:")
            div_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 95px;")
            color_row.addWidget(div_label)

            color_btn = QPushButton()
            color_btn.setFixedSize(72, 18)
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

        # Add performance indicator colors section
        colors_layout.addSpacing(8)

        perf_colors_title = QLabel("Performance Indicator Colors")
        perf_colors_title.setStyleSheet("font-weight: bold; font-size: 10pt; border: none; color: white;")
        colors_layout.addWidget(perf_colors_title)

        # Faster color (green by default)
        faster_color_row = QHBoxLayout()
        faster_color_row.setSpacing(5)

        faster_label = QLabel("Faster/Gained:")
        faster_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 95px;")
        faster_color_row.addWidget(faster_label)

        self.faster_color_btn = QPushButton()
        self.faster_color_btn.setFixedSize(72, 18)
        self.faster_color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.parent_overlay.settings.faster_color};
                border: 2px solid #555555;
            }}
            QPushButton:hover {{
                border: 2px solid #777777;
            }}
        """)
        self.faster_color_btn.clicked.connect(lambda: self.choose_performance_color('faster'))
        faster_color_row.addWidget(self.faster_color_btn)

        self.faster_color_value_label = QLabel(self.parent_overlay.settings.faster_color)
        self.faster_color_value_label.setStyleSheet("""
            border: none;
            color: white;
            font-size: 9pt;
            background-color: #404040;
            padding: 2px 4px;
            min-width: 60px;
        """)
        faster_color_row.addWidget(self.faster_color_value_label)

        faster_color_row.addStretch()
        colors_layout.addLayout(faster_color_row)

        # Slower color (red by default)
        slower_color_row = QHBoxLayout()
        slower_color_row.setSpacing(5)

        slower_label = QLabel("Slower/Lost:")
        slower_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 95px;")
        slower_color_row.addWidget(slower_label)

        self.slower_color_btn = QPushButton()
        self.slower_color_btn.setFixedSize(72, 18)
        self.slower_color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.parent_overlay.settings.slower_color};
                border: 2px solid #555555;
            }}
            QPushButton:hover {{
                border: 2px solid #777777;
            }}
        """)
        self.slower_color_btn.clicked.connect(lambda: self.choose_performance_color('slower'))
        slower_color_row.addWidget(self.slower_color_btn)

        self.slower_color_value_label = QLabel(self.parent_overlay.settings.slower_color)
        self.slower_color_value_label.setStyleSheet("""
            border: none;
            color: white;
            font-size: 9pt;
            background-color: #404040;
            padding: 2px 4px;
            min-width: 60px;
        """)
        slower_color_row.addWidget(self.slower_color_value_label)

        slower_color_row.addStretch()
        colors_layout.addLayout(slower_color_row)

        left_column.addWidget(colors_group)
        left_column.addStretch()

        # RIGHT COLUMN
        right_column = QVBoxLayout()
        right_column.setSpacing(5)

        # Window settings (moved to right column)
        window_group = QFrame()
        window_group.setStyleSheet("QFrame { border: 1px solid #555555; padding: 4px; background-color: #333333; }")
        window_group.setMinimumWidth(300)
        window_group.setMaximumWidth(300)
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
        self.opacity_slider.setValue(int(self.parent_overlay.settings.opacity * 20))
        opacity_row.addWidget(self.opacity_slider)

        self.opacity_value_label = QLabel(f"{self.parent_overlay.settings.opacity:.2f}")
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
        self.refresh_slider.setMinimum(1) 
        self.refresh_slider.setMaximum(TelemetryConfig.MAX_REFRESH_RATE/TelemetryConfig.MIN_REFRESH_RATE)
        self.refresh_slider.setSingleStep(1)  # 0.25 increment
        self.refresh_slider.setPageStep(1)
        self.refresh_slider.setValue(int(self.parent_overlay.settings.refresh_rate * 4))
        refresh_row.addWidget(self.refresh_slider)

        self.refresh_value_label = QLabel(f"{self.parent_overlay.settings.refresh_rate:.2f}")
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
        self.font_size_combo.setCurrentText(self.parent_overlay.settings.font_size)
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
        self.color_style_combo.addItems(["Default", "Dark", "Alternate", "Outline"])
        self.color_style_combo.setCurrentText(self.parent_overlay.settings.row_color_style)
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

        # Log level selector
        log_level_row = QHBoxLayout()
        log_level_label = QLabel("Log Level:")
        log_level_label.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 100px;")
        log_level_row.addWidget(log_level_label)

        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.log_level_combo.setCurrentText(self.parent_overlay.settings.log_level)
        self.log_level_combo.setStyleSheet("""
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
        log_level_row.addWidget(self.log_level_combo)
        window_layout.addLayout(log_level_row)

        # Checkboxes in 2x2 grid (left and right columns)
        checkbox_row1 = QHBoxLayout()

        self.hide_headers_cb = QCheckBox("Auto-hide headers")
        self.hide_headers_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.hide_headers_cb.setChecked(self.parent_overlay.settings.hide_headers)
        checkbox_row1.addWidget(self.hide_headers_cb)

        self.center_drivers_cb = QCheckBox("Center driver names")
        self.center_drivers_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.center_drivers_cb.setChecked(self.parent_overlay.settings.center_drivers)
        checkbox_row1.addWidget(self.center_drivers_cb)

        window_layout.addLayout(checkbox_row1)

        checkbox_row2 = QHBoxLayout()

        self.bold_drivers_cb = QCheckBox("Bold all driver rows")
        self.bold_drivers_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.bold_drivers_cb.setChecked(self.parent_overlay.settings.bold_drivers)
        checkbox_row2.addWidget(self.bold_drivers_cb)

        self.show_division_gap_cb = QCheckBox("Show division gap")
        self.show_division_gap_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.show_division_gap_cb.setChecked(self.parent_overlay.settings.show_division_gap)
        checkbox_row2.addWidget(self.show_division_gap_cb)

        window_layout.addLayout(checkbox_row2)

        checkbox_row3 = QHBoxLayout()

        self.show_last_lap_cb = QCheckBox("Show last lap")
        self.show_last_lap_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.show_last_lap_cb.setChecked(self.parent_overlay.settings.show_last_lap)
        checkbox_row3.addWidget(self.show_last_lap_cb)

        self.show_delta_cb = QCheckBox("Show delta")
        self.show_delta_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.show_delta_cb.setChecked(self.parent_overlay.settings.show_delta)
        checkbox_row3.addWidget(self.show_delta_cb)

        window_layout.addLayout(checkbox_row3)

        checkbox_row4 = QHBoxLayout()

        self.show_best_lap_cb = QCheckBox("Show best lap")
        self.show_best_lap_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.show_best_lap_cb.setChecked(self.parent_overlay.settings.show_best_lap)
        checkbox_row4.addWidget(self.show_best_lap_cb)

        self.show_positions_gained_cb = QCheckBox("Show positions gained")
        self.show_positions_gained_cb.setStyleSheet("border: none; color: white; font-size: 9pt; min-width: 150px;")
        self.show_positions_gained_cb.setChecked(self.parent_overlay.settings.show_positions_gained)
        checkbox_row4.addWidget(self.show_positions_gained_cb)

        window_layout.addLayout(checkbox_row4)

        right_column.addWidget(window_group)

        # Add columns to main layout with equal stretch factors (1:1 ratio)
        columns_layout.addLayout(left_column, 1)
        columns_layout.addLayout(right_column, 1)
        layout.addLayout(columns_layout)

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
        
        # Status label (shows driver count when loading files, or version by default)
        self.status_label = QLabel(f"Version {VERSION}")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888888; font-size: 8pt;")
        layout.addWidget(self.status_label)

        # Check for updates and show link if available
        if hasattr(self.parent_overlay, 'latest_version') and self.parent_overlay.latest_version:
            version_text = f"Version {VERSION} | <a href='https://leagueoverlay.com/download.php' style='color: #FF8C00;'>Update to v{self.parent_overlay.latest_version}</a>"
            self.status_label.setText(version_text)
            self.status_label.setOpenExternalLinks(True)
        
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
        
    def choose_color(self, division):
        """Open color picker to customize a division's color."""
        current_color = self.parent_overlay.division_manager.division_colors[division]
        color = QColorDialog.getColor(QColor(current_color), self, f"Choose {division} Color")

        if color.isValid():
            new_color = color.name()
            self.parent_overlay.division_manager.division_colors[division] = new_color
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

    def choose_performance_color(self, color_type):
        """Open color picker to customize performance indicator colors.

        Args:
            color_type: Either 'faster' or 'slower'
        """
        if color_type == 'faster':
            current_color = self.parent_overlay.settings.faster_color
            title = "Choose Faster/Gained Color"
        else:  # slower
            current_color = self.parent_overlay.settings.slower_color
            title = "Choose Slower/Lost Color"

        color = QColorDialog.getColor(QColor(current_color), self, title)

        if color.isValid():
            new_color = color.name()

            if color_type == 'faster':
                self.parent_overlay.settings.faster_color = new_color
                self.faster_color_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {new_color};
                        border: 2px solid #555555;
                    }}
                    QPushButton:hover {{
                        border: 2px solid #777777;
                    }}
                """)
                self.faster_color_value_label.setText(new_color)
            else:  # slower
                self.parent_overlay.settings.slower_color = new_color
                self.slower_color_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {new_color};
                        border: 2px solid #555555;
                    }}
                    QPushButton:hover {{
                        border: 2px solid #777777;
                    }}
                """)
                self.slower_color_value_label.setText(new_color)

    def _update_status_message(self):
        """Update the status label with current driver count."""
        driver_count = len(self.parent_overlay.division_manager.driver_colors.get('drivers', []))

        # Get league name for display
        config_file = self.parent_overlay.color_config_file
        if config_file.startswith("official:"):
            league_name = config_file.replace("official:", "")
            self.status_label.setText(f"Loaded {driver_count} driver{'s' if driver_count != 1 else ''} from {league_name}")
        else:
            filename = os.path.basename(config_file)
            self.status_label.setText(f"Loaded {driver_count} driver{'s' if driver_count != 1 else ''} from {filename}")

        self.status_label.setStyleSheet("color: #4CAF50; font-size: 8pt;")

    def populate_league_dropdown(self):
        """Populate the league selection dropdown."""
        from config.official_leagues import OFFICIAL_LEAGUES

        # Block signals while repopulating to prevent triggering on_league_selected
        self.league_combo.blockSignals(True)

        self.league_combo.clear()

        # Add official leagues
        if OFFICIAL_LEAGUES:
            for league in OFFICIAL_LEAGUES:
                display_text = f"🏁 {league.name}"
                self.league_combo.addItem(display_text, f"official:{league.name}")

        # Add separator if we have recent files
        if self.parent_overlay.settings.recent_local_configs:
            self.league_combo.insertSeparator(self.league_combo.count())

        # Add recent local files
        for file_path in self.parent_overlay.settings.recent_local_configs:
            if os.path.exists(file_path):
                display_name = os.path.basename(file_path)
                self.league_combo.addItem(f"💻 {display_name}", file_path)

        # Add separator and actions
        self.league_combo.insertSeparator(self.league_combo.count())
        self.league_combo.addItem("📂 Load Other File...", "action:load")
        self.league_combo.addItem("➕ Create New...", "action:create")

        # Select current active league
        self._select_active_league()

        # Re-enable signals
        self.league_combo.blockSignals(False)

    def _select_active_league(self):
        """Select the currently active league in the dropdown."""
        current = self.parent_overlay.color_config_file

        for i in range(self.league_combo.count()):
            data = self.league_combo.itemData(i)
            if data == current:
                self.league_combo.setCurrentIndex(i)
                self._update_refresh_button()
                return

        # Not found - check if it's a valid local file that's not in recent list
        if current and not current.startswith("official:") and not current.startswith("action:"):
            if os.path.exists(current):
                # Add this file to recent configs (at the beginning as most recent)
                if current not in self.parent_overlay.settings.recent_local_configs:
                    self.parent_overlay.settings.recent_local_configs.insert(0, current)
                    self.parent_overlay.settings_manager.save(self.parent_overlay.settings)
                    logger.info(f"Added legacy config file to recent list: {current}")

                # Re-populate dropdown to include this file
                self.populate_league_dropdown()
                return

        # File doesn't exist or is invalid - select first item and log warning
        logger.warning(f"Current config '{current}' not found or invalid, defaulting to first available option")
        if self.league_combo.count() > 0:
            self.league_combo.setCurrentIndex(0)
            self._update_refresh_button()

    def _update_refresh_button(self):
        """Enable/disable refresh and save local copy buttons based on selection."""
        # Guard against buttons not being created yet during initialization
        if not hasattr(self, 'refresh_btn') or not hasattr(self, 'save_local_btn'):
            return

        current_data = self.league_combo.currentData()
        # Check if current_data is a string and starts with "official:"
        is_official = isinstance(current_data, str) and current_data.startswith("official:")
        self.refresh_btn.setEnabled(is_official)
        self.save_local_btn.setEnabled(is_official)

    def on_league_selected(self, index):
        """Handle league selection from dropdown."""
        data = self.league_combo.itemData(index)

        # Skip if data is None (e.g., separator items)
        if data is None:
            return

        if data == "action:load":
            # Reset to previous selection before showing dialog
            self._select_active_league()
            self.load_config()
        elif data == "action:create":
            # Reset to previous selection before showing dialog
            self._select_active_league()
            self.create_new_config()
        elif isinstance(data, str) and data.startswith("official:"):
            self._load_official_league(data)
        elif data:
            # It's a local file path
            self._load_local_file(data)

        self._update_refresh_button()

    def _load_official_league(self, league_source):
        """Load an official league."""
        try:
            self.parent_overlay.color_config_file = league_source
            self.parent_overlay.division_manager.config_file = league_source
            self.parent_overlay.division_manager.load_driver_config()
            self.parent_overlay.signals.refresh_colors.emit()

            # Save to settings (but don't add to recent - it's official)
            self.parent_overlay.settings.league_config = league_source
            self.parent_overlay.save_settings()

            # Update status message
            self._update_status_message()

            logger.info(f"Switched to official league: {league_source}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load official league: {e}")
            self._select_active_league()

    def _load_local_file(self, file_path):
        """Load a local config file."""
        try:
            # Validate file exists and is readable
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            with open(file_path, 'r') as f:
                json.load(f)  # Validate JSON

            # Load the config
            self.parent_overlay.color_config_file = file_path
            self.parent_overlay.division_manager.config_file = file_path
            self.parent_overlay.division_manager.load_driver_config()
            self.parent_overlay.signals.refresh_colors.emit()

            # Add to recent files and save settings
            self.parent_overlay.add_to_recent_files(file_path)
            self.parent_overlay.settings.league_config = file_path
            self.parent_overlay.save_settings()

            # Update status message
            self._update_status_message()

            logger.info(f"Switched to local config: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load config file: {e}")
            self._select_active_league()

    def refresh_league(self):
        """Refresh the current official league."""
        success, message, driver_count = self.parent_overlay.refresh_official_league()

        # Update status message
        if success:
            self.status_label.setText(f"Refreshed {driver_count} driver{'s' if driver_count != 1 else ''}")
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 8pt;")
        else:
            self.status_label.setText(f"Refresh failed")
            self.status_label.setStyleSheet("color: #FF5555; font-size: 8pt;")
            QMessageBox.critical(self, "Refresh Failed", message)

        # Repopulate dropdown in case anything changed
        self.populate_league_dropdown()

    def save_local_copy(self):
        """Save current official league as a local editable copy."""
        from config.official_leagues import get_official_league

        current_data = self.league_combo.currentData()
        if not isinstance(current_data, str) or not current_data.startswith("official:"):
            return

        # Get league name and info
        league_name = current_data.replace("official:", "")
        try:
            league = get_official_league(league_name)
        except ValueError as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        # Generate sanitized default filename
        sanitized_name = re.sub(r'[^\w\s-]', '', league_name).strip().replace(' ', '_')
        default_filename = f"{sanitized_name}.json"

        # Get app directory for default location
        app_dir = os.path.dirname(os.path.abspath(self.parent_overlay.color_config_file))

        # Open save dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Local Copy",
            os.path.join(app_dir, default_filename),
            "JSON files (*.json);;All files (*.*)"
        )

        if not file_path:
            return  # User cancelled

        try:
            # Get cache file path
            cache_file = os.path.join(app_dir, league.cache_file)

            # Check if cache exists
            if not os.path.exists(cache_file):
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Cache file not found: {league.cache_file}\n\n"
                    "Try refreshing the league first."
                )
                return

            # Copy cache file to new location
            shutil.copy2(cache_file, file_path)

            # Load the new local file
            self._load_local_file(file_path)

            # Repopulate dropdown to show in recent files
            self.populate_league_dropdown()

            # Update status message
            filename = os.path.basename(file_path)
            driver_count = len(self.parent_overlay.division_manager.driver_colors.get('drivers', []))
            self.status_label.setText(
                f"Saved and switched to local copy: {filename} ({driver_count} driver{'s' if driver_count != 1 else ''})"
            )
            self.status_label.setStyleSheet("color: #4CAF50; font-size: 8pt;")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save local copy: {e}")

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

                # Load the new config
                self._load_local_file(file_path)

                # Repopulate dropdown to show in recent files
                self.populate_league_dropdown()
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
            self._load_local_file(file_path)
            # Repopulate dropdown to show in recent files
            self.populate_league_dropdown()
                
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
            self.log_level_combo.setCurrentText("INFO")
            
            default_colors = {
                "Pro": "#FF8C00",
                "ProAm": "#9370DB",
                "Am": "#45B3E0",
                "Rookie": "#FF2000"
            }
            
            for division, color in default_colors.items():
                if division in self.color_buttons:
                    self.parent_overlay.division_manager.division_colors[division] = color
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

            # Reset performance indicator colors
            self.parent_overlay.settings.faster_color = "#00FF00"  # Green
            self.faster_color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #00FF00;
                    border: 2px solid #555555;
                }}
                QPushButton:hover {{
                    border: 2px solid #777777;
                }}
            """)
            self.faster_color_value_label.setText("#00FF00")

            self.parent_overlay.settings.slower_color = "#FF0000"  # Red
            self.slower_color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #FF0000;
                    border: 2px solid #555555;
                }}
                QPushButton:hover {{
                    border: 2px solid #777777;
                }}
            """)
            self.slower_color_value_label.setText("#FF0000")

            self.parent_overlay.settings.opacity = 0.5
            self.parent_overlay.update_all_backgrounds()

    def apply_settings(self):
        """Apply all settings"""
        try:
            self.parent_overlay.settings.opacity = self.opacity_slider.value() / 20.0
            self.parent_overlay.settings.refresh_rate = self.refresh_slider.value() / 4.0
            self.parent_overlay.settings.hide_headers = self.hide_headers_cb.isChecked()
            self.parent_overlay.settings.center_drivers = self.center_drivers_cb.isChecked()
            self.parent_overlay.settings.bold_drivers = self.bold_drivers_cb.isChecked()
            self.parent_overlay.settings.show_division_gap = self.show_division_gap_cb.isChecked()
            self.parent_overlay.settings.show_last_lap = self.show_last_lap_cb.isChecked()
            self.parent_overlay.settings.show_delta = self.show_delta_cb.isChecked()
            self.parent_overlay.settings.show_best_lap = self.show_best_lap_cb.isChecked()
            self.parent_overlay.settings.show_positions_gained = self.show_positions_gained_cb.isChecked()
            self.parent_overlay.settings.font_size = self.font_size_combo.currentText()
            self.parent_overlay.settings.row_color_style = self.color_style_combo.currentText()

            # Apply log level change immediately
            new_log_level = self.log_level_combo.currentText()
            if new_log_level != self.parent_overlay.settings.log_level:
                set_log_level(new_log_level)
            self.parent_overlay.settings.log_level = new_log_level

            self.parent_overlay.update_all_backgrounds()

            # Save and refresh
            self.parent_overlay.save_settings()
            self.parent_overlay.signals.refresh_colors.emit()

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply settings: {e}")
            
    def on_cancel(self):
        """Cancel settings"""
        self.reject()

