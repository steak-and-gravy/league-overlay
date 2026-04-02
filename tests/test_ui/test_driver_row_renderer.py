"""Tests for manufacturer logo rendering in driver rows."""

from types import SimpleNamespace

from core.driver_state import DriverState
from ui.driver_row_renderer import DriverRowRenderer


def _make_parent():
    from config.constants import DEFAULT_COLUMN_ORDER
    settings = SimpleNamespace(
        row_color_style="Default",
        highlight=0.25,
        faster_color="#00FF00",
        slower_color="#FF0000",
        show_positions_gained=False,
        show_car_manufacturer=True,
        show_rating=False,
        show_car_number=True,
        show_gap=False,
        show_division_gap=False,
        show_interval=False,
        show_division_interval=False,
        show_best_lap=False,
        show_last_lap=False,
        show_delta=False,
        show_pit_lap=False,
        bold_drivers=False,
        pit_stop_indicator=True,
        column_order=list(DEFAULT_COLUMN_ORDER),
    )

    return SimpleNamespace(
        settings=settings,
        get_bg_color=lambda color: color,
        blend_color_with_black=lambda color, amount: "#112233",
        create_gradient_background=lambda color: f"gradient({color})",
        get_font_size=lambda element_type: "9pt" if element_type != "spacing" else 3,
        show_context_menu=lambda driver: None,
    )


def _make_driver(car_path: str, manufacturer: str = "MFR", positions_gained: str = "", **overrides) -> DriverState:
    driver = DriverState(
        car_idx=5,
        driver_info={
            "UserName": "Logo Driver",
            "CarNumber": "42",
            "CarClassID": 100,
            "CarPath": car_path,
        },
        division_color="#00AAFF",
        car_manufacturer=manufacturer,
        positions_gained=positions_gained,
    )
    for key, value in overrides.items():
        setattr(driver, key, value)
    return driver


def test_get_manufacturer_logo_path_matches_known_asset():
    driver = _make_driver("ferrari 296 gt3")

    logo_path = DriverRowRenderer._get_manufacturer_logo_path(driver)

    assert logo_path is not None
    assert logo_path.name == "ferrari.png"


def test_get_manufacturer_logo_path_uses_display_code_aliases():
    driver = _make_driver("", manufacturer="CHE")

    logo_path = DriverRowRenderer._get_manufacturer_logo_path(driver)

    assert logo_path is not None
    assert logo_path.name == "chevrolet.png"


def test_get_manufacturer_logo_path_prefers_display_code_when_car_path_differs():
    driver = _make_driver("unknown prototype", manufacturer="POR")

    logo_path = DriverRowRenderer._get_manufacturer_logo_path(driver)

    assert logo_path is not None
    assert logo_path.name == "porsche.png"


def test_create_row_uses_logo_when_asset_exists(qapp):
    renderer = DriverRowRenderer(_make_parent())
    driver = _make_driver("porsche 911 gt3 r", manufacturer="POR")

    row = renderer.create_row(driver)
    layout = row.layout()
    manufacturer_label = layout.itemAtPosition(0, 1).widget()

    assert manufacturer_label.pixmap() is not None
    assert manufacturer_label.text() == ""
    row.deleteLater()


def test_create_row_applies_subtle_banding_to_alternate_rows(qapp):
    parent = _make_parent()
    parent.settings.row_color_style = "Banding"
    renderer = DriverRowRenderer(parent)
    driver = _make_driver("porsche 911 gt3 r", manufacturer="POR")

    even_row = renderer.create_row(driver, row_index=0)
    odd_row = renderer.create_row(driver, row_index=1)

    assert "background-color: #000000;" in even_row.styleSheet()
    assert "background-color: #333333;" in odd_row.styleSheet()

    even_row.deleteLater()
    odd_row.deleteLater()


