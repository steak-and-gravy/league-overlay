"""Configuration constants for the League Overlay application."""

from dataclasses import dataclass
from typing import Dict, Any


# Application version
VERSION = "0.9.9.8"


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
class LicenseColors:
    """Background colors for license class ratings (R, D, C, B, A, P)."""
    ROOKIE: str = '#8B0000'      # Dark Red (R 1-4)
    D_CLASS: str = "#A55B00"     # Dark Orange (D 5-8)
    C_CLASS: str = '#DAA520'     # Goldenrod (C 9-12)
    B_CLASS: str = '#006400'     # Dark Green (B 13-16)
    A_CLASS: str = '#00008B'     # Dark Blue (A 17-20)
    PRO: str = '#4B0082'         # Indigo (P 21-24)
    WC: str = '#800080'          # Purple (World Championship 25+)


@dataclass(frozen=True)
class UIDimensions:
    """UI element dimensions."""
    WINDOW_MIN_WIDTH: int = 250
    WINDOW_MIN_HEIGHT: int = 200
    TITLE_BAR_HEIGHT: int = 30
    SIZE_GRIP_SIZE: int = 20
    CLOSE_BUTTON_WIDTH: int = 25
    SETTINGS_DIALOG_WIDTH: int = 630
    SETTINGS_DIALOG_HEIGHT: int = 680
    BROADCAST_HEADER_MIN_HEIGHT: int = 60


@dataclass(frozen=True)
class ColumnLayout:
    """Column stretch factors for driver list."""
    POS: int = 6
    POSITIONS_GAINED: int = 6
    CAR_MANUFACTURER: int = 5  # Small column for manufacturer badge
    DIV_POS: int = 6
    CAR_NUM: int = 6
    DRIVER_NAME: int = 25
    GAP: int = 9  # Gap to overall leader
    DIV_GAP: int = 9  # Gap to division leader (D-Gap)
    INTERVAL: int = 9  # Interval to car ahead (overall)
    DIV_INTERVAL: int = 9  # Interval to car ahead in division (D-Int)
    BEST_LAP: int = 9
    DELTA: int = 6
    LAST_LAP: int = 9
    RATING: int = 13
    PIT_LAP: int = 5


@dataclass(frozen=True)
class ColumnMinWidths:
    """Minimum pixel widths for columns to prevent misalignment at small window sizes."""
    POS: int = 25
    POSITIONS_GAINED: int = 30
    CAR_MANUFACTURER: int = 30
    DIV_POS: int = 35
    CAR_NUM: int = 35
    DRIVER_NAME: int = 60
    GAP: int = 50  # Gap to overall leader
    DIV_GAP: int = 50  # Gap to division leader (D-Gap)
    INTERVAL: int = 50  # Interval to car ahead (overall)
    DIV_INTERVAL: int = 50  # Interval to car ahead in division (D-Int)
    BEST_LAP: int = 55
    DELTA: int = 35
    LAST_LAP: int = 55
    RATING: int = 55  # Combined iRating + Safety Rating column
    PIT_LAP: int = 35  # Combined Last Pit + Out Lap column


