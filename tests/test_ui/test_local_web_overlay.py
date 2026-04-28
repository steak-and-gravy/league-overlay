"""Tests for the local web overlay server and snapshot."""

import json
import urllib.request
from types import SimpleNamespace

from config.settings import AppSettings
from core.driver_state import DriverState
import ui.local_web_overlay as local_web_overlay
from ui.local_web_overlay import (
    LOCAL_MACHINE_HOST,
    LOCAL_NETWORK_BIND_HOST,
    LocalWebOverlayServer,
    build_local_web_snapshot,
    get_local_network_ip,
    get_local_network_url,
)


def test_build_local_web_snapshot_uses_visible_columns_and_driver_values():
    settings = AppSettings(show_car_number=True, show_interval=True)
    driver = DriverState(
        car_idx=12,
        driver_info={"UserName": "Test Driver", "CarNumber": "42"},
        position=3,
        division_position=1,
        division_color="#FF8C00",
        interval="1.2s",
        recent_lap_flash="1:29.9",
        recent_lap_flash_state="faster",
        is_player=True,
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        broadcast_header_title="Test League",
        broadcast_header_logo="https://example.com/logo.png",
        broadcast_header_accent_color="#FF8C00",
        _last_status_text="Race - Lap 4",
        _last_status_color="yellow",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    assert snapshot["title"] == "Test League"
    assert snapshot["logo"] == "https://example.com/logo.png"
    assert snapshot["statusText"] == "Race - Lap 4"
    assert snapshot["statusColor"] == "yellow"
    assert snapshot["broadcastSessionColor"] == "white"
    assert any(column["id"] == "interval" for column in snapshot["columns"])
    cells = {cell["id"]: cell["value"] for cell in snapshot["drivers"][0]["cells"]}
    driver_name_cell = next(cell for cell in snapshot["drivers"][0]["cells"] if cell["id"] == "driver_name")
    assert cells["driver_name"] == "Test Driver"
    assert driver_name_cell["flash"] == "1:29.9"
    assert driver_name_cell["flashState"] == "faster"
    assert cells["car_number"] == "42"
    assert cells["interval"] == "1.2s"
    assert snapshot["drivers"][0]["recentLapFlashState"] == "faster"


def test_build_local_web_snapshot_matches_broadcast_session_status_colors():
    settings = AppSettings()
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[],
        _last_status_text="CAUTION - Lap 4",
        _last_status_color="yellow",
        _last_footer_data={},
    )

    caution_snapshot = build_local_web_snapshot(overlay)
    overlay._last_status_text = "Update available: v1.2.3"
    update_snapshot = build_local_web_snapshot(overlay)

    assert caution_snapshot["broadcastSessionColor"] == "#FFD700"
    assert update_snapshot["broadcastSessionColor"] == "#00FF00"


def test_get_local_network_url_uses_lan_ip(monkeypatch):
    monkeypatch.setattr(local_web_overlay, "_local_ip_from_udp_route", lambda: "192.168.1.211")
    monkeypatch.setattr(local_web_overlay, "_local_ip_from_hostname", lambda: "10.0.0.12")

    assert get_local_network_ip() == "192.168.1.211"
    assert get_local_network_url(8765) == "http://192.168.1.211:8765/"


def test_get_local_network_ip_falls_back_to_loopback(monkeypatch):
    monkeypatch.setattr(local_web_overlay, "_local_ip_from_udp_route", lambda: "")
    monkeypatch.setattr(local_web_overlay, "_local_ip_from_hostname", lambda: "")

    assert get_local_network_ip() == LOCAL_MACHINE_HOST