def test_create_row_falls_back_to_text_when_logo_missing(qapp):
    renderer = DriverRowRenderer(_make_parent())
    driver = _make_driver("hyundai elantra n", manufacturer="HYU")

    row = renderer.create_row(driver)
    layout = row.layout()
    manufacturer_label = layout.itemAtPosition(0, 1).widget()

    pixmap = manufacturer_label.pixmap()
    assert pixmap is None or pixmap.isNull()
    assert manufacturer_label.text() == "HYU"
    row.deleteLater()


def test_create_row_uses_triangle_symbol_for_positions_gained(qapp):
    parent = _make_parent()
    parent.settings.show_positions_gained = True
    renderer = DriverRowRenderer(parent)
    driver = _make_driver("porsche 911 gt3 r", manufacturer="POR", positions_gained="↑3")

    row = renderer.create_row(driver)
    layout = row.layout()
    positions_label = layout.itemAtPosition(0, 1).widget()

    assert positions_label.text() == "▲ 3"
    assert "font-size: calc(9pt + 2pt);" in positions_label.styleSheet()
    row.deleteLater()


def test_create_row_shows_pit_status_in_gap_and_interval_columns(qapp):
    parent = _make_parent()
    parent.settings.show_gap = True
    parent.settings.show_division_gap = True
    parent.settings.show_interval = True
    parent.settings.show_division_interval = True
    renderer = DriverRowRenderer(parent)
    driver = _make_driver(
        "porsche 911 gt3 r",
        manufacturer="POR",
        pit_lap="TOW",
        gap_to_leader="5.4",
        division_gap_to_leader="1.2",
        interval="0.8",
        division_interval="0.4",
    )

    row = renderer.create_row(driver)
    layout = row.layout()

    assert layout.itemAtPosition(0, 5).widget().text() == "TOW"
    assert layout.itemAtPosition(0, 6).widget().text() == "TOW"
    assert layout.itemAtPosition(0, 7).widget().text() == "TOW"
    assert layout.itemAtPosition(0, 8).widget().text() == "TOW"
    assert "#FF3B30" in layout.itemAtPosition(0, 5).widget().styleSheet()
    row.deleteLater()


def test_create_row_shows_pit_status_in_gap_and_interval_columns_for_pit(qapp):
    parent = _make_parent()
    parent.settings.show_gap = True
    parent.settings.show_division_gap = True
    parent.settings.show_interval = True
    parent.settings.show_division_interval = True
    renderer = DriverRowRenderer(parent)
    driver = _make_driver(
        "porsche 911 gt3 r",
        manufacturer="POR",
        pit_lap="PIT",
        gap_to_leader="5.4",
        division_gap_to_leader="1.2",
        interval="0.8",
        division_interval="0.4",
    )

    row = renderer.create_row(driver)
    layout = row.layout()

    assert layout.itemAtPosition(0, 5).widget().text() == "PIT"
    assert layout.itemAtPosition(0, 6).widget().text() == "PIT"
    assert layout.itemAtPosition(0, 7).widget().text() == "PIT"
    assert layout.itemAtPosition(0, 8).widget().text() == "PIT"
    row.deleteLater()


def test_create_row_restores_gap_and_interval_values_when_not_in_pit(qapp):
    parent = _make_parent()
    parent.settings.show_gap = True
    parent.settings.show_division_gap = True
    parent.settings.show_interval = True
    parent.settings.show_division_interval = True
    renderer = DriverRowRenderer(parent)
    driver = _make_driver(
        "porsche 911 gt3 r",
        manufacturer="POR",
        pit_lap="OUT",
        gap_to_leader="5.4",
        division_gap_to_leader="1.2",
        interval="0.8",
        division_interval="0.4",
    )

    row = renderer.create_row(driver)
    layout = row.layout()

    assert layout.itemAtPosition(0, 5).widget().text() == "5.4"
    assert layout.itemAtPosition(0, 6).widget().text() == "1.2"
    assert layout.itemAtPosition(0, 7).widget().text() == "0.8"
    assert layout.itemAtPosition(0, 8).widget().text() == "0.4"
    row.deleteLater()
