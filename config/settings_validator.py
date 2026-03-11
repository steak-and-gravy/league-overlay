"""Settings validation and type coercion.

This module handles validation and type coercion of settings data loaded from JSON.
It ensures that settings values are of the correct type and within valid ranges,
providing graceful fallbacks to defaults when invalid data is encountered.

Defaults are extracted from the AppSettings dataclass to ensure a single source of truth.
"""

from dataclasses import fields, MISSING
from typing import Optional, Any, List, Dict
from config.constants import TELEMETRY_CONFIG
from config.logging_config import get_logger

logger = get_logger(__name__)


class SettingsValidator:
    """Validates and coerces settings data from JSON.

    This class handles type coercion (e.g., "500" string -> 500 int),
    range validation (e.g., clamping opacity to 0.1-1.0), and enum
    validation (e.g., ensuring font_size is one of valid values).

    All validation errors are logged but don't crash the application.
    Invalid values are replaced with defaults extracted from the AppSettings dataclass.
    """

    def __init__(self):
        """Initialize validator with defaults extracted from AppSettings dataclass."""
        # Import here to avoid circular dependency
        from config.settings import AppSettings

        # Extract defaults from AppSettings dataclass fields
        self.defaults = {}
        for field in fields(AppSettings):
            if field.default is not MISSING:
                self.defaults[field.name] = field.default
            elif field.default_factory is not MISSING:
                self.defaults[field.name] = field.default_factory()
            else:
                self.defaults[field.name] = None

        # Special handling for division_colors default (from UI_CONFIG)
        # This gets set in AppSettings.__post_init__, not in the field default
        if 'division_colors' in self.defaults and self.defaults['division_colors'] is None:
            from config.constants import UI_CONFIG
            self.defaults['division_colors'] = UI_CONFIG.DEFAULT_COLORS.copy()

    def validate_and_coerce(self, data: dict) -> dict:
        """Validate and coerce all fields from raw JSON data.

        This method processes each field from the JSON data, performing
        type coercion, range validation, and providing defaults for
        missing or invalid values.

        Args:
            data: Raw dictionary from JSON

        Returns:
            Dictionary with validated and type-coerced values ready for
            AppSettings construction
        """
        validated = {}

        # String fields (optional)
        validated['league_config'] = self.coerce_string(
            data.get('league_config'),
            default=self.defaults['league_config'],
            field_name='league_config'
        )

        # List fields
        validated['recent_local_configs'] = self.coerce_string_list(
            data.get('recent_local_configs'),
            default=self.defaults['recent_local_configs'],
            field_name='recent_local_configs'
        )

        # Integer fields (window position and dimensions)
        validated['x'] = self.coerce_int(
            data.get('x'),
            default=self.defaults['x'],
            min_val=-10000,  # Allow off-screen positioning
            max_val=10000,
            field_name='x'
        )
        validated['y'] = self.coerce_int(
            data.get('y'),
            default=self.defaults['y'],
            min_val=-10000,
            max_val=10000,
            field_name='y'
        )
        validated['width'] = self.coerce_int(
            data.get('width'),
            default=self.defaults['width'],
            min_val=200,
            max_val=2000,
            field_name='width'
        )
        validated['height'] = self.coerce_int(
            data.get('height'),
            default=self.defaults['height'],
            min_val=200,
            max_val=2000,
            field_name='height'
        )

        # Float fields
        validated['opacity'] = self.coerce_float(
            data.get('opacity'),
            default=self.defaults['opacity'],
            min_val=0.1,
            max_val=1.0,
            field_name='opacity'
        )
        validated['refresh_rate'] = self.coerce_float(
            data.get('refresh_rate'),
            default=self.defaults['refresh_rate'],
            min_val=TELEMETRY_CONFIG.MIN_REFRESH_RATE,
            max_val=TELEMETRY_CONFIG.MAX_REFRESH_RATE,
            field_name='refresh_rate'
        )
        validated['highlight'] = self.coerce_float(
            data.get('highlight'),
            default=self.defaults['highlight'],
            min_val=0.0,
            max_val=1.0,
            field_name='highlight'
        )

        # Boolean fields
        validated['hide_headers'] = self.coerce_bool(
            data.get('hide_headers'),
            default=self.defaults['hide_headers'],
            field_name='hide_headers'
        )
        validated['center_drivers'] = self.coerce_bool(
            data.get('center_drivers'),
            default=self.defaults['center_drivers'],
            field_name='center_drivers'
        )
        validated['bold_drivers'] = self.coerce_bool(
            data.get('bold_drivers'),
            default=self.defaults['bold_drivers'],
            field_name='bold_drivers'
        )
        validated['show_gap'] = self.coerce_bool(
            data.get('show_gap'),
            default=self.defaults['show_gap'],
            field_name='show_gap'
        )
        validated['show_division_gap'] = self.coerce_bool(
            data.get('show_division_gap'),
            default=self.defaults['show_division_gap'],
            field_name='show_division_gap'
        )
        validated['show_interval'] = self.coerce_bool(
            data.get('show_interval'),
            default=self.defaults['show_interval'],
            field_name='show_interval'
        )
        validated['show_division_interval'] = self.coerce_bool(
            data.get('show_division_interval'),
            default=self.defaults['show_division_interval'],
            field_name='show_division_interval'
        )
        validated['show_last_lap'] = self.coerce_bool(
            data.get('show_last_lap'),
            default=self.defaults['show_last_lap'],
            field_name='show_last_lap'
        )
        validated['show_delta'] = self.coerce_bool(
            data.get('show_delta'),
            default=self.defaults['show_delta'],
            field_name='show_delta'
        )
        validated['show_best_lap'] = self.coerce_bool(
            data.get('show_best_lap'),
            default=self.defaults['show_best_lap'],
            field_name='show_best_lap'
        )
        validated['show_positions_gained'] = self.coerce_bool(
            data.get('show_positions_gained'),
            default=self.defaults['show_positions_gained'],
            field_name='show_positions_gained'
        )
        validated['show_rating'] = self.coerce_bool(
            data.get('show_rating'),
            default=self.defaults['show_rating'],
            field_name='show_rating'
        )
        validated['show_pit_lap'] = self.coerce_bool(
            data.get('show_pit_lap'),
            default=self.defaults['show_pit_lap'],
            field_name='show_pit_lap'
        )
        validated['show_footer'] = self.coerce_bool(
            data.get('show_footer'),
            default=self.defaults['show_footer'],
            field_name='show_footer'
        )
        validated['show_broadcast_header'] = self.coerce_bool(
            data.get('show_broadcast_header'),
            default=self.defaults['show_broadcast_header'],
            field_name='show_broadcast_header'
        )
        validated['broadcast_roll_enabled'] = self.coerce_bool(
            data.get('broadcast_roll_enabled'),
            default=self.defaults['broadcast_roll_enabled'],
            field_name='broadcast_roll_enabled'
        )
        validated['broadcast_roll_rows'] = self.coerce_int(
            data.get('broadcast_roll_rows'),
            default=self.defaults['broadcast_roll_rows'],
            min_val=1,
            max_val=20,
            field_name='broadcast_roll_rows'
        )
        validated['broadcast_roll_interval_seconds'] = self.coerce_int(
            data.get('broadcast_roll_interval_seconds'),
            default=self.defaults['broadcast_roll_interval_seconds'],
            min_val=1,
            max_val=60,
            field_name='broadcast_roll_interval_seconds'
        )

        # Enum fields (limited valid values)
        validated['font_size'] = self.coerce_enum(
            data.get('font_size'),
            valid_values=["Small", "Medium", "Large", "Extra Large"],
            default=self.defaults['font_size'],
            field_name='font_size'
        )
        validated['row_color_style'] = self.coerce_enum(
            data.get('row_color_style'),
            valid_values=["Default", "Alternate", "Outline", "Dark"],
            default=self.defaults['row_color_style'],
            field_name='row_color_style'
        )
        validated['log_level'] = self.coerce_enum(
            data.get('log_level'),
            valid_values=["DEBUG", "INFO", "WARNING", "ERROR"],
            default=self.defaults['log_level'],
            field_name='log_level'
        )

        # Dict field (division colors)
        validated['division_colors'] = self.coerce_division_colors(
            data.get('division_colors'),
            field_name='division_colors'
        )

        # Color fields (performance indicator colors)
        validated['faster_color'] = self.coerce_color(
            data.get('faster_color'),
            default=self.defaults['faster_color'],
            field_name='faster_color'
        )
        validated['slower_color'] = self.coerce_color(
            data.get('slower_color'),
            default=self.defaults['slower_color'],
            field_name='slower_color'
        )

        return validated

    def coerce_string(self, value: Any, default: Optional[str], field_name: str) -> Optional[str]:
        """Coerce value to string or None.

        Args:
            value: Raw value from JSON
            default: Default value if coercion fails
            field_name: Name of field (for logging)

        Returns:
            String value or None
        """
        if value is None:
            return default
        if isinstance(value, str):
            return value
        logger.warning(f"Field '{field_name}' has invalid type {type(value).__name__}, using default '{default}'")
        return default

    def coerce_string_list(self, value: Any, default: List[str], field_name: str) -> List[str]:
        """Coerce value to list of strings.

        Args:
            value: Raw value from JSON
            default: Default value if coercion fails
            field_name: Name of field (for logging)

        Returns:
            List of strings
        """
        if value is None:
            return default

        if not isinstance(value, list):
            logger.warning(
                f"Field '{field_name}' has invalid type {type(value).__name__}, using default"
            )
            return default

        # Validate that all items are strings
        validated_list = []
        for item in value:
            if isinstance(item, str):
                validated_list.append(item)
            else:
                logger.warning(
                    f"Field '{field_name}' contains non-string item {item} (type {type(item).__name__}), skipping"
                )

        return validated_list

    def coerce_int(self, value: Any, default: int, min_val: int, max_val: int, field_name: str) -> int:
        """Coerce value to integer within range.

        Handles string-to-int conversion (e.g., "500" -> 500) and
        clamping to valid range.

        Args:
            value: Raw value from JSON
            default: Default value if coercion fails
            min_val: Minimum valid value (inclusive)
            max_val: Maximum valid value (inclusive)
            field_name: Name of field (for logging)

        Returns:
            Integer value clamped to [min_val, max_val]
        """
        if value is None:
            return default

        try:
            # Try to convert to int (handles strings like "500")
            int_val = int(value)

            # Clamp to range
            if int_val < min_val or int_val > max_val:
                logger.warning(
                    f"Field '{field_name}' value {int_val} out of range [{min_val}, {max_val}], "
                    f"clamping to valid range"
                )
                return max(min_val, min(max_val, int_val))

            return int_val

        except (TypeError, ValueError):
            logger.warning(
                f"Field '{field_name}' has invalid value '{value}' (type {type(value).__name__}), "
                f"using default {default}"
            )
            return default

    def coerce_float(self, value: Any, default: float, min_val: float, max_val: float, field_name: str) -> float:
        """Coerce value to float within range.

        Handles string-to-float conversion (e.g., "0.9" -> 0.9) and
        clamping to valid range.

        Args:
            value: Raw value from JSON
            default: Default value if coercion fails
            min_val: Minimum valid value (inclusive)
            max_val: Maximum valid value (inclusive)
            field_name: Name of field (for logging)

        Returns:
            Float value clamped to [min_val, max_val]
        """
        if value is None:
            return default

        try:
            # Try to convert to float (handles strings like "0.9")
            float_val = float(value)

            # Clamp to range
            if float_val < min_val or float_val > max_val:
                logger.warning(
                    f"Field '{field_name}' value {float_val} out of range [{min_val}, {max_val}], "
                    f"clamping to valid range"
                )
                return max(min_val, min(max_val, float_val))

            return float_val

        except (TypeError, ValueError):
            logger.warning(
                f"Field '{field_name}' has invalid value '{value}' (type {type(value).__name__}), "
                f"using default {default}"
            )
            return default

    def coerce_bool(self, value: Any, default: bool, field_name: str) -> bool:
        """Coerce value to boolean.

        Handles various representations:
        - Boolean: True/False
        - String: "true"/"false", "yes"/"no", "on"/"off", "1"/"0"
        - Numeric: 1/0, non-zero is True

        Args:
            value: Raw value from JSON
            default: Default value if coercion fails
            field_name: Name of field (for logging)

        Returns:
            Boolean value
        """
        if value is None:
            return default

        # Handle boolean values
        if isinstance(value, bool):
            return value

        # Handle string representations
        if isinstance(value, str):
            lower_val = value.lower()
            if lower_val in ['true', '1', 'yes', 'on']:
                return True
            if lower_val in ['false', '0', 'no', 'off']:
                return False

        # Handle numeric representations
        if isinstance(value, (int, float)):
            return bool(value)

        logger.warning(
            f"Field '{field_name}' has invalid value '{value}' (type {type(value).__name__}), "
            f"using default {default}"
        )
        return default

    def coerce_enum(self, value: Any, valid_values: List[str], default: str, field_name: str) -> str:
        """Coerce value to one of the valid enum values.

        Args:
            value: Raw value from JSON
            valid_values: List of valid string values
            default: Default value if coercion fails
            field_name: Name of field (for logging)

        Returns:
            String value from valid_values
        """
        if value is None:
            return default

        if not isinstance(value, str):
            logger.warning(
                f"Field '{field_name}' has invalid type {type(value).__name__}, "
                f"using default '{default}'"
            )
            return default

        if value not in valid_values:
            logger.warning(
                f"Field '{field_name}' has invalid value '{value}', "
                f"must be one of {valid_values}, using default '{default}'"
            )
            return default

        return value

    def coerce_division_colors(self, value: Any, field_name: str) -> Dict[str, str]:
        """Coerce division colors dict, validating hex color format.

        Ensures all required divisions have valid hex colors.
        Invalid colors are replaced with defaults.

        Args:
            value: Raw value from JSON
            field_name: Name of field (for logging)

        Returns:
            Dictionary mapping division names to hex color strings
        """
        if value is None:
            return self.defaults['division_colors'].copy()

        if not isinstance(value, dict):
            logger.warning(
                f"Field '{field_name}' has invalid type {type(value).__name__}, using defaults"
            )
            return self.defaults['division_colors'].copy()

        # Validate each color value
        validated_colors = {}
        for division, color in value.items():
            if not isinstance(division, str):
                logger.warning(f"Division name '{division}' is not a string, skipping")
                continue

            if not isinstance(color, str):
                logger.warning(f"Color for division '{division}' is not a string, using default")
                validated_colors[division] = self.defaults['division_colors'].get(division, '#FFFFFF')
                continue

            # Validate hex color format (#RRGGBB or #RRGGBBAA)
            if not self._is_valid_hex_color(color):
                logger.warning(
                    f"Color '{color}' for division '{division}' is not valid hex format, using default"
                )
                validated_colors[division] = self.defaults['division_colors'].get(division, '#FFFFFF')
                continue

            validated_colors[division] = color

        # Ensure all required divisions exist
        for division in ['Pro', 'ProAm', 'Am', 'Rookie']:
            if division not in validated_colors:
                validated_colors[division] = self.defaults['division_colors'][division]

        return validated_colors

    def coerce_color(self, value: Any, default: str, field_name: str) -> str:
        """Coerce value to valid hex color string.

        Args:
            value: Raw value from JSON
            default: Default hex color to use if invalid
            field_name: Name of field (for logging)

        Returns:
            Validated hex color string (#RRGGBB or #RRGGBBAA)
        """
        if value is None:
            return default

        if not isinstance(value, str):
            logger.warning(
                f"Field '{field_name}' has invalid type {type(value).__name__}, using default {default}"
            )
            return default

        # Validate hex color format
        if not self._is_valid_hex_color(value):
            logger.warning(
                f"Field '{field_name}' has invalid color format '{value}', using default {default}"
            )
            return default

        return value

    def _is_valid_hex_color(self, color: str) -> bool:
        """Check if string is a valid hex color format.

        Args:
            color: Color string to validate

        Returns:
            True if valid hex color (#RRGGBB or #RRGGBBAA)
        """
        if not color.startswith('#'):
            return False

        if len(color) not in [7, 9]:  # #RRGGBB or #RRGGBBAA
            return False

        # Check if all characters after # are valid hex digits
        try:
            int(color[1:], 16)
            return True
        except ValueError:
            return False
