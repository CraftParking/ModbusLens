import asyncio
import threading
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy, QGroupBox, QRadioButton,
    QButtonGroup,
)

from pymodbus.datastore import ModbusSimulatorContext, ModbusServerContext
from pymodbus.server import StartTcpServer, ServerStop
from pymodbus.constants import ExcCodes

from widgets.status_indicator import StatusIndicator
from theme import apply_dropdown_delegate
from core.modbus_client import ModbusClient

SPACE_SIZE = 1000  # cells per data space (coils/discrete/input/holding)

# (label, Modbus function code used only to look up this space's offset)
SPACES = [
    ("Coils", 1),
    ("Discrete Inputs", 2),
    ("Holding Registers", 3),
    ("Input Registers", 4),
]
BIT_SPACES = (1, 2)

# Maps script-language type names (see script_widget.TYPE_ALIASES) to the function
# codes used to look up each space's offset in the simulator context.
_TYPE_TO_FC = {"Coil": 1, "Discrete Input": 2, "Holding Register": 3, "Input Register": 4}

# pymodbus's ServerStop() targets a single process-wide pointer to "the" running server
# (ModbusBaseServer.active_server), so only one ServerWidget -- across every open window --
# can actually own a stoppable server at a time. Tracked here, not per-instance.
_active_server_widget = None

# Function codes Gateway Mode actually relays. 1/2/3/4 are the plain reads; 5/6 are also
# routed through the read path below because pymodbus's own WriteSingleCoil/Register
# handling asks the context to "read back" the address immediately after a successful
# write, to build the echo response the spec requires -- rather than caching the just-
# written value (which could go stale if a concurrent request raced it), this re-reads
# the real device, which also doubles as confirmation the write actually stuck.
_GATEWAY_READ_FUNC_CODES = {1, 2, 3, 4, 5, 6}
_GATEWAY_WRITE_FUNC_CODES = {5, 6, 15, 16}

_GATEWAY_FUNC_CODE_LABELS = {
    1: "Read Coils", 2: "Read Discrete Inputs", 3: "Read Holding Registers",
    4: "Read Input Registers", 5: "Write Single Coil", 6: "Write Single Register",
    15: "Write Multiple Coils", 16: "Write Multiple Registers",
}


