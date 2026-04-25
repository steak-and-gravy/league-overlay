"""Tests for the custom overlay title bar."""

from types import SimpleNamespace
from unittest.mock import Mock

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from config.constants import UI_DIMENSIONS
from league_overlay import LeagueOverlay


class TitleBarHarness:
    """Minimal object with the attributes create_title_bar needs."""

    def __init__(self):
        self.settings = SimpleNamespace(opacity=1, font_size="Medium")
        self.host = QWidget()
        self.main_layout = QVBoxLayout(self.host)
        self.toggle_division_filter = Mock()
        self.open_settings = Mock()
        self.close_application = Mock()
        self.showMinimized = Mock()
        self.minimize_application = LeagueOverlay.minimize_application.__get__(self)

    def get_bg_color(self, color):
        return color

    def get_font_size(self, _element_type):
        return "9pt"


def test_title_bar_has_minimize_button_next_to_close_button(qapp):
    """The frameless title bar exposes working minimize and close controls."""
    harness = TitleBarHarness()

    LeagueOverlay.create_title_bar(harness)

    minimize_btn = harness.title_bar.findChild(QPushButton, "minimizeButton")
    close_btn = harness.title_bar.findChild(QPushButton, "closeButton")

    assert minimize_btn is not None
    assert close_btn is not None
    assert minimize_btn.text() == "-"
    assert minimize_btn.width() == UI_DIMENSIONS.CLOSE_BUTTON_WIDTH
    assert harness.title_bar.layout().indexOf(close_btn) - harness.title_bar.layout().indexOf(minimize_btn) == 1

    minimize_btn.click()
    close_btn.click()

    harness.showMinimized.assert_called_once_with()
    harness.close_application.assert_called_once_with()
