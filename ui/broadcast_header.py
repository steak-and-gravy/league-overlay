"""Broadcast-style header widget for the overlay.

Displays league logo, league name, session info, and track name in a
professional broadcast-quality layout suitable for spectator streams.
"""

import os
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap

from config.constants import UI_COLORS, UI_DIMENSIONS
from config.logging_config import get_logger

logger = get_logger(__name__)


class BroadcastHeaderWidget(QWidget):
    """Broadcast-quality header showing logo, league name, session info, and track name."""

    def __init__(self, settings: Any, get_bg_color_fn, get_font_size_fn, parent: Optional[QWidget] = None):
        """Initialize the broadcast header.

        Args:
            settings: AppSettings instance
            get_bg_color_fn: Function to get background color with opacity (hex -> rgba)
            get_font_size_fn: Function to get font size for an element type
            parent: Parent widget
        """
        super().__init__(parent)
        self.settings = settings
        self.get_bg_color = get_bg_color_fn
        self.get_font_size = get_font_size_fn
        self._logo_pixmap: Optional[QPixmap] = None
        self._setup_ui()
        self._load_logo()

    def _setup_ui(self):
        """Build the header layout."""
        self.setMinimumHeight(UI_DIMENSIONS.BROADCAST_HEADER_MIN_HEIGHT)
        self._update_background()

        # Main horizontal layout: [logo] [text column]
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(10)

        # Logo label (left side)
        self.logo_label = QLabel()
        self.logo_label.setStyleSheet("background-color: transparent;")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(48, 48)
        self.logo_label.hide()
        main_layout.addWidget(self.logo_label)

        # Text column (right side)
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        # League name
        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignCenter)
        self._style_title_label()
        text_layout.addWidget(self.title_label)

        # Accent line
        self.accent_line = QWidget()
        self.accent_line.setFixedHeight(2)
        self._style_accent_line()
        text_layout.addWidget(self.accent_line)

        # Session info (e.g., "RACE · Lap 14/20 · 14:23")
        self.session_label = QLabel("")
        self.session_label.setAlignment(Qt.AlignCenter)
        self._style_session_label()
        text_layout.addWidget(self.session_label)

        # Track name
        self.track_label = QLabel("")
        self.track_label.setAlignment(Qt.AlignCenter)
        self._style_track_label()
        text_layout.addWidget(self.track_label)

        main_layout.addLayout(text_layout, 1)

        # Set initial title text
        if self.settings.broadcast_header_title:
            self.title_label.setText(self.settings.broadcast_header_title.upper())

    def _update_background(self):
        """Update the widget background color with opacity."""
        bg = self.get_bg_color('#141414')
        self.setStyleSheet(f"BroadcastHeaderWidget {{ background-color: {bg}; }}")
        self.setAutoFillBackground(False)

    def _style_title_label(self):
        """Apply styling to the league name label."""
        font_size = self.get_font_size('broadcast_title')
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: {font_size};
                letter-spacing: 1px;
                background-color: transparent;
            }}
        """)

    def _style_accent_line(self):
        """Apply styling to the accent divider line."""
        color = self.settings.broadcast_header_accent_color
        self.accent_line.setStyleSheet(f"background-color: {color};")

    def _style_session_label(self):
        """Apply styling to the session info label."""
        font_size = self.get_font_size('broadcast_session')
        self.session_label.setStyleSheet(f"""
            QLabel {{
                color: #CCCCCC;
                font-size: {font_size};
                font-weight: normal;
                background-color: transparent;
            }}
        """)

    def _set_session_label_caution_style(self):
        """Highlight CAUTION text in broadcast mode."""
        font_size = self.get_font_size('broadcast_session')
        self.session_label.setStyleSheet(f"""
            QLabel {{
                color: #FFD700;
                font-size: {font_size};
                font-weight: bold;
                background-color: transparent;
            }}
        """)

    def _style_track_label(self):
        """Apply styling to the track name label."""
        font_size = self.get_font_size('broadcast_track')
        self.track_label.setStyleSheet(f"""
            QLabel {{
                color: white;
                font-size: {font_size};
                font-style: italic;
                background-color: transparent;
            }}
        """)

    def _load_logo(self):
        """Load the league logo from the configured path."""
        logo_path = self.settings.broadcast_header_logo
        if not logo_path:
            self.logo_label.hide()
            return

        # Support both absolute and relative paths
        if not os.path.isabs(logo_path):
            logo_path = os.path.join(os.getcwd(), logo_path)

        if not os.path.isfile(logo_path):
            logger.warning(f"Broadcast header logo not found: {logo_path}")
            self.logo_label.hide()
            return

        pixmap = QPixmap(logo_path)
        if pixmap.isNull():
            logger.warning(f"Failed to load broadcast header logo: {logo_path}")
            self.logo_label.hide()
            return

        self._logo_pixmap = pixmap
        self._apply_logo()
        self.logo_label.show()

    def _apply_logo(self):
        """Scale and apply the cached logo pixmap to the label."""
        if self._logo_pixmap is None:
            return
        max_size = self.logo_label.size()
        scaled = self._logo_pixmap.scaled(
            max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.logo_label.setPixmap(scaled)

    def update_session_info(self, session_data: Dict[str, Any]):
        """Update the header with live session data.

        Args:
            session_data: Dictionary containing:
                - session_status: Formatted session status text (e.g., "Race - Lap 5/20")
                - track_display_name: Track name from iRacing WeekendInfo
                - status_color: Color name for flag state ('green', 'yellow', 'orange')
        """
        status_text = session_data.get('session_status', '')
        if status_text:
            # Convert "Race - Lap 14/20" to "RACE · Lap 14/20" style
            parts = status_text.split(' - ', 1)
            if len(parts) == 2:
                formatted = f"{parts[0].upper()}  ·  {parts[1]}"
            else:
                formatted = status_text.upper()
            self.session_label.setText(formatted)
            if 'CAUTION' in status_text.upper():
                self._set_session_label_caution_style()
            else:
                self._style_session_label()

        track_name = session_data.get('track_display_name', '')
        if track_name:
            self.track_label.setText(track_name)
            self.track_label.show()
        elif not self.track_label.text():
            self.track_label.hide()

        # Update accent line color for flag status
        status_color = session_data.get('status_color')
        if status_color:
            color_map = {
                'yellow': '#FFD700',   # Caution flag
                'orange': '#FF8C00',   # Connecting/warning
                'green': self.settings.broadcast_header_accent_color,  # Normal - user's accent
            }
            accent = color_map.get(status_color, self.settings.broadcast_header_accent_color)
            self.accent_line.setStyleSheet(f"background-color: {accent};")

    def refresh_styles(self):
        """Refresh all styles (called when settings change)."""
        self._update_background()
        self._style_title_label()
        self._style_accent_line()
        self._style_session_label()
        self._style_track_label()

        if self.settings.broadcast_header_title:
            self.title_label.setText(self.settings.broadcast_header_title.upper())
        else:
            self.title_label.setText("")

        self._load_logo()

    def paintEvent(self, event):
        """Custom paint to ensure background renders with opacity."""
        from PySide6.QtGui import QPainter, QColor

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Parse the background color
        bg = self.get_bg_color('#141414')
        # Extract rgba values
        if bg.startswith('rgba('):
            try:
                values = bg[5:-1].split(',')
                r, g, b = int(values[0].strip()), int(values[1].strip()), int(values[2].strip())
                a = float(values[3].strip())
                color = QColor(r, g, b, int(a * 255))
            except (ValueError, IndexError):
                color = QColor(20, 20, 20, 128)
        else:
            color = QColor(20, 20, 20, 128)

        painter.fillRect(self.rect(), color)
        painter.end()

        super().paintEvent(event)
