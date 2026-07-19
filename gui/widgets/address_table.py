from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QHeaderView, QComboBox, QSpinBox,
    QCheckBox, QGroupBox, QTextEdit, QTableWidgetItem, QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
import time


class AddressTableWidget(QWidget):
    """ModScan-like address table for live monitoring and editing of Modbus registers/coils."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.monitoring_active = False
        self.monitoring_timer = QTimer()
        self.monitoring_timer.timeout.connect(self.update_table_data)
        self.current_data = {}
        self.range_is_one_based = True
        self._building_table = False
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Control panel: function/address controls on the left, status log on the right
        control_layout = QHBoxLayout()
        left_controls = QVBoxLayout()

        control_group = QGroupBox("Address Range Configuration")
        address_layout = QHBoxLayout(control_group)

        function_label = QLabel("Function:")
        function_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        address_layout.addWidget(function_label)
        self.function_combo = QComboBox()
        self.function_combo.addItems([
            "Read Coils (1)", "Read Discrete Inputs (2)", "Read Holding Registers (3)",
            "Read Input Registers (4)", "Write Single Coil (5)", "Write Single Register (6)",
            "Write Multiple Coils (15)", "Write Multiple Registers (16)"
        ])
        self.function_combo.currentTextChanged.connect(self.on_function_changed)
        address_layout.addWidget(self.function_combo)

        start_address_label = QLabel("Start Address:")
        start_address_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        address_layout.addWidget(start_address_label)
        self.address_input = QSpinBox()
        self.address_input.setRange(1, 65536)
        self.address_input.setValue(1)
        self.address_input.valueChanged.connect(self.on_address_range_changed)
        address_layout.addWidget(self.address_input)

        count_label = QLabel("Count:")
        count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        address_layout.addWidget(count_label)
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 2000)  # upper bound; the real per-function limit is checked in create_address_table
        self.count_input.setValue(1)
        self.count_input.valueChanged.connect(self.on_address_range_changed)
        address_layout.addWidget(self.count_input)

        self.offset_checkbox = QCheckBox("0-Based Addressing")
        self.offset_checkbox.setToolTip("When enabled, use 0-based addressing (user address 0 is sent as protocol offset 0)")
        self.offset_checkbox.stateChanged.connect(self.on_offset_checkbox_changed)
        address_layout.addWidget(self.offset_checkbox)

        self.create_btn = QPushButton("Create Table")
        self.create_btn.clicked.connect(self.create_address_table)
        address_layout.addWidget(self.create_btn)

        left_controls.addWidget(control_group)

        monitor_group = QGroupBox("Live Monitoring")
        monitor_layout = QHBoxLayout(monitor_group)

        self.monitoring_checkbox = QCheckBox("Enable Live Monitoring")
        self.monitoring_checkbox.stateChanged.connect(self.toggle_monitoring)
        self.monitoring_checkbox.setEnabled(False)  # enabled once connected
        monitor_layout.addWidget(self.monitoring_checkbox)

        monitor_layout.addWidget(QLabel("Interval (ms):"))
        self.interval_input = QSpinBox()
        self.interval_input.setRange(100, 10000)
        self.interval_input.setValue(1000)
        self.interval_input.setEnabled(False)
        monitor_layout.addWidget(self.interval_input)
        self.interval_input.valueChanged.connect(self.update_monitoring_interval)
        monitor_layout.addStretch()

        left_controls.addWidget(monitor_group)

        log_group = QGroupBox("Status Log")
        log_layout = QVBoxLayout(log_group)
        self.log_output = QTextEdit()
        self.log_output.setMinimumHeight(200)
        self.log_output.setMaximumWidth(300)
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #F8F9FA;
                color: #333333;
                border: 1px solid #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        log_layout.addWidget(self.log_output)

        control_layout.addLayout(left_controls, 3)
        control_layout.addWidget(log_group, 1)
        layout.addLayout(control_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Address", "Value"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(300)
        self.table.setMaximumHeight(400)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setAutoScroll(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.viewport().setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed | QTableWidget.AnyKeyPressed)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                color: #000000;
                gridline-color: #D0D0D0;
                border: 1px solid #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 6px;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #E0E0E0;
                border-right: 1px solid #E0E0E0;
            }
            QTableWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
        """)
        self.table.cellChanged.connect(self.on_cell_changed)
        layout.addWidget(self.table)
        layout.setStretchFactor(self.table, 1)

        # Disable everything until a connection is established
        self.function_combo.setEnabled(False)
        self.address_input.setEnabled(False)
        self.count_input.setEnabled(False)
        self.create_btn.setEnabled(False)
        self.offset_checkbox.setEnabled(False)
        self.monitoring_checkbox.setEnabled(False)
        self.interval_input.setEnabled(False)

    def on_function_changed(self, function_text):
        is_write_function = any(f in function_text for f in ["Write Single", "Write Multiple"])
        self.count_input.setEnabled(not is_write_function or "Multiple" in function_text)

        if "Write Single" in function_text:
            self.count_input.setValue(1)

        self.update_monitoring_availability()
        self.ensure_address_mode_bounds()
        if hasattr(self, 'current_count') and self.table.rowCount() > 0:
            self.log(f"Function changed to {function_text}; rebuilding address table")
            self.create_address_table()

    def is_read_function(self, function=None):
        """Return True when the selected function supports live monitoring."""
        function = function or self.function_combo.currentText()
        return "Read" in function

    def has_active_connection(self):
        """Return True when the parent window has an active Modbus connection."""
        if not self.parent_window or not getattr(self.parent_window, 'modbus', None):
            return False
        return bool(self.parent_window.modbus.is_connected())

    def update_monitoring_availability(self):
        """Enable live monitoring only for read functions on an active connection."""
        can_monitor = self.has_active_connection() and self.is_read_function()
        if not can_monitor and self.monitoring_checkbox.isChecked():
            self.monitoring_checkbox.setChecked(False)
        self.monitoring_checkbox.setEnabled(can_monitor)
        self.interval_input.setEnabled(can_monitor and self.monitoring_checkbox.isChecked())

    def get_operation_type(self, function):
        """Return the Modbus operation type for address conversion."""
        if "Coil" in function:
            return "coils"
        if "Discrete Input" in function:
            return "discrete_inputs"
        if "Input Register" in function:
            return "input_registers"
        if "Register" in function:
            return "holding_registers"
        return None

    def get_function_code(self, function=None):
        """Return the Modbus function code selected in the Address Table."""
        function = function or self.function_combo.currentText()
        try:
            return int(function.rsplit("(", 1)[1].rstrip(")"))
        except (IndexError, ValueError):
            return None

    def ensure_address_mode_bounds(self):
        """Keep the address input range unambiguous for 0-based vs 1-based mode."""
        current_value = self.address_input.value()
        minimum = 1 if self.range_is_one_based else 0
        maximum = 65536 if self.range_is_one_based else 65535
        self.address_input.setRange(minimum, maximum)
        if current_value < minimum:
            self.address_input.setValue(minimum)

    def get_user_address_for_row(self, row):
        """Return the user-facing address represented by a table row."""
        return self.current_start_address + row

    def convert_user_address_to_offset(self, user_address, function=None):
        """Convert a user-facing Address Table address to a 0-based protocol offset."""
        function = function or self.current_function
        offset = user_address - 1 if self.range_is_one_based else user_address

        if offset < 0:
            raise ValueError(f"Invalid address: {user_address} converts to negative protocol offset {offset}")
        if offset > 65535:
            raise ValueError(f"Invalid address: {user_address} converts to protocol offset {offset} above 65535")
        return offset

    def on_address_range_changed(self, *_args):
        """Keep range-level offset state valid when the start/count controls change."""
        if hasattr(self, 'current_count') and self.table.rowCount() > 0:
            self.current_start_address = self.address_input.value()
            self.current_count = self.count_input.value()
            self.refresh_address_column()

    def get_modbus_address(self, address: int, function: str) -> str:
        """Return the user-facing Modbus reference address for the selected function."""
        operation_type = self.get_operation_type(function)
        reference_bases = {
            "coils": 0,
            "discrete_inputs": 10000,
            "input_registers": 30000,
            "holding_registers": 40000,
        }
        base = reference_bases.get(operation_type, 0)
        return f"{base + address:05d}"

    def create_address_table(self):
        function = self.function_combo.currentText()
        self.ensure_address_mode_bounds()
        start_address = self.address_input.value()
        count = self.count_input.value()
        self.monitoring_checkbox.setEnabled(False)

        try:
            start_offset = self.convert_user_address_to_offset(start_address, function)
        except ValueError as e:
            self.log(f"Address error: {e}")
            return

        if start_offset + count > 65536:
            self.log("Error: Address range exceeds 65535")
            return

        if function.startswith("Read"):
            operation_type = self.get_operation_type(function)
            max_count = 125 if operation_type in ("holding_registers", "input_registers") else 2000
            if count > max_count:
                self.log(f"Error: {function} allows at most {max_count} values per request")
                return

        self._building_table = True
        self.table.setRowCount(0)
        self.current_data.clear()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Address", "Value"])
        self.table.setRowCount(count)

        is_write = "Write" in function

        for i in range(count):
            address = start_address + i
            modbus_address = self.get_modbus_address(address, function)

            address_item = QTableWidgetItem(modbus_address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            address_item.setBackground(QColor("#F0F0F0"))
            self.table.setItem(i, 0, address_item)

            if is_write and "Coil" in function:
                checkbox = QCheckBox()
                checkbox.setChecked(False)
                checkbox.setStyleSheet("QCheckBox { margin-left: 5px; }")
                self.table.setCellWidget(i, 1, checkbox)
                checkbox.stateChanged.connect(lambda state, row=i: self.on_coil_checkbox_changed(row, state))
            else:
                value_item = QTableWidgetItem("")
                if is_write:
                    value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)
                else:
                    value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, 1, value_item)

        self._building_table = False

        # Monitoring controls stay disabled here; _set_connection_controls re-enables them once connected
        self.update_monitoring_availability()

        self.current_function = function
        self.current_start_address = start_address
        self.current_count = count

        self.log(f"Created table: {function} from address {start_address}, count {count}")

    def on_offset_checkbox_changed(self, state):
        """Handle range-level offset checkbox state change."""
        self.range_is_one_based = (state != 2)  # checking "0-Based Addressing" turns 1-based off
        self.ensure_address_mode_bounds()
        self.refresh_address_column()
        self.log(f"Address range offset mode: {'1-based' if self.range_is_one_based else '0-based'}")

    def refresh_address_column(self):
        """Refresh displayed addresses after function or offset changes."""
        if not hasattr(self, 'current_start_address') or not hasattr(self, 'current_count'):
            return

        function = getattr(self, 'current_function', self.function_combo.currentText())
        for row in range(min(self.table.rowCount(), self.current_count)):
            address = self.current_start_address + row
            address_item = self.table.item(row, 0)
            if address_item:
                address_item.setText(self.get_modbus_address(address, function))

    def toggle_monitoring(self, state):
        """Toggle live monitoring on/off with interlock (read functions only)."""
        try:
            if state == 2:  # Qt.Checked
                if hasattr(self, 'current_function') and self.current_function:
                    if "Read" not in self.current_function:
                        self.log("Live monitoring is only available for read functions")
                        self.monitoring_checkbox.setChecked(False)
                        return

                # Auto-stop tag monitoring since only one live poll should run at a time
                if hasattr(self.parent_window, 'tag_start_monitoring_btn'):
                    if not self.parent_window.tag_start_monitoring_btn.isEnabled():
                        self.parent_window.tag_stop_monitoring_btn.click()
                        self.log("Auto-stopped tag monitoring")

                self.interval_input.setEnabled(True)
                self.start_monitoring()
            else:
                self.interval_input.setEnabled(False)
                self.stop_monitoring()
        except Exception as e:
            self.log(f"Error in toggle_monitoring: {e}")

    def start_monitoring(self):
        """Start live monitoring."""
        try:
            if not hasattr(self, 'current_function'):
                self.log("Error: Please create a table first")
                self.monitoring_checkbox.setChecked(False)
                return

            if not self.parent_window:
                self.log("Error: No parent window")
                self.monitoring_checkbox.setChecked(False)
                return

            if not hasattr(self.parent_window, 'modbus') or not self.parent_window.modbus:
                self.log("Error: Modbus client not initialized - please connect first")
                self.monitoring_checkbox.setChecked(False)
                return

            if not self.parent_window.modbus.is_connected():
                self.log("Error: Not connected to Modbus server - please connect first")
                self.monitoring_checkbox.setChecked(False)
                return

            self.monitoring_active = True
            interval = self.interval_input.value()
            self.monitoring_timer.start(interval)
            self.log(f"Started monitoring with {interval}ms interval")
        except Exception as e:
            self.log(f"Error in start_monitoring: {e}")

    def stop_monitoring(self):
        """Stop live monitoring."""
        self.monitoring_active = False
        self.monitoring_timer.stop()
        self.log("Stopped monitoring")

    def update_monitoring_interval(self):
        if self.monitoring_active:
            interval = self.interval_input.value()
            self.monitoring_timer.setInterval(interval)
            self.log(f"Updated monitoring interval to {interval}ms")

    def update_table_data(self):
        """Poll the device for the current address range and refresh the table."""
        if not self.monitoring_active:
            return

        if not self.parent_window or not hasattr(self.parent_window, 'modbus') or not self.parent_window.modbus:
            self.log("Error: Modbus client not available")
            self.stop_monitoring()
            return

        if not self.parent_window.modbus.is_connected():
            self.log("Error: Modbus connection lost")
            self.stop_monitoring()
            return

        try:
            try:
                protocol_offset = self.convert_user_address_to_offset(self.current_start_address, self.current_function)
            except ValueError as e:
                self.parent_window._log(f"Address error: {e}")
                return

            if "Coils" in self.current_function:
                if "Read Coils" in self.current_function:
                    data = self.parent_window.modbus.read_coils(protocol_offset, self.current_count)
                else:
                    return  # write functions don't poll
            elif "Discrete Inputs" in self.current_function:
                data = self.parent_window.modbus.read_discrete_inputs(protocol_offset, self.current_count)
            elif "Holding Registers" in self.current_function:
                data = self.parent_window.modbus.read_registers(protocol_offset, self.current_count)
            elif "Input Registers" in self.current_function:
                data = self.parent_window.modbus.read_input_registers(protocol_offset, self.current_count)
            else:
                return

            if data is not None:
                self.update_table_values(data)
            else:
                error_msg = getattr(self.parent_window.modbus, 'last_error', 'Unknown error')
                self.log(f"Read failed: {error_msg}")
        except Exception as e:
            self.log(f"Monitoring error: {e}")
            self.stop_monitoring()

    def update_table_values(self, data):
        for i in range(min(len(data), self.current_count)):
            value = data[i] if isinstance(data, list) else data

            value_item = self.table.item(i, 1)
            if value_item and not value_item.flags() & Qt.ItemIsEditable:
                value_item.setText(str(int(value)))
                value_item.setBackground(QColor("#E8F5E8"))

            original_address = self.current_start_address + i
            self.current_data[original_address] = value

    def on_cell_changed(self, row, column):
        """Handle manual value edits for write operations only."""
        if self._building_table:
            return
        if column != 1:
            return

        if not hasattr(self, 'current_function') or not self.current_function:
            return

        if "Write" not in self.current_function:
            return

        address = self.current_start_address + row
        value_text = self.table.item(row, 1).text()

        try:
            if "Coils" in self.current_function:
                value = bool(int(value_text)) if value_text else False
            else:
                value = int(value_text) if value_text else 0

            self.current_data[address] = value

            success = self.write_value_to_device(address, value)
            if success:
                self.log(f"Wrote {value} to address {address}")
            else:
                self.log(f"Write failed to address {address}: {getattr(self.parent_window.modbus, 'last_error', 'Unknown error')}")
        except ValueError as e:
            self.log(f"Invalid value '{value_text}' for address {address}: {e}")
            if address in self.current_data:
                self.table.item(row, 1).setText(str(self.current_data[address]))

    def write_value_to_device(self, address, value):
        """Write a single value to the Modbus device."""
        try:
            if not hasattr(self.parent_window, 'modbus') or not self.parent_window.modbus:
                self.log("Error: No Modbus connection available for write operation")
                return False

            if not self.parent_window.modbus.is_connected():
                self.log("Error: Not connected to Modbus device for write operation")
                return False

            if self.get_operation_type(self.current_function) is None:
                self.log(f"Error: Could not determine operation type from function: {self.current_function}")
                return False

            try:
                protocol_offset = self.convert_user_address_to_offset(address, self.current_function)
            except ValueError as e:
                self.log(f"Address error: {e}")
                return False

            if "Write Single Coil" in self.current_function:
                return self.parent_window.modbus.write_coil(protocol_offset, value)
            elif "Write Single Register" in self.current_function:
                return self.parent_window.modbus.write_register(protocol_offset, value)
            elif "Write Multiple Coils" in self.current_function:
                # Each row is edited independently, so this only ever writes one coil at a time
                return self.parent_window.modbus.write_coils(protocol_offset, [value])
            elif "Write Multiple Registers" in self.current_function:
                # Each row is edited independently, so this only ever writes one register at a time
                return self.parent_window.modbus.write_registers(protocol_offset, [value])
            else:
                self.log(f"Error: Write operation not supported for function: {self.current_function}")
                return False
        except Exception as e:
            self.log(f"Write error: {e}")
            return False

    def on_coil_checkbox_changed(self, row, state):
        """Handle coil checkbox state change for write operations."""
        try:
            if not hasattr(self, 'current_function') or not self.current_function:
                return

            if "Write" not in self.current_function:
                return

            value = (state == 2)  # Qt.Checked
            address = self.current_start_address + row
            self.current_data[address] = value

            success = self.write_value_to_device(address, value)
            if success:
                self.log(f"Wrote coil {'ON' if value else 'OFF'} to address {address}")
            else:
                self.log(f"Coil write failed to address {address}: {getattr(self.parent_window.modbus, 'last_error', 'Unknown error')}")
        except Exception as e:
            self.log(f"Error in coil checkbox handler: {e}")

    def log(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_output.append(f"{timestamp} {message}")
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