def test_build_local_web_snapshot_matches_default_style_cells_and_rows():
    settings = AppSettings(
        show_positions_gained=True,
        show_car_number=True,
    )
    drivers = [
        DriverState(
            car_idx=1,
            driver_info={"UserName": "Even Driver", "CarNumber": "11"},
            position=1,
            division_position=1,
            division_color="#FF8C00",
            positions_gained="—",
        ),
        DriverState(
            car_idx=2,
            driver_info={"UserName": "Odd Driver", "CarNumber": "22"},
            position=2,
            division_position=2,
            division_color="#45B3E0",
            positions_gained="▲ 1",
        ),
    ]
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=drivers,
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    even_cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    odd_cells = {cell["id"]: cell for cell in snapshot["drivers"][1]["cells"]}

    assert snapshot["drivers"][0]["rowStyle"]["background"] == "rgba(0, 0, 0, 0.8)"
    assert snapshot["drivers"][1]["rowStyle"]["background"] == "rgba(51, 51, 51, 0.8)"
    assert even_cells["pos"]["style"]["color"] == "#000000"
    assert even_cells["pos"]["style"]["backgroundColor"] == "rgba(255, 255, 255, 0.9)"
    assert odd_cells["div_pos"]["style"]["backgroundColor"] == "rgba(69, 179, 224, 0.9)"
    assert odd_cells["positions_gained"]["style"]["backgroundColor"] == "rgba(51, 51, 51, 0.8)"
    assert odd_cells["positions_gained"]["style"]["color"] == settings.faster_color


def test_build_local_web_snapshot_applies_half_opacity_to_overall_and_class_position_backgrounds():
    settings = AppSettings(opacity=0.25)
    driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Transparent Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#FF8C00",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    assert cells["pos"]["style"]["color"] == "#000000"
    assert cells["pos"]["style"]["backgroundColor"] == "rgba(255, 255, 255, 0.625)"
    assert cells["div_pos"]["style"]["backgroundColor"] == "rgba(255, 140, 0, 0.625)"


def test_build_local_web_snapshot_keeps_half_visible_position_backgrounds_at_zero_opacity():
    settings = AppSettings(opacity=0.0)
    driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Transparent Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#FF8C0080",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    assert cells["pos"]["style"]["backgroundColor"] == "rgba(255, 255, 255, 0.5)"
    assert cells["div_pos"]["style"]["backgroundColor"] == "rgba(255, 140, 0, 0.25098039215686274)"


def test_build_local_web_snapshot_preserves_division_color_alpha_for_class_position_background():
    settings = AppSettings(opacity=0.25)
    driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Transparent Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#FF8C0080",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    assert cells["div_pos"]["style"]["backgroundColor"] == "rgba(255, 140, 0, 0.3137254901960784)"


def test_build_local_web_snapshot_default_player_uses_player_highlight():
    settings = AppSettings()
    driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Player Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#45B3E0",
        is_player=True,
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    driver_cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    assert snapshot["drivers"][0]["rowStyle"]["background"].startswith(
        "linear-gradient(90deg, #112c38"
    )
    assert driver_cells["driver_name"]["style"]["backgroundColor"] == "#112c38"


