"""Tests for row style strategies."""

from types import SimpleNamespace

from core.driver_state import DriverState
from ui.styles import AlternateColorStyle, DarkColorStyle, DefaultColorStyle, OutlineColorStyle


def _make_parent(
    row_color_style: str = "Default",
    opacity: float = 0.8,
    highlight_player_border: bool = False,
):
    """Create a minimal parent object for style strategy tests."""
    highlight = 0.25

    return SimpleNamespace(
        settings=SimpleNamespace(
            row_color_style=row_color_style,
            highlight=highlight,
            faster_color="#00FF00",
            slower_color="#FF0000",
            pit_stop_indicator=True,
            opacity=opacity,
            highlight_player_border=highlight_player_border,
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


def test_default_style_adds_yellow_outline_for_player_when_enabled(qapp):
    """The optional player border uses the same yellow outline as spectated rows."""
    style = DefaultColorStyle()
    parent = _make_parent(highlight_player_border=True)
    driver = _make_driver(is_player=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 2px solid yellow;" in style_sheet


def test_non_default_styles_add_yellow_outline_for_player_when_enabled(qapp):
    """The optional player border is visible for all row color styles."""
    parent = _make_parent(highlight_player_border=True)
    driver = _make_driver(is_player=True)

    dark_styling = DarkColorStyle().get_styling(driver, parent)
    outline_styling = OutlineColorStyle().get_styling(driver, parent)
    alternate_styling = AlternateColorStyle().get_styling(driver, parent)

    assert "border: 2px solid yellow;" in dark_styling["row_widget"].styleSheet()
    assert "border: 2px solid yellow;" in outline_styling["row_widget"].styleSheet()
    assert "background-color: transparent;" in alternate_styling["container_widget"].styleSheet()
    assert "border: 2px solid yellow;" in alternate_styling["container_widget"].styleSheet()


def test_default_style_does_not_add_yellow_outline_when_player_is_also_spectated(qapp):
    """Player rows stay borderless even if they are also marked as spectated."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(is_player=True, is_spectated=True)

    styling = style.get_styling(driver, parent)

    style_sheet = styling["row_widget"].styleSheet()
    assert "background: gradient(#00AAFF);" in style_sheet
    assert "border: 2px solid yellow;" not in style_sheet


def test_default_style_uses_row_background_for_car_number_with_2px_outline_by_default():
    """Default style keeps the row background behind the outlined car number."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(show_car_number_outline=True)

    styling = style.get_styling(driver, parent)

    assert styling["car_number_bg"] == "transparent"
    assert styling["car_number_border"] == "border: 2px solid #00AAFF;"
    assert styling["car_number_color"] == "white"
    assert styling["division_position_bg"] == "rgba(0, 170, 255, 0.9)"
    assert styling["position_bg"] == "rgba(255, 255, 255, 0.9)"
    assert styling["position_color"] == "#000000"


def test_default_style_applies_half_opacity_to_overall_and_class_position_backgrounds(qapp):
    """Overall/Class position backgrounds get a softer version of the opacity setting."""
    style = DefaultColorStyle()
    parent = _make_parent(opacity=0.25)
    driver = _make_driver()

    styling = style.get_styling(driver, parent)

    assert styling["position_bg"] == "rgba(255, 255, 255, 0.625)"
    assert styling["division_position_bg"] == "rgba(0, 170, 255, 0.625)"
    assert styling["position_color"] == "#000000"


def test_default_style_keeps_half_visible_overall_and_class_backgrounds_at_zero_opacity(qapp):
    """Overall/Class half-opacity backgrounds keep the same formula at zero opacity."""
    style = DefaultColorStyle()
    parent = _make_parent(opacity=0.0)
    driver = _make_driver()

    styling = style.get_styling(driver, parent)

    assert styling["position_bg"] == "rgba(255, 255, 255, 0.5)"
    assert styling["division_position_bg"] == "rgba(0, 170, 255, 0.5)"


def test_default_style_preserves_division_color_alpha_for_class_position_background(qapp):
    """Half-opacity class backgrounds should keep any alpha embedded in the color."""
    style = DefaultColorStyle()
    parent = _make_parent(opacity=0.25)
    driver = _make_driver(division_color="#00AAFF80")

    styling = style.get_styling(driver, parent)

    assert styling["division_position_bg"] == "rgba(0, 170, 255, 0.3137254901960784)"


def test_default_style_keeps_2px_outline_for_pending_mandatory_stop():
    """Pending mandatory stops keep the standard 2px outlined car-number style."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(show_car_number_outline=True)

    styling = style.get_styling(driver, parent)

    assert styling["car_number_bg"] == "transparent"
    assert styling["car_number_border"] == "border: 2px solid #00AAFF;"
    assert styling["car_number_color"] == "white"


def test_default_style_uses_no_outline_when_required_stop_is_complete():
    """Completed required stops remove the car-number outline when Pit Stop Indicator is enabled."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver(show_car_number_outline=False)

    styling = style.get_styling(driver, parent)

    assert styling["car_number_bg"] == "transparent"
    assert styling["car_number_border"] == ""


def test_default_style_uses_2px_outline_when_pit_stop_indicator_setting_disabled():
    """Disabling Pit Stop Indicator keeps the standard 2px outlined car-number style."""
    style = DefaultColorStyle()
    parent = _make_parent()
    parent.settings.pit_stop_indicator = False
    driver = _make_driver(show_car_number_outline=False)

    styling = style.get_styling(driver, parent)

    assert styling["car_number_bg"] == "transparent"
    assert styling["car_number_border"] == "border: 2px solid #00AAFF;"


def test_default_style_uses_colored_division_position_with_division_outline():
    """Default style renders C-Pos with a division-color background, outline, and white text."""
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver()

    styling = style.get_styling(driver, parent)

    assert styling["division_position_bg"] == "rgba(0, 170, 255, 0.9)"
    assert styling["division_position_border"] == "border: 2px solid #00AAFF;"
    assert styling["division_position_color"] == "white"


def test_default_style_applies_alternating_row_backgrounds(qapp):
    style = DefaultColorStyle()
    parent = _make_parent()
    driver = _make_driver()

    even_styling = style.get_styling(driver, parent, row_index=0)
    odd_styling = style.get_styling(driver, parent, row_index=1)

    assert "background-color: #000000;" in even_styling["row_widget"].styleSheet()
    assert "background-color: #333333;" in odd_styling["row_widget"].styleSheet()
    assert even_styling["label_bg"] == "transparent"
    assert odd_styling["label_bg"] == "transparent"
