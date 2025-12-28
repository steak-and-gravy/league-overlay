"""Tests for config.settings_validator module.

Tests cover:
- Integer coercion and range validation
- Float coercion and range validation
- Boolean coercion from various types
- Enum validation
- Division colors validation
- Hex color format validation
- Complete validation pipeline
"""

import pytest
from config.settings_validator import SettingsValidator


class TestCoerceInt:
    """Test cases for integer coercion and validation."""

    def test_coerce_string_to_int(self):
        """Test converting string to int."""
        validator = SettingsValidator()
        result = validator.coerce_int("500", default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 500

    def test_coerce_float_to_int(self):
        """Test converting float to int (truncates)."""
        validator = SettingsValidator()
        result = validator.coerce_int(500.7, default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 500

    def test_coerce_invalid_type_returns_default(self):
        """Test invalid type returns default."""
        validator = SettingsValidator()
        result = validator.coerce_int([500], default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 400

    def test_clamp_to_min(self):
        """Test value below min is clamped."""
        validator = SettingsValidator()
        result = validator.coerce_int(100, default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 200

    def test_clamp_to_max(self):
        """Test value above max is clamped."""
        validator = SettingsValidator()
        result = validator.coerce_int(3000, default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 2000

    def test_within_range_unchanged(self):
        """Test value within range is unchanged."""
        validator = SettingsValidator()
        result = validator.coerce_int(500, default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 500

    def test_none_returns_default(self):
        """Test None returns default value."""
        validator = SettingsValidator()
        result = validator.coerce_int(None, default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 400

    def test_negative_values(self):
        """Test negative values with negative min."""
        validator = SettingsValidator()
        result = validator.coerce_int(-500, default=100, min_val=-10000, max_val=10000, field_name='x')
        assert result == -500

    def test_invalid_string_returns_default(self):
        """Test non-numeric string returns default."""
        validator = SettingsValidator()
        result = validator.coerce_int("abc", default=400, min_val=200, max_val=2000, field_name='width')
        assert result == 400


class TestCoerceFloat:
    """Test cases for float coercion and validation."""

    def test_coerce_string_to_float(self):
        """Test converting string to float."""
        validator = SettingsValidator()
        result = validator.coerce_float("0.9", default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.9

    def test_coerce_int_to_float(self):
        """Test converting int to float."""
        validator = SettingsValidator()
        result = validator.coerce_float(1, default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 1.0

    def test_clamp_opacity_high(self):
        """Test opacity above 1.0 is clamped."""
        validator = SettingsValidator()
        result = validator.coerce_float(1.5, default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 1.0

    def test_clamp_opacity_low(self):
        """Test opacity below 0.1 is clamped."""
        validator = SettingsValidator()
        result = validator.coerce_float(-0.5, default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.1

    def test_within_range_unchanged(self):
        """Test value within range is unchanged."""
        validator = SettingsValidator()
        result = validator.coerce_float(0.75, default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.75

    def test_none_returns_default(self):
        """Test None returns default value."""
        validator = SettingsValidator()
        result = validator.coerce_float(None, default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.5

    def test_invalid_string_returns_default(self):
        """Test non-numeric string returns default."""
        validator = SettingsValidator()
        result = validator.coerce_float("abc", default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.5

    def test_invalid_type_returns_default(self):
        """Test invalid type returns default."""
        validator = SettingsValidator()
        result = validator.coerce_float([0.9], default=0.5, min_val=0.1, max_val=1.0, field_name='opacity')
        assert result == 0.5


class TestCoerceBool:
    """Test cases for boolean coercion."""

    def test_string_true_variants(self):
        """Test various string representations of True."""
        validator = SettingsValidator()
        assert validator.coerce_bool("true", default=False, field_name='flag') is True
        assert validator.coerce_bool("True", default=False, field_name='flag') is True
        assert validator.coerce_bool("TRUE", default=False, field_name='flag') is True
        assert validator.coerce_bool("yes", default=False, field_name='flag') is True
        assert validator.coerce_bool("1", default=False, field_name='flag') is True
        assert validator.coerce_bool("on", default=False, field_name='flag') is True

    def test_string_false_variants(self):
        """Test various string representations of False."""
        validator = SettingsValidator()
        assert validator.coerce_bool("false", default=True, field_name='flag') is False
        assert validator.coerce_bool("False", default=True, field_name='flag') is False
        assert validator.coerce_bool("FALSE", default=True, field_name='flag') is False
        assert validator.coerce_bool("no", default=True, field_name='flag') is False
        assert validator.coerce_bool("0", default=True, field_name='flag') is False
        assert validator.coerce_bool("off", default=True, field_name='flag') is False

    def test_numeric_true(self):
        """Test non-zero numbers evaluate to True."""
        validator = SettingsValidator()
        assert validator.coerce_bool(1, default=False, field_name='flag') is True
        assert validator.coerce_bool(-5, default=False, field_name='flag') is True
        assert validator.coerce_bool(99, default=False, field_name='flag') is True

    def test_numeric_false(self):
        """Test zero evaluates to False."""
        validator = SettingsValidator()
        assert validator.coerce_bool(0, default=True, field_name='flag') is False

    def test_bool_type_unchanged(self):
        """Test boolean type is passed through."""
        validator = SettingsValidator()
        assert validator.coerce_bool(True, default=False, field_name='flag') is True
        assert validator.coerce_bool(False, default=True, field_name='flag') is False

    def test_invalid_string_returns_default(self):
        """Test invalid string returns default."""
        validator = SettingsValidator()
        assert validator.coerce_bool("maybe", default=False, field_name='flag') is False
        assert validator.coerce_bool("yep", default=True, field_name='flag') is True

    def test_invalid_type_returns_default(self):
        """Test invalid type returns default."""
        validator = SettingsValidator()
        assert validator.coerce_bool({}, default=False, field_name='flag') is False
        assert validator.coerce_bool([], default=True, field_name='flag') is True

    def test_none_returns_default(self):
        """Test None returns default."""
        validator = SettingsValidator()
        assert validator.coerce_bool(None, default=True, field_name='flag') is True


class TestCoerceEnum:
    """Test cases for enum validation."""

    def test_valid_value(self):
        """Test valid enum value is accepted."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum("Medium", valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"

    def test_invalid_value_returns_default(self):
        """Test invalid value returns default."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum("Medum", valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"

    def test_case_sensitive(self):
        """Test enum validation is case-sensitive."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum("medium", valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"

    def test_wrong_type_returns_default(self):
        """Test non-string type returns default."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum(123, valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"

    def test_none_returns_default(self):
        """Test None returns default."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum(None, valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"

    def test_empty_string_returns_default(self):
        """Test empty string returns default."""
        validator = SettingsValidator()
        valid_values = ["Small", "Medium", "Large", "Extra Large"]
        result = validator.coerce_enum("", valid_values, default="Medium", field_name='font_size')
        assert result == "Medium"


class TestIsValidHexColor:
    """Test cases for hex color validation."""

    def test_valid_six_digit_hex(self):
        """Test valid 6-digit hex color."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#FF0000") is True
        assert validator._is_valid_hex_color("#00FF00") is True
        assert validator._is_valid_hex_color("#0000FF") is True

    def test_valid_eight_digit_hex(self):
        """Test valid 8-digit hex color (with alpha)."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#FF0000AA") is True
        assert validator._is_valid_hex_color("#00FF00FF") is True

    def test_lowercase_hex_valid(self):
        """Test lowercase hex digits are valid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#ff0000") is True
        assert validator._is_valid_hex_color("#aabbcc") is True

    def test_mixed_case_valid(self):
        """Test mixed case hex is valid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#FfAaBb") is True

    def test_missing_hash_invalid(self):
        """Test missing # is invalid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("FF0000") is False

    def test_wrong_length_invalid(self):
        """Test wrong length is invalid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#FF00") is False
        assert validator._is_valid_hex_color("#FF00000") is False

    def test_invalid_characters(self):
        """Test non-hex characters are invalid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("#FF00GG") is False
        assert validator._is_valid_hex_color("#ZZZZZZ") is False

    def test_empty_string_invalid(self):
        """Test empty string is invalid."""
        validator = SettingsValidator()
        assert validator._is_valid_hex_color("") is False


class TestCoerceDivisionColors:
    """Test cases for division colors validation."""

    def test_valid_hex_colors_accepted(self):
        """Test valid hex colors are accepted."""
        validator = SettingsValidator()
        colors = {
            'Pro': '#FF0000',
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result == colors

    def test_invalid_hex_uses_default(self):
        """Test invalid hex color uses default."""
        validator = SettingsValidator()
        colors = {
            'Pro': '#FF00GG',  # Invalid
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result['Pro'] == '#FF0000'  # Default
        assert result['ProAm'] == '#00FF00'  # Original

    def test_missing_hash_uses_default(self):
        """Test hex without # uses default."""
        validator = SettingsValidator()
        colors = {
            'Pro': 'FF0000',  # Missing #
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result['Pro'] == '#FF0000'  # Default

    def test_wrong_length_uses_default(self):
        """Test hex with wrong length uses default."""
        validator = SettingsValidator()
        colors = {
            'Pro': '#FF00',  # Too short
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result['Pro'] == '#FF0000'  # Default

    def test_non_dict_returns_defaults(self):
        """Test non-dict type returns all defaults."""
        validator = SettingsValidator()
        result = validator.coerce_division_colors("red", field_name='division_colors')
        assert result == validator.default_division_colors

    def test_none_returns_defaults(self):
        """Test None returns all defaults."""
        validator = SettingsValidator()
        result = validator.coerce_division_colors(None, field_name='division_colors')
        assert result == validator.default_division_colors

    def test_missing_required_divisions_added(self):
        """Test missing required divisions are added."""
        validator = SettingsValidator()
        colors = {
            'Pro': '#FF0000',
            # ProAm, Am, Rookie missing
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert 'ProAm' in result
        assert 'Am' in result
        assert 'Rookie' in result
        assert result['ProAm'] == validator.default_division_colors['ProAm']

    def test_non_string_color_uses_default(self):
        """Test non-string color value uses default."""
        validator = SettingsValidator()
        colors = {
            'Pro': 123,  # Not a string
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result['Pro'] == '#FF0000'  # Default

    def test_extra_divisions_preserved(self):
        """Test extra divisions beyond the required four are preserved."""
        validator = SettingsValidator()
        colors = {
            'Pro': '#FF0000',
            'ProAm': '#00FF00',
            'Am': '#0000FF',
            'Rookie': '#FFFF00',
            'Custom': '#AABBCC'
        }
        result = validator.coerce_division_colors(colors, field_name='division_colors')
        assert result['Custom'] == '#AABBCC'


class TestValidateAndCoerce:
    """Test cases for complete validation pipeline."""

    def test_all_valid_fields(self):
        """Test all valid fields are accepted."""
        validator = SettingsValidator()
        data = {
            'x': 250,
            'y': 300,
            'width': 500,
            'height': 600,
            'opacity': 0.75,
            'refresh_rate': 1.5,
            'hide_headers': True,
            'center_drivers': False,
            'bold_drivers': True,
            'font_size': 'Large',
            'row_color_style': 'Alternate',
            'league_config': 'custom.json',
            'division_colors': {
                'Pro': '#FF0000',
                'ProAm': '#00FF00',
                'Am': '#0000FF',
                'Rookie': '#FFFF00'
            }
        }
        result = validator.validate_and_coerce(data)
        assert result['x'] == 250
        assert result['width'] == 500
        assert result['opacity'] == 0.75
        assert result['font_size'] == 'Large'

    def test_partial_fields_uses_defaults(self):
        """Test partial fields fills in defaults."""
        validator = SettingsValidator()
        data = {
            'font_size': 'Small',
            'opacity': 0.9
        }
        result = validator.validate_and_coerce(data)
        assert result['font_size'] == 'Small'
        assert result['opacity'] == 0.9
        assert result['width'] == 320  # Default
        assert result['height'] == 350  # Default
        assert result['refresh_rate'] == 2.0  # Default

    def test_all_invalid_fields_uses_defaults(self):
        """Test all invalid fields uses all defaults."""
        validator = SettingsValidator()
        data = {
            'x': 'abc',
            'width': 'invalid',
            'opacity': 'bad',
            'font_size': 'InvalidSize',
            'hide_headers': 'maybe'
        }
        result = validator.validate_and_coerce(data)
        assert result['x'] == 100  # Default
        assert result['width'] == 320  # Default
        assert result['opacity'] == 0.5  # Default
        assert result['font_size'] == 'Medium'  # Default
        assert result['hide_headers'] is False  # Default

    def test_empty_dict_uses_all_defaults(self):
        """Test empty dict uses all defaults."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['x'] == 100
        assert result['y'] == 100
        assert result['width'] == 320
        assert result['height'] == 350
        assert result['opacity'] == 0.5
        assert result['refresh_rate'] == 2.0

    def test_type_coercion_integrated(self):
        """Test type coercion works in full pipeline."""
        validator = SettingsValidator()
        data = {
            'width': "500",  # String -> int
            'opacity': "0.9",  # String -> float
            'hide_headers': "true",  # String -> bool
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 500
        assert result['opacity'] == 0.9
        assert result['hide_headers'] is True

    def test_range_clamping_integrated(self):
        """Test range clamping works in full pipeline."""
        validator = SettingsValidator()
        data = {
            'width': 5000,  # > max
            'opacity': 1.5,  # > max
            'refresh_rate': 0.1  # < min
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 2000  # Clamped
        assert result['opacity'] == 1.0  # Clamped
        assert result['refresh_rate'] == 0.25  # Clamped to MIN_REFRESH_RATE


class TestCoerceString:
    """Test cases for string coercion."""

    def test_string_unchanged(self):
        """Test string value is unchanged."""
        validator = SettingsValidator()
        result = validator.coerce_string("test.json", default=None, field_name='config')
        assert result == "test.json"

    def test_none_returns_default(self):
        """Test None returns default."""
        validator = SettingsValidator()
        result = validator.coerce_string(None, default="default.json", field_name='config')
        assert result == "default.json"

    def test_none_default_returns_none(self):
        """Test None with None default returns None."""
        validator = SettingsValidator()
        result = validator.coerce_string(None, default=None, field_name='config')
        assert result is None

    def test_non_string_returns_default(self):
        """Test non-string type returns default."""
        validator = SettingsValidator()
        result = validator.coerce_string(123, default="default.json", field_name='config')
        assert result == "default.json"


class TestNewDisplaySettings:
    """Test cases for show_last_lap and show_delta boolean settings."""

    def test_show_last_lap_default_false(self):
        """Test show_last_lap defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is False

    def test_show_delta_default_false(self):
        """Test show_delta defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_delta'] is False

    def test_show_last_lap_true(self):
        """Test show_last_lap can be set to True."""
        validator = SettingsValidator()
        data = {'show_last_lap': True}
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is True

    def test_show_delta_true(self):
        """Test show_delta can be set to True."""
        validator = SettingsValidator()
        data = {'show_delta': True}
        result = validator.validate_and_coerce(data)
        assert result['show_delta'] is True

    def test_show_last_lap_string_coercion(self):
        """Test show_last_lap string coercion."""
        validator = SettingsValidator()
        data = {'show_last_lap': "true"}
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is True

    def test_show_delta_string_coercion(self):
        """Test show_delta string coercion."""
        validator = SettingsValidator()
        data = {'show_delta': "false"}
        result = validator.validate_and_coerce(data)
        assert result['show_delta'] is False

    def test_show_last_lap_numeric_coercion(self):
        """Test show_last_lap numeric coercion."""
        validator = SettingsValidator()
        data = {'show_last_lap': 1}
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is True

    def test_show_delta_numeric_coercion(self):
        """Test show_delta numeric coercion."""
        validator = SettingsValidator()
        data = {'show_delta': 0}
        result = validator.validate_and_coerce(data)
        assert result['show_delta'] is False

    def test_both_settings_together(self):
        """Test both show_last_lap and show_delta can be set together."""
        validator = SettingsValidator()
        data = {
            'show_last_lap': True,
            'show_delta': True
        }
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True

    def test_show_last_lap_invalid_returns_default(self):
        """Test invalid show_last_lap value returns default."""
        validator = SettingsValidator()
        data = {'show_last_lap': 'maybe'}
        result = validator.validate_and_coerce(data)
        assert result['show_last_lap'] is False

    def test_show_delta_invalid_returns_default(self):
        """Test invalid show_delta value returns default."""
        validator = SettingsValidator()
        data = {'show_delta': [True]}
        result = validator.validate_and_coerce(data)
        assert result['show_delta'] is False

    def test_complete_settings_with_display_columns(self):
        """Test complete settings including new display columns."""
        validator = SettingsValidator()
        data = {
            'width': 500,
            'opacity': 0.8,
            'show_division_gap': True,
            'show_last_lap': True,
            'show_delta': True,
            'font_size': 'Large'
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 500
        assert result['opacity'] == 0.8
        assert result['show_division_gap'] is True
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True
        assert result['font_size'] == 'Large'


class TestNewColumnSettings:
    """Test cases for show_best_lap and show_positions_gained boolean settings."""

    def test_show_best_lap_default_false(self):
        """Test show_best_lap defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is False

    def test_show_positions_gained_default_false(self):
        """Test show_positions_gained defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is False

    def test_show_best_lap_true(self):
        """Test show_best_lap can be set to True."""
        validator = SettingsValidator()
        data = {'show_best_lap': True}
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is True

    def test_show_positions_gained_true(self):
        """Test show_positions_gained can be set to True."""
        validator = SettingsValidator()
        data = {'show_positions_gained': True}
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is True

    def test_show_best_lap_string_coercion(self):
        """Test show_best_lap string coercion."""
        validator = SettingsValidator()
        data = {'show_best_lap': "true"}
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is True

    def test_show_positions_gained_string_coercion(self):
        """Test show_positions_gained string coercion."""
        validator = SettingsValidator()
        data = {'show_positions_gained': "false"}
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is False

    def test_show_best_lap_numeric_coercion(self):
        """Test show_best_lap numeric coercion."""
        validator = SettingsValidator()
        data = {'show_best_lap': 1}
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is True

    def test_show_positions_gained_numeric_coercion(self):
        """Test show_positions_gained numeric coercion."""
        validator = SettingsValidator()
        data = {'show_positions_gained': 0}
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is False

    def test_both_new_settings_together(self):
        """Test both show_best_lap and show_positions_gained can be set together."""
        validator = SettingsValidator()
        data = {
            'show_best_lap': True,
            'show_positions_gained': True
        }
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is True
        assert result['show_positions_gained'] is True

    def test_show_best_lap_invalid_returns_default(self):
        """Test invalid show_best_lap value returns default."""
        validator = SettingsValidator()
        data = {'show_best_lap': 'maybe'}
        result = validator.validate_and_coerce(data)
        assert result['show_best_lap'] is False

    def test_show_positions_gained_invalid_returns_default(self):
        """Test invalid show_positions_gained value returns default."""
        validator = SettingsValidator()
        data = {'show_positions_gained': [True]}
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is False

    def test_all_four_column_settings_together(self):
        """Test all four optional column settings together."""
        validator = SettingsValidator()
        data = {
            'show_positions_gained': True,
            'show_best_lap': True,
            'show_last_lap': True,
            'show_delta': True
        }
        result = validator.validate_and_coerce(data)
        assert result['show_positions_gained'] is True
        assert result['show_best_lap'] is True
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True

    def test_complete_settings_with_all_columns(self):
        """Test complete settings including all optional columns."""
        validator = SettingsValidator()
        data = {
            'width': 500,
            'opacity': 0.8,
            'show_division_gap': True,
            'show_positions_gained': True,
            'show_best_lap': True,
            'show_last_lap': True,
            'show_delta': True,
            'font_size': 'Large'
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 500
        assert result['opacity'] == 0.8
        assert result['show_division_gap'] is True
        assert result['show_positions_gained'] is True
        assert result['show_best_lap'] is True
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True
        assert result['font_size'] == 'Large'
