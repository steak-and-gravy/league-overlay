"""Local web overlay server for browser-source display."""

from __future__ import annotations

import json
import ipaddress
import socket
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from config.constants import COLUMN_REGISTRY, UI_COLORS
from config.logging_config import get_logger
from core.driver_state import DriverState
from core.gap_calculator import GapCalculator
from ui.driver_row_renderer import DriverRowRenderer

logger = get_logger(__name__)

LOCAL_NETWORK_BIND_HOST = "0.0.0.0"
LOCAL_MACHINE_HOST = "127.0.0.1"
MANUFACTURER_ASSET_ROUTE = "/assets/manufacturer_logos/"
APP_ICON_PATH = Path(__file__).resolve().parent.parent / "app_icon.ico"


def get_local_network_url(port: int) -> str:
    """Return a LAN-facing URL for the local web overlay when possible."""
    return f"http://{get_local_network_ip()}:{port}/"


def get_local_network_ip() -> str:
    """Best-effort local IPv4 address for other devices on the private network."""
    udp_ip = _local_ip_from_udp_route()
    if udp_ip:
        return udp_ip

    hostname_ip = _local_ip_from_hostname()
    if hostname_ip:
        return hostname_ip

    return LOCAL_MACHINE_HOST


def _local_ip_from_udp_route() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = sock.getsockname()[0]
    except OSError:
        return ""

    return candidate if _is_usable_lan_ip(candidate) else ""


def _local_ip_from_hostname() -> str:
    try:
        addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return ""

    candidates = []
    for address in addresses:
        candidate = address[4][0]
        if _is_usable_lan_ip(candidate):
            candidates.append(candidate)

    for candidate in candidates:
        if ipaddress.ip_address(candidate).is_private:
            return candidate

    return candidates[0] if candidates else ""


def _is_usable_lan_ip(candidate: str) -> bool:
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return address.version == 4 and not address.is_loopback


def _rgba(hex_color: str, opacity: float) -> str:
    color = hex_color.lstrip("#")
    if len(color) != 6:
        return hex_color
    try:
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
    except ValueError:
        return hex_color
    return f"rgba({red}, {green}, {blue}, {opacity})"


def build_local_web_snapshot(overlay: Any) -> Dict[str, Any]:
    """Build a JSON-safe snapshot from already-rendered overlay state."""
    settings = overlay.settings
    status_text = getattr(overlay, "_last_status_text", "Connecting to iRacing...")
    drivers = getattr(overlay, "_local_web_render_data", None)
    if drivers is None:
        drivers = getattr(overlay, "displayed_data", []) or []
    visible_columns = []

    for col_id in settings.column_order:
        col_def = COLUMN_REGISTRY.get(col_id)
        if col_def is None:
            continue
        if col_def.settings_key and not getattr(settings, col_def.settings_key, False):
            continue
        visible_columns.append({
            "id": col_def.id,
            "header": col_def.header,
            "className": f"col-{col_def.id.replace('_', '-')}",
        })

    return {
        "title": getattr(overlay, "broadcast_header_title", "BB's League Overlay"),
        "logo": _safe_broadcast_logo_url(getattr(overlay, "broadcast_header_logo", "")),
        "accentColor": getattr(overlay, "broadcast_header_accent_color", "#FF8C00"),
        "statusText": status_text,
        "statusColor": getattr(overlay, "_last_status_color", "orange"),
        "broadcastSessionColor": _broadcast_session_text_color(status_text),
        "showBroadcastHeader": settings.show_broadcast_header,
        "showFooter": settings.show_footer,
        "opacity": settings.opacity,
        "backgroundColor": _rgba(UI_COLORS.BACKGROUND_BLACK, settings.opacity),
        "headerColor": _rgba(UI_COLORS.HEADER_DARK_GRAY, settings.opacity),
        "fasterColor": settings.faster_color,
        "slowerColor": settings.slower_color,
        "columns": visible_columns,
        "drivers": [
            _serialize_driver(driver, visible_columns, settings, row_index)
            for row_index, driver in enumerate(drivers)
        ],
        "footer": getattr(overlay, "_last_footer_data", {}),
    }


def _broadcast_session_text_color(status_text: str) -> str:
    """Return the web color that matches BroadcastHeaderWidget session text."""
    normalized = status_text.upper()
    if "CAUTION" in normalized:
        return "#FFD700"
    if "UPDATE AVAILABLE" in normalized:
        return "#00FF00"
    return "white"


