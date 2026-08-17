import sys
import os
import re
import subprocess
import logging
import time
import struct
import csv
import json
import math
import socket
import threading
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QSpinBox, QDoubleSpinBox, QTabWidget, QGroupBox,
    QApplication, QMessageBox, QDialog, QCheckBox,
    QAbstractItemView, QFrame, QGridLayout, QSizePolicy, QMenu, QRadioButton
)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QIcon, QActionGroup, QShortcut, QKeySequence

# Add the gui directory to the path for relative imports
sys.path.insert(0, str(Path(__file__).parent))

# Import extracted components
from widgets.status_indicator import StatusIndicator
from widgets.address_table import AddressTableWidget
from widgets.trend_widget import TrendWidget
from widgets.server_widget import ServerWidget
from widgets.script_widget import ScriptWidget, validate_tag_name
from widgets.documentation_dialog import DocumentationDialog
from widgets.about_dialog import AboutDialog
from diagnostics.advanced_diagnostics import AdvancedDiagnostics
from diagnostics.diagnostics_dialogs import DiagnosticsDialogs
from diagnostics.register_scanner import RegisterScannerWidget
from diagnostics.serial_discovery import SerialDiscoveryDialog
from diagnostics.diagnostic_functions import DiagnosticFunctionsDialog
from monitoring.monitoring_manager import MonitoringManager
from monitoring.shared_read_cache import SharedReadCache
from network.network_diagnostics import NetworkDiagnosticsDialog

from core.modbus_client import ModbusClient
from app_paths import resource_path, app_data_dir
from log_format import format_log_html
from modbus_meta import function_code_for, MULTI_WORD_FORMATS, format_word_width
import theme

__version__ = "2.2.0"

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


apply_theme = theme.apply_theme  # kept as a module-level name other code may reference


