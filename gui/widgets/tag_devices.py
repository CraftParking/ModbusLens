"""Add/Edit Device dialog and device validation.

A device is one Modbus unit with its own connection settings, configured on the Overview
tab: {"name": str, "unit": int, "connection": {...}} (see device_links). Devices whose
connection settings match share one physical link."""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)

from device_links import describe, link_key, normalize_connection, serial_conflict

UNIT_MIN, UNIT_MAX = 0, 255  # same range Connection Settings' Unit ID accepts
ADD_DEVICE_SENTINEL = "+ Add Device..."
# Logical index of the Tags table's Device column. Appended last so every existing
# hard-coded column index stays valid; it is only *displayed* next to Tag Name.
TAG_DEVICE_COLUMN = 15


def validate_device(name, unit, existing, editing=None, connection=None):
    """Error text for a device that can't be saved, or None. `editing` is the name of
    the device being edited (it may keep its own name and unit). A Unit ID only has to
    be unique among devices on the same link."""
    name = (name or "").strip()
    if not name:
        return "Enter a device name."
    if not UNIT_MIN <= unit <= UNIT_MAX:
        return f"Unit ID must be between {UNIT_MIN} and {UNIT_MAX}."
    key = link_key(connection) if connection else None
    for device in existing:
        if device["name"] == editing:
            continue
        if device["name"].lower() == name.lower():
            return f"A device named \"{device['name']}\" already exists."
        other_key = link_key(device.get("connection")) if device.get("connection") else None
        if device["unit"] == unit and (key is None or other_key is None or other_key == key):
            return f"Unit ID {unit} is already used by \"{device['name']}\" on this connection."
    if connection:
        return serial_conflict(connection, editing or name, existing)
    return None


class DeviceDialog(QDialog):
    """Name, connection (edited in the classic Connection Settings dialog) and Unit ID."""

    def __init__(self, existing, device=None, input_style="", parent=None,
                 default_connection=None, edit_connection=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Device" if device else "Add Device")
        self.setMinimumWidth(460)
        self._existing = existing
        self._editing = device["name"] if device else None
        self._edit_connection = edit_connection
        self._connection = normalize_connection(
            (device or {}).get("connection") or default_connection)

        layout = QVBoxLayout(self)
        hint = QLabel("A device is one Modbus unit: a name, how to reach it, and its Unit ID. "
                      "Devices with the same connection settings share one link (e.g. several "
                      "meters behind one gateway or on one RS-485 port).")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.name_input = QLineEdit(device["name"] if device else "")
        self.name_input.setPlaceholderText("e.g. LOAD meter")
        self.name_input.setStyleSheet(input_style)
        form.addRow("Name:", self.name_input)

        conn_row = QHBoxLayout()
        self.connection_label = QLabel(describe(self._connection))
        conn_row.addWidget(self.connection_label, 1)
        self.connection_btn = QPushButton("Connection Settings...")
        self.connection_btn.clicked.connect(self._change_connection)
        self.connection_btn.setEnabled(edit_connection is not None)
        conn_row.addWidget(self.connection_btn)
        form.addRow("Connection:", conn_row)

        self.unit_input = QSpinBox()
        self.unit_input.setRange(UNIT_MIN, UNIT_MAX)
        self.unit_input.setValue(device["unit"] if device else self._next_free_unit())
        self.unit_input.setStyleSheet(input_style)
        form.addRow("Unit ID:", self.unit_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #d9534f;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.name_input.setFocus()

    def _next_free_unit(self):
        key = link_key(self._connection)
        used = {d["unit"] for d in self._existing
                if not d.get("connection") or link_key(d["connection"]) == key}
        return next((u for u in range(1, UNIT_MAX + 1) if u not in used), 1)

    def _change_connection(self):
        result = self._edit_connection(self._connection, self.unit_input.value())
        if result is None:
            return
        self._connection, unit = result
        self.unit_input.setValue(unit)
        self.connection_label.setText(describe(self._connection))
        self.error_label.setText("")

    def _accept(self):
        error = validate_device(self.name_input.text(), self.unit_input.value(), self._existing,
                                self._editing, self._connection)
        if error:
            self.error_label.setText(error)
            return
        self.accept()

    def device(self):
        return {"name": self.name_input.text().strip(), "unit": self.unit_input.value(),
                "connection": dict(self._connection)}
