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
    Shows diagonal arrow pattern when parent window has focus, allows window resizing.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize custom size grip.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.parent_window: Optional[QMainWindow] = None
        # Make the widget background transparent
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_parent_window(self, window: QMainWindow) -> None:
        """Set reference to parent window for focus checking.

        Args:
            window: Parent main window reference
        """
        self.parent_window = window

    def paintEvent(self, event) -> None:
        """Custom paint to show diagonal arrows when focused with transparent background.

        Args:
            event: Paint event
        """
        # Don't call super().paintEvent() to avoid default rendering

        if self.parent_window and self.parent_window.hasFocus():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Make background fully transparent
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            painter.fillRect(self.rect(), Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # Draw diagonal arrows
            painter.setPen(QColor("#888888"))

            # Draw diagonal double arrow pattern
            size = self.width()
            spacing = 4

            # Draw three diagonal lines to create arrow effect
            for i in range(3):
                offset = i * spacing
                painter.drawLine(
                    size - 3 - offset, offset + 3,
                    offset + 3, size - 3 - offset
                )
