import sys
import logging
import math
import time
import socket
import struct
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QGroupBox, QGridLayout,
    QSplitter, QFrame, QComboBox, QSpinBox, QCheckBox, QProgressBar,
    QStatusBar, QMenuBar, QMenu, QTableWidget, QTableWidgetItem, QDialog,
    QHeaderView, QTabWidget, QScrollArea, QSystemTrayIcon, QAbstractItemView
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap, QPainter, QBrush

from app_paths import app_data_dir, resource_path
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
            intensity = (1 + 0.3 * math.sin(self._animation_angle / 180.0 * math.pi)) / 1.3
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


class MonitoringResultsWindow(QMainWindow):
    """Detached Excel-style view for live monitoring results."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Monitoring Results")
        self.resize(1100, 560)

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)

        actions_layout = QHBoxLayout()
        self.write_selected_btn = QPushButton("Write Selected")
        self.write_selected_btn.clicked.connect(parent._write_results_window_selected)
        actions_layout.addWidget(self.write_selected_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Tag Name", "Mode", "Type", "Address", "Read Value", "Write Value", "Comment", "Timestamp"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                color: #000000;
                gridline-color: #D0D0D0;
                border: 1px solid #CCCCCC;
            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 6px;
                font-weight: bold;
            }
        """)

        layout.addWidget(self.table)
        self.setCentralWidget(central_widget)

    def update_row(self, tag_name, mode, data_type, address, read_value="", write_value="", comment="", timestamp=""): 
        row = self._find_row(tag_name, data_type, address) 
        if row is None: 
            row = self.table.rowCount() 
            self.table.insertRow(row) 

        # If the user is actively typing in the Write Value cell, do not refresh the row.
        # Refreshing (setItem) cancels the editor and clears in-progress edits.
        if (
            self.table.state() == QAbstractItemView.EditingState
            and self.table.currentRow() == row
            and self.table.currentColumn() == 5
        ):
            return
 
        current_write_item = self.table.item(row, 5) 
        current_write_value = current_write_item.text() if current_write_item else "" 
        if current_write_value and not write_value: 
            write_value = current_write_value 

        current_read_item = self.table.item(row, 4)
        current_read_value = current_read_item.text() if current_read_item else ""
        if current_read_value and not read_value:
            read_value = current_read_value

        can_write = mode == "Write"
        values_by_column = {
            0: tag_name,
            1: mode,
            2: data_type,
            3: str(address),
            4: read_value,
            5: write_value,
            6: comment,
            7: timestamp,
        }

        for column in range(8):
            if column == 5 and can_write:
                # Don't overwrite user's typed value with empty polling updates.
                if not values_by_column[5] and self.table.item(row, 5) is not None:
                    existing_item = self.table.item(row, 5)
                    existing_item.setFlags(existing_item.flags() | Qt.ItemIsEditable)
                    continue

            item = QTableWidgetItem(values_by_column[column])
            if column != 5 or not can_write:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if column == 5 and not can_write:
                item.setBackground(QColor("#F0F0F0"))
                item.setForeground(QColor("#777777"))
            self.table.setItem(row, column, item)

    def clear(self):
        self.table.setRowCount(0)

    def current_values(self):
        values = {}
        for row in range(self.table.rowCount()):
            key = (self._item_text(row, 0), self._item_text(row, 2), self._item_text(row, 3))
            values[key] = {
                "read_value": self._item_text(row, 4),
                "write_value": self._item_text(row, 5),
                "timestamp": self._item_text(row, 7),
            }
        return values

    def selected_write_rows(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row not in rows:
            rows.append(current_row)

        selected = []
        for row in rows:
            mode = self._item_text(row, 1)
            if mode != "Write":
                continue
            selected.append({
                "name": self._item_text(row, 0),
                "mode": mode,
                "type": self._item_text(row, 2),
                "address": self._item_text(row, 3),
                "write_value": self._item_text(row, 5),
            })
        return selected

    def _item_text(self, row, column):
        item = self.table.item(row, column)
        return item.text().strip() if item else ""

    def _find_row(self, tag_name, data_type, address):
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            type_item = self.table.item(row, 2)
            address_item = self.table.item(row, 3)
            if (
                name_item and type_item and address_item
                and name_item.text() == tag_name
                and type_item.text() == data_type
                and address_item.text() == str(address)
            ):
                return row
        return None


class ModbusGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.modbus = None
        self.connection_history = []
        self.results_window = None
        self._monitoring_write_value_cache = {}
        self._updating_monitoring_table = False
        self._updating_tag_table = False
        self._modbus_busy = False
        self._active_ranges = []
        self.monitoring_active = False
        self._monitoring_poll_in_progress = False
        self._monitoring_failure_count = 0
        self._monitoring_max_failures = 3
        self._write_poll_in_progress = False
        self.monitoring_timer = QTimer(self)
        self.monitoring_timer.timeout.connect(self._update_monitored_data)
        self.write_poll_timer = QTimer(self)
        self.write_poll_timer.timeout.connect(self._update_write_tag_values)

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
                background-color: #F7F7F7;
                border: 1px solid #CCCCCC;
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
        status_label.setStyleSheet("color: #333333; font-weight: bold;")
        status_layout.addWidget(status_label)

        self.status_indicator = StatusIndicator()
        status_layout.addWidget(self.status_indicator)

        self.status_text = QLabel("Disconnected")
        self.status_text.setStyleSheet("color: #333333;")
        status_layout.addWidget(self.status_text)

        layout.addLayout(status_layout)

        # Connection inputs
        inputs_layout = QGridLayout()
        inputs_layout.setSpacing(10)

        # IP input
        ip_label = QLabel("IP Address:")
        ip_label.setStyleSheet("color: #333333;")
        inputs_layout.addWidget(ip_label, 0, 0)

        self.ip_input = QLineEdit("127.0.0.1")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.ip_input, 0, 1)

        # Port input
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #333333;")
        inputs_layout.addWidget(port_label, 1, 0)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(502)
        self.port_input.setStyleSheet("""
            QSpinBox {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.port_input, 1, 1)

        # Unit ID input
        unit_label = QLabel("Unit ID:")
        unit_label.setStyleSheet("color: #333333;")
        inputs_layout.addWidget(unit_label, 0, 2)

        self.unit_input = QSpinBox()
        self.unit_input.setRange(1, 247)
        self.unit_input.setValue(1)
        self.unit_input.setStyleSheet("""
            QSpinBox {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.unit_input, 0, 3)

        # Connection history
        history_label = QLabel("Recent:")
        history_label.setStyleSheet("color: #333333;")
        inputs_layout.addWidget(history_label, 1, 2)

        self.connection_history_combo = QComboBox()
        self.connection_history_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
        """)
        inputs_layout.addWidget(self.connection_history_combo, 1, 3)

        self.delete_history_btn = QPushButton("Delete History")
        self.delete_history_btn.setStyleSheet(self._get_button_style())
        inputs_layout.addWidget(self.delete_history_btn, 1, 4)

        layout.addLayout(inputs_layout)

        # Control buttons
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(10)

        self.connect_btn = QPushButton("Connect") 
        self.connect_btn.setStyleSheet(""" 
            QPushButton { 
                background-color: #E0E0E0; 
                color: #000000; 
                border: 1px solid #B0B0B0; 
                border-radius: 6px; 
                padding: 10px 20px; 
                font-weight: bold; 
                font-size: 12px; 
            } 
            QPushButton:hover { 
                background-color: #D5D5D5; 
            } 
            QPushButton:pressed { 
                background-color: #C0C0C0; 
            } 
            QPushButton:disabled {
                background-color: #F0F0F0;
                color: #999999;
                border: 1px solid #C8C8C8;
            }
        """) 
        buttons_layout.addWidget(self.connect_btn) 
 
        self.disconnect_btn = QPushButton("Disconnect") 
        self.disconnect_btn.setStyleSheet(""" 
            QPushButton { 
                background-color: #E0E0E0; 
                color: #000000; 
                border: 1px solid #B0B0B0; 
                border-radius: 6px; 
                padding: 10px 20px; 
                font-weight: bold; 
                font-size: 12px; 
            } 
            QPushButton:hover { 
                background-color: #D5D5D5; 
            } 
            QPushButton:pressed { 
                background-color: #C0C0C0; 
            } 
            QPushButton:disabled {
                background-color: #F0F0F0;
                color: #999999;
                border: 1px solid #C8C8C8;
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
                border: 1px solid #CCCCCC;
                background-color: #F7F7F7;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #E9E9E9;
                color: #333333;
                padding: 8px 16px;
                border: 1px solid #CCCCCC;
                border-bottom: none;
                border-radius: 8px 8px 0 0;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #007ACC;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #DADADA;
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
                color: #222222;
                border: 1px solid #CCCCCC;
                border-radius: 8px;
                margin-top: 1ex;
                background-color: #F8F8F8;
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

        self.tab_widget.addTab(read_widget, "Read")

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

        self.tab_widget.addTab(write_widget, "Write")

    def _setup_monitoring_tab(self):
        """Setup monitoring tab with real-time data display."""
        monitor_widget = QWidget()
        layout = QVBoxLayout(monitor_widget)

        # Control buttons
        control_layout = QHBoxLayout()

        self.start_monitoring_btn = QPushButton("Start Monitoring")
        self.start_monitoring_btn.setStyleSheet(self._get_button_style())
        control_layout.addWidget(self.start_monitoring_btn)

        self.stop_monitoring_btn = QPushButton("Stop Monitoring")
        self.stop_monitoring_btn.setStyleSheet(self._get_button_style())
        self.stop_monitoring_btn.setEnabled(False)
        control_layout.addWidget(self.stop_monitoring_btn)

        self.open_results_btn = QPushButton("Open Results Window")
        self.open_results_btn.setStyleSheet(self._get_button_style())
        control_layout.addWidget(self.open_results_btn)

        control_layout.addWidget(QLabel("Interval (ms):"))
        self.monitoring_interval = QSpinBox()
        self.monitoring_interval.setRange(100, 10000)
        self.monitoring_interval.setValue(1000)
        self.monitoring_interval.setStyleSheet(self._get_input_style())
        control_layout.addWidget(self.monitoring_interval)

        layout.addLayout(control_layout)

        # Tag manager table (Excel-style)
        tag_group = QGroupBox("Tags")
        tag_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #222222;
                border: 1px solid #CCCCCC;
                border-radius: 8px;
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

        self.monitoring_tag_table = QTableWidget() 
        self.monitoring_tag_table.setColumnCount(7) 
        self.monitoring_tag_table.setHorizontalHeaderLabels(["Tag Name", "Mode", "Type", "Address", "Count", "Format", "Comment"]) 
        self.monitoring_tag_table.horizontalHeader().setStretchLastSection(True) 
        self.monitoring_tag_table.setSelectionBehavior(QTableWidget.SelectRows) 
        self.monitoring_tag_table.setStyleSheet(""" 
            QTableWidget { 
                background-color: #FFFFFF; 
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 5px;
            }
        """)
        tag_layout.addWidget(self.monitoring_tag_table)

        tag_buttons_layout = QHBoxLayout()
        self.add_tag_btn = QPushButton("Add Tag")
        self.add_tag_btn.setStyleSheet(self._get_button_style())
        tag_buttons_layout.addWidget(self.add_tag_btn)

        self.remove_tag_btn = QPushButton("Remove Selected Tag")
        self.remove_tag_btn.setStyleSheet(self._get_button_style())
        self.remove_tag_btn.setEnabled(False)
        tag_buttons_layout.addWidget(self.remove_tag_btn)

        tag_layout.addLayout(tag_buttons_layout)
        layout.addWidget(tag_group)

        self.monitoring_tag_table.itemSelectionChanged.connect(self._update_tag_buttons_state)
        self.add_tag_btn.clicked.connect(self._add_monitoring_tag)
        self.remove_tag_btn.clicked.connect(self._remove_monitoring_tag)

        self._add_monitoring_tag()

        self.tab_widget.addTab(monitor_widget, "Tags")

    def _setup_bottom_section(self, splitter):
        """Setup bottom section with output and logs."""
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)

        # Output tabs
        self.output_tabs = QTabWidget()
        self.output_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #CCCCCC;
                background-color: #FFFFFF;
            }
            QTabBar::tab {
                background-color: #E9E9E9;
                color: #333333;
                padding: 5px 10px;
                border: 1px solid #CCCCCC;
            }
            QTabBar::tab:selected {
                background-color: #007ACC;
                color: white;
            }
        """)

        # Monitoring results
        self.monitoring_table = QTableWidget()
        self.monitoring_table.setColumnCount(8)
        self.monitoring_table.setHorizontalHeaderLabels([
            "Tag Name", "Mode", "Type", "Address", "Read Value", "Write Value", "Comment", "Timestamp"
        ])
        self.monitoring_table.setAlternatingRowColors(True)
        self.monitoring_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.monitoring_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.monitoring_table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
                gridline-color: #D0D0D0;
            }
            QHeaderView::section {
                background-color: #E9E9E9;
                color: #000000;
                border: 1px solid #CCCCCC;
                padding: 5px;
            }
        """)
        self.output_tabs.addTab(self.monitoring_table, "Results")

        # Log output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.output_tabs.addTab(self.log_output, "Logs")

        # Raw data output
        self.data_output = QTextEdit()
        self.data_output.setReadOnly(True)
        self.data_output.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        self.output_tabs.addTab(self.data_output, "Raw Data")

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
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
            QSpinBox:focus, QLineEdit:focus {
                border-color: #007ACC;
            }
        """

    def _get_button_style(self, color=None):
        """Get consistent button style."""
        return """
            QPushButton {
                background-color: #E0E0E0;
                color: #000000;
                border: 1px solid #B0B0B0;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #D5D5D5;
            }
            QPushButton:pressed {
                background-color: #C0C0C0;
            }
            QPushButton:disabled {
                background-color: #F0F0F0;
                color: #999999;
            }
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
            w.setRange(0, 65535) 
            w.setValue(value if value is not None else 0) 
            w.setStyleSheet(self._get_input_style()) 
            return w 
        return None 
 
    def _add_monitoring_tag(self, tag_name="", mode="Read", tag_type="Coil", address=0, count=1, value_format=None, comment=""): 
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

    def _update_tag_buttons_state(self):
        selected = bool(self._get_selected_tag_rows())
        self.remove_tag_btn.setEnabled(selected)

    def _get_selected_tag_rows(self):
        selected_rows = {index.row() for index in self.monitoring_tag_table.selectedIndexes()}
        current_row = self.monitoring_tag_table.currentRow()
        if current_row >= 0:
            selected_rows.add(current_row)
        return selected_rows

    def _get_monitoring_tags(self): 
        tags = [] 
        for row in range(self.monitoring_tag_table.rowCount()): 
            name_widget = self.monitoring_tag_table.cellWidget(row, 0) 
            mode_widget = self.monitoring_tag_table.cellWidget(row, 1) 
            type_widget = self.monitoring_tag_table.cellWidget(row, 2) 
            address_widget = self.monitoring_tag_table.cellWidget(row, 3) 
            count_widget = self.monitoring_tag_table.cellWidget(row, 4) 
            format_widget = self.monitoring_tag_table.cellWidget(row, 5)
            comment_widget = self.monitoring_tag_table.cellWidget(row, 6) 
 
            if not all((name_widget, mode_widget, type_widget, address_widget, count_widget, format_widget, comment_widget)): 
                continue 
 
            name = name_widget.text().strip() or f"Tag {row + 1}" 
            mode = mode_widget.currentText() 
            tag_type = type_widget.currentText() 
            address = address_widget.value() 
            count = count_widget.value() 
            value_format = format_widget.currentText() if hasattr(format_widget, "currentText") else "U16"
            comment = comment_widget.text().strip() 
            tags.append({ 
                "row": row, 
                "name": name, 
                "mode": mode, 
                "type": tag_type, 
                "address": address, 
                "count": count, 
                "format": value_format,
                "comment": comment, 
            }) 
 
        return tags 

    def _create_operation_button(self, text, color):
        """Create a styled operation button."""
        btn = QPushButton(text)
        btn.setStyleSheet(self._get_button_style(color))
        return btn

    def _connect_signals(self):
        """Connect all UI signals to their handlers."""
        # Connection signals
        self.connect_btn.clicked.connect(self._connect)
        self.disconnect_btn.clicked.connect(self._disconnect)
        self.connection_history_combo.currentTextChanged.connect(self._load_connection_from_history)
        self.delete_history_btn.clicked.connect(self._delete_selected_history)

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
        self.open_results_btn.clicked.connect(self._show_results_window)
        self.monitoring_table.itemChanged.connect(self._on_monitoring_table_item_changed)

    def _on_monitoring_table_item_changed(self, item):
        # Cache manual edits to the "Write Value" column so polling never overwrites user input.
        if self._updating_monitoring_table or item is None:
            return
        if item.column() != 5:
            return

        row = item.row()
        tag_name = self._table_item_text(self.monitoring_table, row, 0).strip()
        data_type = self._table_item_text(self.monitoring_table, row, 2).strip()
        address = self._table_item_text(self.monitoring_table, row, 3).strip()
        mode = self._table_item_text(self.monitoring_table, row, 1).strip()
        if not tag_name or not data_type or not address or mode != "Write":
            return

        self._monitoring_write_value_cache[(tag_name, data_type, address)] = item.text()

    def _connect(self):
        """Connect to Modbus server."""
        try:
            self.status_indicator.set_status("connecting")
            self.status_text.setText("Connecting...")
            self._set_connection_controls(connected=False, connecting=True)

            ip = self.ip_input.text().strip()
            port = self.port_input.value()
            unit_id = self.unit_input.value()

            self.modbus = ModbusClient(ip, port, unit_id)

            if self.modbus.connect():
                self.status_indicator.set_status("connected")
                self.status_text.setText(f"Connected to {ip}:{port}")
                self.connection_status.setText(f"Connected: {ip}:{port} (Unit {unit_id})")
                self._set_connection_controls(connected=True)

                # Add to connection history
                connection_string = f"{ip}:{port}:{unit_id}"
                if connection_string not in self.connection_history:
                    self.connection_history.insert(0, connection_string)
                    self._refresh_connection_history_combo()
                    self._save_settings()

                self._log(f"Connected to Modbus server at {ip}:{port} (Unit ID: {unit_id})")
            else:
                self.status_indicator.set_status("error")
                self.status_text.setText("Connection Failed")
                self._set_connection_controls(connected=False)
                self._log("Failed to connect to Modbus server")

        except Exception as e:
            self.status_indicator.set_status("error")
            self.status_text.setText("Connection Error")
            self._set_connection_controls(connected=False)
            self._log(f"Connection error: {e}")

    def _disconnect(self):
        """Disconnect from Modbus server."""
        if self.modbus:
            self.modbus.disconnect()
            self.modbus = None

        self.status_indicator.set_status("disconnected")
        self.status_text.setText("Disconnected")
        self.connection_status.setText("Not Connected")

        self._set_connection_controls(connected=False)

        if self.monitoring_active:
            self._stop_monitoring()

        self._log("🔌 Disconnected from Modbus server")

    def _set_connection_controls(self, connected: bool, connecting: bool = False):
        if connecting:
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(False)
            return
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)

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

    def _delete_selected_history(self):
        """Delete the currently selected connection history entry."""
        connection_string = self.connection_history_combo.currentText().strip()
        if not connection_string:
            return

        self.connection_history = [
            connection for connection in self.connection_history
            if connection != connection_string
        ]
        self._refresh_connection_history_combo()
        self._save_settings()
        self._log(f"Deleted connection history entry: {connection_string}")

    def _refresh_connection_history_combo(self):
        current_text = self.connection_history_combo.currentText()
        self.connection_history_combo.blockSignals(True)
        self.connection_history_combo.clear()
        self.connection_history_combo.addItems(self.connection_history[:10])
        if current_text in self.connection_history:
            self.connection_history_combo.setCurrentText(current_text)
        self.connection_history_combo.blockSignals(False)

    def _read_operation(self, operation_type):
        """Handle read operations."""
        if not self._check_connection():
            return
        if self._modbus_busy:
            self._log("Safety interlock: another Modbus request is active")
            return

        try:
            self._modbus_busy = True
            start_addr = self.read_start_addr.value()
            count = self.read_count.value()
            if start_addr + count - 1 > 65535:
                self._log("Read operation blocked: address range exceeds 65535")
                return

            if operation_type == "coils":
                data = self.modbus.read_coils(start_addr, count)
                if data is not None:
                    self._log(f"Read {len(data)} coils from {start_addr}: {data}")
                    self._display_raw_data(f"Coils[{start_addr}:{start_addr+count-1}]", data)
                else:
                    extra = f" ({self.modbus.last_error})" if getattr(self.modbus, "last_error", None) else ""
                    self._log(f"Failed to read coils{extra}")

            elif operation_type == "discrete_inputs":
                data = self.modbus.read_discrete_inputs(start_addr, count)
                if data is not None:
                    self._log(f"Read {len(data)} discrete inputs from {start_addr}: {data}")
                    self._display_raw_data(f"DiscreteInputs[{start_addr}:{start_addr+count-1}]", data)
                else:
                    extra = f" ({self.modbus.last_error})" if getattr(self.modbus, "last_error", None) else ""
                    self._log(f"Failed to read discrete inputs{extra}")

            elif operation_type == "holding_registers":
                data = self.modbus.read_registers(start_addr, count)
                if data is not None:
                    self._log(f"Read {len(data)} holding registers from {start_addr}: {data}")
                    self._display_raw_data(f"HoldingRegisters[{start_addr}:{start_addr+count-1}]", data)
                else:
                    extra = f" ({self.modbus.last_error})" if getattr(self.modbus, "last_error", None) else ""
                    self._log(f"Failed to read holding registers{extra}")

            elif operation_type == "input_registers":
                data = self.modbus.read_input_registers(start_addr, count)
                if data is not None:
                    self._log(f"Read {len(data)} input registers from {start_addr}: {data}")
                    self._display_raw_data(f"InputRegisters[{start_addr}:{start_addr+count-1}]", data)
                else:
                    extra = f" ({self.modbus.last_error})" if getattr(self.modbus, "last_error", None) else ""
                    self._log(f"Failed to read input registers{extra}")

        except Exception as e:
            self._log(f"Read operation error: {e}")
        finally:
            self._modbus_busy = False

    def _write_operation(self, operation_type):
        """Handle write operations."""
        if not self._check_connection():
            return
        if self._modbus_busy:
            self._log("Safety interlock: another Modbus request is active")
            return

        was_monitoring = self.monitoring_active
        monitor_interval = self.monitoring_interval.value()
        if was_monitoring:
            self.monitoring_timer.stop()
            self.write_poll_timer.stop()
            self._log("Safety interlock: monitoring paused while write request is active")

        try:
            self._modbus_busy = True
            addr = self.write_addr.value()

            if operation_type == "coil":
                value_text = self.write_single_value.text().strip()
                if not value_text:
                    self._log("Please enter a value for coil")
                    return
                value = bool(int(value_text))
                success = self.modbus.write_coil(addr, value)
                if success:
                    self._log(f"Wrote coil {addr} = {value}")
                else:
                    self._log("Failed to write coil")

            elif operation_type == "register":
                value_text = self.write_single_value.text().strip()
                if not value_text:
                    self._log("Please enter a value for register")
                    return
                value = int(value_text)
                success = self.modbus.write_register(addr, value)
                if success:
                    self._log(f"Wrote register {addr} = {value}")
                else:
                    self._log("Failed to write register")

            elif operation_type == "coils":
                values_text = self.write_multi_values.text().strip()
                if not values_text:
                    self._log("Please enter values for coils")
                    return
                values = [bool(int(v.strip())) for v in values_text.split(",")]
                success = self.modbus.write_coils(addr, values)
                if success:
                    self._log(f"Wrote {len(values)} coils starting at {addr}: {values}")
                else:
                    self._log("Failed to write coils")

            elif operation_type == "registers":
                values_text = self.write_multi_values.text().strip()
                if not values_text:
                    self._log("Please enter values for registers")
                    return
                values = [int(v.strip()) for v in values_text.split(",")]
                success = self.modbus.write_registers(addr, values)
                if success:
                    self._log(f"Wrote {len(values)} registers starting at {addr}: {values}")
                else:
                    self._log("Failed to write registers")

        except ValueError as e:
            self._log(f"Invalid value format: {e}")
        except Exception as e:
            self._log(f"Write operation error: {e}")
        finally:
            self._modbus_busy = False
            if was_monitoring and self.monitoring_active:
                self._restart_monitoring_timers(monitor_interval)
                self._log("Safety interlock: monitoring resumed after write request")

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

        tags_by_key = {self._tag_key(tag): tag for tag in self._get_monitoring_tags()}
        wrote_any = False
        was_monitoring = self.monitoring_active
        monitor_interval = self.monitoring_interval.value()

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
            self.output_tabs.setCurrentWidget(self.monitoring_table)

    def _tag_key(self, tag):
        return (tag["name"], tag["type"], str(tag["address"]))

    def _result_key(self, result_row):
        return (result_row["name"], result_row["type"], str(result_row["address"]))

    def _write_tag(self, tag):
        if tag["type"] in ("Discrete Input", "Input Register"):
            raise ValueError(f"{tag['type']} is read-only")

        if not tag["write_value"]:
            raise ValueError("write value is empty")

        if tag["type"] == "Coil":
            values = self._parse_coil_values(tag["write_value"])
            if tag["count"] == 1:
                desired_value = values[0]
                current_value = self._read_tag_value(tag)
                if current_value == desired_value:
                    return True, desired_value, "Skipped write; value already matches"

                if not self.modbus.write_coil(tag["address"], desired_value):
                    return False, desired_value, "Write failed"

                verified_value = self._read_tag_value(tag)
                if verified_value != desired_value:
                    return False, desired_value, f"Write verification failed; read back {verified_value}"
                return True, desired_value, "Write verified"

            values = self._fit_write_values(values, tag["count"])
            current_values = self._read_tag_value(tag)
            if current_values == values:
                return True, values, "Skipped write; values already match"

            if not self.modbus.write_coils(tag["address"], values):
                return False, values, "Write failed"

            verified_values = self._read_tag_value(tag)
            if verified_values != values:
                return False, values, f"Write verification failed; read back {verified_values}"
            return True, values, "Write verified"

        value_format = (tag.get("format") or "U16").strip().upper()
        desired_registers = self._parse_register_values(tag["write_value"], value_format, tag["count"])

        current_registers = self._read_tag_value(tag)
        if tag["count"] == 1 and not isinstance(current_registers, list):
            current_registers = [current_registers]
        if isinstance(current_registers, list):
            current_registers = current_registers[: tag["count"]]

        if current_registers == desired_registers:
            return True, self._format_written_value(tag, desired_registers), "Skipped write; value already matches"

        if tag["count"] == 1:
            if not self.modbus.write_register(tag["address"], desired_registers[0]):
                return False, self._format_written_value(tag, desired_registers), "Write failed"
        else:
            if not self.modbus.write_registers(tag["address"], desired_registers):
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

    def _read_tag_value(self, tag):
        if tag["type"] == "Coil":
            value = self.modbus.read_coils(tag["address"], tag["count"])
        elif tag["type"] == "Holding Register":
            value = self.modbus.read_registers(tag["address"], tag["count"])
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
                num = int(token, 16)
                registers.append(num & 0xFFFF)
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

            # Fallback to raw 16-bit ints
            registers.append(int(token, 10) & 0xFFFF)

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
        if tag["address"] < 0 or tag["address"] > 65535:
            raise ValueError("address must be between 0 and 65535")
        if tag["count"] < 1:
            raise ValueError("count must be at least 1")
        if tag["address"] + tag["count"] - 1 > 65535:
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
        return {
            "operation": operation,
            "space": tag["type"],
            "start": tag["address"],
            "end": tag["address"] + tag["count"] - 1,
            "tag": tag["name"],
        }

    def _ranges_overlap(self, left, right):
        if left["space"] != right["space"]:
            return False
        return left["start"] <= right["end"] and right["start"] <= left["end"]

    def _start_monitoring(self):
        """Start real-time data monitoring."""
        if not self._check_connection():
            return

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
        self._monitoring_failure_count = 0
        self._monitoring_poll_in_progress = False
        self._write_poll_in_progress = False
        interval = self.monitoring_interval.value()
        self._restart_monitoring_timers(interval)

        self.start_monitoring_btn.setEnabled(False)
        self.stop_monitoring_btn.setEnabled(True)
        self._set_tag_editor_enabled(False)

        self._log(f"Started monitoring with {interval}ms interval")

    def _find_duplicate_tag_addresses(self, tags):
        seen = {}
        duplicates = []
        for tag in tags:
            key = (tag["type"], int(tag["address"]))
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
                start = int(tag["address"])
                end = int(tag["address"]) + int(tag["count"]) - 1
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
        self._monitoring_poll_in_progress = False
        self._write_poll_in_progress = False

        self.start_monitoring_btn.setEnabled(True)
        self.stop_monitoring_btn.setEnabled(False)
        self._set_tag_editor_enabled(True)

        self._log("Stopped monitoring")

    def _set_tag_editor_enabled(self, enabled):
        self.monitoring_tag_table.setEnabled(enabled)
        self.add_tag_btn.setEnabled(enabled)
        self.remove_tag_btn.setEnabled(enabled and bool(self._get_selected_tag_rows()))

    def _restart_monitoring_timers(self, read_interval):
        tags = self._get_monitoring_tags()
        if any(tag["mode"] == "Read" for tag in tags):
            self.monitoring_timer.start(read_interval)
        if any(tag["mode"] == "Write" for tag in tags):
            self.write_poll_timer.start(1000)

    def _clear_monitoring_results(self):
        self.monitoring_table.setRowCount(0)
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
        values = {}
        for row in range(self.monitoring_table.rowCount()):
            key = (
                self._table_item_text(self.monitoring_table, row, 0),
                self._table_item_text(self.monitoring_table, row, 2),
                self._table_item_text(self.monitoring_table, row, 3),
            )
            values[key] = {
                "read_value": self._table_item_text(self.monitoring_table, row, 4),
                "write_value": self._table_item_text(self.monitoring_table, row, 5),
                "timestamp": self._table_item_text(self.monitoring_table, row, 7),
            }
        return values

    def _table_item_text(self, table, row, column):
        item = table.item(row, column)
        return item.text() if item else ""

    def _update_monitored_data(self):
        """Update monitored data in the table."""
        if not self.modbus or not self.monitoring_active:
            return
        if self._monitoring_poll_in_progress:
            self._log("Safety interlock: skipped monitor tick because previous poll is still running")
            return

        tags = [tag for tag in self._get_monitoring_tags() if tag["mode"] == "Read"]
        if not tags:
            return

        self._monitoring_poll_in_progress = True
        self.monitoring_timer.stop()
        poll_failed = False
        timestamp = time.strftime("%H:%M:%S")
        try:
            for tag in tags:
                try:
                    self._validate_tag_request(tag, "read")
                    if not self._begin_modbus_operation(tag, "read"):
                        self._log(f"Safety interlock: skipped read for {tag['name']} because the range is busy")
                        continue

                    try:
                        value = self._read_tag_for_monitoring(tag)
                    finally:
                        self._end_modbus_operation(tag, "read")

                    if value is None:
                        poll_failed = True
                        self._add_monitoring_row(
                            tag["name"], tag["mode"], tag["type"], tag["address"], "ERROR", "",
                            tag["comment"], timestamp
                        )
                        extra = ""
                        if self.modbus is not None and getattr(self.modbus, "last_error", None):
                            extra = f" ({self.modbus.last_error})"
                        self._log(f"Monitoring read failed for {tag['name']} at {tag['address']}{extra}")
                        break

                    display_value = self._format_monitoring_value(tag, value)
                    self._add_monitoring_row(
                        tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                        tag["comment"], timestamp
                    )
                except Exception as e:
                    poll_failed = True
                    self._log(f"Monitoring error for {tag['name']}: {e}")
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
                        "Monitoring was stopped after repeated Modbus failures. Check tag type, address, unit ID, and server status.",
                    )
            else:
                self._monitoring_failure_count = 0
        finally:
            self._monitoring_poll_in_progress = False
            if self.monitoring_active:
                self.monitoring_timer.start(self.monitoring_interval.value())

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
        if tag["type"] == "Coil":
            return self.modbus.read_coils(tag["address"], tag["count"])
        if tag["type"] == "Discrete Input":
            return self.modbus.read_discrete_inputs(tag["address"], tag["count"])
        if tag["type"] == "Holding Register":
            return self.modbus.read_registers(tag["address"], tag["count"])
        return self.modbus.read_input_registers(tag["address"], tag["count"])

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
                return [bool(int(r)) for r in registers]
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
        key = (tag_name, data_type, str(address))
        if write_value:
            self._monitoring_write_value_cache[key] = write_value

        cached_write_value = self._monitoring_write_value_cache.get(key, "")
        initial_write_value = write_value if write_value else cached_write_value

        row_count = self.monitoring_table.rowCount()

        self._updating_monitoring_table = True
        try:
            for row in range(row_count):
                name_item = self.monitoring_table.item(row, 0)
                type_item = self.monitoring_table.item(row, 2)
                address_item = self.monitoring_table.item(row, 3)
                if (
                    name_item and type_item and address_item
                    and name_item.text() == tag_name
                    and type_item.text() == data_type
                    and address_item.text() == str(address)
                ):
                    # Don't mutate the row while the user is typing a write value; it cancels the editor.
                    if (
                        self.monitoring_table.state() == QAbstractItemView.EditingState
                        and self.monitoring_table.currentRow() == row
                        and self.monitoring_table.currentColumn() == 5
                    ):
                        return

                    self.monitoring_table.setItem(row, 1, QTableWidgetItem(mode))
                    self.monitoring_table.setItem(row, 3, QTableWidgetItem(str(address)))
                    if read_value:
                        self.monitoring_table.setItem(row, 4, QTableWidgetItem(read_value))

                    # Only set the write column if we have a meaningful value to show.
                    # This avoids stomping on user edits during polling.
                    if write_value:
                        self.monitoring_table.setItem(row, 5, QTableWidgetItem(write_value))
                    elif initial_write_value and self.monitoring_table.item(row, 5) is None:
                        self.monitoring_table.setItem(row, 5, QTableWidgetItem(initial_write_value))

                    self.monitoring_table.setItem(row, 6, QTableWidgetItem(comment))
                    self.monitoring_table.setItem(row, 7, QTableWidgetItem(timestamp))
                    if self.results_window is not None:
                        self.results_window.update_row(
                            tag_name, mode, data_type, address, read_value, write_value, comment, timestamp
                        )
                    return

            self.monitoring_table.insertRow(row_count)
            self.monitoring_table.setItem(row_count, 0, QTableWidgetItem(tag_name))
            self.monitoring_table.setItem(row_count, 1, QTableWidgetItem(mode))
            self.monitoring_table.setItem(row_count, 2, QTableWidgetItem(data_type))
            self.monitoring_table.setItem(row_count, 3, QTableWidgetItem(str(address)))
            self.monitoring_table.setItem(row_count, 4, QTableWidgetItem(read_value))
            self.monitoring_table.setItem(row_count, 5, QTableWidgetItem(initial_write_value))
            self.monitoring_table.setItem(row_count, 6, QTableWidgetItem(comment))
            self.monitoring_table.setItem(row_count, 7, QTableWidgetItem(timestamp))
        finally:
            self._updating_monitoring_table = False

        if self.results_window is not None:
            self.results_window.update_row(
                tag_name, mode, data_type, address, read_value, write_value, comment, timestamp
            )

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
            history_file = app_data_dir() / "connection_history.txt"
            if history_file.exists():
                with open(history_file, 'r') as f:
                    self.connection_history = [line.strip() for line in f.readlines() if line.strip()]
                self._refresh_connection_history_combo()
        except Exception:
            pass

    def _save_settings(self):
        """Save user settings and preferences."""
        try:
            config_dir = app_data_dir()
            config_dir.mkdir(parents=True, exist_ok=True)
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
        self._clear_monitoring_results()
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
        dialog = NetworkDiagnosticsDialog(
            host=self.ip_input.text().strip() or "127.0.0.1",
            port=int(self.port_input.value()),
            unit_id=int(self.unit_input.value()),
            parent=self,
        )
        dialog.exec()

    def _show_documentation(self):
        """Show documentation."""
        # TODO: Implement documentation viewer
        QMessageBox.information(self, "Documentation", "Documentation viewer will be implemented in the next update!")

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(self, "About ModbusLens",
                         "<b>ModbusLens v1.0</b><br><br>"
                         "Professional Modbus TCP Client<br>"
                         "Made by Alvin A D<br><br>"
                         "Available features:<br>"
                         "&bull; Modbus TCP read operations (coils, discrete inputs, holding registers, input registers)<br>"
                         "&bull; Modbus TCP write operations (single/multiple coils, single/multiple registers)<br>"
                         "&bull; Real-time monitoring with tag table (read and write modes)<br>"
                         "&bull; Detached monitoring results window with write-selected action<br>"
                         "&bull; Recent connection history (per-user)<br>"
                         "&bull; Network diagnostics (DNS + TCP + optional Modbus connect)<br><br>"
                         "Planned / unavailable features:<br>"
                         "&bull; Save session / load session<br>"
                         "&bull; Export data<br>"
                         "&bull; Theme toggle<br>"
                         "&bull; Connection profiles<br>"
                         "&bull; Data templates<br>"
                         "&bull; Scripting console<br>"
                         "&bull; Documentation viewer<br><br>"
                         "GitHub: <a href=\"https://github.com/CraftParking/ModbusLens\">https://github.com/CraftParking/ModbusLens</a><br><br>"
                         "&copy; 2026 ModbusLens Team")

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
                border-radius: 6px;
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


