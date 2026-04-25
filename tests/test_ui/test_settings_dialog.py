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
        self.update_all_backgrounds_result = None
        self.save_settings_called = False

    def apply_official_league_broadcast_metadata(self):
        pass

    def update_all_backgrounds(self):
        return self.update_all_backgrounds_result

    def save_settings(self):
        self.save_settings_called = True

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


def test_apply_settings_updates_recent_lap_flash_checkbox(qapp):
    """Applying the dialog should persist the recent-lap flash toggle."""
    overlay, dialog = _build_dialog()

    assert dialog.show_recent_lap_flash_cb.text() == "Recent lap update"
    dialog.show_recent_lap_flash_cb.setChecked(False)
    dialog.apply_settings()

    assert overlay.settings.show_recent_lap_flash is False
    assert overlay.signals.refresh_colors.emit.called

    dialog.deleteLater()
    overlay.deleteLater()


def test_apply_settings_preserves_existing_quarter_step_refresh_rate(qapp):
    """Applying without changing refresh should not rewrite legacy quarter-step values."""
    overlay, dialog = _build_dialog()
    overlay.settings.refresh_rate = 1.25

    dialog.deleteLater()
    dialog = SettingsDialog(overlay)

    assert dialog.refresh_slider.minimum() == 2
    assert dialog.refresh_slider.value() == 5
    assert dialog.refresh_value_label.text() == "1.25"

    dialog.apply_settings()

    assert overlay.settings.refresh_rate == 1.25

    dialog.deleteLater()
    overlay.deleteLater()


def test_refresh_rate_label_matches_clamped_slider_value(qapp):
    """Dialog label should reflect the clamped slider value for out-of-range settings."""
    overlay, dialog = _build_dialog()
    overlay.settings.refresh_rate = 0.25

    dialog.deleteLater()
    dialog = SettingsDialog(overlay)

    assert dialog.refresh_slider.minimum() == 2
    assert dialog.refresh_slider.value() == 2
    assert dialog.refresh_value_label.text() == "0.50"

    dialog.deleteLater()
    overlay.deleteLater()


def test_apply_settings_updates_local_website_controls(qapp):
    """Applying the dialog should persist local-network browser-source settings."""
    with patch("ui.settings_dialog.get_local_network_url", return_value="http://192.168.1.211:8765/"):
        overlay, dialog = _build_dialog()

        assert dialog.local_website_section_title.text() == "Local Website"
        assert dialog.local_website_enabled_cb.text() == "Enable local website"
        assert dialog.local_website_link.text() == "http://192.168.1.211:8765/"
        assert dialog.local_website_link.openExternalLinks() is False
        assert dialog.local_website_link.textInteractionFlags() == Qt.NoTextInteraction
        dialog.local_website_enabled_cb.setChecked(True)
        assert dialog.local_website_link.openExternalLinks() is True
        assert dialog.local_website_link.textInteractionFlags() == Qt.TextBrowserInteraction
        assert 'href="http://192.168.1.211:8765/"' in dialog.local_website_link.text()
        dialog.local_website_port_spin.setValue(8766)
        dialog.apply_settings()

    assert overlay.settings.local_website_enabled is True
    assert overlay.settings.local_website_port == 8766
    assert overlay.signals.refresh_colors.emit.called

    dialog.deleteLater()
    overlay.deleteLater()


def test_local_website_link_updates_port_and_respects_enabled_state(qapp):
    """Local website URL should be shown below controls and only clickable when enabled."""
    with patch("ui.settings_dialog.get_local_network_url") as get_url:
        get_url.side_effect = lambda port: f"http://192.168.1.211:{port}/"
        overlay, dialog = _build_dialog()

        assert dialog.local_website_link.text() == "http://192.168.1.211:8765/"
        assert dialog.local_website_link.openExternalLinks() is False

        dialog.local_website_port_spin.setValue(8777)
        assert dialog.local_website_link.text() == "http://192.168.1.211:8777/"
        assert dialog.local_website_link.openExternalLinks() is False

        dialog.local_website_enabled_cb.setChecked(True)
        assert 'href="http://192.168.1.211:8777/"' in dialog.local_website_link.text()
        assert ">http://192.168.1.211:8777/</a>" in dialog.local_website_link.text()
        assert dialog.local_website_link.openExternalLinks() is True

        dialog.local_website_enabled_cb.setChecked(False)
        assert dialog.local_website_link.text() == "http://192.168.1.211:8777/"
        assert dialog.local_website_link.openExternalLinks() is False

    dialog.deleteLater()
    overlay.deleteLater()


def test_apply_settings_reverts_local_website_when_startup_fails(qapp):
    """Failed local website startup should be visible and should not save the bad port."""
    overlay, dialog = _build_dialog()
    original_enabled = overlay.settings.local_website_enabled
    original_port = overlay.settings.local_website_port
    overlay.update_all_backgrounds_result = False

    dialog.local_website_enabled_cb.setChecked(True)
    dialog.local_website_port_spin.setValue(8766)
    with patch("ui.settings_dialog.QMessageBox.critical") as critical:
        dialog.apply_settings()

    assert overlay.settings.local_website_enabled is original_enabled
    assert overlay.settings.local_website_port == original_port
    assert dialog.local_website_enabled_cb.isChecked() is original_enabled
    assert dialog.local_website_port_spin.value() == original_port
    assert overlay.save_settings_called is False
    assert overlay.signals.refresh_colors.emit.called is False
    critical.assert_called_once()

    dialog.deleteLater()
    overlay.deleteLater()
