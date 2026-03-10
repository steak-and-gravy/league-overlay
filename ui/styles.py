"""Driver row color style strategies."""

from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from league_overlay import LeagueOverlay
    from core.driver_state import DriverState


def is_light_color(hex_color: str) -> bool:
    """Determine if a hex color is light or dark.
    
    Uses luminance calculation: if luminance > 0.5, it's a light color.
    Args:
        hex_color: Hex color string (e.g., '#FFFFFF')
    
    Returns:
        True if color is light (use dark text), False if dark (use light text)
    """
    if not hex_color.startswith('#') or len(hex_color) < 7:
        return False
    
    try:
        r = int(hex_color[1:3], 16) / 255.0
        g = int(hex_color[3:5], 16) / 255.0
        b = int(hex_color[5:7], 16) / 255.0
        
        # Calculate relative luminance using sRGB formula
        # Reference: https://www.w3.org/TR/WCAG20/#relativeluminancedef
        def adjust(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        
        r = adjust(r)
        g = adjust(g)
        b = adjust(b)
        
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return luminance > 0.5
    except (ValueError, IndexError):
        return False


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
                - delta_faster_color: Color for positive delta (you're faster)
                - delta_slower_color: Color for negative delta (you're slower)
                - label_bg: Background color for labels
                - label_border: CSS border style for labels
                - layout_margins: Tuple of (left, top, right, bottom) margins
                - layout_spacing: Spacing between layout elements
        """
        raise NotImplementedError("Subclasses must implement get_styling()")


class DarkColorStyle(ColorStyleStrategy):
    """Dark color style: Black background with colored text, player gets gradient glow."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        text_color = driver.division_color
        gap_color = "white"
        delta_faster_color = parent.settings.faster_color
        delta_slower_color = parent.settings.slower_color

        if driver.is_player or driver.is_spectated:
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
            'delta_faster_color': delta_faster_color,
            'delta_slower_color': delta_slower_color,
            'label_bg': label_bg,
            'label_border': '',
            'layout_margins': (0, 2, 0, 2),
            'layout_spacing': 2
        }


class AlternateColorStyle(ColorStyleStrategy):
    """Alternate color style: Division color fills entire row background, black text."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        base_bg = driver.division_color
        bg_style = f"background-color: {parent.get_bg_color(base_bg)};"
        text_color = "#000000"
        gap_color = "#000000"
        delta_faster_color = parent.settings.faster_color
        delta_slower_color = parent.settings.slower_color
        label_bg = parent.get_bg_color(base_bg)

        if driver.is_player or driver.is_spectated:
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
                'delta_faster_color': delta_faster_color,
                'delta_slower_color': delta_slower_color,
                'label_bg': label_bg,
                'label_border': '',
                'layout_margins': (0, 2, 0, 2),
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
                'delta_faster_color': delta_faster_color,
                'delta_slower_color': delta_slower_color,
                'label_bg': label_bg,
                'label_border': '',
                'layout_margins': (0, 2, 0, 2),
                'layout_spacing': 2
            }


class OutlineColorStyle(ColorStyleStrategy):
    """Outline color style: Black background with colored border and text."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        text_color = driver.division_color
        gap_color = "white"
        delta_faster_color = parent.settings.faster_color
        delta_slower_color = parent.settings.slower_color
        label_bg = "transparent"
        label_border = "border: none;"

        if driver.is_player or driver.is_spectated:
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
            'delta_faster_color': delta_faster_color,
            'delta_slower_color': delta_slower_color,
            'label_bg': label_bg,
            'label_border': label_border,
            'layout_margins': (0, 2, 0, 2),
            'layout_spacing': 2
        }


class DefaultColorStyle(ColorStyleStrategy):
    """Default color style: Red position background, division color car number and driver name, white gap."""

    def get_styling(self, driver: 'DriverState', parent: 'LeagueOverlay') -> Dict[str, Any]:
        text_color = driver.division_color
        gap_color = "white"
        delta_faster_color = parent.settings.faster_color
        delta_slower_color = parent.settings.slower_color
        label_bg = parent.get_bg_color('#000000')
        label_border = ''
        position_bg = parent.get_bg_color('#FF0000')
        position_color = "white"
        car_number_bg = parent.get_bg_color(driver.division_color)
        # Use black text for light division colors, white for dark
        car_number_color = "#000000" if is_light_color(driver.division_color) else "white"

        if driver.is_player or driver.is_spectated:
            bg_style = f"background: {parent.create_gradient_background(driver.division_color)};"
            label_bg = parent.blend_color_with_black(driver.division_color, 0.25)
        else:
            bg_style = f"background-color: {parent.get_bg_color('#000000')};"

        row_widget = QWidget()
        row_widget.setStyleSheet(bg_style)

        return {
            'row_widget': row_widget,
            'container_widget': None,
            'text_color': text_color,
            'gap_color': gap_color,
            'delta_faster_color': delta_faster_color,
            'delta_slower_color': delta_slower_color,
            'label_bg': label_bg,  # Default background (driver name, gap)
            'label_border': label_border,
            'layout_margins': (0, 2, 0, 2),
            'layout_spacing': 2,
            # Special styling for specific labels
            'position_bg': position_bg,  # Red background for position
            'position_color': position_color,
            'car_number_bg': car_number_bg,  # Division color for car number
            'car_number_color': car_number_color  # White text for car number and div position
        }
