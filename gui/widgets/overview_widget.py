"""Overview tab: one card per device on the current connection -- status at a glance
(online / no response / device exception / paused / not monitoring, success rate, last
poll) plus a few pinned live values, with Open Tags jumping to that device's tab inside
Tags. Purely a view over the Tags table and Tag Monitoring's results: values come from
the table's own Read/Engineering Value cells, status from MonitoringManager.device_stats,
so nothing here polls the wire on its own (the Unit ID sweep below is the one exception,
and only runs on request, with monitoring stopped)."""

import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from device_links import describe, link_key, normalize_connection
from widgets.tag_devices import UNIT_MAX, validate_device

MAX_PINNED = 6
DEFAULT_PINNED = 4

STATUS_LABELS = {
    "disconnected": "Disconnected",
    "failed": "Connection failed",
    "reconnecting": "Reconnecting...",
    "online": "Online",
    "exception": "Device exception",
    "partial": "Partly failing",
    "no_response": "No response",
    "paused": "Paused",
    "idle": "Connected",
    "no_tags": "No tags",
    "waiting": "Waiting for first poll",
}


def status_color(status, colors):
    return {
        "online": colors.get("log_connect", "#2E7D32"),
        "idle": colors.get("log_connect", "#2E7D32"),
        "failed": colors.get("log_error", "#C62828"),
        "reconnecting": colors.get("log_warning", "#EF6C00"),
        "exception": colors.get("log_warning", "#EF6C00"),
        "partial": colors.get("log_warning", "#EF6C00"),
        "no_response": colors.get("log_error", "#C62828"),
    }.get(status, colors.get("text_disabled", "#999999"))


def device_status(stats, monitoring_active, paused, tag_count, link_state="connected"):
    """The one status word a card/status-bar entry shows: the device's link state first
    ("disconnected" / "failed" / "reconnecting"), then poll health from
    MonitoringManager.device_stats[key]."""
    if link_state != "connected":
        return link_state
    if paused:
        return "paused"
    if not tag_count:
        return "no_tags"
    if not monitoring_active:
        return "idle"
    if not stats or not stats.get("status"):
        return "waiting"
    return stats["status"]


