import sys
import logging
import time
import struct
import csv
import math
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget,
    QComboBox, QSpinBox, QTabWidget, QGroupBox,
    QApplication, QMessageBox, QDialog, QCheckBox,
    QAbstractItemView, QFrame, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

# Add the gui directory to the path for relative imports
sys.path.insert(0, str(Path(__file__).parent))

# Import extracted components
from widgets.status_indicator import StatusIndicator
from widgets.monitoring_window import MonitoringResultsWindow
from widgets.address_table import AddressTableWidget
from diagnostics.advanced_diagnostics import AdvancedDiagnostics
from diagnostics.diagnostics_dialogs import DiagnosticsDialogs
from monitoring.monitoring_manager import MonitoringManager
from network.network_diagnostics import NetworkDiagnosticsDialog

from core.modbus_client import ModbusClient
from app_paths import resource_path, app_data_dir

__version__ = "1.1.0"

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


class ModbusGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.modbus = None
        self.connection_history = []
        self.results_window = None
        
        # Connection parameters
        self.target_ip = "127.0.0.1"
        self.target_port = 502
        self.target_unit_id = 1

        # Initialize extracted components
        self.advanced_diagnostics = AdvancedDiagnostics()
        self.diagnostics_dialogs = DiagnosticsDialogs(self)
        self.monitoring_manager = MonitoringManager(self)
        self.network_diagnostics = NetworkDiagnosticsDialog(self)
        
        self._updating_monitoring_table = False
        self._updating_tag_table = False
        self._modbus_busy = False
        self._active_ranges = []
        self.monitoring_active = False
        self._write_poll_in_progress = False
        self.tag_address_one_based = False
        
        self.monitoring_timer = QTimer(self)
        self.monitoring_timer.timeout.connect(self._update_monitored_data)
        self.write_poll_timer = QTimer(self)
        self.write_poll_timer.timeout.connect(self._update_write_tag_values)

        self._setup_window()
        self._setup_menu()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()
        self.diagnostics_dialogs.setup_diagnostics_widgets()  # Initialize diagnostics widgets early
        self._load_settings()
        
    def convert_to_protocol_address(self, user_address, operation_type=None, is_one_based=False):
        """Convert user-entered address to a 0-based Modbus protocol offset.
        
        Args:
            user_address: The address entered by the user
            operation_type: The type of operation (coils, discrete_inputs, input_registers, holding_registers)
            is_one_based: If True, use 1-based (datasheet) addressing; if False, use 0-based (protocol)
            
        Returns:
            The protocol offset to use in Modbus communication
            
        Raises:
            ValueError: If the converted address is negative
        """
        if is_one_based:
            protocol_offset = user_address - 1
        else:  # 0-based
            protocol_offset = user_address

        if protocol_offset < 0:
            raise ValueError(f"Invalid address: {user_address} converts to negative protocol offset {protocol_offset}")
        
        return protocol_offset

    def _setup_window(self):
        """Setup main window properties."""
        self.setWindowTitle("ModbusLens - Professional Modbus TCP Client")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1000, 700)

        # Set application icon if available
        icon_path = resource_path("assets", "icon.ico")
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
        theme_label = view_menu.addAction("Light Theme (fixed)")
        theme_label.setEnabled(False)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction("Connection Settings", self._show_connection_settings)
        tools_menu.addAction("Connection Profiles", self._manage_profiles)
        tools_menu.addAction("Data Templates", self._manage_templates)
        tools_menu.addAction("Scripting Console", self._show_scripting_console)
        
        # Diagnostics menu
        diagnostics_menu = menubar.addMenu("&Diagnostics")
        diagnostics_menu.addAction("Network Discovery & Diagnostics", self._network_diagnostics)
        diagnostics_menu.addSeparator()
        diagnostics_menu.addAction("Results Log", self._show_diagnostics_results)
        diagnostics_menu.addAction("Communication Log", self._show_diagnostics_logs)
        diagnostics_menu.addAction("Raw Data", self._show_diagnostics_raw_data)
        diagnostics_menu.addSeparator()
        diagnostics_menu.addAction("Clear All Logs", self._clear_diagnostics_logs)

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

        # Top section: Connection and status (fixed height)
        self._setup_connection_section(main_layout)
        
        # Add stretch to allow proper resizing
        main_layout.addStretch(0)

        # Operations section (expands to fill available space)
        self._setup_operations_section(main_layout)

    def _setup_connection_section(self, parent_layout):
        """Setup compact connection bar."""
        connection_frame = QFrame()
        connection_frame.setObjectName("connectionBar")
        connection_frame.setStyleSheet("""
            QFrame#connectionBar {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
            }
        """)
        connection_frame.setFixedHeight(50)

        main_layout = QHBoxLayout(connection_frame)
        main_layout.setContentsMargins(15, 5, 15, 5)
        main_layout.setSpacing(15)

        # 1. Status Section (Left)
        self.status_indicator = StatusIndicator()
        main_layout.addWidget(self.status_indicator)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet("color: #E0E0E0;")
        main_layout.addWidget(sep)

        # 2. Connection Info Label
        self.connection_info_label = QLabel()
        self.connection_info_label.setStyleSheet("color: #444444; font-weight: 500; font-size: 12px;")
        self._update_connection_info()
        main_layout.addWidget(self.connection_info_label)
        
        main_layout.addStretch()

        # 3. Control Buttons
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.setFixedSize(90, 30)
        self.settings_btn.setStyleSheet(self._get_button_style(small=True))
        self.settings_btn.clicked.connect(self._show_connection_settings)
        main_layout.addWidget(self.settings_btn)

        self.connect_btn = QPushButton("Connect") 
        self.connect_btn.setFixedSize(90, 30)
        self.connect_btn.setStyleSheet(self._get_button_style(small=True))
        main_layout.addWidget(self.connect_btn) 
 
        self.disconnect_btn = QPushButton("Disconnect") 
        self.disconnect_btn.setFixedSize(90, 30)
        self.disconnect_btn.setStyleSheet(self._get_button_style(small=True))
        self.disconnect_btn.setEnabled(False) 
        main_layout.addWidget(self.disconnect_btn) 

        parent_layout.addWidget(connection_frame)

    def _update_connection_info(self):
        """Update the connection info label text."""
        if hasattr(self, 'connection_info_label'):
            self.connection_info_label.setText(f"{self.target_ip}:{self.target_port} (Unit {self.target_unit_id})")

    def _setup_operations_section(self, parent_layout):
        """Setup operations section with full height for address tables."""
        # Tab widget for operations
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #CCCCCC;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background-color: #F5F5F5;
                color: #333333;
                padding: 8px 16px;
                border: 1px solid #CCCCCC;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #333333;
                border-bottom: 1px solid #FFFFFF;
            }
            QTabBar::tab:hover {
                background-color: #E8E8E8;
            }
        """)

        # Address Table tab (ModScan-like interface)
        self._setup_address_table_tab()

        # Monitoring tab
        self._setup_monitoring_tab()
        
        # Connect tab change signal for interlock
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        parent_layout.addWidget(self.tab_widget)
        parent_layout.setStretchFactor(self.tab_widget, 1)  # Make tab widget expand

    def _setup_address_table_tab(self):
        """Setup Address Table tab with ModScan-like interface."""
        # Create the address table widget
        self.address_table_widget = AddressTableWidget(self)
        self.tab_widget.addTab(self.address_table_widget, "Address Table")

    def _setup_monitoring_tab(self):
        """Setup monitoring tab with real-time data display."""
        monitor_widget = QWidget()
        layout = QVBoxLayout(monitor_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Control buttons section
        control_group = QGroupBox("Monitoring Controls")
        control_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #222222;
                border: 1px solid #CCCCCC;
                                margin-top: 1ex;
                background-color: #F8F8F8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
        """)
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(10)
        control_layout.setContentsMargins(15, 15, 15, 15)

        # First row: Monitoring buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)

        self.tag_start_monitoring_btn = QPushButton("Start Monitoring")
        self.tag_start_monitoring_btn.setStyleSheet(self._get_button_style())
        self.tag_start_monitoring_btn.setEnabled(False)  # Initially disabled until connection
        self.tag_start_monitoring_btn.setMinimumWidth(120)
        buttons_layout.addWidget(self.tag_start_monitoring_btn)

        self.tag_stop_monitoring_btn = QPushButton("Stop Monitoring")
        self.tag_stop_monitoring_btn.setStyleSheet(self._get_button_style())
        self.tag_stop_monitoring_btn.setEnabled(False)
        self.tag_stop_monitoring_btn.setMinimumWidth(120)
        buttons_layout.addWidget(self.tag_stop_monitoring_btn)

        self.open_results_btn = QPushButton("Open Results Window")
        self.open_results_btn.setStyleSheet(self._get_button_style())
        self.open_results_btn.setMinimumWidth(140)
        buttons_layout.addWidget(self.open_results_btn)

        # Add stretch to push interval controls to the right
        buttons_layout.addStretch()

        # Interval controls
        interval_label = QLabel("Interval (ms):")
        interval_label.setStyleSheet("color: #333333; font-weight: normal;")
        buttons_layout.addWidget(interval_label)

        self.tag_monitoring_interval = QSpinBox()
        self.tag_monitoring_interval.setRange(100, 10000)
        self.tag_monitoring_interval.setValue(1000)
        self.tag_monitoring_interval.setStyleSheet(self._get_input_style())
        self.tag_monitoring_interval.setMinimumWidth(80)
        buttons_layout.addWidget(self.tag_monitoring_interval)

        self.tag_offset_checkbox = QCheckBox("1-Based Addressing")
        self.tag_offset_checkbox.setToolTip("When enabled, tag address 1 is sent as protocol offset 0")
        self.tag_offset_checkbox.setEnabled(False)
        self.tag_offset_checkbox.toggled.connect(self._on_tag_address_mode_changed)
        buttons_layout.addWidget(self.tag_offset_checkbox)

        control_layout.addLayout(buttons_layout)
        layout.addWidget(control_group)

        # Tag manager table (Excel-style)
        tag_group = QGroupBox("Tags")
        tag_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #222222;
                border: 1px solid #CCCCCC;
                                margin-top: 1ex;
                background-color: #F8F8F8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
        """)
        tag_layout = QVBoxLayout(tag_group)
        tag_layout.setSpacing(10)
        tag_layout.setContentsMargins(15, 25, 15, 15)  # Extra top margin for title

        self.monitoring_tag_table = QTableWidget() 
        self.monitoring_tag_table.setColumnCount(7) 
        self.monitoring_tag_table.setHorizontalHeaderLabels(["Tag Name", "Mode", "Type", "Address", "Count", "Format", "Comment"]) 
        self.monitoring_tag_table.horizontalHeader().setStretchLastSection(True) 
        self.monitoring_tag_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.monitoring_tag_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.monitoring_tag_table.setMinimumHeight(200)  # Ensure minimum height
        self.monitoring_tag_table.setMaximumHeight(16777215)  # Remove maximum height constraint
        
        # Ensure proper scrolling
        self.monitoring_tag_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.monitoring_tag_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.monitoring_tag_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.monitoring_tag_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel) 
        self.monitoring_tag_table.setStyleSheet(""" 
            QTableWidget { 
                background-color: #FFFFFF; 
                color: #000000;
                border: 1px solid #CCCCCC;
                            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #007ACC;
                color: #FFFFFF;
            }
            QTableWidget::item:selected:!active {
                background-color: #B3D7FF;
                color: #000000;
            }
        """)
        tag_layout.addWidget(self.monitoring_tag_table)
        tag_layout.setStretchFactor(self.monitoring_tag_table, 1)  # Make table expand

        first_row_layout = QHBoxLayout()
        first_row_layout.setSpacing(10)
        first_row_layout.setContentsMargins(0, 10, 0, 5)
        
        self.add_tag_btn = QPushButton("Add Tag")
        self.add_tag_btn.setStyleSheet(self._get_button_style())
        self.add_tag_btn.setMinimumWidth(100)
        first_row_layout.addWidget(self.add_tag_btn)

        self.remove_tag_btn = QPushButton("Remove Selected Tag")
        self.remove_tag_btn.setStyleSheet(self._get_button_style())
        self.remove_tag_btn.setEnabled(False)
        self.remove_tag_btn.setMinimumWidth(150)
        first_row_layout.addWidget(self.remove_tag_btn)

        self.remove_all_tags_btn = QPushButton("Remove All Tags")
        self.remove_all_tags_btn.setStyleSheet(self._get_button_style())
        self.remove_all_tags_btn.setEnabled(False)
        self.remove_all_tags_btn.setMinimumWidth(120)
        first_row_layout.addWidget(self.remove_all_tags_btn)

        first_row_layout.addStretch()

        csv_row_layout = QHBoxLayout()
        csv_row_layout.setSpacing(10)
        csv_row_layout.setContentsMargins(0, 5, 0, 10)
        
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.setStyleSheet(self._get_button_style())
        self.export_csv_btn.setMinimumWidth(100)
        csv_row_layout.addWidget(self.export_csv_btn)

        self.import_csv_btn = QPushButton("Import CSV")
        self.import_csv_btn.setStyleSheet(self._get_button_style())
        self.import_csv_btn.setMinimumWidth(100)
        csv_row_layout.addWidget(self.import_csv_btn)

        csv_row_layout.addStretch()

        tag_buttons_layout = QVBoxLayout()
        tag_buttons_layout.addLayout(first_row_layout)
        tag_buttons_layout.addLayout(csv_row_layout)
        tag_buttons_layout.addStretch()

        tag_layout.addLayout(tag_buttons_layout)
        layout.addWidget(tag_group)

        self.monitoring_tag_table.itemSelectionChanged.connect(self._update_tag_buttons_state)
        self.add_tag_btn.clicked.connect(self._add_monitoring_tag)
        self.remove_tag_btn.clicked.connect(self._remove_monitoring_tag)
        self.remove_all_tags_btn.clicked.connect(self._remove_all_monitoring_tags)
        
        # Connect CSV management buttons
        self.export_csv_btn.clicked.connect(self._export_tags_csv)
        self.import_csv_btn.clicked.connect(self._import_tags_csv)

        self.tab_widget.addTab(monitor_widget, "Tags")

    def _show_diagnostics_results(self):
        """Show diagnostics dialog with results data."""
        self.diagnostics_dialogs.show_diagnostics_results()

    def _show_diagnostics_logs(self):
        """Show diagnostics dialog with communication logs."""
        self.diagnostics_dialogs.show_diagnostics_logs()

    def _show_diagnostics_raw_data(self):
        """Show diagnostics dialog with raw data."""
        self.diagnostics_dialogs.show_diagnostics_raw_data(self.advanced_diagnostics)

    def _clear_diagnostics_logs(self):
        """Clear all diagnostics data."""
        self.diagnostics_dialogs.clear_all_diagnostics_logs()
        self._log("Diagnostics logs cleared")
        if hasattr(self, 'diagnostics_results_table'):
            self.diagnostics_results_table.setRowCount(0)
        self._log("All diagnostics data cleared")

    def _setup_status_bar(self):
        """Setup status bar with additional information."""
        self.status_bar = self.statusBar()

        self.connection_status = QLabel("Not Connected")
        self.status_bar.addWidget(self.connection_status)

        version = QApplication.applicationVersion()
        self.status_bar.addPermanentWidget(QLabel(f"ModbusLens v{version}"))

    def _get_input_style(self):
        """Get consistent input widget style."""
        return """
            QSpinBox, QLineEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                                padding: 5px;
            }
            QSpinBox:focus, QLineEdit:focus {
                border-color: #007ACC;
            }
        """

    def _get_button_style(self, color=None, small=False):
        """Get professional button style (gray theme)."""
        font_size = "11px" if small else "12px"
        padding = "4px 8px" if small else "8px 16px"
        
        return f"""
            QPushButton {{
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #CCCCCC;
                                padding: {padding};
                font-weight: 500;
                font-size: {font_size};
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: #E8E8E8;
                border-color: #BBBBBB;
            }}
            QPushButton:pressed {{
                background-color: #DDDDDD;
                border-color: #AAAAAA;
            }}
            QPushButton:disabled {{
                background-color: #F8F8F8;
                color: #999999;
                border-color: #EEEEEE;
            }}
        """

    def _create_monitoring_tag_widget(self, widget_type, value=None): 
        if widget_type == "lineedit": 
            w = QLineEdit() 
            w.setText(value or "") 
            w.setStyleSheet(self._get_input_style()) 
            return w 
        if widget_type == "mode_combo":
            w = QComboBox()
            w.addItems(["Read", "Write"])
            if value:
                w.setCurrentText(value)
            return w
        if widget_type == "type_combo": 
            w = QComboBox() 
            w.addItems(["Coil", "Discrete Input", "Holding Register", "Input Register"]) 
            if value: 
                w.setCurrentText(value) 
            return w 
        if widget_type == "format_combo":
            w = QComboBox()
            w.addItems(["Bool", "U16", "S16", "U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP", "Hex"])
            w.setCurrentText(value or "U16")
            return w
        if widget_type == "spinbox": 
            w = QSpinBox() 
            maximum = 65536 if getattr(self, "tag_address_one_based", False) else 65535
            w.setRange(1, maximum)
            w.setValue(value if value is not None else 1)
            w.setStyleSheet(self._get_input_style()) 
            return w 
        return None 
 
    def _add_monitoring_tag(self, tag_name="", mode="Read", tag_type="Coil", address=1, count=1, value_format=None, comment=""): 
        row = self.monitoring_tag_table.rowCount() 
        self.monitoring_tag_table.insertRow(row) 

        if value_format is None:
            value_format = "Bool" if tag_type in ("Coil", "Discrete Input") else "U16"
 
        self.monitoring_tag_table.setCellWidget(row, 0, self._create_monitoring_tag_widget("lineedit", tag_name)) 
        self.monitoring_tag_table.setCellWidget(row, 1, self._create_monitoring_tag_widget("mode_combo", mode)) 
        type_widget = self._create_monitoring_tag_widget("type_combo", tag_type)
        self.monitoring_tag_table.setCellWidget(row, 2, type_widget) 
 
        address_widget = self._create_monitoring_tag_widget("spinbox", address) 
        self.monitoring_tag_table.setCellWidget(row, 3, address_widget) 

        count_widget = self._create_monitoring_tag_widget("spinbox", count) 
        count_widget.setRange(1, 125) 
        self.monitoring_tag_table.setCellWidget(row, 4, count_widget) 

        format_widget = self._create_monitoring_tag_widget("format_combo", value_format)
        self.monitoring_tag_table.setCellWidget(row, 5, format_widget)
        self.monitoring_tag_table.setCellWidget(row, 6, self._create_monitoring_tag_widget("lineedit", comment)) 

        # Keep "count" valid for 32-bit formats (U32/S32/F32 require even register count).
        if hasattr(format_widget, "currentTextChanged"):
            format_widget.currentTextChanged.connect(self._on_monitoring_tag_format_changed)
        if hasattr(count_widget, "valueChanged"):
            count_widget.valueChanged.connect(self._on_monitoring_tag_count_changed)
        if hasattr(address_widget, "valueChanged"):
            address_widget.valueChanged.connect(self._on_monitoring_tag_address_or_type_changed)
        if hasattr(type_widget, "currentTextChanged"):
            type_widget.currentTextChanged.connect(self._on_monitoring_tag_address_or_type_changed)

        self._coerce_monitoring_tag_count(row)
        self._ensure_unique_monitoring_tag_address(row)

    def _on_tag_address_mode_changed(self, checked):
        """Toggle Tags between user-facing 1-based and protocol 0-based address input."""
        self.tag_address_one_based = bool(checked)
        maximum = 65536 if self.tag_address_one_based else 65535

        try:
            self._updating_tag_table = True
            for row in range(self.monitoring_tag_table.rowCount()):
                address_widget = self.monitoring_tag_table.cellWidget(row, 3)
                if not address_widget or not hasattr(address_widget, "setRange"):
                    continue
                current = address_widget.value()
                address_widget.setRange(1, maximum)
                if current < 1:
                    address_widget.setValue(1)
        finally:
            self._updating_tag_table = False

        self._log(f"Tag address mode: {'1-based' if self.tag_address_one_based else '0-based'}")

    def _tag_user_address_to_offset(self, tag):
        """Convert a tag's user-facing address to the 0-based Modbus protocol offset."""
        user_address = int(tag["address"])
        offset = user_address - 1 if self.tag_address_one_based else user_address
        if offset < 0:
            raise ValueError(f"address {user_address} converts to negative protocol offset {offset}")
        if offset > 65535:
            raise ValueError(f"address {user_address} converts to protocol offset {offset} above 65535")
        return offset

    def _find_monitoring_tag_row(self, widget, column):
        for row in range(self.monitoring_tag_table.rowCount()):
            if self.monitoring_tag_table.cellWidget(row, column) is widget:
                return row
        return None

    def _on_monitoring_tag_format_changed(self, _value=None):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 5)
        if row is None:
            return
        self._coerce_monitoring_tag_count(row)

    def _on_monitoring_tag_count_changed(self, _value=None):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 4)
        if row is None:
            return
        self._coerce_monitoring_tag_count(row)

    def _on_monitoring_tag_address_or_type_changed(self, _value=None):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 3)
        if row is None:
            row = self._find_monitoring_tag_row(sender, 2)
        if row is None:
            return
        self._coerce_monitoring_tag_count(row)
        self._ensure_unique_monitoring_tag_address(row)

    def _coerce_monitoring_tag_count(self, row):
        type_widget = self.monitoring_tag_table.cellWidget(row, 2)
        count_widget = self.monitoring_tag_table.cellWidget(row, 4)
        format_widget = self.monitoring_tag_table.cellWidget(row, 5)
        if not (type_widget and count_widget and format_widget):
            return

        tag_type = type_widget.currentText() if hasattr(type_widget, "currentText") else ""
        value_format = (format_widget.currentText() if hasattr(format_widget, "currentText") else "U16").strip().upper()

        wants_32 = tag_type in ("Holding Register", "Input Register") and value_format in (
            "U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP"
        )
        try:
            self._updating_tag_table = True
            if wants_32:
                # 32-bit values use 2 registers each.
                count_widget.setSingleStep(2)
                count_widget.setMaximum(124)
                if count_widget.value() < 2:
                    count_widget.setValue(2)
                elif count_widget.value() % 2 != 0:
                    count_widget.setValue(count_widget.value() + 1)
            else:
                count_widget.setSingleStep(1)
                count_widget.setMaximum(125)
        finally:
            self._updating_tag_table = False

    def _ensure_unique_monitoring_tag_address(self, row):
        type_widget = self.monitoring_tag_table.cellWidget(row, 2)
        address_widget = self.monitoring_tag_table.cellWidget(row, 3)
        count_widget = self.monitoring_tag_table.cellWidget(row, 4)
        if not (type_widget and address_widget and count_widget):
            return

        tag_type = type_widget.currentText() if hasattr(type_widget, "currentText") else ""
        address = int(address_widget.value()) if hasattr(address_widget, "value") else None
        if address is None:
            return

        used = set()
        for other_row in range(self.monitoring_tag_table.rowCount()):
            if other_row == row:
                continue
            other_type = self.monitoring_tag_table.cellWidget(other_row, 2)
            other_addr = self.monitoring_tag_table.cellWidget(other_row, 3)
            if not (other_type and other_addr):
                continue
            if other_type.currentText() != tag_type:
                continue
            used.add(int(other_addr.value()))

        if address not in used:
            return

        # Duplicate start address: advance to next free address in this memory space.
        next_addr = address
        while next_addr in used and next_addr < 65535:
            next_addr += 1

        if next_addr in used:
            QMessageBox.critical(self, "Duplicate Address", f"No free address available for {tag_type}.")
            return

        try:
            self._updating_tag_table = True
            address_widget.setValue(next_addr)
        finally:
            self._updating_tag_table = False

        self._log(f"Duplicate {tag_type} address {address} detected; moved to next free address {next_addr}.")

    def _remove_monitoring_tag(self):
        selected_rows = sorted(self._get_selected_tag_rows(), reverse=True)
        for row in selected_rows:
            self.monitoring_tag_table.removeRow(row)
        self._update_tag_buttons_state()

    def _remove_all_monitoring_tags(self):
        """Remove all tags from the monitoring table."""
        reply = QMessageBox.question(
            self,
            "Remove All Tags",
            "Are you sure you want to remove all tags?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.monitoring_tag_table.setRowCount(0)
            self._update_tag_buttons_state()
            self._log("All tags removed")

    def _update_tag_buttons_state(self):
        selected = bool(self._get_selected_tag_rows())
        has_tags = self.monitoring_tag_table.rowCount() > 0
        self.remove_tag_btn.setEnabled(selected)
        self.remove_all_tags_btn.setEnabled(has_tags)

    def _get_selected_tag_rows(self):
        selected_rows = {index.row() for index in self.monitoring_tag_table.selectedIndexes()}
        current_row = self.monitoring_tag_table.currentRow()
        if current_row >= 0:
            selected_rows.add(current_row)
        return selected_rows

    def _connect_signals(self):
        """Connect all UI signals to their handlers."""
        # Connection signals
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)

        # Monitoring tab signals (keep existing monitoring functionality)
        if hasattr(self, 'tag_start_monitoring_btn'):
            self.tag_start_monitoring_btn.clicked.connect(self._start_monitoring)
        if hasattr(self, 'tag_stop_monitoring_btn'):
            self.tag_stop_monitoring_btn.clicked.connect(self._stop_monitoring)
        if hasattr(self, 'open_results_btn'):
            self.open_results_btn.clicked.connect(self._show_results_window)
        if hasattr(self, 'monitoring_table'):
            self.monitoring_table.itemChanged.connect(self._on_monitoring_table_item_changed)
        if hasattr(self, 'monitoring_tag_table'):
            self.monitoring_tag_table.itemChanged.connect(self._on_monitoring_table_item_changed)

        # Note: Read/Write operation signals removed - now handled in unified Modbus Address tab
        # Note: Data type change signals removed - now handled in unified Modbus Address tab

    def _show_connection_settings(self):
        """Show the connection settings dialog."""
        dialog = ConnectionSettingsDialog(self, self.connection_history, self.target_ip, self.target_port, self.target_unit_id)
        if dialog.exec() == QDialog.Accepted:
            vals = dialog.get_values()
            self.target_ip = vals['ip']
            self.target_port = vals['port']
            self.target_unit_id = vals['unit']
            self.connection_history = vals['history']
            self._update_connection_info()
            self._save_settings()

    def _on_monitoring_table_item_changed(self, item):
        # Cache manual edits to the "Write Value" column so polling never overwrites user input.
        if self._updating_monitoring_table or item is None:
            return
        if item.column() != 5:
            return

        table = item.tableWidget()
        if table is None:
            return

        row = item.row()
        tag_name = self._table_item_text(table, row, 0).strip()
        mode = self._table_item_text(table, row, 1).strip()
        data_type = self._table_item_text(table, row, 2).strip()
        address = self._table_item_text(table, row, 3).strip()
        if not tag_name or not data_type or not address or mode != "Write":
            return

        self.monitoring_manager.update_write_value_cache((tag_name, data_type, address), item.text())

    def _connect(self):
        """Connect to Modbus server."""
        try:
            ip, port, unit_id = self.target_ip, self.target_port, self.target_unit_id

            self.status_indicator.set_connection_info(f"Connecting to {ip}:{port}...")
            self.status_indicator.set_status("connecting")
            self._set_connection_controls(connected=False, connecting=True)

            self.modbus = ModbusClient(ip, port, unit_id)

            if self.modbus.connect():
                conn_info = f"{ip}:{port} (Unit {unit_id})"
                self.status_indicator.set_connection_info(conn_info)
                self.status_indicator.set_status("connected")
                self.connection_status.setText(f"Connected: {conn_info}")
                self._set_connection_controls(connected=True)

                # Add to connection history
                connection_string = f"{ip}:{port}:{unit_id}"
                if connection_string in self.connection_history:
                    self.connection_history.remove(connection_string)
                
                self.connection_history.insert(0, connection_string)
                self.connection_history = self.connection_history[:10]
                self._save_settings()

                self._log(f"Connected to Modbus server at {ip}:{port} (Unit ID: {unit_id})")
            else:
                self.status_indicator.set_status("error")
                self.status_indicator.set_connection_info("Connection failed")
                self._set_connection_controls(connected=False)
                self._log("Failed to connect to Modbus server")
                # Show connection failure dialog
                self._show_connection_error_dialog(ip, port, unit_id, "Connection failed")

        except Exception as e:
            self.status_indicator.set_status("error")
            self.status_indicator.set_connection_info("Error encountered")
            self._set_connection_controls(connected=False)
            self._log(f"Connection error: {e}")
            # Show connection error dialog
            self._show_connection_error_dialog(ip, port, unit_id, str(e))

    def _disconnect(self):
        """Disconnect from Modbus server."""
        if self.modbus:
            self.modbus.disconnect()
            self.modbus = None

        self.status_indicator.set_status("disconnected")
        self.status_indicator.set_connection_info("")
        self.connection_status.setText("Not Connected")

        self._set_connection_controls(connected=False)

        if self.monitoring_active:
            self._stop_monitoring()

        self._log("Disconnected from Modbus server")

    def _show_connection_error_dialog(self, ip, port, unit_id, error_message):
        """Show connection error dialog with detailed information."""
        try:
            # Create error dialog
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Connection Failed")
            dialog.setText(f"Failed to connect to Modbus server")
            dialog.setInformativeText(f"""
<strong>Connection Details:</strong><br>
IP Address: {ip}<br>
Port: {port}<br>
Unit ID: {unit_id}<br><br>
<strong>Error:</strong> {error_message}<br><br>
<strong>Possible Solutions:</strong><br>
• Check if the Modbus server is running<br>
• Verify the IP address and port number<br>
• Ensure network connectivity to the device<br>
• Check if the Unit ID matches the device configuration<br>
• Verify firewall settings are not blocking the connection
            """)
            dialog.setStandardButtons(QMessageBox.Ok)
            dialog.setStyleSheet("""
                QMessageBox {
                    background-color: #FFFFFF;
                }
                QMessageBox QTextEdit {
                    background-color: #F8F9FA;
                    border: 1px solid #CCCCCC;
                    padding: 8px;
                }
            """)
            dialog.exec()
        except Exception as e:
            self._log(f"Error showing connection dialog: {e}")

    def _get_monitoring_tags(self):
        """Get all monitoring tags from the table."""
        return self.monitoring_manager.get_monitoring_tags()

    def _export_tags_csv(self):
        """Export tags to CSV file."""
        try:
            from PySide6.QtWidgets import QFileDialog
            
            row_count = self.monitoring_tag_table.rowCount()
            if row_count == 0:
                QMessageBox.warning(self, "No Tags", "No tags to export. Please add tags first.")
                return
            
            tags = self._get_monitoring_tags()
            if not tags:
                QMessageBox.warning(self, "No Tags", f"No tags to export. Table has {row_count} rows but no valid tags found. Please add tags with valid addresses or names.")
                return
            
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Tags CSV", f"tags_{time.strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)"
            )
            
            if not file_path:
                return
            
            # Export to CSV
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['Tag Name', 'Mode', 'Type', 'Address', 'Count', 'Format', 'Comment']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for tag in tags:
                    writer.writerow({
                        'Tag Name': tag['name'],
                        'Mode': tag['mode'],
                        'Type': tag['type'],
                        'Address': tag['address'],
                        'Count': tag['count'],
                        'Format': tag['format'],
                        'Comment': tag['comment']
                    })
            
            self._log(f"Exported {len(tags)} tags to {file_path}")
            QMessageBox.information(self, "Export Complete", f"Successfully exported {len(tags)} tags to CSV file!")
            
        except Exception as e:
            self._log(f"Error exporting CSV: {e}")
            QMessageBox.critical(self, "Error", f"Failed to export tags: {e}")

    def _import_tags_csv(self):
        """Import tags from CSV file."""
        try:
            from PySide6.QtWidgets import QFileDialog
            
            # Get file path
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Import Tags CSV", "", "CSV Files (*.csv)"
            )
            
            if not file_path:
                return
            
            # Read CSV file
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                
                # Validate CSV structure
                required_fields = ['Tag Name', 'Mode', 'Type', 'Address', 'Count', 'Format', 'Comment']
                if not all(field in reader.fieldnames for field in required_fields):
                    QMessageBox.warning(self, "Invalid CSV", 
                        "CSV file must contain columns: Tag Name, Mode, Type, Address, Count, Format, Comment")
                    return
                
                # Clear existing tags
                self.monitoring_tag_table.setRowCount(0)
                
                # Import tags
                imported_count = 0
                for row in reader:
                    try:
                        self._add_monitoring_tag(
                            tag_name=row.get('Tag Name', '').strip(),
                            mode=row.get('Mode', 'Read').strip(),
                            tag_type=row.get('Type', 'Coil').strip(),
                            address=int(row.get('Address', 0)),
                            count=int(row.get('Count', 1)),
                            value_format=row.get('Format', 'U16').strip(),
                            comment=row.get('Comment', '').strip()
                        )
                        imported_count += 1
                    except (ValueError, KeyError) as e:
                        self._log(f"Skipping invalid row: {e}")
                        continue
                
                self._log(f"Imported {imported_count} tags from {file_path}")
                QMessageBox.information(self, "Import Complete", 
                    f"Successfully imported {imported_count} tags from CSV file!")
            
        except Exception as e:
            self._log(f"Error importing CSV: {e}")
            QMessageBox.critical(self, "Error", f"Failed to import tags: {e}")

    def _set_connection_controls(self, connected: bool, connecting: bool = False):
        """Update UI control states based on connection status."""
        if connecting:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            self.settings_btn.setEnabled(False)
            # STRICT: Always disable monitoring checkbox during connection

            # During connection attempt, disable all monitoring entry points
            if hasattr(self, 'address_table_widget'):
                self.address_table_widget.monitoring_checkbox.setEnabled(False)
            
            if hasattr(self, 'tag_start_monitoring_btn'):
                self.tag_start_monitoring_btn.setEnabled(False)
            
            return
        

        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        self.settings_btn.setEnabled(not connected)
        
        # STRICT: Disable all functions when there is no Modbus connection

        # Update Address Table controls
        if hasattr(self, 'address_table_widget'):
            self.address_table_widget.function_combo.setEnabled(connected)
            self.address_table_widget.address_input.setEnabled(connected)
            self.address_table_widget.count_input.setEnabled(connected)
            self.address_table_widget.offset_checkbox.setEnabled(connected)
            self.address_table_widget.create_btn.setEnabled(connected)
            self.address_table_widget.update_monitoring_availability()
        
        # Also disable tag monitoring controls when not connected

        # Update Tag monitoring controls
        if hasattr(self, 'tag_start_monitoring_btn'):
            self.tag_start_monitoring_btn.setEnabled(connected)
            
        if hasattr(self, 'tag_stop_monitoring_btn'):
            self.tag_stop_monitoring_btn.setEnabled(False)
            # Ensure stop is disabled if we are not connected
            if not connected:
                self.tag_stop_monitoring_btn.setEnabled(False)

        if hasattr(self, 'tag_offset_checkbox'):
            # Only allow editing address mode if not currently monitoring
            self.tag_offset_checkbox.setEnabled(connected and not self.monitoring_active)

    def on_tab_changed(self, index):
        """Handle tab change to implement smart monitoring interlock."""
        try:
            # Get the current tab text
            tab_text = self.tab_widget.tabText(index)
            self._log(f"Switched to tab: {tab_text}")
            
            # Smart interlock: auto-disable instead of stopping all monitoring
            if tab_text == "Address Table":
                # Auto-stop tag monitoring when going to address table
                if hasattr(self, 'tag_start_monitoring_btn'):
                    if not self.tag_start_monitoring_btn.isEnabled():
                        # Tag monitoring is active, stop it
                        self.tag_stop_monitoring_btn.click()
                
                # Enable address table monitoring controls if connected
                if hasattr(self, 'address_table_widget'):
                    self.address_table_widget.update_monitoring_availability()
            
            elif tab_text == "Monitoring":
                # Auto-disable live monitoring when going to tags tab
                if hasattr(self, 'address_table_widget'):
                    if self.address_table_widget.monitoring_checkbox.isChecked():
                        # Uncheck to disable live monitoring
                        self.address_table_widget.monitoring_checkbox.setChecked(False)
                    self.address_table_widget.update_monitoring_availability()
                
                # Enable tag monitoring controls
                if hasattr(self, 'tag_start_monitoring_btn'):
                    if hasattr(self, 'modbus') and self.modbus and self.modbus.is_connected():
                        self.tag_start_monitoring_btn.setEnabled(True)
                
        except Exception as e:
            self._log(f"Error in tab change: {e}", "ERROR")
    
    def stop_all_monitoring(self):
        """Stop all monitoring systems."""
        try:
            # Stop address table monitoring
            if hasattr(self, 'address_table_widget'):
                if self.address_table_widget.monitoring_checkbox.isChecked():
                    self.address_table_widget.monitoring_checkbox.setChecked(False)
                self.address_table_widget.monitoring_checkbox.setEnabled(False)
                self.address_table_widget.interval_input.setEnabled(False)
                self.address_table_widget.stop_monitoring()
            
            # Stop tag monitoring
            if hasattr(self, 'tag_start_monitoring_btn'):
                if self.tag_start_monitoring_btn.isEnabled():
                    self.tag_start_monitoring_btn.click()
            
            # Stop main monitoring
            if self.monitoring_active:
                self._stop_monitoring()
                
        except Exception as e:
            self.log(f"Error stopping all monitoring: {e}", "ERROR")
    
    def _write_results_window_selected(self):
        """Write selected rows from the detached results window."""
        if not self._check_connection():
            return

        if self.results_window is None:
            QMessageBox.warning(self, "Results Window Closed", "Open the results window before writing tag values.")
            return

        selected_rows = self.results_window.selected_write_rows()
        if not selected_rows:
            QMessageBox.warning(self, "No Result Selected", "Please select at least one write-mode result row.")
            return

        invalid_rows = self.results_window.invalid_write_rows()
        selected_row_numbers = {row["row"] + 1 for row in selected_rows}
        selected_invalid_rows = [row for row in invalid_rows if row[0] in selected_row_numbers]
        if selected_invalid_rows:
            details = "\n".join(
                f"Row {row_number} ({tag_name}): {message}"
                for row_number, tag_name, message in selected_invalid_rows[:8]
            )
            QMessageBox.warning(self, "Invalid Write Value", details)
            return

        tags_by_key = {self._tag_key(tag): tag for tag in self._get_monitoring_tags()}
        wrote_any = False
        was_monitoring = self.monitoring_active
        monitor_interval = self.tag_monitoring_interval.value()

        if was_monitoring:
            self.monitoring_timer.stop()
            self._log("Safety interlock: monitoring paused while write request is active")

        try:
            for result_row in selected_rows:
                tag = tags_by_key.get(self._result_key(result_row))
                if not tag:
                    continue

                if tag["mode"] != "Write":
                    self._log(f"Skipped {tag['name']}: result row is Read mode")
                    continue

                tag = dict(tag)
                tag["write_value"] = result_row["write_value"]

                try:
                    self._validate_tag_request(tag, "write")
                    if not self._begin_modbus_operation(tag, "write"):
                        self._log(f"Safety interlock: skipped write for {tag['name']} because the range is busy")
                        continue

                    try:
                        success, written_value, write_status = self._write_tag(tag)
                    finally:
                        self._end_modbus_operation(tag, "write")

                    if success:
                        wrote_any = True
                        timestamp = time.strftime("%H:%M:%S")
                        self._add_monitoring_row(
                            tag["name"], tag["mode"], tag["type"], tag["address"], "", str(written_value),
                            tag["comment"], timestamp
                        )
                        self._log(f"{write_status}: {tag['name']} at {tag['address']} = {written_value}")
                    else:
                        self._log(f"{write_status}: {tag['name']}")
                except ValueError as e:
                    self._log(f"Invalid write value for {tag['name']}: {e}")
                except Exception as e:
                    self._log(f"Write error for {tag['name']}: {e}")
        finally:
            if was_monitoring and self.monitoring_active:
                self.monitoring_timer.start(monitor_interval)
                self._log("Safety interlock: monitoring resumed after write request")

        if wrote_any:
            self.tab_widget.setCurrentWidget(self.monitoring_tag_table)

    def _tag_key(self, tag):
        return (tag["name"], tag["type"], str(tag["address"]))

    def _result_key(self, result_row):
        return (result_row["name"], result_row["type"], str(result_row["address"]))

    def _validate_result_write_value(self, result_row):
        tags_by_key = {self._tag_key(tag): tag for tag in self._get_monitoring_tags()}
        tag = tags_by_key.get(self._result_key(result_row))
        if not tag:
            return False, "matching tag configuration was not found"
        if tag["mode"] != "Write":
            return False, "tag is not in Write mode"
        if tag["type"] in ("Discrete Input", "Input Register"):
            return False, f"{tag['type']} is read-only"

        write_value = str(result_row.get("write_value", "")).strip()
        if not write_value:
            return False, "write value is empty"

        try:
            if tag["type"] == "Coil":
                values = self._parse_coil_values(write_value)
                self._fit_write_values(values, tag["count"])
            else:
                value_format = (tag.get("format") or "U16").strip().upper()
                self._parse_register_values(write_value, value_format, tag["count"])
        except ValueError as e:
            return False, str(e)
        return True, ""

    def _write_tag(self, tag):
        if tag["type"] in ("Discrete Input", "Input Register"):
            raise ValueError(f"{tag['type']} is read-only")

        if not tag["write_value"]:
            raise ValueError("write value is empty")

        if tag["type"] == "Coil":
            values = self._parse_coil_values(tag["write_value"])
            protocol_offset = self._tag_user_address_to_offset(tag)
            if tag["count"] == 1:
                desired_value = values[0]
                current_value = self._read_tag_value(tag)
                if current_value == desired_value:
                    return True, desired_value, "Skipped write; value already matches"

                if not self.modbus.write_coil(protocol_offset, desired_value):
                    return False, desired_value, "Write failed"

                verified_value = self._read_tag_value(tag)
                if verified_value != desired_value:
                    return False, desired_value, f"Write verification failed; read back {verified_value}"
                return True, desired_value, "Write verified"

            values = self._fit_write_values(values, tag["count"])
            current_values = self._read_tag_value(tag)
            if current_values == values:
                return True, values, "Skipped write; values already match"

            if not self.modbus.write_coils(protocol_offset, values):
                return False, values, "Write failed"

            verified_values = self._read_tag_value(tag)
            if verified_values != values:
                return False, values, f"Write verification failed; read back {verified_values}"
            return True, values, "Write verified"

        value_format = (tag.get("format") or "U16").strip().upper()
        desired_registers = self._parse_register_values(tag["write_value"], value_format, tag["count"])
        protocol_offset = self._tag_user_address_to_offset(tag)

        current_registers = self._read_tag_value(tag)
        if tag["count"] == 1 and not isinstance(current_registers, list):
            current_registers = [current_registers]
        if isinstance(current_registers, list):
            current_registers = current_registers[: tag["count"]]

        if current_registers == desired_registers:
            return True, self._format_written_value(tag, desired_registers), "Skipped write; value already matches"

        if tag["count"] == 1:
            if not self.modbus.write_register(protocol_offset, desired_registers[0]):
                return False, self._format_written_value(tag, desired_registers), "Write failed"
        else:
            if not self.modbus.write_registers(protocol_offset, desired_registers):
                return False, self._format_written_value(tag, desired_registers), "Write failed"

        verified_registers = self._read_tag_value(tag)
        if tag["count"] == 1 and not isinstance(verified_registers, list):
            verified_registers = [verified_registers]
        if isinstance(verified_registers, list):
            verified_registers = verified_registers[: tag["count"]]

        if verified_registers != desired_registers:
            return (
                False,
                self._format_written_value(tag, desired_registers),
                f"Write verification failed; read back {self._format_written_value(tag, verified_registers)}",
            )
        return True, self._format_written_value(tag, desired_registers), "Write verified"

    def _read_tag_value(self, tag, is_one_based=None):
        try:
            protocol_offset = self._tag_user_address_to_offset(tag)
        except ValueError as e:
            raise ValueError(f"Address error for tag {tag['name']}: {e}")
        
        if tag["type"] == "Coil":
            value = self.modbus.read_coils(protocol_offset, tag["count"])
        elif tag["type"] == "Holding Register":
            value = self.modbus.read_registers(protocol_offset, tag["count"])
        else:
            raise ValueError(f"{tag['type']} cannot be written")

        if value is None:
            raise ValueError("pre-read failed; write blocked")

        value = value[:tag["count"]] if isinstance(value, list) else value
        if tag["count"] == 1 and isinstance(value, list):
            return value[0]
        return value

    def _parse_coil_values(self, value_text):
        values = []
        for raw_value in value_text.split(","):
            value = raw_value.strip().lower()
            if not value:
                continue
            if value in ("1", "true", "on"):
                values.append(True)
            elif value in ("0", "false", "off"):
                values.append(False)
            else:
                raise ValueError("coil values must be 0/1, true/false, or on/off")
        if not values:
            raise ValueError("write value is empty")
        return values

    def _parse_register_values(self, value_text, value_format, register_count):
        raw = [part.strip() for part in str(value_text).split(",") if part.strip()]
        if not raw:
            raise ValueError("write value is empty")

        value_format = (value_format or "U16").strip().upper()
        swap_words = value_format.endswith("_SWAP")
        base_format = value_format.replace("_SWAP", "")

        word_width = 2 if base_format in ("U32", "S32", "F32") else 1
        if register_count % word_width != 0:
            raise ValueError(f"{value_format} requires count to be a multiple of {word_width}")

        expected_values = register_count // word_width
        if len(raw) != expected_values:
            raise ValueError(f"expected {expected_values} value(s), got {len(raw)}")

        registers = []
        for token in raw:
            if base_format == "HEX":
                raw_hex = token[2:] if token.lower().startswith("0x") else token
                if not raw_hex or any(ch not in "0123456789abcdefABCDEF" for ch in raw_hex):
                    raise ValueError("HEX values must use hexadecimal digits only")
                num = int(raw_hex, 16)
                if num < 0 or num > 0xFFFF:
                    raise ValueError("HEX out of range (0x0000..0xFFFF)")
                registers.append(num)
                continue
            if base_format == "S16":
                num = int(token, 10)
                if num < -32768 or num > 32767:
                    raise ValueError("S16 out of range (-32768..32767)")
                registers.append(num & 0xFFFF)
                continue
            if base_format == "U16":
                num = int(token, 10)
                if num < 0 or num > 65535:
                    raise ValueError("U16 out of range (0..65535)")
                registers.append(num & 0xFFFF)
                continue
            if base_format == "BOOL":
                lowered = token.lower()
                if lowered in ("1", "true", "on"):
                    registers.append(1)
                elif lowered in ("0", "false", "off"):
                    registers.append(0)
                else:
                    raise ValueError("BOOL values must be 0/1, true/false, or on/off")
                continue

            if base_format in ("U32", "S32", "F32"):
                if base_format == "F32":
                    num = float(token)
                    if not math.isfinite(num):
                        raise ValueError("F32 must be a finite number")
                    u32 = int.from_bytes(struct.pack(">f", num), "big", signed=False)
                else:
                    num = int(token, 10)
                    if base_format == "U32":
                        if num < 0 or num > 0xFFFFFFFF:
                            raise ValueError("U32 out of range (0..4294967295)")
                        u32 = num
                    else:
                        if num < -2147483648 or num > 2147483647:
                            raise ValueError("S32 out of range (-2147483648..2147483647)")
                        u32 = num & 0xFFFFFFFF

                hi = (u32 >> 16) & 0xFFFF
                lo = u32 & 0xFFFF
                if swap_words:
                    registers.append(lo)
                    registers.append(hi)
                else:
                    registers.append(hi)
                    registers.append(lo)
                continue

            raise ValueError(f"unsupported data format: {value_format}")

        if len(registers) != register_count:
            raise ValueError(f"expected {register_count} register value(s), got {len(registers)}")
        return registers

    def _format_written_value(self, tag, registers):
        if tag["type"] in ("Coil", "Discrete Input"):
            if isinstance(registers, list):
                if len(registers) == 1:
                    return bool(registers[0])
                return [bool(v) for v in registers]
            return bool(registers)

        fmt = (tag.get("format") or "U16").strip().upper()
        try:
            decoded = self._decode_register_values(registers if isinstance(registers, list) else [registers], fmt)
        except Exception:
            decoded = registers
        if isinstance(decoded, list) and len(decoded) == 1:
            return decoded[0]
        return decoded

    def _fit_write_values(self, values, count):
        if len(values) != count:
            raise ValueError(f"expected {count} value(s), got {len(values)}")
        return values

    def _validate_tag_request(self, tag, operation):
        user_address = int(tag["address"])
        maximum_address = 65536 if self.tag_address_one_based else 65535
        if user_address < 1 or user_address > maximum_address:
            raise ValueError(f"address must be between 1 and {maximum_address}")

        start_offset = self._tag_user_address_to_offset(tag)
        if tag["count"] < 1:
            raise ValueError("count must be at least 1")
        if start_offset + tag["count"] - 1 > 65535:
            raise ValueError("address range exceeds 65535")

        if operation == "read":
            if tag["type"] in ("Holding Register", "Input Register") and tag["count"] > 125:
                raise ValueError("register reads are limited to 125 values")
            if tag["type"] in ("Coil", "Discrete Input") and tag["count"] > 2000:
                raise ValueError("coil/input reads are limited to 2000 values")
            if tag["type"] in ("Holding Register", "Input Register"):
                value_format = (tag.get("format") or "U16").strip().upper()
                if value_format in ("U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP") and (tag["count"] % 2 != 0):
                    raise ValueError(f"{value_format} requires an even count")
            return

        if tag["type"] in ("Discrete Input", "Input Register"):
            raise ValueError(f"{tag['type']} is read-only")
        if tag["type"] == "Coil" and tag["count"] > 1968:
            raise ValueError("multiple-coil writes are limited to 1968 values")
        if tag["type"] == "Holding Register" and tag["count"] > 123:
            raise ValueError("multiple-register writes are limited to 123 values")
        if tag["type"] == "Holding Register":
            value_format = (tag.get("format") or "U16").strip().upper()
            if value_format in ("U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP") and (tag["count"] % 2 != 0):
                raise ValueError(f"{value_format} requires an even count")

    def _begin_modbus_operation(self, tag, operation):
        request_range = self._operation_range(tag, operation)
        if self._modbus_busy:
            return False
        for active_range in self._active_ranges:
            if self._ranges_overlap(request_range, active_range):
                return False

        self._modbus_busy = True
        self._active_ranges.append(request_range)
        return True

    def _end_modbus_operation(self, tag, operation):
        request_range = self._operation_range(tag, operation)
        self._active_ranges = [
            active_range for active_range in self._active_ranges
            if active_range != request_range
        ]
        self._modbus_busy = False

    def _operation_range(self, tag, operation):
        start_offset = self._tag_user_address_to_offset(tag)
        return {
            "operation": operation,
            "space": tag["type"],
            "start": start_offset,
            "end": start_offset + tag["count"] - 1,
            "tag": tag["name"],
        }

    def _ranges_overlap(self, left, right):
        if left["space"] != right["space"]:
            return False
        return left["start"] <= right["end"] and right["start"] <= left["end"]

    def _start_monitoring(self):
        """Start real-time data monitoring with interlock."""
        if not self._check_connection():
            return

        # Auto-turn off address table monitoring when starting tag monitoring
        if hasattr(self, 'address_table_widget'):
            if self.address_table_widget.monitoring_checkbox.isChecked():
                # Address table monitoring is active, turn it off
                self.address_table_widget.monitoring_checkbox.setChecked(False)
                self._log("Auto-turned off address table monitoring")

        tags = self._get_monitoring_tags()
        read_tags = [tag for tag in tags if tag["mode"] == "Read"]
        write_tags = [tag for tag in tags if tag["mode"] == "Write"]
        if not read_tags and not write_tags:
            QMessageBox.warning(self, "No Tags", "Please add at least one read or write tag before starting monitoring.")
            return

        duplicate_messages = self._find_duplicate_tag_addresses(tags)
        if duplicate_messages:
            QMessageBox.critical(
                self,
                "Duplicate Addresses",
                "Duplicate start addresses were found. Please change them before monitoring:\n\n"
                + "\n".join(duplicate_messages[:12]),
            )
            return

        overlap_messages = self._find_overlapping_tag_ranges(tags)
        if overlap_messages:
            QMessageBox.warning(
                self,
                "Overlapping Ranges",
                "Overlapping address ranges were found. Monitoring can continue, but values may be confusing:\n\n"
                + "\n".join(overlap_messages[:12]),
            )

        self._clear_monitoring_results()
        self.monitoring_active = True
        
        # Initialize monitoring manager failure tracking
        self.monitoring_manager._monitoring_failure_count = 0
        self.monitoring_manager._monitoring_poll_in_progress = False
        self.monitoring_manager._write_poll_in_progress = False
        
        interval = self.tag_monitoring_interval.value() if hasattr(self, 'tag_monitoring_interval') else 1000
        self._restart_monitoring_timers(interval)

        # Update correct button references for Tags tab
        if hasattr(self, 'tag_start_monitoring_btn'):
            self.tag_start_monitoring_btn.setEnabled(False)
        if hasattr(self, 'tag_stop_monitoring_btn'):
            self.tag_stop_monitoring_btn.setEnabled(True)
        self._set_tag_editor_enabled(False)

        self._log(f"Started monitoring with {interval}ms interval")

    def _find_duplicate_tag_addresses(self, tags):
        seen = {}
        duplicates = []
        for tag in tags:
            key = (tag["type"], self._tag_user_address_to_offset(tag))
            if key in seen:
                other = seen[key]
                duplicates.append(
                    f"{tag['type']} address {tag['address']}: {other['name']} and {tag['name']}"
                )
            else:
                seen[key] = tag
        return duplicates

    def _find_overlapping_tag_ranges(self, tags):
        overlaps = []
        by_type = {}
        for tag in tags:
            by_type.setdefault(tag["type"], []).append(tag)

        for tag_type, group in by_type.items():
            ranges = []
            for tag in group:
                start = self._tag_user_address_to_offset(tag)
                end = start + int(tag["count"]) - 1
                ranges.append((start, end, tag["name"]))

            ranges.sort(key=lambda x: (x[0], x[1]))
            for i in range(len(ranges)):
                a_start, a_end, a_name = ranges[i]
                for j in range(i + 1, len(ranges)):
                    b_start, b_end, b_name = ranges[j]
                    if b_start > a_end:
                        break
                    if a_start == b_start:
                        # Exact start duplicates are handled separately.
                        continue
                    overlaps.append(f"{tag_type}: {a_name} [{a_start}..{a_end}] overlaps {b_name} [{b_start}..{b_end}]")
        return overlaps

    def _stop_monitoring(self):
        """Stop real-time data monitoring."""
        self.monitoring_active = False
        self.monitoring_timer.stop()
        self.write_poll_timer.stop()
        
        # Reset monitoring manager state
        self.monitoring_manager._monitoring_poll_in_progress = False
        self.monitoring_manager._write_poll_in_progress = False

        # Clear monitoring results when stopping
        self.monitoring_manager.clear_monitoring_results()

        # Update correct button references for Tags tab
        if hasattr(self, 'tag_start_monitoring_btn'):
            self.tag_start_monitoring_btn.setEnabled(True)
        if hasattr(self, 'tag_stop_monitoring_btn'):
            self.tag_stop_monitoring_btn.setEnabled(False)
        self._set_tag_editor_enabled(True)

        self._log("Stopped monitoring")

    def _set_tag_editor_enabled(self, enabled):
        self.monitoring_tag_table.setEnabled(enabled)
        self.add_tag_btn.setEnabled(enabled)
        self.remove_tag_btn.setEnabled(enabled and bool(self._get_selected_tag_rows()))
        if hasattr(self, 'tag_offset_checkbox'):
            self.tag_offset_checkbox.setEnabled(enabled)

    def _restart_monitoring_timers(self, read_interval):
        tags = self._get_monitoring_tags()
        if any(tag["mode"] == "Read" for tag in tags):
            self.monitoring_timer.start(read_interval)
        if any(tag["mode"] == "Write" for tag in tags):
            self.write_poll_timer.start(1000)

    def _clear_monitoring_results(self):
        """Clear monitoring results table."""
        self.monitoring_manager.clear_monitoring_results()
        
        # Check if diagnostics results table exists
        if hasattr(self, 'diagnostics_results_table'):
            self.diagnostics_results_table.setRowCount(0)
        if self.results_window is not None:
            self._sync_results_window()

    def _show_results_window(self):
        """Open the detached monitoring results table."""
        if self.results_window is None:
            self.results_window = MonitoringResultsWindow(self)

        self._sync_results_window()
        self.results_window.show()
        if self.results_window.isMinimized():
            self.results_window.showNormal()
        self.results_window.raise_()
        self.results_window.activateWindow()

    def _sync_results_window(self):
        """Copy configured tags and current values into the detached results window."""
        if self.results_window is None:
            return

        window_values = self.results_window.current_values()
        current_values = self._current_result_values()
        self.results_window.clear()
        for tag in self._get_monitoring_tags():
            # Skip default placeholder names
            name = tag.get("name", "")
            if name.startswith("Tag_") and name.split("_")[-1].isdigit():
                continue
            
            key = self._tag_key(tag)
            values = current_values.get(key, {})
            window_row = window_values.get(key, {})
            self.results_window.update_row(
                tag["name"],
                tag["mode"],
                tag["type"],
                tag["address"],
                values.get("read_value", window_row.get("read_value", "")),
                values.get("write_value", window_row.get("write_value", "")),
                tag["comment"],
                values.get("timestamp", window_row.get("timestamp", "")),
            )

    def _current_result_values(self):
        """Get current values from monitoring results."""
        return self.monitoring_manager.get_current_result_values()

    def _table_item_text(self, table, row, column):
        item = table.item(row, column)
        return item.text() if item else ""

    def _update_monitored_data(self):
        """Update monitored data in the table."""
        self.monitoring_manager.update_monitored_data()

    def _update_write_tag_values(self):
        """Poll write-mode tags at a fixed 1000ms interval for their current device values."""
        if not self.modbus or not self.monitoring_active:
            return
        if self._write_poll_in_progress:
            self._log("Safety interlock: skipped write-tag poll because previous poll is still running")
            return
        if self._modbus_busy:
            return

        tags = [tag for tag in self._get_monitoring_tags() if tag["mode"] == "Write"]
        if not tags:
            return

        self._write_poll_in_progress = True
        self.write_poll_timer.stop()
        poll_failed = False
        timestamp = time.strftime("%H:%M:%S")
        try:
            for tag in tags:
                try:
                    self._validate_tag_request(tag, "write")
                    if not self._begin_modbus_operation(tag, "read"):
                        self._log(f"Safety interlock: skipped write-tag read for {tag['name']} because the range is busy")
                        continue

                    try:
                        value = self._read_tag_value(tag)
                    finally:
                        self._end_modbus_operation(tag, "read")

                    display_value = self._format_monitoring_value(tag, value)
                    self._add_monitoring_row(
                        tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                        tag["comment"], timestamp
                    )
                except Exception as e:
                    poll_failed = True
                    self._log(f"Write-tag value polling error for {tag['name']}: {e}")
                    break

            if poll_failed:
                self._monitoring_failure_count += 1
                if self._monitoring_failure_count >= self._monitoring_max_failures:
                    self._log(
                        f"Monitoring stopped after {self._monitoring_failure_count} consecutive failed poll(s)"
                    )
                    self._stop_monitoring()
                    QMessageBox.warning(
                        self,
                        "Monitoring Stopped",
                        "Monitoring was stopped after repeated Modbus failures. Check write tag type, address, unit ID, and server status.",
                    )
            else:
                self._monitoring_failure_count = 0
        finally:
            self._write_poll_in_progress = False
            if self.monitoring_active:
                self.write_poll_timer.start(1000)

    def _read_tag_for_monitoring(self, tag):
        protocol_offset = self._tag_user_address_to_offset(tag)
        if tag["type"] == "Coil":
            return self.modbus.read_coils(protocol_offset, tag["count"])
        if tag["type"] == "Discrete Input":
            return self.modbus.read_discrete_inputs(protocol_offset, tag["count"])
        if tag["type"] == "Holding Register":
            return self.modbus.read_registers(protocol_offset, tag["count"])
        return self.modbus.read_input_registers(protocol_offset, tag["count"])

    def _format_monitoring_value(self, tag, value):
        if value is None:
            return "ERROR"

        if tag["type"] in ("Coil", "Discrete Input"):
            if isinstance(value, list):
                visible_values = value[: tag["count"]]
                if tag["count"] == 1 and visible_values:
                    return str(bool(visible_values[0]))
                return ", ".join(str(bool(v)) for v in visible_values)
            return str(bool(value))

        if not isinstance(value, list):
            return str(value)

        registers = value[: tag["count"]]
        value_format = (tag.get("format") or "U16").strip().upper()
        try:
            decoded = self._decode_register_values(registers, value_format)
        except Exception:
            decoded = registers

        if isinstance(decoded, list):
            if len(decoded) == 1:
                return str(decoded[0])
            return ", ".join(str(v) for v in decoded)
        return str(decoded)

    def _decode_register_values(self, registers, value_format):
        value_format = (value_format or "U16").strip().upper()

        if value_format in ("HEX",):
            return [f"0x{int(r) & 0xFFFF:04X}" for r in registers]

        if value_format in ("S16",):
            values = []
            for r in registers:
                r = int(r) & 0xFFFF
                values.append(r - 0x10000 if r & 0x8000 else r)
            return values

        if value_format in ("U16", "BOOL"):
            if value_format == "BOOL":
                values = []
                for r in registers:
                    raw = int(r)
                    if raw not in (0, 1):
                        raise ValueError(f"BOOL register value must be 0 or 1, got {raw}")
                    values.append(bool(raw))
                return values
            return [int(r) & 0xFFFF for r in registers]

        if value_format in ("U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP"):
            if len(registers) % 2 != 0:
                raise ValueError("32-bit format requires even register count")
            values = []
            swap_words = value_format.endswith("_SWAP")
            base_format = value_format.replace("_SWAP", "")
            for i in range(0, len(registers), 2):
                first = int(registers[i]) & 0xFFFF
                second = int(registers[i + 1]) & 0xFFFF
                if swap_words:
                    lo, hi = first, second
                else:
                    hi, lo = first, second
                u32 = (hi << 16) | lo
                if base_format == "U32":
                    values.append(u32)
                elif base_format == "S32":
                    values.append(u32 - 0x100000000 if u32 & 0x80000000 else u32)
                else:
                    values.append(struct.unpack(">f", u32.to_bytes(4, "big"))[0])
            return values

        return [int(r) & 0xFFFF for r in registers]

    def _add_monitoring_row(self, tag_name, mode, data_type, address, read_value, write_value, comment, timestamp):
        """Add or update a tag row in the monitoring results table."""
        # Delegate to the monitoring manager
        self.monitoring_manager.add_monitoring_row(tag_name, mode, data_type, address, read_value, write_value, comment, timestamp)

    def _check_connection(self):
        """Check if connected to Modbus server."""
        if not self.modbus or not self.modbus.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to a Modbus server first.")
            return False
        return True

    def _log(self, message):
        """Add message to log output."""
        timestamp = time.strftime("[%H:%M:%S]")
        formatted_message = f"{timestamp} {message}"
        
        # Update main log output if it exists
        if hasattr(self, 'log_output'):
            current_text = self.log_output.toPlainText()
            if current_text:
                current_text += "\n"
            current_text += formatted_message
            self.log_output.setPlainText(current_text)
            
            # Auto scroll to bottom
            scrollbar = self.log_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        
        # Update diagnostics log if it exists
        if hasattr(self, 'diagnostics_log_output'):
            current_text = self.diagnostics_log_output.toPlainText()
            if current_text:
                current_text += "\n"
            current_text += formatted_message
            self.diagnostics_log_output.setPlainText(current_text)
            
            # Auto scroll to bottom
            scrollbar = self.diagnostics_log_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _display_raw_data(self, title, data):
        """Display raw data in the data output tab."""
        timestamp = time.strftime('[%H:%M:%S]')
        
        # Update statistics
        self.advanced_diagnostics.update_request_stats(
            success=data is not None, 
            function_code=self._get_function_code_from_title(title),
            exception_code=self._get_exception_code_from_error() if data is None else None
        )
        
        if self.advanced_diagnostics.advanced_diagnostics:
            # Create detailed diagnostics information
            detailed_info = self.advanced_diagnostics.create_advanced_diagnostics(title, data, self.modbus)
            formatted_data = f"{timestamp} {title}:\n{data}\n\n--- Advanced Diagnostics ---\n{detailed_info}"
        else:
            formatted_data = f"{timestamp} {title}:\n{data}"
        
        # Update main data output if it exists
        if hasattr(self, 'data_output'):
            current_text = self.data_output.toPlainText()
            if current_text:
                current_text += "\n\n"
            current_text += formatted_data
            self.data_output.setPlainText(current_text)
            
            # Auto scroll to bottom
            scrollbar = self.data_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        
        # Update diagnostics raw data if it exists
        if hasattr(self, 'diagnostics_data_output'):
            current_text = self.diagnostics_data_output.toPlainText()
            if current_text:
                current_text += "\n\n"
            current_text += formatted_data
            self.diagnostics_data_output.setPlainText(current_text)
            
            # Auto scroll to bottom
            scrollbar = self.diagnostics_data_output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def _get_function_code_from_title(self, title):
        """Extract function code from title for statistics."""
        # Simple mapping based on title content
        if "Address[" in title or "Tag[" in title:
            return 0x03  # Default to Read Holding Registers
        return 0x01  # Default to Read Coils
    
    def _get_exception_code_from_error(self):
        """Extract exception code from modbus error."""
        if not self.modbus or not hasattr(self.modbus, 'last_error'):
            return None
        
        error = self.modbus.last_error.lower()
        if 'illegal function' in error:
            return 0x01
        elif 'illegal data address' in error or 'illegal address' in error:
            return 0x02
        elif 'illegal data value' in error:
            return 0x03
        elif 'server device failure' in error:
            return 0x04
        elif 'server device busy' in error:
            return 0x06
        return None

    def _load_settings(self):
        """Load user settings and preferences."""
        # Load connection history from a simple file
        try:
            history_file = app_data_dir() / "connection_history.txt"
            if history_file.exists():
                with open(history_file, 'r') as f:
                    self.connection_history = [line.strip() for line in f.readlines() if line.strip()][:10]
        except Exception:
            pass

    def _save_settings(self):
        """Save user settings and preferences."""
        try:
            config_dir = app_data_dir()
            config_dir.mkdir(parents=True, exist_ok=True)
            history_file = config_dir / "connection_history.txt"
            with open(history_file, 'w') as f:
                for connection in self.connection_history[:10]:  # Save last 10
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
        self._clear_monitoring_results()
        # Clear logs if they exist
        if hasattr(self, 'log_output'):
            self.log_output.clear()
        if hasattr(self, 'data_output'):
            self.data_output.clear()
        # Clear diagnostics logs if they exist
        if hasattr(self, 'diagnostics_log_output'):
            self.diagnostics_log_output.clear()
        if hasattr(self, 'diagnostics_data_output'):
            self.diagnostics_data_output.clear()
        self._log(" New session started")

    def _save_session(self):
        """Save current session."""
        QMessageBox.information(self, "Save Session", "Session saving will be implemented in the next update!")

    def _load_session(self):
        """Load a saved session."""
        QMessageBox.information(self, "Load Session", "Session loading will be implemented in the next update!")

    def _export_data(self):
        """Export monitoring data."""
        QMessageBox.information(self, "Export Data", "Data export will be implemented in the next update!")

    def _toggle_theme(self):
        """Toggle between light and dark themes."""
        QMessageBox.information(self, "Theme Toggle", "Theme switching will be implemented in the next update!")

    def _manage_profiles(self):
        """Manage connection profiles."""
        QMessageBox.information(self, "Connection Profiles", "Profile management will be implemented in the next update!")

    def _manage_templates(self):
        """Manage data templates."""
        QMessageBox.information(self, "Data Templates", "Template management will be implemented in the next update!")

    def _show_scripting_console(self):
        """Show scripting console."""
        QMessageBox.information(self, "Scripting Console", "Scripting console will be implemented in the next update!")

    def _network_diagnostics(self): 
        """Show network diagnostics.""" 
        self.network_diagnostics.show_diagnostics(self.target_ip, self.target_port, self.target_unit_id)

    def _show_documentation(self):
        """Show documentation."""
        QMessageBox.information(self, "Documentation", "Documentation viewer will be implemented in the next update!")

    def _show_about(self):
        """Show about dialog."""
        version = QApplication.applicationVersion()
        
        about_text = (
            f"<h3>ModbusLens v{version}</h3>"
            "<p><b>ModbusLens is free software</b> professional Modbus TCP client designed for engineers working with industrial automation systems.</p>"
            
            "<h4>Key Features</h4>"
            "<ul>"
            "<li>Modbus TCP read/write (coils, inputs, registers)</li>"
            "<li>Tag-based real-time monitoring</li>"
            "<li>Detached monitoring results window</li>"
            "<li>Network discovery & diagnostics (ARP + Modbus detection)</li>"
            "</ul>"
            
            "<h4>Upcoming Features</h4>"
            "<ul>"
            "<li>Modbus RTU support</li>"
            "<li>Multi-device management</li>"
            "<li>Data logging and export</li>"
            "<li>Advanced scripting and automation</li>"
            "<li>Graphical data visualization (charts, trends, live graphs)</li>"
            "</ul>"
            
            "<h4>Support</h4>"
            "<p>If you find this tool useful, you can support development:<br>"
            "<a href=\"https://buymeacoffee.com/craftparking\">Buy Me a Coffee</a></p>"
            
            "<h4>Links</h4>"
            "<p>GitHub: <a href=\"https://github.com/CraftParking/ModbusLens\">https://github.com/CraftParking/ModbusLens</a></p>"
            
            "<h4>License</h4>"
            "<p>License: Apache License 2.0</p>"
            
            "<p style='margin-top: 15px;'><i>Note: Verify behavior before use in critical industrial systems.</i></p>"
            "<hr>"
            "<p align='center' style='color: #666666;'>© 2026 ModbusLens | CraftParking</p>"
        )
        
        QMessageBox.about(self, "About ModbusLens", about_text)

    def closeEvent(self, event): 
        """Handle application close event.""" 
        if self.monitoring_active: 
            self._stop_monitoring() 
        if self.modbus: 
            self._disconnect() 
        self._save_settings() 
        event.accept() 
 

