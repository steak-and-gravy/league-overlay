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
    """Spectated drivers in Default style keep their highlight and gain a yellow outline."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_spectated=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 1px solid yellow;" in style_sheet


def test_default_style_does_not_add_yellow_outline_for_player_driver(qapp):
    """Player highlight in Default style should remain borderless when not spectated."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_player=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 1px solid yellow;" not in style_sheet