class GatewayRelayContext(ModbusSimulatorContext):
    """Stands in for the local in-memory datastore ModbusSimulatorContext normally
    keeps, relaying every request to a real downstream ModbusClient (a serial RTU/ASCII
    connection to an actual device) instead -- turning the TCP server side of Server Mode
    into a transparent TCP-to-serial gateway. See ServerWidget's Gateway mode.

    Only async_OLD_getValues/async_OLD_setValues are overridden -- those are the two
    methods ModbusServerContext.async_getValues/async_setValues actually call (see
    pymodbus.datastore.context), so the registers/fc_offset machinery the base class
    builds from `config` is never touched; the config passed to super().__init__() below
    is just enough to satisfy its constructor."""

    # One cell per space (co/di/ir/hr), laid out the same non-overlapping way
    # ServerWidget._build_config() lays out its real 1000-cell-per-space version --
    # each space needs its own address slice of the shared `registers` array, even
    # though nothing here ever actually reads or writes through it.
    _MINIMAL_CONFIG = {
        "setup": {
            "co size": 1, "di size": 1, "ir size": 1, "hr size": 1,
            "shared blocks": False, "type exception": True,
            "defaults": {
                "value": {"bits": 0, "uint16": 0, "uint32": 0, "float32": 0.0, "string": " "},
                "action": {"bits": None, "uint16": None, "uint32": None, "float32": None, "string": None},
            },
        },
        "invalid": [], "write": [[0, 0], [3, 3]],
        "bits": [{"addr": [0, 0], "value": 0}, {"addr": [1, 1], "value": 0}],
        "uint16": [{"addr": [2, 2], "value": 0}, {"addr": [3, 3], "value": 0}],
        "uint32": [], "float32": [], "string": [], "repeat": [],
    }

    def __init__(self, downstream, log_callback=None):
        super().__init__(self._MINIMAL_CONFIG, None)
        self.downstream = downstream
        self.log_callback = log_callback
        # A real serial bus only has one transaction in flight at a time regardless of
        # how many TCP clients are connected upstream -- this serializes their requests
        # onto it rather than letting them race the same port.
        self._bus_lock = threading.Lock()

    async def async_OLD_getValues(self, func_code, address, count=1):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._relay_read, func_code, address, count)

    async def async_OLD_setValues(self, func_code, address, values):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._relay_write, func_code, address, values)

    def _relay_read(self, func_code, address, count):
        with self._bus_lock:
            if func_code in (1, 5):
                result = self.downstream.read_coils(address, count)
            elif func_code == 2:
                result = self.downstream.read_discrete_inputs(address, count)
            elif func_code in (3, 6):
                result = self.downstream.read_registers(address, count)
            elif func_code == 4:
                result = self.downstream.read_input_registers(address, count)
            else:
                self._log("read", func_code, address, count, None, ExcCodes.ILLEGAL_FUNCTION)
                return ExcCodes.ILLEGAL_FUNCTION

            if result is None:
                exc = self._map_error()
                self._log("read", func_code, address, count, None, exc)
                return exc
            self._log("read", func_code, address, count, result, None)
            return result

    def _relay_write(self, func_code, address, values):
        with self._bus_lock:
            if func_code == 5:
                ok = self.downstream.write_coil(address, bool(values[0]))
            elif func_code == 6:
                ok = self.downstream.write_register(address, int(values[0]))
            elif func_code == 15:
                ok = self.downstream.write_coils(address, [bool(v) for v in values])
            elif func_code == 16:
                ok = self.downstream.write_registers(address, [int(v) for v in values])
            else:
                self._log("write", func_code, address, values, None, ExcCodes.ILLEGAL_FUNCTION)
                return ExcCodes.ILLEGAL_FUNCTION

            if not ok:
                exc = self._map_error()
                self._log("write", func_code, address, values, None, exc)
                return exc
            self._log("write", func_code, address, values, values, None)
            return None

    def _map_error(self):
        """Translate the downstream ModbusClient's last failure into the ExcCodes value
        sent back over TCP -- a real device's own exception code (Illegal Data Address,
        etc.) passes straight through, while a communications failure on the serial side
        becomes one of the two standard Modbus gateway exception codes, matching what a
        real hardware TCP-to-RTU gateway returns in the same situation."""
        exception_code = self.downstream.last_exception_code
        if exception_code is not None:
            try:
                return ExcCodes(exception_code)
            except ValueError:
                return ExcCodes.DEVICE_FAILURE
        category = self.downstream.last_error_category
        if category == "connection":
            return ExcCodes.GATEWAY_PATH_UNAVIABLE
        if category == "timeout":
            return ExcCodes.GATEWAY_NO_RESPONSE
        if category == "rejected":
            return ExcCodes.ILLEGAL_VALUE
        return ExcCodes.DEVICE_FAILURE

    def _log(self, direction, func_code, address, request_data, response_data, exc):
        if self.log_callback:
            self.log_callback({
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "direction": direction,
                "func_code": func_code,
                "address": address,
                "request_data": request_data,
                "response_data": response_data,
                "exc": exc,
            })


