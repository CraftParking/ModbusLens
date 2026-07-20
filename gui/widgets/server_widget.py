import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QAbstractItemView, QSizePolicy
)

from pymodbus.datastore import ModbusSimulatorContext, ModbusServerContext
from pymodbus.server import StartTcpServer, ServerStop

from widgets.status_indicator import StatusIndicator

SPACE_SIZE = 1000  # cells per data space (coils/discrete/input/holding)

# (label, Modbus function code used only to look up this space's offset)
SPACES = [
    ("Coils", 1),
    ("Discrete Inputs", 2),
    ("Holding Registers", 3),
    ("Input Registers", 4),
]
BIT_SPACES = (1, 2)


class ServerWidget(QWidget):
    """Modbus TCP server/slave simulator: host a local device other masters can poll."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.sim_context = None
        self.server_thread = None
        self.running = False
        self._updating_table = False

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_view)

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

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Listen Address:"))
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
        self.unit_input.setRange(0, 247)
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
        layout.addLayout(toolbar)

        view_row = QHBoxLayout()
        view_row.addWidget(QLabel("Data Space:"))
        self.space_combo = QComboBox()
        self.space_combo.addItems([label for label, _ in SPACES])
        self.space_combo.setStyleSheet(self._input_style())
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
        layout.addLayout(view_row)

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

    def _start_server(self):
        host = self.host_input.text().strip() or "0.0.0.0"
        port = self.port_input.value()

        try:
            self.sim_context = ModbusSimulatorContext(self._build_config(), None)
            server_context = ModbusServerContext(devices=self.sim_context, single=True)
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
        self.host_input.setEnabled(False)
        self.port_input.setEnabled(False)
        self.unit_input.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_indicator.set_status("connected")
        self.status_label.setText(f"Listening on {host}:{port} (unit {self.unit_input.value()})")
        self._set_view_controls_enabled(True)
        self._load_view()
        self.refresh_timer.start(500)

    def _stop_server(self):
        try:
            ServerStop()
        except Exception:
            pass  # already stopped or never fully started -- nothing more to clean up

        self.refresh_timer.stop()
        self.running = False
        self.sim_context = None
        self.server_thread = None
        self.host_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self.unit_input.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
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

                if is_bit_space:
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

        if fc in BIT_SPACES:
            self._write_bit(offset, addr, text.lower() in ("1", "true", "on"))
            return

        idx = offset + addr
        if not (0 <= idx < len(self.sim_context.registers)):
            return
        try:
            value = int(text) & 0xFFFF
        except ValueError:
            return
        self.sim_context.registers[idx].value = value
