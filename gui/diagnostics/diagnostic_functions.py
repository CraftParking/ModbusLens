"""Diagnostics > Modbus Diagnostic Functions -- FC07 Read Exception Status, FC08
Diagnostics (Loopback/Restart/Read Diagnostic Register/Clear Counters), FC11/12 Get Comm
Event Counter/Log, FC17 Report Server ID, FC20/21 Read/Write File Record, FC22 Mask
Write Register, FC24 Read FIFO Queue, and FC43 Read Device Information.

pymodbus's client already implements the wire protocol for every one of these (see
core/modbus_client.py's wrappers) -- there was just no ModbusLens UI to reach them before.
Niche next to the four basic read/write operations, but a real gap for compliance/interop
testing. One dialog covers all of them, rather than ModbusTools' one-dialog-per-function
approach, since these are occasional diagnostic probes rather than a primary workflow --
a function picker plus the couple of parameters each one actually needs is enough.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QLineEdit, QCheckBox, QTextEdit, QWidget,
)


def _parse_hex_bytes(text):
    """Accepts "1234", "12 34", or "0x12 0x34" -- whatever's easiest to type -- and
    returns the raw bytes. Raises ValueError on anything that isn't an even number of
    hex digits once separators/0x prefixes are stripped."""
    cleaned = text.strip()
    for token in ("0x", "0X"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.replace(" ", "").replace(",", "")
    if not cleaned:
        return b""
    if len(cleaned) % 2 != 0 or any(ch not in "0123456789abcdefABCDEF" for ch in cleaned):
        raise ValueError("expected an even number of hex digits, e.g. \"12 34\" or \"1234\"")
    return bytes.fromhex(cleaned)


def _format_identifier(data):
    """Report Server ID's identifier is vendor-defined free-form bytes -- show it as text
    when it decodes cleanly (the common case), otherwise fall back to hex."""
    try:
        return data.decode("ascii")
    except UnicodeDecodeError:
        return data.hex(" ")


READ_CODE_OPTIONS = [("Basic", 0x01), ("Regular", 0x02), ("Extended", 0x03), ("Specific object", 0x04)]


def _spin_param(name, minimum=0, maximum=65535, default=0, tooltip=""):
    return {"name": name, "kind": "spin", "minimum": minimum, "maximum": maximum, "default": default, "tooltip": tooltip}


def _hex_param(name, default="", tooltip=""):
    return {"name": name, "kind": "hex", "default": default, "tooltip": tooltip}


def _check_param(name, default=True, tooltip=""):
    return {"name": name, "kind": "check", "default": default, "tooltip": tooltip}


def _combo_param(name, options, tooltip=""):
    return {"name": name, "kind": "combo", "options": options, "tooltip": tooltip}


def _run_simple(method_name, *arg_names):
    """Most functions here just forward their param values positionally to one
    ModbusClient method of the same shape -- this covers all of those in one place."""
    def run(modbus, values):
        return getattr(modbus, method_name)(*(values[name] for name in arg_names))
    return run


FUNCTIONS = [
    {
        "key": "read_exception_status",
        "label": "Read Exception Status (FC07)",
        "params": [],
        "run": _run_simple("read_exception_status"),
        "format": lambda r: f"Exception status: 0x{r:02X}  ({r:#010b})",
    },
    {
        "key": "diag_query_data",
        "label": "Diagnostics: Loopback / Query Data (FC08-00)",
        "params": [_hex_param("Message (hex)", default="1234", tooltip="Bytes to send; a working device echoes them back unchanged.")],
        "run": lambda modbus, values: modbus.diag_query_data(_parse_hex_bytes(values["Message (hex)"])),
        "format": lambda r: f"Echoed back: {r.hex(' ') if r else '(empty)'}",
    },
    {
        "key": "diag_restart_communication",
        "label": "Diagnostics: Restart Communications (FC08-01)",
        "params": [_check_param("Clear event log/counters too", default=True)],
        "run": _run_simple("diag_restart_communication", "Clear event log/counters too"),
        "format": lambda r: "Restart acknowledged" if r else "Failed",
    },
    {
        "key": "diag_read_diagnostic_register",
        "label": "Diagnostics: Read Diagnostic Register (FC08-02)",
        "params": [],
        "run": _run_simple("diag_read_diagnostic_register"),
        "format": lambda r: f"Diagnostic register: {r!r} (meaning is vendor-specific)",
    },
    {
        "key": "diag_clear_counters",
        "label": "Diagnostics: Clear Counters (FC08-0A)",
        "params": [],
        "run": _run_simple("diag_clear_counters"),
        "format": lambda r: "Counters cleared" if r else "Failed",
    },
    {
        "key": "get_comm_event_counter",
        "label": "Get Comm Event Counter (FC11)",
        "params": [],
        "run": _run_simple("get_comm_event_counter"),
        "format": lambda r: f"Status: {'ready' if r['status'] else 'busy'}, Event count: {r['count']}",
    },
    {
        "key": "get_comm_event_log",
        "label": "Get Comm Event Log (FC12)",
        "params": [],
        "run": _run_simple("get_comm_event_log"),
        "format": lambda r: (
            f"Status: {'ready' if r['status'] else 'busy'}, Event count: {r['event_count']}, "
            f"Message count: {r['message_count']}\nEvents: {r['events']}"
        ),
    },
    {
        "key": "report_device_id",
        "label": "Report Server ID (FC17)",
        "params": [],
        "run": _run_simple("report_device_id"),
        "format": lambda r: f"Identifier: {_format_identifier(r['identifier'])}\nRun indicator: {'ON' if r['status'] else 'OFF'}",
    },
    {
        "key": "read_file_record",
        "label": "Read File Record (FC20)",
        "params": [
            _spin_param("File Number", minimum=0, maximum=0xFFFF, default=4),
            _spin_param("Record Number", minimum=0, maximum=0xFFFF, default=0),
            _spin_param("Register Count", minimum=1, maximum=120, default=1),
        ],
        "run": lambda modbus, values: modbus.read_file_record(
            [(values["File Number"], values["Record Number"], values["Register Count"])]
        ),
        "format": lambda r: "\n".join(
            f"File {rec['file_number']}, Record {rec['record_number']}: {rec['record_data'].hex(' ')}" for rec in r
        ),
    },
    {
        "key": "write_file_record",
        "label": "Write File Record (FC21)",
        "params": [
            _spin_param("File Number", minimum=0, maximum=0xFFFF, default=4),
            _spin_param("Record Number", minimum=0, maximum=0xFFFF, default=0),
            _hex_param("Data (hex)", default="0001 0002", tooltip="One or more 16-bit registers, as hex bytes."),
        ],
        "run": lambda modbus, values: modbus.write_file_record(
            [(values["File Number"], values["Record Number"], _parse_hex_bytes(values["Data (hex)"]))]
        ),
        "format": lambda r: "Write confirmed (device echoed the record back)" if r else "Failed",
    },
    {
        "key": "mask_write_register",
        "label": "Mask Write Register (FC22)",
        "params": [
            _spin_param("Address", minimum=0, maximum=65535, default=0),
            _hex_param("AND Mask (hex)", default="FFFF"),
            _hex_param("OR Mask (hex)", default="0000"),
        ],
        "run": lambda modbus, values: modbus.mask_write_register(
            values["Address"],
            int(values["AND Mask (hex)"].strip() or "0", 16),
            int(values["OR Mask (hex)"].strip() or "0", 16),
        ),
        "format": lambda r: f"Address {r['address']}: AND 0x{r['and_mask']:04X}, OR 0x{r['or_mask']:04X}",
    },
    {
        "key": "read_fifo_queue",
        "label": "Read FIFO Queue (FC24)",
        "params": [_spin_param("Address", minimum=0, maximum=65535, default=0)],
        "run": _run_simple("read_fifo_queue", "Address"),
        "format": lambda r: f"{len(r)} value(s): {r}",
    },
    {
        "key": "read_device_information",
        "label": "Read Device Information (FC43)",
        "params": [
            _combo_param("Read Code", READ_CODE_OPTIONS),
            _spin_param("Object Id", minimum=0, maximum=255, default=0),
        ],
        "run": lambda modbus, values: modbus.read_device_information(values["Read Code"], values["Object Id"]),
        "format": lambda r: (
            "\n".join(f"  Object 0x{oid:02X}: {_format_identifier(data)}" for oid, data in sorted(r["information"].items()))
            + (f"\nMore objects follow (next object id 0x{r['next_object_id']:02X})" if r["more_follows"] else "")
        ) or "(no objects returned)",
    },
]


class DiagnosticFunctionsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Modbus Diagnostic Functions")
        self.setMinimumWidth(520)
        self._param_widgets = {}

        layout = QVBoxLayout(self)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel("Function:"))
        self.function_combo = QComboBox()
        self.function_combo.setStyleSheet(parent._get_input_style())
        for spec in FUNCTIONS:
            self.function_combo.addItem(spec["label"])
        self.function_combo.currentIndexChanged.connect(self._rebuild_params)
        picker_row.addWidget(self.function_combo, 1)
        layout.addLayout(picker_row)

        self.param_container = QWidget()
        self.param_form = QFormLayout(self.param_container)
        layout.addWidget(self.param_container)

        run_row = QHBoxLayout()
        run_row.addStretch()
        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet(parent._get_button_style())
        self.run_btn.clicked.connect(self._run_selected)
        run_row.addWidget(self.run_btn)
        layout.addLayout(run_row)

        layout.addWidget(QLabel("Result:"))
        self.result_output = QTextEdit()
        self.result_output.setReadOnly(True)
        self.result_output.setMinimumHeight(140)
        self.result_output.setStyleSheet(parent._get_input_style())
        layout.addWidget(self.result_output)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(parent._get_button_style())
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._rebuild_params()

    def _rebuild_params(self, _index=None):
        while self.param_form.rowCount():
            self.param_form.removeRow(0)
        self._param_widgets = {}

        spec = FUNCTIONS[self.function_combo.currentIndex()]
        for param in spec["params"]:
            widget = self._build_param_widget(param)
            self._param_widgets[param["name"]] = widget
            self.param_form.addRow(param["name"] + ":", widget)

        if not spec["params"]:
            self.param_form.addRow(QLabel("(no parameters)"))

    def _build_param_widget(self, param):
        if param["kind"] == "spin":
            widget = QSpinBox()
            widget.setRange(param["minimum"], param["maximum"])
            widget.setValue(param["default"])
            widget.setStyleSheet(self.parent_window._get_input_style())
        elif param["kind"] == "hex":
            widget = QLineEdit(param["default"])
            widget.setStyleSheet(self.parent_window._get_input_style())
        elif param["kind"] == "check":
            widget = QCheckBox()
            widget.setChecked(param["default"])
        elif param["kind"] == "combo":
            widget = QComboBox()
            widget.setStyleSheet(self.parent_window._get_input_style())
            for label, _value in param["options"]:
                widget.addItem(label)
        else:
            raise ValueError(f"unknown param kind: {param['kind']}")
        if param.get("tooltip"):
            widget.setToolTip(param["tooltip"])
        return widget

    def _param_values(self, spec):
        values = {}
        for param in spec["params"]:
            widget = self._param_widgets[param["name"]]
            if param["kind"] == "spin":
                values[param["name"]] = widget.value()
            elif param["kind"] == "hex":
                values[param["name"]] = widget.text()
            elif param["kind"] == "check":
                values[param["name"]] = widget.isChecked()
            elif param["kind"] == "combo":
                values[param["name"]] = param["options"][widget.currentIndex()][1]
        return values

    def _run_selected(self):
        if not self.parent_window._check_connection():
            return
        spec = FUNCTIONS[self.function_combo.currentIndex()]
        try:
            values = self._param_values(spec)
            result = spec["run"](self.parent_window.modbus, values)
        except ValueError as e:
            self.result_output.setPlainText(f"Invalid parameter: {e}")
            return
        except Exception as e:
            self.result_output.setPlainText(f"Error: {e}")
            self.parent_window._log(f"{spec['label']} failed: {e}")
            return

        if result is None or result is False:
            error_text = self.parent_window.modbus.last_error or "Failed (no further detail from the device)"
            self.result_output.setPlainText(f"Failed: {error_text}")
            self.parent_window._log(f"{spec['label']} failed: {error_text}")
            return

        try:
            formatted = spec["format"](result)
        except Exception as e:
            formatted = f"(received a result, but couldn't format it: {e})\nRaw: {result!r}"
        self.result_output.setPlainText(formatted)
        self.parent_window._log(f"{spec['label']} succeeded")
