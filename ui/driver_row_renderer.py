"""Driver row rendering with pluggable style strategies."""

from typing import TYPE_CHECKING, Dict
from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QSizePolicy
from PySide6.QtCore import Qt

from config.constants import COLUMN_LAYOUT
from core.driver_state import DriverState
from .styles import DefaultColorStyle, AlternateColorStyle, OutlineColorStyle, DarkColorStyle

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class DriverRowRenderer:
    """Handles driver row creation with pluggable color styles."""

    STYLES = {
        "Default": DefaultColorStyle(),
        "Dark": DarkColorStyle(),
        "Alternate": AlternateColorStyle(),
        "Outline": OutlineColorStyle()
    }

    def __init__(self, parent: 'LeagueOverlay'):
        """Initialize renderer with reference to parent overlay.

        Args:
            parent: LeagueOverlay instance
        """
        self.parent = parent

    def create_row(self, driver: DriverState) -> QWidget:
        """Create a driver row widget using the configured color style.

        Args:
            driver: DriverState object containing driver information

        Returns:
            QWidget representing the driver row
        """
        # Get color style
        style = self.STYLES.get(self.parent.settings.row_color_style, self.STYLES["Default"])
        styling = style.get_styling(driver, self.parent)

        # Extract styling components
        row_widget = styling['row_widget']
        container_widget = styling['container_widget']
        text_color = styling['text_color']
        gap_color = styling['gap_color']
        delta_faster_color = styling['delta_faster_color']
        delta_slower_color = styling['delta_slower_color']
        label_bg = styling['label_bg']
        label_border = styling['label_border']

        # Create layout
        layout = QGridLayout(row_widget)
        layout.setContentsMargins(*styling['layout_margins'])
        layout.setSpacing(styling['layout_spacing'])

        # Set column stretches
        # Layout: Position | Div Pos | Driver Name | Car Number | Gap | Last Lap | Delta
        layout.setColumnStretch(0, COLUMN_LAYOUT.POS)
        layout.setColumnStretch(1, COLUMN_LAYOUT.DIV_POS)
        layout.setColumnStretch(2, COLUMN_LAYOUT.DRIVER_NAME)
        layout.setColumnStretch(3, COLUMN_LAYOUT.CAR_NUM)
        layout.setColumnStretch(4, COLUMN_LAYOUT.GAP)
        layout.setColumnStretch(5, COLUMN_LAYOUT.LAST_LAP)
        layout.setColumnStretch(6, COLUMN_LAYOUT.DELTA)

        # Determine font weight
        font_weight = "bold" if driver.is_player or self.parent.settings.bold_drivers else "normal"

        # Create labels (pass styling for special styles like Default)
        # Car number is always on the right (column 3), driver name on the left (column 2)
        car_col = 3
        name_col = 2

        self._create_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling)
        self._create_division_position_label(layout, driver, text_color, label_bg, label_border, font_weight, styling)
        self._create_car_number_label(layout, driver, text_color, label_bg, label_border, font_weight, styling, car_col)
        self._create_driver_name_label(layout, driver, text_color, label_bg, label_border, font_weight, name_col)
        self._create_gap_label(layout, driver, gap_color, label_bg, label_border, font_weight)
        self._create_last_lap_label(layout, driver, gap_color, label_bg, label_border, font_weight)
        self._create_delta_label(layout, driver, delta_faster_color, delta_slower_color, gap_color, label_bg, label_border, font_weight)

        # Set context menu for row widget
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )

        # Set context menu for container if it exists
        if container_widget:
            container_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            container_widget.customContextMenuRequested.connect(
                lambda pos, d=driver: self.parent.show_context_menu(d)
            )

        return container_widget if container_widget else row_widget

    def _create_position_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                               label_bg: str, label_border: str, font_weight: str, styling: Dict = None) -> None:
        """Create position label."""
        # Check for special position styling (for Default style)
        pos_color = styling.get('position_color', text_color) if styling else text_color
        pos_bg = styling.get('position_bg', label_bg) if styling else label_bg

        pos_label = QLabel(str(driver.position if driver.position else ''))
        pos_label.setStyleSheet(f"""
            QLabel {{
                color: {pos_color};
                background-color: {pos_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        pos_label.setAlignment(Qt.AlignCenter)
        pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        pos_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(pos_label, 0, 0)

    def _create_division_position_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, styling: Dict = None) -> None:
        """Create division position label."""
        # Check for special division position styling (same as car number for Default style)
        div_pos_color = styling.get('car_number_color', text_color) if styling else text_color
        div_pos_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        div_pos_label = QLabel(str(driver.division_position if driver.division_position else ''))
        div_pos_label.setStyleSheet(f"""
            QLabel {{
                color: {div_pos_color};
                background-color: {div_pos_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        div_pos_label.setAlignment(Qt.AlignCenter)
        div_pos_label.setContextMenuPolicy(Qt.CustomContextMenu)
        div_pos_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(div_pos_label, 0, 1)

    def _create_car_number_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                 label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 2) -> None:
        """Create car number label."""
        # Check for special car number styling (for Default style)
        car_color = styling.get('car_number_color', text_color) if styling else text_color
        car_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        car_label = QLabel(str(driver.car_number))
        car_label.setStyleSheet(f"""
            QLabel {{
                color: {car_color};
                background-color: {car_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        car_label.setAlignment(Qt.AlignCenter)
        car_label.setContextMenuPolicy(Qt.CustomContextMenu)
        car_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(car_label, 0, column)

    def _create_driver_name_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                                  label_bg: str, label_border: str, font_weight: str, column: int = 3) -> None:
        """Create driver name label."""
        name_align = Qt.AlignCenter if self.parent.settings.center_drivers else Qt.AlignLeft
        name_label = QLabel(driver.driver_name)
        name_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                padding-left: 0.5px;
                {label_border}
            }}
        """)
        name_label.setAlignment(name_align | Qt.AlignVCenter)
        name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name_label.setWordWrap(False)
        name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        name_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(name_label, 0, column)

    def _create_gap_label(self, layout: QGridLayout, driver: DriverState, gap_color: str,
                         label_bg: str, label_border: str, font_weight: str) -> None:
        """Create gap label."""
        gap_label = QLabel(driver.gap)
        gap_label.setStyleSheet(f"""
            QLabel {{
                color: {gap_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        gap_label.setAlignment(Qt.AlignCenter)
        gap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        gap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(gap_label, 0, 4)

    def _create_delta_label(self, layout: QGridLayout, driver: DriverState, delta_faster_color: str,
                           delta_slower_color: str, default_color: str, label_bg: str,
                           label_border: str, font_weight: str) -> None:
        """Create delta label with style-specific colors.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing delta value
            delta_faster_color: Color for positive delta (you're faster)
            delta_slower_color: Color for negative delta (you're slower)
            default_color: Fallback color for no data ("--")
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
        """
        # Color code deltas: green for positive (you're faster), red for negative (you're slower)
        if driver.delta.startswith('+'):
            delta_display_color = delta_faster_color  # Green - they're slower than you (you're faster)
        elif driver.delta.startswith('-'):
            delta_display_color = delta_slower_color  # Red - they're faster than you (you're slower)
        else:
            delta_display_color = default_color  # Default color for "--"

        delta_label = QLabel(driver.delta)
        delta_label.setStyleSheet(f"""
            QLabel {{
                color: {delta_display_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        delta_label.setAlignment(Qt.AlignCenter)
        delta_label.setContextMenuPolicy(Qt.CustomContextMenu)
        delta_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(delta_label, 0, 6)

    def _create_last_lap_label(self, layout: QGridLayout, driver: DriverState, text_color: str,
                               label_bg: str, label_border: str, font_weight: str) -> None:
        """Create last lap time label.

        Args:
            layout: Grid layout to add label to
            driver: Driver state containing last lap time
            text_color: Text color (gap_color - white)
            label_bg: Background color
            label_border: Border style
            font_weight: Font weight
        """
        last_lap_label = QLabel(driver.last_lap)
        last_lap_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                background-color: {label_bg};
                font-size: {self.parent.get_font_size('data')};
                font-weight: {font_weight};
                {label_border}
            }}
        """)
        last_lap_label.setAlignment(Qt.AlignCenter)
        last_lap_label.setContextMenuPolicy(Qt.CustomContextMenu)
        last_lap_label.customContextMenuRequested.connect(
            lambda pos, d=driver: self.parent.show_context_menu(d)
        )
        layout.addWidget(last_lap_label, 0, 5)
