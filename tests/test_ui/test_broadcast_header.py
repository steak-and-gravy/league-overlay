"""Tests for the broadcast header widget."""

import pytest
from PySide6.QtCore import Qt
from unittest.mock import Mock, patch
import requests

from ui.broadcast_header import BroadcastHeaderWidget
from config.settings import AppSettings


@pytest.fixture
def default_settings():
    settings = AppSettings()
    settings.show_broadcast_header = True
    settings.broadcast_header_title = "TEST RACING LEAGUE"
    settings.broadcast_header_accent_color = "#FF8C00"
    settings.broadcast_header_logo = "/tmp/logo.png"
    return settings


def _get_bg_color(_hex_color):
    return "rgba(20, 20, 20, 0.5)"


def _get_font_size(element_type):
    sizes = {
        'broadcast_title': '11pt',
        'broadcast_session': '8.5pt',
        'broadcast_track': '8pt',
        'spacing': 3,
    }
    return sizes.get(element_type, '9pt')


class TestBroadcastHeaderWidget:
    def test_widget_creates_without_error(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        assert widget is not None
        assert widget.testAttribute(Qt.WA_StyledBackground)
        widget.deleteLater()

    def test_title_displayed_uppercase(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        assert widget.title_label.text() == "TEST RACING LEAGUE"
        widget.deleteLater()

    def test_update_session_info_caution_style(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        widget.update_session_info({'session_status': 'CAUTION - Lap 5/20', 'status_color': 'yellow'})
        assert 'color: #FFD700;' in widget.session_label.styleSheet()
        assert '#FFD700' in widget.accent_line.styleSheet()
        widget.deleteLater()

    def test_update_session_info_restores_regular_style(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        widget.update_session_info({'session_status': 'CAUTION - Lap 5/20', 'status_color': 'yellow'})
        widget.update_session_info({'session_status': 'Race - Lap 6/20', 'status_color': 'green'})
        assert 'color: white;' in widget.session_label.styleSheet()
        assert 'font-weight: bold;' in widget.session_label.styleSheet()
        assert '#FF8C00' in widget.accent_line.styleSheet()
        widget.deleteLater()

    def test_update_session_info_update_available_uses_green_bold_style(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        widget.update_session_info({'session_status': 'Update available: v1.2.3', 'status_color': 'green'})
        assert 'color: #00FF00;' in widget.session_label.styleSheet()
        assert 'font-weight: bold;' in widget.session_label.styleSheet()
        widget.deleteLater()

    def test_logo_hidden_when_not_url(self, qapp):
        settings = AppSettings()
        settings.broadcast_header_logo = "/tmp/logo.png"
        widget = BroadcastHeaderWidget(settings, _get_bg_color, _get_font_size)
        assert not widget.logo_label.isVisible()
        widget.deleteLater()

    def test_logo_loads_from_url(self, qapp, default_settings):
        response = Mock()
        response.content = b"not-used"
        response.raise_for_status = Mock()
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)

        with patch("ui.broadcast_header.requests.get", return_value=response), patch("ui.broadcast_header.QPixmap") as qpix_cls:
            pixmap_mock = Mock()
            pixmap_mock.loadFromData.return_value = True
            qpix_cls.return_value = pixmap_mock
            pixmap = widget._load_logo_from_url("https://example.com/logo.png")
        assert pixmap is pixmap_mock
        widget.deleteLater()

    def test_logo_url_failure_returns_none(self, qapp, default_settings):
        widget = BroadcastHeaderWidget(default_settings, _get_bg_color, _get_font_size)
        with patch("ui.broadcast_header.requests.get", side_effect=requests.RequestException("network failure")):
            pixmap = widget._load_logo_from_url("https://example.com/logo.png")
        assert pixmap is None
        widget.deleteLater()
