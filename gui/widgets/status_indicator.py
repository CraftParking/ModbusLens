from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QLinearGradient, QFontMetrics


class StatusIndicator(QWidget):
    """Compact status indicator with better boundary management."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = "disconnected"
        self.setFixedSize(140, 40)  # Optimized size for text
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.animate_pulse)
        self.pulse_value = 0
        self.pulse_direction = 1
        self.is_animating = False
        
        # Create layout for better text management
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)
        self.layout().setSpacing(2)

    def set_status(self, status):
        """Set the status indicator with animation."""
        self.status = status
        
        # Start animation for connecting state
        if status == "connecting":
            self.is_animating = True
            self.animation_timer.start(60)
        else:
            self.is_animating = False
            self.animation_timer.stop()
            self.pulse_value = 0
        
        self.update()

    def animate_pulse(self):
        """Animate pulsing effect for connecting state."""
        self.pulse_value += self.pulse_direction * 4
        if self.pulse_value >= 100 or self.pulse_value <= 0:
            self.pulse_direction *= -1
        self.update()

    def paintEvent(self, event):
        """Paint the compact status indicator with proper boundaries."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Define drawing area with margins
        draw_rect = self.rect().adjusted(2, 2, -2, -2)
        
        # Set colors based on status
        if self.status == "connected":
            primary_color = QColor("#00E676")  # Material green
            secondary_color = QColor("#69F0AE")  # Light green
            text_color = QColor("#FFFFFF")
            status_text = "CONNECTED"
            icon_text = "●"
        elif self.status == "connecting":
            # Animated orange for connecting
            pulse_factor = self.pulse_value / 100.0
            primary_color = QColor(
                int(255 * (0.6 + 0.4 * pulse_factor)),
                int(145 * (0.6 + 0.4 * pulse_factor)),
                int(0)
            )
            secondary_color = QColor("#FFB74D")
            text_color = QColor("#FFFFFF")
            status_text = "CONNECTING"
            icon_text = "○"
        elif self.status == "error":
            primary_color = QColor("#FFA000")  # Material yellow/amber
            secondary_color = QColor("#FFD54F")  # Light yellow
            text_color = QColor("#000000")  # Black text for yellow background
            status_text = "ERROR"
            icon_text = "⚠"
        else:  # disconnected
            primary_color = QColor("#FF5252")  # Material red
            secondary_color = QColor("#FF8A80")  # Light red
            text_color = QColor("#FFFFFF")
            status_text = "DISCONNECTED"
            icon_text = "○"

        # Create vertical gradient
        gradient = QLinearGradient(0, draw_rect.top(), 0, draw_rect.bottom())
        gradient.setColorAt(0, primary_color)
        gradient.setColorAt(1, secondary_color)

        # Draw clean rectangle with proper boundaries
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(primary_color.darker(130), 2))
        painter.drawRect(draw_rect)

        # Calculate text boundaries
        text_rect = draw_rect.adjusted(8, 2, -8, -2)
        
        # Draw status icon (smaller to fit)
        painter.setPen(QPen(text_color, 2))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        icon_rect = QRect(text_rect.left(), text_rect.top() + 2, 12, 12)
        painter.drawText(icon_rect, Qt.AlignCenter, icon_text)

        # Draw status text with proper boundaries
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        text_bounds = QRect(text_rect.left() + 16, text_rect.top(), 
                           text_rect.width() - 16, text_rect.height())
        
        # Adjust font size if text is too long
        font = painter.font()
        while QFontMetrics(font).horizontalAdvance(status_text) > text_bounds.width() and font.pointSize() > 6:
            font.setPointSize(font.pointSize() - 1)
            painter.setFont(font)
        
        painter.drawText(text_bounds, Qt.AlignVCenter, status_text)
