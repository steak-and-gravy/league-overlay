"""Driver row rendering with pluggable style strategies."""

from typing import TYPE_CHECKING, Dict
from PySide6.QtWidgets import QWidget, QLabel, QGridLayout, QSizePolicy
from PySide6.QtCore import Qt

from config.constants import COLUMN_LAYOUT
from .styles import DefaultColorStyle, AlternateColorStyle, OutlineColorStyle, StreamColorStyle

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay


class DriverRowRenderer:
    """Handles driver row creation with pluggable color styles."""

    STYLES = {
        "Default": DefaultColorStyle(),
        "Alternate": AlternateColorStyle(),
        "Outline": OutlineColorStyle(),
        "Stream": StreamColorStyle()
    }

    def __init__(self, parent: 'LeagueOverlay'):
        """Initialize renderer with reference to parent overlay.

        Args:
            parent: LeagueOverlay instance
        """
        self.parent = parent

    def create_row(self, driver_data: Dict) -> QWidget:
        """Create a driver row widget using the configured color style.

        Args:
            driver_data: Dictionary containing driver information

        Returns:
            QWidget representing the driver row
        """
        driver_color = self.parent.get_driver_color(driver_data.get('driver_info', {}))
        is_player = driver_data.get('is_player', False)

        # Get color style
        style = self.STYLES.get(self.parent.row_color_style, self.STYLES["Default"])
        styling = style.get_styling(driver_data, is_player, driver_color, self.parent)

        # Extract styling components
        row_widget = styling['row_widget']
        container_widget = styling['container_widget']
        text_color = styling['text_color']
        gap_color = styling['gap_color']
        label_bg = styling['label_bg']
        label_border = styling['label_border']

        # Create layout
        layout = QGridLayout(row_widget)
        layout.setContentsMargins(*styling['layout_margins'])
        layout.setSpacing(styling['layout_spacing'])

        # Determine if we're using Stream style (which swaps car number and driver name positions)
        is_stream_style = self.parent.row_color_style == "Stream"

        # Set column stretches
        layout.setColumnStretch(0, COLUMN_LAYOUT.POS)
        layout.setColumnStretch(1, COLUMN_LAYOUT.DIV_POS)
        if is_stream_style:
            # Stream: Position | Div Pos | Driver Name | Car Number | Gap
            layout.setColumnStretch(2, COLUMN_LAYOUT.DRIVER_NAME)
            layout.setColumnStretch(3, COLUMN_LAYOUT.CAR_NUM)
        else:
            # Default: Position | Div Pos | Car Number | Driver Name | Gap
            layout.setColumnStretch(2, COLUMN_LAYOUT.CAR_NUM)
            layout.setColumnStretch(3, COLUMN_LAYOUT.DRIVER_NAME)
        layout.setColumnStretch(4, COLUMN_LAYOUT.GAP)

        # Determine font weight
        font_weight = "bold" if is_player or self.parent.bold_drivers else "normal"

        # Create labels (pass styling for special styles like Stream)
        # Column positions depend on style
        car_col = 3 if is_stream_style else 2
        name_col = 2 if is_stream_style else 3

        self._create_position_label(layout, driver_data, text_color, label_bg, label_border, font_weight, styling)
        self._create_division_position_label(layout, driver_data, text_color, label_bg, label_border, font_weight, styling)
        self._create_car_number_label(layout, driver_data, text_color, label_bg, label_border, font_weight, styling, car_col)
        self._create_driver_name_label(layout, driver_data, text_color, label_bg, label_border, font_weight, name_col)
        self._create_gap_label(layout, driver_data, gap_color, label_bg, label_border, font_weight)

        # Set context menu for row widget
        row_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        row_widget.customContextMenuRequested.connect(
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )

        # Set context menu for container if it exists
        if container_widget:
            container_widget.setContextMenuPolicy(Qt.CustomContextMenu)
            container_widget.customContextMenuRequested.connect(
                lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
            )

        return container_widget if container_widget else row_widget

    def _create_position_label(self, layout: QGridLayout, driver_data: Dict, text_color: str,
                               label_bg: str, label_border: str, font_weight: str, styling: Dict = None) -> None:
        """Create position label."""
        # Check for special position styling (for Stream style)
        pos_color = styling.get('position_color', text_color) if styling else text_color
        pos_bg = styling.get('position_bg', label_bg) if styling else label_bg

        pos_label = QLabel(str(driver_data.get('position', '')))
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
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )
        layout.addWidget(pos_label, 0, 0)

    def _create_division_position_label(self, layout: QGridLayout, driver_data: Dict, text_color: str,
                                       label_bg: str, label_border: str, font_weight: str, styling: Dict = None) -> None:
        """Create division position label."""
        # Check for special division position styling (same as car number for Stream style)
        div_pos_color = styling.get('car_number_color', text_color) if styling else text_color
        div_pos_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        div_pos_label = QLabel(str(driver_data.get('division_position', '')))
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
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )
        layout.addWidget(div_pos_label, 0, 1)

    def _create_car_number_label(self, layout: QGridLayout, driver_data: Dict, text_color: str,
                                 label_bg: str, label_border: str, font_weight: str, styling: Dict = None, column: int = 2) -> None:
        """Create car number label."""
        # Check for special car number styling (for Stream style)
        car_color = styling.get('car_number_color', text_color) if styling else text_color
        car_bg = styling.get('car_number_bg', label_bg) if styling else label_bg

        car_label = QLabel(str(driver_data.get('car_number', '')))
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
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )
        layout.addWidget(car_label, 0, column)

    def _create_driver_name_label(self, layout: QGridLayout, driver_data: Dict, text_color: str,
                                  label_bg: str, label_border: str, font_weight: str, column: int = 3) -> None:
        """Create driver name label."""
        name_align = Qt.AlignCenter if self.parent.center_drivers else Qt.AlignLeft
        name_label = QLabel(driver_data.get('driver_name', ''))
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
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )
        layout.addWidget(name_label, 0, column)

    def _create_gap_label(self, layout: QGridLayout, driver_data: Dict, gap_color: str,
                         label_bg: str, label_border: str, font_weight: str) -> None:
        """Create gap label."""
        from config.logging_config import get_logger
        logger = get_logger(__name__)

        gap_value = driver_data.get('gap', '')

        # Log gap values for critical positions or when gap is "Leader"
        position = driver_data.get('position', -1)
        car_idx = driver_data.get('car_idx', -1)
        if position in [1, 2, 3, 9, 10] or gap_value == "Leader":
            logger.info(f"UI_GAP - Car {car_idx} (P{position}): gap_value='{gap_value}', "
                       f"car_number={driver_data.get('car_number', '?')}, "
                       f"driver_name={driver_data.get('driver_name', '?')}")

        gap_label = QLabel(gap_value)
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
            lambda pos, dd=driver_data: self.parent.show_context_menu(dd)
        )
        layout.addWidget(gap_label, 0, 4)