def _serialize_driver(driver: DriverState, columns: List[Dict[str, str]],
                      settings: Any, row_index: int) -> Dict[str, Any]:
    flash_visible = settings.show_recent_lap_flash and bool(driver.recent_lap_flash)
    manufacturer_logo_url = _manufacturer_logo_url(driver)
    style_context = _web_style_context(driver, settings, row_index)
    values = {
        "pos": driver.position or "",
        "positions_gained": driver.positions_gained,
        "div_pos": driver.division_position or "",
        "driver_name": driver.team_name if driver.team_name > "" else driver.driver_name,
        "car_manufacturer": driver.car_manufacturer,
        "rating": driver.combined_rating,
        "car_number": driver.car_number,
        "gap": _gap_display_text(driver, driver.gap_to_leader),
        "div_gap": _gap_display_text(driver, driver.division_gap_to_leader),
        "interval": _gap_display_text(driver, driver.interval),
        "div_interval": _gap_display_text(driver, driver.division_interval),
        "best_lap": driver.best_lap,
        "last_lap": driver.last_lap,
        "delta": driver.delta,
        "pit_lap": driver.pit_lap,
    }
    return {
        "carIdx": driver.car_idx,
        "isPlayer": driver.is_player,
        "isSpectated": driver.is_spectated,
        "isFinished": driver.is_finished,
        "divisionColor": driver.division_color or "#FFFFFF",
        "manufacturerColor": driver.car_manufacturer_color,
        "recentLapFlashState": driver.recent_lap_flash_state if flash_visible else "",
        "showCarNumberOutline": driver.show_car_number_outline,
        "rowStyle": style_context["rowStyle"],
        "cells": [
            {
                "id": column["id"],
                "value": str(values.get(column["id"], "")),
                "flash": driver.recent_lap_flash if column["id"] == "driver_name" and flash_visible else "",
                "flashState": driver.recent_lap_flash_state if column["id"] == "driver_name" and flash_visible else "",
                "logoUrl": manufacturer_logo_url if column["id"] == "car_manufacturer" else "",
                "style": _cell_style(driver, settings, column["id"], style_context),
            }
            for column in columns
        ],
    }


def _web_style_context(driver: DriverState, settings: Any, row_index: int) -> Dict[str, Any]:
    style_name = getattr(settings, "row_color_style", "Default")
    opacity = getattr(settings, "opacity", 0.8)
    division_color = driver.division_color or "#FFFFFF"
    label_bg = _bg_color("#000000", opacity)
    row_style = {"background": _bg_color("#000000", opacity), "border": ""}
    text_color = "white"
    gap_color = "white"
    label_border = ""

    if style_name == "Banding" and driver.is_player:
        row_style["background"] = _gradient_background(division_color, settings)
        label_bg = _blend_color_with_black(division_color, getattr(settings, "highlight", 0.25))
    elif style_name == "Banding":
        banded_bg = "#000000" if row_index % 2 == 0 else UI_COLORS.HEADER_DARK_GRAY
        label_bg = _bg_color(banded_bg, opacity)
        row_style["background"] = label_bg
    elif style_name == "Dark":
        text_color = division_color
        if driver.is_player or driver.is_spectated:
            row_style["background"] = _gradient_background(division_color, settings)
            label_bg = _blend_color_with_black(division_color, getattr(settings, "highlight", 0.25))
        else:
            row_style["background"] = _bg_color("#000000", opacity)
    elif style_name == "Alternate":
        label_bg = _bg_color(division_color, opacity)
        row_style["background"] = label_bg
        if driver.is_player or driver.is_spectated:
            row_style["border"] = "2px solid #FFFFFF"
        text_color = "#000000"
        gap_color = "#000000"
    elif style_name == "Outline":
        text_color = division_color
        label_bg = "transparent"
        label_border = "none"
        if driver.is_player or driver.is_spectated:
            row_style["background"] = _gradient_background(division_color, settings)
        else:
            row_style["background"] = _bg_color("#000000", opacity)
            row_style["border"] = f"1px solid {division_color}"
    elif driver.is_player:
        row_style["background"] = _gradient_background(division_color, settings)
        label_bg = _blend_color_with_black(division_color, getattr(settings, "highlight", 0.25))

    if style_name in ("Default", "Banding") and driver.is_spectated and not driver.is_player:
        row_style["border"] = "2px solid yellow"

    return {
        "styleName": style_name,
        "rowStyle": row_style,
        "labelBg": label_bg,
        "labelBorder": label_border,
        "textColor": text_color,
        "gapColor": gap_color,
        "opacity": opacity,
    }


