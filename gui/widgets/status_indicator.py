from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QBrush


class StatusIndicator(QWidget):
    """Custom status indicator widget with colored circle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = "disconnected"
        self.setFixedSize(16, 16)

    def set_status(self, status):
        """Set the status indicator color."""
        self.status = status
        self.update()

    def paintEvent(self, event):
        """Paint the status indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Set color based on status
        if self.status == "connected":
            color = QColor("#4CAF50")  # Green
        elif self.status == "connecting":
            color = QColor("#FF9800")  # Orange
        else:  # disconnected
            color = QColor("#F44336")  # Red

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)

        # Draw circle
        center = self.rect().center()
        radius = min(self.width(), self.height()) // 2 - 1
        painter.drawEllipse(center, radius, radius)
