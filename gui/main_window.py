import sys
import logging
import time
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QGridLayout,
    QSplitter, QFrame, QComboBox, QSpinBox, QCheckBox, QProgressBar,
    QStatusBar, QMenuBar, QMenu, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget, QScrollArea, QSystemTrayIcon
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QBrush

from core.modbus_client import ModbusClient

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


class StatusIndicator(QWidget):
    """Custom status indicator widget with colored circle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self._status = "disconnected"  # disconnected, connecting, connected, error
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self.update)
        self._animation_angle = 0

    def set_status(self, status: str):
        """Set status: 'disconnected', 'connecting', 'connected', 'error'"""
        self._status = status.lower()
        if status == "connecting":
            self._animation_timer.start(50)  # 20 FPS animation
        else:
            self._animation_timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = QPoint(self.width() // 2, self.height() // 2)
        radius = min(self.width(), self.height()) // 2 - 2

        # Choose color based on status
        if self._status == "connected":
            color = QColor("#4CAF50")  # Green
        elif self._status == "connecting":
            color = QColor("#FF9800")  # Orange
            # Animated pulsing effect
            self._animation_angle = (self._animation_angle + 10) % 360
            intensity = (1 + 0.3 * (self._animation_angle / 180.0 * 3.14159).sin()) / 1.3
            color.setAlphaF(intensity)
        elif self._status == "error":
            color = QColor("#F44336")  # Red
        else:  # disconnected
            color = QColor("#9E9E9E")  # Gray

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center, radius, radius)

        # Add white border for better visibility
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawEllipse(center, radius, radius)


class ModbusGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.modbus = None
        self.connection_history = []
        self.monitoring_active = False
        self.monitoring_timer = QTimer(self)
        self.monitoring_timer.timeout.connect(self._update_monitored_data)

        self._setup_window()
        self._setup_menu()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()
        self._load_settings()

    def _setup_window(self):
        """Setup main window properties."""
        self.setWindowTitle("ModbusLens - Professional Modbus TCP Client")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)

        # Set application icon if available
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _setup_menu(self):
        """Setup menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")
        file_menu.addAction("New Session", self._new_session)
        file_menu.addAction("Save Session", self._save_session)
        file_menu.addAction("Load Session", self._load_session)
        file_menu.addSeparator()
        file_menu.addAction("Export Data", self._export_data)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # View menu
        view_menu = menubar.addMenu("&View")
        self.theme_action = view_menu.addAction("Dark Theme", self._toggle_theme)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(True)  # Default to dark theme

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction("Connection Profiles", self._manage_profiles)
        tools_menu.addAction("Data Templates", self._manage_templates)
        tools_menu.addAction("Scripting Console", self._show_scripting_console)
        tools_menu.addSeparator()
        tools_menu.addAction("Network Diagnostics", self._network_diagnostics)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("Documentation", self._show_documentation)
        help_menu.addAction("About", self._show_about)

    def _setup_central_widget(self):
        """Setup the main central widget with modern layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Top section: Connection and status
        self._setup_connection_section(main_layout)

        # Main content area with splitter
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter)

        # Operations section
        self._setup_operations_section(splitter)

        # Bottom section: Output and monitoring
        self._setup_bottom_section(splitter)

        # Set splitter proportions
        splitter.setSizes([400, 300])

    def _setup_connection_section(self, parent_layout):
        """Setup connection section with modern design."""
        connection_frame = QFrame()
        connection_frame.setFrameStyle(QFrame.StyledPanel)
        connection_frame.setStyleSheet("""
            QFrame {
                background-color: #2D2D30;
                border: 1px solid #3E3E42;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(connection_frame)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Status indicator
        status_layout = QVBoxLayout()
        status_layout.setAlignment(Qt.AlignCenter)

        status_label = QLabel("Status")
        status_label.setStyleSheet("color: #CCCCCC; font-weight: bold;")
        status_layout.addWidget(status_label)

        self.status_indicator = StatusIndicator()
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("Disconnected")
        self.status_text.setStyleSheet("color: #CCCCCC;")
        status_layout.addWidget(self.status_text)

        layout.addLayout(status_layout)

        # Connection inputs
        inputs_layout = QGridLayout()
        inputs_layout.setSpacing(10)

        # IP input
        ip_label = QLabel("IP Address:")
        ip_label.setStyleSheet("color: #CCCCCC;")
        inputs_layout.addWidget(ip_label, 0, 0)

        self.ip_input = QLineEdit("127.0.0.1")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.ip_input, 0, 1)

        # Port input
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #CCCCCC;")
        inputs_layout.addWidget(port_label, 1, 0)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        self.port_input.setStyleSheet("""
            QSpinBox {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.port_input, 1, 1)

        # Unit ID input
        unit_label = QLabel("Unit ID:")
        unit_label.setStyleSheet("color: #CCCCCC;")
        inputs_layout.addWidget(unit_label, 0, 2)

        self.unit_input = QSpinBox()
        self.unit_input.setRange(1, 247)
        self.unit_input.setValue(1)
        self.unit_input.setStyleSheet("""
            QSpinBox {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.unit_input, 0, 3)

        # Connection history
        history_label = QLabel("Recent:")
        history_label.setStyleSheet("color: #CCCCCC;")
        inputs_layout.addWidget(history_label, 1, 2)

        self.connection_history_combo = QComboBox()
        self.connection_history_combo.setStyleSheet("""
            QComboBox {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.connection_history_combo, 1, 3)

        layout.addLayout(inputs_layout)

        # Control buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)

        self.connect_btn = QPushButton("🔗 Connect")
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1177BB;
            }
            QPushButton:pressed {
                background-color: #0D5A8A;
            }
        """)
        buttons_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("❌ Disconnect")
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #C42B1C;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #E33B2C;
            }
            QPushButton:pressed {
                background-color: #A8251A;
            }
        """)
        self.disconnect_btn.setEnabled(False)
        buttons_layout.addWidget(self.disconnect_btn)

        layout.addLayout(buttons_layout)

        parent_layout.addWidget(connection_frame)

    def _setup_operations_section(self, splitter):
        """Setup operations section with tabs."""
        operations_widget = QWidget()
        operations_layout = QVBoxLayout(operations_widget)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3E3E42;
                background-color: #2D2D30;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #2D2D30;
                color: #CCCCCC;
                padding: 8px 16px;
                border: 1px solid #3E3E42;
                border-bottom: none;
                border-radius: 8px 8px 0 0;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #007ACC;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #3E3E42;
            }
        """)

        # Read operations tab
        self._setup_read_tab()

        # Write operations tab
        self._setup_write_tab()

        # Monitoring tab
        self._setup_monitoring_tab()

        operations_layout.addWidget(self.tab_widget)
        splitter.addWidget(operations_widget)

    def _setup_read_tab(self):
        """Setup read operations tab."""
        read_widget = QWidget()
        layout = QVBoxLayout(read_widget)

        # Address inputs
        addr_group = QGroupBox("Address Range")
        addr_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 8px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
        """)
        addr_layout = QHBoxLayout(addr_group)

        addr_layout.addWidget(QLabel("Start Address:"))
        self.read_start_addr = QSpinBox()
        self.read_start_addr.setRange(0, 65535)
        self.read_start_addr.setStyleSheet(self._get_input_style())
        addr_layout.addWidget(self.read_start_addr)

        addr_layout.addWidget(QLabel("Count:"))
        self.read_count = QSpinBox()
        self.read_count.setRange(1, 125)
        self.read_count.setValue(10)
        self.read_count.setStyleSheet(self._get_input_style())
        addr_layout.addWidget(self.read_count)

        layout.addWidget(addr_group)

        # Read buttons
        buttons_group = QGroupBox("Read Operations")
        buttons_layout = QGridLayout(buttons_group)

        self.read_coils_btn = self._create_operation_button("Read Coils (0x)", "#4CAF50")
        buttons_layout.addWidget(self.read_coils_btn, 0, 0)

        self.read_discrete_inputs_btn = self._create_operation_button("Read Discrete Inputs (1x)", "#2196F3")
        buttons_layout.addWidget(self.read_discrete_inputs_btn, 0, 1)

        self.read_holding_registers_btn = self._create_operation_button("Read Holding Registers (4x)", "#FF9800")
        buttons_layout.addWidget(self.read_holding_registers_btn, 1, 0)

        self.read_input_registers_btn = self._create_operation_button("Read Input Registers (3x)", "#9C27B0")
        buttons_layout.addWidget(self.read_input_registers_btn, 1, 1)

        layout.addWidget(buttons_group)

        self.tab_widget.addTab(read_widget, "📖 Read")

    def _setup_write_tab(self):
        """Setup write operations tab."""
        write_widget = QWidget()
        layout = QVBoxLayout(write_widget)

        # Address input
        addr_group = QGroupBox("Address")
        addr_layout = QHBoxLayout(addr_group)

        addr_layout.addWidget(QLabel("Address:"))
        self.write_addr = QSpinBox()
        self.write_addr.setRange(0, 65535)
        self.write_addr.setStyleSheet(self._get_input_style())
        addr_layout.addWidget(self.write_addr)

        layout.addWidget(addr_group)

        # Value inputs
        value_group = QGroupBox("Values")
        value_layout = QVBoxLayout(value_group)

        # Single value
        single_layout = QHBoxLayout()
        single_layout.addWidget(QLabel("Single Value:"))
        self.write_single_value = QLineEdit()
        self.write_single_value.setStyleSheet(self._get_input_style())
        single_layout.addWidget(self.write_single_value)
        value_layout.addLayout(single_layout)

        # Multiple values
        multi_layout = QHBoxLayout()
        multi_layout.addWidget(QLabel("Multiple Values (comma-separated):"))
        self.write_multi_values = QLineEdit()
        self.write_multi_values.setStyleSheet(self._get_input_style())
        multi_layout.addWidget(self.write_multi_values)
        value_layout.addLayout(multi_layout)

        layout.addWidget(value_group)

        # Write buttons
        buttons_group = QGroupBox("Write Operations")
        buttons_layout = QGridLayout(buttons_group)

        self.write_coil_btn = self._create_operation_button("Write Coil", "#4CAF50")
        buttons_layout.addWidget(self.write_coil_btn, 0, 0)

        self.write_register_btn = self._create_operation_button("Write Register", "#FF9800")
        buttons_layout.addWidget(self.write_register_btn, 0, 1)

        self.write_coils_btn = self._create_operation_button("Write Multiple Coils", "#2196F3")
        buttons_layout.addWidget(self.write_coils_btn, 1, 0)

        self.write_registers_btn = self._create_operation_button("Write Multiple Registers", "#9C27B0")
        buttons_layout.addWidget(self.write_registers_btn, 1, 1)

        layout.addWidget(buttons_group)

        self.tab_widget.addTab(write_widget, "✏️ Write")

    def _setup_monitoring_tab(self):
        """Setup monitoring tab with real-time data display."""
        monitor_widget = QWidget()
        layout = QVBoxLayout(monitor_widget)

        # Control buttons
        control_layout = QHBoxLayout()

        self.start_monitoring_btn = QPushButton("▶️ Start Monitoring")
        self.start_monitoring_btn.setStyleSheet(self._get_button_style("#4CAF50"))
        control_layout.addWidget(self.start_monitoring_btn)

        self.stop_monitoring_btn = QPushButton("⏹️ Stop Monitoring")
        self.stop_monitoring_btn.setStyleSheet(self._get_button_style("#F44336"))
        self.stop_monitoring_btn.setEnabled(False)
        control_layout.addWidget(self.stop_monitoring_btn)

        control_layout.addWidget(QLabel("Interval (ms):"))
        self.monitoring_interval = QSpinBox()
        self.monitoring_interval.setRange(100, 10000)
        self.monitoring_interval.setValue(1000)
        self.monitoring_interval.setStyleSheet(self._get_input_style())
        control_layout.addWidget(self.monitoring_interval)

        layout.addLayout(control_layout)

        # Data table
        self.monitoring_table = QTableWidget()
        self.monitoring_table.setColumnCount(4)
        self.monitoring_table.setHorizontalHeaderLabels(["Address", "Type", "Value", "Timestamp"])
        self.monitoring_table.horizontalHeader().setStretchLastSection(True)
        self.monitoring_table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #2D2D30;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                padding: 5px;
            }
        """)
        layout.addWidget(self.monitoring_table)

        self.tab_widget.addTab(monitor_widget, "📊 Monitor")

    def _setup_bottom_section(self, splitter):
        """Setup bottom section with output and logs."""
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)

        # Output tabs
        self.output_tabs = QTabWidget()
        self.output_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #3E3E42;
                background-color: #1E1E1E;
            }
            QTabBar::tab {
                background-color: #2D2D30;
                color: #CCCCCC;
                padding: 5px 10px;
                border: 1px solid #3E3E42;
            }
            QTabBar::tab:selected {
                background-color: #007ACC;
                color: white;
            }
        """)

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.output_tabs.addTab(self.log_output, "📝 Logs")

        # Raw data output
        self.data_output = QTextEdit()
        self.data_output.setReadOnly(True)
        self.data_output.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.output_tabs.addTab(self.data_output, "📄 Raw Data")

        bottom_layout.addWidget(self.output_tabs)
        splitter.addWidget(bottom_widget)

    def _setup_status_bar(self):
        """Setup status bar with additional information."""
        self.status_bar = self.statusBar()

        self.connection_status = QLabel("Not Connected")
        self.status_bar.addWidget(self.connection_status)

        self.status_bar.addPermanentWidget(QLabel("ModbusLens v1.0"))

    def _get_input_style(self):
        """Get consistent input widget style."""
        return """
            QSpinBox, QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
            QSpinBox:focus, QLineEdit:focus {
                border-color: #007ACC;
            }
        """

    def _get_button_style(self, color="#007ACC"):
        """Get consistent button style."""
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {color}DD;
            }}
            QPushButton:pressed {{
                background-color: {color}BB;
            }}
            QPushButton:disabled {{
                background-color: #666666;
                color: #999999;
            }}
        """

    def _create_operation_button(self, text, color):
        """Create a styled operation button."""
        btn = QPushButton(text)
        btn.setStyleSheet(self._get_button_style(color))
        return btn

    def _connect_signals(self):
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.read_coils_btn.clicked.connect(self.read_coils)
        self.read_discrete_inputs_btn.clicked.connect(self.read_discrete_inputs)
        self.read_holding_registers_btn.clicked.connect(self.read_holding_registers)
        self.read_input_registers_btn.clicked.connect(self.read_input_registers)

        self.write_coil_btn.clicked.connect(self.write_coil)
        self.write_register_btn.clicked.connect(self.write_register)
        self.write_coils_btn.clicked.connect(self.write_coils)
        self.write_registers_btn.clicked.connect(self.write_registers)

    def _connect_signals(self):
        """Connect all UI signals to their handlers."""
        # Connection signals
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.connection_history_combo.currentTextChanged.connect(self._load_connection_from_history)

        # Read operation signals
        self.read_coils_btn.clicked.connect(lambda: self._read_operation("coils"))
        self.read_discrete_inputs_btn.clicked.connect(lambda: self._read_operation("discrete_inputs"))
        self.read_holding_registers_btn.clicked.connect(lambda: self._read_operation("holding_registers"))
        self.read_input_registers_btn.clicked.connect(lambda: self._read_operation("input_registers"))

        # Write operation signals
        self.write_coil_btn.clicked.connect(lambda: self._write_operation("coil"))
        self.write_register_btn.clicked.connect(lambda: self._write_operation("register"))
        self.write_coils_btn.clicked.connect(lambda: self._write_operation("coils"))
        self.write_registers_btn.clicked.connect(lambda: self._write_operation("registers"))

        # Monitoring signals
        self.start_monitoring_btn.clicked.connect(self._start_monitoring)
        self.stop_monitoring_btn.clicked.connect(self._stop_monitoring)

    def _connect(self):
        """Connect to Modbus server."""
        try:
            self.status_indicator.set_status("connecting")
            self.status_text.setText("Connecting...")
            self.connect_btn.setEnabled(False)

            ip = self.ip_input.text().strip()
            port = self.port_input.value()
            unit_id = self.unit_input.value()

            self.modbus = ModbusClient(ip, port, unit_id)

            if self.modbus.connect():
                self.status_indicator.set_status("connected")
                self.status_text.setText(f"Connected to {ip}:{port}")
                self.connection_status.setText(f"Connected: {ip}:{port} (Unit {unit_id})")

                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)

                # Add to connection history
                connection_string = f"{ip}:{port}:{unit_id}"
                if connection_string not in self.connection_history:
                    self.connection_history.insert(0, connection_string)
                    self.connection_history_combo.clear()
                    self.connection_history_combo.addItems(self.connection_history[:10])  # Keep last 10

                self._log(f"✅ Connected to Modbus server at {ip}:{port} (Unit ID: {unit_id})")
            else:
                self.status_indicator.set_status("error")
                self.status_text.setText("Connection Failed")
                self.connect_btn.setEnabled(True)
                self._log("❌ Failed to connect to Modbus server")

        except Exception as e:
            self.status_indicator.set_status("error")
            self.status_text.setText("Connection Error")
            self.connect_btn.setEnabled(True)
            self._log(f"❌ Connection error: {e}")

    def _disconnect(self):
        """Disconnect from Modbus server."""
        if self.modbus:
            self.modbus.disconnect()
            self.modbus = None

        self.status_indicator.set_status("disconnected")
        self.status_text.setText("Disconnected")
        self.connection_status.setText("Not Connected")

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)

        if self.monitoring_active:
            self._stop_monitoring()

        self._log("🔌 Disconnected from Modbus server")

    def _load_connection_from_history(self, connection_string):
        """Load connection parameters from history."""
        if not connection_string or ":" not in connection_string:
            return

        try:
            parts = connection_string.split(":")
            if len(parts) >= 3:
                self.ip_input.setText(parts[0])
                self.port_input.setValue(int(parts[1]))
                self.unit_input.setValue(int(parts[2]))
        except (ValueError, IndexError):
            pass

    def _read_operation(self, operation_type):
        """Handle read operations."""
        if not self._check_connection():
            return

        try:
            start_addr = self.read_start_addr.value()
            count = self.read_count.value()

            if operation_type == "coils":
                data = self.modbus.read_coils(start_addr, count)
                if data is not None:
                    self._log(f"📖 Read {len(data)} coils from {start_addr}: {data}")
                    self._display_raw_data(f"Coils[{start_addr}:{start_addr+count-1}]", data)
                else:
                    self._log("❌ Failed to read coils")

            elif operation_type == "discrete_inputs":
                data = self.modbus.read_discrete_inputs(start_addr, count)
                if data is not None:
                    self._log(f"📖 Read {len(data)} discrete inputs from {start_addr}: {data}")
                    self._display_raw_data(f"DiscreteInputs[{start_addr}:{start_addr+count-1}]", data)
                else:
                    self._log("❌ Failed to read discrete inputs")

            elif operation_type == "holding_registers":
                data = self.modbus.read_registers(start_addr, count)
                if data is not None:
                    self._log(f"📖 Read {len(data)} holding registers from {start_addr}: {data}")
                    self._display_raw_data(f"HoldingRegisters[{start_addr}:{start_addr+count-1}]", data)
                else:
                    self._log("❌ Failed to read holding registers")

            elif operation_type == "input_registers":
                data = self.modbus.read_input_registers(start_addr, count)
                if data is not None:
                    self._log(f"📖 Read {len(data)} input registers from {start_addr}: {data}")
                    self._display_raw_data(f"InputRegisters[{start_addr}:{start_addr+count-1}]", data)
                else:
                    self._log("❌ Failed to read input registers")

        except Exception as e:
            self._log(f"❌ Read operation error: {e}")

    def _write_operation(self, operation_type):
        """Handle write operations."""
        if not self._check_connection():
            return

        try:
            addr = self.write_addr.value()

            if operation_type == "coil":
                value_text = self.write_single_value.text().strip()
                if not value_text:
                    self._log("❌ Please enter a value for coil")
                    return
                value = bool(int(value_text))
                success = self.modbus.write_coil(addr, value)
                if success:
                    self._log(f"✏️ Wrote coil {addr} = {value}")
                else:
                    self._log("❌ Failed to write coil")

            elif operation_type == "register":
                value_text = self.write_single_value.text().strip()
                if not value_text:
                    self._log("❌ Please enter a value for register")
                    return
                value = int(value_text)
                success = self.modbus.write_register(addr, value)
                if success:
                    self._log(f"✏️ Wrote register {addr} = {value}")
                else:
                    self._log("❌ Failed to write register")

            elif operation_type == "coils":
                values_text = self.write_multi_values.text().strip()
                if not values_text:
                    self._log("❌ Please enter values for coils")
                    return
                values = [bool(int(v.strip())) for v in values_text.split(",")]
                success = self.modbus.write_coils(addr, values)
                if success:
                    self._log(f"✏️ Wrote {len(values)} coils starting at {addr}: {values}")
                else:
                    self._log("❌ Failed to write coils")

            elif operation_type == "registers":
                values_text = self.write_multi_values.text().strip()
                if not values_text:
                    self._log("❌ Please enter values for registers")
                    return
                values = [int(v.strip()) for v in values_text.split(",")]
                success = self.modbus.write_registers(addr, values)
                if success:
                    self._log(f"✏️ Wrote {len(values)} registers starting at {addr}: {values}")
                else:
                    self._log("❌ Failed to write registers")

        except ValueError as e:
            self._log(f"❌ Invalid value format: {e}")
        except Exception as e:
            self._log(f"❌ Write operation error: {e}")

    def _start_monitoring(self):
        """Start real-time data monitoring."""
        if not self._check_connection():
            return

        self.monitoring_active = True
        interval = self.monitoring_interval.value()
        self.monitoring_timer.start(interval)

        self.start_monitoring_btn.setEnabled(False)
        self.stop_monitoring_btn.setEnabled(True)

        self._log(f"▶️ Started monitoring with {interval}ms interval")

    def _stop_monitoring(self):
        """Stop real-time data monitoring."""
        self.monitoring_active = False
        self.monitoring_timer.stop()

        self.start_monitoring_btn.setEnabled(True)
        self.stop_monitoring_btn.setEnabled(False)

        self._log("⏹️ Stopped monitoring")

    def _update_monitored_data(self):
        """Update monitored data in the table."""
        if not self.modbus or not self.monitoring_active:
            return

        try:
            # Read some sample data for demonstration
            timestamp = time.strftime("%H:%M:%S")

            # Read coils
            coils = self.modbus.read_coils(0, 8)
            if coils:
                for i, value in enumerate(coils):
                    self._add_monitoring_row(0 + i, "Coil", str(value), timestamp)

            # Read holding registers
            registers = self.modbus.read_registers(0, 8)
            if registers:
                for i, value in enumerate(registers):
                    self._add_monitoring_row(40000 + i, "Holding Reg", str(value), timestamp)

        except Exception as e:
            self._log(f"⚠️ Monitoring error: {e}")

    def _add_monitoring_row(self, address, data_type, value, timestamp):
        """Add a row to the monitoring table."""
        row_count = self.monitoring_table.rowCount()

        # Check if address already exists, update if so
        for row in range(row_count):
            if self.monitoring_table.item(row, 0) and self.monitoring_table.item(row, 0).text() == str(address):
                self.monitoring_table.setItem(row, 2, QTableWidgetItem(value))
                self.monitoring_table.setItem(row, 3, QTableWidgetItem(timestamp))
                return

        # Add new row
        self.monitoring_table.insertRow(row_count)
        self.monitoring_table.setItem(row_count, 0, QTableWidgetItem(str(address)))
        self.monitoring_table.setItem(row_count, 1, QTableWidgetItem(data_type))
        self.monitoring_table.setItem(row_count, 2, QTableWidgetItem(value))
        self.monitoring_table.setItem(row_count, 3, QTableWidgetItem(timestamp))

    def _check_connection(self):
        """Check if connected to Modbus server."""
        if not self.modbus or not self.modbus.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to a Modbus server first.")
            return False
        return True

    def _log(self, message):
        """Add message to log output."""
        timestamp = time.strftime("[%H:%M:%S]")
        current_text = self.log_output.toPlainText()
        if current_text:
            current_text += "\n"
        current_text += f"{timestamp} {message}"
        self.log_output.setPlainText(current_text)

        # Auto scroll to bottom
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _display_raw_data(self, title, data):
        """Display raw data in the data output tab."""
        current_text = self.data_output.toPlainText()
        if current_text:
            current_text += "\n\n"
        current_text += f"[{time.strftime('%H:%M:%S')}] {title}:\n{data}"
        self.data_output.setPlainText(current_text)

    def _load_settings(self):
        """Load user settings and preferences."""
        # Load connection history from a simple file
        try:
            history_file = Path(__file__).parent.parent / "config" / "connection_history.txt"
            if history_file.exists():
                with open(history_file, 'r') as f:
                    self.connection_history = [line.strip() for line in f.readlines() if line.strip()]
                self.connection_history_combo.addItems(self.connection_history[:10])
        except Exception:
            pass

    def _save_settings(self):
        """Save user settings and preferences."""
        try:
            config_dir = Path(__file__).parent.parent / "config"
            config_dir.mkdir(exist_ok=True)
            history_file = config_dir / "connection_history.txt"
            with open(history_file, 'w') as f:
                for connection in self.connection_history[:20]:  # Save last 20
                    f.write(f"{connection}\n")
        except Exception:
            pass

    # Menu action handlers
    def _new_session(self):
        """Start a new session."""
        if self.monitoring_active:
            self._stop_monitoring()
        if self.modbus:
            self._disconnect()
        self.monitoring_table.setRowCount(0)
        self.log_output.clear()
        self.data_output.clear()
        self._log("🆕 New session started")

    def _save_session(self):
        """Save current session."""
        # TODO: Implement session saving
        QMessageBox.information(self, "Save Session", "Session saving will be implemented in the next update!")

    def _load_session(self):
        """Load a saved session."""
        # TODO: Implement session loading
        QMessageBox.information(self, "Load Session", "Session loading will be implemented in the next update!")

    def _export_data(self):
        """Export monitoring data."""
        # TODO: Implement data export
        QMessageBox.information(self, "Export Data", "Data export will be implemented in the next update!")

    def _toggle_theme(self):
        """Toggle between light and dark themes."""
        # TODO: Implement theme switching
        QMessageBox.information(self, "Theme Toggle", "Theme switching will be implemented in the next update!")

    def _manage_profiles(self):
        """Manage connection profiles."""
        # TODO: Implement profile management
        QMessageBox.information(self, "Connection Profiles", "Profile management will be implemented in the next update!")

    def _manage_templates(self):
        """Manage data templates."""
        # TODO: Implement template management
        QMessageBox.information(self, "Data Templates", "Template management will be implemented in the next update!")

    def _show_scripting_console(self):
        """Show scripting console."""
        # TODO: Implement scripting console
        QMessageBox.information(self, "Scripting Console", "Scripting console will be implemented in the next update!")

    def _network_diagnostics(self):
        """Show network diagnostics."""
        # TODO: Implement network diagnostics
        QMessageBox.information(self, "Network Diagnostics", "Network diagnostics will be implemented in the next update!")

    def _show_documentation(self):
        """Show documentation."""
        # TODO: Implement documentation viewer
        QMessageBox.information(self, "Documentation", "Documentation viewer will be implemented in the next update!")

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About ModbusLens",
                         "ModbusLens v1.0\n\n"
                         "Professional Modbus TCP Client\n\n"
                         "Features:\n"
                         "• Real-time data monitoring\n"
                         "• Advanced read/write operations\n"
                         "• Connection profiles\n"
                         "• Data visualization\n"
                         "• Scripting support\n\n"
                         "© 2026 ModbusLens Team")

    def closeEvent(self, event):
        """Handle application close event."""
        if self.monitoring_active:
            self._stop_monitoring()
        if self.modbus:
            self._disconnect()
        self._save_settings()
        event.accept()


def main():
    try:
        # Check if QApplication already exists (e.g., in IDE environments)
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        app.setApplicationName("ModbusLens")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("ModbusLens")

        window = ModbusGUI()
        window.show()

        sys.exit(app.exec())
    except Exception as e:
        error_msg = str(e)
        if "QApplication" in error_msg or "singleton" in error_msg:
            print("GUI Error: QApplication instance already exists.")
            print("This can happen when running in certain IDE environments.")
            print("Try running from command line: python main.py --gui")
        elif "display" in error_msg.lower() or "headless" in error_msg.lower():
            print("GUI Error: No graphical display available.")
            print("This application requires a graphical desktop environment.")
            print("Try running on a system with a GUI, or use the CLI version:")
            print("  python main.py")
        else:
            print(f"Failed to start GUI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()