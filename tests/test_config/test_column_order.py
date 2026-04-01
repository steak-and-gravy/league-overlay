"""Tests for column order settings validation and persistence."""

import json
import os
import tempfile

import pytest

from config.constants import DEFAULT_COLUMN_ORDER, VALID_COLUMN_IDS, COLUMN_REGISTRY
from config.settings import AppSettings, SettingsManager
from config.settings_validator import SettingsValidator


class TestColumnOrderDefaults:
    """Test that default column order is well-formed."""

    def test_default_order_contains_all_columns(self):
        settings = AppSettings()
        assert set(settings.column_order) == VALID_COLUMN_IDS

    def test_default_order_has_no_duplicates(self):
        settings = AppSettings()
        assert len(settings.column_order) == len(set(settings.column_order))

    def test_default_order_matches_constant(self):
        settings = AppSettings()
        assert settings.column_order == list(DEFAULT_COLUMN_ORDER)


class TestColumnOrderValidation:
    """Test SettingsValidator.coerce_column_order."""

    def setup_method(self):
        self.validator = SettingsValidator()

    def test_none_returns_default(self):
        result = self.validator.coerce_column_order(None, 'column_order')
        assert result == list(DEFAULT_COLUMN_ORDER)

    def test_non_list_returns_default(self):
        result = self.validator.coerce_column_order("not_a_list", 'column_order')
        assert result == list(DEFAULT_COLUMN_ORDER)

    def test_valid_reordered_list(self):
        reordered = list(reversed(DEFAULT_COLUMN_ORDER))
        result = self.validator.coerce_column_order(reordered, 'column_order')
        assert result == reordered

    def test_unknown_ids_stripped(self):
        order = list(DEFAULT_COLUMN_ORDER) + ["fake_column"]
        result = self.validator.coerce_column_order(order, 'column_order')
        assert "fake_column" not in result
        assert set(result) == VALID_COLUMN_IDS

    def test_duplicates_stripped(self):
        order = list(DEFAULT_COLUMN_ORDER) + [DEFAULT_COLUMN_ORDER[0]]
        result = self.validator.coerce_column_order(order, 'column_order')
        assert len(result) == len(VALID_COLUMN_IDS)

    def test_missing_ids_appended(self):
        partial = list(DEFAULT_COLUMN_ORDER)[:3]
        result = self.validator.coerce_column_order(partial, 'column_order')
        # First 3 should match, rest appended
        assert result[:3] == partial
        assert set(result) == VALID_COLUMN_IDS

    def test_empty_list_returns_all_defaults(self):
        result = self.validator.coerce_column_order([], 'column_order')
        assert set(result) == VALID_COLUMN_IDS

    def test_non_string_items_skipped(self):
        order = [123, DEFAULT_COLUMN_ORDER[0], None]
        result = self.validator.coerce_column_order(order, 'column_order')
        assert DEFAULT_COLUMN_ORDER[0] in result
        assert set(result) == VALID_COLUMN_IDS


class TestColumnOrderPersistence:
    """Test column_order round-trips through save/load."""

    def test_save_and_load_preserves_order(self, tmp_path):
        settings_file = str(tmp_path / "test_config.json")
        manager = SettingsManager(settings_file)

        # Set custom order
        custom_order = list(reversed(DEFAULT_COLUMN_ORDER))
        settings = AppSettings()
        settings.column_order = custom_order
        manager.save(settings)

        # Load and verify
        loaded = manager.load()
        assert loaded.column_order == custom_order

    def test_load_without_column_order_uses_default(self, tmp_path):
        settings_file = str(tmp_path / "test_config.json")
        # Write a config file without column_order
        with open(settings_file, 'w') as f:
            json.dump({"opacity": 0.9}, f)

        manager = SettingsManager(settings_file)
        loaded = manager.load()
        assert loaded.column_order == list(DEFAULT_COLUMN_ORDER)

    def test_load_with_partial_column_order_appends_missing(self, tmp_path):
        settings_file = str(tmp_path / "test_config.json")
        partial = list(DEFAULT_COLUMN_ORDER)[:5]
        with open(settings_file, 'w') as f:
            json.dump({"column_order": partial}, f)

        manager = SettingsManager(settings_file)
        loaded = manager.load()
        assert loaded.column_order[:5] == partial
        assert set(loaded.column_order) == VALID_COLUMN_IDS


class TestColumnRegistry:
    """Test that column registry is consistent."""

    def test_all_default_order_ids_in_registry(self):
        for col_id in DEFAULT_COLUMN_ORDER:
            assert col_id in COLUMN_REGISTRY

    def test_registry_entries_have_required_fields(self):
        for col_id, col_def in COLUMN_REGISTRY.items():
            assert col_def.id == col_id
            assert len(col_def.header) > 0
            assert col_def.stretch > 0
            assert col_def.min_width > 0
            assert len(col_def.render_method) > 0

    def test_always_visible_columns_have_no_settings_key(self):
        always_visible = {'pos', 'div_pos', 'driver_name'}
        for col_id in always_visible:
            assert COLUMN_REGISTRY[col_id].settings_key == ''

    def test_optional_columns_have_settings_key(self):
        optional = VALID_COLUMN_IDS - {'pos', 'div_pos', 'driver_name'}
        for col_id in optional:
            assert COLUMN_REGISTRY[col_id].settings_key != '', f"{col_id} should have a settings_key"
