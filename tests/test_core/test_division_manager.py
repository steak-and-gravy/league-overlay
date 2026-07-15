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
import threading
from unittest.mock import Mock, patch

from config.official_leagues import OfficialLeague
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

    def test_league_file_colors_override_app_defaults(self, tmp_path):
        """Test league-file division colors layer over app defaults."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"
        with open(config_file, 'w') as f:
            json.dump({
                'drivers': [],
                'division_colors': {
                    'Pro': '#111111',
                    'ProAm': 'not-a-color',
                }
            }, f)

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file),
            app_default_colors={
                'Pro': '#AAAAAA',
                'ProAm': '#BBBBBB',
                'Am': '#CCCCCC',
                'Rookie': '#DDDDDD',
                'Default': '#EEEEEE',
            },
        )

        assert manager.division_colors['Pro'] == '#111111'
        assert manager.division_colors['ProAm'] == '#BBBBBB'
        assert manager.division_color_status == "League defaults"

    def test_user_override_wins_over_league_file_colors(self, tmp_path):
        """Test per-league user overrides are the highest color layer."""
        config_file = tmp_path / "divisions.json"
        settings_file = tmp_path / "settings.json"
        with open(config_file, 'w') as f:
            json.dump({
                'drivers': [],
                'division_colors': {'Pro': '#111111'}
            }, f)

        source_key = os.path.abspath(str(config_file))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(settings_file),
            app_default_colors={'Pro': '#AAAAAA'},
            league_color_overrides={source_key: {'Pro': '#222222'}},
        )

        assert manager.division_colors['Pro'] == '#222222'
        assert manager.division_color_status == "Custom"

    def test_normalize_league_source_expands_local_paths(self, tmp_path, monkeypatch):
        """Test local league override keys use absolute expanded paths."""
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        monkeypatch.setenv("HOME", str(home_dir))

        normalized = DivisionManager.normalize_league_source("~/league.json")

        assert normalized == os.path.abspath(os.path.join(str(home_dir), "league.json"))
        assert DivisionManager.normalize_league_source(" official:Test League ") == "official:Test League"
        assert DivisionManager.normalize_league_source("official:") == ""


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

    def test_unknown_driver_uses_configured_fallback_without_writing_league_file(self, tmp_path):
        config_file = tmp_path / "divisions.json"
        config_file.write_text(json.dumps({
            'drivers': [{'id': '123', 'name': 'Known', 'division': 'Pro'}]
        }))
        original_contents = config_file.read_text()

        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='Am',
        )

        assert manager.get_driver_division({'UserID': '123', 'UserName': 'Known'}) == 'Pro'
        assert manager.get_driver_division({'UserID': '999', 'UserName': 'Unknown'}) == 'Am'
        assert manager.get_driver_division_key({'UserID': '999', 'UserName': 'Unknown'}) == 'Am'
        assert manager.get_driver_color({'UserID': '999', 'UserName': 'Unknown'}) == manager.division_colors['Am']
        assert config_file.read_text() == original_contents

    def test_unknown_driver_fallback_rejects_invalid_class_and_can_be_disabled(self, tmp_path):
        manager = DivisionManager(
            config_file=str(tmp_path / "divisions.json"),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='Invalid',
        )
        unknown = {'UserID': '999', 'UserName': 'Unknown'}

        assert manager.get_driver_division(unknown) is None
        manager.set_unknown_driver_class('Rookie')
        assert manager.get_driver_division(unknown) == 'Rookie'
        manager.set_unknown_driver_class(None)
        assert manager.get_driver_division(unknown) is None

    def test_unknown_driver_can_be_persisted_once_to_local_league_file(self, tmp_path):
        config_file = tmp_path / "divisions.json"
        config_file.write_text(json.dumps({'drivers': []}))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='ProAm',
            persist_unknown_driver_assignments=True,
        )
        unknown = {'UserID': '789', 'UserName': 'New Driver'}

        assert manager.get_driver_division(unknown) == 'ProAm'
        assert manager.get_driver_division(unknown) == 'ProAm'

        saved = json.loads(config_file.read_text())
        assert saved['drivers'] == [
            {'division': 'ProAm', 'id': '789', 'name': 'New Driver'}
        ]

    def test_official_unknown_driver_updates_cache_until_next_refresh(self, tmp_path):
        cache_file = tmp_path / "cache_test_league.json"
        league = OfficialLeague(
            name="Test League",
            path="test/league.json",
            title="Test League",
            description="Test",
            logo=None,
            cache_file=str(cache_file),
        )
        remote_data = {
            'drivers': [{'id': '123', 'name': 'Known Driver', 'division': 'Pro'}],
            'division_colors': {'Pro': '#112233'},
        }
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = lambda: json.loads(json.dumps(remote_data))

        with (
            patch("config.official_leagues.get_official_league", return_value=league),
            patch("requests.get", return_value=response),
        ):
            manager = DivisionManager(
                config_file="official:Test League",
                settings_file=str(tmp_path / "settings.json"),
                unknown_driver_class='Am',
                persist_unknown_driver_assignments=True,
            )
            unknown = {'UserID': '999', 'UserName': 'Cached Driver'}

            assert manager.get_writable_config_path() == str(cache_file)
            assert manager.get_driver_division(unknown) == 'Am'
            augmented_cache = json.loads(cache_file.read_text())
            assert augmented_cache['drivers'][-1] == {
                'division': 'Am', 'id': '999', 'name': 'Cached Driver'
            }

            refresh_started = threading.Event()
            release_refresh = threading.Event()

            def blocked_refresh_json():
                refresh_started.set()
                assert release_refresh.wait(timeout=2)
                return json.loads(json.dumps(remote_data))

            response.json.side_effect = blocked_refresh_json
            refresh_thread = threading.Thread(target=manager.load_driver_config)
            refresh_thread.start()
            assert refresh_started.wait(timeout=2)
            assert manager.get_driver_division(
                {'UserID': '888', 'UserName': 'Concurrent Cached Driver'}
            ) == 'Am'
            release_refresh.set()
            refresh_thread.join(timeout=2)
            assert refresh_thread.is_alive() is False

        refreshed_cache = json.loads(cache_file.read_text())
        assert refreshed_cache == remote_data
        assert all(driver.get('id') != '999' for driver in refreshed_cache['drivers'])

    def test_failed_automatic_write_rolls_back_and_retries(self, tmp_path):
        config_file = tmp_path / "divisions.json"
        config_file.write_text(json.dumps({'drivers': []}))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='Rookie',
            persist_unknown_driver_assignments=True,
        )
        unknown = {'UserID': '404', 'UserName': 'Retry Driver'}
        original_atomic_write = manager._atomic_write_json
        attempts = 0

        def fail_once(target_file, data):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return False
            return original_atomic_write(target_file, data)

        with (
            patch.object(manager, '_atomic_write_json', side_effect=fail_once),
            patch("core.division_manager.time.monotonic", side_effect=[100.0, 101.0, 106.0]),
        ):
            assert manager.get_driver_division(unknown) == 'Rookie'
            assert manager.driver_colors['drivers'] == []
            assert manager.get_driver_division(unknown) == 'Rookie'
            assert attempts == 1
            assert manager.get_driver_division(unknown) == 'Rookie'

        assert attempts == 2
        assert json.loads(config_file.read_text())['drivers'] == [
            {'division': 'Rookie', 'id': '404', 'name': 'Retry Driver'}
        ]

    def test_persistent_write_failure_is_rate_limited(self, tmp_path):
        config_file = tmp_path / "divisions.json"
        config_file.write_text(json.dumps({'drivers': []}))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='Am',
            persist_unknown_driver_assignments=True,
        )
        unknown = {'UserID': '500', 'UserName': 'Read Only Driver'}

        with (
            patch.object(manager, '_atomic_write_json', return_value=False) as atomic_write,
            patch("core.division_manager.time.monotonic", side_effect=[20.0, 21.0, 22.0]),
        ):
            assert manager.get_driver_division(unknown) == 'Am'
            assert manager.get_driver_division(unknown) == 'Am'
            assert manager.get_driver_division(unknown) == 'Am'

        assert atomic_write.call_count == 1
        assert manager.driver_colors['drivers'] == []

    def test_atomic_write_failure_preserves_existing_json(self, tmp_path):
        config_file = tmp_path / "divisions.json"
        original_data = {'drivers': [{'id': '1', 'division': 'Pro'}]}
        config_file.write_text(json.dumps(original_data))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
        )

        assert manager._atomic_write_json(str(config_file), {'invalid': object()}) is False
        assert json.loads(config_file.read_text()) == original_data

    def test_source_switch_keeps_old_target_active_until_atomic_commit(self, tmp_path):
        old_file = tmp_path / "old.json"
        new_file = tmp_path / "new.json"
        old_file.write_text(json.dumps({'drivers': []}))
        new_data = {'drivers': [{'id': '2', 'name': 'New Known', 'division': 'Pro'}]}
        new_file.write_text(json.dumps(new_data))
        manager = DivisionManager(
            config_file=str(old_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='Am',
            persist_unknown_driver_assignments=True,
        )
        load_started = threading.Event()
        release_load = threading.Event()
        original_load_local = manager._load_local_file

        def blocked_load(config_file):
            load_started.set()
            assert release_load.wait(timeout=2)
            return original_load_local(config_file)

        with patch.object(manager, '_load_local_file', side_effect=blocked_load):
            switch_thread = threading.Thread(
                target=manager.change_config_source,
                args=(str(new_file),),
            )
            switch_thread.start()
            assert load_started.wait(timeout=2)
            assert manager.config_file == str(old_file)

            unknown = {'UserID': '999', 'UserName': 'Old Session Unknown'}
            assert manager.get_driver_division(unknown) == 'Am'

            release_load.set()
            switch_thread.join(timeout=2)
            assert switch_thread.is_alive() is False

        assert json.loads(old_file.read_text())['drivers'][-1]['id'] == '999'
        assert json.loads(new_file.read_text()) == new_data
        assert manager.config_file == str(new_file)
        assert manager.get_driver_division({'UserID': '2'}) == 'Pro'

    def test_same_source_reload_cannot_install_stale_data_over_persisted_assignment(self, tmp_path):
        config_file = tmp_path / "league.json"
        config_file.write_text(json.dumps({'drivers': []}))
        manager = DivisionManager(
            config_file=str(config_file),
            settings_file=str(tmp_path / "settings.json"),
            unknown_driver_class='ProAm',
            persist_unknown_driver_assignments=True,
        )
        read_started = threading.Event()
        release_read = threading.Event()
        persistence_finished = threading.Event()
        original_json_load = json.load

        def blocked_json_load(file_obj):
            read_started.set()
            assert release_read.wait(timeout=2)
            return original_json_load(file_obj)

        with patch("core.division_manager.json.load", side_effect=blocked_json_load):
            reload_thread = threading.Thread(target=manager.load_driver_config)
            reload_thread.start()
            assert read_started.wait(timeout=2)

            def persist_unknown():
                manager.get_driver_division({'UserID': '321', 'UserName': 'Locked Driver'})
                persistence_finished.set()

            persistence_thread = threading.Thread(target=persist_unknown)
            persistence_thread.start()
            assert persistence_finished.wait(timeout=0.05) is False
            release_read.set()
            reload_thread.join(timeout=2)
            persistence_thread.join(timeout=2)

        assert reload_thread.is_alive() is False
        assert persistence_thread.is_alive() is False
        assert json.loads(config_file.read_text())['drivers'] == [
            {'division': 'ProAm', 'id': '321', 'name': 'Locked Driver'}
        ]

    def test_failed_official_source_switch_preserves_active_local_league(self, tmp_path):
        local_file = tmp_path / "active.json"
        local_data = {'drivers': [{'id': '1', 'name': 'Active Driver', 'division': 'Pro'}]}
        local_file.write_text(json.dumps(local_data))
        manager = DivisionManager(
            config_file=str(local_file),
            settings_file=str(tmp_path / "settings.json"),
        )
        league = OfficialLeague(
            name="Unavailable League",
            path="missing.json",
            title="Unavailable",
            description="Unavailable",
            logo=None,
            cache_file=str(tmp_path / "missing-cache.json"),
        )

        with (
            patch("config.official_leagues.get_official_league", return_value=league),
            patch("requests.get", side_effect=OSError("offline")),
        ):
            success, _message, _count = manager.change_config_source(
                "official:Unavailable League"
            )

        assert success is False
        assert manager.config_file == str(local_file)
        assert manager.driver_colors == local_data
        assert manager.get_driver_division({'UserID': '1'}) == 'Pro'


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