class ServerWidget(QWidget):
    """Modbus TCP server/slave simulator: host a local device other masters can poll.

    Also doubles as a TCP-to-serial Gateway (see Mode in Server Configuration): instead
    of answering from a local simulated datastore, it relays real requests to a real
    downstream serial (RTU/ASCII) device and returns its real response. Like every other
    feature here, this only runs while ModbusLens itself is open -- it's an interactive
    bridge for testing/commissioning, not an unattended 24/7 production gateway."""

    GATEWAY_LOG_LIMIT = 500

    # Mirrors ConnectionSettingsDialog's serial constants (main_window.py) so Gateway
    # Mode's downstream serial config looks and behaves the same as everywhere else.
    BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
    PARITIES = [("None", "N"), ("Even", "E"), ("Odd", "O")]
    STOP_BITS = [1, 2]
    BYTE_SIZES = [7, 8]

    # A Qt signal, not a direct call: GatewayRelayContext logs from inside
    # loop.run_in_executor()'s worker thread, never the Qt/GUI thread. Emitting a signal
    # is thread-safe (Qt auto-queues delivery onto the receiver's own thread); touching
    # self.table directly from that worker thread would not be.
    gateway_log_entry = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.sim_context = None
        self.server_thread = None
        self.running = False
        self.gateway_mode = False
        self.downstream_client = None
        self._updating_table = False

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_view)
        self.gateway_log_entry.connect(self._append_gateway_log_row)

        self._setup_ui()

    def _button_style(self):
        if self.parent_window is not None and hasattr(self.parent_window, "_get_button_style"):
            return self.parent_window._get_button_style()
        return ""

    def _input_style(self):
        if self.parent_window is not None and hasattr(self.parent_window, "_get_input_style"):
            return self.parent_window._get_input_style()
        return ""

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        control_group = QGroupBox("Server Configuration")
        control_layout = QVBoxLayout(control_group)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self.simulate_radio = QRadioButton("Simulate")
        self.simulate_radio.setToolTip(
            "Answer every request from a local, manually-editable datastore -- for testing "
            "a master against a fake device with no real hardware involved."
        )
        self.gateway_radio = QRadioButton("Gateway")
        self.gateway_radio.setToolTip(
            "Relay real requests to a real downstream serial (RTU/ASCII) device and return "
            "its actual response -- turns a serial-only device into one reachable over TCP. "
            "Runs only while ModbusLens stays open, like every other feature here."
        )
        self.simulate_radio.setChecked(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.simulate_radio)
        self._mode_group.addButton(self.gateway_radio)
        self.simulate_radio.toggled.connect(self._on_mode_toggled)
        mode_row.addWidget(self.simulate_radio)
        mode_row.addWidget(self.gateway_radio)
        mode_row.addStretch()
        control_layout.addLayout(mode_row)

        toolbar = QHBoxLayout()
        control_layout.addLayout(toolbar)
        toolbar.addWidget(QLabel("Server Address:"))
        self.host_input = QLineEdit("0.0.0.0")
        self.host_input.setStyleSheet(self._input_style())
        self.host_input.setMaximumWidth(120)
        toolbar.addWidget(self.host_input)

        toolbar.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(5020)
        self.port_input.setStyleSheet(self._input_style())
        toolbar.addWidget(self.port_input)

        toolbar.addWidget(QLabel("Unit ID:"))
        self.unit_input = QSpinBox()
        self.unit_input.setRange(0, 255)
        self.unit_input.setValue(1)
        self.unit_input.setStyleSheet(self._input_style())
        toolbar.addWidget(self.unit_input)

        self.start_btn = QPushButton("Start Server")
        self.start_btn.setStyleSheet(self._button_style())
        self.start_btn.clicked.connect(self._start_server)
        toolbar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Server")
        self.stop_btn.setStyleSheet(self._button_style())
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_server)
        toolbar.addWidget(self.stop_btn)

        toolbar.addSpacing(15)
        self.status_indicator = StatusIndicator()
        toolbar.addWidget(self.status_indicator)
        self.status_label = QLabel("Stopped")
        toolbar.addWidget(self.status_label)

        toolbar.addStretch()
        layout.addWidget(control_group)

        self.gateway_group = QGroupBox("Downstream Serial Device (Gateway)")
        gateway_grid = QHBoxLayout(self.gateway_group)

        gateway_grid.addWidget(QLabel("COM Port:"))
        self.gw_serial_port_combo = QComboBox()
        self.gw_serial_port_combo.setEditable(True)
        self.gw_serial_port_combo.setStyleSheet(self._input_style())
        for port_name in self._detect_serial_ports():
            self.gw_serial_port_combo.addItem(port_name)
        gateway_grid.addWidget(self.gw_serial_port_combo)

        gateway_grid.addWidget(QLabel("Baud:"))
        self.gw_baud_combo = QComboBox()
        self.gw_baud_combo.setEditable(True)
        self.gw_baud_combo.setStyleSheet(self._input_style())
        for rate in self.BAUD_RATES:
            self.gw_baud_combo.addItem(str(rate))
        self.gw_baud_combo.setCurrentText("19200")
        gateway_grid.addWidget(self.gw_baud_combo)

        gateway_grid.addWidget(QLabel("Parity:"))
        self.gw_parity_combo = QComboBox()
        self.gw_parity_combo.setStyleSheet(self._input_style())
        for label, code in self.PARITIES:
            self.gw_parity_combo.addItem(label, code)
        gateway_grid.addWidget(self.gw_parity_combo)

        gateway_grid.addWidget(QLabel("Stop Bits:"))
        self.gw_stopbits_combo = QComboBox()
        self.gw_stopbits_combo.setStyleSheet(self._input_style())
        for bits in self.STOP_BITS:
            self.gw_stopbits_combo.addItem(str(bits), bits)
        gateway_grid.addWidget(self.gw_stopbits_combo)

        gateway_grid.addWidget(QLabel("Byte Size:"))
        self.gw_bytesize_combo = QComboBox()
        self.gw_bytesize_combo.setStyleSheet(self._input_style())
        for size in self.BYTE_SIZES:
            self.gw_bytesize_combo.addItem(str(size), size)
        self.gw_bytesize_combo.setCurrentIndex(1)
        gateway_grid.addWidget(self.gw_bytesize_combo)

        gateway_grid.addWidget(QLabel("Framing:"))
        self.gw_framer_combo = QComboBox()
        self.gw_framer_combo.setStyleSheet(self._input_style())
        self.gw_framer_combo.addItem("RTU (binary)", "rtu")
        self.gw_framer_combo.addItem("ASCII", "ascii")
        gateway_grid.addWidget(self.gw_framer_combo)

        for combo in (self.gw_serial_port_combo, self.gw_baud_combo, self.gw_parity_combo,
                      self.gw_stopbits_combo, self.gw_bytesize_combo, self.gw_framer_combo):
            apply_dropdown_delegate(combo, getattr(self.parent_window, "_theme_mode", "light"))

        gateway_grid.addStretch()
        layout.addWidget(self.gateway_group)
        self.gateway_group.setVisible(False)

        self.view_group = QGroupBox("Data Space View")
        view_row = QHBoxLayout(self.view_group)
        view_row.addWidget(QLabel("Data Space:"))
        self.space_combo = QComboBox()
        self.space_combo.addItems([label for label, _ in SPACES])
        self.space_combo.setStyleSheet(self._input_style())
        apply_dropdown_delegate(self.space_combo, getattr(self.parent_window, "_theme_mode", "light"))
        self.space_combo.currentIndexChanged.connect(self._load_view)
        view_row.addWidget(self.space_combo)

        view_row.addWidget(QLabel("Start Address:"))
        self.start_address_input = QSpinBox()
        self.start_address_input.setRange(0, SPACE_SIZE - 1)
        self.start_address_input.setValue(0)
        self.start_address_input.setStyleSheet(self._input_style())
        view_row.addWidget(self.start_address_input)

        view_row.addWidget(QLabel("Count:"))
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 200)
        self.count_input.setValue(20)
        self.count_input.setStyleSheet(self._input_style())
        view_row.addWidget(self.count_input)

        self.load_view_btn = QPushButton("Load")
        self.load_view_btn.setStyleSheet(self._button_style())
        self.load_view_btn.clicked.connect(self._load_view)
        view_row.addWidget(self.load_view_btn)

        view_row.addStretch()
        layout.addWidget(self.view_group)

        self.gateway_activity_group = QGroupBox("Gateway Activity")
        activity_row = QHBoxLayout(self.gateway_activity_group)
        activity_row.addWidget(QLabel("Every request relayed to the downstream device, most recent last."))
        activity_row.addStretch()
        self.clear_gateway_log_btn = QPushButton("Clear Log")
        self.clear_gateway_log_btn.setStyleSheet(self._button_style())
        self.clear_gateway_log_btn.clicked.connect(self._clear_gateway_log)
        activity_row.addWidget(self.clear_gateway_log_btn)
        layout.addWidget(self.gateway_activity_group)
        self.gateway_activity_group.setVisible(False)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Address", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.itemChanged.connect(self._on_cell_edited)
        layout.addWidget(self.table, 1)

        self._set_view_controls_enabled(False)

    def _set_view_controls_enabled(self, enabled):
        self.space_combo.setEnabled(enabled)
        self.start_address_input.setEnabled(enabled)
        self.count_input.setEnabled(enabled)
        self.load_view_btn.setEnabled(enabled)
        self.table.setEnabled(enabled)

    # --- Gateway mode ---

    def _detect_serial_ports(self):
        try:
            from serial.tools import list_ports
            return [p.device for p in list_ports.comports()]
        except Exception:
            return []

    def _on_mode_toggled(self, simulate_checked):
        if self.running:
            return  # radios are disabled while running anyway; ignore a stray signal
        self.gateway_mode = not simulate_checked
        self.gateway_group.setVisible(self.gateway_mode)
        self.view_group.setVisible(not self.gateway_mode)
        self.gateway_activity_group.setVisible(self.gateway_mode)
        self._configure_table_for_mode()

    def _configure_table_for_mode(self):
        self._updating_table = True
        try:
            self.table.setRowCount(0)
            if self.gateway_mode:
                self.table.setColumnCount(5)
                self.table.setHorizontalHeaderLabels(["Time", "Direction", "Function", "Address", "Result"])
                self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            else:
                self.table.setColumnCount(2)
                self.table.setHorizontalHeaderLabels(["Address", "Value"])
                self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        finally:
            self._updating_table = False

    def _append_gateway_log_row(self, entry):
        """Slot for gateway_log_entry -- always runs on the GUI thread regardless of which
        worker thread emitted it, so touching self.table here is safe."""
        self._updating_table = True
        try:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(entry["time"]))
            self.table.setItem(row, 1, QTableWidgetItem(entry["direction"].capitalize()))
            func_label = _GATEWAY_FUNC_CODE_LABELS.get(entry["func_code"], f"FC {entry['func_code']}")
            self.table.setItem(row, 2, QTableWidgetItem(func_label))
            self.table.setItem(row, 3, QTableWidgetItem(str(entry["address"])))

            exc = entry["exc"]
            result_item = QTableWidgetItem(
                f"Exception: {exc.name}" if exc is not None else str(entry["response_data"])
            )
            if exc is not None:
                result_item.setForeground(QColor("#C62828"))
            self.table.setItem(row, 4, result_item)

            while self.table.rowCount() > self.GATEWAY_LOG_LIMIT:
                self.table.removeRow(0)
            self.table.scrollToBottom()
        finally:
            self._updating_table = False

    def _clear_gateway_log(self):
        self._updating_table = True
        try:
            self.table.setRowCount(0)
        finally:
            self._updating_table = False

    # --- Server lifecycle ---

    def _build_config(self):
        size = SPACE_SIZE
        co_end, di_end, ir_end, hr_end = size, size, size, size
        di_start = co_end
        ir_start = co_end + di_end
        hr_start = co_end + di_end + ir_end
        return {
            "setup": {
                "co size": co_end, "di size": di_end, "ir size": ir_end, "hr size": hr_end,
                "shared blocks": False, "type exception": True,
                "defaults": {
                    "value": {"bits": 0, "uint16": 0, "uint32": 0, "float32": 0.0, "string": " "},
                    "action": {"bits": None, "uint16": None, "uint32": None, "float32": None, "string": None},
                },
            },
            "invalid": [],
            "write": [[0, co_end - 1], [hr_start, hr_start + hr_end - 1]],
            "bits": [
                {"addr": [0, co_end - 1], "value": 0},
                {"addr": [di_start, di_start + di_end - 1], "value": 0},
            ],
            "uint16": [
                {"addr": [ir_start, ir_start + ir_end - 1], "value": 0},
                {"addr": [hr_start, hr_start + hr_end - 1], "value": 0},
            ],
            "uint32": [], "float32": [], "string": [], "repeat": [],
        }

    def _set_gateway_config_enabled(self, enabled):
        for combo in (self.gw_serial_port_combo, self.gw_baud_combo, self.gw_parity_combo,
                      self.gw_stopbits_combo, self.gw_bytesize_combo, self.gw_framer_combo):
            combo.setEnabled(enabled)

    def _build_gateway_context(self):
        """Open the downstream serial connection and wrap it in a GatewayRelayContext.
        Returns the ModbusServerContext to hand to StartTcpServer, or None -- having
        already shown the user why -- if the downstream connection couldn't be opened."""
        serial_port = self.gw_serial_port_combo.currentText().strip()
        if not serial_port:
            QMessageBox.warning(self, "Gateway Setup Failed", "Choose the downstream serial device's COM port first.")
            return None
        try:
            baudrate = int(self.gw_baud_combo.currentText())
        except ValueError:
            QMessageBox.warning(self, "Gateway Setup Failed", "Baud rate must be a number.")
            return None

        # Unit ID is shared with the TCP side (Server Configuration above) -- a
        # transparent passthrough, not a remap, so the same physical/logical device the
        # rest of the app already understands as "Unit N" stays Unit N on both sides.
        self.downstream_client = ModbusClient(
            mode="serial", unit_id=self.unit_input.value(), serial_port=serial_port, baudrate=baudrate,
            parity=self.gw_parity_combo.currentData(), stopbits=self.gw_stopbits_combo.currentData(),
            bytesize=self.gw_bytesize_combo.currentData(), serial_framer=self.gw_framer_combo.currentData(),
        )
        if not self.downstream_client.connect():
            QMessageBox.warning(
                self, "Gateway Setup Failed",
                f"Could not open the downstream serial connection on {serial_port}: "
                f"{self.downstream_client.last_error}",
            )
            self.downstream_client = None
            return None

        gateway_context = GatewayRelayContext(self.downstream_client, log_callback=self.gateway_log_entry.emit)
        return ModbusServerContext(devices={self.unit_input.value(): gateway_context})

    def _start_server(self):
        global _active_server_widget
        if _active_server_widget is not None and _active_server_widget is not self:
            QMessageBox.warning(
                self,
                "Server Already Running",
                "Only one Server tab can be running at a time, across all open windows -- "
                "in either Simulate or Gateway mode. ModbusLens uses pymodbus's StartTcpServer "
                "for both: it spins up its own asyncio event loop for the listener and "
                "datastore, and isn't designed to have more than one instance active in the "
                "same process at once. Stop the other one first.",
            )
            return

        host = self.host_input.text().strip() or "0.0.0.0"
        port = self.port_input.value()

        if self.gateway_mode:
            server_context = self._build_gateway_context()
            if server_context is None:
                return
        else:
            try:
                self.sim_context = ModbusSimulatorContext(self._build_config(), None)
                # pymodbus's single= is deprecated and ignored -- passing devices as a bare
                # context (not a dict) makes it fall back to device id 0 for *any* request,
                # regardless of Unit ID configured above, silently answering every unit id
                # the same way. Keying it under the configured unit id is what actually
                # makes the simulator only answer as that unit.
                server_context = ModbusServerContext(devices={self.unit_input.value(): self.sim_context})
            except Exception as e:
                QMessageBox.warning(self, "Server Setup Failed", f"Could not build the device datastore: {e}")
                self.sim_context = None
                return

        error_holder = {}

        def run():
            try:
                StartTcpServer(context=server_context, address=(host, port))
            except Exception as e:
                error_holder["error"] = e

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        time.sleep(0.3)  # give a bad host/port a moment to fail fast
        if "error" in error_holder or not self.server_thread.is_alive():
            detail = error_holder.get("error", "the listener exited immediately")
            QMessageBox.warning(self, "Server Failed", f"Could not start server on {host}:{port}: {detail}")
            self.sim_context = None
            self.server_thread = None
            return

        self.running = True
        _active_server_widget = self
        self.host_input.setEnabled(False)
        self.port_input.setEnabled(False)
        self.unit_input.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.simulate_radio.setEnabled(False)
        self.gateway_radio.setEnabled(False)
        self.status_indicator.set_status("connected")

        if self.gateway_mode:
            self._set_gateway_config_enabled(False)
            self._configure_table_for_mode()
            self.status_label.setText(
                f"Gateway: {host}:{port} (unit {self.unit_input.value()}) <-> "
                f"{self.downstream_client.target_description()}"
            )
        else:
            self.status_label.setText(f"Listening on {host}:{port} (unit {self.unit_input.value()})")
            self._set_view_controls_enabled(True)
            self._load_view()
            self.refresh_timer.start(500)

    def _stop_server(self):
        global _active_server_widget
        try:
            if _active_server_widget is self:
                ServerStop()
        except Exception:
            pass  # already stopped or never fully started -- nothing more to clean up
        if _active_server_widget is self:
            _active_server_widget = None

        if self.server_thread is not None:
            # ServerStop() asks the listener's event loop to exit, but doesn't wait for
            # it -- join so the OS has actually released the port before this returns,
            # otherwise an immediate Start on the same port can spuriously fail with
            # "address already in use" even though nothing is really wrong.
            self.server_thread.join(timeout=2.0)

        if self.downstream_client is not None:
            self.downstream_client.disconnect()
            self.downstream_client = None

        self.refresh_timer.stop()
        self.running = False
        self.sim_context = None
        self.server_thread = None
        self.host_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self.unit_input.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.simulate_radio.setEnabled(True)
        self.gateway_radio.setEnabled(True)
        self._set_gateway_config_enabled(True)
        self.status_indicator.set_status("disconnected")
        self.status_label.setText("Stopped")
        self._set_view_controls_enabled(False)
        self.table.setRowCount(0)

    # --- Register view ---

    def _current_space(self):
        return SPACES[self.space_combo.currentIndex()]

    def _cell_index_for_bit(self, offset, addr):
        """pymodbus packs 16 coils/discrete-inputs per storage word."""
        return offset + (addr // 16), addr % 16

    def _read_bit(self, offset, addr):
        word_idx, bit_pos = self._cell_index_for_bit(offset, addr)
        if not (0 <= word_idx < len(self.sim_context.registers)):
            return None
        return bool(self.sim_context.registers[word_idx].value & (1 << bit_pos))

    def _write_bit(self, offset, addr, on):
        word_idx, bit_pos = self._cell_index_for_bit(offset, addr)
        if not (0 <= word_idx < len(self.sim_context.registers)):
            return
        cell = self.sim_context.registers[word_idx]
        if on:
            cell.value |= (1 << bit_pos)
        else:
            cell.value &= ~(1 << bit_pos)

    # --- Direct datastore access (used by a "Server Script" in the Script tab) ---

    def read_value(self, data_type, address):
        """Read one value straight out of the local datastore. Returns None if the
        server isn't running or the address is out of range."""
        if not self.running or self.sim_context is None:
            return None
        if not (0 <= address < SPACE_SIZE):
            return None
        fc = _TYPE_TO_FC[data_type]
        offset = self.sim_context.fc_offset[fc]
        if fc in BIT_SPACES:
            bit = self._read_bit(offset, address)
            return None if bit is None else int(bit)
        idx = offset + address
        if not (0 <= idx < len(self.sim_context.registers)):
            return None
        return self.sim_context.registers[idx].value

    def write_value(self, data_type, address, value):
        """Write one value straight into the local datastore. All four data spaces are
        writable here (unlike a real client, a server script is simulating the device
        itself, so setting an Input Register/Discrete Input directly is the point).
        Returns False if the server isn't running or the address is out of range."""
        if not self.running or self.sim_context is None:
            return False
        if not (0 <= address < SPACE_SIZE):
            return False
        fc = _TYPE_TO_FC[data_type]
        offset = self.sim_context.fc_offset[fc]
        if fc in BIT_SPACES:
            self._write_bit(offset, address, bool(value))
            return True
        idx = offset + address
        if not (0 <= idx < len(self.sim_context.registers)):
            return False
        self.sim_context.registers[idx].value = int(value) & 0xFFFF
        return True

    def _load_view(self):
        if not self.running or self.sim_context is None:
            return

        _, fc = self._current_space()
        offset = self.sim_context.fc_offset[fc]
        start = self.start_address_input.value()
        count = self.count_input.value()
        is_bit_space = fc in BIT_SPACES

        self._updating_table = True
        try:
            self.table.setRowCount(count)
            for i in range(count):
                addr = start + i

                addr_item = QTableWidgetItem(str(addr))
                addr_item.setFlags(addr_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, 0, addr_item)

                # Start + Count can run past this space's own SPACE_SIZE cells (they're
                # set independently in the UI); idx would still land inside the shared
                # registers array at that point -- just inside the *next* space's slice
                # of it -- so bound against SPACE_SIZE here, not just the array length,
                # to avoid silently showing/aliasing another space's data.
                if addr >= SPACE_SIZE:
                    value_text = ""
                elif is_bit_space:
                    bit = self._read_bit(offset, addr)
                    value_text = "" if bit is None else ("1" if bit else "0")
                else:
                    idx = offset + addr
                    value_text = str(self.sim_context.registers[idx].value) if 0 <= idx < len(self.sim_context.registers) else ""
                self.table.setItem(i, 1, QTableWidgetItem(value_text))
        finally:
            self._updating_table = False

    def _refresh_view(self):
        if not self.running or self.sim_context is None:
            return
        if self.table.state() == QAbstractItemView.EditingState:
            return  # don't clobber a cell the user is actively editing
        self._load_view()

    def _on_cell_edited(self, item):
        if self._updating_table or item.column() != 1 or not self.running:
            return

        _, fc = self._current_space()
        offset = self.sim_context.fc_offset[fc]
        addr = self.start_address_input.value() + item.row()
        text = item.text().strip()

        if addr >= SPACE_SIZE:
            # Past this space's own size -- reject rather than write into the next
            # space's slice of the shared registers array. Restore on the next tick.
            return

        if fc in BIT_SPACES:
            self._write_bit(offset, addr, text.lower() in ("1", "true", "on"))
            return

        idx = offset + addr
        if not (0 <= idx < len(self.sim_context.registers)):
            return
        try:
            value = int(text) & 0xFFFF
        except ValueError:
            # Reject and restore the last real value rather than silently leaving the
            # invalid text sitting in the cell until the next refresh tick overwrites it.
            self._updating_table = True
            try:
                item.setText(str(self.sim_context.registers[idx].value))
            finally:
                self._updating_table = False
            return
        self.sim_context.registers[idx].value = value
