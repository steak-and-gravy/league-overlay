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
        assert result['Pro'] == validator.defaults['division_colors']['Pro']  # Default from UI_CONFIG
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
        assert result['Pro'] == validator.defaults['division_colors']['Pro']  # Default from UI_CONFIG

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
        assert result['Pro'] == validator.defaults['division_colors']['Pro']  # Default from UI_CONFIG

    def test_non_dict_returns_defaults(self):
        """Test non-dict type returns all defaults."""
        validator = SettingsValidator()
        result = validator.coerce_division_colors("red", field_name='division_colors')
        assert result == validator.defaults['division_colors']

    def test_none_returns_defaults(self):
        """Test None returns all defaults."""
        validator = SettingsValidator()
        result = validator.coerce_division_colors(None, field_name='division_colors')
        assert result == validator.defaults['division_colors']

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
        assert result['ProAm'] == validator.defaults['division_colors']['ProAm']

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
        assert result['Pro'] == validator.defaults['division_colors']['Pro']  # Default from UI_CONFIG

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
            'pit_required': False,
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
        assert result['refresh_rate'] == 1.0  # Default from AppSettings

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
        assert result['opacity'] == 0.8  # Default
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
        assert result['opacity'] == 0.8
        assert result['refresh_rate'] == 1.0  # Default from AppSettings

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
            'show_division_interval': True,
            'show_last_lap': True,
            'show_delta': True,
            'font_size': 'Large'
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 500
        assert result['opacity'] == 0.8
        assert result['show_division_gap'] is True
        assert result['show_division_interval'] is True
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
            'show_division_interval': True,
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
        assert result['show_division_interval'] is True
        assert result['show_positions_gained'] is True
        assert result['show_best_lap'] is True
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True
        assert result['font_size'] == 'Large'