class NetworkDiagnosticsWorker(QThread):
    output = Signal(str)
    done = Signal(bool)

    def __init__(self, host: str, port: int, unit_id: int, timeout_s: float, test_modbus: bool):
        super().__init__()
        self.host = host
        self.port = int(port)
        self.unit_id = int(unit_id)
        self.timeout_s = float(timeout_s)
        self.test_modbus = bool(test_modbus)

    def _emit(self, line: str):
        self.output.emit(line)

    def run(self):
        ok = True
        try:
            host = self.host.strip()
            if not host:
                self._emit("ERROR: Host is empty.")
                self.done.emit(False)
                return

            self._emit(f"Target: {host}:{self.port} (Unit {self.unit_id})")
            self._emit(f"Timeout: {self.timeout_s:.1f}s")

            # DNS / address resolution
            try:
                infos = socket.getaddrinfo(host, self.port, type=socket.SOCK_STREAM)
                addrs = []
                for family, socktype, proto, canonname, sockaddr in infos:
                    if sockaddr and sockaddr[0] not in addrs:
                        addrs.append(sockaddr[0])
                if addrs:
                    self._emit("Resolve: OK -> " + ", ".join(addrs[:5]))
                else:
                    self._emit("Resolve: OK")
            except Exception as e:
                ok = False
                self._emit(f"Resolve: FAIL ({e})")
                self.done.emit(False)
                return

            # TCP connect test (port reachability)
            try:
                start = time.perf_counter()
                sock = socket.create_connection((host, self.port), timeout=self.timeout_s)
                try:
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    self._emit(f"TCP Connect: OK ({elapsed_ms:.0f} ms)")
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass
            except Exception as e:
                ok = False
                self._emit(f"TCP Connect: FAIL ({e})")
                self.done.emit(False)
                return

            if self.test_modbus:
                self._emit("Modbus Connect: running...")
                try:
                    client = ModbusClient(host, self.port, self.unit_id, timeout=self.timeout_s, retries=0)
                    if client.connect():
                        self._emit("Modbus Connect: OK")
                    else:
                        ok = False
                        self._emit("Modbus Connect: FAIL (connect returned False)")
                    client.disconnect()
                except Exception as e:
                    ok = False
                    self._emit(f"Modbus Connect: FAIL ({e})")
        finally:
            self.done.emit(ok)