class TagTableWidget(QTableWidget):
    """Tags table with row reordering via dragging the row-number header.

    Every cell here holds a live QWidget (combobox, spinbox, or line edit) covering the entire
    row, not a plain QTableWidgetItem -- so a mouse press anywhere on a row is consumed by that
    cell's own widget (text cursor placement, combobox popup, etc.) and never reaches the table's
    own drag-detection logic. There's no "empty" surface on a row to grab. The row-number gutter
    (the vertical header) is the one part of the table not covered by a cell widget, so reordering
    is done by dragging that instead, via QHeaderView's own built-in section-move support.
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        # Row-height resize (dragging a header boundary) competes with row-reorder (dragging a
        # header section) for the same mouse gesture in the same gutter -- disable resize so
        # every drag there means "reorder" with no ambiguity.
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.verticalHeader().setSectionsMovable(True)
        self.verticalHeader().sectionMoved.connect(self._on_row_header_moved)

        # QHeaderView's own drag animation only moves the header label itself -- it doesn't
        # show where the row would land in the table body. Draw that line ourselves, tracking
        # the header's mouse-move events for as long as a drag is in progress.
        self._drop_indicator = QFrame(self.viewport())
        self._drop_indicator.setStyleSheet(f"background-color: {main_window._colors()['accent']};")
        self._drop_indicator.setFixedHeight(2)
        self._drop_indicator.hide()
        self.verticalHeader().installEventFilter(self)

        # Delete key removes the selected row(s), mirroring "Remove Selected Tag". Every
        # cell here is a live QLineEdit/QComboBox/QSpinBox/QCheckBox (see class docstring), so
        # this needs WidgetWithChildrenShortcut to fire no matter which cell widget currently
        # holds focus -- QLineEdit/QSpinBox already claim a plain Delete for their own
        # in-place editing (via ShortcutOverride), so this only actually fires when focus is on
        # a combo/checkbox cell or the table itself, never mid-edit of a name/comment field.
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self)
        self._delete_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._delete_shortcut.activated.connect(main_window._remove_monitoring_tag)

        # Ctrl+C copies the selected row(s) the same way the context menu's "Copy Row(s)"
        # does. QLineEdit already claims Ctrl+C for its own text selection via
        # ShortcutOverride, so like Delete above, this only fires from a combo/checkbox/
        # spinbox cell or the table itself -- never steals a mid-edit text copy.
        self._copy_shortcut = QShortcut(QKeySequence.Copy, self)
        self._copy_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        self._copy_shortcut.activated.connect(
            lambda: main_window._copy_tag_rows(main_window._get_selected_tag_rows())
        )

    def eventFilter(self, watched, event):
        if watched is self.verticalHeader():
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                self._update_drop_indicator(event.position().toPoint().y())
            elif event.type() in (QEvent.Type.MouseButtonRelease, QEvent.Type.Leave):
                self._drop_indicator.hide()
        return super().eventFilter(watched, event)

    def _update_drop_indicator(self, header_y):
        """Show a line at the row boundary the header drag is currently hovering over --
        header_y and the table body share the same vertical row layout, just different columns."""
        row_count = self.rowCount()
        if row_count == 0:
            self._drop_indicator.hide()
            return

        row = self.rowAt(header_y)
        if row == -1:
            last_row = row_count - 1
            y = self.rowViewportPosition(last_row) + self.rowHeight(last_row)
        else:
            row_top = self.rowViewportPosition(row)
            row_bottom = row_top + self.rowHeight(row)
            y = row_bottom if (header_y - row_top) > (row_bottom - row_top) / 2 else row_top

        self._drop_indicator.setGeometry(0, max(0, y - 1), self.viewport().width(), 2)
        self._drop_indicator.show()
        self._drop_indicator.raise_()

    def _on_row_header_moved(self, logical_index, old_visual_index, new_visual_index):
        self._drop_indicator.hide()
        header = self.verticalHeader()
        # The header just reordered itself visually -- snap it back to sequential order and
        # instead physically relocate the row's own widgets, so the header's numbers (1, 2, 3...)
        # never desync from which row they're actually labeling.
        header.blockSignals(True)
        try:
            header.moveSection(new_visual_index, old_visual_index)
        finally:
            header.blockSignals(False)
        self.main_window._move_tag_row(old_visual_index, new_visual_index)


class ModbusGUI(QMainWindow):
    _open_windows = []  # keeps extra connection windows alive (see _new_connection_window)

    WATCHDOG_HEALTHY_INTERVAL_MS = 3000  # how often to check a connection that's currently fine
    RECONNECT_BASE_DELAY_MS = 2000  # first retry delay after a drop
    RECONNECT_MAX_DELAY_MS = 30000  # cap for exponential backoff between retries

    def __init__(self):
        super().__init__()

        # The theme was already applied to the QApplication in main() before this window
        # was constructed -- resolve the same mode again here so widget-level style strings
        # (built per-widget below, since QPalette/global QSS in theme.py don't reach every
        # custom-colored table/dialog) use matching colors instead of hardcoded light-only hex.
        self._theme_mode = theme.resolve_mode(theme.load_saved_mode(), QApplication.instance())
        self._c = theme.get_colors(self._theme_mode)

        self.modbus = None
        self.connection_history = []
        # Write bounds loaded from a Session file, waiting for a live ModbusClient to apply
        # them to -- write bounds only ever exist on the current connection's own instance
        # (ModbusClient.write_bounds), so a Session loaded before connecting (or while a
        # previous connection is still up) can't set them immediately. Applied by
        # _apply_pending_write_bounds(), called again right after every successful _connect().
        self._pending_write_bounds = []

        # Connection parameters
        self.connection_mode = "tcp"  # "tcp" or "serial"
        self.target_ip = "127.0.0.1"
        self.target_port = 502
        self.target_unit_id = 1
        self.serial_port = "COM1"
        self.baudrate = 19200
        self.parity = "N"
        self.stopbits = 1
        self.bytesize = 8
        self.serial_framer = "rtu"  # "rtu" or "ascii"
        # Short (~200ms) timeout, no retries, and a bare TCP reachability probe instead of
        # a full retry/timeout cycle when a poll fails -- for LANs where a real timeout
        # means "dead device," not "slow network."
        self.fast_lan_mode = False
        # None = let the OS pick the outgoing route (today's behavior); otherwise the IP of
        # the interface to bind the TCP socket to, e.g. so a VPN + Ethernet + Wi-Fi machine
        # actually goes out the NIC the user picked instead of whatever the OS defaults to.
        self.interface_ip = None

        # Shared between Tag Monitoring's poll worker and Trend's own poll timer so the
        # exact same register range configured in both doesn't cost two wire round-trips
        # every cycle -- see shared_read_cache.SharedReadCache.
        self._shared_read_cache = SharedReadCache()

        # Initialize extracted components
        self.advanced_diagnostics = AdvancedDiagnostics()
        self.diagnostics_dialogs = DiagnosticsDialogs(self)
        self.monitoring_manager = MonitoringManager(self)
        self.network_diagnostics = NetworkDiagnosticsDialog(self)
        self.serial_discovery = SerialDiscoveryDialog(self)
        
        self._updating_tag_table = False
        self._modbus_busy = False
        self._active_ranges = []
        # Guards _active_ranges/_modbus_busy's check-then-mutate sequence in
        # _reserve_range/_release_range. _modbus_busy is a single global flag -- any
        # reservation attempt is rejected outright while it's set, regardless of whether
        # the requested range actually overlaps anything active -- so despite the
        # "range" framing this already acts as a de facto mutex around the one wire call
        # each reservation brackets. That was safe with a plain bool as long as every
        # caller ran on the GUI thread (Register Scanner/Serial Discovery are the only
        # prior background-thread callers, and both fully pause every other poller before
        # running, so they never actually raced this flag). Tag Monitoring's poll worker
        # breaks that assumption -- it runs continuously alongside Address Table/Trend's
        # GUI-thread polls, so the check-then-set here needs a real lock now, not just
        # GIL-assisted luck.
        self._active_ranges_lock = threading.Lock()
        # Opt-out of the per-write confirm dialog, scoped to the current connection --
        # reset on every new connect() so it can't silently stay suppressed for months
        # the way SafetyWarningDialog's permanent "don't show again" can (see notes.md).
        self._write_confirm_suppressed = False
        # Rows currently painted as selected in the Tags table (see
        # _on_tag_table_selection_changed) -- tracked separately from Qt's own
        # selection model because every cell is a setCellWidget(), which paints over
        # QTableWidget's normal ::item:selected background, so selection was
        # otherwise invisible.
        self._highlighted_tag_rows = set()
        self.monitoring_active = False
        self._write_poll_in_progress = False
        self.tag_address_one_based = True
        
        self.monitoring_timer = QTimer(self)
        self.monitoring_timer.timeout.connect(self._update_monitored_data)
        self.write_poll_timer = QTimer(self)
        self.write_poll_timer.timeout.connect(self._update_write_tag_values)

        # Auto-reconnect: watches the connection after a successful connect() and, if it
        # drops unexpectedly (not via the user clicking Disconnect), retries with backoff
        # until it's healthy again.
        self._reconnect_watchdog_timer = QTimer(self)
        self._reconnect_watchdog_timer.setSingleShot(True)
        self._reconnect_watchdog_timer.timeout.connect(self._check_connection_watchdog)
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._monitoring_paused_by_disconnect = False

        self.diagnostics_dialogs.setup_diagnostics_widgets()  # Initialize diagnostics widgets early, the Raw Data tab needs them

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
        file_menu.addAction("New Connection Window", self._new_connection_window)
        file_menu.addSeparator()
        file_menu.addAction("New Session", self._new_session)
        file_menu.addAction("Save Session", self._save_session)
        file_menu.addAction("Load Session", self._load_session)
        file_menu.addSeparator()
        file_menu.addAction("Export Data", self._export_data)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        # View menu
        view_menu = menubar.addMenu("&View")
        theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        saved_mode = theme.load_saved_mode()
        self._theme_actions = {}
        for mode, label in (("light", "Light"), ("dark", "Dark"), ("system", "Follow System")):
            action = theme_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == saved_mode)
            action.triggered.connect(lambda checked, m=mode: self._set_theme_mode(m))
            theme_group.addAction(action)
            self._theme_actions[mode] = action

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction("Connection Settings", self._show_connection_settings)
        tools_menu.addAction("Connection Profiles", self._manage_profiles)
        tools_menu.addAction("Data Templates", self._manage_templates)
        tools_menu.addSeparator()
        tools_menu.addAction("IP Configuration", self._show_ip_config)
        tools_menu.addSeparator()
        tools_menu.addAction("Show Safety Warning Again", self._show_safety_warning_again)

        # Diagnostics menu
        diagnostics_menu = menubar.addMenu("&Diagnostics")
        diagnostics_menu.addAction("Network Discovery & Diagnostics", self._network_diagnostics)
        diagnostics_menu.addAction("Serial Discovery", self._serial_discovery)
        diagnostics_menu.addAction("Modbus Diagnostic Functions", self._show_diagnostic_functions)
        diagnostics_menu.addSeparator()
        diagnostics_menu.addAction("System Logs", self._show_diagnostics_logs)
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
        connection_frame.setStyleSheet(f"""
            QFrame#connectionBar {{
                background-color: {self._c["surface"]};
                border: 1px solid {self._c["border_light"]};
                border-radius: 6px;
            }}
        """)
        connection_frame.setFixedHeight(50)

        main_layout = QHBoxLayout(connection_frame)
        main_layout.setContentsMargins(15, 5, 15, 5)
        main_layout.setSpacing(15)

        # 1. Status Section (Left)
        self.status_indicator = StatusIndicator(dark=(self._theme_mode == "dark"))
        main_layout.addWidget(self.status_indicator)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setStyleSheet(f"color: {self._c['border_light']};")
        main_layout.addWidget(sep)

        # 2. Connection Info Label
        self.connection_info_label = QLabel()
        self.connection_info_label.setStyleSheet(f"color: {self._c['text_dim']}; font-weight: 500; font-size: 12px;")
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
            self.connection_info_label.setText(f"{self._target_description()} (Unit {self.target_unit_id})")

    def _target_description(self):
        if self.connection_mode == "serial":
            framer_label = "ASCII" if self.serial_framer == "ascii" else "RTU"
            return f"{self.serial_port} @ {self.baudrate} baud ({framer_label})"
        return f"{self.target_ip}:{self.target_port}"

    def _build_connection_string(self):
        """Serialize the current connection settings for the Recent Connections history."""
        if self.connection_mode == "serial":
            return (
                f"serial:{self.serial_port}:{self.baudrate}:{self.parity}:"
                f"{self.bytesize}:{self.stopbits}:{self.target_unit_id}:{self.serial_framer}"
            )
        return f"{self.target_ip}:{self.target_port}:{self.target_unit_id}"

    def _record_connection_history(self):
        """Push the current connection settings to the front of Recent Connections,
        deduping any existing identical entry. Shared by a successful Connect and by
        Save Settings alone, so history stays current either way instead of only
        updating on a live connect."""
        connection_string = self._build_connection_string()
        if connection_string in self.connection_history:
            self.connection_history.remove(connection_string)
        self.connection_history.insert(0, connection_string)
        self.connection_history = self.connection_history[:10]

    def _setup_operations_section(self, parent_layout):
        """Setup operations section with full height for address tables."""
        # Tab widget for operations
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {self._c["border"]};
                background-color: {self._c["surface"]};
            }}
            QTabBar::tab {{
                background-color: {self._c["surface_alt"]};
                color: {self._c["text_secondary"]};
                padding: 8px 16px;
                border: 1px solid {self._c["border"]};
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background-color: {self._c["surface"]};
                color: {self._c["text_secondary"]};
                border-bottom: 1px solid {self._c["surface"]};
            }}
            QTabBar::tab:hover {{
                background-color: {self._c["hover_strong"]};
            }}
        """)

        # Address Table tab (ModScan-like interface)
        self._setup_address_table_tab()

        # Monitoring tab
        self._setup_monitoring_tab()

        # Raw Data tab
        self._setup_raw_data_tab()

        # Trend tab
        self._setup_trend_tab()

        # Server tab
        self._setup_server_tab()

        # Script tab
        self._setup_script_tab()

        # Scanner tab
        self._setup_register_scanner_tab()

        # Connect tab change signal for interlock
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        parent_layout.addWidget(self.tab_widget)
        parent_layout.setStretchFactor(self.tab_widget, 1)  # Make tab widget expand

    def _setup_address_table_tab(self):
        """Setup Address Table tab with ModScan-like interface."""
        # Create the address table widget
        self.address_table_widget = AddressTableWidget(self)
        self.tab_widget.addTab(self.address_table_widget, "Address Table")

    def _setup_trend_tab(self):
        """Setup Trend tab with live/historical multi-pen graphing."""
        self.trend_widget = TrendWidget(self)
        self.tab_widget.addTab(self.trend_widget, "Trend")

    def _setup_server_tab(self):
        """Setup Server tab (Modbus TCP slave simulator)."""
        self.server_widget = ServerWidget(self)
        self.tab_widget.addTab(self.server_widget, "Server")

    def _setup_script_tab(self):
        """Setup Script tab (WRITE/READ/WAIT/REPEAT/IF test sequences)."""
        self.script_widget = ScriptWidget(self)
        self.tab_widget.addTab(self.script_widget, "Script")

    def _setup_register_scanner_tab(self):
        """Setup Scanner tab (register address / serial parameter auto-discovery)."""
        self.register_scanner_widget = RegisterScannerWidget(self)
        self.tab_widget.addTab(self.register_scanner_widget, "Scanner")

    def _setup_monitoring_tab(self):
        """Setup monitoring tab with real-time data display."""
        monitor_widget = QWidget()
        layout = QVBoxLayout(monitor_widget)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # Control buttons section
        control_group = QGroupBox("Monitoring Controls")
        control_group.setStyleSheet(self._get_groupbox_style())
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

        self.write_selected_btn = QPushButton("Write Selected")
        self.write_selected_btn.setStyleSheet(self._get_button_style())
        self.write_selected_btn.setMinimumWidth(120)
        buttons_layout.addWidget(self.write_selected_btn)

        self.write_all_btn = QPushButton("Write All")
        self.write_all_btn.setStyleSheet(self._get_button_style())
        self.write_all_btn.setMinimumWidth(120)
        buttons_layout.addWidget(self.write_all_btn)

        self.tags_log_btn = QPushButton("Log to CSV")
        self.tags_log_btn.setStyleSheet(self._get_button_style())
        self.tags_log_btn.setMinimumWidth(120)
        buttons_layout.addWidget(self.tags_log_btn)

        # Add stretch to push interval controls to the right
        buttons_layout.addStretch()

        # Interval controls
        interval_label = QLabel("Interval (ms):")
        interval_label.setStyleSheet(f"color: {self._c['text_secondary']}; font-weight: normal;")
        buttons_layout.addWidget(interval_label)

        self.tag_monitoring_interval = QSpinBox()
        self.tag_monitoring_interval.setRange(100, 10000)
        self.tag_monitoring_interval.setValue(1000)
        self.tag_monitoring_interval.setStyleSheet(self._get_input_style())
        self.tag_monitoring_interval.setMinimumWidth(80)
        buttons_layout.addWidget(self.tag_monitoring_interval)

        self.tag_offset_checkbox = QCheckBox("0-Based Addressing")
        self.tag_offset_checkbox.setToolTip("When enabled, use 0-based addressing (tag address 0 is sent as protocol offset 0)")
        # Purely a local address-interpretation preference (see _on_tag_address_mode_changed --
        # it only touches spinbox ranges/table cells, never self.modbus), so it doesn't need a
        # live connection to be safe to use. Only monitoring being actively in progress disables
        # it (via _set_tag_editor_enabled), same as Add/Remove Tag and the tag editor columns.
        self.tag_offset_checkbox.toggled.connect(self._on_tag_address_mode_changed)
        buttons_layout.addWidget(self.tag_offset_checkbox)

        control_layout.addLayout(buttons_layout)
        layout.addWidget(control_group)

        # Tag manager table (Excel-style)
        tag_group = QGroupBox("Tags")
        tag_group.setStyleSheet(self._get_groupbox_style())
        tag_layout = QVBoxLayout(tag_group)
        tag_layout.setSpacing(10)
        tag_layout.setContentsMargins(15, 25, 15, 15)  # Extra top margin for title

        self.monitoring_tag_table = TagTableWidget(self)
        self.monitoring_tag_table.setColumnCount(14)
        self.monitoring_tag_table.setHorizontalHeaderLabels(["Tag Name", "Mode", "Type", "Address", "Count", "Format", "Read Value", "Raw (Hex)", "Write Value", "Comment", "Timestamp", "Engineering Value", "Scale", "Enabled"])
        self._update_tag_address_header()
        self.monitoring_tag_table.horizontalHeader().setStretchLastSection(True)
        self.monitoring_tag_table.setColumnWidth(11, 130)
        self.monitoring_tag_table.setSelectionBehavior(QTableWidget.SelectRows)
        # Every cell here is a setCellWidget() covering the row, so the only click surface
        # Qt's own selection model ever sees is the row-number header (see TagTableWidget's
        # docstring). Without an explicit mode here, QAbstractItemView defaults to
        # SingleSelection -- a plain click there always worked, but Ctrl/Shift-click never
        # extended it to more than one row. ExtendedSelection is what actually enables that.
        self.monitoring_tag_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.monitoring_tag_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.monitoring_tag_table.customContextMenuRequested.connect(self._show_tag_context_menu)
        # Column drag-reorder is purely a display preference -- every cell lookup elsewhere
        # addresses columns by their stable logical index (cellWidget(row, col)), which Qt
        # keeps unchanged when a user drags a column to a new visual position, so this needs
        # none of the snap-back-and-rebuild machinery the row reorder above does (there, row
        # order is semantically meaningful).
        self.monitoring_tag_table.horizontalHeader().setSectionsMovable(True)
        self.monitoring_tag_table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.monitoring_tag_table.horizontalHeader().customContextMenuRequested.connect(self._show_tag_column_picker)
        self.monitoring_tag_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.monitoring_tag_table.setMinimumHeight(200)  # Ensure minimum height
        self.monitoring_tag_table.setMaximumHeight(16777215)  # Remove maximum height constraint
        
        # Ensure proper scrolling
        self.monitoring_tag_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.monitoring_tag_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.monitoring_tag_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.monitoring_tag_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel) 
        self.monitoring_tag_table.setStyleSheet(self._get_table_style())
        self.monitoring_tag_table.itemSelectionChanged.connect(self._on_tag_table_selection_changed)
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

    def _setup_raw_data_tab(self):
        """Setup the Raw Data tab, showing the untouched Modbus traffic behind every read/write."""
        raw_data_widget = self.diagnostics_dialogs.build_raw_data_tab(self.advanced_diagnostics)
        self.tab_widget.addTab(raw_data_widget, "Raw Data")

    def _show_diagnostics_logs(self):
        """Show diagnostics dialog with system logs."""
        self.diagnostics_dialogs.show_diagnostics_logs()

    def _clear_diagnostics_logs(self):
        """Clear all diagnostics data."""
        self.diagnostics_dialogs.clear_all_diagnostics_logs()
        self._log("All diagnostics data cleared")

    def _setup_status_bar(self):
        """Setup status bar with additional information."""
        self.status_bar = self.statusBar()

        self.connection_status = QLabel("Not Connected")
        self.status_bar.addWidget(self.connection_status)

        version = QApplication.applicationVersion()
        self.status_bar.addPermanentWidget(QLabel(f"ModbusLens v{version}"))

    def _get_table_style(self):
        c = self._c
        return f"""
            QTableWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}
            QHeaderView::section {{
                background-color: {c["header_bg"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                padding: 5px;
            }}
            QTableWidget::item:selected {{
                background-color: {c["selection_bg"]};
                color: {c["selection_text"]};
            }}
            QTableWidget::item:selected:!active {{
                background-color: {c["selection_inactive_bg"]};
                color: {c["selection_inactive_text"]};
            }}
            QLineEdit[tagRowSelected="true"], QComboBox[tagRowSelected="true"],
            QSpinBox[tagRowSelected="true"], QCheckBox[tagRowSelected="true"] {{
                background-color: {c["selection_bg"]};
                color: {c["selection_text"]};
            }}
        """

    def _get_groupbox_style(self):
        c = self._c
        return f"""
            QGroupBox {{
                font-weight: bold;
                color: {c["heading"]};
                border: 1px solid {c["border"]};
                margin-top: 1ex;
                background-color: {c["surface_alt2"]};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }}
        """

    def _colors(self):
        """The current theme's color tokens -- other widget files reach this via
        self.parent_window._colors() the same way they already call _get_button_style()."""
        return self._c

    def _set_theme_mode(self, mode):
        previous_mode = theme.load_saved_mode()
        if mode == previous_mode:
            return

        reply = QMessageBox.question(
            self, "Restart Required",
            f"Switch to the {mode.title()} theme?\n\nModbusLens needs to restart to apply this.",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Ok,
        )
        if reply != QMessageBox.Ok:
            self._theme_actions[previous_mode].setChecked(True)
            return

        theme.save_mode(mode)
        self._restart_application()

    def _restart_application(self):
        """Relaunch the app (frozen exe or `python gui_main.py`) and quit this instance,
        closing every open connection window first so each one's normal cleanup
        (stop monitoring, disconnect, stop the Server tab's listener) still runs.

        Passes this process's own PID via --wait-for-pid so the new instance (see
        gui_main.py's _wait_for_previous_instance) holds off touching Qt until this one
        has actually exited -- a --onefile build extracts its Qt plugins to a temp folder
        on launch and deletes it on exit, and starting the new copy immediately raced that
        cleanup, intermittently producing "no Qt platform plugin" on relaunch."""
        cmd = [sys.executable]
        if not getattr(sys, "frozen", False):
            cmd.append(os.path.abspath(sys.argv[0]))
        cmd.extend(sys.argv[1:])
        cmd.append(f"--wait-for-pid={os.getpid()}")
        subprocess.Popen(cmd)

        for window in list(ModbusGUI._open_windows) + [self]:
            try:
                window.close()
            except Exception:
                pass
        QApplication.instance().quit()

    def _get_input_style(self):
        """Get consistent input widget style."""
        c = self._c
        up_arrow, down_arrow = theme.get_arrow_icon_paths(self._theme_mode)
        return f"""
            QSpinBox, QLineEdit {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                padding: 5px;
            }}
            QSpinBox {{
                padding-right: 2px;
            }}
            QSpinBox:focus, QLineEdit:focus {{
                border-color: {c["accent"]};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                subcontrol-origin: border;
                width: 16px;
                border-left: 1px solid {c["border"]};
                background-color: {c["window_bg"]};
            }}
            QSpinBox::up-button {{
                subcontrol-position: top right;
                border-bottom: 1px solid {c["border"]};
            }}
            QSpinBox::down-button {{
                subcontrol-position: bottom right;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {c["hover"]};
            }}
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
                background-color: {c["pressed"]};
            }}
            QSpinBox::up-arrow {{
                image: url({up_arrow});
                width: 7px;
                height: 7px;
            }}
            QSpinBox::down-arrow {{
                image: url({down_arrow});
                width: 7px;
                height: 7px;
            }}
        """

    def _get_button_style(self, color=None, small=False):
        """Get professional button style (gray theme)."""
        c = self._c
        font_size = "11px" if small else "12px"
        padding = "4px 8px" if small else "8px 16px"

        return f"""
            QPushButton {{
                background-color: {c["surface_alt"]};
                color: {c["text_secondary"]};
                border: 1px solid {c["border"]};
                padding: {padding};
                font-weight: 500;
                font-size: {font_size};
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {c["hover_strong"]};
                border-color: {c["button_hover_border"]};
            }}
            QPushButton:pressed {{
                background-color: {c["button_pressed_bg"]};
                border-color: {c["button_pressed_border"]};
            }}
            QPushButton:disabled {{
                background-color: {c["surface_alt2"]};
                color: {c["text_disabled"]};
                border-color: {c["button_disabled_border"]};
            }}
        """

    def _create_monitoring_tag_widget(self, widget_type, value=None):
        w = None
        if widget_type == "lineedit":
            w = QLineEdit()
            w.setText(value or "")
            w.setStyleSheet(self._get_input_style())
        elif widget_type == "mode_combo":
            w = QComboBox()
            w.addItems(["Read", "Write"])
            if value:
                w.setCurrentText(value)
        elif widget_type == "type_combo":
            w = QComboBox()
            w.addItems(["Coil", "Discrete Input", "Holding Register", "Input Register"])
            if value:
                w.setCurrentText(value)
        elif widget_type == "format_combo":
            w = QComboBox()
            w.addItems([
                "Bool", "U16", "S16",
                "U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP",
                "U64", "S64", "F64", "U64_SWAP", "S64_SWAP", "F64_SWAP",
                "Hex",
            ])
            w.setCurrentText(value or "U16")
        elif widget_type == "spinbox":
            w = QSpinBox()
            one_based = getattr(self, "tag_address_one_based", True)
            minimum = 1 if one_based else 0
            maximum = 65536 if one_based else 65535
            w.setRange(minimum, maximum)
            w.setValue(value if value is not None else minimum)
            w.setStyleSheet(self._get_input_style())

        if w is not None:
            # Let a right-click bubble up to the table's own context menu (Configure
            # Alarm etc.) instead of the cell widget swallowing it for Cut/Copy/Paste.
            w.setContextMenuPolicy(Qt.NoContextMenu)
        return w
 
    def _add_monitoring_tag(self, tag_name="", mode="Read", tag_type="Coil", address=1, count=1, value_format=None,
                             comment="", insert_row=None, read_value="", raw_hex="", write_value="", timestamp="",
                             engineering_value="", enabled=True):
        # An explicit insert_row is used when rebuilding a row that's being dragged to a new
        # position (see _move_tag_row) -- otherwise fall back to the normal Add Tag behavior.
        if insert_row is None:
            selected_rows = self._get_selected_tag_rows()
            if selected_rows:
                # Insert below the last selected row
                insert_row = max(selected_rows) + 1
            else:
                # Append to end if no row selected
                insert_row = self.monitoring_tag_table.rowCount()

        self.monitoring_tag_table.insertRow(insert_row)
        self.monitoring_manager.handle_row_inserted(insert_row)

        if value_format is None:
            value_format = "Bool" if tag_type in ("Coil", "Discrete Input") else "U16"

        name_widget = self._create_monitoring_tag_widget("lineedit", tag_name)
        self.monitoring_tag_table.setCellWidget(insert_row, 0, name_widget)
        self.monitoring_tag_table.setCellWidget(insert_row, 1, self._create_monitoring_tag_widget("mode_combo", mode))
        type_widget = self._create_monitoring_tag_widget("type_combo", tag_type)
        self.monitoring_tag_table.setCellWidget(insert_row, 2, type_widget)

        address_widget = self._create_monitoring_tag_widget("spinbox", address)
        self.monitoring_tag_table.setCellWidget(insert_row, 3, address_widget)

        count_widget = self._create_monitoring_tag_widget("spinbox", count)
        count_widget.setRange(1, 125)
        self.monitoring_tag_table.setCellWidget(insert_row, 4, count_widget)

        format_widget = self._create_monitoring_tag_widget("format_combo", value_format)
        self.monitoring_tag_table.setCellWidget(insert_row, 5, format_widget)
        self.monitoring_tag_table.setCellWidget(insert_row, 6, self._create_monitoring_tag_widget("lineedit", read_value))  # Read Value
        raw_hex_widget = self._create_monitoring_tag_widget("lineedit", raw_hex)
        raw_hex_widget.setReadOnly(True)
        self.monitoring_tag_table.setCellWidget(insert_row, 7, raw_hex_widget)  # Raw (Hex)
        write_value_widget = self._create_monitoring_tag_widget("lineedit", write_value)
        self.monitoring_tag_table.setCellWidget(insert_row, 8, write_value_widget)  # Write Value
        write_value_widget.returnPressed.connect(self._on_write_value_enter)
        self.monitoring_tag_table.setCellWidget(insert_row, 9, self._create_monitoring_tag_widget("lineedit", comment))  # Comment
        self.monitoring_tag_table.setCellWidget(insert_row, 10, self._create_monitoring_tag_widget("lineedit", timestamp))  # Timestamp

        eng_value_widget = self._create_monitoring_tag_widget("lineedit", engineering_value)
        eng_value_widget.setReadOnly(True)
        self.monitoring_tag_table.setCellWidget(insert_row, 11, eng_value_widget)  # Engineering Value

        scale_widget = QCheckBox()
        scale_widget.setToolTip("Enable engineering-unit scaling for this tag")
        self.monitoring_tag_table.setCellWidget(insert_row, 12, scale_widget)  # Scale
        scale_widget.toggled.connect(self._on_scale_checkbox_toggled)

        enabled_widget = QCheckBox()
        enabled_widget.setChecked(enabled)
        enabled_widget.setToolTip(
            "When unchecked, this tag is skipped by continuous polling (Tag Monitoring's read "
            "cycle and the write-mode value refresh) without deleting the row. Manual actions "
            "(Write Selected, one-shot write via Enter) still work regardless of this."
        )
        self.monitoring_tag_table.setCellWidget(insert_row, 13, enabled_widget)  # Enabled

        # Keep "count" valid for 32-bit formats (U32/S32/F32 require even register count).
        if hasattr(format_widget, "currentTextChanged"):
            format_widget.currentTextChanged.connect(self._on_monitoring_tag_format_changed)
        if hasattr(count_widget, "valueChanged"):
            count_widget.valueChanged.connect(self._on_monitoring_tag_count_changed)
        if hasattr(address_widget, "editingFinished"):
            address_widget.editingFinished.connect(self._on_monitoring_tag_address_edited)
        if hasattr(type_widget, "currentTextChanged"):
            type_widget.currentTextChanged.connect(self._on_monitoring_tag_address_or_type_changed)
        if hasattr(name_widget, "editingFinished"):
            name_widget.editingFinished.connect(self._on_monitoring_tag_name_edited)

        self._coerce_monitoring_tag_count(insert_row)
        self._ensure_unique_monitoring_tag_address(insert_row)
        
        # Auto-select the newly inserted row
        self.monitoring_tag_table.selectRow(insert_row)
        self.monitoring_tag_table.setCurrentCell(insert_row, 0)

    def _capture_tag_row(self, row):
        """Snapshot every column of a Tags row so it can be torn down and rebuilt at a new
        row index -- used for drag-and-drop reordering, since the cell contents are live
        QWidgets, not plain QTableWidgetItems Qt's built-in row move can relocate on its own."""
        def widget_at(column):
            return self.monitoring_tag_table.cellWidget(row, column)

        name_widget, mode_widget, type_widget = widget_at(0), widget_at(1), widget_at(2)
        address_widget, count_widget, format_widget = widget_at(3), widget_at(4), widget_at(5)
        read_value_widget, raw_hex_widget = widget_at(6), widget_at(7)
        write_value_widget, comment_widget, timestamp_widget = widget_at(8), widget_at(9), widget_at(10)
        eng_value_widget = widget_at(11)
        enabled_widget = widget_at(13)

        return {
            "tag_name": name_widget.text() if name_widget else "",
            "mode": mode_widget.currentText() if mode_widget else "Read",
            "tag_type": type_widget.currentText() if type_widget else "Coil",
            "address": address_widget.value() if address_widget else 1,
            "count": count_widget.value() if count_widget else 1,
            "value_format": format_widget.currentText() if format_widget else "U16",
            "read_value": read_value_widget.text() if read_value_widget else "",
            "raw_hex": raw_hex_widget.text() if raw_hex_widget else "",
            "write_value": write_value_widget.text() if write_value_widget else "",
            "comment": comment_widget.text() if comment_widget else "",
            "timestamp": timestamp_widget.text() if timestamp_widget else "",
            "engineering_value": eng_value_widget.text() if eng_value_widget else "",
            "enabled": enabled_widget.isChecked() if enabled_widget else True,
        }

    def _move_tag_row(self, source_row, target_row):
        """Move a Tags row to a new position by rebuilding it there, preserving its live
        values and alarm configuration. Called from TagTableWidget's row-header drag handler.

        source_row/target_row use the same semantics as QHeaderView.sectionMoved's
        oldVisualIndex/newVisualIndex: target_row is where the row ends up in the *final*
        list, i.e. plain list.pop(source_row); list.insert(target_row, item) semantics --
        which is exactly what QTableWidget.insertRow(target_row) does too. No off-by-one
        adjustment is needed here; target_row is used as-is.
        """
        row_count = self.monitoring_tag_table.rowCount()
        if source_row == target_row or not (0 <= source_row < row_count) or not (0 <= target_row < row_count):
            return

        data = self._capture_tag_row(source_row)
        alarm = self.monitoring_manager.tag_alarms.get(source_row)
        scaling = self.monitoring_manager.tag_scaling.get(source_row)

        self.monitoring_tag_table.removeRow(source_row)
        self.monitoring_manager.handle_row_removed(source_row)
        # Every row's widgets get rebuilt fresh below, so any tracked highlight-by-index
        # from before the move is meaningless now -- drop it (see _remove_monitoring_tag).
        self._highlighted_tag_rows.clear()

        self._add_monitoring_tag(insert_row=target_row, **data)

        if alarm:
            self.monitoring_manager.tag_alarms[target_row] = alarm

        if scaling:
            self.monitoring_manager.tag_scaling[target_row] = scaling
            scale_widget = self.monitoring_tag_table.cellWidget(target_row, 12)
            if scale_widget:
                try:
                    self._updating_tag_table = True
                    scale_widget.setChecked(True)
                finally:
                    self._updating_tag_table = False

        self._log(f"Moved tag '{data['tag_name']}' to row {target_row + 1}")

    def _on_tag_address_mode_changed(self, checked):
        """Toggle Tags between user-facing 1-based and protocol 0-based address input."""
        self.tag_address_one_based = not bool(checked)
        minimum = 1 if self.tag_address_one_based else 0
        maximum = 65536 if self.tag_address_one_based else 65535

        try:
            self._updating_tag_table = True
            for row in range(self.monitoring_tag_table.rowCount()):
                address_widget = self.monitoring_tag_table.cellWidget(row, 3)
                if not address_widget or not hasattr(address_widget, "setRange"):
                    continue
                current = address_widget.value()
                address_widget.setRange(minimum, maximum)
                if current < minimum:
                    address_widget.setValue(minimum)
        finally:
            self._updating_tag_table = False

        self._update_tag_address_header()
        self._log(f"Tag address mode: {'1-based' if self.tag_address_one_based else '0-based'}")

    def _update_tag_address_header(self):
        """Label the Address column with the active addressing mode, so it's visible right
        where a user is typing an address instead of only on the far-off toolbar checkbox."""
        mode = "1-based" if self.tag_address_one_based else "0-based"
        header_item = QTableWidgetItem(f"Address ({mode})")
        header_item.setToolTip(
            "1-based: address 1 is sent as protocol offset 0.\n"
            "0-based: address 0 is sent as protocol offset 0."
        )
        self.monitoring_tag_table.setHorizontalHeaderItem(3, header_item)

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

    def _on_monitoring_tag_name_edited(self, _value=None):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 0)
        if row is None:
            return
        name = sender.text()
        if not self._tag_name_used_in_script(name):
            # The strict identifier grammar only matters for a tag a Script actually
            # references by bare name -- see _tag_name_used_in_script.
            return
        error = validate_tag_name(name)
        if error:
            QMessageBox.warning(self, "Invalid Tag Name", error)
            try:
                self._updating_tag_table = True
                sender.clear()
            finally:
                self._updating_tag_table = False

    def _tag_name_used_in_script(self, name):
        """validate_tag_name's strict [A-Za-z_][A-Za-z0-9_]* rule exists because tag names
        are bare tokens in the WRITE/READ/LET script grammar -- the script parser
        (_parse_write_args/_parse_read_args in script_widget.py) already enforces that same
        grammar itself, independently, at parse time, whenever a script line actually
        references a tag by name. So this only needs to gate the UI-level warning, not
        correctness: a tag never mentioned in the current Script text is free to use any
        name (spaces, punctuation, etc.), since nothing ever tokenizes it as an identifier.
        A whole-word text search is a deliberately simple heuristic (vs. re-parsing the
        script) -- good enough to catch the common case without a fragile dependency on the
        rest of the script's text being currently valid."""
        name = name.strip()
        if not name or not hasattr(self, "script_widget"):
            return False
        return re.search(r"\b" + re.escape(name) + r"\b", self.script_widget.editor.toPlainText()) is not None

    def _on_monitoring_tag_address_edited(self, _value=None):
        # Bound to editingFinished (not valueChanged) so the duplicate-address
        # check runs once the user commits a value, instead of after every
        # keystroke -- otherwise typing "100" gets mutated mid-entry whenever
        # a shorter prefix (e.g. "1") collides with another row's address.
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 3)
        if row is None:
            return
        self._ensure_unique_monitoring_tag_address(row)

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

        width = format_word_width(value_format) if tag_type in ("Holding Register", "Input Register") else 1
        try:
            self._updating_tag_table = True
            if width > 1:
                count_widget.setSingleStep(width)
                count_widget.setMaximum(124)  # a multiple of both 2 and 4, the widths in play
                if count_widget.value() < width:
                    count_widget.setValue(width)
                elif count_widget.value() % width != 0:
                    count_widget.setValue(count_widget.value() + (width - count_widget.value() % width))
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
            self.monitoring_manager.handle_row_removed(row)
        # Removed rows' widgets are gone with them; nothing left to un-highlight, but
        # the tracked set still holds now-meaningless indices -- drop them so a future
        # diff doesn't skip highlighting a row that reused a stale index.
        self._highlighted_tag_rows.clear()
        self._update_tag_buttons_state()

    def _show_tag_context_menu(self, pos):
        table = self.monitoring_tag_table
        row = table.rowAt(pos.y())
        if row < 0:
            return
        selected_rows = sorted(self._get_selected_tag_rows())
        if row not in selected_rows:
            # Right-clicking a row that isn't already selected should act on that row,
            # not whatever was selected before -- same convention as the Raw Data table.
            table.selectRow(row)
            selected_rows = [row]

        menu = QMenu(self)
        alarm_action = menu.addAction("Configure Alarm...")
        menu.addSeparator()
        copy_action = menu.addAction("Copy Row(s)")
        action = menu.exec(table.viewport().mapToGlobal(pos))
        if action == alarm_action:
            self._configure_tag_alarm(row)
        elif action == copy_action:
            self._copy_tag_rows(selected_rows)

    def _copy_tag_rows(self, rows):
        """Copy every column of the given Tags-table rows, tab-separated, one line per row --
        reads the live cell widgets directly (not the underlying tag data) so it reflects
        exactly what's on screen, including read-only Read Value/Raw Hex/Engineering Value."""
        if not rows:
            return
        table = self.monitoring_tag_table
        lines = []
        for row in sorted(rows):
            cells = [self._tag_cell_text(table.cellWidget(row, col)) for col in range(table.columnCount())]
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    @staticmethod
    def _tag_cell_text(widget):
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return "Yes" if widget.isChecked() else "No"
        if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            return str(widget.value())
        if isinstance(widget, QLineEdit):
            return widget.text()
        return ""

    def _show_tag_column_picker(self, pos):
        """Right-click on the Tags table's column header: a checklist of every column,
        toggling setColumnHidden -- lets a user hide columns they don't care about (e.g.
        Comment, Timestamp) without touching the underlying data, same spirit as the
        Enabled checkbox skipping a row without deleting it."""
        header = self.monitoring_tag_table.horizontalHeader()
        menu = QMenu(self)
        for col in range(self.monitoring_tag_table.columnCount()):
            header_item = self.monitoring_tag_table.horizontalHeaderItem(col)
            label = header_item.text() if header_item else f"Column {col}"
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.monitoring_tag_table.isColumnHidden(col))
            action.toggled.connect(lambda checked, c=col: self.monitoring_tag_table.setColumnHidden(c, not checked))
        menu.exec(header.mapToGlobal(pos))

    def _configure_tag_alarm(self, row):
        tags_by_row = {tag["row"]: tag for tag in self._get_monitoring_tags()}
        tag = tags_by_row.get(row)
        if not tag:
            QMessageBox.warning(self, "No Tag", "This row doesn't have a configured tag yet.")
            return

        existing = self.monitoring_manager.tag_alarms.get(row)
        dialog = AlarmConfigDialog(tag, existing, self)
        if dialog.exec() == QDialog.Accepted:
            self.monitoring_manager.tag_alarms[row] = dialog.values()
            self._log(f"Alarm configured for {tag['name']}")

    def _on_scale_checkbox_toggled(self, checked):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 12)
        if row is None:
            return

        if not checked:
            self.monitoring_manager.tag_scaling.pop(row, None)
            eng_widget = self.monitoring_tag_table.cellWidget(row, 11)
            if eng_widget:
                eng_widget.clear()
            return

        existing = self.monitoring_manager.tag_scaling.get(row)
        dialog = ScalingConfigDialog(existing, self)
        if dialog.exec() == QDialog.Accepted:
            self.monitoring_manager.tag_scaling[row] = dialog.values()
        else:
            try:
                self._updating_tag_table = True
                sender.setChecked(False)
            finally:
                self._updating_tag_table = False

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
            self.monitoring_manager.tag_alarms.clear()
            self._update_tag_buttons_state()
            self._log("All tags removed")

    def _update_tag_buttons_state(self):
        selected = bool(self._get_selected_tag_rows())
        has_tags = self.monitoring_tag_table.rowCount() > 0
        self.remove_tag_btn.setEnabled(selected)
        self.remove_all_tags_btn.setEnabled(has_tags)

    def _get_selected_tag_rows(self):
        """Rows Qt's own selection model actually considers selected -- deliberately
        NOT falling back to currentRow() when that set is empty. currentRow() stays
        put after clearSelection() (clicking empty space doesn't reset it), so that
        fallback used to leave a row silently counted as "selected" for Write
        Selected / Remove Tag well after the user had visually deselected it."""
        return {index.row() for index in self.monitoring_tag_table.selectedIndexes()}

    def _on_tag_table_selection_changed(self):
        """Every Tags-table cell is a setCellWidget() (QComboBox/QSpinBox/QLineEdit),
        which paints its own opaque background over Qt's normal ::item:selected
        highlight -- so without this, selecting a row gave zero visual feedback.
        Diff against the last-painted set instead of repainting every row every time,
        since this fires continuously during a drag-select."""
        new_selected = self._get_selected_tag_rows()
        for row in self._highlighted_tag_rows - new_selected:
            self._set_tag_row_highlight(row, False)
        for row in new_selected - self._highlighted_tag_rows:
            self._set_tag_row_highlight(row, True)
        self._highlighted_tag_rows = new_selected

    def _set_tag_row_highlight(self, row, highlighted):
        """QLineEdit/QSpinBox cells carry their own local stylesheet
        (_get_input_style(), set directly on the widget) -- a local stylesheet wins
        over a same-specificity rule cascaded down from an ancestor's stylesheet, so
        the tagRowSelected property selector in _get_table_style() has no effect on
        them. Override those two types' own stylesheet directly instead; QComboBox/
        QCheckBox have no local stylesheet, so the property selector still works
        fine for them."""
        if not (0 <= row < self.monitoring_tag_table.rowCount()):
            return
        c = self._c
        input_highlight = (
            f"QSpinBox, QLineEdit {{ background-color: {c['selection_bg']}; color: {c['selection_text']}; }}"
            if highlighted else ""
        )
        for col in range(self.monitoring_tag_table.columnCount()):
            widget = self.monitoring_tag_table.cellWidget(row, col)
            if widget is None:
                continue
            if isinstance(widget, (QLineEdit, QSpinBox)):
                widget.setStyleSheet(self._get_input_style() + input_highlight)
            else:
                widget.setProperty("tagRowSelected", highlighted)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

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
        if hasattr(self, 'write_selected_btn'):
            self.write_selected_btn.clicked.connect(self._write_selected_tags)
        if hasattr(self, 'write_all_btn'):
            self.write_all_btn.clicked.connect(self._write_all_tags)
        if hasattr(self, 'tags_log_btn'):
            self.tags_log_btn.clicked.connect(self._toggle_tags_logging)

    def _toggle_tags_logging(self):
        """Start or stop CSV logging of every Tags poll tick."""
        if self.monitoring_manager.is_logging():
            self.monitoring_manager.stop_csv_logging()
            self.tags_log_btn.setText("Log to CSV")
            self._log("Stopped logging Tags data to CSV")
            return

        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getSaveFileName(self, "Log Tags to CSV", "tags_log.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            self.monitoring_manager.start_csv_logging(file_path)
        except OSError as e:
            QMessageBox.warning(self, "Logging Failed", f"Could not open file for logging: {e}")
            return
        self.tags_log_btn.setText("Stop Logging")
        self._log(f"Logging Tags data to {file_path}")

    def _apply_connection_settings(self, vals):
        """Copy a dict of connection fields onto the live attributes _connect() reads --
        the shape ConnectionSettingsDialog.get_values() produces, and also what a loaded
        Session file's "connection" section uses, so both go through the same one place."""
        self.connection_mode = vals['mode']
        self.target_ip = vals['ip']
        self.target_port = vals['port']
        self.target_unit_id = vals['unit']
        self.serial_port = vals['serial_port']
        self.baudrate = vals['baudrate']
        self.parity = vals['parity']
        self.stopbits = vals['stopbits']
        self.bytesize = vals['bytesize']
        self.serial_framer = vals['serial_framer']
        self.fast_lan_mode = vals['fast_lan_mode']
        self.interface_ip = vals['interface_ip']

    def _show_connection_settings(self, serial_overrides=None):
        """Show the connection settings dialog."""
        dialog = ConnectionSettingsDialog(self, self.connection_history, self, serial_overrides=serial_overrides)
        if dialog.exec() == QDialog.Accepted:
            vals = dialog.get_values()
            self._apply_connection_settings(vals)
            self.connection_history = vals['history']
            self._record_connection_history()
            self._update_connection_info()
            self._save_settings()
        elif dialog.scan_requested_port is not None:
            self._serial_discovery(dialog.scan_requested_port)

    def _connect(self):
        """Connect to Modbus server."""
        target = self._target_description()
        unit_id = self.target_unit_id
        try:
            self.status_indicator.set_connection_info(f"Connecting to {target}...")
            self.status_indicator.set_status("connecting")
            self._set_connection_controls(connected=False, connecting=True)

            if self.connection_mode == "serial":
                self.modbus = ModbusClient(
                    unit_id=unit_id, mode="serial", serial_port=self.serial_port,
                    baudrate=self.baudrate, parity=self.parity, stopbits=self.stopbits, bytesize=self.bytesize,
                    serial_framer=self.serial_framer,
                )
            elif self.fast_lan_mode:
                self.modbus = ModbusClient(
                    self.target_ip, self.target_port, unit_id, timeout=0.2, retries=0,
                    source_address=self.interface_ip,
                )
            else:
                self.modbus = ModbusClient(self.target_ip, self.target_port, unit_id, source_address=self.interface_ip)

            if self.modbus.connect():
                conn_info = f"{target} (Unit {unit_id})"
                self.status_indicator.set_connection_info(conn_info)
                self.status_indicator.set_status("connected")
                self.connection_status.setText(f"Connected: {conn_info}")
                self._set_connection_controls(connected=True)
                self._write_confirm_suppressed = False
                self._apply_pending_write_bounds()

                self._record_connection_history()
                self._save_settings()

                self._log(f"Connected to Modbus server at {target} (Unit ID: {unit_id})")
                self._reconnect_attempt = 0
                self._reconnecting = False
                self._reconnect_watchdog_timer.start(self.WATCHDOG_HEALTHY_INTERVAL_MS)
            else:
                self.status_indicator.set_status("error")
                self.status_indicator.set_connection_info("Connection failed")
                self._set_connection_controls(connected=False)
                self._log("Failed to connect to Modbus server")
                self._show_connection_error_dialog(target, unit_id, "Connection failed")

        except Exception as e:
            self.status_indicator.set_status("error")
            self.status_indicator.set_connection_info("Error encountered")
            self._set_connection_controls(connected=False)
            self._log(f"Connection error: {e}")
            self._show_connection_error_dialog(target, unit_id, str(e))

    def _disconnect(self):
        """Disconnect from Modbus server."""
        # A user-initiated disconnect should never trigger auto-reconnect -- stop the
        # watchdog before clearing self.modbus, since it checks that for its own "still
        # relevant?" guard.
        self._reconnect_watchdog_timer.stop()
        self._reconnecting = False
        self._reconnect_attempt = 0
        self._monitoring_paused_by_disconnect = False

        # A Scanner worker thread, or Tag Monitoring's poll worker, may still be mid-read
        # on self.modbus -- stop and wait for each before tearing the connection down,
        # otherwise it can hit a closed/replaced client from another thread.
        if hasattr(self, 'register_scanner_widget'):
            self.register_scanner_widget.stop_all_scans()
        self.monitoring_manager.wait_for_idle()

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

    def _check_connection_watchdog(self):
        """Runs on its own timer after a successful connect(). While the connection is
        healthy this just re-arms itself; if it finds the connection dropped, it retries
        with exponential backoff until it recovers, and restarts Tags monitoring if that
        was auto-stopped by the drop (see the failed_count == len(tags) paths)."""
        if not self.modbus:
            return  # user disconnected, or another window's connection object -- nothing to watch

        if self.modbus.is_connected():
            if self._reconnecting:
                self._on_reconnected()
            self._reconnect_watchdog_timer.start(self.WATCHDOG_HEALTHY_INTERVAL_MS)
            return

        self._reconnecting = True
        self._reconnect_attempt += 1
        target = self._target_description()
        self.status_indicator.set_connection_info(f"Reconnecting to {target} (attempt {self._reconnect_attempt})...")
        self.status_indicator.set_status("connecting")
        self._log(f"Connection lost - reconnect attempt {self._reconnect_attempt}")

        if self.modbus.connect():
            self._on_reconnected()
            self._reconnect_watchdog_timer.start(self.WATCHDOG_HEALTHY_INTERVAL_MS)
        else:
            delay = min(
                self.RECONNECT_BASE_DELAY_MS * (2 ** (self._reconnect_attempt - 1)),
                self.RECONNECT_MAX_DELAY_MS,
            )
            self._reconnect_watchdog_timer.start(delay)

    def _on_reconnected(self):
        self._reconnecting = False
        self._reconnect_attempt = 0
        conn_info = f"{self._target_description()} (Unit {self.target_unit_id})"
        self.status_indicator.set_connection_info(conn_info)
        self.status_indicator.set_status("connected")
        self.connection_status.setText(f"Connected: {conn_info}")
        self._set_connection_controls(connected=True)
        self._log("Reconnected to Modbus server")

        if self._monitoring_paused_by_disconnect:
            self._monitoring_paused_by_disconnect = False
            self._start_monitoring()

    def _show_connection_error_dialog(self, target_description, unit_id, error_message):
        """Show connection error dialog with detailed information."""
        try:
            if self.connection_mode == "serial":
                tips = (
                    "• Check that the COM port exists and isn't already open in another program<br>"
                    "• Verify baud rate, parity, and stop bits match the device<br>"
                    "• Check the cable/adapter and that the device is powered<br>"
                    "• Check if the Unit ID matches the device configuration"
                )
            else:
                tips = (
                    "• Check if the Modbus server is running<br>"
                    "• Verify the IP address and port number<br>"
                    "• Ensure network connectivity to the device<br>"
                    "• Check if the Unit ID matches the device configuration<br>"
                    "• Verify firewall settings are not blocking the connection"
                )

            # Create error dialog
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Warning)
            dialog.setWindowTitle("Connection Failed")
            dialog.setText(f"Failed to connect to Modbus server")
            dialog.setInformativeText(f"""
<strong>Connection Details:</strong><br>
Target: {target_description}<br>
Unit ID: {unit_id}<br><br>
<strong>Error:</strong> {error_message}<br><br>
<strong>Possible Solutions:</strong><br>
{tips}
            """)
            dialog.setStandardButtons(QMessageBox.Ok)
            dialog.setStyleSheet(f"""
                QMessageBox {{
                    background-color: {self._c["surface"]};
                }}
                QMessageBox QTextEdit {{
                    background-color: {self._c["surface_alt2"]};
                    border: 1px solid {self._c["border"]};
                    padding: 8px;
                }}
            """)
            dialog.exec()
        except Exception as e:
            self._log(f"Error showing connection dialog: {e}")

    def _get_monitoring_tags(self):
        """Get all monitoring tags from the table."""
        return self.monitoring_manager.get_monitoring_tags()

    TAG_ROW_FIELDS = ['Tag Name', 'Mode', 'Type', 'Address', 'Count', 'Format', 'Comment', 'Enabled',
                      'Scale Enabled', 'Scale Mode', 'Raw Min', 'Raw Max', 'Scaled Min',
                      'Scaled Max', 'Factor', 'Value Type']

    def _build_tag_export_rows(self):
        """The Tags table as a list of plain dicts, one per tag, in the exact shape both
        CSV export and a saved Session file use -- a single source of truth so the two
        can never drift out of sync with each other."""
        rows = []
        for tag in self._get_monitoring_tags():
            scaling = self.monitoring_manager.tag_scaling.get(tag['row'])
            rows.append({
                'Tag Name': tag['name'],
                'Mode': tag['mode'],
                'Type': tag['type'],
                'Address': tag['address'],
                'Count': tag['count'],
                'Format': tag['format'],
                'Comment': tag['comment'],
                'Enabled': tag['enabled'],
                'Scale Enabled': bool(scaling),
                'Scale Mode': scaling.get('mode', 'linear') if scaling else '',
                'Raw Min': scaling.get('raw_min', '') if scaling else '',
                'Raw Max': scaling.get('raw_max', '') if scaling else '',
                'Scaled Min': scaling.get('scaled_min', '') if scaling else '',
                'Scaled Max': scaling.get('scaled_max', '') if scaling else '',
                'Factor': scaling.get('factor', '') if scaling else '',
                'Value Type': scaling.get('value_type', '') if scaling else '',
            })
        return rows

    def _apply_imported_tag_rows(self, rows):
        """Clears the Tags table and repopulates it from `rows` (the same per-tag dict
        shape _build_tag_export_rows produces) -- shared by CSV import and Load Session,
        so a row from either source is handled by the exact same tolerant, older-export
        -friendly logic. Returns the number of tags actually imported."""
        self.monitoring_tag_table.setRowCount(0)
        self.monitoring_manager.tag_scaling.clear()

        imported_count = 0
        for row in rows:
            try:
                new_row = self.monitoring_tag_table.rowCount()
                # Older exports have no "Enabled" column -- absent means every tag
                # was implicitly enabled, since the concept didn't exist yet.
                enabled = str(row.get('Enabled', 'True')).strip().lower() in ('true', '1', 'yes')
                self._add_monitoring_tag(
                    tag_name=row.get('Tag Name', '').strip(),
                    mode=row.get('Mode', 'Read').strip(),
                    tag_type=row.get('Type', 'Coil').strip(),
                    address=int(row.get('Address', 0)),
                    count=int(row.get('Count', 1)),
                    value_format=row.get('Format', 'U16').strip(),
                    comment=row.get('Comment', '').strip(),
                    enabled=enabled,
                )
                imported_count += 1
            except (ValueError, KeyError) as e:
                self._log(f"Skipping invalid row: {e}")
                continue

            # Older exports have no scaling columns -- absent means "not scaled",
            # not an error.
            scale_enabled = str(row.get('Scale Enabled', '')).strip().lower() in ('true', '1', 'yes')
            if not scale_enabled:
                continue
            # Older exports have no "Scale Mode" column -- linear was the only
            # mode that existed when they were written.
            scale_mode = (row.get('Scale Mode', '') or 'linear').strip().lower()
            try:
                if scale_mode == 'multiply':
                    scaling = {
                        'enabled': True,
                        'mode': 'multiply',
                        'factor': float(row.get('Factor', 1) or 1),
                        'value_type': row.get('Value Type', '').strip() or 'Real',
                    }
                else:
                    scaling = {
                        'enabled': True,
                        'mode': 'linear',
                        'raw_min': float(row.get('Raw Min', 0) or 0),
                        'raw_max': float(row.get('Raw Max', 0) or 0),
                        'scaled_min': float(row.get('Scaled Min', 0) or 0),
                        'scaled_max': float(row.get('Scaled Max', 0) or 0),
                        'value_type': row.get('Value Type', '').strip() or 'Real',
                    }
            except (ValueError, TypeError) as e:
                self._log(f"Skipping invalid scaling config on imported row: {e}")
                continue
            self.monitoring_manager.tag_scaling[new_row] = scaling
            scale_widget = self.monitoring_tag_table.cellWidget(new_row, 12)
            if scale_widget:
                try:
                    self._updating_tag_table = True
                    scale_widget.setChecked(True)
                finally:
                    self._updating_tag_table = False

        return imported_count

    def _export_tags_csv(self):
        """Export tags to CSV file."""
        try:
            from PySide6.QtWidgets import QFileDialog

            row_count = self.monitoring_tag_table.rowCount()
            if row_count == 0:
                QMessageBox.warning(self, "No Tags", "No tags to export. Please add tags first.")
                return

            rows = self._build_tag_export_rows()
            if not rows:
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
                writer = csv.DictWriter(csvfile, fieldnames=self.TAG_ROW_FIELDS)
                writer.writeheader()
                writer.writerows(rows)

            self._log(f"Exported {len(rows)} tags to {file_path}")
            QMessageBox.information(self, "Export Complete", f"Successfully exported {len(rows)} tags to CSV file!")

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
                if not reader.fieldnames or not all(field in reader.fieldnames for field in required_fields):
                    QMessageBox.warning(self, "Invalid CSV",
                        "CSV file must contain columns: Tag Name, Mode, Type, Address, Count, Format, Comment")
                    return

                imported_count = self._apply_imported_tag_rows(list(reader))

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

            if hasattr(self, 'register_scanner_widget'):
                self.register_scanner_widget.refresh_connection_state()

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

        # tag_offset_checkbox is deliberately left alone here -- it's a local address-
        # interpretation preference, not a live-connection dependency (see its construction
        # above); only actively monitoring should disable it, already enforced by
        # _set_tag_editor_enabled.

        if hasattr(self, 'register_scanner_widget'):
            self.register_scanner_widget.refresh_connection_state()

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
            
            elif tab_text == "Tags":
                # Auto-disable live monitoring when going to tags tab
                if hasattr(self, 'address_table_widget'):
                    if self.address_table_widget.monitoring_checkbox.isChecked():
                        # Uncheck to disable live monitoring
                        self.address_table_widget.monitoring_checkbox.setChecked(False)
                    self.address_table_widget.update_monitoring_availability()

                # Enable tag monitoring controls -- but not if monitoring is already
                # running, or returning to this tab would wrongly re-enable Start and
                # make an active monitoring session look stopped.
                if hasattr(self, 'tag_start_monitoring_btn'):
                    if hasattr(self, 'modbus') and self.modbus and self.modbus.is_connected():
                        self.tag_start_monitoring_btn.setEnabled(not self.monitoring_active)
                if hasattr(self, 'tag_stop_monitoring_btn'):
                    self.tag_stop_monitoring_btn.setEnabled(self.monitoring_active)

        except Exception as e:
            self._log(f"Error in tab change: {e}")

    def _on_write_value_enter(self):
        """Enter in a Write Value cell writes just that tag -- mirrors the Modbus Poll
        workflow of typing a value and hitting Enter, without needing to select the row
        and click Write Selected first."""
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, 8)
        if row is None:
            return
        self.monitoring_tag_table.selectRow(row)
        self.monitoring_tag_table.setCurrentCell(row, 8)
        self._write_selected_tags()

    def _write_selected_tags(self):
        """Write selected rows from the integrated Tags table."""
        if not self._check_connection():
            return

        selected_rows = self._get_selected_tag_rows()
        if not selected_rows:
            QMessageBox.warning(self, "No Tag Selected", "Please select at least one tag row to write.")
            return

        self._write_tag_rows(selected_rows)

    def _write_all_tags(self):
        """Write every Write-mode tag in the table, regardless of selection or of the
        per-tag Enabled checkbox -- same "manual actions always work" carve-out as
        Write Selected and the one-shot Enter write (see the Enabled checkbox's
        tooltip), since Enabled only pauses continuous polling, not a deliberate
        one-off write the user just asked for."""
        if not self._check_connection():
            return

        all_rows = set(range(self.monitoring_tag_table.rowCount()))
        if not all_rows:
            QMessageBox.warning(self, "No Tags", "There are no tags to write.")
            return

        self._write_tag_rows(all_rows)

    def _write_tag_rows(self, rows):
        """Shared by Write Selected and Write All -- validates and writes whichever
        row set the caller collected."""
        tags_to_write = []
        for row in rows:
            mode_widget = self.monitoring_tag_table.cellWidget(row, 1)
            write_value_widget = self.monitoring_tag_table.cellWidget(row, 8)
            
            if not mode_widget or not write_value_widget:
                continue
                
            mode = mode_widget.currentText()
            write_value = write_value_widget.text().strip()
            
            if mode != "Write":
                self._log(f"Skipped row {row + 1}: tag is in Read mode")
                continue
                
            if not write_value:
                self._log(f"Skipped row {row + 1}: no write value specified")
                continue
                
            # Get tag details
            name_widget = self.monitoring_tag_table.cellWidget(row, 0)
            type_widget = self.monitoring_tag_table.cellWidget(row, 2)
            address_widget = self.monitoring_tag_table.cellWidget(row, 3)
            count_widget = self.monitoring_tag_table.cellWidget(row, 4)
            format_widget = self.monitoring_tag_table.cellWidget(row, 5)
            comment_widget = self.monitoring_tag_table.cellWidget(row, 9)

            if not all([name_widget, type_widget, address_widget, count_widget, format_widget, comment_widget]):
                continue
                
            tag = {
                "name": name_widget.text().strip(),
                "mode": mode,
                "type": type_widget.currentText(),
                "address": address_widget.value(),
                "count": count_widget.value(),
                "format": format_widget.currentText(),
                "comment": comment_widget.text().strip(),
                "write_value": write_value,
                "row": row
            }
            
            tags_to_write.append(tag)

        if not tags_to_write:
            QMessageBox.warning(self, "No Valid Tags", "No write-mode tags with values found.")
            return

        if not self._confirm_write(tags_to_write):
            self._log("Write cancelled by user")
            return

        wrote_any = False
        was_monitoring = self.monitoring_active

        if was_monitoring:
            self.monitoring_timer.stop()
            self._log("Safety interlock: monitoring paused while write request is active")

        try:
            for tag in tags_to_write:
                try:
                    self._validate_tag_request(tag, "write")
                    if not self._begin_modbus_operation(tag, "write"):
                        self._log(f"Safety interlock: skipped write for {tag['name']} because the range is busy")
                        continue

                    start_time = time.perf_counter()
                    try:
                        success, written_value, write_status = self._write_tag(tag)
                    finally:
                        self._end_modbus_operation(tag, "write")
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    self._display_raw_data(
                        f"Tag[{tag['name']}] Write", written_value if success else None, elapsed_ms,
                        function_code_for(tag["type"], is_write=True, count=tag.get("count", 1)),
                    )

                    if success:
                        wrote_any = True
                        timestamp = time.strftime("%H:%M:%S")
                        # Update the Write Value column in the integrated table
                        write_value_widget = self.monitoring_tag_table.cellWidget(tag["row"], 8)
                        if write_value_widget:
                            write_value_widget.setText(str(written_value))

                        # Update timestamp
                        timestamp_widget = self.monitoring_tag_table.cellWidget(tag["row"], 10)
                        if timestamp_widget:
                            timestamp_widget.setText(timestamp)
                            
                        self._log(f"{write_status}: {tag['name']} at {tag['address']} = {written_value}")
                    else:
                        self._log(f"{write_status}: {tag['name']}")
                except ValueError as e:
                    self._log(f"Invalid write value for {tag['name']}: {e}")
                except Exception as e:
                    self._log(f"Write error for {tag['name']}: {e}")
        finally:
            if was_monitoring and self.monitoring_active:
                self.monitoring_timer.start(self.tag_monitoring_interval.value())
                self._log("Safety interlock: monitoring resumed after write request")

        if wrote_any:
            self._log(f"Successfully wrote {len(tags_to_write)} tag(s)")

    def _confirm_write(self, tags_to_write):
        """Ask before any value actually reaches the wire -- mirrors the confirm
        already required for "Remove All Tags" (a data-loss risk), extended to writes
        (a real-equipment risk). Defaults to No so a reflexive Enter doesn't confirm it.

        Includes a "don't ask again" checkbox scoped to the CURRENT connection only
        (cleared on every new connect(), see _connect) -- unlike SafetyWarningDialog's
        permanent, no-way-back suppression, this can't silently stay off for months on
        a box someone else later points at live equipment."""
        if self._write_confirm_suppressed:
            return True

        max_listed = 8
        lines = [
            f"  {tag['name']} @ {tag['address']} ({tag['type']}) = {tag['write_value']}"
            for tag in tags_to_write[:max_listed]
        ]
        if len(tags_to_write) > max_listed:
            lines.append(f"  ...and {len(tags_to_write) - max_listed} more")

        plural = "s" if len(tags_to_write) != 1 else ""
        message = (
            f"About to write {len(tags_to_write)} value{plural} to the connected device:\n\n"
            + "\n".join(lines)
            + "\n\nContinue?"
        )

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Confirm Write")
        box.setText(message)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        suppress_checkbox = QCheckBox("Don't ask again for this connection")
        box.setCheckBox(suppress_checkbox)
        reply = box.exec()

        confirmed = reply == QMessageBox.Yes
        if confirmed and suppress_checkbox.isChecked():
            self._write_confirm_suppressed = True
        return confirmed

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

        word_width = format_word_width(base_format)
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
                elif all(ch in "01" for ch in token) and 1 <= len(token) <= 16:
                    # A full 16-bit pattern (e.g. 0000000000000101) sets individual bits directly
                    registers.append(int(token, 2))
                else:
                    raise ValueError("BOOL values must be 0/1, true/false, on/off, or a bit pattern like 0000000000000101")
                continue

            if base_format in ("U32", "S32", "F32", "U64", "S64", "F64"):
                bit_width = word_width * 16
                if base_format in ("F32", "F64"):
                    num = float(token)
                    if not math.isfinite(num):
                        raise ValueError(f"{base_format} must be a finite number")
                    byte_len = word_width * 2
                    struct_fmt = ">f" if base_format == "F32" else ">d"
                    raw_int = int.from_bytes(struct.pack(struct_fmt, num), "big", signed=False)
                else:
                    num = int(token, 10)
                    if base_format.startswith("U"):
                        max_val = (1 << bit_width) - 1
                        if num < 0 or num > max_val:
                            raise ValueError(f"{base_format} out of range (0..{max_val})")
                        raw_int = num
                    else:
                        min_val = -(1 << (bit_width - 1))
                        max_val = (1 << (bit_width - 1)) - 1
                        if num < min_val or num > max_val:
                            raise ValueError(f"{base_format} out of range ({min_val}..{max_val})")
                        raw_int = num & ((1 << bit_width) - 1)

                # Split into `word_width` 16-bit registers, most-significant first (the same
                # word order the U32/S32/F32 case always used) -- swap_words reverses that,
                # same convention _decode_register_values uses so a value written here reads
                # back identically.
                words = [(raw_int >> shift) & 0xFFFF for shift in range(bit_width - 16, -1, -16)]
                if swap_words:
                    words.reverse()
                registers.extend(words)
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
        minimum_address = 1 if self.tag_address_one_based else 0
        maximum_address = 65536 if self.tag_address_one_based else 65535
        if user_address < minimum_address or user_address > maximum_address:
            raise ValueError(f"address must be between {minimum_address} and {maximum_address}")

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
                width = format_word_width(value_format)
                if width > 1 and (tag["count"] % width != 0):
                    raise ValueError(f"{value_format} requires count to be a multiple of {width}")
            return

        if tag["type"] in ("Discrete Input", "Input Register"):
            raise ValueError(f"{tag['type']} is read-only")
        if tag["type"] == "Coil" and tag["count"] > 1968:
            raise ValueError("multiple-coil writes are limited to 1968 values")
        if tag["type"] == "Holding Register" and tag["count"] > 123:
            raise ValueError("multiple-register writes are limited to 123 values")
        if tag["type"] == "Holding Register":
            value_format = (tag.get("format") or "U16").strip().upper()
            width = format_word_width(value_format)
            if width > 1 and (tag["count"] % width != 0):
                raise ValueError(f"{value_format} requires count to be a multiple of {width}")

    def _begin_modbus_operation(self, tag, operation):
        return self._reserve_range(self._operation_range(tag, operation))

    def _end_modbus_operation(self, tag, operation):
        self._release_range(self._operation_range(tag, operation))

    def _operation_range(self, tag, operation):
        """Build a range dict for the Tags table's own interlock bookkeeping. Uses
        self.tag_address_one_based -- the Tags table's addressing-mode toggle -- so
        this must NOT be reused for another feature with its own independent
        addressing mode (e.g. the Address Table has its own one/zero-based
        checkbox); such callers should build their range dict directly with their
        own already-computed protocol offset and call _reserve_range/_release_range."""
        start_offset = self._tag_user_address_to_offset(tag)
        return {
            "operation": operation,
            "space": tag["type"],
            "start": start_offset,
            "end": start_offset + tag["count"] - 1,
            "tag": tag["name"],
        }

    def _reserve_range(self, request_range):
        """Shared busy/overlap interlock, keyed on a plain range dict (space/start/end)
        rather than a Tags-table tag -- lets other features (Address Table, Register
        Scanner, Trend, Script, Tag Monitoring's poll worker) participate in the same
        interlock without going through _operation_range's Tags-specific addressing-mode
        assumption. Locked because _modbus_busy is now checked and set from more than one
        thread (see _active_ranges_lock's comment in __init__)."""
        with self._active_ranges_lock:
            if self._modbus_busy:
                return False
            for active_range in self._active_ranges:
                if self._ranges_overlap(request_range, active_range):
                    return False

            self._modbus_busy = True
            self._active_ranges.append(request_range)
            return True

    def _release_range(self, request_range):
        with self._active_ranges_lock:
            self._active_ranges = [
                active_range for active_range in self._active_ranges
                if active_range != request_range
            ]
            self._modbus_busy = False

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
        
        # Reset monitoring manager state -- non-blocking: self.modbus stays alive across a
        # Stop Monitoring click, so an in-flight poll worker can just finish its current
        # tag in the background rather than needing to be waited on here.
        self.monitoring_manager.stop_poll_worker(wait=False)
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
        """Lock the tag *configuration* columns while monitoring is active, without disabling
        the table itself -- disabling the whole QTableWidget also blocked column resize and
        Write Value edits, even though writing while monitoring is a supported feature."""
        for row in range(self.monitoring_tag_table.rowCount()):
            for column in range(6):  # Tag Name, Mode, Type, Address, Count, Format
                widget = self.monitoring_tag_table.cellWidget(row, column)
                if widget is not None:
                    widget.setEnabled(enabled)
        self.add_tag_btn.setEnabled(enabled)
        self.remove_tag_btn.setEnabled(enabled and bool(self._get_selected_tag_rows()))
        if hasattr(self, 'tag_offset_checkbox'):
            self.tag_offset_checkbox.setEnabled(enabled)
        # Row drag-to-reorder is a configuration action too -- keep it disabled while the
        # poll loop is iterating rows by index, same as Add/Remove Tag.
        self.monitoring_tag_table.verticalHeader().setSectionsMovable(enabled)

    def _restart_monitoring_timers(self, read_interval):
        tags = self._get_monitoring_tags()
        if any(tag["mode"] == "Read" for tag in tags):
            self.monitoring_timer.start(read_interval)
        if any(tag["mode"] == "Write" for tag in tags):
            self.write_poll_timer.start(1000)

    def _clear_monitoring_results(self):
        """Clear monitoring results table."""
        self.monitoring_manager.clear_monitoring_results()

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

        tags = [tag for tag in self._get_monitoring_tags() if tag["mode"] == "Write" and tag["enabled"]]
        if not tags:
            return

        self._write_poll_in_progress = True
        self.write_poll_timer.stop()
        failed_count = 0
        timestamp = time.strftime("%H:%M:%S")
        try:
            for tag in tags:
                try:
                    self._validate_tag_request(tag, "read")
                    if not self._begin_modbus_operation(tag, "read"):
                        self._log(f"Safety interlock: skipped write-tag read for {tag['name']} because the range is busy")
                        continue

                    start_time = time.perf_counter()
                    try:
                        value = self._read_tag_value(tag)
                    finally:
                        self._end_modbus_operation(tag, "read")
                    elapsed_ms = (time.perf_counter() - start_time) * 1000

                    display_value = self._format_monitoring_value(tag, value)
                    raw_hex = self.monitoring_manager.format_raw_hex(tag, value)
                    self._display_raw_data(
                        f"Tag[{tag['name']}] (write-mode, current value)", value, elapsed_ms,
                        function_code_for(tag["type"], is_write=False),
                    )
                    self._add_monitoring_row(
                        tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                        tag["comment"], timestamp, raw_hex
                    )
                except Exception as e:
                    failed_count += 1
                    self._log(f"Write-tag value polling error for {tag['name']}: {e}")
                    continue

            # Only a fully failed tick (every write tag failed) counts toward
            # auto-stop -- one bad tag shouldn't halt polling for the rest.
            if tags and failed_count == len(tags):
                self.monitoring_manager._monitoring_failure_count += 1
                if self.monitoring_manager._monitoring_failure_count >= self.monitoring_manager._monitoring_max_failures:
                    self._log(
                        f"Monitoring stopped after {self.monitoring_manager._monitoring_failure_count} consecutive failed poll(s)"
                    )
                    self._monitoring_paused_by_disconnect = True
                    self._stop_monitoring()
                    QMessageBox.warning(
                        self,
                        "Monitoring Stopped",
                        "Monitoring was stopped after repeated Modbus failures. ModbusLens will keep trying to "
                        "reconnect in the background and resume monitoring automatically once it succeeds. If it "
                        "doesn't recover, check write tag type, address, unit ID, and server status.",
                    )
            else:
                self.monitoring_manager._monitoring_failure_count = 0
        finally:
            self._write_poll_in_progress = False
            if self.monitoring_active:
                self.write_poll_timer.start(1000)

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

        registers = value[: tag["count"]] if isinstance(value, list) else [value]
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
                # A register is a 16-bit word, not a single flag; show every bit (bit15..bit0)
                # so the user can read individual status/alarm bits out of it.
                return [format(int(r) & 0xFFFF, "016b") for r in registers]
            return [int(r) & 0xFFFF for r in registers]

        if value_format in MULTI_WORD_FORMATS:
            swap_words = value_format.endswith("_SWAP")
            base_format = value_format.replace("_SWAP", "")
            word_width = format_word_width(base_format)
            bit_width = word_width * 16
            if len(registers) % word_width != 0:
                raise ValueError(f"{value_format} requires register count to be a multiple of {word_width}")
            values = []
            for i in range(0, len(registers), word_width):
                words = [int(registers[i + j]) & 0xFFFF for j in range(word_width)]
                if swap_words:
                    words.reverse()
                raw_int = 0
                for w in words:
                    raw_int = (raw_int << 16) | w
                if base_format.startswith("U"):
                    values.append(raw_int)
                elif base_format.startswith("S"):
                    sign_bit = 1 << (bit_width - 1)
                    values.append(raw_int - (1 << bit_width) if raw_int & sign_bit else raw_int)
                else:
                    struct_fmt = ">f" if base_format == "F32" else ">d"
                    values.append(struct.unpack(struct_fmt, raw_int.to_bytes(word_width * 2, "big"))[0])
            return values

        return [int(r) & 0xFFFF for r in registers]

    def _add_monitoring_row(self, tag_name, mode, data_type, address, read_value, write_value, comment, timestamp, raw_hex=""):
        """Add or update a tag row in the integrated Tags table."""
        self.monitoring_manager.add_monitoring_row(tag_name, mode, data_type, address, read_value, write_value, comment, timestamp, raw_hex)

    def _check_connection(self):
        """Check if connected to Modbus server."""
        if not self.modbus or not self.modbus.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to a Modbus server first.")
            return False
        return True

    def _log(self, message):
        """Add message to the System Logs, color-coded by what kind of event it looks like
        (write, connect, error) so the right lines stand out at a glance in a busy log."""
        timestamp = time.strftime("[%H:%M:%S]")
        if hasattr(self, 'diagnostics_log_output'):
            scrollbar = self.diagnostics_log_output.verticalScrollBar()
            # Only follow new lines if the user was already at the bottom -- otherwise a
            # scroll-up to inspect something gets yanked back down on every new entry.
            was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
            self.diagnostics_log_output.append(format_log_html(timestamp, message, self._theme_mode))
            if was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())

    def _display_raw_data(self, title, data, elapsed_ms=None, function_info=None, error_category=None):
        """Log one Modbus transaction to the Raw Data tab: what was requested, its raw
        value(s) in decimal and hex, whether it succeeded, how long it took, and (when the
        caller knows it) which function code was actually used.

        function_info is an optional (code, name) tuple -- callers that already know exactly
        what operation they performed (Address Table, Tags, Script) pass it explicitly rather
        than having it guessed back out of the free-form title string.

        error_category lets a caller pass through an already-captured ModbusClient
        _set_error category instead of this method reading self.modbus.last_error_category
        live -- needed by Tag Monitoring's poll worker specifically, since its merged-block
        reads happen on a background thread and a later block's read can overwrite
        last_error_category before this GUI-thread call runs for an earlier one's result
        (same reasoning TagPollWorker already applies to last_error itself). Every other
        caller here reads synchronously right after its own blocking call, so the live
        read below is accurate for them.
        """
        timestamp = time.strftime('%H:%M:%S')
        function_code, _function_name = function_info if function_info else (None, None)
        if function_code is None:
            function_code = self._get_function_code_from_title(title)

        exception_code = self._get_exception_code_from_error() if data is None else None
        if error_category is None and data is None:
            error_category = getattr(self.modbus, 'last_error_category', None)

        # Update statistics (Show Statistics still breaks this down by function/exception code)
        self.advanced_diagnostics.update_request_stats(
            success=data is not None,
            response_time=elapsed_ms,
            function_code=function_code,
            exception_code=exception_code,
            error_category=error_category,
        )

        if hasattr(self, 'diagnostics_dialogs'):
            error_text = getattr(self.modbus, 'last_error', None) if data is None else None
            tx_bytes = getattr(self.modbus, 'last_tx_bytes', None)
            rx_bytes = getattr(self.modbus, 'last_rx_bytes', None)
            # Blank for a plain communications failure (timeout, no response) -- only a
            # device that actually replied with a Modbus exception code gets one, so the
            # Raw Data tab's Exception column distinguishes "the device refused this" from
            # "nothing answered at all" instead of lumping both under the same Failed status.
            exception_text = (
                self.advanced_diagnostics.get_exception_code_description(exception_code)
                if exception_code is not None else ""
            )
            self.diagnostics_dialogs.add_raw_data_row(
                timestamp, title, data, elapsed_ms, error_text, tx_bytes, rx_bytes, exception_text
            )
    
    def _get_function_code_from_title(self, title):
        """Extract function code from title for statistics."""
        # Simple mapping based on title content
        if "Address[" in title or "Tag[" in title:
            return 0x03  # Default to Read Holding Registers
        return 0x01  # Default to Read Coils
    
    def _get_exception_code_from_error(self):
        """The numeric Modbus exception code (1=Illegal Function, 2=Illegal Data Address, ...)
        from the device's own exception response, captured directly on the client rather than
        guessed from last_error's text -- pymodbus's error text doesn't spell out the exception
        name, only its number, so string-matching against phrases like "illegal data address"
        never actually matched anything real."""
        if not self.modbus:
            return None
        return getattr(self.modbus, 'last_exception_code', None)

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

    def _new_connection_window(self):
        """Open another, fully independent connection window (its own connection, tags, trend, server)."""
        new_window = ModbusGUI()
        new_window.show()
        ModbusGUI._open_windows.append(new_window)

    SESSION_FILE_VERSION = 1

    def _build_session_data(self):
        """Bundle everything needed to reproduce this session in a fresh window: connection
        settings, the Tags list (+ scaling), Address Table's current range config, and any
        write bounds set on the live connection. Previously only Tags round-tripped at all
        (via their own separate CSV export/import) -- connection settings, Address Table
        config, and write bounds never traveled together with them."""
        at = self.address_table_widget
        return {
            "version": self.SESSION_FILE_VERSION,
            "connection": {
                "mode": self.connection_mode,
                "ip": self.target_ip,
                "port": self.target_port,
                "unit": self.target_unit_id,
                "serial_port": self.serial_port,
                "baudrate": self.baudrate,
                "parity": self.parity,
                "stopbits": self.stopbits,
                "bytesize": self.bytesize,
                "serial_framer": self.serial_framer,
                "fast_lan_mode": self.fast_lan_mode,
                "interface_ip": self.interface_ip,
            },
            "tags": self._build_tag_export_rows(),
            "address_table": {
                "function": at.function_combo.currentText(),
                "start_address": at.address_input.value(),
                "count": at.count_input.value(),
                "one_based": at.range_is_one_based,
            },
            # Write bounds only ever exist on the live ModbusClient instance (see
            # ModbusClient.write_bounds) -- nothing to save if there's no connection.
            "write_bounds": (
                [[address, bounds[0], bounds[1]] for address, bounds in self.modbus.write_bounds.items()]
                if self.modbus else []
            ),
        }

    def _apply_session_data(self, data):
        """Reverse of _build_session_data. Connection settings are only copied onto the
        live attributes _connect() reads -- Load Session deliberately does not itself
        connect, the same way applying a Recent Connections entry doesn't, so an
        accidental load can't reach real equipment on its own."""
        connection = data.get("connection")
        if connection:
            self._apply_connection_settings(connection)
            self._update_connection_info()

        tags = data.get("tags")
        if tags is not None:
            self._apply_imported_tag_rows(tags)

        at_data = data.get("address_table")
        if at_data:
            at = self.address_table_widget
            # Order matters: one-based toggles the Address spinbox's own min/max range,
            # and function affects whether Count is editable at all -- both need to land
            # before start_address/count are set, or they can get clamped/ignored.
            if "one_based" in at_data:
                at.offset_checkbox.setChecked(not at_data["one_based"])
            if "function" in at_data:
                at.function_combo.setCurrentText(at_data["function"])
            if "start_address" in at_data:
                at.address_input.setValue(at_data["start_address"])
            if "count" in at_data:
                at.count_input.setValue(at_data["count"])

        self._pending_write_bounds = [tuple(entry) for entry in (data.get("write_bounds") or [])]
        self._apply_pending_write_bounds()

    def _apply_pending_write_bounds(self):
        """Write bounds loaded from a Session file before a connection exists (or while a
        previous one is still up) sit in _pending_write_bounds until there's an actual
        ModbusClient to set them on. Called from Load Session and again right after every
        successful _connect(), so whichever happens second is the one that applies them."""
        if not self.modbus or not self._pending_write_bounds:
            return
        for address, minimum, maximum in self._pending_write_bounds:
            self.modbus.set_write_bound(address, minimum, maximum)
        self._log(f"Applied {len(self._pending_write_bounds)} write bound(s) from loaded session")
        self._pending_write_bounds = []

    def _save_session(self):
        """Save connection settings, Tags, Address Table range, and any live write bounds
        together in one file."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Session", f"session_{time.strftime('%Y%m%d_%H%M%S')}.mlsession",
            "ModbusLens Session (*.mlsession)",
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self._build_session_data(), f, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "Save Session Failed", f"Could not write session file: {e}")
            return
        self._log(f"Saved session to {file_path}")
        QMessageBox.information(self, "Save Session", "Session saved successfully!")

    def _load_session(self):
        """Load a saved session."""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(self, "Load Session", "", "ModbusLens Session (*.mlsession)")
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Load Session Failed", f"Could not read session file: {e}")
            return
        if not isinstance(data, dict) or "version" not in data:
            QMessageBox.warning(self, "Invalid Session File", "This doesn't look like a ModbusLens session file.")
            return

        self._apply_session_data(data)
        self._log(f"Loaded session from {file_path}")
        QMessageBox.information(
            self, "Load Session",
            "Session loaded: connection settings, Tags, and Address Table range have been applied.\n\n"
            "Connect using these settings to finish applying any saved write bounds."
        )

    def _export_data(self):
        """Export monitoring data."""
        QMessageBox.information(self, "Export Data", "Data export will be implemented in the next update!")

    def _manage_profiles(self):
        """Manage connection profiles."""
        QMessageBox.information(self, "Connection Profiles", "Profile management will be implemented in the next update!")

    def _manage_templates(self):
        """Manage data templates."""
        QMessageBox.information(self, "Data Templates", "Template management will be implemented in the next update!")

    def _show_ip_config(self):
        """Show a small ipconfig-style dialog listing this machine's network adapters."""
        if psutil is None:
            QMessageBox.warning(self, "IP Configuration", "psutil is not available, so adapter information can't be read.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("IP Configuration")
        dialog.resize(560, 320)
        layout = QVBoxLayout(dialog)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Adapter", "IP Address", "Subnet Mask", "Status"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {self._c["surface"]};
                color: {self._c["text"]};
                gridline-color: {self._c["pressed"]};
                border: 1px solid {self._c["border"]};
            }}
            QHeaderView::section {{
                background-color: {self._c["header_bg"]};
                color: {self._c["text"]};
                border: 1px solid {self._c["border"]};
                padding: 6px;
                font-weight: bold;
            }}
        """)

        rows = []
        try:
            interface_stats = psutil.net_if_stats()
            for name, addresses in psutil.net_if_addrs().items():
                stats = interface_stats.get(name)
                status = "Up" if stats and stats.isup else "Down"
                for addr in addresses:
                    if addr.family == socket.AF_INET:
                        rows.append((name, addr.address, addr.netmask or "-", status))
        except Exception as e:
            self._log(f"IP Configuration error: {e}")

        table.setRowCount(len(rows))
        for row, (name, ip_address, subnet_mask, status) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setItem(row, 1, QTableWidgetItem(ip_address))
            table.setItem(row, 2, QTableWidgetItem(subnet_mask))
            table.setItem(row, 3, QTableWidgetItem(status))

        layout.addWidget(table)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._get_button_style())
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        dialog.exec()

    def _network_diagnostics(self):
        """Show network diagnostics."""
        self.network_diagnostics.show_diagnostics(self.target_ip, self.target_port, self.target_unit_id)

    def _serial_discovery(self, initial_port=None):
        """Show the Serial Discovery dialog, optionally pre-filled with a COM port."""
        self.serial_discovery.show_discovery(initial_port or self.serial_port)

    def _show_diagnostic_functions(self):
        """Show the FC07/08/11/12/17/20/21/22/24/43 diagnostic functions dialog."""
        dialog = DiagnosticFunctionsDialog(self)
        dialog.exec()

    def _show_documentation(self):
        """Show the Help documentation."""
        dialog = DocumentationDialog(self)
        dialog.exec()

    def _show_about(self):
        """Show about dialog, with a second tab that checks GitHub for a newer release."""
        version = QApplication.applicationVersion()
        dialog = AboutDialog(version, self)
        dialog.exec()

    def _show_safety_warning_again(self):
        """The startup safety warning's "don't show again" had no in-app way back --
        someone testing against a simulator who checked it gets no warning months later
        against the live VFD. This is that way back: re-shows the actual dialog right now
        (a live re-confirmation, not just a settings toggle) and persists whatever the
        checkbox ends up at for future launches. Unlike the startup gate, clicking "Exit"
        here just closes the reminder -- it must not quit the whole running app, since the
        user is already using it and didn't ask to leave."""
        dialog = SafetyWarningDialog(self, colors=self._colors())
        dialog.exec()
        dialog.save_preference()
        if dialog.dont_show_again.isChecked():
            self._log("Safety warning: will stay hidden on next launch")
        else:
            self._log("Safety warning: will show again on next launch")

    def closeEvent(self, event):
        """Handle application close event."""
        # Stop any in-progress scan before touching the connection it's using --
        # _disconnect() below now does this too, but do it explicitly first so a hang
        # in the worker thread doesn't leave the connection torn down under it.
        if hasattr(self, 'register_scanner_widget'):
            self.register_scanner_widget.stop_all_scans()
        if hasattr(self, 'serial_discovery'):
            self.serial_discovery.stop_all_scans()
        if self.monitoring_active:
            self._stop_monitoring()
        if self.modbus:
            self._disconnect()
        if hasattr(self, 'server_widget') and self.server_widget.running:
            self.server_widget._stop_server()
        if hasattr(self, 'trend_widget') and self.trend_widget._detach_window is not None:
            self.trend_widget._redock()
        if self in ModbusGUI._open_windows:
            ModbusGUI._open_windows.remove(self)
        self._save_settings()
        event.accept()
 

