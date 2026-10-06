"""Stop the mouse wheel from changing dropdowns/number boxes that sit inside a table.

Qt hands a wheel event to whatever widget is under the cursor, so scrolling a table whose
cells are QComboBox/QSpinBox widgets (the Tags table, Trend's pen grid) silently changed
each cell the pointer passed over -- a tag's Device flipped to another meter, its Address
crept up by one. Guarded widgets pass the wheel to the enclosing scroll area instead, so
the table scrolls; values change only by click or keyboard."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QApplication


class _WheelGuard(QObject):
    def eventFilter(self, obj, event):
        if event.type() != QEvent.Wheel:
            return False
        parent = obj.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            QApplication.sendEvent(parent.viewport(), event)
        return True  # never let the cell widget itself act on it


_guard = None


def install_wheel_guard(widget):
    """Make `widget` (and its line edit, for an editable spin/combo) ignore the wheel."""
    global _guard
    if _guard is None:
        _guard = _WheelGuard()
    widget.setFocusPolicy(Qt.StrongFocus)  # no focus-by-wheel either
    widget.installEventFilter(_guard)
    return widget