class TestPerformanceIndicatorColors:
    """Test cases for faster_color and slower_color settings."""

    def test_faster_color_default(self):
        """Test faster_color defaults to green (#00FF00)."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == "#00FF00"

    def test_slower_color_default(self):
        """Test slower_color defaults to red (#FF0000)."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['slower_color'] == "#FF0000"

    def test_faster_color_valid_hex(self):
        """Test faster_color accepts valid hex color."""
        validator = SettingsValidator()
        data = {'faster_color': '#FF8C00'}
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == '#FF8C00'

    def test_slower_color_valid_hex(self):
        """Test slower_color accepts valid hex color."""
        validator = SettingsValidator()
        data = {'slower_color': '#0000FF'}
        result = validator.validate_and_coerce(data)
        assert result['slower_color'] == '#0000FF'

    def test_faster_color_invalid_hex_returns_default(self):
        """Test invalid faster_color returns default green."""
        validator = SettingsValidator()
        data = {'faster_color': 'not-a-color'}
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == "#00FF00"

    def test_slower_color_invalid_hex_returns_default(self):
        """Test invalid slower_color returns default red."""
        validator = SettingsValidator()
        data = {'slower_color': 'invalid'}
        result = validator.validate_and_coerce(data)
        assert result['slower_color'] == "#FF0000"

    def test_faster_color_missing_hash_returns_default(self):
        """Test faster_color without # returns default."""
        validator = SettingsValidator()
        data = {'faster_color': 'FF8C00'}
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == "#00FF00"

    def test_slower_color_wrong_length_returns_default(self):
        """Test slower_color with wrong length returns default."""
        validator = SettingsValidator()
        data = {'slower_color': '#FF00'}
        result = validator.validate_and_coerce(data)
        assert result['slower_color'] == "#FF0000"

    def test_faster_color_invalid_type_returns_default(self):
        """Test faster_color with invalid type returns default."""
        validator = SettingsValidator()
        data = {'faster_color': 12345}
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == "#00FF00"

    def test_slower_color_none_returns_default(self):
        """Test slower_color None returns default."""
        validator = SettingsValidator()
        data = {'slower_color': None}
        result = validator.validate_and_coerce(data)
        assert result['slower_color'] == "#FF0000"

    def test_both_colors_custom(self):
        """Test both performance colors can be customized together."""
        validator = SettingsValidator()
        data = {
            'faster_color': '#0FC436',
            'slower_color': '#FFA500'
        }
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == '#0FC436'
        assert result['slower_color'] == '#FFA500'

    def test_colors_with_alpha_channel(self):
        """Test colors support RGBA format (#RRGGBBAA)."""
        validator = SettingsValidator()
        data = {
            'faster_color': '#00FF00FF',
            'slower_color': '#FF0000FF'
        }
        result = validator.validate_and_coerce(data)
        assert result['faster_color'] == '#00FF00FF'
        assert result['slower_color'] == '#FF0000FF'

    def test_complete_settings_with_colors(self):
        """Test complete settings including performance colors."""
        validator = SettingsValidator()
        data = {
            'width': 500,
            'opacity': 0.8,
            'show_best_lap': True,
            'show_positions_gained': True,
            'faster_color': '#0000FF',
            'slower_color': '#FFFF00',
            'font_size': 'Large'
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 500
        assert result['opacity'] == 0.8
        assert result['show_best_lap'] is True
        assert result['show_positions_gained'] is True
        assert result['faster_color'] == '#0000FF'
        assert result['slower_color'] == '#FFFF00'
        assert result['font_size'] == 'Large'


class TestNewDriverInfoColumns:
    """Test cases for new driver info column settings (iRating, SR, Last Pit, Out Lap, Car)."""

    def test_show_car_number_default_true(self):
        """Test show_car_number defaults to True."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_car_number'] is True

    def test_show_car_number_false(self):
        """Test show_car_number can be set to False."""
        validator = SettingsValidator()
        data = {'show_car_number': False}
        result = validator.validate_and_coerce(data)
        assert result['show_car_number'] is False

    def test_show_rating_default_false(self):
        """Test show_rating defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is False

    def test_show_rating_default_false(self):
        """Test show_rating defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is False

    def test_show_pit_lap_default_false(self):
        """Test show_pit_lap defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is False

    def test_show_pit_lap_default_false(self):
        """Test show_pit_lap defaults to False."""
        validator = SettingsValidator()
        data = {}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is False

    def test_show_rating_true(self):
        """Test show_rating can be set to True."""
        validator = SettingsValidator()
        data = {'show_rating': True}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is True

    def test_show_rating_true(self):
        """Test show_rating can be set to True."""
        validator = SettingsValidator()
        data = {'show_rating': True}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is True

    def test_show_pit_lap_true(self):
        """Test show_pit_lap can be set to True."""
        validator = SettingsValidator()
        data = {'show_pit_lap': True}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is True

    def test_show_pit_lap_true(self):
        """Test show_pit_lap can be set to True."""
        validator = SettingsValidator()
        data = {'show_pit_lap': True}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is True

    def test_show_rating_string_coercion(self):
        """Test show_rating string coercion."""
        validator = SettingsValidator()
        data = {'show_rating': "true"}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is True

    def test_show_rating_string_coercion(self):
        """Test show_rating string coercion."""
        validator = SettingsValidator()
        data = {'show_rating': "false"}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is False

    def test_show_pit_lap_numeric_coercion(self):
        """Test show_pit_lap numeric coercion."""
        validator = SettingsValidator()
        data = {'show_pit_lap': 1}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is True

    def test_show_pit_lap_numeric_coercion(self):
        """Test show_pit_lap numeric coercion."""
        validator = SettingsValidator()
        data = {'show_pit_lap': 0}
        result = validator.validate_and_coerce(data)
        assert result['show_pit_lap'] is False

    def test_pit_required_defaults_true(self):
        """Test pit_required defaults to True."""
        validator = SettingsValidator()
        result = validator.validate_and_coerce({})
        assert result['pit_required'] is True

    def test_pit_required_false(self):
        """Test pit_required can be disabled."""
        validator = SettingsValidator()
        result = validator.validate_and_coerce({'pit_required': False})
        assert result['pit_required'] is False

    def test_all_four_new_settings_together(self):
        """Test all four new driver info settings can be set together."""
        validator = SettingsValidator()
        data = {
            'show_rating': True,
            'show_rating': True,
            'show_pit_lap': True,
            'show_pit_lap': True,
            'pit_required': False,
        }
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is True
        assert result['show_rating'] is True
        assert result['show_pit_lap'] is True
        assert result['show_pit_lap'] is True
        assert result['pit_required'] is False

    def test_show_rating_invalid_returns_default(self):
        """Test invalid show_rating value returns default."""
        validator = SettingsValidator()
        data = {'show_rating': 'maybe'}
        result = validator.validate_and_coerce(data)
        assert result['show_rating'] is False

    def test_complete_settings_with_all_nine_optional_columns(self):
        """Test complete settings including all 9 optional columns (4 existing + 5 new).

        This test verifies backward compatibility - settings files can be loaded
        with any combination of old and new column settings.
        """
        validator = SettingsValidator()
        data = {
            'width': 600,
            'opacity': 0.9,
            # Existing optional columns
            'show_positions_gained': True,
            'show_best_lap': True,
            'show_last_lap': True,
            'show_delta': True,
            # New optional columns
            'show_rating': True,
            'show_rating': True,
            'show_pit_lap': True,
            'show_pit_lap': True,
            'show_car_manufacturer': True,
            'font_size': 'Large'
        }
        result = validator.validate_and_coerce(data)
        assert result['width'] == 600
        assert result['opacity'] == 0.9
        # Verify existing columns
        assert result['show_positions_gained'] is True
        assert result['show_best_lap'] is True
        assert result['show_last_lap'] is True
        assert result['show_delta'] is True
        # Verify new columns
        assert result['show_rating'] is True
        assert result['show_rating'] is True
        assert result['show_pit_lap'] is True
        assert result['show_pit_lap'] is True
        assert result['font_size'] == 'Large'

    def test_backward_compatibility_old_config_without_new_columns(self):
        """Test backward compatibility - old config files without new columns.

        This test simulates loading a config file that was created before the
        new columns were added. All new settings should default to False.
        This is the CRITICAL test that would have caught the original bug.
        """
        validator = SettingsValidator()
        # Simulate an old config file with only the original settings
        data = {
            'width': 500,
            'opacity': 0.8,
            'show_positions_gained': True,
            'show_best_lap': False,
            'show_last_lap': True,
            'show_delta': False
            # NOTE: New columns (show_rating, show_division_gap, show_division_interval) are NOT in this config
        }
        result = validator.validate_and_coerce(data)

        # Verify old settings are preserved
        assert result['width'] == 500
        assert result['opacity'] == 0.8
        assert result['show_positions_gained'] is True
        assert result['show_best_lap'] is False
        assert result['show_last_lap'] is True
        assert result['show_delta'] is False

        # CRITICAL: Verify new settings get their intended defaults
        # Without the fix in settings_validator.py, these would be missing
        # from the validated dict, causing KeyError when constructing AppSettings
        assert result['show_rating'] is False
        assert result['show_car_number'] is True
        assert result['show_pit_lap'] is False
        assert result['pit_required'] is True
        assert result['show_division_gap'] is False
        assert result['show_division_interval'] is False

    def test_partial_new_columns_in_config(self):
        """Test loading config with only some of the new columns.

        Simulates a scenario where a user manually edited their config
        and only added some of the new settings.
        """
        validator = SettingsValidator()
        data = {
            'show_rating': True,
            'show_rating': True,
            # show_pit_lap, show_pit_lap not present
        }
        result = validator.validate_and_coerce(data)

        # Present settings should be True
        assert result['show_rating'] is True
        assert result['show_rating'] is True

        # Missing settings should default to False
        assert result['show_pit_lap'] is False
        assert result['show_pit_lap'] is False


class TestBroadcastRollingSettings:
    """Tests for broadcast rolling settings coercion and defaults."""

    def test_broadcast_roll_settings_default_when_missing(self):
        validator = SettingsValidator()
        result = validator.validate_and_coerce({})
        assert result['broadcast_roll_rows'] == 5
        assert result['broadcast_roll_interval_seconds'] == 5

    def test_broadcast_roll_settings_clamped_to_range(self):
        validator = SettingsValidator()
        result = validator.validate_and_coerce({
            'broadcast_roll_rows': 0,
            'broadcast_roll_interval_seconds': 99,
        })
        assert result['broadcast_roll_rows'] == 1
        assert result['broadcast_roll_interval_seconds'] == 60