def _cell_style(driver: DriverState, settings: Any, column_id: str,
                style_context: Dict[str, Any]) -> Dict[str, str]:
    label_bg = style_context["labelBg"]
    label_border = style_context["labelBorder"]
    text_color = style_context["textColor"]
    gap_color = style_context["gapColor"]
    style = {
        "color": text_color,
        "backgroundColor": label_bg,
        "border": label_border,
    }
    style_name = style_context["styleName"]
    opacity = style_context["opacity"]
    division_color = driver.division_color or "#FFFFFF"

    if column_id == "pos" and style_name in ("Default", "Banding"):
        style["color"] = "#000000"
        style["backgroundColor"] = _bg_color("#FFFFFF", opacity)
    elif column_id == "div_pos" and style_name in ("Default", "Banding"):
        style["color"] = "white"
        style["backgroundColor"] = _bg_color(division_color, opacity)
        style["border"] = f"2px solid {division_color}"
    elif column_id == "car_number" and style_name in ("Default", "Banding"):
        style["color"] = "white"
        style["backgroundColor"] = _bg_color("#000000", opacity)
        pit_indicator_enabled = getattr(settings, "pit_stop_indicator", True)
        if not pit_indicator_enabled or driver.show_car_number_outline:
            style["border"] = f"2px solid {division_color}"
    elif column_id == "positions_gained":
        if driver.positions_gained.startswith("▲"):
            style["color"] = settings.faster_color
        elif driver.positions_gained.startswith("▼"):
            style["color"] = settings.slower_color
    elif column_id == "car_manufacturer":
        style["color"] = driver.car_manufacturer_color
    elif column_id == "rating":
        style["color"] = "white"
        style["backgroundColor"] = GapCalculator.get_license_background_color(driver.lic_level)
    elif column_id in ("gap", "div_gap", "interval", "div_interval"):
        if driver.pit_lap == "TOW":
            style["color"] = "#FF3B30"
        else:
            style["color"] = gap_color
    elif column_id == "delta":
        if driver.delta.startswith("-"):
            style["color"] = settings.faster_color
        elif driver.delta.startswith("+"):
            style["color"] = settings.slower_color
        else:
            style["color"] = gap_color
    elif column_id in ("last_lap", "best_lap"):
        style["color"] = gap_color
    elif column_id == "pit_lap":
        if driver.pit_lap == "OUT":
            style["color"] = "#FF8200"
        elif driver.pit_lap == "TOW":
            style["color"] = "#FF3B30"

    return style


def _gap_display_text(driver: DriverState, default_text: str) -> str:
    if driver.pit_lap == "TOW":
        return "TOW"
    if driver.pit_lap == "PIT":
        return "PIT"
    return default_text


def _bg_color(hex_color: str, opacity: float) -> str:
    return _rgba(hex_color, opacity)


def _blend_color_with_black(color_hex: str, amount: float = 0.15) -> str:
    color_hex = color_hex.lstrip("#")
    try:
        red = int(color_hex[0:2], 16)
        green = int(color_hex[2:4], 16)
        blue = int(color_hex[4:6], 16)
    except (ValueError, IndexError):
        return "#000000"
    return f"#{int(red * amount):02x}{int(green * amount):02x}{int(blue * amount):02x}"


def _gradient_background(color_hex: str, settings: Any) -> str:
    tinted = _blend_color_with_black(color_hex, getattr(settings, "highlight", 0.25))
    return f"linear-gradient(90deg, {tinted}, #1a1a1a, {tinted})"


