"""Configuration constants for the League Overlay application."""

from dataclasses import dataclass
from typing import Dict, Any, List, NamedTuple, Optional


# Application version
VERSION = "0.9.9.8b"


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
    SETTINGS_DIALOG_WIDTH: int = 660
    SETTINGS_DIALOG_HEIGHT: int = 740
    BROADCAST_HEADER_MIN_HEIGHT: int = 60


class ColumnDef(NamedTuple):
    """Definition of a single overlay column."""
    id: str                 # Unique identifier (matches settings key without 'show_' prefix)
    header: str             # Display text in header row
    stretch: int            # Stretch factor for layout
    min_width: int          # Minimum pixel width
    max_width: Optional[int]  # Maximum pixel width (None = can keep stretching)
    settings_key: str       # AppSettings bool field name ('' = always visible)
    tooltip: str            # Tooltip text ('' = none)
    render_method: str      # Method name on DriverRowRenderer (without '_create_' prefix and '_label' suffix)


# Authoritative column definitions — order here is the DEFAULT display order.
# Both create_headers() and create_row() iterate this registry.
COLUMN_DEFS: List[ColumnDef] = [
    ColumnDef('pos',              'Overall',  7,  35,  35, '',                       '',                                              'position'),
    ColumnDef('positions_gained', '+/-',      5,  28,  28, 'show_positions_gained',  '',                                              'positions_gained'),
    ColumnDef('div_pos',          'Class',    6,  27,  27, '',                       '',                                              'division_position'),
    ColumnDef('driver_name',      'Driver',  25,  60, None, '',                       '',                                              'driver_name'),
    ColumnDef('car_manufacturer', 'Mfr',      4,  28,  28, 'show_car_manufacturer',  '',                                              'manufacturer'),
    ColumnDef('rating',           'Rating',  14,  58,  65, 'show_rating',            '',                                              'combined_rating'),
    ColumnDef('car_number',       'Car#',     6,  29,  30, 'show_car_number',        '',                                              'car_number'),
    ColumnDef('gap',              'Gap',      8,  42,  46, 'show_gap',               'Gap to overall leader',                         'gap'),
    ColumnDef('div_gap',          'C-Gap',    8,  42,  46, 'show_division_gap',      'Gap to division leader',                        'division_gap'),
    ColumnDef('interval',         'Int',      8,  42,  46, 'show_interval',          'Interval to car ahead in overall standings',    'interval'),
    ColumnDef('div_interval',     'C-Int',    8,  42,  46, 'show_division_interval', 'Interval to car ahead in your division',        'division_interval'),
    ColumnDef('best_lap',         'Best Lap', 9,  50,  65, 'show_best_lap',          '',                                              'best_lap'),
    ColumnDef('last_lap',         'Last Lap', 9,  50,  65, 'show_last_lap',          '',                                              'last_lap'),
    ColumnDef('delta',            'Delta',    6,  34,  40, 'show_delta',             '',                                              'delta'),
    ColumnDef('pit_lap',          'Pit',      5,  28,  32, 'show_pit_lap',           '',                                              'pit_lap'),
]

# Column ID → ColumnDef lookup
COLUMN_REGISTRY: Dict[str, ColumnDef] = {c.id: c for c in COLUMN_DEFS}

# Default column order (list of column IDs)
DEFAULT_COLUMN_ORDER: List[str] = [c.id for c in COLUMN_DEFS]

# Set of all valid column IDs
VALID_COLUMN_IDS: frozenset = frozenset(DEFAULT_COLUMN_ORDER)


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
                    "title": "8pt",
                    "button": "8pt",
                    "status": "8pt",
                    "header": "7.5pt",
                    "data": "8pt",
                    "broadcast_title": "10pt",
                    "broadcast_session": "8pt",
                    "broadcast_track": "7.5pt",
                    "spacing": 2
                },
                "Medium": {
                    "title": "9pt",
                    "button": "8.5pt",
                    "status": "9pt",
                    "header": "8pt",
                    "data": "9pt",
                    "broadcast_title": "11pt",
                    "broadcast_session": "9pt",
                    "broadcast_track": "8.5pt",
                    "spacing": 3
                },
                "Slim Large": {
                    "title": "10pt",
                    "button": "9pt",
                    "status": "10pt",
                    "header": "9pt",
                    "data": "10pt",
                    "broadcast_title": "12pt",
                    "broadcast_session": "10pt",
                    "broadcast_track": "9.5pt",
                    "spacing": 2
                },
                "Large": {
                    "title": "10pt",
                    "button": "9pt",
                    "status": "10pt",
                    "header": "9pt",
                    "data": "10pt",
                    "broadcast_title": "12pt",
                    "broadcast_session": "10pt",
                    "broadcast_track": "9.5pt",
                    "spacing": 4
                }
            })

        if self.DEFAULT_COLORS is None:
            object.__setattr__(self, 'DEFAULT_COLORS', {
                "Pro": "#FF8C00",
                "ProAm": "#FE00FF",
                "Am": "#45B3E0",
                "Rookie": "#FF2000",
                "Default": "#C5C5C5"
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
    'kia': ('KIA', '#05141F'),
    'nissan': ('NIS', '#C3002F'),
    'hyundai': ('HYU', '#002C5F'),
    'pontiac': ('PON', '#C41E3A'),
    'renault': ('REN', '#FFD200'),
    'subaru': ('SUB', '#003C7D'),
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
TIMING = Timing()
UI_CONFIG = UIConfig()
FILE_CONFIG = FileConfig()
TELEMETRY_CONFIG = TelemetryConfig()


def _parse_point_size(font_size_value: Any) -> float:
    """Convert a '9pt' style value into a numeric point size."""
    if isinstance(font_size_value, (int, float)):
        return float(font_size_value)
    if isinstance(font_size_value, str):
        normalized = font_size_value.strip().lower().removesuffix("pt")
        try:
            return float(normalized)
        except ValueError:
            return 0.0
    return 0.0


def get_column_width_scale(font_size_name: str) -> float:
    """Scale column widths to track the selected UI font size."""
    medium_sizes = UI_CONFIG.FONT_SIZES["Medium"]
    current_sizes = UI_CONFIG.FONT_SIZES.get(font_size_name, medium_sizes)

    medium_pt = max(
        _parse_point_size(medium_sizes.get("header")),
        _parse_point_size(medium_sizes.get("data")),
    )
    current_pt = max(
        _parse_point_size(current_sizes.get("header")),
        _parse_point_size(current_sizes.get("data")),
    )

    if medium_pt <= 0 or current_pt <= 0:
        return 1.0

    return current_pt / medium_pt


def get_scaled_column_widths(col_def: ColumnDef, font_size_name: str) -> tuple[int, Optional[int]]:
    """Return font-scaled min/max widths for a column definition."""
    scale = get_column_width_scale(font_size_name)
    min_width = max(col_def.min_width, round(col_def.min_width * scale))

    if col_def.max_width is None:
        return min_width, None

    max_width = max(min_width, round(col_def.max_width * scale))
    return min_width, max_width
