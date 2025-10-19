"""Settings dialog for configuring overlay appearance and behavior."""

import os
import json
from typing import TYPE_CHECKING
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSlider, QCheckBox, QFileDialog, QMessageBox, QColorDialog, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from config.constants import VERSION

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class SettingsDialog(QDialog):
    """Modal settings dialog for configuring overlay appearance and behavior. Shows update link if new version available."""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_overlay = parent
        self.setWindowTitle("BB's League Overlay - Settings")
        self.setModal(True)
        self.setFixedSize(300, 705)

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
        
    def choose_color(self, division):
        """Open color picker to customize a division's color."""
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

                # Delegate to parent to handle division config reload
                self.parent_overlay.reload_division_config(file_path)
                self.current_config_label.setText(os.path.basename(file_path))

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
                # Validate JSON file can be loaded
                with open(file_path, 'r') as f:
                    config_data = json.load(f)

                # Delegate to parent to handle division config reload
                self.parent_overlay.reload_division_config(file_path)
                self.current_config_label.setText(os.path.basename(file_path))

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
        self.reject()

