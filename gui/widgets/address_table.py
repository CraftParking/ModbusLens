from PySide6.QtWidgets import (

    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 

    QPushButton, QTableWidget, QHeaderView, QComboBox, QSpinBox,

    QCheckBox, QGroupBox, QSplitter, QTextEdit, QTableWidgetItem, QSizePolicy, QAbstractItemView

)

from PySide6.QtCore import Qt, QTimer, Signal

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

        self.address_input.setRange(0, 65535)

        self.address_input.setValue(0)

        address_layout.addWidget(self.address_input)

        

        # Count

        address_layout.addWidget(QLabel("Count:"))

        self.count_input = QSpinBox()
        self.count_input.setRange(1, 2000)  # Modbus standard allows up to 2000 registers/coils
        self.count_input.setValue(1)  # Default to 1 for new layout

        address_layout.addWidget(self.count_input)

        

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

        self.table.setColumnCount(2)  # Only Address and Value columns

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
        self.monitoring_checkbox.setEnabled(False)
        self.interval_input.setEnabled(False)



    def on_function_changed(self, function_text):

        """Handle function type change."""

        is_write_function = any(f in function_text for f in ["Write Single", "Write Multiple"])

        self.count_input.setEnabled(not is_write_function or "Multiple" in function_text)

        

        if "Write Single" in function_text:

            self.count_input.setValue(1)

            self.count_input.setEnabled(False)

            

    def get_modbus_address(self, address: int, function: str) -> str:

        """Get proper Modbus address format based on function type.

        

        Modbus Address Formats:

        - Coils (Read/Write): 000001-065536

        - Discrete Inputs: 100001-165536

        - Holding Registers: 400001-465536

        - Input Registers: 300001-365536

        """

        # Explicit function name matching for all 8 functions

        if function == "Read Coils (1)" or function == "Write Single Coil (5)" or function == "Write Multiple Coils (15)":

            return f"{address + 1:06d}"  # 000001 format

        elif function == "Read Holding Registers (3)" or function == "Write Single Register (6)" or function == "Write Multiple Registers (16)":

            return f"{400000 + address + 1:06d}"  # 400001 format

        elif function == "Read Discrete Inputs (2)":

            return f"{100000 + address + 1:06d}"  # 100001 format

        elif function == "Read Input Registers (4)":

            return f"{300000 + address + 1:06d}"  # 300001 format

        else:

            return str(address)  # Fallback to simple address

    

    def create_address_table(self):

        """Create the address table based on input parameters."""

        function = self.function_combo.currentText()

        start_address = self.address_input.value()

        count = self.count_input.value()

        

        # STRICT: Disable monitoring checkbox during table creation

        # Store current state to restore after creation

        was_enabled_before = self.monitoring_checkbox.isEnabled()

        self.monitoring_checkbox.setEnabled(False)

        

        # Validate inputs

        if start_address + count > 65536:

            self.log(f"Error: Address range exceeds 65535")

            return

        

        # Modbus standard allows up to 2000 registers/2000 coils per request
        # Remove artificial 20-row limitation for full Modbus compliance
        # The table will handle any reasonable count within Modbus specifications

        

        # Clear existing data

        self.table.setRowCount(0)

        self.current_data.clear()

        

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

            value_item = QTableWidgetItem("")

            if is_write:

                value_item.setFlags(value_item.flags() | Qt.ItemIsEditable)

                # Light blue background for writable values

                value_item.setBackground(QColor("#E6F3FF"))  # Light blue for editable

            else:

                value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)

                # White background for read-only values

                value_item.setBackground(QColor("#FFFFFF"))  # White for read-only

            self.table.setItem(i, 1, value_item)

        

        # STRICT: Do NOT enable monitoring controls - only enable when there's active connection

        # The monitoring checkbox will be enabled by _set_connection_controls when connected

        # self.monitoring_checkbox.setEnabled(True)  # REMOVED - strict control

        # self.interval_input.setEnabled(True)  # REMOVED - strict control

        

        # Restore monitoring checkbox state based on connection (strict control)

        # Only enable if there's an active connection (check main window connection state)

        if hasattr(self, 'parent_window') and self.parent_window:

            # Check if the main window indicates a successful connection

            if hasattr(self.parent_window, 'modbus') and self.parent_window.modbus:

                # Check if connected (using the main window's connection state)

                connect_btn_enabled = self.parent_window.connect_btn.isEnabled()

                disconnect_btn_enabled = self.parent_window.disconnect_btn.isEnabled()

                

                # If disconnect button is enabled, we have an active connection

                if disconnect_btn_enabled:

                    self.monitoring_checkbox.setEnabled(True)

                else:

                    self.monitoring_checkbox.setEnabled(False)

            else:

                self.monitoring_checkbox.setEnabled(False)

        else:

            self.monitoring_checkbox.setEnabled(False)

        

        # Store current configuration

        self.current_function = function

        self.current_start_address = start_address

        self.current_count = count

        

        # Do NOT auto-populate with demo data - let users input real values

        # Demo data was causing confusion with random numbers

        

        self.log(f"Created table: {function} from address {start_address}, count {count}")

        

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

            # Read data based on function type

            if "Coils" in self.current_function:

                if "Read Coils" in self.current_function:

                    data = self.parent_window.modbus.read_coils(self.current_start_address, self.current_count)

                else:

                    return  # Write operations don't need polling

            elif "Discrete Inputs" in self.current_function:

                data = self.parent_window.modbus.read_discrete_inputs(self.current_start_address, self.current_count)

            elif "Holding Registers" in self.current_function:

                data = self.parent_window.modbus.read_registers(self.current_start_address, self.current_count)

            elif "Input Registers" in self.current_function:

                data = self.parent_window.modbus.read_input_registers(self.current_start_address, self.current_count)

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

            

    def update_demo_data(self):

        """Update table with demo data when not connected to Modbus device."""

        import random

        

        for i in range(self.current_count):

            # Generate random demo values based on function type

            if "Coils" in self.current_function:

                demo_value = random.choice([True, False])

                display_value = "1" if demo_value else "0"

            elif "Registers" in self.current_function:

                demo_value = random.randint(0, 65535)

                display_value = str(demo_value)

            else:

                demo_value = random.randint(0, 255)

                display_value = str(demo_value)

            

            # Update value column (column 1)

            value_item = self.table.item(i, 1)

            if value_item:

                value_item.setText(display_value)

                value_item.setBackground(QColor("#E8F5E8"))  # Light green for demo data

                

            # Store current value with original address as key

            original_address = self.current_start_address + i

            self.current_data[original_address] = demo_value

            

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
                # Update hex and binary representations
                self.update_cell_formats(row, value)
            else:
                self.log(f"Write failed to address {address}: {getattr(self.parent_window.modbus, 'last_error', 'Unknown error')}")

                

        except ValueError as e:

            self.log(f"Invalid value '{value_text}' for address {address}: {e}")

            # Revert to previous value if available

            if address in self.current_data:

                self.table.item(row, 1).setText(str(self.current_data[address]))

                

    def update_cell_formats(self, row, value):

        """Update hex and binary format cells."""

        hex_item = self.table.item(row, 2)

        if hex_item:

            hex_item.setText(f"0x{int(value):04X}" if isinstance(value, (int, bool)) else "")

            

        binary_item = self.table.item(row, 3)

        if binary_item:

            binary_item.setText(format(int(value), '016b') if isinstance(value, (int, bool)) else "")

            

    def write_value_to_device(self, address, value):
        """Write a single value to the Modbus device."""
        try:
            if "Write Single Coil" in self.current_function:
                return self.parent_window.modbus.write_coil(address, value)
            elif "Write Single Register" in self.current_function:
                return self.parent_window.modbus.write_register(address, value)
            elif "Write Multiple Coils" in self.current_function:
                # For multiple coils, write a single coil as a list
                return self.parent_window.modbus.write_coils(address, [value])
            elif "Write Multiple Registers" in self.current_function:
                # For multiple registers, write a single register as a list
                return self.parent_window.modbus.write_registers(address, [value])
            else:
                self.log(f"Error: Write operation not supported for function: {self.current_function}")
                return False
        except Exception as e:
            self.log(f"Write error: {e}")
            return False

            

    def log(self, message):

        """Add message to log output."""

        timestamp = time.strftime("[%H:%M:%S]")

        self.log_output.append(f"{timestamp} {message}")

        # Auto-scroll to bottom

        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

