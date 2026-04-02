"""Tests for the settings dialog column visibility list."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QStyleOptionViewItem

from config.official_leagues import OfficialLeague
from config.settings import AppSettings
from ui.settings_dialog import SettingsDialog, ColumnListItemDelegate, ALWAYS_VISIBLE_ROLE


class DummyOverlay(QWidget):
    """Minimal QWidget parent for SettingsDialog tests."""

    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.division_manager = SimpleNamespace(
            division_colors=self.settings.division_colors.copy(),
            driver_colors={'drivers': []},
            config_file="official:BWRL GT3 Sprint",
        )
        self.color_config_file = "official:BWRL GT3 Sprint"
        self.settings_manager = Mock()
        self.signals = SimpleNamespace(refresh_colors=SimpleNamespace(emit=Mock()))
        self.latest_version = None

    def apply_official_league_broadcast_metadata(self):
        pass

    def update_all_backgrounds(self):
        pass

    def save_settings(self):
        pass

    def add_to_recent_files(self, file_path):
        pass

    def refresh_official_league(self):
        return True, "", 0


def _build_dialog():
    overlay = DummyOverlay()
    league = OfficialLeague(
        name="BWRL GT3 Sprint",
        path="bwrl/broken_wing_gt3.json",
        title="Broken Wing GT3 Sprint",
        description="Broken Wing Racing League Sunday Night GT3",
        logo=None,
        cache_file="cache_broken_wing_gt3.json",
    )

    with patch("config.official_leagues.OFFICIAL_LEAGUES", [league]):
        dialog = SettingsDialog(overlay)

    return overlay, dialog


def _find_item(dialog, col_id):
    for row in range(dialog.column_list.count()):
        item = dialog.column_list.item(row)
        if item.data(Qt.UserRole) == col_id:
            return row, item
    raise AssertionError(f"Column {col_id} not found")


def test_fixed_columns_use_disabled_checkbox_behavior(qapp):
    """Overall/Class/Driver stay checked and use the fixed-column delegate path."""
    overlay, dialog = _build_dialog()

    assert isinstance(dialog.column_list.itemDelegate(), ColumnListItemDelegate)

    delegate = dialog.column_list.itemDelegate()
    option = QStyleOptionViewItem()
    model = dialog.column_list.model()

    for col_id in ("pos", "div_pos", "driver_name"):
        row, item = _find_item(dialog, col_id)
        assert item.checkState() == Qt.Checked
        assert item.data(ALWAYS_VISIBLE_ROLE) is True
        assert item.toolTip() == "Always visible"
        assert delegate.editorEvent(None, model, option, model.index(row, 0)) is False

    _, gap_item = _find_item(dialog, "gap")
    assert gap_item.data(ALWAYS_VISIBLE_ROLE) is False

    dialog.deleteLater()
    overlay.deleteLater()


def test_reset_column_list_preserves_fixed_column_state(qapp):
    """Reset should rebuild fixed columns with the same always-visible metadata."""
    overlay, dialog = _build_dialog()
    overlay.settings.show_gap = True
    dialog._populate_column_list()

    _, gap_item = _find_item(dialog, "gap")
    assert gap_item.checkState() == Qt.Checked
    assert gap_item.data(ALWAYS_VISIBLE_ROLE) is False

    dialog._reset_column_list_to_defaults(AppSettings())

    for col_id in ("pos", "div_pos", "driver_name"):
        _, item = _find_item(dialog, col_id)
        assert item.checkState() == Qt.Checked
        assert item.data(ALWAYS_VISIBLE_ROLE) is True

    _, reset_gap_item = _find_item(dialog, "gap")
    assert reset_gap_item.checkState() == Qt.Unchecked
    assert reset_gap_item.data(ALWAYS_VISIBLE_ROLE) is False

    dialog.deleteLater()
    overlay.deleteLater()
