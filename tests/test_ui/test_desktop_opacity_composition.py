"""Rendered-alpha checks for the desktop overlay background hierarchy."""

from types import MethodType, SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from config.constants import UI_CONFIG
from config.settings import AppSettings
from core.driver_state import DriverState
from league_overlay import LeagueOverlay
from ui.broadcast_header import BroadcastHeaderWidget
from ui.driver_row_renderer import DriverRowRenderer
from ui.widgets import DriverListContentWidget


def _rendered_color(root: QWidget, widget: QWidget, local_point: QPoint) -> QColor:
    image = QImage(root.size(), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    root.render(painter, QPoint(0, 0))
    painter.end()
    return QColor.fromRgba(image.pixel(widget.mapTo(root, local_point)))


@pytest.mark.parametrize(
    ("opacity", "expected_alpha"),
    [
        (0.0, 0.01),
        (0.5, 0.5),
        (1.0, 1.0),
    ],
)
def test_empty_driver_list_fills_the_viewport_at_configured_opacity(
    qapp,
    opacity,
    expected_alpha,
):
    content = DriverListContentWidget(
        get_opacity=lambda: max(0.01, opacity),
    )
    content.resize(320, 240)
    content.show()
    qapp.processEvents()

    color = _rendered_color(content, content, content.rect().center())

    assert color.alphaF() == pytest.approx(expected_alpha, abs=1 / 255)

    content.deleteLater()


@pytest.mark.parametrize(
    ("opacity", "expected_alpha"),
    [
        (0.0, 0.01),
        (0.5, 0.5),
        (1.0, 1.0),
    ],
)
@pytest.mark.parametrize("row_color_style", ["Default", "Dark", "Alternate", "Outline"])
def test_broadcast_header_and_alternating_rows_share_configured_opacity(
    qapp,
    monkeypatch,
    opacity,
    expected_alpha,
    row_color_style,
):
    settings = AppSettings(
        opacity=opacity,
        row_color_style=row_color_style,
        column_order=["driver_name"],
    )
    parent = SimpleNamespace(settings=settings, font_sizes=UI_CONFIG.FONT_SIZES)
    parent.get_bg_color = MethodType(LeagueOverlay.get_bg_color, parent)
    parent.get_font_size = MethodType(LeagueOverlay.get_font_size, parent)
    parent.blend_color_with_black = MethodType(LeagueOverlay.blend_color_with_black, parent)
    parent.create_gradient_background = MethodType(LeagueOverlay.create_gradient_background, parent)
    parent.show_context_menu = lambda driver: None

    root = QWidget()
    root.setAttribute(Qt.WA_TranslucentBackground, True)
    root.resize(700, 240)
    root_layout = QVBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    monkeypatch.setattr(BroadcastHeaderWidget, "_load_logo", lambda self: None)
    header = BroadcastHeaderWidget(
        settings,
        parent.get_bg_color,
        parent.get_font_size,
        get_broadcast_title_fn=lambda: "Opacity Test",
        get_broadcast_logo_fn=lambda: "",
    )
    root_layout.addWidget(header)

    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.NoFrame)
    parent.scroll_area = scroll_area
    LeagueOverlay.update_scroll_area_style(parent)

    scroll_content = DriverListContentWidget(
        get_opacity=lambda: max(0.01, settings.opacity),
    )
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(0)
    renderer = DriverRowRenderer(parent)

    rows = []
    for row_index, name in enumerate(("Even Row", "Odd Row", "Player Row")):
        driver = DriverState(
            car_idx=row_index,
            driver_info={"UserName": name, "CarNumber": str(row_index + 1)},
            division_color="#00AAFF",
            is_player=row_index == 2,
        )
        row = renderer.create_row(driver, row_index=row_index)
        rows.append(row)
        scroll_layout.addWidget(row)
    scroll_layout.addStretch()
    scroll_area.setWidget(scroll_content)
    root_layout.addWidget(scroll_area)

    root.show()
    qapp.processEvents()

    header_color = _rendered_color(root, header, QPoint(2, 2))
    row_colors = []
    for row in rows:
        cell = row.findChild(QWidget, "driverNameCell")
        row_colors.append(
            _rendered_color(
                root,
                cell,
                QPoint(max(cell.width() - 3, 0), cell.height() // 2),
            )
        )

    alpha_tolerance = 1 / 255
    assert header_color.alphaF() == pytest.approx(expected_alpha, abs=alpha_tolerance)
    assert row_colors[0].alphaF() == pytest.approx(expected_alpha, abs=alpha_tolerance)
    assert row_colors[1].alphaF() == pytest.approx(expected_alpha, abs=alpha_tolerance)
    assert row_colors[2].alphaF() == pytest.approx(expected_alpha, abs=alpha_tolerance)

    empty_color = _rendered_color(
        root,
        scroll_content,
        QPoint(scroll_content.width() // 2, scroll_content.height() - 2),
    )
    assert empty_color.alphaF() == pytest.approx(expected_alpha, abs=alpha_tolerance)
    assert rows[0].geometry().left() == 0
    assert rows[0].geometry().right() == scroll_content.width() - 1
    assert rows[1].geometry().top() == rows[0].geometry().bottom() + 1

    if row_color_style == "Default" and opacity == 0.5:
        assert row_colors[1].red() > row_colors[0].red()

    root.deleteLater()