class SafetyWarningDialog(QDialog):
    def __init__(self, parent=None, colors=None):
        super().__init__(parent)
        self._c = colors or theme.LIGHT
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
        title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {self._c['danger']};")
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
        body.setStyleSheet(f"color: {self._c['heading']};")
        layout.addWidget(body)

        # Add "Don't show again" checkbox
        self.dont_show_again = QCheckBox("Don't show this warning again")
        self.dont_show_again.setStyleSheet(f"color: {self._c['heading']};")
        layout.addWidget(self.dont_show_again)

        buttons = QHBoxLayout()
        buttons.addStretch()

        exit_btn = QPushButton("Exit")
        exit_btn.setStyleSheet(self._button_style(danger=True))
        exit_btn.clicked.connect(self.reject)
        # Explicit safe default: a reflexive Enter at dialog-open should back out, not
        # proceed into a live-write tool's warning -- not left to Qt's implicit focus order.
        exit_btn.setDefault(True)
        exit_btn.setFocus()
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
        """Save the user's checkbox choice either way. Previously this only ever wrote
        True when checked, with no code path that ever wrote it back to False -- so once
        "don't show again" was checked once, there was no way back short of editing
        QSettings by hand. Writing the checkbox's actual current state unconditionally
        fixes that for every caller, including the "Show Safety Warning Again" menu
        action below."""
        from PySide6.QtCore import QSettings
        settings = QSettings("ModbusLens", "ModbusLens")
        settings.setValue("hide_safety_warning", self.dont_show_again.isChecked())

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


