"""A "Device: [METER 1 ▾]" picker for the single-device tools (Address Table, Script,
Scanner, Diagnostics). Each tool talks to the device picked in its own selector -- there
is no app-wide "active device". The main window keeps every selector in sync with the
device list (see DeviceManagerMixin._refresh_device_selectors); like the Tags table's
Device column, a selector is only shown while there are 2+ devices."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget


class DeviceSelector(QWidget):
    changed = Signal(str)  # device name

    def __init__(self, main_window, label="Device:", tooltip="", parent=None):
        super().__init__(parent)
        self.mw = main_window
        self._device = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel(label)
        layout.addWidget(self.label)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(170)
        if tooltip:
            self.combo.setToolTip(tooltip)
        style = getattr(main_window, "_get_input_style", None)
        if style:
            self.combo.setStyleSheet(style())
        self.combo.currentIndexChanged.connect(self._on_index_changed)
        layout.addWidget(self.combo)
        selectors = getattr(main_window, "_device_selectors", None)
        if selectors is not None:
            selectors.append(self)
        self.refresh()

    # -- model ------------------------------------------------------------------
    def device(self):
        """The selected device's name (the first device if nothing's picked yet)."""
        names = self._names()
        if self._device in names:
            return self._device
        return names[0] if names else None

    def set_device(self, name):
        if name in self._names() and name != self._device:
            self._device = name
            self.refresh()
            self.changed.emit(name)

    def modbus(self):
        """A DeviceView of the selected device, or None while it isn't connected."""
        name = self.device()
        return self.mw._device_view(name) if name else None

    def unit(self):
        name = self.device()
        return self.mw._tag_device_unit(name) if name else None

    def is_connected(self):
        view = self.modbus()
        return bool(view is not None and view.is_connected())

    def describe(self):
        """'METER 2 -- 192.168.1.254:4196 (RTU over TCP), Unit 2' for status lines."""
        name = self.device()
        return self.mw._describe_device(name) if name else ""

    # -- UI ---------------------------------------------------------------------
    def _names(self):
        return [d["name"] for d in getattr(self.mw, "tag_devices", [])]

    def refresh(self, renamed=None):
        if renamed and self._device in renamed:
            self._device = renamed[self._device]
        previous = self.device()
        devices = getattr(self.mw, "tag_devices", [])
        self.combo.blockSignals(True)
        self.combo.clear()
        for d in devices:
            self.combo.addItem(f"{d['name']} (Unit {d['unit']})", d["name"])
        self.combo.setCurrentIndex(max(self.combo.findData(previous), 0))
        self.combo.blockSignals(False)
        self._device = previous
        self.setVisible(len(devices) > 1)

    def _on_index_changed(self, _index):
        name = self.combo.currentData()
        if name and name != self._device:
            self._device = name
            self.changed.emit(name)