class NetworkDiagnosticsDialog(QDialog):
    def __init__(self, host: str, port: int, unit_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Network Diagnostics")
        self.setModal(True)
        self.resize(760, 460)

        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        form = QGroupBox("Target")
        form_layout = QGridLayout(form)
        form_layout.setSpacing(8)

        form_layout.addWidget(QLabel("Host/IP:"), 0, 0)
        self.host_input = QLineEdit(host)
        self.host_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self.host_input, 0, 1)

        form_layout.addWidget(QLabel("Port:"), 0, 2)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(port))
        self.port_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self.port_input, 0, 3)

        form_layout.addWidget(QLabel("Unit ID:"), 1, 0)
        self.unit_input = QSpinBox()
        self.unit_input.setRange(1, 247)
        self.unit_input.setValue(int(unit_id))
        self.unit_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self.unit_input, 1, 1)

        form_layout.addWidget(QLabel("Timeout (s):"), 1, 2)
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(1, 30)
        self.timeout_input.setValue(2)
        self.timeout_input.setStyleSheet(self._input_style())
        form_layout.addWidget(self.timeout_input, 1, 3)

        self.modbus_check = QCheckBox("Also test Modbus connect")
        self.modbus_check.setChecked(True)
        form_layout.addWidget(self.modbus_check, 2, 0, 1, 4)

        layout.addWidget(form)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        layout.addWidget(self.output)

        buttons = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #333333;")
        buttons.addWidget(self.status_label)
        buttons.addStretch()

        self.run_btn = QPushButton("Run Tests")
        self.run_btn.setStyleSheet(self._button_style(primary=True))
        self.run_btn.clicked.connect(self._run)
        buttons.addWidget(self.run_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._button_style())
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)

        layout.addLayout(buttons)

    def _append(self, line: str):
        current = self.output.toPlainText()
        if current:
            current += "\n"
        current += line
        self.output.setPlainText(current)
        scrollbar = self.output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_running(self, running: bool):
        self.host_input.setEnabled(not running)
        self.port_input.setEnabled(not running)
        self.unit_input.setEnabled(not running)
        self.timeout_input.setEnabled(not running)
        self.modbus_check.setEnabled(not running)
        self.run_btn.setEnabled(not running)

    def _run(self):
        if self._worker is not None and self._worker.isRunning():
            return

        self.output.clear()
        self.status_label.setText("Running...")
        self._set_running(True)

        self._worker = NetworkDiagnosticsWorker(
            host=self.host_input.text().strip(),
            port=int(self.port_input.value()),
            unit_id=int(self.unit_input.value()),
            timeout_s=float(self.timeout_input.value()),
            test_modbus=bool(self.modbus_check.isChecked()),
        )
        self._worker.output.connect(self._append)
        self._worker.done.connect(self._done)
        self._worker.start()

    def _done(self, ok: bool):
        self.status_label.setText("OK" if ok else "FAILED")
        self._set_running(False)
        self._worker = None

    @staticmethod
    def _input_style() -> str:
        return """
            QSpinBox, QLineEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
            }
            QSpinBox:focus, QLineEdit:focus {
                border-color: #007ACC;
            }
        """

    @staticmethod
    def _button_style(primary: bool = False) -> str:
        if primary:
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
                border-radius: 6px;
                padding: 8px 14px;
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


def main(): 
    try: 
        # Check if QApplication already exists (e.g., in IDE environments) 
        app = QApplication.instance() 
        if app is None: 
            app = QApplication(sys.argv)

        app.setApplicationName("ModbusLens") 
        app.setApplicationVersion("1.0") 
        app.setOrganizationName("ModbusLens") 
 
        warning = SafetyWarningDialog()
        if warning.exec() != QDialog.Accepted:
            sys.exit(0)

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
