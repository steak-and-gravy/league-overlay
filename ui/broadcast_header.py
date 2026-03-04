"""Broadcast-style header widget for the overlay.

Displays league logo, league name, session info, and track name in a
professional broadcast-quality layout suitable for spectator streams.
"""

from typing import Optional, Dict, Any
from urllib.parse import urlparse

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
import requests

from config.constants import UI_COLORS, UI_DIMENSIONS
from config.logging_config import get_logger

logger = get_logger(__name__)


class BroadcastHeaderWidget(QWidget):
    """Broadcast-quality header showing logo, league name, session info, and track name."""

    def __init__(
        self,
        settings: Any,
        get_bg_color_fn,
        get_font_size_fn,
        get_broadcast_title_fn=None,
        get_broadcast_logo_fn=None,
        get_broadcast_accent_fn=None,
        parent: Optional[QWidget] = None,
    ):
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
        self.get_broadcast_title = get_broadcast_title_fn
        self.get_broadcast_logo = get_broadcast_logo_fn
        self.get_broadcast_accent = get_broadcast_accent_fn
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

        # Set initial title text (with default fallback)
        self.title_label.setText(self._get_display_title())

    def _get_display_title(self) -> str:
        """Return configured title or fallback default for broadcast header."""
        title = None
        if callable(self.get_broadcast_title):
            title = self.get_broadcast_title()
        if not title:
            title = getattr(self.settings, "broadcast_header_title", None)
        if not title:
            title = "BB's League Overlay"
        return title.upper()

    def _get_accent_color(self) -> str:
        """Return broadcast accent color (runtime provider takes precedence)."""
        color = None
        if callable(self.get_broadcast_accent):
            color = self.get_broadcast_accent()
        if not color:
            color = getattr(self.settings, "broadcast_header_accent_color", None)
        return color or "#FF8C00"

    def _get_logo_path(self) -> str:
        """Return runtime broadcast logo URL with default fallback."""
        logo_path = None
        if callable(self.get_broadcast_logo):
            logo_path = self.get_broadcast_logo()
        if not logo_path:
            logo_path = getattr(self.settings, "broadcast_header_logo", None)
        return logo_path or self._get_default_logo_path()

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
        color = self._get_accent_color()
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
        """Load the league logo from configured URL or default URL."""
        logo_path = self._get_logo_path()

        if not self._is_logo_url(logo_path):
            logger.warning(f"Broadcast header logo must be an HTTP(S) URL: {logo_path}")
            self.logo_label.hide()
            return

        pixmap = self._load_logo_from_url(logo_path)
        if pixmap is None:
            self.logo_label.hide()
            return

        self._logo_pixmap = pixmap
        self._apply_logo()
        self.logo_label.show()

    @staticmethod
    def _is_logo_url(path: str) -> bool:
        """Return True if a logo path is an HTTP(S) URL."""
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def _load_logo_from_url(self, logo_url: str) -> Optional[QPixmap]:
        """Load and decode logo image from web URL."""
        try:
            response = requests.get(logo_url, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch broadcast header logo from URL {logo_url}: {e}")
            return None

        pixmap = QPixmap()
        if not pixmap.loadFromData(response.content):
            logger.warning(f"Failed to decode broadcast header logo from URL: {logo_url}")
            return None
        return pixmap

    def _get_default_logo_path(self) -> str:
        """Return the default broadcast logo URL."""
        return "https://leagueoverlay.com/assets/img/BBLeagueOverlay96.png"

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
        else:
            self.track_label.setText("")
            self.track_label.hide()

        # Update accent line color for flag status
        status_color = session_data.get('status_color')
        if status_color:
            color_map = {
                'yellow': '#FFD700',   # Caution flag
                'orange': '#FF8C00',   # Connecting/warning
                'green': self._get_accent_color(),  # Normal accent
            }
            accent = color_map.get(status_color, self._get_accent_color())
            self.accent_line.setStyleSheet(f"background-color: {accent};")

    def refresh_styles(self):
        """Refresh all styles (called when settings change)."""
        self._update_background()
        self._style_title_label()
        self._style_accent_line()
        self._style_session_label()
        self._style_track_label()

        self.title_label.setText(self._get_display_title())

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
