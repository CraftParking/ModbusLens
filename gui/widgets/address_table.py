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
        
        self.range_is_one_based = False
        self._building_table = False

        

        self.setup_ui()

        

    def setup_ui(self):

        """Setup the address table interface."""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        

        # Control Panel with monitoring and log side by side

        control_layout = QHBoxLayout()

        

        # Left side - Function and address controls

        left_controls = QVBoxLayout()

        

        # Function and address group

        control_group = QGroupBox("Address Range Configuration")

        address_layout = QHBoxLayout(control_group)

        

        # Function Type

        address_layout.addWidget(QLabel("Function:"))

        self.function_combo = QComboBox()

        self.function_combo.addItems([

            "Read Coils (1)", "Read Discrete Inputs (2)", "Read Holding Registers (3)",

            "Read Input Registers (4)", "Write Single Coil (5)", "Write Single Register (6)",

            "Write Multiple Coils (15)", "Write Multiple Registers (16)"

        ])

        self.function_combo.currentTextChanged.connect(self.on_function_changed)

        address_layout.addWidget(self.function_combo)

        

        # Starting Address

        address_layout.addWidget(QLabel("Start Address:"))

        self.address_input = QSpinBox()

        self.address_input.setRange(1, 65536)

        self.address_input.setValue(1)
        self.address_input.valueChanged.connect(self.on_address_range_changed)

        address_layout.addWidget(self.address_input)

        

        # Count

        address_layout.addWidget(QLabel("Count:"))

        self.count_input = QSpinBox()
        self.count_input.setRange(1, 2000)  # Modbus standard allows up to 2000 registers/coils
        self.count_input.setValue(1)  # Default to 1 for new layout
        self.count_input.valueChanged.connect(self.on_address_range_changed)

        address_layout.addWidget(self.count_input)

        # Address offset mode
        self.offset_checkbox = QCheckBox("1-Based Addressing")
        self.offset_checkbox.setToolTip("When enabled, user address 1 is sent as protocol offset 0")
        self.offset_checkbox.stateChanged.connect(self.on_offset_checkbox_changed)
        address_layout.addWidget(self.offset_checkbox)

        

        # Create Table Button

        self.create_btn = QPushButton("Create Table")

        self.create_btn.clicked.connect(self.create_address_table)

        # Remove special styling - make it a normal button

        address_layout.addWidget(self.create_btn)

        

        left_controls.addWidget(control_group)

        

        # Monitoring controls

        monitor_group = QGroupBox("Live Monitoring")

        monitor_layout = QHBoxLayout(monitor_group)

        

        self.monitoring_checkbox = QCheckBox("Enable Live Monitoring")

        self.monitoring_checkbox.stateChanged.connect(self.toggle_monitoring)

        self.monitoring_checkbox.setEnabled(False)  # Initially disabled until connection

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

        

        # Right side - Status Log

        log_group = QGroupBox("Status Log")

        log_layout = QVBoxLayout(log_group)

        

        self.log_output = QTextEdit()

        self.log_output.setMinimumHeight(200)  # Taller for better visibility

        self.log_output.setMaximumWidth(300)  # Limit width to not dominate

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

        

        # Add left and right sides to main control layout

        control_layout.addLayout(left_controls, 3)  # Left side gets 3/4 space

        control_layout.addWidget(log_group, 1)       # Right side gets 1/4 space

        

        layout.addLayout(control_layout)

        

        # Address Table (full width below controls)

        self.table = QTableWidget()

        self.table.setColumnCount(2)  # Address, Value columns
        self.table.setHorizontalHeaderLabels(["Address", "Value"])

        self.table.setAlternatingRowColors(True)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.table.setMinimumHeight(400)  # Ensure minimum height
        
        # Add proper size policy for resizing
        # Constrain table to proper size within layout
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(300)
        self.table.setMaximumHeight(400)  # Limit table height to prevent overflow
        
        # Make table scrollable and enable value modification
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)  # Show when needed
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setAutoScroll(True)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        # Ensure proper viewport behavior
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
        layout.setStretchFactor(self.table, 1)  # Normal stretch factor

        

        # Initially disable all controls until connection
        self.function_combo.setEnabled(False)
        self.address_input.setEnabled(False)
        self.count_input.setEnabled(False)
        self.create_btn.setEnabled(False)
        self.offset_checkbox.setEnabled(False)
        self.monitoring_checkbox.setEnabled(False)
        self.interval_input.setEnabled(False)



    def on_function_changed(self, function_text):

        """Handle function type change."""

        is_write_function = any(f in function_text for f in ["Write Single", "Write Multiple"])

        self.count_input.setEnabled(not is_write_function or "Multiple" in function_text)

        

        if "Write Single" in function_text:

            self.count_input.setValue(1)

            self.count_input.setEnabled(False)

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
        maximum = 65536 if self.range_is_one_based else 65535
        self.address_input.setRange(1, maximum)
        if current_value < 1:
            self.address_input.setValue(1)

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

        """Create the address table based on input parameters."""

        function = self.function_combo.currentText()

        self.ensure_address_mode_bounds()

        start_address = self.address_input.value()

        count = self.count_input.value()

        

        # STRICT: Disable monitoring checkbox during table creation

        # Store current state to restore after creation

        was_enabled_before = self.monitoring_checkbox.isEnabled()

        self.monitoring_checkbox.setEnabled(False)

        

        # Validate inputs

        try:
            start_offset = self.convert_user_address_to_offset(start_address, function)
        except ValueError as e:
            self.log(f"Address error: {e}")
            return

        if start_offset + count > 65536:

            self.log(f"Error: Address range exceeds 65535")

            return

        

        # Modbus standard allows up to 2000 registers/2000 coils per request
        # Remove artificial 20-row limitation for full Modbus compliance
        # The table will handle any reasonable count within Modbus specifications

        

        # Clear existing data

        self._building_table = True
        self.table.setRowCount(0)

        self.current_data.clear()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Address", "Value"])
        

        # Set up table rows

        self.table.setRowCount(count)

        

        # Determine if this is a write operation

        is_write = "Write" in function

        

        for i in range(count):

            address = start_address + i

            modbus_address = self.get_modbus_address(address, function)
            
            # Address column (read-only) - show proper Modbus address

            address_item = QTableWidgetItem(modbus_address)

            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)

            address_item.setBackground(QColor("#F0F0F0"))

            self.table.setItem(i, 0, address_item)

            
            # Value column (editable only for write functions, read-only for read functions)

            if is_write and "Coil" in function:
                # Use checkbox for coil write functions
                checkbox = QCheckBox()
                checkbox.setChecked(False)  # Default to false
                checkbox.setStyleSheet("QCheckBox { margin-left: 5px; }")
                self.table.setCellWidget(i, 1, checkbox)
                # Connect checkbox state change to handle write
                checkbox.stateChanged.connect(lambda state, row=i: self.on_coil_checkbox_changed(row, state))
            else:
                # Use text field for other cases
                value_item = QTableWidgetItem("")
                if is_write:
                    value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)
                else:
                    value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, 1, value_item)

        self._building_table = False
            
        # STRICT: Do NOT enable monitoring controls - only enable when there's active connection

        # The monitoring checkbox will be enabled by _set_connection_controls when connected

        # self.monitoring_checkbox.setEnabled(True)  # REMOVED - strict control

        # self.interval_input.setEnabled(True)  # REMOVED - strict control

        

        # Restore monitoring checkbox state based on connection (strict control)

        # Only enable if there's an active connection (check main window connection state)

        self.update_monitoring_availability()

        

        # Store current configuration

        self.current_function = function

        self.current_start_address = start_address

        self.current_count = count

        

        # Do NOT auto-populate with demo data - let users input real values

        # Demo data was causing confusion with random numbers

        

        self.log(f"Created table: {function} from address {start_address}, count {count}")

        

    def on_offset_checkbox_changed(self, state):
        """Handle range-level offset checkbox state change."""
        self.range_is_one_based = (state == 2)  # Qt.Checked is 2
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
            self.log(f"Toggle monitoring called with state: {state}")
            
            if state == 2:  # Qt.Checked value is 2
                # Check if current function supports monitoring (only read functions)
                if hasattr(self, 'current_function') and self.current_function:
                    is_read = "Read" in self.current_function
                    if not is_read:
                        self.log("Live monitoring is only available for read functions")
                        self.monitoring_checkbox.setChecked(False)
                        return
                
                # Auto-turn off tag monitoring when starting address table monitoring
                if hasattr(self.parent_window, 'tag_start_monitoring_btn'):
                    if not self.parent_window.tag_start_monitoring_btn.isEnabled():
                        # Tag monitoring is active, stop it
                        self.parent_window.tag_stop_monitoring_btn.click()
                        self.log("Auto-stopped tag monitoring")
                
                self.interval_input.setEnabled(True)
                self.log("Starting monitoring via checkbox")
                self.start_monitoring()
            else:
                self.interval_input.setEnabled(False)
                self.log("Stopping monitoring via checkbox")
                self.stop_monitoring()
        except Exception as e:
            self.log(f"Error in toggle_monitoring: {e}", "ERROR")

            

    def start_monitoring(self):

        """Start live monitoring."""

        try:

            self.log("start_monitoring called")

            

            if not hasattr(self, 'current_function'):

                self.log("Error: Please create a table first")

                self.monitoring_checkbox.setChecked(False)

                return

            

            self.log(f"current_function exists: {getattr(self, 'current_function', 'NOT_FOUND')}")

            

            # Check if parent window exists and has modbus connection

            if not self.parent_window:

                self.log("Error: No parent window")

                self.monitoring_checkbox.setChecked(False)

                return

            

            self.log(f"parent_window exists: {type(self.parent_window)}")

            

            # Check for modbus connection - require real connection for monitoring

            if not hasattr(self.parent_window, 'modbus') or not self.parent_window.modbus:

                self.log("Error: Modbus client not initialized - please connect first")

                self.monitoring_checkbox.setChecked(False)

                return

            

            modbus = self.parent_window.modbus

            self.log(f"modbus client exists: {type(modbus)}")

            

            if not modbus.is_connected():

                self.log("Error: Not connected to Modbus server - please connect first")

                self.monitoring_checkbox.setChecked(False)

                return

            

            self.log("modbus is connected - starting monitoring")

            

            # Real connection confirmed - start monitoring

            self.monitoring_active = True

            interval = self.interval_input.value()

            self.monitoring_timer.start(interval)

            self.log(f"Started monitoring with {interval}ms interval")

            

        except Exception as e:

            self.log(f"Error in start_monitoring: {e}", "ERROR")

            import traceback

            self.log(f"Traceback: {traceback.format_exc()}", "ERROR")

        

    def stop_monitoring(self):

        """Stop live monitoring."""

        self.monitoring_active = False

        self.monitoring_timer.stop()

        self.log("Stopped monitoring")

        

    def update_monitoring_interval(self):

        """Update monitoring interval."""

        if self.monitoring_active:

            interval = self.interval_input.value()

            self.monitoring_timer.setInterval(interval)

            self.log(f"Updated monitoring interval to {interval}ms")

            

    def update_table_data(self):

        """Update table data from Modbus device."""

        if not self.monitoring_active:

            return

            

        # Ensure parent window and modbus connection exist

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

            # Read data based on function type
            if "Coils" in self.current_function:
                if "Read Coils" in self.current_function:
                    data = self.parent_window.modbus.read_coils(protocol_offset, self.current_count)
                else:
                    return  # Write operations don't need polling
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
                self.log(f"Updated {len(data) if isinstance(data, list) else 1} values")
            else:
                error_msg = getattr(self.parent_window.modbus, 'last_error', 'Unknown error')
                self.log(f"Read failed: {error_msg}")

        except Exception as e:
            self.log(f"Monitoring error: {e}")
            # Stop monitoring on errors to prevent continuous failures
            self.stop_monitoring()

            

    def update_table_values(self, data):

        """Update table with new data."""

        for i in range(min(len(data), self.current_count)):

            value = data[i] if isinstance(data, list) else data

            

            # Update value column (column 1)

            value_item = self.table.item(i, 1)

            if value_item and not value_item.flags() & Qt.ItemIsEditable:

                value_item.setText(str(int(value)))

                value_item.setBackground(QColor("#E8F5E8"))  # Light green for updated values

                

            # Store current value with original address as key

            original_address = self.current_start_address + i

            self.current_data[original_address] = value

            

    def on_cell_changed(self, row, column):

        """Handle cell value changes for write operations only."""

        if self._building_table:

            return

        if column != 1:  # Only value column is writable for operations

            return

            

        # Only process changes for write functions

        if not hasattr(self, 'current_function') or not self.current_function:

            return

            

        is_write = "Write" in self.current_function

        if not is_write:

            return  # Don't process changes for read functions

            

        # Always register the value in current_data for write functions

        address = self.current_start_address + row

        value_text = self.table.item(row, 1).text()

        

        try:

            # Parse value based on function type and store in current_data

            if "Coils" in self.current_function:

                value = bool(int(value_text)) if value_text else False

            else:

                value = int(value_text) if value_text else 0

                

            # Always store the value in current_data for registration

            self.current_data[address] = value

            self.log(f"Registered write value {value} at address {address}")

            

            # Always write to device for write functions (no monitoring required)
            # Live monitoring should only be for read functions
            success = self.write_value_to_device(address, value)
            
            if success:
                self.log(f"Wrote {value} to address {address}")
            else:
                self.log(f"Write failed to address {address}: {getattr(self.parent_window.modbus, 'last_error', 'Unknown error')}")

                

        except ValueError as e:

            self.log(f"Invalid value '{value_text}' for address {address}: {e}")

            # Revert to previous value if available

            if address in self.current_data:

                self.table.item(row, 1).setText(str(self.current_data[address]))

                

    def write_value_to_device(self, address, value):
        """Write a single value to the Modbus device."""
        try:
            # Check if parent window and modbus connection exist
            if not hasattr(self, 'parent_window') or not self.parent_window:
                self.log("Error: No parent window available for write operation")
                return False
            
            if not hasattr(self.parent_window, 'modbus') or not self.parent_window.modbus:
                self.log("Error: No Modbus connection available for write operation")
                return False
                
            # Check if modbus is connected
            if not self.parent_window.modbus.is_connected():
                self.log("Error: Not connected to Modbus device for write operation")
                return False
            
            if self.get_operation_type(self.current_function) is None:
                self.log(f"ERROR: Could not determine operation type from function: {self.current_function}")
                return False
            
            try:
                protocol_offset = self.convert_user_address_to_offset(address, self.current_function)
            except ValueError as e:
                self.log(f"Address error: {e}")
                return False
            
            self.log(f"Writing value={value} to protocol offset={protocol_offset}")
            
            if "Write Single Coil" in self.current_function:
                return self.parent_window.modbus.write_coil(protocol_offset, value)
            elif "Write Single Register" in self.current_function:
                return self.parent_window.modbus.write_register(protocol_offset, value)
            elif "Write Multiple Coils" in self.current_function:
                # For multiple coils, write a single coil as a list
                return self.parent_window.modbus.write_coils(protocol_offset, [value])
            elif "Write Multiple Registers" in self.current_function:
                # For multiple registers, write a single register as a list
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
            # Only process changes for write functions
            if not hasattr(self, 'current_function') or not self.current_function:
                self.log("ERROR: No current_function set")
                return
            
            self.log(f"Current function: {self.current_function}")
                
            is_write = "Write" in self.current_function
            if not is_write:
                return  # Don't process changes for read functions
                
            # Convert checkbox state to boolean value
            value = (state == 2)  # Qt.Checked is 2, Qt.Unchecked is 0
            
            # Get the address for this row
            address = self.current_start_address + row
            
            self.log(f"Coil checkbox changed: {'ON' if value else 'OFF'} at address {address}")
            
            # Store the value in current_data
            self.current_data[address] = value
            
            # Write to device immediately
            success = self.write_value_to_device(address, value)
            
            if success:
                self.log(f"Wrote coil {'ON' if value else 'OFF'} to address {address}")
            else:
                self.log(f"Coil write failed to address {address}: {getattr(self.parent_window.modbus, 'last_error', 'Unknown error')}")
                
        except Exception as e:
            self.log(f"Error in coil checkbox handler: {e}")

    def log(self, message):

        """Add message to log output."""

        timestamp = time.strftime("[%H:%M:%S]")

        self.log_output.append(f"{timestamp} {message}")

        # Auto-scroll to bottom

        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

