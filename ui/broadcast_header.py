"""Broadcast-style header widget for the overlay.

Displays league logo, league name, and session info in a
professional broadcast-quality layout suitable for spectator streams.
"""

from typing import Optional, Dict, Any
from urllib.parse import urlparse
import threading

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
import requests

from config.constants import UI_DIMENSIONS
from config.logging_config import get_logger

logger = get_logger(__name__)


class BroadcastHeaderWidget(QWidget):
    """Broadcast-quality header showing logo, league name, and session info."""
    logo_loaded = Signal(str, object)

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
        super().__init__(parent)
        self.settings = settings
        self.get_bg_color = get_bg_color_fn
        self.get_font_size = get_font_size_fn
        self.get_broadcast_title = get_broadcast_title_fn
        self.get_broadcast_logo = get_broadcast_logo_fn
        self.get_broadcast_accent = get_broadcast_accent_fn
        self._logo_pixmap: Optional[QPixmap] = None
        self._logo_url: Optional[str] = None
        self.logo_loaded.connect(self._apply_loaded_logo)
        self._setup_ui()
        self._load_logo()

    def _setup_ui(self):
        self.setMinimumHeight(UI_DIMENSIONS.BROADCAST_HEADER_MIN_HEIGHT)
        self._update_background()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 6)
        main_layout.setSpacing(10)

        self.logo_label = QLabel()
        self.logo_label.setStyleSheet("background-color: transparent;")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(48, 48)
        self.logo_label.hide()
        main_layout.addWidget(self.logo_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignCenter)
        self._style_title_label()
        text_layout.addWidget(self.title_label)

        self.accent_line = QWidget()
        self.accent_line.setFixedHeight(2)
        self._style_accent_line()
        text_layout.addWidget(self.accent_line)

        self.session_label = QLabel("")
        self.session_label.setAlignment(Qt.AlignCenter)
        self._style_session_label()
        text_layout.addWidget(self.session_label)

        self.track_label = QLabel("")
        self.track_label.setAlignment(Qt.AlignCenter)
        self._style_track_label()
        text_layout.addWidget(self.track_label)

        main_layout.addLayout(text_layout, 1)
        self.title_label.setText(self._get_display_title())

    def _get_display_title(self) -> str:
        title = None
        if callable(self.get_broadcast_title):
            title = self.get_broadcast_title()
        if not title:
            title = getattr(self.settings, "broadcast_header_title", None)
        if not title:
            title = "BB's League Overlay"
        return title.upper()

    def _get_accent_color(self) -> str:
        color = None
        if callable(self.get_broadcast_accent):
            color = self.get_broadcast_accent()
        if not color:
            color = getattr(self.settings, "broadcast_header_accent_color", None)
        return color or "#FF8C00"

    def _get_logo_path(self) -> str:
        logo_path = None
        if callable(self.get_broadcast_logo):
            logo_path = self.get_broadcast_logo()
        if not logo_path:
            logo_path = getattr(self.settings, "broadcast_header_logo", None)
        return logo_path or self._get_default_logo_path()

    def _update_background(self):
        bg = self.get_bg_color("#141414")
        self.setStyleSheet(f"BroadcastHeaderWidget {{ background-color: {bg}; }}")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)

    def _style_title_label(self):
        font_size = self.get_font_size("broadcast_title")
        self.title_label.setStyleSheet(
            f"""
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: {font_size};
                letter-spacing: 1px;
                background-color: transparent;
            }}
        """
        )

    def _style_accent_line(self):
        color = self._get_accent_color()
        self.accent_line.setStyleSheet(f"background-color: {color};")

    def _style_session_label(self):
        font_size = self.get_font_size("broadcast_session")
        self.session_label.setStyleSheet(
            f"""
            QLabel {{
                color: white;
                font-size: {font_size};
                font-weight: bold;
                background-color: transparent;
            }}
        """
        )

    def _set_session_label_caution_style(self):
        font_size = self.get_font_size("broadcast_session")
        self.session_label.setStyleSheet(
            f"""
            QLabel {{
                color: #FFD700;
                font-size: {font_size};
                font-weight: bold;
                background-color: transparent;
            }}
        """
        )

    def _set_session_label_update_available_style(self):
        font_size = self.get_font_size("broadcast_session")
        self.session_label.setStyleSheet(
            f"""
            QLabel {{
                color: #00FF00;
                font-size: {font_size};
                font-weight: bold;
                background-color: transparent;
            }}
        """
        )

    def _style_track_label(self):
        font_size = self.get_font_size("broadcast_track")
        self.track_label.setStyleSheet(
            f"""
            QLabel {{
                color: white;
                font-size: {font_size};
                font-style: italic;
                background-color: transparent;
            }}
        """
        )

    def _load_logo(self):
        logo_path = self._get_logo_path()

        if not self._is_logo_url(logo_path):
            logger.warning(f"Broadcast header logo must be an HTTP(S) URL: {logo_path}")
            self.logo_label.hide()
            return

        if self._logo_url == logo_path and self._logo_pixmap is not None:
            self._apply_logo()
            self.logo_label.show()
            return

        self._logo_url = logo_path
        self.logo_label.hide()
        self._load_logo_async(logo_path)

    def _load_logo_async(self, logo_url: str):
        """Load logo from URL in a background thread to avoid UI stalls."""
        def worker():
            logo_data = self._fetch_logo_data(logo_url)
            self.logo_loaded.emit(logo_url, logo_data)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_loaded_logo(self, logo_url: str, logo_data: Optional[bytes]):
        """Apply asynchronously loaded logo if still current."""
        if logo_url != self._logo_url or logo_data is None:
            self.logo_label.hide()
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(logo_data):
            logger.warning(f"Failed to decode broadcast header logo from URL: {logo_url}")
            self.logo_label.hide()
            return
        self._logo_pixmap = pixmap
        self._apply_logo()
        self.logo_label.show()

    @staticmethod
    def _is_logo_url(path: str) -> bool:
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def _fetch_logo_data(self, logo_url: str) -> Optional[bytes]:
        try:
            response = requests.get(logo_url, timeout=5)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch broadcast header logo from URL {logo_url}: {e}")
            return None
        return response.content

    def _load_logo_from_url(self, logo_url: str) -> Optional[QPixmap]:
        logo_data = self._fetch_logo_data(logo_url)
        if logo_data is None:
            return None
        pixmap = QPixmap()
        if not pixmap.loadFromData(logo_data):
            logger.warning(f"Failed to decode broadcast header logo from URL: {logo_url}")
            return None
        return pixmap

    def _get_default_logo_path(self) -> str:
        return "https://leagueoverlay.com/assets/img/BBLeagueOverlay96.png"

    def _apply_logo(self):
        if self._logo_pixmap is None:
            return
        max_size = self.logo_label.size()
        scaled = self._logo_pixmap.scaled(max_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.logo_label.setPixmap(scaled)

    def update_session_info(self, session_data: Dict[str, Any]):
        status_text = session_data.get("session_status", "")
        if status_text:
            parts = status_text.split(" - ", 1)
            if len(parts) == 2:
                formatted = f"{parts[0].upper()}  ·  {parts[1]}"
            else:
                formatted = status_text.upper()
            self.session_label.setText(formatted)
            if "CAUTION" in status_text.upper():
                self._set_session_label_caution_style()
            elif "UPDATE AVAILABLE" in status_text.upper():
                self._set_session_label_update_available_style()
            else:
                self._style_session_label()

        track_name = session_data.get("track_display_name", "")
        if track_name:
            self.track_label.setText(track_name)
            self.track_label.show()
        else:
            self.track_label.setText("")
            self.track_label.hide()

        status_color = session_data.get("status_color")
        if status_color:
            color_map = {
                "yellow": "#FFD700",
                "orange": "#FF8C00",
                "green": self._get_accent_color(),
            }
            accent = color_map.get(status_color, self._get_accent_color())
            self.accent_line.setStyleSheet(f"background-color: {accent};")

    def refresh_styles(self):
        self._update_background()
        self._style_title_label()
        self._style_accent_line()
        self._style_session_label()
        self._style_track_label()
        self.title_label.setText(self._get_display_title())
        self._load_logo()
