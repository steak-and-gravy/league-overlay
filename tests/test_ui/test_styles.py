"""Tests for row style strategies."""

from types import SimpleNamespace

from core.driver_state import DriverState
from ui.styles import DefaultColorStyle


def _make_parent(row_color_style: str = "Default"):
    """Create a minimal parent object for style strategy tests."""
    highlight = 0.25

    return SimpleNamespace(
        settings=SimpleNamespace(
            row_color_style=row_color_style,
            highlight=highlight,
            faster_color="#00FF00",
            slower_color="#FF0000",
        ),
        get_bg_color=lambda color: color,
        blend_color_with_black=lambda color, amount: "#112233",
        create_gradient_background=lambda color: f"gradient({color})",
    )


def _make_driver(**overrides):
    """Create a DriverState with sensible defaults for styling tests."""
    base_driver = DriverState(
        car_idx=5,
        driver_info={"UserName": "Focused Driver", "CarNumber": "42", "CarClassID": 100},
        division_color="#00AAFF",
    )

    for key, value in overrides.items():
        setattr(base_driver, key, value)

    return base_driver


def test_default_style_adds_yellow_outline_for_spectated_driver(qapp):
    """Spectated drivers in Default style use only the yellow outline."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_spectated=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background-color: #000000;" in style_sheet
    assert "background: gradient(#00AAFF);" not in style_sheet
    assert "border: 2px solid yellow;" in style_sheet


def test_default_style_does_not_add_yellow_outline_for_player_driver(qapp):
    """Player highlight in Default style should remain borderless when not spectated."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_player=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 2px solid yellow;" not in style_sheet


def test_default_style_does_not_add_yellow_outline_when_player_is_also_spectated(qapp):
    """Player rows stay borderless even if they are also marked as spectated."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_player=True, is_spectated=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 2px solid yellow;" not in style_sheet


def test_default_style_uses_black_car_number_background_with_division_outline():
    """Default style renders the car number on black with a 2px division-color outline and white text."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver()

    styling = style.get_styling(driver, parent)

    assert styling["car_number_bg"] == "#000000"
    assert styling["car_number_border"] == "border: 2px solid #00AAFF;"
    assert styling["car_number_color"] == "white"
    assert styling["division_position_bg"] == "#00AAFF"


def test_default_style_uses_black_division_position_with_division_outline():
    """Default style renders C-Pos with a division-color background, outline, and white text."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver()

    styling = style.get_styling(driver, parent)

    assert styling["division_position_bg"] == "#00AAFF"
    assert styling["division_position_border"] == "border: 2px solid #00AAFF;"
    assert styling["division_position_color"] == "white"
