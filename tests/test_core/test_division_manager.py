"""Tests for core.division_manager module.

Tests cover:
- Driver config loading (valid, invalid, missing files)
- Division color loading
- Driver division assignment and retrieval
- Division color retrieval
- Config saving
- Edge cases (missing IDs, name matching, etc.)
"""

import pytest
import json
import os
from core.division_manager import DivisionManager


class TestLoadDriverConfig:
    """Test cases for loading driver configuration."""

    def test_load_valid_config(self, tmp_path):
        """Test loading valid driver config file."""
        config_file = tmp_path / "divisions.json"
        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'},
                {'id': '456', 'name': 'Driver 2', 'division': 'ProAm'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert len(manager.driver_colors['drivers']) == 2
        assert manager.driver_colors['drivers'][0]['division'] == 'Pro'

    def test_load_empty_config(self, tmp_path):
        """Test loading empty config file."""
        config_file = tmp_path / "divisions.json"
        with open(config_file, 'w') as f:
            json.dump({}, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert manager.driver_colors == {'drivers': []}

    def test_load_missing_config(self, tmp_path):
        """Test loading when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert manager.driver_colors == {'drivers': []}

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON file."""
        config_file = tmp_path / "divisions.json"
        with open(config_file, 'w') as f:
            f.write("{invalid json")

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Should fall back to default
        assert manager.driver_colors == {'drivers': []}

    def test_load_config_no_drivers_key(self, tmp_path):
        """Test loading config with missing 'drivers' key."""
        config_file = tmp_path / "divisions.json"
        with open(config_file, 'w') as f:
            json.dump({'other_key': 'value'}, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert manager.driver_colors == {'drivers': []}


class TestLoadDivisionColors:
    """Test cases for loading division colors."""

    def test_load_valid_colors(self, tmp_path):
        """Test loading valid division colors."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        settings_data = {
            'division_colors': {
                'Pro': '#FF0000',
                'ProAm': '#00FF00',
                'Am': '#0000FF'
            }
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert manager.division_colors['Pro'] == '#FF0000'
        assert manager.division_colors['ProAm'] == '#00FF00'
        assert manager.division_colors['Am'] == '#0000FF'

    def test_load_missing_settings_uses_defaults(self, tmp_path):
        """Test missing settings file uses default colors."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "nonexistent.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Should have default colors
        assert 'Default' in manager.division_colors

    def test_load_invalid_settings_json(self, tmp_path):
        """Test invalid settings JSON uses defaults."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        with open(settings_file, 'w') as f:
            f.write("{invalid json")

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Should have default colors
        assert 'Default' in manager.division_colors


class TestGetDriverDivision:
    """Test cases for retrieving driver division."""

    def test_get_division_by_id(self, tmp_path):
        """Test retrieving division by user ID."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'},
                {'id': '456', 'name': 'Driver 2', 'division': 'ProAm'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        division = manager.get_driver_division(driver_info)

        assert division == 'Pro'

    def test_get_division_by_name(self, tmp_path):
        """Test retrieving division by user name when ID not available."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserName': 'Driver 1'}
        division = manager.get_driver_division(driver_info)

        assert division == 'Pro'

    def test_get_division_id_takes_precedence(self, tmp_path):
        """Test ID matching takes precedence over name."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'},
                {'name': 'Driver 1', 'division': 'Am'}  # Same name, different ID
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Match by ID
        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        division = manager.get_driver_division(driver_info)

        assert division == 'Pro'

    def test_get_division_not_found(self, tmp_path):
        """Test retrieving division for unknown driver returns None."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '999', 'UserName': 'Unknown Driver'}
        division = manager.get_driver_division(driver_info)

        assert division is None

    def test_get_division_empty_driver_info(self, tmp_path):
        """Test retrieving division with empty driver info."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        division = manager.get_driver_division({})
        assert division is None


class TestSetDriverDivision:
    """Test cases for setting driver division."""

    def test_set_new_driver_division(self, tmp_path):
        """Test adding new driver to division."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'Pro')

        # Verify it was added
        division = manager.get_driver_division(driver_info)
        assert division == 'Pro'

        # Verify it was saved to file
        assert os.path.exists(config_file)
        with open(config_file, 'r') as f:
            data = json.load(f)
            assert len(data['drivers']) == 1
            assert data['drivers'][0]['division'] == 'Pro'

    def test_update_existing_driver_division(self, tmp_path):
        """Test updating existing driver's division."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'ProAm')

        # Verify it was updated
        division = manager.get_driver_division(driver_info)
        assert division == 'ProAm'

        # Verify only one entry exists
        assert len(manager.driver_colors['drivers']) == 1

    def test_set_division_to_default_removes_driver(self, tmp_path):
        """Test setting division to 'Default' removes driver from config."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'Default')

        # Driver should be removed
        division = manager.get_driver_division(driver_info)
        assert division is None

        assert len(manager.driver_colors['drivers']) == 0

    def test_set_division_without_user_id(self, tmp_path):
        """Test setting division with only user name."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'Pro')

        # Verify it was added
        division = manager.get_driver_division(driver_info)
        assert division == 'Pro'

    def test_set_division_without_user_name(self, tmp_path):
        """Test setting division with only user ID."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserID': '123'}
        manager.set_driver_division(driver_info, 'Pro')

        # Verify it was added
        division = manager.get_driver_division(driver_info)
        assert division == 'Pro'

    def test_update_preserves_missing_fields(self, tmp_path):
        """Test updating driver preserves missing ID/name fields."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Update with partial info (only name)
        driver_info = {'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'ProAm')

        # ID should still be in the entry
        saved_driver = manager.driver_colors['drivers'][0]
        assert saved_driver['id'] == '123'
        assert saved_driver['name'] == 'Driver 1'
        assert saved_driver['division'] == 'ProAm'


class TestGetDivisionColor:
    """Test cases for retrieving division colors."""

    def test_get_existing_division_color(self, tmp_path):
        """Test getting color for existing division."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        settings_data = {
            'division_colors': {
                'Pro': '#FF0000',
                'ProAm': '#00FF00'
            }
        }

        with open(settings_file, 'w') as f:
            json.dump(settings_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        assert manager.get_division_color('Pro') == '#FF0000'
        assert manager.get_division_color('ProAm') == '#00FF00'

    def test_get_unknown_division_returns_default(self, tmp_path):
        """Test getting color for unknown division returns default."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        color = manager.get_division_color('UnknownDivision')
        # Should return default color
        assert color == manager.division_colors.get("Default", "#FFFFFF")

    def test_get_none_division_returns_default(self, tmp_path):
        """Test getting color for None division returns default."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        color = manager.get_division_color(None)
        assert color == manager.division_colors.get("Default", "#FFFFFF")


class TestSaveConfig:
    """Test cases for saving configuration."""

    def test_save_creates_file(self, tmp_path):
        """Test save creates config file."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        manager.driver_colors = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        manager.save_config()

        assert os.path.exists(config_file)

        with open(config_file, 'r') as f:
            data = json.load(f)
            assert len(data['drivers']) == 1
            assert data['drivers'][0]['division'] == 'Pro'

    def test_save_overwrites_existing(self, tmp_path):
        """Test save overwrites existing config."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        # Create initial config
        initial_data = {
            'drivers': [
                {'id': '123', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(initial_data, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Modify and save
        manager.driver_colors['drivers'].append(
            {'id': '456', 'division': 'ProAm'}
        )
        manager.save_config()

        # Verify overwritten
        with open(config_file, 'r') as f:
            data = json.load(f)
            assert len(data['drivers']) == 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_driver_info_dict(self, tmp_path):
        """Test handling empty driver info dict."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Should not crash
        division = manager.get_driver_division({})
        assert division is None

    def test_driver_with_special_characters(self, tmp_path):
        """Test driver names with special characters."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        driver_info = {'UserName': 'Drivér #1 [PRO]', 'UserID': '123'}
        manager.set_driver_division(driver_info, 'Pro')

        division = manager.get_driver_division(driver_info)
        assert division == 'Pro'

    def test_very_long_division_name(self, tmp_path):
        """Test very long division name."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        long_division = 'A' * 1000
        driver_info = {'UserID': '123'}
        manager.set_driver_division(driver_info, long_division)

        division = manager.get_driver_division(driver_info)
        assert division == long_division


class TestDivisionCaching:
    """Test cases for O(1) division lookup caching."""

    def test_cache_built_on_load(self, tmp_path):
        """Test division cache is built when config is loaded."""
        config_file = tmp_path / "divisions.json"
        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'},
                {'id': '456', 'name': 'Driver 2', 'division': 'ProAm'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Verify cache was built
        assert '123' in manager._division_cache_by_id
        assert '456' in manager._division_cache_by_id
        assert 'Driver 1' in manager._division_cache_by_name
        assert 'Driver 2' in manager._division_cache_by_name

    def test_cache_lookup_by_id(self, tmp_path):
        """Test division lookup uses cache by UserID."""
        config_file = tmp_path / "divisions.json"
        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Lookup by UserID should use cache
        driver_info = {'UserID': '123', 'UserName': 'Different Name'}
        division = manager.get_driver_division(driver_info)

        assert division == 'Pro'
        assert manager._division_cache_by_id['123'] == 'Pro'

    def test_cache_lookup_by_name_fallback(self, tmp_path):
        """Test division lookup falls back to name cache if ID not found."""
        config_file = tmp_path / "divisions.json"
        config_data = {
            'drivers': [
                {'name': 'Driver 1', 'division': 'Pro'}  # No ID
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Lookup by UserName should use name cache
        driver_info = {'UserName': 'Driver 1'}
        division = manager.get_driver_division(driver_info)

        assert division == 'Pro'
        assert manager._division_cache_by_name['Driver 1'] == 'Pro'

    def test_cache_rebuilt_after_set_division(self, tmp_path):
        """Test cache is rebuilt when driver division is changed."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Add a driver
        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'Pro')

        # Verify cache has the entry
        assert manager._division_cache_by_id['123'] == 'Pro'
        assert manager._division_cache_by_name['Driver 1'] == 'Pro'

        # Update the driver's division
        manager.set_driver_division(driver_info, 'ProAm')

        # Verify cache was rebuilt with new value
        assert manager._division_cache_by_id['123'] == 'ProAm'
        assert manager._division_cache_by_name['Driver 1'] == 'ProAm'

    def test_cache_rebuilt_after_removing_driver(self, tmp_path):
        """Test cache is rebuilt when driver is removed."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Add a driver
        driver_info = {'UserID': '123', 'UserName': 'Driver 1'}
        manager.set_driver_division(driver_info, 'Pro')

        # Verify cache has the entry
        assert '123' in manager._division_cache_by_id

        # Remove the driver (set to Default)
        manager.set_driver_division(driver_info, 'Default')

        # Verify cache was rebuilt without the entry
        assert '123' not in manager._division_cache_by_id
        assert 'Driver 1' not in manager._division_cache_by_name

    def test_cache_handles_drivers_without_division(self, tmp_path):
        """Test cache ignores drivers without division assigned."""
        config_file = tmp_path / "divisions.json"
        config_data = {
            'drivers': [
                {'id': '123', 'name': 'Driver 1'},  # No division
                {'id': '456', 'name': 'Driver 2', 'division': 'Pro'}
            ]
        }

        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        settings_file = tmp_path / "settings.json"
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file)
        )

        # Cache should only have driver with division
        assert '123' not in manager._division_cache_by_id
        assert '456' in manager._division_cache_by_id
        assert manager._division_cache_by_id['456'] == 'Pro'
