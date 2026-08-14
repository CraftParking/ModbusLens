from PySide6.QtCore import QObject, QEvent, Qt

MIN_FONT_PX = 7
MAX_FONT_PX = 20


class _CtrlWheelZoomFilter(QObject):
    """Ctrl+scroll wheel zoom for a log/table widget whose font size is pinned by a QSS
    stylesheet -- a stylesheet's font-size always wins over widget.setFont()/zoomIn(), so
    "zoom" here means recomputing and reapplying the stylesheet at a new pixel size, via the
    caller-supplied `restyle(px)`, not adjusting the QFont object directly.

    Installed on the widget's viewport() rather than the widget itself: QTextEdit/QTableWidget
    are QAbstractScrollArea subclasses, and wheel events are delivered to the viewport widget,
    not the outer widget an event filter would naturally be installed on."""

    def __init__(self, widget, initial_px, restyle):
        super().__init__(widget)
        self._px = initial_px
        self._restyle = restyle

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            step = 1 if event.angleDelta().y() > 0 else -1
            new_px = max(MIN_FONT_PX, min(MAX_FONT_PX, self._px + step))
            if new_px != self._px:
                self._px = new_px
                self._restyle(new_px)
            return True
        return super().eventFilter(watched, event)


def install_ctrl_wheel_zoom(widget, initial_px, restyle):
    """Wire Ctrl+scroll wheel zoom into `widget` (a QTextEdit or QTableWidget). `restyle(px)`
    is called with the new font pixel size and is responsible for actually reapplying it
    (typically re-invoking the widget's own stylesheet-builder with the new size)."""
    zoom_filter = _CtrlWheelZoomFilter(widget, initial_px, restyle)
    widget.viewport().installEventFilter(zoom_filter)
    return zoom_filter
