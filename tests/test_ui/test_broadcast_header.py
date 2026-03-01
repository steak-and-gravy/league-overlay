"""Tests for the broadcast header widget."""

import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from ui.broadcast_header import BroadcastHeaderWidget
from config.settings import AppSettings


@pytest.fixture(scope='session')
def qapp():
    """Create QApplication for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def default_settings():
    """AppSettings with broadcast header enabled."""
    settings = AppSettings()
    settings.show_broadcast_header = True
    settings.broadcast_header_title = "TEST RACING LEAGUE"
    settings.broadcast_header_accent_color = "#FF8C00"
    return settings


def _get_bg_color(hex_color):
    """Stub for get_bg_color."""
    return f"rgba(20, 20, 20, 0.5)"


def _get_font_size(element_type):
    """Stub for get_font_size."""
    sizes = {
        'broadcast_title': '11',
        'broadcast_session': '8.5',
        'broadcast_track': '8',
        'spacing': 3,
    }
    return sizes.get(element_type, '9')


class TestBroadcastHeaderWidget:
    """Tests for BroadcastHeaderWidget."""

    def test_widget_creates_without_error(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        assert widget is not None
        widget.deleteLater()

    def test_title_displayed_uppercase(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        assert widget.title_label.text() == "TEST RACING LEAGUE"
        widget.deleteLater()

    def test_empty_title(self, qapp):
        settings = AppSettings()
        settings.broadcast_header_title = ""
        widget = BroadcastHeaderWidget(
            settings=settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        assert widget.title_label.text() == ""
        widget.deleteLater()

    def test_update_session_info(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        widget.update_session_info({
            'session_status': 'Race - Lap 14/20',
            'track_display_name': 'Daytona International Speedway',
        })
        assert "RACE" in widget.session_label.text()
        assert "Lap 14/20" in widget.session_label.text()
        assert widget.track_label.text() == "Daytona International Speedway"
        widget.deleteLater()

    def test_update_session_info_no_dash(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        widget.update_session_info({
            'session_status': 'Connected',
            'track_display_name': '',
        })
        assert widget.session_label.text() == "CONNECTED"
        widget.deleteLater()

    def test_accent_line_changes_on_caution(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        widget.update_session_info({'status_color': 'yellow'})
        assert '#FFD700' in widget.accent_line.styleSheet()
        widget.deleteLater()

    def test_accent_line_restores_on_green(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        widget.update_session_info({'status_color': 'yellow'})
        widget.update_session_info({'status_color': 'green'})
        assert default_settings.broadcast_header_accent_color in widget.accent_line.styleSheet()
        widget.deleteLater()

    def test_disconnect_status_forwarded(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        widget.update_session_info({
            'session_status': 'Connecting to iRacing...',
            'status_color': 'orange',
        })
        assert "CONNECTING" in widget.session_label.text()
        assert '#FF8C00' in widget.accent_line.styleSheet()
        widget.deleteLater()

    def test_logo_hidden_when_no_path(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        assert not widget.logo_label.isVisible()
        widget.deleteLater()

    def test_logo_hidden_when_file_missing(self, qapp):
        settings = AppSettings()
        settings.broadcast_header_logo = "/nonexistent/path/logo.png"
        widget = BroadcastHeaderWidget(
            settings=settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        assert not widget.logo_label.isVisible()
        widget.deleteLater()

    def test_refresh_styles_updates_title(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        default_settings.broadcast_header_title = "NEW LEAGUE NAME"
        widget.refresh_styles()
        assert widget.title_label.text() == "NEW LEAGUE NAME"
        widget.deleteLater()

    def test_refresh_styles_clears_title_when_empty(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(
            settings=default_settings,
            get_bg_color_fn=_get_bg_color,
            get_font_size_fn=_get_font_size,
        )
        default_settings.broadcast_header_title = ""
        widget.refresh_styles()
        assert widget.title_label.text() == ""
        widget.deleteLater()


class TestBroadcastHeaderSettings:
    """Tests for broadcast header settings in AppSettings."""

    def test_default_settings(self):
        settings = AppSettings()
        assert settings.show_broadcast_header is False
        assert settings.broadcast_header_logo is None
        assert settings.broadcast_header_title == ""
        assert settings.broadcast_header_accent_color == "#FF8C00"

    def test_settings_round_trip(self, tmp_path):
        from config.settings import SettingsManager
        config_file = str(tmp_path / "test.config")
        manager = SettingsManager(config_file)

        settings = AppSettings()
        settings.show_broadcast_header = True
        settings.broadcast_header_title = "MY LEAGUE"
        settings.broadcast_header_logo = "/path/to/logo.png"
        settings.broadcast_header_accent_color = "#00FF00"

        manager.save(settings)
        loaded = manager.load()

        assert loaded.show_broadcast_header is True
        assert loaded.broadcast_header_title == "MY LEAGUE"
        assert loaded.broadcast_header_logo == "/path/to/logo.png"
        assert loaded.broadcast_header_accent_color == "#00FF00"


class TestBroadcastHeaderValidation:
    """Tests for broadcast header settings validation."""

    def test_validator_coerces_broadcast_fields(self):
        from config.settings_validator import SettingsValidator
        validator = SettingsValidator()

        data = {
            'show_broadcast_header': 'true',
            'broadcast_header_title': 'TEST',
            'broadcast_header_logo': None,
            'broadcast_header_accent_color': '#FF0000',
        }
        result = validator.validate_and_coerce(data)
        assert result['show_broadcast_header'] is True
        assert result['broadcast_header_title'] == 'TEST'
        assert result['broadcast_header_logo'] is None
        assert result['broadcast_header_accent_color'] == '#FF0000'

    def test_validator_defaults_for_missing_broadcast_fields(self):
        from config.settings_validator import SettingsValidator
        validator = SettingsValidator()

        result = validator.validate_and_coerce({})
        assert result['show_broadcast_header'] is False
        assert result['broadcast_header_title'] == ""
        assert result['broadcast_header_logo'] is None
        assert result['broadcast_header_accent_color'] == '#FF8C00'

    def test_validator_rejects_invalid_accent_color(self):
        from config.settings_validator import SettingsValidator
        validator = SettingsValidator()

        data = {'broadcast_header_accent_color': 'not-a-color'}
        result = validator.validate_and_coerce(data)
        assert result['broadcast_header_accent_color'] == '#FF8C00'  # Falls back to default