class AlarmConfigDialog(QDialog):
    """Configure a High/Low (or ON/OFF) alarm threshold for one Tags row."""

    def __init__(self, tag, existing_alarm, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configure Alarm - {tag['name']}")
        existing_alarm = existing_alarm or {}
        self.is_bool_like = tag["type"] in ("Coil", "Discrete Input") or (tag.get("format") or "").strip().upper() == "BOOL"

        layout = QVBoxLayout(self)

        self.enable_checkbox = QCheckBox("Enable Alarm")
        self.enable_checkbox.setChecked(existing_alarm.get("enabled", False))
        layout.addWidget(self.enable_checkbox)

        if self.is_bool_like:
            state_row = QHBoxLayout()
            state_row.addWidget(QLabel("Alarm when value is:"))
            self.state_combo = QComboBox()
            self.state_combo.addItems(["ON / True", "OFF / False"])
            self.state_combo.setCurrentIndex(0 if existing_alarm.get("bool_state", True) else 1)
            state_row.addWidget(self.state_combo)
            layout.addLayout(state_row)
        else:
            high_row = QHBoxLayout()
            self.high_enable = QCheckBox("High Limit:")
            self.high_enable.setChecked(existing_alarm.get("high_enabled", False))
            high_row.addWidget(self.high_enable)
            self.high_spin = QDoubleSpinBox()
            self.high_spin.setRange(-1e9, 1e9)
            self.high_spin.setValue(existing_alarm.get("high", 0.0))
            high_row.addWidget(self.high_spin)
            layout.addLayout(high_row)

            low_row = QHBoxLayout()
            self.low_enable = QCheckBox("Low Limit:")
            self.low_enable.setChecked(existing_alarm.get("low_enabled", False))
            low_row.addWidget(self.low_enable)
            self.low_spin = QDoubleSpinBox()
            self.low_spin.setRange(-1e9, 1e9)
            self.low_spin.setValue(existing_alarm.get("low", 0.0))
            low_row.addWidget(self.low_spin)
            layout.addLayout(low_row)

        button_row = QHBoxLayout()
        button_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def values(self):
        result = {"enabled": self.enable_checkbox.isChecked()}
        if self.is_bool_like:
            result["bool_state"] = self.state_combo.currentIndex() == 0
        else:
            result["high_enabled"] = self.high_enable.isChecked()
            result["high"] = self.high_spin.value()
            result["low_enabled"] = self.low_enable.isChecked()
            result["low"] = self.low_spin.value()
        return result


class ScalingConfigDialog(QDialog):
    """Configure engineering-unit scaling for one Tags row -- either a linear transform
    (raw min/max -> scaled min/max, e.g. raw ADC counts 0-4095 -> 0-100 PSI) or a simple
    multiply-by-constant transform (e.g. raw 151 -> 15.1 via a factor of 0.1)."""

    def __init__(self, existing_scaling, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Engineering Scaling")
        existing_scaling = existing_scaling or {}
        is_multiply = existing_scaling.get("mode") == "multiply"

        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Scaling mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Linear (Min/Max)", "Multiply by Constant"])
        self.mode_combo.setCurrentIndex(1 if is_multiply else 0)
        self.mode_combo.currentIndexChanged.connect(self._update_mode_visibility)
        mode_row.addWidget(self.mode_combo)
        layout.addLayout(mode_row)

        self.linear_group = QWidget()
        linear_layout = QVBoxLayout(self.linear_group)
        linear_layout.setContentsMargins(0, 0, 0, 0)

        raw_row = QHBoxLayout()
        raw_row.addWidget(QLabel("Raw Min:"))
        self.raw_min_spin = QDoubleSpinBox()
        self.raw_min_spin.setRange(-1e9, 1e9)
        self.raw_min_spin.setValue(existing_scaling.get("raw_min", 0.0))
        raw_row.addWidget(self.raw_min_spin)
        raw_row.addWidget(QLabel("Raw Max:"))
        self.raw_max_spin = QDoubleSpinBox()
        self.raw_max_spin.setRange(-1e9, 1e9)
        self.raw_max_spin.setValue(existing_scaling.get("raw_max", 4095.0))
        raw_row.addWidget(self.raw_max_spin)
        linear_layout.addLayout(raw_row)

        scaled_row = QHBoxLayout()
        scaled_row.addWidget(QLabel("Scaled Min:"))
        self.scaled_min_spin = QDoubleSpinBox()
        self.scaled_min_spin.setRange(-1e9, 1e9)
        self.scaled_min_spin.setValue(existing_scaling.get("scaled_min", 0.0))
        scaled_row.addWidget(self.scaled_min_spin)
        scaled_row.addWidget(QLabel("Scaled Max:"))
        self.scaled_max_spin = QDoubleSpinBox()
        self.scaled_max_spin.setRange(-1e9, 1e9)
        self.scaled_max_spin.setValue(existing_scaling.get("scaled_max", 100.0))
        scaled_row.addWidget(self.scaled_max_spin)
        linear_layout.addLayout(scaled_row)
        layout.addWidget(self.linear_group)

        self.multiply_group = QWidget()
        multiply_layout = QHBoxLayout(self.multiply_group)
        multiply_layout.setContentsMargins(0, 0, 0, 0)
        multiply_layout.addWidget(QLabel("Multiply raw value by:"))
        self.factor_spin = QDoubleSpinBox()
        self.factor_spin.setRange(-1e9, 1e9)
        self.factor_spin.setDecimals(6)
        self.factor_spin.setValue(existing_scaling.get("factor", 0.1))
        multiply_layout.addWidget(self.factor_spin)
        multiply_layout.addWidget(QLabel("(e.g. 0.1 turns raw 151 into 15.1)"))
        layout.addWidget(self.multiply_group)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Store scaled value as:"))
        self.value_type_combo = QComboBox()
        self.value_type_combo.addItems(["Real", "Integer"])
        self.value_type_combo.setCurrentText(existing_scaling.get("value_type", "Real"))
        type_row.addWidget(self.value_type_combo)
        layout.addLayout(type_row)

        button_row = QHBoxLayout()
        button_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

        self._update_mode_visibility()

    def _update_mode_visibility(self):
        is_multiply = self.mode_combo.currentIndex() == 1
        self.linear_group.setVisible(not is_multiply)
        self.multiply_group.setVisible(is_multiply)

    def _on_ok(self):
        if self.mode_combo.currentIndex() == 1:
            if self.factor_spin.value() == 0:
                QMessageBox.warning(self, "Invalid Factor", "Multiply factor can't be zero.")
                return
        elif self.raw_min_spin.value() == self.raw_max_spin.value():
            QMessageBox.warning(self, "Invalid Range", "Raw Min and Raw Max can't be equal.")
            return
        self.accept()

    def values(self):
        if self.mode_combo.currentIndex() == 1:
            return {
                "enabled": True,
                "mode": "multiply",
                "factor": self.factor_spin.value(),
                "value_type": self.value_type_combo.currentText(),
            }
        return {
            "enabled": True,
            "mode": "linear",
            "raw_min": self.raw_min_spin.value(),
            "raw_max": self.raw_max_spin.value(),
            "scaled_min": self.scaled_min_spin.value(),
            "scaled_max": self.scaled_max_spin.value(),
            "value_type": self.value_type_combo.currentText(),
        }


class ConnectionSettingsDialog(QDialog):
    """Dialog for advanced Modbus connection configuration (TCP or serial/RTU)."""

    SERIAL_PORTS_HINT = ["COM1", "COM2", "COM3", "COM4"]
    BAUD_RATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
    PARITIES = [("None", "N"), ("Even", "E"), ("Odd", "O")]
    STOP_BITS = [1, 2]
    BYTE_SIZES = [7, 8]

    def __init__(self, parent, history, current, serial_overrides=None):
        super().__init__(parent)
        self.setWindowTitle("Connection Settings")
        self.setMinimumWidth(450)
        self.history = history[:]
        # Set by _open_serial_scan() -- the caller checks this after exec() to decide
        # whether to open Serial Discovery once this dialog has closed.
        self.scan_requested_port = None

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)

        # 0. Connection type
        mode_group = QGroupBox("Connection Type")
        mode_layout = QHBoxLayout(mode_group)
        self.tcp_radio = QRadioButton("Modbus TCP")
        self.serial_radio = QRadioButton("Modbus Serial (RTU/ASCII)")
        (self.serial_radio if current.connection_mode == "serial" else self.tcp_radio).setChecked(True)
        self.tcp_radio.toggled.connect(self._update_mode_visibility)
        mode_layout.addWidget(self.tcp_radio)
        mode_layout.addWidget(self.serial_radio)
        layout.addWidget(mode_group)

        # 1. TCP configuration
        self.tcp_group = QGroupBox("Target Device (TCP)")
        grid = QGridLayout(self.tcp_group)
        grid.setSpacing(10)

        grid.addWidget(QLabel("IP Address:"), 0, 0)
        self.ip_input = QLineEdit(current.target_ip)
        self.ip_input.setStyleSheet(parent._get_input_style())
        grid.addWidget(self.ip_input, 0, 1)

        grid.addWidget(QLabel("Port:"), 1, 0)
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(current.target_port)
        self.port_input.setStyleSheet(parent._get_input_style())
        grid.addWidget(self.port_input, 1, 1)

        self.fast_lan_checkbox = QCheckBox("Fast LAN Mode (200ms timeout, no retries)")
        self.fast_lan_checkbox.setToolTip(
            "For a local network where a timeout means the device is actually gone, not "
            "just slow. Polling also skips straight to a quick reachability check instead "
            "of retrying every tag when the device drops off."
        )
        self.fast_lan_checkbox.setChecked(getattr(current, "fast_lan_mode", False))
        grid.addWidget(self.fast_lan_checkbox, 2, 0, 1, 2)
        layout.addWidget(self.tcp_group)

        # 2. Network interface (TCP only)
        self.iface_group = QGroupBox("Network Interface")
        iface_layout = QHBoxLayout(self.iface_group)
        self.iface_combo = QComboBox()
        self.iface_combo.setStyleSheet(parent._get_input_style())

        # "Auto" (data=None) keeps today's behavior -- the OS picks the outgoing route --
        # since actually binding to a NIC is a deliberate opt-in, not a default every
        # existing connection should suddenly start doing.
        self.iface_combo.addItem("Auto (let OS choose route)", None)
        try:
            from network.network_diagnostics import get_network_interfaces
            interfaces = get_network_interfaces()
            for i in interfaces:
                self.iface_combo.addItem(i['display_name'], i['ipv4'])
        except Exception:
            pass

        current_iface_ip = getattr(current, "interface_ip", None)
        if current_iface_ip:
            match_index = self.iface_combo.findData(current_iface_ip)
            if match_index >= 0:
                self.iface_combo.setCurrentIndex(match_index)

        self.iface_combo.currentTextChanged.connect(self._on_iface_changed)
        iface_layout.addWidget(self.iface_combo)
        layout.addWidget(self.iface_group)

        # 3. Serial configuration
        self.serial_group = QGroupBox("Target Device (Serial)")
        serial_grid = QGridLayout(self.serial_group)
        serial_grid.setSpacing(10)

        serial_grid.addWidget(QLabel("COM Port:"), 0, 0)
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setEditable(True)
        self.serial_port_combo.setStyleSheet(parent._get_input_style())
        for port_name in self._detect_serial_ports():
            self.serial_port_combo.addItem(port_name)
        self.serial_port_combo.setCurrentText(current.serial_port)
        serial_grid.addWidget(self.serial_port_combo, 0, 1)

        serial_grid.addWidget(QLabel("Baud Rate:"), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.setStyleSheet(parent._get_input_style())
        for rate in self.BAUD_RATES:
            self.baud_combo.addItem(str(rate))
        self.baud_combo.setCurrentText(str(current.baudrate))
        serial_grid.addWidget(self.baud_combo, 1, 1)

        serial_grid.addWidget(QLabel("Parity:"), 2, 0)
        self.parity_combo = QComboBox()
        self.parity_combo.setStyleSheet(parent._get_input_style())
        for label, code in self.PARITIES:
            self.parity_combo.addItem(label, code)
        index = next((i for i, (_, code) in enumerate(self.PARITIES) if code == current.parity), 0)
        self.parity_combo.setCurrentIndex(index)
        serial_grid.addWidget(self.parity_combo, 2, 1)

        serial_grid.addWidget(QLabel("Stop Bits:"), 3, 0)
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.setStyleSheet(parent._get_input_style())
        for bits in self.STOP_BITS:
            self.stopbits_combo.addItem(str(bits), bits)
        self.stopbits_combo.setCurrentIndex(self.STOP_BITS.index(current.stopbits) if current.stopbits in self.STOP_BITS else 0)
        serial_grid.addWidget(self.stopbits_combo, 3, 1)

        serial_grid.addWidget(QLabel("Byte Size:"), 4, 0)
        self.bytesize_combo = QComboBox()
        self.bytesize_combo.setStyleSheet(parent._get_input_style())
        for size in self.BYTE_SIZES:
            self.bytesize_combo.addItem(str(size), size)
        self.bytesize_combo.setCurrentIndex(self.BYTE_SIZES.index(current.bytesize) if current.bytesize in self.BYTE_SIZES else 1)
        serial_grid.addWidget(self.bytesize_combo, 4, 1)

        serial_grid.addWidget(QLabel("Framing:"), 5, 0)
        self.framer_combo = QComboBox()
        self.framer_combo.setStyleSheet(parent._get_input_style())
        self.framer_combo.addItem("RTU (binary)", "rtu")
        self.framer_combo.addItem("ASCII", "ascii")
        framer_index = 1 if getattr(current, "serial_framer", "rtu") == "ascii" else 0
        self.framer_combo.setCurrentIndex(framer_index)
        serial_grid.addWidget(self.framer_combo, 5, 1)

        scan_btn = QPushButton("Scan for Connection Parameters...")
        scan_btn.clicked.connect(self._open_serial_scan)
        serial_grid.addWidget(scan_btn, 6, 0, 1, 2)
        layout.addWidget(self.serial_group)

        # 4. Unit ID (shared by both modes)
        unit_group = QGroupBox("Unit ID")
        unit_layout = QHBoxLayout(unit_group)
        self.unit_input = QSpinBox()
        self.unit_input.setRange(0, 247)
        self.unit_input.setValue(current.target_unit_id)
        self.unit_input.setStyleSheet(parent._get_input_style())
        unit_layout.addWidget(self.unit_input)
        layout.addWidget(unit_group)

        # 5. History
        hist_group = QGroupBox("Recent Connections")
        hist_layout = QHBoxLayout(hist_group)
        self.hist_combo = QComboBox()
        self.hist_combo.setStyleSheet(parent._get_input_style())
        self.hist_combo.currentIndexChanged.connect(self._on_history_select)
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

        # Pre-fill from a Serial Discovery match (see SerialDiscoveryDialog._apply_selected_match)
        # -- applied after every field above already exists, but Save Settings is still the
        # action that actually commits it, same as picking a Recent Connections entry.
        if serial_overrides:
            self.serial_radio.setChecked(True)
            self.serial_port_combo.setCurrentText(serial_overrides["serial_port"])
            self.baud_combo.setCurrentText(str(serial_overrides["baudrate"]))
            parity_index = next(
                (i for i, (_, code) in enumerate(self.PARITIES) if code == serial_overrides["parity"]), 0
            )
            self.parity_combo.setCurrentIndex(parity_index)
            self.bytesize_combo.setCurrentIndex(self.BYTE_SIZES.index(8))
            if serial_overrides["stopbits"] in self.STOP_BITS:
                self.stopbits_combo.setCurrentIndex(self.STOP_BITS.index(serial_overrides["stopbits"]))
            self.unit_input.setValue(serial_overrides["unit_id"])
            self.framer_combo.setCurrentIndex(1 if serial_overrides.get("framer") == "ascii" else 0)

        self._update_mode_visibility()

    @staticmethod
    def _detect_serial_ports():
        try:
            from serial.tools import list_ports
            ports = [p.device for p in list_ports.comports()]
            if ports:
                return ports
        except Exception:
            pass
        return ConnectionSettingsDialog.SERIAL_PORTS_HINT

    def _open_serial_scan(self):
        """Close this dialog without saving and let the caller open Serial Discovery,
        pre-filled with whichever COM port is currently selected here."""
        self.scan_requested_port = self.serial_port_combo.currentText().strip()
        self.reject()

    def _update_mode_visibility(self):
        is_serial = self.serial_radio.isChecked()
        self.tcp_group.setVisible(not is_serial)
        self.iface_group.setVisible(not is_serial)
        self.serial_group.setVisible(is_serial)
        self._populate_history_combo()

    def _on_iface_changed(self, _text):
        """Only offer the interface's IP as a convenience when Target IP is blank --
        never overwrite an address the user already typed in. "Auto" carries no IP
        (data=None), so there's nothing to prefill."""
        data = self.iface_combo.currentData()
        if data and not self.ip_input.text().strip():
            self.ip_input.setText(data)

    def _friendly_history_label(self, entry):
        """A raw history token like 'serial:COM5:9600:N:8:1:1:rtu' isn't something a user
        should have to parse by eye -- show it the same way the rest of the dialog does."""
        parts = entry.split(":")
        if entry.startswith("serial:") and len(parts) in (7, 8):
            # Older saved history entries have 7 fields (no framer) -- treat those as RTU,
            # since that's what every version before ASCII support only ever wrote.
            if len(parts) == 8:
                _, serial_port, baud, parity, bytesize, stopbits, unit, framer = parts
            else:
                _, serial_port, baud, parity, bytesize, stopbits, unit = parts
                framer = "rtu"
            parity_label = next((label for label, code in self.PARITIES if code == parity), parity)
            framer_label = "ASCII" if framer == "ascii" else "RTU"
            return (
                f"{serial_port} @ {baud} baud ({parity_label} parity, {bytesize}/{stopbits}, "
                f"{framer_label}, Unit {unit})"
            )
        if len(parts) >= 3:
            return f"{parts[0]}:{parts[1]} (Unit {parts[2]})"
        return entry

    def _populate_history_combo(self):
        """Show every saved history entry regardless of which connection type is currently
        selected -- each label already says TCP or serial on its face (see
        _friendly_history_label), and selecting one now switches the radio to match."""
        self.hist_combo.blockSignals(True)
        self.hist_combo.clear()
        for entry in self.history:
            self.hist_combo.addItem(self._friendly_history_label(entry), entry)
        self.hist_combo.blockSignals(False)

    def _on_history_select(self, index):
        entry = self.hist_combo.itemData(index)
        if not entry:
            return

        # History is no longer filtered by the currently selected connection type (see
        # _populate_history_combo), so picking an entry of the other type needs to flip
        # the radio itself -- otherwise the form fields get filled in but the visible
        # TCP/Serial group and mode never actually change to match. That toggle re-runs
        # _populate_history_combo, which would otherwise reset the combo's own visible
        # selection -- restore it once we're done.
        try:
            if entry.startswith("serial:"):
                parts = entry.split(":")
                if len(parts) not in (7, 8):
                    return
                self.serial_radio.setChecked(True)
                if len(parts) == 8:
                    _, serial_port, baud, parity, bytesize, stopbits, unit, framer = parts
                else:
                    # Older saved entries have no framer field -- they predate ASCII
                    # support, so they were always RTU.
                    _, serial_port, baud, parity, bytesize, stopbits, unit = parts
                    framer = "rtu"
                self.serial_port_combo.setCurrentText(serial_port)
                self.baud_combo.setCurrentText(baud)
                parity_index = next((i for i, (_, code) in enumerate(self.PARITIES) if code == parity), 0)
                self.parity_combo.setCurrentIndex(parity_index)
                if int(bytesize) in self.BYTE_SIZES:
                    self.bytesize_combo.setCurrentIndex(self.BYTE_SIZES.index(int(bytesize)))
                if int(stopbits) in self.STOP_BITS:
                    self.stopbits_combo.setCurrentIndex(self.STOP_BITS.index(int(stopbits)))
                self.unit_input.setValue(int(unit))
                self.framer_combo.setCurrentIndex(1 if framer == "ascii" else 0)
                return

            parts = entry.split(":")
            if len(parts) >= 3:
                self.tcp_radio.setChecked(True)
                self.ip_input.setText(parts[0])
                self.port_input.setValue(int(parts[1]))
                self.unit_input.setValue(int(parts[2]))
        finally:
            restore_index = self.hist_combo.findData(entry)
            if restore_index >= 0 and self.hist_combo.currentIndex() != restore_index:
                self.hist_combo.blockSignals(True)
                self.hist_combo.setCurrentIndex(restore_index)
                self.hist_combo.blockSignals(False)

    def get_values(self):
        return {
            'mode': "serial" if self.serial_radio.isChecked() else "tcp",
            'ip': self.ip_input.text(),
            'port': self.port_input.value(),
            'unit': self.unit_input.value(),
            'serial_port': self.serial_port_combo.currentText(),
            'baudrate': int(self.baud_combo.currentText()),
            'parity': self.parity_combo.currentData(),
            'stopbits': self.stopbits_combo.currentData(),
            'bytesize': self.bytesize_combo.currentData(),
            'serial_framer': self.framer_combo.currentData(),
            'fast_lan_mode': self.fast_lan_checkbox.isChecked(),
            'interface_ip': self.iface_combo.currentData(),
            'history': self.history,
        }


def main(): 
    try: 
        # Check if QApplication already exists (e.g., in IDE environments) 
        app = QApplication.instance() 
        if app is None: 
            app = QApplication(sys.argv)

        app.setApplicationName("ModbusLens")
        app.setApplicationVersion(__version__)
        app.setOrganizationName("ModbusLens")

        # Resolve the saved theme preference ("light"/"dark"/"system") to a concrete
        # mode and apply it before creating any widgets -- widgets read colors from
        # this resolved mode at construction time (see ModbusGUI._colors).
        resolved_theme = theme.resolve_mode(theme.load_saved_mode(), app)
        theme.apply_theme(app, resolved_theme)

        warning = SafetyWarningDialog(colors=theme.get_colors(resolved_theme))
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