def _safe_broadcast_logo_url(logo_url: str) -> str:
    if not logo_url:
        return ""
    parsed = urlparse(logo_url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return logo_url
    return ""


def _manufacturer_logo_url(driver: DriverState) -> str:
    logo_path = DriverRowRenderer._get_manufacturer_logo_path(driver)
    if logo_path is None:
        return ""

    try:
        logo_name = logo_path.relative_to(DriverRowRenderer.LOGO_DIRECTORY).name
    except ValueError:
        return ""

    return f"{MANUFACTURER_ASSET_ROUTE}{logo_name}"


@dataclass
class _SharedState:
    snapshot: Dict[str, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    request_slots: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(8)
    )


class LocalWebOverlayServer:
    """Serve the live overlay as a local-network browser page."""

    def __init__(self) -> None:
        self._state = _SharedState(snapshot=_empty_snapshot())
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: Optional[int] = None
        self.bind_host: str = LOCAL_NETWORK_BIND_HOST

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def url(self) -> str:
        port = self.port or 0
        return f"http://{LOCAL_MACHINE_HOST}:{port}/"

    def start(self, port: int) -> None:
        if self.is_running and self.port == port:
            return

        handler = self._make_handler(self._state)
        server, bind_host = self._bind_server(port, handler)
        server.daemon_threads = True
        thread = threading.Thread(
            target=server.serve_forever,
            name="LocalWebOverlayServer",
            daemon=True,
        )
        old_server = self._server
        old_thread = self._thread
        self._server = server
        self._thread = thread
        self.port = server.server_address[1]
        self.bind_host = bind_host
        thread.start()
        self._stop_server(old_server, old_thread)
        if bind_host == LOCAL_NETWORK_BIND_HOST:
            logger.info(f"Local web overlay started at {self.url} and is reachable on the local network")
        else:
            logger.info(f"Local web overlay started at {self.url} for same-machine access only")

    def stop(self) -> None:
        if self._server is None:
            return
        logger.info("Stopping local web overlay")
        self._stop_server(self._server, self._thread)
        self._server = None
        self._thread = None
        self.port = None
        self.bind_host = LOCAL_NETWORK_BIND_HOST

    def update(self, snapshot: Dict[str, Any]) -> None:
        with self._state.lock:
            self._state.snapshot = snapshot

    @staticmethod
    def _make_handler(state: _SharedState):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib handler API
                acquired = state.request_slots.acquire(blocking=False)
                if not acquired:
                    self.send_error(503, "Local web overlay is busy")
                    return
                try:
                    self.connection.settimeout(3.0)
                    if self.path in ("/", "/index.html"):
                        self._send_html(_render_html())
                        return
                    if urlparse(self.path).path == "/favicon.ico":
                        self._send_app_icon()
                        return
                    if self.path == "/api/state":
                        with state.lock:
                            payload = json.dumps(state.snapshot).encode("utf-8")
                        self._send_bytes(payload, "application/json; charset=utf-8")
                        return
                    if urlparse(self.path).path.startswith(MANUFACTURER_ASSET_ROUTE):
                        self._send_manufacturer_logo()
                        return
                    self.send_error(404)
                finally:
                    state.request_slots.release()

            def log_message(self, format, *args):  # noqa: A002 - stdlib handler API
                logger.debug("Local web overlay: " + format, *args)

            def _send_html(self, html: str) -> None:
                self._send_bytes(html.encode("utf-8"), "text/html; charset=utf-8")

            def _send_bytes(self, body: bytes, content_type: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_app_icon(self) -> None:
                if not APP_ICON_PATH.is_file():
                    self.send_error(404)
                    return
                self._send_bytes(APP_ICON_PATH.read_bytes(), "image/x-icon")

            def _send_manufacturer_logo(self) -> None:
                request_path = urlparse(self.path).path
                logo_name = unquote(request_path.removeprefix(MANUFACTURER_ASSET_ROUTE))
                if not logo_name or "/" in logo_name or "\\" in logo_name:
                    self.send_error(404)
                    return

                logo_path = DriverRowRenderer.LOGO_DIRECTORY / logo_name
                if logo_path.suffix.lower() != ".png" or not logo_path.is_file():
                    self.send_error(404)
                    return

                self._send_bytes(logo_path.read_bytes(), "image/png")

        return Handler

    def _bind_server(self, port: int, handler) -> tuple[ThreadingHTTPServer, str]:
        try:
            return _LocalNetworkThreadingHTTPServer((LOCAL_NETWORK_BIND_HOST, port), handler), LOCAL_NETWORK_BIND_HOST
        except PermissionError as e:
            logger.warning(
                f"Local network bind failed ({e}); falling back to same-machine access only"
            )
            return _LocalNetworkThreadingHTTPServer((LOCAL_MACHINE_HOST, port), handler), LOCAL_MACHINE_HOST

    @staticmethod
    def _stop_server(server: Optional[ThreadingHTTPServer],
                     thread: Optional[threading.Thread]) -> None:
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)


class _LocalNetworkThreadingHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that avoids reverse-DNS lookup during bind."""

    def server_bind(self) -> None:
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()
        self.server_name = LOCAL_NETWORK_BIND_HOST
        self.server_port = self.server_address[1]


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "title": "BB's League Overlay",
        "logo": "",
        "accentColor": "#FF8C00",
        "statusText": "Connecting to iRacing...",
        "statusColor": "orange",
        "broadcastSessionColor": "white",
        "showBroadcastHeader": False,
        "showFooter": False,
        "opacity": 0.8,
        "backgroundColor": "rgba(0, 0, 0, 0.8)",
        "headerColor": "rgba(51, 51, 51, 0.8)",
        "fasterColor": "#00FF00",
        "slowerColor": "#FF2F18",
        "columns": [],
        "drivers": [],
        "footer": {},
    }


def _render_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="/favicon.ico">
  <title>BB's League Overlay</title>
  <style>
    html, body {{
      margin: 0;
      height: 100%;
      min-height: 100%;
      background: #2b2b2b;
      color: #fff;
      font-family: Arial, Helvetica, sans-serif;
      overflow: hidden;
    }}
    #overlay {{
      min-width: 320px;
      height: var(--viewport-height, 100vh);
      height: var(--viewport-height, 100dvh);
      max-height: var(--viewport-height, 100vh);
      max-height: var(--viewport-height, 100dvh);
      display: flex;
      flex-direction: column;
      background: rgba(0, 0, 0, 0.8);
    }}
    .broadcast {{
      display: none;
      align-items: center;
      gap: 12px;
      padding: 8px 10px;
      background: rgba(51, 51, 51, 0.8);
      border-bottom: 3px solid #FF8C00;
    }}
    .broadcast.visible {{ display: flex; }}
    .broadcast img {{
      width: 44px;
      height: 44px;
      object-fit: contain;
    }}
    .broadcast-title {{
      font-size: 12pt;
      font-weight: 700;
      line-height: 1.1;
    }}
    .broadcast-status {{
      margin-top: 2px;
      color: #ddd;
      font-size: 9pt;
    }}
    .status {{
      padding: 5px;
      text-align: center;
      font-size: 10pt;
      font-weight: 700;
      background: rgba(0, 0, 0, 0.8);
      color: #00FF00;
    }}
    .status.hidden {{ display: none; }}
    .table-viewport {{
      flex: 1 1 auto;
      min-height: 0;
      overflow-x: hidden;
      overflow-y: auto;
      overscroll-behavior: contain;
      -webkit-overflow-scrolling: touch;
      background: transparent;
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      background: transparent;
    }}
    .header-table {{
      flex: 0 0 auto;
    }}
    th {{
      padding: 2px 4px;
      background: rgba(51, 51, 51, 0.8);
      color: #fff;
      font-size: 9pt;
      font-weight: 700;
      text-align: center;
      white-space: nowrap;
    }}
    td {{
      padding: 3px 4px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      color: #fff;
      font-size: 10pt;
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      text-align: center;
    }}
    .col-driver-name {{
      width: auto;
      text-align: left;
      position: relative;
    }}
    .driver-name-text {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .recent-lap-flash {{
      position: absolute;
      top: 50%;
      right: 4px;
      z-index: 1;
      transform: translateY(-50%);
      pointer-events: none;
      white-space: nowrap;
      padding-left: 8px;
      padding-right: 2px;
    }}
    .col-pos, .col-div-pos, .col-car-manufacturer, .col-car-number, .col-positions-gained {{
      width: 38px;
    }}
    .manufacturer-logo {{
      display: block;
      max-width: 22px;
      max-height: 16px;
      margin: 0 auto;
      object-fit: contain;
    }}
    .car-outline {{
      outline: 2px solid var(--division-color);
      outline-offset: -2px;
    }}
    .recent-faster {{ color: var(--faster-color); }}
    .recent-slower {{ color: var(--slower-color); }}
    .footer {{
      display: none;
      justify-content: space-between;
      padding: 5px 8px;
      background: rgba(51, 51, 51, 0.8);
      font-size: 10pt;
      font-weight: 700;
    }}
    .footer.visible {{ display: flex; }}
  </style>
</head>
<body>
  <div id="overlay">
    <div id="broadcast" class="broadcast">
      <img id="logo" alt="">
      <div>
        <div id="title" class="broadcast-title"></div>
        <div id="broadcastStatus" class="broadcast-status"></div>
      </div>
    </div>
    <div id="status" class="status"></div>
    <table class="table header-table">
      <thead><tr id="headers"></tr></thead>
    </table>
    <div id="tableViewport" class="table-viewport">
      <table class="table">
        <tbody id="rows"></tbody>
      </table>
    </div>
    <div id="footer" class="footer">
      <span id="sof"></span>
      <span id="incidents"></span>
      <span id="trackTemp"></span>
    </div>
  </div>
  <script>
    const overlay = document.getElementById('overlay');
    const broadcast = document.getElementById('broadcast');
    const status = document.getElementById('status');
    const tableViewport = document.getElementById('tableViewport');
    const rows = document.getElementById('rows');
    const headers = document.getElementById('headers');
    const footer = document.getElementById('footer');
    const AUTO_CENTER_PAUSE_MS = 5000;
    const PROGRAMMATIC_SCROLL_GRACE_MS = 250;
    let lastManualScrollAt = 0;
    let programmaticScrollUntil = 0;

    function monotonicNow() {{
      return window.performance && window.performance.now ? window.performance.now() : Date.now();
    }}

    function setViewportHeight() {{
      const viewportHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight;
      document.documentElement.style.setProperty('--viewport-height', viewportHeight + 'px');
    }}

    function noteManualScroll() {{
      const currentTime = monotonicNow();
      if (currentTime < programmaticScrollUntil) return;
      lastManualScrollAt = currentTime;
    }}

    function shouldAutoCenter() {{
      return monotonicNow() - lastManualScrollAt >= AUTO_CENTER_PAUSE_MS;
    }}

    function centerTargetRow() {{
      if (!shouldAutoCenter()) return;
      const targetRow = rows.querySelector('tr.spectated') || rows.querySelector('tr.player');
      if (!targetRow) return;

      const viewportHeight = tableViewport.clientHeight;
      const maxScroll = tableViewport.scrollHeight - viewportHeight;
      if (viewportHeight <= 0 || maxScroll <= 0) return;

      const viewportRect = tableViewport.getBoundingClientRect();
      const rowRect = targetRow.getBoundingClientRect();
      const rowCenter = rowRect.top - viewportRect.top + tableViewport.scrollTop + (rowRect.height / 2);
      const targetScroll = Math.max(0, Math.min(maxScroll, rowCenter - (viewportHeight / 2)));

      if (Math.abs(tableViewport.scrollTop - targetScroll) < 1) return;
      programmaticScrollUntil = monotonicNow() + PROGRAMMATIC_SCROLL_GRACE_MS;
      tableViewport.scrollTo({{ top: targetScroll, behavior: 'auto' }});
    }}

    setViewportHeight();
    window.addEventListener('resize', setViewportHeight, {{ passive: true }});
    if (window.visualViewport) {{
      window.visualViewport.addEventListener('resize', setViewportHeight, {{ passive: true }});
    }}
    tableViewport.addEventListener('wheel', noteManualScroll, {{ passive: true }});
    tableViewport.addEventListener('touchstart', noteManualScroll, {{ passive: true }});
    tableViewport.addEventListener('pointerdown', noteManualScroll, {{ passive: true }});
    tableViewport.addEventListener('scroll', noteManualScroll, {{ passive: true }});
    document.addEventListener('keydown', (event) => {{
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) {{
        noteManualScroll();
      }}
    }}, {{ passive: true }});

    function text(value) {{
      return value == null ? '' : String(value);
    }}

    function applyStyle(element, style) {{
      if (!style) return;
      if (style.color) element.style.color = style.color;
      if (style.backgroundColor) element.style.backgroundColor = style.backgroundColor;
      if (style.border) element.style.border = style.border;
    }}

    function effectiveCellBackground(cellElement, rowElement, data) {{
      const cellBackground = cellElement.style.backgroundColor || cellElement.style.background;
      if (cellBackground && cellBackground !== 'transparent') return cellBackground;
      if (rowElement.style.background) return rowElement.style.background;
      return data.backgroundColor || 'rgba(0, 0, 0, 0.8)';
    }}

    function render(data) {{
      overlay.style.background = data.backgroundColor;
      overlay.style.setProperty('--faster-color', data.fasterColor);
      overlay.style.setProperty('--slower-color', data.slowerColor);
      broadcast.style.background = data.headerColor;
      broadcast.style.borderBottomColor = data.accentColor;
      status.style.background = data.backgroundColor;
      status.style.color = data.statusColor || '#00FF00';

      document.getElementById('title').textContent = text(data.title);
      document.getElementById('broadcastStatus').textContent = text(data.statusText);
      document.getElementById('broadcastStatus').style.color = data.broadcastSessionColor || 'white';
      const logo = document.getElementById('logo');
      logo.src = text(data.logo);
      logo.style.display = data.logo ? '' : 'none';
      broadcast.classList.toggle('visible', Boolean(data.showBroadcastHeader));

      status.textContent = text(data.statusText);
      status.classList.toggle('hidden', Boolean(data.showBroadcastHeader));

      headers.innerHTML = '';
      for (const column of data.columns) {{
        const th = document.createElement('th');
        th.className = column.className;
        th.textContent = column.header;
        th.style.background = data.headerColor;
        headers.appendChild(th);
      }}

      rows.innerHTML = '';
      for (const driver of data.drivers) {{
        const tr = document.createElement('tr');
        tr.classList.toggle('player', Boolean(driver.isPlayer));
        tr.classList.toggle('spectated', Boolean(driver.isSpectated));
        if (driver.rowStyle) {{
          if (driver.rowStyle.background) tr.style.background = driver.rowStyle.background;
          if (driver.rowStyle.border) tr.style.outline = driver.rowStyle.border;
          if (driver.rowStyle.border) tr.style.outlineOffset = '-1px';
        }}
        tr.style.setProperty('--division-color', driver.divisionColor);
        tr.style.setProperty('--division-glow', driver.divisionColor + '33');
        for (const cell of driver.cells) {{
          const td = document.createElement('td');
          td.className = 'col-' + cell.id.replace(/_/g, '-');
          applyStyle(td, cell.style);
          if (cell.id === 'car_manufacturer' && cell.logoUrl) {{
            const logoImg = document.createElement('img');
            logoImg.className = 'manufacturer-logo';
            logoImg.src = cell.logoUrl;
            logoImg.alt = text(cell.value);
            logoImg.onerror = () => {{
              td.textContent = text(cell.value);
              td.style.color = driver.manufacturerColor;
            }};
            td.appendChild(logoImg);
          }} else if (cell.id === 'driver_name') {{
            const nameSpan = document.createElement('span');
            nameSpan.className = 'driver-name-text';
            nameSpan.textContent = text(cell.value);
            td.appendChild(nameSpan);
            if (cell.flash) {{
              const flashSpan = document.createElement('span');
              flashSpan.textContent = text(cell.flash);
              flashSpan.classList.add('recent-lap-flash');
              flashSpan.classList.add(cell.flashState === 'slower' ? 'recent-slower' : 'recent-faster');
              flashSpan.style.background = effectiveCellBackground(td, tr, data);
              td.appendChild(flashSpan);
            }}
          }} else {{
            td.textContent = text(cell.value);
          }}
          if (cell.id === 'car_manufacturer') {{
            td.style.color = driver.manufacturerColor;
          }}
          if (cell.id === 'car_number' && driver.showCarNumberOutline) {{
            td.classList.add('car-outline');
          }}
          tr.appendChild(td);
        }}
        rows.appendChild(tr);
      }}

      const footerData = data.footer || {{}};
      footer.classList.toggle('visible', Boolean(data.showFooter));
      document.getElementById('sof').textContent = footerData.sof == null ? 'SoF: ----' : 'SoF: ' + (footerData.sof / 1000).toFixed(1) + 'k';
      document.getElementById('incidents').textContent = footerData.incidents == null ? '--x' : String(footerData.incidents) + 'x';
      document.getElementById('trackTemp').textContent = footerData.track_temp == null ? '--F / --C' : Math.round(footerData.track_temp * 9 / 5 + 32) + 'F / ' + Math.round(footerData.track_temp) + 'C';
      requestAnimationFrame(centerTargetRow);
    }}

    async function refresh() {{
      try {{
        const response = await fetch('/api/state', {{ cache: 'no-store' }});
        if (response.ok) render(await response.json());
      }} catch (error) {{}}
    }}

    refresh();
    setInterval(refresh, 500);
  </script>
</body>
</html>"""
