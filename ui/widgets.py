"""Custom Qt widgets for the overlay application."""

from typing import Optional
from PySide6.QtWidgets import QSizeGrip, QMainWindow, QWidget
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QPainter, QColor


class DataUpdateSignal(QObject):
    """Signal emitter for thread-safe GUI updates."""
    update_data = Signal(list)
    update_status = Signal(str, str)  # text, color
    refresh_colors = Signal()


class CustomSizeGrip(QSizeGrip):
    """Custom size grip widget with transparent background and conditional visibility.
    Shows diagonal arrow pattern when parent window has focus or mouse is hovering over the app.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize custom size grip.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.parent_window: Optional[QMainWindow] = None
        self._is_hovered = False
        # Make the widget background transparent
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # Enable hover events
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)

    def set_parent_window(self, window: QMainWindow) -> None:
        """Set reference to parent window for focus checking.

        Args:
            window: Parent main window reference
        """
        self.parent_window = window

    def set_hovered(self, hovered: bool) -> None:
        """Update hover state and trigger repaint.

        Args:
            hovered: Whether the parent window is being hovered
        """
        if self._is_hovered != hovered:
            self._is_hovered = hovered
            self.update()

    def _should_show_grip(self) -> bool:
        """Determine if grip should be visible based on focus or hover state.

        Returns:
            True if grip should be shown
        """
        if not self.parent_window:
            return False

        # Show if window has focus OR if mouse is hovering over the window
        return self.parent_window.hasFocus() or self._is_hovered

    def paintEvent(self, event) -> None:
        """Custom paint to show diagonal arrows when focused/hovered with subtle background.

        Args:
            event: Paint event
        """
        # Don't call super().paintEvent() to avoid default rendering

        if self._should_show_grip():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Make background fully transparent first
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw background box (fully opaque)
            painter.fillRect(self.rect(), QColor(60, 60, 60, 255))

            # Draw diagonal resize arrows (bottom-right to top-left direction)
            painter.setPen(QColor("#AAAAAA"))

            size = self.width()

            # Main diagonal line (from bottom-right to top-left)
            painter.drawLine(size - 3, size - 3, 3, 3)

            # Arrowhead at top-left (angled lines pointing back toward center)
            painter.drawLine(3, 3, 8, 5)  # diagonal going down-right
            painter.drawLine(3, 3, 5, 8)  # diagonal going down-right

            # Arrowhead at bottom-right (angled lines pointing back toward center)
            painter.drawLine(size - 3, size - 3, size - 8, size - 5)  # diagonal going up-left
            painter.drawLine(size - 3, size - 3, size - 5, size - 8)  # diagonal going up-left
