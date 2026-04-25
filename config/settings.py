"""Application settings management."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List

from .constants import UI_CONFIG, FILE_CONFIG, TELEMETRY_CONFIG, TIMING, DEFAULT_COLUMN_ORDER
from .logging_config import get_logger
from .settings_validator import SettingsValidator

logger = get_logger(__name__)


@dataclass
class AppSettings:
    """Application settings with defaults and type safety."""

    # Window position and size
    x: int = 100
    y: int = 100
    width: int = 320
    height: int = 350

    # Appearance
    opacity: float = 0.8
    font_size: str = "Slim Large"
    row_color_style: str = "Banding"
    highlight: float = 0.25

    # Behavior
    refresh_rate: float = 1.0
    hide_headers: bool = False
    pit_stop_indicator: bool = True
    bold_drivers: bool = True
    show_gap: bool = False  # Show Gap to overall leader column
    show_division_gap: bool = False  # Show Gap to division leader column (C-Gap)
    show_interval: bool = True  # Show Interval to car ahead (overall) column
    show_division_interval: bool = False  # Show Interval to car ahead in division column (C-Int)
    show_last_lap: bool = False
    show_delta: bool = False
    show_recent_lap_flash: bool = True
    show_best_lap: bool = False
    show_positions_gained: bool = True
    show_car_manufacturer: bool = False  # Show car manufacturer badge column
    show_rating: bool = False  # Combined iRating + Safety Rating column
    show_car_number: bool = True  # Show car number column
    show_pit_lap: bool = False  # Combined Last Pit + Out Lap column
    show_footer: bool = False  # Show footer with track temp, incidents, and SoF
    log_level: str = "INFO"
    show_broadcast_header: bool = False  # Show broadcast-style header with logo/session info
    broadcast_roll_enabled: bool = False  # Lock top rows and roll lower standings in broadcast mode
    broadcast_roll_rows: int = TIMING.BROADCAST_ROLL_ROWS  # Number of rows in the rotating standings window
    broadcast_roll_interval_seconds: int = TIMING.BROADCAST_ROLL_INTERVAL_SECONDS  # Seconds between rolling page advances
    local_website_enabled: bool = False  # Serve the overlay to this machine and trusted local-network devices
    local_website_port: int = 8765  # Local browser-source port for the web overlay

    # Performance indicator colors
    faster_color: str = "#00FF00"  # Green - for faster lap times and positions gained
    slower_color: str = "#FF2F18"  # Warm red - for slower lap times and positions lost

    # Configuration files
    league_config: Optional[str] = None
    recent_local_configs: List[str] = field(default_factory=list)

    # Column display order (list of column IDs)
    column_order: List[str] = field(default_factory=lambda: list(DEFAULT_COLUMN_ORDER))

    # Division colors (loaded from config)
    division_colors: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """Initialize default division colors if not provided."""
        if self.division_colors is None:
            self.division_colors = UI_CONFIG.DEFAULT_COLORS.copy()


class SettingsManager:
    """Manages application settings persistence, validation, and loading."""

    def __init__(self, settings_file: str = FILE_CONFIG.SETTINGS_FILE):
        """Initialize settings manager.

        Args:
            settings_file: Path to the settings JSON file
        """
        self.settings_file = settings_file
        self.validator = SettingsValidator()

    def load(self) -> AppSettings:
        """Load settings from file with comprehensive validation.

        This method loads settings from JSON, validates and coerces each field
        using SettingsValidator, and returns a fully validated AppSettings
        instance. Invalid values are replaced with sensible defaults.

        Returns:
            AppSettings instance with loaded or default values
        """
        if not os.path.exists(self.settings_file):
            logger.info(f"Settings file {self.settings_file} not found, using defaults")
            return AppSettings()

        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)

            logger.info(f"Settings loaded from {self.settings_file}")

            # Auto-migrate legacy show_division + show_gap/show_interval to split columns
            # Legacy: show_division controlled scope for both Gap and Interval
            # New: show_division_gap and show_division_interval are separate column toggles
            #
            # Migration preserves visual state:
            # - show_division=True meant columns were division-scoped → map to C-Gap/C-Int, disable overall
            # - show_division=False meant columns were overall-scoped → keep Gap/Int, don't enable C-Gap/C-Int
            if 'show_division' in data:
                old_show_division = data.pop('show_division')
                old_show_gap = data.get('show_gap', False)
                old_show_interval = data.get('show_interval', True)

                if old_show_division:
                    # Division mode was on: old columns were division-scoped
                    if 'show_division_gap' not in data:
                        data['show_division_gap'] = old_show_gap
                    if 'show_division_interval' not in data:
                        data['show_division_interval'] = old_show_interval
                    # Disable overall columns to preserve 2-column visual state
                    data.setdefault('show_gap', False)
                    data.setdefault('show_interval', False)
                    # Override the old values that are already in data
                    if old_show_gap:
                        data['show_gap'] = False
                    if old_show_interval:
                        data['show_interval'] = False
                    logger.info(f"Migrated show_division=True: C-Gap={data.get('show_division_gap')}, C-Int={data.get('show_division_interval')}, Gap=False, Int=False")
                else:
                    # Division mode was off: old columns were overall-scoped
                    if 'show_division_gap' not in data:
                        data['show_division_gap'] = False
                    if 'show_division_interval' not in data:
                        data['show_division_interval'] = False
                    logger.info(f"Migrated show_division=False: Gap={old_show_gap}, Int={old_show_interval}, C-Gap=False, C-Int=False")

            # Validate and coerce all fields using validator
            validated_dict = self.validator.validate_and_coerce(data)

            # Create AppSettings with validated data
            settings = AppSettings(**validated_dict)

            logger.info("Settings validation completed successfully")
            return settings

        except json.JSONDecodeError as e:
            logger.warning(f"Settings file is corrupted JSON: {e}, using defaults", exc_info=True)
            return AppSettings()
        except Exception as e:
            logger.error(f"Unexpected settings error: {e}, using defaults", exc_info=True)
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        """Save settings to file.

        Args:
            settings: AppSettings instance to save
        """
        try:
            # Convert dataclass to dict
            settings_dict = {
                'league_config': settings.league_config,
                'recent_local_configs': settings.recent_local_configs,
                'division_colors': settings.division_colors,
                'x': settings.x,
                'y': settings.y,
                'width': settings.width,
                'height': settings.height,
                'opacity': settings.opacity,
                'refresh_rate': settings.refresh_rate,
                'highlight': settings.highlight,
                'hide_headers': settings.hide_headers,
                'pit_stop_indicator': settings.pit_stop_indicator,
                'bold_drivers': settings.bold_drivers,
                'show_gap': settings.show_gap,
                'show_division_gap': settings.show_division_gap,
                'show_interval': settings.show_interval,
                'show_division_interval': settings.show_division_interval,
                'show_last_lap': settings.show_last_lap,
                'show_delta': settings.show_delta,
                'show_recent_lap_flash': settings.show_recent_lap_flash,
                'show_best_lap': settings.show_best_lap,
                'show_positions_gained': settings.show_positions_gained,
                'show_car_manufacturer': settings.show_car_manufacturer,
                'show_rating': settings.show_rating,
                'show_car_number': settings.show_car_number,
                'show_pit_lap': settings.show_pit_lap,
                'show_footer': settings.show_footer,
                'show_broadcast_header': settings.show_broadcast_header,
                'broadcast_roll_enabled': settings.broadcast_roll_enabled,
                'broadcast_roll_rows': settings.broadcast_roll_rows,
                'broadcast_roll_interval_seconds': settings.broadcast_roll_interval_seconds,
                'local_website_enabled': settings.local_website_enabled,
                'local_website_port': settings.local_website_port,
                'font_size': settings.font_size,
                'row_color_style': settings.row_color_style,
                'log_level': settings.log_level,
                'faster_color': settings.faster_color,
                'slower_color': settings.slower_color,
                'column_order': settings.column_order
            }

            with open(self.settings_file, 'w') as f:
                json.dump(settings_dict, f, indent=2)

            logger.debug(f"Settings saved successfully to {self.settings_file}")

        except IOError as e:
            logger.error(f"Failed to save settings: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected save error: {e}", exc_info=True)

    def validate(self, settings: AppSettings) -> AppSettings:
        """Validate an existing AppSettings instance.

        This method is provided for backward compatibility with tests
        and manual validation. During normal load() operations, validation
        happens automatically via SettingsValidator.

        Args:
            settings: AppSettings instance to validate

        Returns:
            New AppSettings instance with validated values
        """
        # Convert to dict
        settings_dict = {
            'league_config': settings.league_config,
            'recent_local_configs': settings.recent_local_configs,
            'division_colors': settings.division_colors,
            'x': settings.x,
            'y': settings.y,
            'width': settings.width,
            'height': settings.height,
            'opacity': settings.opacity,
            'refresh_rate': settings.refresh_rate,
            'highlight': settings.highlight,
            'hide_headers': settings.hide_headers,
            'pit_stop_indicator': settings.pit_stop_indicator,
            'bold_drivers': settings.bold_drivers,
            'show_gap': settings.show_gap,
            'show_division_gap': settings.show_division_gap,
            'show_interval': settings.show_interval,
            'show_division_interval': settings.show_division_interval,
            'show_last_lap': settings.show_last_lap,
            'show_delta': settings.show_delta,
            'show_recent_lap_flash': settings.show_recent_lap_flash,
            'show_best_lap': settings.show_best_lap,
            'show_positions_gained': settings.show_positions_gained,
            'show_car_manufacturer': settings.show_car_manufacturer,
            'show_rating': settings.show_rating,
            'show_car_number': settings.show_car_number,
            'show_pit_lap': settings.show_pit_lap,
            'show_footer': settings.show_footer,
            'show_broadcast_header': settings.show_broadcast_header,
            'broadcast_roll_enabled': settings.broadcast_roll_enabled,
            'broadcast_roll_rows': settings.broadcast_roll_rows,
            'broadcast_roll_interval_seconds': settings.broadcast_roll_interval_seconds,
            'local_website_enabled': settings.local_website_enabled,
            'local_website_port': settings.local_website_port,
            'font_size': settings.font_size,
            'row_color_style': settings.row_color_style,
            'log_level': settings.log_level,
            'faster_color': settings.faster_color,
            'slower_color': settings.slower_color,
            'column_order': settings.column_order
        }
        validated_dict = self.validator.validate_and_coerce(settings_dict)

        # Return new AppSettings with validated values
        return AppSettings(**validated_dict)
