"""Configuration constants for the League Overlay application."""

from dataclasses import dataclass
from typing import Dict, Any


# Application version
VERSION = "0.9.7.7"


@dataclass(frozen=True)
class UIColors:
    """Color palette for the overlay UI."""
    BACKGROUND_BLACK: str = '#000000'
    HEADER_DARK_GRAY: str = '#333333'
    SCROLLBAR_GRAY: str = '#222222'
    BUTTON_GRAY: str = '#555555'
    BUTTON_HOVER_GRAY: str = '#666666'
    GRADIENT_BLACK: str = '#1a1a1a'
    CLOSE_BUTTON_RED: str = '#cc0000'
    CLOSE_BUTTON_HOVER_RED: str = '#ff0000'
    DIVISION_HIGHLIGHT_GREEN: str = '#0FC436'


@dataclass(frozen=True)
class UIDimensions:
    """UI element dimensions."""
    WINDOW_MIN_WIDTH: int = 250
    WINDOW_MIN_HEIGHT: int = 200
    TITLE_BAR_HEIGHT: int = 30
    SIZE_GRIP_SIZE: int = 20
    CLOSE_BUTTON_WIDTH: int = 25
    SETTINGS_DIALOG_WIDTH: int = 310
    SETTINGS_DIALOG_HEIGHT: int = 705


@dataclass(frozen=True)
class ColumnLayout:
    """Column stretch factors for driver list."""
    POS: int = 11
    DIV_POS: int = 11
    CAR_NUM: int = 13
    DRIVER_NAME: int = 46
    GAP: int = 19


@dataclass(frozen=True)
class Timing:
    """Additional timing constants."""
    AUTO_CENTER_CHECK_INTERVAL: int = 1000  # milliseconds
    STARTUP_GRACE_PERIOD: float = 3.0  # seconds
    AUTO_HIDE_DELAY: int = 500  # milliseconds
    UPDATE_CHECK_DELAY: float = 1.0  # seconds
    CHECKERED_REFRESH: float = 0.1  # seconds (10 Hz - fast finish tracking, throttled UI updates)


@dataclass(frozen=True)
class UIConfig:
    """UI configuration constants."""
    # Font size configurations
    FONT_SIZES: Dict[str, Dict[str, Any]] = None

    # Default division colors
    DEFAULT_COLORS: Dict[str, str] = None

    # Auto-center settings
    MANUAL_SCROLL_TIMEOUT: float = 5.0  # seconds
    STATUS_UPDATE_INTERVAL: int = 1000  # milliseconds

    def __post_init__(self):
        if self.FONT_SIZES is None:
            object.__setattr__(self, 'FONT_SIZES', {
                "Small": {
                    "title": "8.5pt",
                    "button": "8pt",
                    "status": "8pt",
                    "header": "8pt",
                    "data": "8pt",
                    "spacing": 2
                },
                "Medium": {
                    "title": "9.5pt",
                    "button": "8.5pt",
                    "status": "9pt",
                    "header": "9pt",
                    "data": "9pt",
                    "spacing": 3
                },
                "Large": {
                    "title": "10.5pt",
                    "button": "9pt",
                    "status": "10pt",
                    "header": "10pt",
                    "data": "10pt",
                    "spacing": 4
                },
                "Extra Large": {
                    "title": "11.5pt",
                    "button": "9.5pt",
                    "status": "11pt",
                    "header": "11pt",
                    "data": "11pt",
                    "spacing": 5
                }
            })

        if self.DEFAULT_COLORS is None:
            object.__setattr__(self, 'DEFAULT_COLORS', {
                "Pro": "#FF8C00",
                "ProAm": "#9370DB",
                "Am": "#45B3E0",
                "Rookie": "#FF2000",
                "Default": "#FFFFFF"
            })


@dataclass(frozen=True)
class FileConfig:
    """File path configuration constants."""
    SETTINGS_FILE: str = "LeagueOverlay.config"
    DIVISIONS_FILE: str = "league_divisions.json"


@dataclass(frozen=True)
class TelemetryConfig:
    """Telemetry configuration constants."""
    DEFAULT_REFRESH_RATE: float = 2.0  # seconds
    MIN_REFRESH_RATE: float = 0.25
    MAX_REFRESH_RATE: float = 5.0

    # iRacing SDK constants
    MAX_CARS: int = 64
    INACTIVE_POSITION: int = 0
    INVALID_LAP: int = -1
    INVALID_LAP_PCT: float = -1.0


# Global configuration instances
UI_COLORS = UIColors()
UI_DIMENSIONS = UIDimensions()
COLUMN_LAYOUT = ColumnLayout()
TIMING = Timing()
UI_CONFIG = UIConfig()
FILE_CONFIG = FileConfig()
TELEMETRY_CONFIG = TelemetryConfig()
