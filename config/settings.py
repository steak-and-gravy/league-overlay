"""Application settings management."""

import json
import os
from dataclasses import dataclass
from typing import Optional, Dict

from .constants import UI_CONFIG, FILE_CONFIG, TELEMETRY_CONFIG
from .logging_config import get_logger

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
    opacity: float = 0.5
    font_size: str = "Medium"
    row_color_style: str = "Default"

    # Behavior
    refresh_rate: float = 2.0
    hide_headers: bool = False
    center_drivers: bool = False
    bold_drivers: bool = True

    # Configuration files
    league_config: Optional[str] = None

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

    def load(self) -> AppSettings:
        """Load settings from file, return defaults if not found or invalid.

        Returns:
            AppSettings instance with loaded or default values
        """
        if not os.path.exists(self.settings_file):
            return AppSettings()

        try:
            with open(self.settings_file, 'r') as f:
                data = json.load(f)

            # Extract known settings fields, ignoring unknown fields
            settings_dict = {}
            for field in AppSettings.__dataclass_fields__:
                if field in data:
                    settings_dict[field] = data[field]

            logger.info(f"Settings loaded successfully from {self.settings_file}")
            return self.validate(AppSettings(**settings_dict))

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning(f"Settings load error: {e}, using defaults", exc_info=True)
            print(f"Settings load error: {e}, using defaults")
            return AppSettings()
        except Exception as e:
            logger.error(f"Unexpected settings error: {e}, using defaults", exc_info=True)
            print(f"Unexpected settings error: {e}, using defaults")
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
                'division_colors': settings.division_colors,
                'x': settings.x,
                'y': settings.y,
                'width': settings.width,
                'height': settings.height,
                'opacity': settings.opacity,
                'refresh_rate': settings.refresh_rate,
                'hide_headers': settings.hide_headers,
                'center_drivers': settings.center_drivers,
                'bold_drivers': settings.bold_drivers,
                'font_size': settings.font_size,
                'row_color_style': settings.row_color_style
            }

            with open(self.settings_file, 'w') as f:
                json.dump(settings_dict, f, indent=2)

            logger.debug(f"Settings saved successfully to {self.settings_file}")

        except IOError as e:
            logger.error(f"Failed to save settings: {e}", exc_info=True)
            print(f"Failed to save settings: {e}")
        except Exception as e:
            logger.error(f"Unexpected save error: {e}", exc_info=True)
            print(f"Unexpected save error: {e}")

    def validate(self, settings: AppSettings) -> AppSettings:
        """Validate and clamp settings to valid ranges.

        Args:
            settings: AppSettings instance to validate

        Returns:
            Validated AppSettings instance with clamped values
        """
        # Clamp opacity to valid range [0.1, 1.0]
        settings.opacity = max(0.1, min(1.0, settings.opacity))

        # Clamp refresh rate to valid range [0.25, 5.0]
        settings.refresh_rate = max(
            TELEMETRY_CONFIG.MIN_REFRESH_RATE,
            min(TELEMETRY_CONFIG.MAX_REFRESH_RATE, settings.refresh_rate)
        )

        # Validate font size
        valid_font_sizes = ["Small", "Medium", "Large", "Extra Large"]
        if settings.font_size not in valid_font_sizes:
            settings.font_size = "Medium"

        # Validate row color style
        valid_color_styles = ["Default", "Alternate", "Outline"]
        if settings.row_color_style not in valid_color_styles:
            settings.row_color_style = "Default"

        # Clamp window dimensions to reasonable values
        settings.width = max(200, min(2000, settings.width))
        settings.height = max(200, min(2000, settings.height))

        return settings
