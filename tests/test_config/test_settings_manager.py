"""Tests for config.settings module.

Tests cover:
- AppSettings dataclass defaults
- Settings loading (valid, invalid, missing files)
- Settings saving
- Settings validation (opacity, refresh rate, font size, color style, dimensions)
- Edge cases (malformed JSON, missing fields, invalid types)
"""

import pytest
import json
import os
from config.constants import UI_CONFIG
from config.settings import AppSettings, SettingsManager


class TestAppSettingsDefaults:
    """Test cases for AppSettings default values."""

    def test_default_window_position(self):
        """Test default window position."""
        settings = AppSettings()
        assert settings.x == 100
        assert settings.y == 100

    def test_default_window_size(self):
        """Test default window size."""
        settings = AppSettings()
        assert settings.width == 320
        assert settings.height == 350

    def test_default_appearance(self):
        """Test default appearance settings."""
        settings = AppSettings()
        assert settings.opacity == 0.8
        assert settings.font_size == "Large"
        assert settings.row_color_style == "Default"
        assert settings.highlight_player_border is False

    def test_default_behavior(self):
        """Test default behavior settings."""
        settings = AppSettings()
        assert settings.refresh_rate == 1.0  # Default from AppSettings
        assert settings.hide_headers is False
        assert settings.pit_stop_indicator is True
        assert settings.bold_drivers is True
        assert settings.show_recent_lap_flash is True
        assert settings.always_use_driver_name is False
        assert settings.show_car_manufacturer is True
        assert settings.broadcast_roll_rows == 5
        assert settings.broadcast_roll_interval_seconds == 5
        assert settings.local_website_enabled is False
        assert settings.local_website_port == 8765
        assert settings.local_website_scale == "Large"
        assert settings.auto_assign_unknown_driver_class is None

    def test_default_config_files(self):
        """Test default config file paths."""
        settings = AppSettings()
        assert settings.league_config is None
        assert settings.recent_local_configs == []

    def test_default_division_colors(self):
        """Test default division colors are initialized."""
        settings = AppSettings()
        assert settings.division_colors is not None
        assert isinstance(settings.division_colors, dict)
        assert settings.division_colors["Default"] == "#C5C5C5"
        assert settings.league_color_overrides == {}


class TestLoadSettings:
    """Test cases for loading settings from file."""

    def test_load_missing_file_returns_defaults(self, tmp_path):
        """Test loading when settings file doesn't exist returns defaults."""
        settings_file = tmp_path / "nonexistent.config"
        manager = SettingsManager(str(settings_file))

        settings = manager.load()

        assert isinstance(settings, AppSettings)
        assert settings.opacity == 0.8  # Default value

    def test_load_valid_settings(self, tmp_path):
        """Test loading valid settings file."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'x': 200,
            'y': 150,
            'width': 500,
            'height': 600,
            'opacity': 0.8,
            'font_size': 'Large',
            'row_color_style': 'Alternate',
            'refresh_rate': 1.5,
            'hide_headers': True,
            'pit_stop_indicator': False,
            'bold_drivers': False,
            'league_config': '/path/to/config.json',
            'recent_local_configs': ['/path/to/file1.json', '/path/to/file2.json']
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.x == 200
        assert settings.y == 150
        assert settings.width == 500
        assert settings.height == 600
        assert settings.opacity == 0.8
        assert settings.font_size == 'Large'
        assert settings.row_color_style == 'Alternate'
        assert settings.refresh_rate == 1.5
        assert settings.hide_headers is True
        assert settings.pit_stop_indicator is False
        assert settings.bold_drivers is False
        assert settings.league_config == '/path/to/config.json'
        assert settings.recent_local_configs == ['/path/to/file1.json', '/path/to/file2.json']

    def test_load_legacy_refresh_rate_below_new_min_clamps_up(self, tmp_path):
        """Test older persisted refresh rates are clamped to the new minimum."""
        settings_file = tmp_path / "settings.config"

        with open(settings_file, 'w') as f:
            json.dump({'refresh_rate': 0.25}, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.refresh_rate == 0.5

    def test_load_partial_settings(self, tmp_path):
        """Test loading file with only some settings (others use defaults)."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'opacity': 0.9,
            'font_size': 'Small'
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Loaded values
        assert settings.opacity == 0.9
        assert settings.font_size == 'Small'

        # Default values for unspecified fields
        assert settings.x == 100
        assert settings.width == 320
        assert settings.refresh_rate == 1.0  # Default from AppSettings
        assert settings.hide_headers is False
        assert settings.auto_assign_unknown_driver_class is None

    def test_load_unknown_driver_class(self, tmp_path):
        settings_file = tmp_path / "settings.config"
        with open(settings_file, 'w') as f:
            json.dump({'auto_assign_unknown_driver_class': 'Am'}, f)

        settings = SettingsManager(str(settings_file)).load()

        assert settings.auto_assign_unknown_driver_class == 'Am'

    def test_load_invalid_json(self, tmp_path):
        """Test loading malformed JSON returns defaults."""
        settings_file = tmp_path / "settings.config"

        with open(settings_file, 'w') as f:
            f.write("{invalid json}")

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should return defaults
        assert isinstance(settings, AppSettings)
        assert settings.opacity == 0.8

    def test_load_unknown_fields_ignored(self, tmp_path):
        """Test loading settings with unknown fields ignores them."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'opacity': 0.7,
            'unknown_field': 'should be ignored',
            'another_unknown': 123
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.opacity == 0.7
        # Should not have unknown fields
        assert not hasattr(settings, 'unknown_field')

    def test_load_with_type_error(self, tmp_path):
        """Test loading with wrong data types returns defaults."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'opacity': 'not a number',  # Should be float
            'hide_headers': 'not a boolean'  # Should be bool
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should return defaults due to type error
        assert isinstance(settings, AppSettings)