@dataclass(frozen=True)
class Timing:
    """Timing and refresh rate constants."""
    AUTO_CENTER_CHECK_INTERVAL: int = 1000  # milliseconds
    STARTUP_GRACE_PERIOD: float = 3.0  # seconds
    AUTO_HIDE_DELAY: int = 500  # milliseconds
    UPDATE_CHECK_DELAY: float = 1.0  # seconds
    CONNECTION_MESSAGE_DURATION: float = 3.0  # seconds - how long to show "Connected" message
    DEFAULT_LAP_TIME_FALLBACK: float = 90.0  # seconds - fallback lap time when no data available
    BROADCAST_ROLL_ROWS: int = 5
    BROADCAST_ROLL_INTERVAL_SECONDS: int = 5  # seconds


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
                    "broadcast_title": "10pt",
                    "broadcast_session": "8pt",
                    "broadcast_track": "7.5pt",
                    "spacing": 2
                },
                "Medium": {
                    "title": "9.5pt",
                    "button": "8.5pt",
                    "status": "9pt",
                    "header": "9pt",
                    "data": "9pt",
                    "broadcast_title": "11pt",
                    "broadcast_session": "9t",
                    "broadcast_track": "8.5pt",
                    "spacing": 3
                },
                "Large": {
                    "title": "10.5pt",
                    "button": "9pt",
                    "status": "10pt",
                    "header": "10pt",
                    "data": "10pt",
                    "broadcast_title": "12pt",
                    "broadcast_session": "10pt",
                    "broadcast_track": "9.5pt",
                    "spacing": 4
                },
                "Extra Large": {
                    "title": "11.5pt",
                    "button": "9.5pt",
                    "status": "11pt",
                    "header": "11pt",
                    "data": "11pt",
                    "broadcast_title": "13pt",
                    "broadcast_session": "11pt",
                    "broadcast_track": "10.5pt",
                    "spacing": 5
                }
            })

        if self.DEFAULT_COLORS is None:
            object.__setattr__(self, 'DEFAULT_COLORS', {
                "Pro": "#FF8C00",
                "ProAm": "#fe00ff",
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
    DEFAULT_REFRESH_RATE: float = 1.0  # seconds
    MIN_REFRESH_RATE: float = 0.25
    MAX_REFRESH_RATE: float = 3.0

    # iRacing SDK constants
    MAX_CARS: int = 63
    INACTIVE_POSITION: int = 0
    INVALID_LAP: int = -1
    INVALID_LAP_PCT: float = -1.0

    # iRacing SessionFlags (bitfield values)
    FLAG_CHECKERED: int = 0x00000001
    FLAG_WHITE: int = 0x00000002
    FLAG_GREEN: int = 0x00000004
    FLAG_YELLOW: int = 0x00000008           # Local yellow
    FLAG_RED: int = 0x00000010
    FLAG_BLUE: int = 0x00000020
    FLAG_DEBRIS: int = 0x00000040
    FLAG_CROSSED: int = 0x00000080
    FLAG_YELLOW_WAVING: int = 0x00000100    # Local yellow waving
    FLAG_ONE_LAP_TO_GREEN: int = 0x00000200
    FLAG_GREEN_HELD: int = 0x00000400
    FLAG_TEN_TO_GO: int = 0x00000800
    FLAG_FIVE_TO_GO: int = 0x00001000
    FLAG_RANDOM_WAVING: int = 0x00002000
    FLAG_CAUTION: int = 0x00004000           # Full Course Yellow
    FLAG_CAUTION_WAVING: int = 0x00008000    # FCY being established


MANUFACTURER_MAP = {
    'ferrari': ('FER', '#DC0000'),
    'porsche': ('POR', '#C0C0C0'),
    'bmw': ('BMW', '#1C69D4'),
    'mercedes': ('MER', '#00D2BE'),
    'lamborghini': ('LAM', '#DAA520'),
    'audi': ('AUD', '#BB0A30'),
    'mclaren': ('MCL', '#FF8700'),
    'aston': ('AMR', '#006F62'),
    'ford': ('FRD', '#003399'),
    'chevrolet': ('CHV', '#D4AF37'),
    'toyota': ('TOY', '#EB0A1E'),
    'honda': ('HND', '#CC0000'),
    'nissan': ('NIS', '#C3002F'),
    'hyundai': ('HYU', '#002C5F'),
    'cadillac': ('CAD', '#A69461'),
    'acura': ('ACU', '#1B1B1B'),
    'mazda': ('MAZ', '#910000'),
    'lotus': ('LOT', '#FFB800'),
    'dallara': ('DAL', '#1E3A5F'),
    'ligier': ('LIG', '#003DA5'),
    'riley': ('RIL', '#2E4057'),
    'radical': ('RAD', '#FF4500'),
    'skip': ('SKP', '#4169E1'),
    'spec': ('SPC', '#228B22'),
    'street': ('STK', '#696969'),
    'supercars': ('V8S', '#FFD700'),
    'global': ('GMZ', '#FF6347'),
}


# Global configuration instances
UI_COLORS = UIColors()
LICENSE_COLORS = LicenseColors()
UI_DIMENSIONS = UIDimensions()
COLUMN_LAYOUT = ColumnLayout()
COLUMN_MIN_WIDTHS = ColumnMinWidths()
TIMING = Timing()
UI_CONFIG = UIConfig()
FILE_CONFIG = FileConfig()
TELEMETRY_CONFIG = TelemetryConfig()