def test_build_local_web_snapshot_reflects_other_row_color_styles():
    base_driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Styled Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#45B3E0",
    )

    dark_snapshot = build_local_web_snapshot(SimpleNamespace(
        settings=AppSettings(row_color_style="Dark"),
        displayed_data=[base_driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    ))
    alternate_snapshot = build_local_web_snapshot(SimpleNamespace(
        settings=AppSettings(row_color_style="Alternate"),
        displayed_data=[base_driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    ))
    outline_snapshot = build_local_web_snapshot(SimpleNamespace(
        settings=AppSettings(row_color_style="Outline"),
        displayed_data=[base_driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    ))

    dark_name_cell = next(
        cell for cell in dark_snapshot["drivers"][0]["cells"]
        if cell["id"] == "driver_name"
    )
    alternate_name_cell = next(
        cell for cell in alternate_snapshot["drivers"][0]["cells"]
        if cell["id"] == "driver_name"
    )

    assert dark_name_cell["style"]["color"] == "#45B3E0"
    assert alternate_snapshot["drivers"][0]["rowStyle"]["background"] == "rgba(69, 179, 224, 0.8)"
    assert alternate_name_cell["style"]["color"] == "#000000"
    assert outline_snapshot["drivers"][0]["rowStyle"]["border"] == "1px solid #45B3E0"


def test_build_local_web_snapshot_alternate_highlight_rows_get_white_wrapper():
    settings = AppSettings(row_color_style="Alternate")
    driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Player Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        division_color="#45B3E0",
        is_player=True,
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    assert snapshot["drivers"][0]["rowStyle"]["background"] == "rgba(69, 179, 224, 0.8)"
    assert snapshot["drivers"][0]["rowStyle"]["border"] == "2px solid #FFFFFF"


def test_build_local_web_snapshot_gap_columns_apply_pit_tow_text_overrides():
    settings = AppSettings(
        show_gap=True,
        show_division_gap=True,
        show_interval=True,
        show_division_interval=True,
    )
    pit_driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Pit Driver", "CarNumber": "11"},
        position=1,
        division_position=1,
        gap_to_leader="Leader",
        division_gap_to_leader="Leader",
        interval="0.4",
        division_interval="0.4",
        pit_lap="PIT",
    )
    tow_driver = DriverState(
        car_idx=2,
        driver_info={"UserName": "Tow Driver", "CarNumber": "22"},
        position=2,
        division_position=2,
        gap_to_leader="12.1",
        division_gap_to_leader="12.1",
        interval="2.0",
        division_interval="2.0",
        pit_lap="TOW",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[pit_driver, tow_driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    pit_cells = {cell["id"]: cell for cell in snapshot["drivers"][0]["cells"]}
    tow_cells = {cell["id"]: cell for cell in snapshot["drivers"][1]["cells"]}
    for col_id in ("gap", "div_gap", "interval", "div_interval"):
        assert pit_cells[col_id]["value"] == "PIT"
        assert tow_cells[col_id]["value"] == "TOW"
        assert tow_cells[col_id]["style"]["color"] == "#FF3B30"


def test_build_local_web_snapshot_rejects_non_http_broadcast_logo_url():
    settings = AppSettings()
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[],
        broadcast_header_logo="file:///tmp/not-used.png",
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    assert snapshot["logo"] == ""


def test_build_local_web_snapshot_prefers_current_render_data():
    settings = AppSettings()
    displayed_driver = DriverState(
        car_idx=1,
        driver_info={"UserName": "Full List", "CarNumber": "1"},
        position=1,
        division_position=1,
    )
    rendered_driver = DriverState(
        car_idx=2,
        driver_info={"UserName": "Rendered Slice", "CarNumber": "2"},
        position=2,
        division_position=2,
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[displayed_driver],
        _local_web_render_data=[rendered_driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    cells = {cell["id"]: cell["value"] for cell in snapshot["drivers"][0]["cells"]}
    assert cells["driver_name"] == "Rendered Slice"


def test_build_local_web_snapshot_honors_recent_lap_update_setting():
    settings = AppSettings(show_recent_lap_flash=False)
    driver = DriverState(
        car_idx=12,
        driver_info={"UserName": "Test Driver", "CarNumber": "42"},
        position=3,
        division_position=1,
        recent_lap_flash="1:29.9",
        recent_lap_flash_state="faster",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    driver_name_cell = next(cell for cell in snapshot["drivers"][0]["cells"] if cell["id"] == "driver_name")
    assert driver_name_cell["value"] == "Test Driver"
    assert driver_name_cell["flash"] == ""
    assert driver_name_cell["flashState"] == ""
    assert snapshot["drivers"][0]["recentLapFlashState"] == ""


def test_build_local_web_snapshot_uses_manufacturer_logo_asset():
    settings = AppSettings(show_car_manufacturer=True)
    driver = DriverState(
        car_idx=12,
        driver_info={"UserName": "Test Driver", "CarNumber": "42"},
        position=3,
        division_position=1,
        car_manufacturer="POR",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    manufacturer_cell = next(
        cell for cell in snapshot["drivers"][0]["cells"]
        if cell["id"] == "car_manufacturer"
    )
    assert manufacturer_cell["value"] == "POR"
    assert manufacturer_cell["logoUrl"] == "/assets/manufacturer_logos/porsche.png"


def test_build_local_web_snapshot_falls_back_when_manufacturer_logo_missing():
    settings = AppSettings(show_car_manufacturer=True)
    driver = DriverState(
        car_idx=12,
        driver_info={"UserName": "Test Driver", "CarNumber": "42"},
        position=3,
        division_position=1,
        car_manufacturer="ORP",
    )
    overlay = SimpleNamespace(
        settings=settings,
        displayed_data=[driver],
        _last_status_text="Race - Lap 4",
        _last_status_color="green",
        _last_footer_data={},
    )

    snapshot = build_local_web_snapshot(overlay)

    manufacturer_cell = next(
        cell for cell in snapshot["drivers"][0]["cells"]
        if cell["id"] == "car_manufacturer"
    )
    assert manufacturer_cell["value"] == "ORP"
    assert manufacturer_cell["logoUrl"] == ""


def test_local_web_overlay_server_serves_html_and_state():
    server = LocalWebOverlayServer()
    snapshot = {
        "title": "Served",
        "columns": [],
        "drivers": [],
    }

    try:
        server.update(snapshot)
        server.start(0)

        assert server.bind_host in {LOCAL_NETWORK_BIND_HOST, LOCAL_MACHINE_HOST}
        assert server._server.server_address[0] == server.bind_host

        with urllib.request.urlopen(server.url, timeout=2) as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(server.url + "api/state", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert "BB's League Overlay" in html
        assert '<link rel="icon" href="/favicon.ico">' in html
        assert "background: #2b2b2b;" in html
        assert '<table class="table header-table">' in html
        assert 'id="tableViewport" class="table-viewport"' in html
        assert "overflow-y: auto;" in html
        assert "position: sticky;" not in html
        assert ".driver-name-text" in html
        assert ".recent-lap-flash" in html
        assert "position: absolute;" in html
        assert "padding-left: 8px;" in html
        assert "function effectiveCellBackground(cellElement, rowElement, data)" in html
        assert "flashSpan.style.background = effectiveCellBackground(td, tr, data);" in html
        assert "flashSpan.style.float" not in html
        assert "const AUTO_CENTER_PAUSE_MS = 5000;" in html
        assert "function centerTargetRow()" in html
        assert "rows.querySelector('tr.spectated') || rows.querySelector('tr.player')" in html
        assert "requestAnimationFrame(centerTargetRow);" in html
        assert "footer.style.background = data.headerColor;" in html
        assert payload == snapshot
    finally:
        server.stop()


def test_local_web_overlay_server_serves_manufacturer_logo_asset():
    server = LocalWebOverlayServer()

    try:
        server.start(0)

        with urllib.request.urlopen(
            server.url + "assets/manufacturer_logos/porsche.png",
            timeout=2,
        ) as response:
            image_bytes = response.read(8)

        assert image_bytes == b"\x89PNG\r\n\x1a\n"
    finally:
        server.stop()


def test_local_web_overlay_server_serves_app_favicon():
    server = LocalWebOverlayServer()

    try:
        server.start(0)

        with urllib.request.urlopen(server.url + "favicon.ico", timeout=2) as response:
            icon_header = response.read(4)

        assert icon_header == b"\x00\x00\x01\x00"
    finally:
        server.stop()


def test_local_web_overlay_server_falls_back_to_same_machine_access(monkeypatch):
    real_server_class = local_web_overlay._LocalNetworkThreadingHTTPServer

    def server_factory(address, handler):
        if address[0] == LOCAL_NETWORK_BIND_HOST:
            raise PermissionError("LAN bind blocked")
        return real_server_class(address, handler)

    monkeypatch.setattr(local_web_overlay, "_LocalNetworkThreadingHTTPServer", server_factory)
    server = LocalWebOverlayServer()

    try:
        server.start(0)

        assert server.bind_host == LOCAL_MACHINE_HOST
        with urllib.request.urlopen(server.url + "api/state", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["title"] == "BB's League Overlay"
    finally:
        server.stop()
