"""Driver row color style strategies."""

from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay
    from core.driver_state import DriverState


class ColorStyleStrategy(ABC):
    """Abstract base class for driver row color styles."""

    @abstractmethod
    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        """Get styling configuration for a driver row.

        Args:
            driver: DriverState object containing all driver information
            parent: Reference to LeagueOverlay instance for accessing helper methods

        Returns:
            Dictionary containing:
                - row_widget: The main QWidget for the row
                - container_widget: Optional container widget (for borders, etc.)
                - text_color: Color for text labels
                - gap_color: Color for gap label
                - label_bg: Background color for labels
                - label_border: CSS border style for labels
                - layout_margins: Tuple of (left, top, right, bottom) margins
                - layout_spacing: Spacing between layout elements
        """
        raise NotImplementedError("Subclasses must implement get_styling()")


class DefaultColorStyle(ColorStyleStrategy):
    """Default color style: Black background with colored text, player gets gradient glow."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        text_color = driver.division_color
        gap_color = "white"

        if driver.is_player:
            bg_style = f"background: {parent.create_gradient_background(driver.division_color)};"
            label_bg = parent.blend_color_with_black(driver.division_color, 0.25)
        else:
            bg_style = f"background-color: {parent.get_bg_color('#000000')};"
            label_bg = parent.get_bg_color('#000000')

        row_widget = QWidget()
        row_widget.setStyleSheet(bg_style)

        return {
            'row_widget': row_widget,
            'container_widget': None,
            'text_color': text_color,
            'gap_color': gap_color,
            'label_bg': label_bg,
            'label_border': '',
            'layout_margins': (2, 2, 2, 2),
            'layout_spacing': 2
        }


class AlternateColorStyle(ColorStyleStrategy):
    """Alternate color style: Division color fills entire row background, black text."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        base_bg = driver.division_color
        bg_style = f"background-color: {parent.get_bg_color(base_bg)};"
        text_color = "#000000"
        gap_color = "#000000"
        label_bg = parent.get_bg_color(base_bg)

        if driver.is_player:
            # Create container for white border
            container_widget = QWidget()
            container_widget.setStyleSheet("background-color: white; padding: 2px;")
            container_layout = QVBoxLayout(container_widget)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(0)

            # Inner row widget with division color background
            row_widget = QWidget()
            row_widget.setStyleSheet(bg_style)
            row_widget.setAttribute(Qt.WA_Hover, True)
            container_layout.addWidget(row_widget)

            return {
                'row_widget': row_widget,
                'container_widget': container_widget,
                'text_color': text_color,
                'gap_color': gap_color,
                'label_bg': label_bg,
                'label_border': '',
                'layout_margins': (2, 2, 2, 2),
                'layout_spacing': 2
            }
        else:
            row_widget = QWidget()
            row_widget.setStyleSheet(bg_style)

            return {
                'row_widget': row_widget,
                'container_widget': None,
                'text_color': text_color,
                'gap_color': gap_color,
                'label_bg': label_bg,
                'label_border': '',
                'layout_margins': (2, 2, 2, 2),
                'layout_spacing': 2
            }


class OutlineColorStyle(ColorStyleStrategy):
    """Outline color style: Black background with colored border and text."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        text_color = driver.division_color
        gap_color = "white"
        label_bg = "transparent"
        label_border = "border: none;"

        if driver.is_player:
            bg_style = f"background: {parent.create_gradient_background(driver.division_color)};"
            border_style = ""
        else:
            bg_style = f"background-color: {parent.get_bg_color('#000000')};"
            border_style = f"border: 1px solid {driver.division_color};"

        row_widget = QWidget()
        row_widget.setStyleSheet(f"{bg_style} {border_style}")

        return {
            'row_widget': row_widget,
            'container_widget': None,
            'text_color': text_color,
            'gap_color': gap_color,
            'label_bg': label_bg,
            'label_border': label_border,
            'layout_margins': (3, 2, 3, 2),
            'layout_spacing': 0
        }


class StreamColorStyle(ColorStyleStrategy):
    """Stream color style: Red position background, division color car number, black driver name and gap."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        # Position: red background, white text
        # Driver name: black background, white text
        # Car number: division color background, white text
        # Division position: division color background, white text
        # Gap: black background, white text

        if driver.is_player:
            bg_style = f"background: {parent.create_gradient_background(driver.division_color)};"
        else:
            bg_style = f"background-color: {parent.get_bg_color('#000000')};"

        row_widget = QWidget()
        row_widget.setStyleSheet(bg_style)

        return {
            'row_widget': row_widget,
            'container_widget': None,
            'text_color': "white",  # Default text color (driver name, gap)
            'gap_color': "white",
            'label_bg': parent.get_bg_color('#000000'),  # Default background (driver name, gap)
            'label_border': '',
            'layout_margins': (2, 2, 2, 2),
            'layout_spacing': 2,
            # Special styling for specific labels
            'position_bg': parent.get_bg_color('#FF0000'),  # Red background for position
            'position_color': "white",
            'car_number_bg': parent.get_bg_color(driver.division_color),  # Division color for car number
            'car_number_color': "white"  # White text for car number and div position
        }
