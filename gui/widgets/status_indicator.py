from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRect, Property, QPropertyAnimation, QParallelAnimationGroup
from PySide6.QtGui import QPainter, QColor, QBrush, QFont, QPen


class StatusIndicator(QWidget):
    """Professional SCADA-style rectangular status badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.status = "disconnected"
        self.connection_info = ""
        self.setFixedSize(140, 35)
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.animate_pulse)
        self.pulse_value = 0
        self.pulse_direction = 1
        self.is_animating = False
        self.setToolTip("Not connected")

        # Animation Properties (Initial Disconnected State)
        self._bg_color = QColor(245, 245, 245, 20)  # Very light tint
        self._border_color = QColor("#9E9E9E")      # Used as Accent Color
        self._text_color = QColor("#424242")

        # Animation Group
        self.anim_group = QParallelAnimationGroup(self)
        self.bg_anim = QPropertyAnimation(self, b"bg_color")
        self.border_anim = QPropertyAnimation(self, b"border_color")
        self.text_anim = QPropertyAnimation(self, b"text_color")

        for anim in [self.bg_anim, self.border_anim, self.text_anim]:
            anim.setDuration(300)
            self.anim_group.addAnimation(anim)

    @Property(QColor)
    def bg_color(self): return self._bg_color
    @bg_color.setter
    def bg_color(self, color):
        self._bg_color = color
        self.update()

    @Property(QColor)
    def border_color(self): return self._border_color
    @border_color.setter
    def border_color(self, color):
        self._border_color = color
        self.update()

    @Property(QColor)
    def text_color(self): return self._text_color
    @text_color.setter
    def text_color(self, color):
        self._text_color = color
        self.update()

    def set_status(self, status):
        """Set the status indicator with animation."""
        if self.status == status:
            return

        self.status = status
        
        # Define Target Colors
        # t_bg uses low alpha (20/255 ~= 8%) for a subtle tint
        if status == "connected":
            t_bg, t_border, t_text = QColor(232, 245, 233, 25), QColor("#4CAF50"), QColor("#2E7D32")
        elif status == "connecting":
            t_bg, t_border, t_text = QColor(255, 243, 224, 25), QColor("#FF9800"), QColor("#E65100")
        elif status == "error":
            t_bg, t_border, t_text = QColor(255, 235, 238, 25), QColor("#F44336"), QColor("#C62828")
        else: # disconnected
            t_bg, t_border, t_text = QColor(245, 245, 245, 20), QColor("#9E9E9E"), QColor("#616161")

        # Setup and start transitions
        self.anim_group.stop()
        self.bg_anim.setStartValue(self._bg_color)
        self.bg_anim.setEndValue(t_bg)
        self.border_anim.setStartValue(self._border_color)
        self.border_anim.setEndValue(t_border)
        self.text_anim.setStartValue(self._text_color)
        self.text_anim.setEndValue(t_text)
        self.anim_group.start()

        tooltips = {
            "connected": "Connection active",
            "connecting": "Attempting to connect...",
            "error": "Connection error",
            "disconnected": "Not connected"
        }
        self.setToolTip(tooltips.get(status, ""))

        if status == "connecting":
            self.is_animating = True
            self.animation_timer.start(60)
        else:
            self.is_animating = False
            self.animation_timer.stop()
            self.pulse_value = 0

    def set_connection_info(self, info):
        """Set the secondary connection details (IP, Port, Unit ID)."""
        # Add a subtle truncation or clean prefixing if needed
        self.connection_info = info.strip()
        self.update()

    def animate_pulse(self):
        """Animate pulsing effect for connecting state."""
        self.pulse_value += self.pulse_direction * 4
        if self.pulse_value >= 100 or self.pulse_value <= 0:
            self.pulse_direction *= -1
        self.update()

    def paintEvent(self, event):
        """Paint the SCADA-style status badge."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Icon and Text mapping (Statics)
        if self.status == "connected":
            status_text = "Connected"
            icon_text = "✔"
        elif self.status == "connecting":
            status_text = "Connecting"
            icon_text = "↻"
        elif self.status == "error":
            status_text = "Error"
            icon_text = "⚠"
        else:
            status_text = "Disconnected"
            icon_text = "○"

        # Apply pulsing alpha if connecting
        current_text_color = QColor(self._text_color)
        if self.status == "connecting":
            pulse_factor = self.pulse_value / 100.0
            current_text_color.setAlpha(140 + int(115 * pulse_factor))

        # 1. Draw Minimal Background Tint
        tint_rect = QRect(0, 2, 135, 30)
        painter.setBrush(QBrush(self._bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(tint_rect, 4, 4)

        # 2. Draw Left Accent Line (SCADA style)
        painter.setBrush(QBrush(self._border_color))
        painter.drawRoundedRect(0, 2, 3, 30, 1, 1)

        # 3. Draw Status Text and Icon
        font = QFont("Segoe UI", 9, QFont.Bold)
        if not font.exactMatch():
            font = QFont("Arial", 9, QFont.Bold)
        
        painter.setFont(font)
        painter.setPen(current_text_color)
        
        # Draw Icon
        icon_rect = QRect(10, 2, 25, 30)
        painter.drawText(icon_rect, Qt.AlignLeft | Qt.AlignVCenter, icon_text)
        
        # Draw Status Text
        text_rect = QRect(38, 2, 90, 30)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, status_text)