class TestSaveSettings:
    """Test cases for saving settings to file."""

    def test_save_creates_file(self, tmp_path):
        """Test saving creates settings file."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(
            x=300,
            y=400,
            opacity=0.75,
            broadcast_roll_rows=7,
            broadcast_roll_interval_seconds=9,
            local_website_enabled=True,
            local_website_port=8766,
            local_website_scale="Large",
        )

        manager.save(settings)

        assert os.path.exists(settings_file)

        with open(settings_file, 'r') as f:
            data = json.load(f)
            assert data['x'] == 300
            assert data['y'] == 400
            assert data['opacity'] == 0.75
            assert data['broadcast_roll_rows'] == 7
            assert data['broadcast_roll_interval_seconds'] == 9
            assert data['local_website_enabled'] is True
            assert data['local_website_port'] == 8766
            assert data['local_website_scale'] == "Large"
            assert 'auto_assign_unknown_driver_class' not in data

    def test_save_all_fields(self, tmp_path):
        """Test saving all settings fields."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(
            x=200,
            y=150,
            width=500,
            height=600,
            opacity=0.8,
            font_size='Large',
            row_color_style='Alternate',
            highlight_player_border=True,
            refresh_rate=1.5,
            hide_headers=True,
            pit_stop_indicator=False,
            bold_drivers=False,
            show_recent_lap_flash=False,
            always_use_driver_name=True,
            local_website_enabled=True,
            local_website_port=8766,
            local_website_scale="Extra Large",
            league_config='/path/to/config.json',
            division_colors={'Pro': '#FF0000'},
            league_color_overrides={'official:League': {'Pro': '#00FF00'}},
            auto_assign_unknown_driver_class='Rookie',
        )

        manager.save(settings)

        with open(settings_file, 'r') as f:
            data = json.load(f)
            assert data['x'] == 200
            assert data['opacity'] == 0.8
            assert data['font_size'] == 'Large'
            assert data['highlight_player_border'] is True
            assert data['pit_stop_indicator'] is False
            assert data['show_recent_lap_flash'] is False
            assert data['always_use_driver_name'] is True
            assert data['local_website_enabled'] is True
            assert data['local_website_port'] == 8766
            assert data['local_website_scale'] == "Extra Large"
            assert data['division_colors'] == {'Pro': '#FF0000'}
            assert data['league_color_overrides'] == {'official:League': {'Pro': '#00FF00'}}
            assert data['auto_assign_unknown_driver_class'] == 'Rookie'

    def test_load_legacy_center_drivers_config_uses_pit_stop_indicator_default(self, tmp_path):
        """Legacy configs should ignore removed center_drivers and default Pit Stop Indicator on."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'opacity': 0.8,
            'center_drivers': True,
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.pit_stop_indicator is True
        assert not hasattr(settings, 'center_drivers')

    def test_save_overwrites_existing(self, tmp_path):
        """Test saving overwrites existing settings file."""
        settings_file = tmp_path / "settings.config"

        # Create initial settings
        initial_data = {'opacity': 0.5}
        with open(settings_file, 'w') as f:
            json.dump(initial_data, f)

        manager = SettingsManager(str(settings_file))
        settings = AppSettings(opacity=0.9)

        manager.save(settings)

        # Verify overwritten
        with open(settings_file, 'r') as f:
            data = json.load(f)
            assert data['opacity'] == 0.9

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test save and load roundtrip preserves settings."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        original = AppSettings(
            x=250,
            y=300,
            opacity=0.65,
            font_size='Large',
            hide_headers=True,
            show_recent_lap_flash=False,
            always_use_driver_name=True,
            highlight_player_border=True,
            local_website_enabled=True,
            local_website_port=8766,
            local_website_scale="Compact",
        )

        manager.save(original)
        loaded = manager.load()

        assert loaded.x == original.x
        assert loaded.y == original.y
        assert loaded.opacity == original.opacity
        assert loaded.font_size == original.font_size
        assert loaded.hide_headers == original.hide_headers
        assert loaded.show_recent_lap_flash == original.show_recent_lap_flash
        assert loaded.always_use_driver_name == original.always_use_driver_name
        assert loaded.highlight_player_border == original.highlight_player_border
        assert loaded.local_website_enabled == original.local_website_enabled
        assert loaded.local_website_port == original.local_website_port
        assert loaded.local_website_scale == original.local_website_scale


class TestValidateSettings:
    """Test cases for settings validation."""

    def test_validate_preserves_league_color_overrides(self, tmp_path):
        """Test manual validation preserves per-league color overrides."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(
            league_color_overrides={'official:League': {'Pro': '#123456'}}
        )
        validated = manager.validate(settings)

        assert validated.league_color_overrides == {'official:League': {'Pro': '#123456'}}

    def test_validate_opacity_clamped_low(self, tmp_path):
        """Test opacity clamped to minimum 0.0."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(opacity=-0.5)
        validated = manager.validate(settings)

        assert validated.opacity == 0.0

    def test_validate_zero_opacity_allowed(self, tmp_path):
        """Test opacity can be fully transparent."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(opacity=0.0)
        validated = manager.validate(settings)

        assert validated.opacity == 0.0

    def test_validate_opacity_clamped_high(self, tmp_path):
        """Test opacity clamped to maximum 1.0."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(opacity=2.5)
        validated = manager.validate(settings)

        assert validated.opacity == 1.0

    def test_validate_opacity_within_range(self, tmp_path):
        """Test opacity within valid range is unchanged."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(opacity=0.75)
        validated = manager.validate(settings)

        assert validated.opacity == 0.75

    def test_validate_refresh_rate_clamped_low(self, tmp_path):
        """Test refresh rate clamped to minimum."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(refresh_rate=0.1)
        validated = manager.validate(settings)

        # Should be clamped to MIN_REFRESH_RATE (0.5)
        assert validated.refresh_rate >= 0.5

    def test_validate_refresh_rate_clamped_high(self, tmp_path):
        """Test refresh rate clamped to maximum."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(refresh_rate=10.0)
        validated = manager.validate(settings)

        # Should be clamped to MAX_REFRESH_RATE (3.0)
        assert validated.refresh_rate <= 3.0

    def test_validate_invalid_font_size(self, tmp_path):
        """Test invalid font size resets to the default."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(font_size='InvalidSize')
        validated = manager.validate(settings)

        assert validated.font_size == 'Large'

    def test_removed_slim_large_font_size_resets_to_default(self, tmp_path):
        """Test old Slim Large configs naturally fall back to the Large default."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(font_size='Slim Large')
        validated = manager.validate(settings)

        assert validated.font_size == 'Large'

    def test_validate_valid_font_sizes(self, tmp_path):
        """Test all valid font sizes pass validation."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        valid_sizes = ["Small", "Medium", "Large", "Extra Large"]

        for size in valid_sizes:
            settings = AppSettings(font_size=size)
            validated = manager.validate(settings)
            assert validated.font_size == size

    def test_font_size_density_settings(self):
        """Test desktop font presets keep the intended row spacing."""
        medium = UI_CONFIG.FONT_SIZES["Medium"]
        large = UI_CONFIG.FONT_SIZES["Large"]
        extra_large = UI_CONFIG.FONT_SIZES["Extra Large"]

        assert medium["data"] == "9pt"
        assert medium["spacing"] == 2
        assert large["data"] == "10pt"
        assert large["spacing"] == 2
        assert extra_large["data"] == "10.5pt"
        assert extra_large["spacing"] == 1

    def test_validate_local_website_scale(self, tmp_path):
        """Test browser-source scale uses the allowed preset names."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        assert manager.validate(AppSettings(local_website_scale="Medium")).local_website_scale == "Medium"
        assert manager.validate(AppSettings(local_website_scale="TooBig")).local_website_scale == "Large"

    def test_validate_invalid_row_color_style(self, tmp_path):
        """Test invalid row color style resets to the default."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(row_color_style='InvalidStyle')
        validated = manager.validate(settings)

        assert validated.row_color_style == 'Default'

    def test_validate_valid_row_color_styles(self, tmp_path):
        """Test all valid row color styles pass validation."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        valid_styles = ["Default", "Dark", "Alternate", "Outline"]

        for style in valid_styles:
            settings = AppSettings(row_color_style=style)
            validated = manager.validate(settings)
            assert validated.row_color_style == style

    def test_validate_width_clamped_low(self, tmp_path):
        """Test width clamped to minimum 200."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(width=50)
        validated = manager.validate(settings)

        assert validated.width == 200

    def test_validate_width_clamped_high(self, tmp_path):
        """Test width clamped to maximum 2000."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(width=5000)
        validated = manager.validate(settings)

        assert validated.width == 2000

    def test_validate_height_clamped_low(self, tmp_path):
        """Test height clamped to minimum 200."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(height=100)
        validated = manager.validate(settings)

        assert validated.height == 200

    def test_validate_height_clamped_high(self, tmp_path):
        """Test height clamped to maximum 2000."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(height=3000)
        validated = manager.validate(settings)

        assert validated.height == 2000