class SafetyWarningDialog(QDialog): 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Safety Warning")
        self.setModal(True)
        self.setMinimumWidth(680)

        # No close button. Also blocks the usual close shortcuts by ignoring closeEvent.
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("WARNING: Live Machine Risk")
        title.setWordWrap(True)
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #B00020;")
        layout.addWidget(title)

        body = QLabel(
            "This tool can READ and WRITE Modbus values. On live equipment, incorrect writes can cause unintended "
            "motion or process changes.\n\n"
            "Common risks:\n"
            "- Unexpected starts/stops or actuator movement\n"
            "- Changing speeds, setpoints, valves, or outputs\n"
            "- Bypassing interlocks/safety logic by writing the wrong coil/register\n"
            "- Equipment damage or unplanned downtime\n"
            "- Serious injury or death\n\n"
            "Use only if you understand the device register map and have authorization. Prefer testing on a "
            "simulator or isolated network. If you are not sure, exit now."
        )
        body.setWordWrap(True)
        body.setStyleSheet("color: #222222;")
        layout.addWidget(body)

        # Add "Don't show again" checkbox
        self.dont_show_again = QCheckBox("Don't show this warning again")
        self.dont_show_again.setStyleSheet("color: #222222;")
        layout.addWidget(self.dont_show_again)

        buttons = QHBoxLayout()
        buttons.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setStyleSheet(self._button_style(danger=True))
        exit_btn.clicked.connect(self.reject)
        buttons.addWidget(exit_btn)

        understand_btn = QPushButton("I Understand")
        understand_btn.setStyleSheet(self._button_style(primary=True))
        understand_btn.clicked.connect(self.accept)
        buttons.addWidget(understand_btn)

        layout.addLayout(buttons)

    def closeEvent(self, event):
        event.ignore()

    def should_show_again(self):
        """Check if the warning should be shown based on user preference."""
        from PySide6.QtCore import QSettings
        settings = QSettings("ModbusLens", "ModbusLens")
        return not settings.value("hide_safety_warning", False, type=bool)

    def save_preference(self):
        """Save the user's preference to not show the warning again."""
        if self.dont_show_again.isChecked():
            from PySide6.QtCore import QSettings
            settings = QSettings("ModbusLens", "ModbusLens")
            settings.setValue("hide_safety_warning", True)

    @staticmethod
    def _button_style(primary: bool = False, danger: bool = False) -> str:
        if danger:
            base = "#F44336"
            hover = "#E53935"
            text = "#FFFFFF"
        elif primary:
            base = "#007ACC"
            hover = "#0066AA"
            text = "#FFFFFF"
        else:
            base = "#E0E0E0"
            hover = "#D5D5D5"
            text = "#000000"

        return f"""
            QPushButton {{
                background-color: {base};
                color: {text};
                border: 1px solid #B0B0B0;
                                padding: 10px 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                background-color: {base};
            }}
            QPushButton:disabled {{
                background-color: #F0F0F0;
                color: #999999;
                border: 1px solid #C8C8C8;
            }}
        """