def format_age(seconds):
    if seconds is None:
        return "never"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{int(seconds // 3600)}h ago"


class DeviceCard(QFrame):
    open_tags = Signal(str)
    pin_values = Signal(str)
    toggle_pause = Signal(str)
    edit_device = Signal(str)
    remove_device = Signal(str)
    toggle_connect = Signal(str)

    WIDTH = 360

    def __init__(self, key, colors, button_style, parent=None):
        super().__init__(parent)
        self.key = key
        self.colors = colors
        self.setObjectName("deviceCard")
        self.setFixedWidth(self.WIDTH)
        # Only as tall as its content, not stretched to the grid's height.
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        self._active = None
        self.set_active(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {colors['heading']};")
        top.addWidget(self.title, 1)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        top.addWidget(self.dot)
        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: 600;")
        top.addWidget(self.status_label)
        if True:
            menu_btn = QToolButton()
            menu_btn.setText("⋮")
            menu_btn.setAutoRaise(True)
            menu_btn.setPopupMode(QToolButton.InstantPopup)
            menu_btn.setToolTip("Edit or remove this device")
            menu_btn.setStyleSheet("QToolButton { border: none; font-size: 16px; padding: 0 4px; }"
                                   " QToolButton::menu-indicator { image: none; width: 0; }")
            menu = QMenu(menu_btn)
            menu.addAction("Edit Device...", lambda: self.edit_device.emit(self.key))
            menu.addAction("Remove Device...", lambda: self.remove_device.emit(self.key))
            menu_btn.setMenu(menu)
            top.addWidget(menu_btn)
        layout.addLayout(top)

        self.subtitle = QLabel()
        self.subtitle.setStyleSheet(f"color: {colors['text_dim']};")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {colors['border_light']};")
        layout.addWidget(line)

        self.values_grid = QGridLayout()
        self.values_grid.setHorizontalSpacing(12)
        self.values_grid.setVerticalSpacing(4)
        layout.addLayout(self.values_grid)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(f"color: {colors['text_dim']}; font-size: 11px;")
        layout.addWidget(self.detail)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.connect_btn = QPushButton("Connect")
        self.open_btn = QPushButton("Open Tags")
        self.pin_btn = QPushButton("Pin Values...")
        self.pause_btn = QPushButton("Pause")
        self.connect_btn.clicked.connect(lambda: self.toggle_connect.emit(self.key))
        for btn in (self.connect_btn, self.open_btn, self.pin_btn, self.pause_btn):
            btn.setStyleSheet(button_style)
            buttons.addWidget(btn)
        self.open_btn.clicked.connect(lambda: self.open_tags.emit(self.key))
        self.pin_btn.clicked.connect(lambda: self.pin_values.emit(self.key))
        self.pause_btn.clicked.connect(lambda: self.toggle_pause.emit(self.key))
        layout.addLayout(buttons)
        self._value_labels = []

    def set_active(self, active):
        """Highlight this card with an accent border (used to point at a device, e.g. after
        clicking it in the top bar)."""
        if active == self._active:
            return
        self._active = active
        c = self.colors
        border = f"2px solid {c['accent']}" if active else f"1px solid {c['border']}"
        self.setStyleSheet(
            f"QFrame#deviceCard {{ background: {c['surface']}; border: {border}; border-radius: 4px; }}"
            f" QLabel {{ background: transparent; border: none; font-weight: normal; }}"
        )

    def update_view(self, title, subtitle, status, detail, values, paused, connected=False):
        self.connect_btn.setText("Disconnect" if connected or status == "reconnecting" else "Connect")
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        color = status_color(status, self.colors)
        self.dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.status_label.setText(STATUS_LABELS.get(status, status))
        self.status_label.setStyleSheet(f"font-weight: 600; color: {color};")
        self.detail.setText(detail)
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.pause_btn.setToolTip("Skip this device in Tag Monitoring's poll cycle" if not paused
                                  else "Poll this device again")

        if len(self._value_labels) != len(values):
            while self.values_grid.count():
                item = self.values_grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._value_labels = []
            for i in range(len(values)):
                name = QLabel()
                name.setStyleSheet(f"color: {self.colors['text_dim']};")
                value = QLabel()
                value.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {self.colors['text']};")
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.values_grid.addWidget(name, i // 2, (i % 2) * 2)
                self.values_grid.addWidget(value, i // 2, (i % 2) * 2 + 1)
                self._value_labels.append((name, value))
        for (name_label, value_label), (name, value) in zip(self._value_labels, values):
            name_label.setText(name)
            value_label.setText(value or "--")
        if not values:
            self.detail.setText((detail + "\n" if detail else "") + "No values pinned -- use Pin Values...")


class PinValuesDialog(QDialog):
    def __init__(self, title, tag_names, pinned, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Pin Values - {title}")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Choose up to {MAX_PINNED} tags to show on this device's card:"))
        self.list = QListWidget()
        for name in tag_names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in pinned else Qt.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._limit)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _limit(self, item):
        if item.checkState() == Qt.Checked and len(self.pinned()) > MAX_PINNED:
            self.list.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.list.blockSignals(False)

    def pinned(self):
        return [self.list.item(i).text() for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class AddFromProfileDialog(QDialog):
    """Pick a saved profile, then name the device and give it a Unit ID -- e.g. two
    "Secure Elite 500" devices at units 1 and 2 from one profile."""

    def __init__(self, profiles, existing, input_style="", parent=None, connection=None, edit_connection=None):
        super().__init__(parent)
        self.setWindowTitle("Add Device from Profile")
        self.profiles = profiles
        self.existing = existing
        self.connection = normalize_connection(connection)
        self._edit_connection = edit_connection
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.profile_combo = QComboBox()
        for p in profiles:
            self.profile_combo.addItem(f"{p.get('name', '(unnamed)')} ({len(p.get('tags') or [])} tags)")
        form.addRow("Profile:", self.profile_combo)
        self.name_input = QLineEdit()
        self.name_input.setStyleSheet(input_style)
        form.addRow("Device name:", self.name_input)
        conn_row = QHBoxLayout()
        self.connection_label = QLabel(describe(self.connection))
        conn_row.addWidget(self.connection_label, 1)
        conn_btn = QPushButton("Connection Settings...")
        conn_btn.setEnabled(edit_connection is not None)
        conn_btn.clicked.connect(self._change_connection)
        conn_row.addWidget(conn_btn)
        form.addRow("Connection:", conn_row)
        self.unit_input = QSpinBox()
        self.unit_input.setRange(0, UNIT_MAX)
        used = {d["unit"] for d in existing if link_key(d.get("connection")) == link_key(self.connection)}
        self.unit_input.setValue(next((u for u in range(1, UNIT_MAX + 1) if u not in used), 1))
        self.unit_input.setStyleSheet(input_style)
        form.addRow("Unit ID:", self.unit_input)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d9534f;")
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.profile_combo.currentIndexChanged.connect(self._suggest_name)
        self._suggest_name()

    def _suggest_name(self):
        base = str(self.profiles[self.profile_combo.currentIndex()].get("name", "Device")) if self.profiles else "Device"
        names = {d["name"].lower() for d in self.existing}
        name, n = base, 2
        while name.lower() in names:
            name, n = f"{base} {n}", n + 1
        self.name_input.setText(name)

    def _change_connection(self):
        result = self._edit_connection(self.connection, self.unit_input.value())
        if result:
            self.connection, unit = result
            self.unit_input.setValue(unit)
            self.connection_label.setText(describe(self.connection))

    def _accept(self):
        error = validate_device(self.name_input.text(), self.unit_input.value(), self.existing,
                                connection=self.connection)
        if error:
            self.error_label.setText(error)
            return
        self.accept()

    def result_device(self):
        profile = self.profiles[self.profile_combo.currentIndex()]
        return {"name": self.name_input.text().strip(), "unit": self.unit_input.value(),
                "connection": dict(self.connection),
                "profile": str(profile.get("name", ""))}, list(profile.get("tags") or [])


class UnitSweepWorker(QThread):
    """Probes Unit IDs one at a time over the app's OWN live connection -- so it works
    the same over Modbus TCP, RTU over TCP, and serial, and never opens extra sockets a
    small gateway might not allow. Any reply counts as "present", including a Modbus
    exception (the device answered, it just didn't like address 0)."""

    progress = Signal(int, int)  # unit, found (1/0)
    done = Signal(list)

    def __init__(self, modbus, units, timeout_s, reserve_range, release_range):
        super().__init__()
        self.modbus = modbus
        self.units = list(units)
        self.timeout_s = timeout_s
        self.reserve_range = reserve_range
        self.release_range = release_range
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        found = []
        original_timeout = self.modbus.get_timeout()
        self.modbus.set_timeout(self.timeout_s)
        try:
            for unit in self.units:
                if self.should_stop:
                    break
                request_range = {"operation": "read", "space": "Holding Register", "start": 0, "end": 0,
                                 "unit": unit, "tag": f"UnitSweep[{unit}]"}
                if not self.reserve_range(request_range):
                    time.sleep(0.05)
                    if not self.reserve_range(request_range):
                        self.progress.emit(unit, 0)
                        continue
                try:
                    result = self.modbus.read_registers(0, 1, unit_id=unit)
                    answered = result is not None or self.modbus.last_exception_code is not None
                finally:
                    self.release_range(request_range)
                if answered:
                    found.append(unit)
                self.progress.emit(unit, 1 if answered else 0)
        finally:
            self.modbus.set_timeout(original_timeout)
        self.done.emit(found)


class UnitSweepDialog(QDialog):
    def __init__(self, mw, existing, parent=None, client=None):
        super().__init__(parent)
        self.mw = mw
        self.client = client if client is not None else mw.modbus
        self.existing = existing
        self.worker = None
        self.setWindowTitle("Find Devices (Unit ID Sweep)")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        info = QLabel(
            "Asks each Unit ID in the range, one at a time, over the chosen connection "
            "(read of holding register 0). Anything that answers -- data or a Modbus "
            "exception -- is listed. Keep the range small on a busy shared bus."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        form = QFormLayout()
        row = QHBoxLayout()
        self.from_spin = QSpinBox(); self.from_spin.setRange(1, 247); self.from_spin.setValue(1)
        self.to_spin = QSpinBox(); self.to_spin.setRange(1, 247); self.to_spin.setValue(10)
        row.addWidget(self.from_spin); row.addWidget(QLabel("to")); row.addWidget(self.to_spin)
        form.addRow("Unit IDs:", row)
        self.timeout_spin = QSpinBox(); self.timeout_spin.setRange(100, 3000); self.timeout_spin.setValue(500)
        self.timeout_spin.setSuffix(" ms")
        form.addRow("Timeout per unit:", self.timeout_spin)
        layout.addLayout(form)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.results = QListWidget()
        layout.addWidget(self.results)
        btns = QHBoxLayout()
        self.start_btn = QPushButton("Start Sweep")
        self.add_btn = QPushButton("Add Selected as Devices")
        self.add_btn.setEnabled(False)
        close_btn = QPushButton("Close")
        for b in (self.start_btn, self.add_btn, close_btn):
            btns.addWidget(b)
        layout.addLayout(btns)
        self.start_btn.clicked.connect(self._start_or_stop)
        self.add_btn.clicked.connect(self.accept)
        close_btn.clicked.connect(self.reject)

    def _start_or_stop(self):
        if self.worker is not None:
            self.worker.stop()
            self.start_btn.setEnabled(False)
            return
        lo, hi = sorted((self.from_spin.value(), self.to_spin.value()))
        self.results.clear()
        self.progress.setRange(0, hi - lo + 1)
        self.progress.setValue(0)
        self.worker = UnitSweepWorker(self.client, range(lo, hi + 1), self.timeout_spin.value() / 1000.0,
                                      self.mw._reserve_range, self.mw._release_range)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.start_btn.setText("Stop")
        self.worker.start()

    def _on_progress(self, unit, found):
        self.progress.setValue(self.progress.value() + 1)
        if found:
            taken = next((d["name"] for d in self.existing if d["unit"] == unit), None)
            item = QListWidgetItem(f"Unit {unit}" + (f"  (already: {taken})" if taken else ""))
            item.setData(Qt.UserRole, unit)
            if taken:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
            self.results.addItem(item)

    def _on_done(self, found):
        self.worker.wait()
        self.worker = None
        self.start_btn.setText("Start Sweep")
        self.start_btn.setEnabled(True)
        self.add_btn.setEnabled(bool(self.selected_units()))
        if not found:
            self.results.addItem("No unit answered in this range.")

    def selected_units(self):
        units = []
        for i in range(self.results.count()):
            item = self.results.item(i)
            if item.data(Qt.UserRole) is not None and item.flags() & Qt.ItemIsUserCheckable \
                    and item.checkState() == Qt.Checked:
                units.append(item.data(Qt.UserRole))
        return units

    def reject(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait()
            self.worker = None
        super().reject()


class OverviewWidget(QWidget):
    """Laid out like the app's other tabs: titled group boxes on the window background --
    Monitoring Controls (same buttons/interval as the Tags tab, kept in sync) and Devices
    (add buttons + the card grid)."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.colors = c = main_window._colors()
        self.cards = {}
        self._highlighted = None  # a card pointed at from the top bar (see show_device)
        group_style = main_window._get_groupbox_style()
        button_style = main_window._get_button_style()
        label_style = f"color: {c['text_secondary']}; font-weight: normal;"

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # -- Monitoring Controls (mirrors the Tags tab's group of the same name)
        control_group = QGroupBox("Monitoring Controls")
        control_group.setStyleSheet(group_style)
        controls = QHBoxLayout(control_group)
        controls.setSpacing(10)
        controls.setContentsMargins(15, 15, 15, 15)
        self.start_btn = QPushButton("Start Monitoring")
        self.stop_btn = QPushButton("Stop Monitoring")
        for btn in (self.start_btn, self.stop_btn):
            btn.setStyleSheet(button_style)
            btn.setMinimumWidth(120)
            controls.addWidget(btn)
        self.start_btn.clicked.connect(main_window._start_monitoring)
        self.stop_btn.clicked.connect(main_window._stop_monitoring)
        controls.addStretch()
        interval_label = QLabel("Interval (ms):")
        interval_label.setStyleSheet(label_style)
        controls.addWidget(interval_label)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 10000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setMinimumWidth(80)
        self.interval_spin.setStyleSheet(main_window._get_input_style())
        self.interval_spin.setToolTip("Same setting as the Tags tab's poll interval")
        self.interval_spin.valueChanged.connect(self._on_interval_changed)
        controls.addWidget(self.interval_spin)
        self.summary = QLabel()
        self.summary.setStyleSheet(label_style + " padding-left: 20px;")
        controls.addWidget(self.summary)
        layout.addWidget(control_group)

        # -- Devices: add buttons + card grid
        devices_group = QGroupBox("Devices")
        devices_group.setStyleSheet(group_style)
        devices_layout = QVBoxLayout(devices_group)
        devices_layout.setSpacing(10)
        devices_layout.setContentsMargins(15, 20, 15, 15)
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        for text, slot, width, tip in (
            ("Add Device", self._add_blank, 120, "A device by name and Unit ID; add its tags afterwards"),
            ("Add from Profile...", self._add_from_profile, 150, "A device with a saved profile's tags"),
            ("Find Devices...", self._add_from_sweep, 130,
             "Unit ID sweep over the current connection -- lists every unit that answers"),
        ):
            btn = QPushButton(text)
            btn.setStyleSheet(button_style)
            btn.setMinimumWidth(width)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            add_row.addWidget(btn)
        add_row.addStretch()
        remove_all_btn = QPushButton("Remove All Devices")
        remove_all_btn.setStyleSheet(button_style)
        remove_all_btn.setMinimumWidth(150)
        remove_all_btn.setToolTip("Disconnect and delete every device and all their tags (asks first)")
        remove_all_btn.clicked.connect(self._remove_all)
        add_row.addWidget(remove_all_btn)
        devices_layout.addLayout(add_row)

        self.empty_label = QLabel(
            "No devices yet.\n\nTags without a device are polled on the connection's own Unit ID. "
            "Add a device for each unit on this connection -- e.g. two meters at Unit IDs 1 and 2 "
            "behind one gateway."
        )
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet(
            f"color: {c['text_dim']}; font-weight: normal; font-size: 12px; padding: 30px; border: none;")
        devices_layout.addWidget(self.empty_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.container = QWidget()
        self.container.setObjectName("overviewCards")
        self.container.setStyleSheet("QWidget#overviewCards { background: transparent; }")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.container)
        devices_layout.addWidget(self.scroll, 1)
        layout.addWidget(devices_group, 1)

        self._columns = 0
        self._interval_linked = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _on_interval_changed(self, value):
        tags_spin = getattr(self.mw, "tag_monitoring_interval", None)
        if tags_spin is not None and tags_spin.value() != value:
            tags_spin.setValue(value)

    def _link_interval(self):
        """Two-way sync with the Tags tab's interval spinbox (built after this tab)."""
        tags_spin = getattr(self.mw, "tag_monitoring_interval", None)
        if tags_spin is None or self._interval_linked:
            return
        self._interval_linked = True
        self.interval_spin.setValue(tags_spin.value())
        tags_spin.valueChanged.connect(self._mirror_tags_interval)

    def _mirror_tags_interval(self, value):
        if self.interval_spin.value() != value:
            self.interval_spin.setValue(value)

    # ----------------------------------------------------------------- data --
    def device_keys(self):
        return [d["name"] for d in self.mw.tag_devices], self.mw._get_monitoring_tags()

    def refresh(self):
        # Built first (it's the first tab), before the Tags table and monitoring manager
        # exist -- the 1 s timer picks it up once the main window is fully constructed.
        if not hasattr(self.mw, "monitoring_tag_table") or not hasattr(self.mw, "monitoring_manager"):
            return
        self._link_interval()
        keys, tags = self.device_keys()
        for key in list(self.cards):
            if key not in keys:
                self.cards.pop(key).deleteLater()
        for key in keys:
            if key not in self.cards:
                card = DeviceCard(key, self.colors, self.mw._get_button_style(small=True))
                card.open_tags.connect(self.mw._show_tags_for_device)
                card.pin_values.connect(self._pin_values)
                card.toggle_pause.connect(self._toggle_pause)
                card.edit_device.connect(self.mw._edit_tag_device)
                card.remove_device.connect(self.mw._remove_tag_device)
                card.toggle_connect.connect(self._toggle_connect)
                self.cards[key] = card
        self._layout_cards(keys)
        self.empty_label.setVisible(not self.mw.tag_devices)
        self.scroll.setVisible(bool(self.mw.tag_devices))

        active = bool(getattr(self.mw, "monitoring_active", False))
        n_connected = sum(1 for k in keys if self.mw._device_is_connected(k))
        self.start_btn.setEnabled(n_connected > 0 and not active)
        self.stop_btn.setEnabled(active)
        self.summary.setText(f"{len(keys)} device(s), {n_connected} connected")

        stats_all = self.mw.monitoring_manager.device_stats
        now = time.time()
        for key in keys:
            meta = self.mw._device_meta(key)
            device_tags = [t for t in tags if t.get("device", "") == key]
            pinned = [n for n in self.mw._device_pinned(key) if any(t["name"] == n for t in device_tags)]
            values = [(n, self.mw._tag_display_value(next(t for t in device_tags if t["name"] == n)))
                      for n in pinned]
            stats = stats_all.get(key, {})
            paused = bool(meta.get("paused"))
            link_state = self.mw._device_link_state(key)
            status = device_status(stats, active, paused, len(device_tags), link_state)
            title = key
            subtitle_parts = [describe(meta.get("connection")), f"Unit {meta.get('unit')}",
                              f"{len(device_tags)} tag(s)"]
            if meta.get("profile"):
                subtitle_parts.insert(1, meta["profile"])
            total = stats.get("ok", 0) + stats.get("fail", 0)
            detail_parts = []
            if total:
                detail_parts.append(f"{100 * stats.get('ok', 0) / total:.0f}% OK of {total} reads")
            detail_parts.append(f"last good read {format_age(now - stats['last_ok'] if stats.get('last_ok') else None)}")
            if stats.get("latency_ms") is not None:
                detail_parts.append(f"{stats['latency_ms']:.0f} ms")
            detail = " · ".join(detail_parts)
            if status in ("no_response", "exception", "partial") and stats.get("last_error"):
                detail += f"\n{stats['last_error'][:120]}"
            if link_state == "failed":
                detail = f"Couldn't connect: {self.mw.link_pool.link_for(meta['connection']).last_error or ''}"
            elif link_state == "disconnected":
                detail = "Not connected -- click Connect."
            card = self.cards[key]
            card.update_view(title, " · ".join(subtitle_parts), status, detail, values, paused,
                             connected=link_state in ("connected", "reconnecting"))
            card.set_active(key == self._highlighted)

    def show_device(self, key):
        """Highlight `key`'s card and scroll it into view (top-bar click)."""
        self._highlighted = key
        self.refresh()
        card = self.cards.get(key)
        if card is not None:
            self.scroll.ensureWidgetVisible(card)
        QTimer.singleShot(2500, self._clear_highlight)

    def _clear_highlight(self):
        self._highlighted = None
        self.refresh()

    def _layout_cards(self, keys):
        columns = max(1, (self.scroll.viewport().width() - 12) // (DeviceCard.WIDTH + 12))
        current = [self.grid.itemAt(i).widget() for i in range(self.grid.count())]
        wanted = [self.cards[k] for k in keys]
        if columns == self._columns and current == wanted:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(wanted):
            self.grid.addWidget(card, i // columns, i % columns, Qt.AlignTop)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._columns = 0
        self.refresh()

    # -------------------------------------------------------------- actions --
    def _pin_values(self, key):
        names = [t["name"] for t in self.mw._get_monitoring_tags() if t.get("device", "") == key]
        if not names:
            QMessageBox.information(self, "Pin Values", "This device has no tags yet.")
            return
        dialog = PinValuesDialog(key, names, self.mw._device_pinned(key), self)
        if dialog.exec() == QDialog.Accepted:
            self.mw._device_meta(key)["pinned"] = dialog.pinned()
            self.mw._save_devices()
            self.refresh()

    def _toggle_pause(self, key):
        meta = self.mw._device_meta(key)
        meta["paused"] = not meta.get("paused")
        self.mw._log(f"{'Paused' if meta['paused'] else 'Resumed'} polling of {key}")
        self.mw._save_devices()
        self.refresh()

    def _toggle_connect(self, key):
        if key in self.mw._connected_devices:
            self.mw._disconnect_device(key)
        else:
            self.mw._connect_device(key)
        self.refresh()

    def _remove_all(self):
        self.mw._remove_all_tag_devices()
        self.refresh()

    def _add_blank(self):
        self.mw._add_tag_device_interactive()
        self.refresh()

    def _add_from_profile(self):
        from widgets.device_profiles import list_profiles
        profiles = [p for p in list_profiles() if p.get("tags")]
        if not profiles:
            QMessageBox.information(self, "Add Device from Profile",
                                    "No saved profiles with tags yet -- create or download one in the Profiles tab.")
            return
        dialog = AddFromProfileDialog(profiles, self.mw.tag_devices, self.mw._get_input_style(), self,
                                      connection=self.mw._device_connection(self.mw.tag_devices[0]["name"]),
                                      edit_connection=self.mw._edit_connection_dialog)
        if dialog.exec() != QDialog.Accepted:
            return
        device, rows = dialog.result_device()
        self.mw._add_tag_device(device)
        imported, skipped = self.mw._import_additional_tag_rows(rows, device=device["name"])
        self.mw._log(f"Added device '{device['name']}' (Unit {device['unit']}) from profile "
                     f"'{device['profile']}': {imported} tag(s)")
        self.refresh()

    def _add_from_sweep(self):
        # One entry per connected link: the sweep asks Unit IDs over that connection.
        links = {}
        for d in self.mw.tag_devices:
            if self.mw._device_is_connected(d["name"]):
                links.setdefault(link_key(d["connection"]), d)
        if not links:
            QMessageBox.information(
                self, "Find Devices",
                "Connect a device first -- the sweep asks other Unit IDs over its connection, "
                "and adds what it finds with the same connection settings.")
            return
        via = next(iter(links.values()))
        if len(links) > 1:
            labels = {f"{describe(d['connection'])}  (via {d['name']})": d for d in links.values()}
            choice, ok = QInputDialog.getItem(self, "Find Devices", "Sweep Unit IDs on which connection?",
                                              list(labels), 0, False)
            if not ok:
                return
            via = labels[choice]
        if getattr(self.mw, "monitoring_active", False):
            QMessageBox.information(self, "Find Devices", "Stop monitoring first, so the sweep has the line to itself.")
            return
        conn = self.mw._device_connection(via["name"])
        same_link = [d for d in self.mw.tag_devices if link_key(d["connection"]) == link_key(conn)]
        dialog = UnitSweepDialog(self.mw, same_link, self, client=self.mw._device_client(via["name"]))
        if dialog.exec() != QDialog.Accepted:
            return
        for unit in dialog.selected_units():
            name, n = f"Unit {unit}", 2
            while any(d["name"].lower() == name.lower() for d in self.mw.tag_devices):
                name, n = f"Unit {unit} ({n})", n + 1
            self.mw._add_tag_device({"name": name, "unit": unit, "connection": dict(conn)})
            self.mw._log(f"Added device '{name}' found by Unit ID sweep")
        self.refresh()


class DeviceStatusBar(QWidget):
    """The top bar's device strip: one entry per device -- status dot, name, status word.
    Click an entry to jump to that device's card on the Overview tab."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.colors = main_window._colors()
        self.entries = {}
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setObjectName("deviceStrip")
        inner.setStyleSheet("QWidget#deviceStrip { background: transparent; }")
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.setSpacing(8)
        self.row.addStretch()
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self):
        mw = self.mw
        if not hasattr(mw, "monitoring_manager") or not hasattr(mw, "link_pool"):
            return
        names = [d["name"] for d in mw.tag_devices]
        for name in list(self.entries):
            if name not in names:
                self.entries.pop(name).deleteLater()
        order = [self.row.itemAt(i).widget() for i in range(self.row.count() - 1)]
        for name in names:
            if name not in self.entries:
                entry = _StatusEntry(name, self.colors)
                entry.clicked.connect(mw._show_device_card)
                self.entries[name] = entry
        if order != [self.entries[n] for n in names]:
            for widget in order:
                self.row.removeWidget(widget)
            for i, name in enumerate(names):
                self.row.insertWidget(i, self.entries[name])
        for name in names:
            entry = self.entries[name]
            meta = mw._device_meta(name)
            device_tags = [t for t in mw._get_monitoring_tags() if t.get("device") == name] \
                if hasattr(mw, "monitoring_tag_table") else []
            status = device_status(mw.monitoring_manager.device_stats.get(name, {}),
                                   bool(getattr(mw, "monitoring_active", False)), bool(meta.get("paused")),
                                   len(device_tags) or 1, mw._device_link_state(name))
            entry.update_view(status, False,
                              f"{name}: {describe(meta.get('connection'))}, Unit {meta.get('unit')}\n"
                              f"{STATUS_LABELS.get(status, status)}\nClick to show it on the Overview")


class _StatusEntry(QFrame):
    clicked = Signal(str)

    def __init__(self, name, colors):
        super().__init__()
        self.name = name
        self.colors = colors
        self.setObjectName("statusEntry")
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 10, 3)
        layout.setSpacing(6)
        self.dot = QLabel()
        self.dot.setFixedSize(10, 10)
        layout.addWidget(self.dot)
        self.name_label = QLabel(name)
        layout.addWidget(self.name_label)
        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self._state = None

    def update_view(self, status, active, tooltip):
        state = (status, active)
        self.setToolTip(tooltip)
        if state == self._state:
            return
        self._state = state
        c = self.colors
        color = status_color(status, c)
        self.dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.name_label.setStyleSheet(f"font-weight: bold; color: {c['heading']}; background: transparent;")
        self.status_label.setText(STATUS_LABELS.get(status, status))
        self.status_label.setStyleSheet(f"color: {color}; background: transparent;")
        border = f"2px solid {c['accent']}" if active else f"1px solid {c['border_light']}"
        self.setStyleSheet(f"QFrame#statusEntry {{ background: {c['surface_alt']}; border: {border};"
                           f" border-radius: 12px; }}")

    def mousePressEvent(self, event):
        self.clicked.emit(self.name)
        super().mousePressEvent(event)