class TestLoadWithValidation:
    """Test that loading automatically validates settings."""

    def test_load_validates_opacity(self, tmp_path):
        """Test loaded settings have opacity validated."""
        settings_file = tmp_path / "settings.config"
        settings_data = {'opacity': 5.0}  # Invalid, too high

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should be clamped to 1.0
        assert settings.opacity == 1.0

    def test_load_validates_font_size(self, tmp_path):
        """Test loaded settings have font size validated."""
        settings_file = tmp_path / "settings.config"
        settings_data = {'font_size': 'Huge'}  # Invalid

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should reset to default
        assert settings.font_size == 'Large'

    def test_load_resets_removed_slim_large_font_size(self, tmp_path):
        """Test old Slim Large persisted configs reset to the Large default."""
        settings_file = tmp_path / "settings.config"
        settings_data = {'font_size': 'Slim Large'}

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.font_size == 'Large'

    def test_load_validates_dimensions(self, tmp_path):
        """Test loaded settings have dimensions validated."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'width': 50,  # Too small
            'height': 5000  # Too large
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.width == 200  # Clamped to min
        assert settings.height == 2000  # Clamped to max


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_settings_file(self, tmp_path):
        """Test loading empty settings file."""
        settings_file = tmp_path / "settings.config"

        with open(settings_file, 'w') as f:
            f.write('')

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should return defaults
        assert isinstance(settings, AppSettings)

    def test_settings_file_with_null_values(self, tmp_path):
        """Test handling null values in settings."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'opacity': None,
            'font_size': None
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should handle gracefully
        assert isinstance(settings, AppSettings)

    def test_division_colors_none_initializes_defaults(self):
        """Test division_colors=None initializes to defaults."""
        settings = AppSettings(division_colors=None)

        # Should be initialized by __post_init__
        assert settings.division_colors is not None
        assert isinstance(settings.division_colors, dict)

    def test_zero_refresh_rate(self, tmp_path):
        """Test zero refresh rate gets clamped."""
        settings_file = tmp_path / "settings.config"
        manager = SettingsManager(str(settings_file))

        settings = AppSettings(refresh_rate=0.0)
        validated = manager.validate(settings)

        assert validated.refresh_rate >= 0.5

    def test_recent_local_configs_validation(self, tmp_path):
        """Test recent_local_configs list validation."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'recent_local_configs': ['/path/to/file1.json', '/path/to/file2.json', '/path/to/file3.json']
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        assert settings.recent_local_configs == ['/path/to/file1.json', '/path/to/file2.json', '/path/to/file3.json']

    def test_recent_local_configs_invalid_type(self, tmp_path):
        """Test recent_local_configs with invalid type uses default."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'recent_local_configs': 'not a list'
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should default to empty list
        assert settings.recent_local_configs == []

    def test_recent_local_configs_mixed_types(self, tmp_path):
        """Test recent_local_configs with mixed types filters non-strings."""
        settings_file = tmp_path / "settings.config"
        settings_data = {
            'recent_local_configs': ['/path/to/file1.json', 123, '/path/to/file2.json', None, 'valid.json']
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = SettingsManager(str(settings_file))
        settings = manager.load()

        # Should only include string values
        assert settings.recent_local_configs == ['/path/to/file1.json', '/path/to/file2.json', 'valid.json']