class ConnectionSettingsDialog(QDialog):
    """Dialog for advanced Modbus connection configuration."""
    def __init__(self, parent, history, ip, port, unit):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setMinimumWidth(450)
        self.history = history[:]
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # 1. Basic configuration
        basic_group = QGroupBox("Target Device")
        grid = QGridLayout(basic_group)
        grid.setSpacing(10)
        
        grid.addWidget(QLabel("IP Address:"), 0, 0)
        self.ip_input = QLineEdit(ip)
        self.ip_input.setStyleSheet(parent._get_input_style())
        grid.addWidget(self.ip_input, 0, 1)
        
        grid.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(port)
        self.port_input.setStyleSheet(parent._get_input_style())
        grid.addWidget(self.port_input, 1, 1)
        
        grid.addWidget(QLabel("Unit ID:"), 2, 0)
        self.unit_input = QSpinBox()
        self.unit_input.setRange(1, 247)
        self.unit_input.setValue(unit)
        self.unit_input.setStyleSheet(parent._get_input_style())
        grid.addWidget(self.unit_input, 2, 1)
        layout.addWidget(basic_group)
        
        # 2. Network selection
        iface_group = QGroupBox("Network Interface")
        iface_layout = QHBoxLayout(iface_group)
        self.iface_combo = QComboBox()
        self.iface_combo.setStyleSheet(parent._get_input_style())
        
        try:
            from network.network_diagnostics import get_network_interfaces
            interfaces = get_network_interfaces()
            for i in interfaces:
                self.iface_combo.addItem(i['display_name'], i['ipv4'])
        except:
            self.iface_combo.addItem("Default Interface", "127.0.0.1")
            
        self.iface_combo.currentTextChanged.connect(lambda t: self.ip_input.setText(self.iface_combo.currentData()))
        iface_layout.addWidget(self.iface_combo)
        layout.addWidget(iface_group)
        
        # 3. History
        hist_group = QGroupBox("Recent Connections")
        hist_layout = QHBoxLayout(hist_group)
        self.hist_combo = QComboBox()
        self.hist_combo.setStyleSheet(parent._get_input_style())
        self.hist_combo.addItems(self.history)
        self.hist_combo.currentTextChanged.connect(self._on_history_select)
        hist_layout.addWidget(self.hist_combo)
        layout.addWidget(hist_group)
        
        # Buttons
        btns = QHBoxLayout()
        btns.addStretch()
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.accept)
        btns.addWidget(save_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _on_history_select(self, text):
        if not text or ":" not in text:
            return
        parts = text.split(":")
        if len(parts) >= 3:
            self.ip_input.setText(parts[0])
            self.port_input.setValue(int(parts[1]))
            self.unit_input.setValue(int(parts[2]))

    def get_values(self):
        return {'ip': self.ip_input.text(), 'port': self.port_input.value(), 'unit': self.unit_input.value(), 'history': self.history}


def main(): 
    try: 
        # Check if QApplication already exists (e.g., in IDE environments) 
        app = QApplication.instance() 
        if app is None: 
            app = QApplication(sys.argv)

        app.setApplicationName("ModbusLens") 
        app.setApplicationVersion(__version__) 
        app.setOrganizationName("ModbusLens") 
 
        warning = SafetyWarningDialog()
        if warning.should_show_again():
            if warning.exec() != QDialog.Accepted:
                sys.exit(0)
            warning.save_preference()

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
