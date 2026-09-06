"""
Phase 1: Unified "Find Devices" panel.

Merges the existing TCP subnet scan (NetworkScanner, network_diagnostics.py) and the
serial connection-parameter sweep (SerialParamScanWorker, diagnostics/serial_discovery.py)
into one dialog with a shared results table, so finding a device doesn't mean picking
between two separate tools depending on transport. Both backends are reused as-is --
this is UI integration only, no new scanning logic.

The deeper, transport-specific tools (Network Discovery & Diagnostics' ARP mode/packet
capture/connectivity tests, and Serial Discovery's own dedicated dialog) are untouched
and still reachable from the Diagnostics menu for anyone who needs them -- this dialog
is the quick "just find my device" entry point for both transports at once.
"""
import ipaddress

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QSpinBox,
    QComboBox, QProgressBar, QTableWidget, QTableWidgetItem, QTextEdit, QStackedWidget,
    QWidget, QHeaderView,
)

from theme import apply_dropdown_delegate
from gui.network.network_diagnostics import (
    NetworkScanner, get_local_subnet_info, compute_scan_network, parse_custom_scan_range,
)
from gui.diagnostics.serial_discovery import (
    SerialParamScanWorker, detect_serial_ports, PARITY_LABELS,
)

TCP_ROW = "tcp"
SERIAL_ROW = "serial"


class FindDevicesDialog:
    """One dialog, two scan modes (TCP subnet scan / serial parameter sweep), one
    results table. Selecting a row and clicking Apply hands the match straight to
    Connection Settings, same as each original tool's own Apply button did."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.dialog = None
        self.tcp_scanner = None
        self.serial_worker = None

    def show_dialog(self, initial_ip=None, initial_port=None, initial_com_port=None,
                     initial_mode="tcp"):
        if self.dialog is None:
            self._build_dialog()

        if initial_ip:
            self.ip_input.setText(initial_ip)
        if initial_port:
            self.port_input.setValue(int(initial_port))
        if initial_com_port:
            self.port_combo.setCurrentText(initial_com_port)
        self.transport_combo.setCurrentIndex(1 if initial_mode == "serial" else 0)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _build_dialog(self):
        c = self.parent._colors()
        self.dialog = QDialog(self.parent)
        self.dialog.setWindowTitle("Find Devices")
        self.dialog.setGeometry(300, 300, 660, 560)
        self.dialog.closeEvent = self._on_dialog_close

        layout = QVBoxLayout(self.dialog)

        # Transport picker
        transport_row = QHBoxLayout()
        transport_row.addWidget(QLabel("Transport:"))
        self.transport_combo = QComboBox()
        self.transport_combo.setStyleSheet(self.parent._get_input_style())
        self.transport_combo.addItems(["TCP (Network Scan)", "Serial (Parameter Sweep)"])
        apply_dropdown_delegate(self.transport_combo, getattr(self.parent, "_theme_mode", "light"))
        transport_row.addWidget(self.transport_combo)
        transport_row.addStretch()
        layout.addLayout(transport_row)

        self.input_stack = QStackedWidget()
        self.input_stack.addWidget(self._build_tcp_panel())
        self.input_stack.addWidget(self._build_serial_panel())
        layout.addWidget(self.input_stack)
        self.transport_combo.currentIndexChanged.connect(self.input_stack.setCurrentIndex)

        # Shared controls
        controls_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Scan")
        self.start_btn.setStyleSheet(self.parent._get_button_style())
        self.start_btn.clicked.connect(self._start_scan)
        controls_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Scan")
        self.stop_btn.setStyleSheet(self.parent._get_button_style())
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_scan)
        controls_row.addWidget(self.stop_btn)

        self.clear_btn = QPushButton("Clear Results")
        self.clear_btn.setStyleSheet(self.parent._get_button_style())
        self.clear_btn.clicked.connect(self._clear_results)
        controls_row.addWidget(self.clear_btn)
        controls_row.addStretch()
        layout.addLayout(controls_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Shared results table
        layout.addWidget(QLabel("Found devices (select one, then Apply):"))
        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["Transport", "Target", "Parameters", "Unit ID"])
        self.results_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}
        """)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.results_table.doubleClicked.connect(lambda _idx: self._apply_selected())
        self.results_table.setMaximumHeight(160)
        layout.addWidget(self.results_table)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self.apply_btn = QPushButton("Apply to Connection Settings")
        self.apply_btn.setStyleSheet(self.parent._get_button_style())
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_selected)
        apply_row.addWidget(self.apply_btn)
        layout.addLayout(apply_row)

        # Output log
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.document().setMaximumBlockCount(5000)
        self.output_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c["surface_alt2"]};
                color: {c["text_secondary"]};
                border: 1px solid {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.output_text, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self.parent._get_button_style())
        close_btn.clicked.connect(self.dialog.hide)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def _build_tcp_panel(self):
        panel = QWidget()
        grid = QVBoxLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("IP Address:"))
        self.ip_input = QLineEdit(getattr(self.parent, "target_ip", ""))
        self.ip_input.setStyleSheet(self.parent._get_input_style())
        self.ip_input.setPlaceholderText("e.g. 192.168.1.100")
        row1.addWidget(self.ip_input)

        row1.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setStyleSheet(self.parent._get_input_style())
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(int(getattr(self.parent, "target_port", 502) or 502))
        row1.addWidget(self.port_input)
        grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Custom Range:"))
        self.range_input = QLineEdit()
        self.range_input.setStyleSheet(self.parent._get_input_style())
        self.range_input.setPlaceholderText(
            "Optional, e.g. 192.168.1.10-192.168.1.50 -- leave blank to auto-detect subnet"
        )
        row2.addWidget(self.range_input)
        grid.addLayout(row2)

        return panel

    def _build_serial_panel(self):
        panel = QWidget()
        grid = QVBoxLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("COM Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setStyleSheet(self.parent._get_input_style())
        self.port_combo.addItems(detect_serial_ports())
        apply_dropdown_delegate(self.port_combo, getattr(self.parent, "_theme_mode", "light"))
        row1.addWidget(self.port_combo)

        row1.addWidget(QLabel("Framing:"))
        self.framer_combo = QComboBox()
        self.framer_combo.setStyleSheet(self.parent._get_input_style())
        self.framer_combo.addItems(["RTU", "ASCII"])
        apply_dropdown_delegate(self.framer_combo, getattr(self.parent, "_theme_mode", "light"))
        row1.addWidget(self.framer_combo)
        grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Start Unit ID:"))
        self.start_unit_input = QSpinBox()
        self.start_unit_input.setStyleSheet(self.parent._get_input_style())
        self.start_unit_input.setRange(0, 255)
        self.start_unit_input.setValue(1)
        row2.addWidget(self.start_unit_input)

        row2.addWidget(QLabel("End Unit ID:"))
        self.end_unit_input = QSpinBox()
        self.end_unit_input.setStyleSheet(self.parent._get_input_style())
        self.end_unit_input.setRange(0, 255)
        self.end_unit_input.setValue(1)
        row2.addWidget(self.end_unit_input)

        row2.addWidget(QLabel("Per-trial timeout (ms):"))
        self.timeout_input = QSpinBox()
        self.timeout_input.setStyleSheet(self.parent._get_input_style())
        self.timeout_input.setRange(50, 2000)
        self.timeout_input.setValue(200)
        row2.addWidget(self.timeout_input)
        grid.addLayout(row2)

        return panel

    # -- scanning --------------------------------------------------------

    def _is_serial_mode(self):
        return self.transport_combo.currentIndex() == 1

    def _start_scan(self):
        if self._is_serial_mode():
            self._start_serial_scan()
        else:
            self._start_tcp_scan()

    def _start_tcp_scan(self):
        if self.tcp_scanner and self.tcp_scanner.isRunning():
            return

        host = self.ip_input.text().strip()
        port = self.port_input.value()
        if not host:
            self.output_text.append("Error: enter an IP address first.")
            return
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            self.output_text.append("Error: invalid IP address format.")
            return

        range_text = self.range_input.text().strip()
        if range_text:
            try:
                base_ip, host_count = parse_custom_scan_range(range_text)
            except ValueError as e:
                self.output_text.append(f"Error: {e}")
                return
        else:
            subnet_info = get_local_subnet_info()
            scan_network = compute_scan_network(host, subnet_info)
            base_ip = str(scan_network.network_address)
            host_count = scan_network.num_addresses

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.transport_combo.setEnabled(False)

        self.tcp_scanner = NetworkScanner(base_ip, host_count, port, continuous=True, scan_delay=2)
        self.tcp_scanner.device_found.connect(self._on_tcp_device_found)
        self.tcp_scanner.progress.connect(self._on_scan_progress)
        self.tcp_scanner.output.connect(self.output_text.append)
        self.tcp_scanner.scan_complete.connect(self._on_scan_complete)
        self.tcp_scanner.start()

    def _start_serial_scan(self):
        if self.serial_worker and self.serial_worker.isRunning():
            return

        port = self.port_combo.currentText().strip()
        if not port:
            self.output_text.append("Error: enter or select a COM port first.")
            return

        modbus = getattr(self.parent, "modbus", None)
        if (
            modbus and modbus.is_connected() and modbus.mode == "serial"
            and modbus.serial_port.strip().upper() == port.upper()
        ):
            self.output_text.append(
                f"{port} is the app's current connection -- disconnect first, or scan a different port."
            )
            return

        start_unit = self.start_unit_input.value()
        end_unit = self.end_unit_input.value()
        if start_unit > end_unit:
            self.output_text.append("Error: Start Unit ID must not be greater than End Unit ID.")
            return

        self.output_text.append(f"Scanning serial settings on {port}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.transport_combo.setEnabled(False)

        self.serial_worker = SerialParamScanWorker(
            port, self.framer_combo.currentText().lower(), start_unit, end_unit,
            self.timeout_input.value() / 1000.0,
        )
        self.serial_worker.combo_matched.connect(self._on_serial_combo_matched)
        self.serial_worker.progress.connect(self.progress_bar.setValue)
        self.serial_worker.output.connect(self.output_text.append)
        self.serial_worker.scan_complete.connect(self._on_scan_complete)
        self.serial_worker.start()

    def _stop_scan(self):
        if self.tcp_scanner and self.tcp_scanner.isRunning():
            self.tcp_scanner.stop()
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.stop()

    def _on_scan_progress(self, percentage, ip=""):
        self.progress_bar.setValue(percentage)

    def _on_scan_complete(self, _count):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.transport_combo.setEnabled(True)

    def _on_tcp_device_found(self, ip, port, status):
        self._add_result_row(TCP_ROW, f"{ip}:{port}", "Modbus confirmed", "-",
                              data={"ip": ip, "port": int(port)})

    def _on_serial_combo_matched(self, baud, parity, stopbits, unit_id):
        port = self.port_combo.currentText().strip()
        framer_value = self.framer_combo.currentText().lower()
        parity_label = PARITY_LABELS.get(parity, parity)
        params = f"{baud} baud, {parity_label} parity, 8/{stopbits}, {self.framer_combo.currentText()}"
        self._add_result_row(SERIAL_ROW, port, params, str(unit_id), data={
            "serial_port": port, "baudrate": baud, "parity": parity,
            "stopbits": stopbits, "unit_id": unit_id, "framer": framer_value,
        })

    def _add_result_row(self, kind, target, params, unit_id_text, data):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        transport_item = QTableWidgetItem("TCP" if kind == TCP_ROW else "Serial")
        transport_item.setData(Qt.UserRole, (kind, data))
        self.results_table.setItem(row, 0, transport_item)
        self.results_table.setItem(row, 1, QTableWidgetItem(target))
        self.results_table.setItem(row, 2, QTableWidgetItem(params))
        self.results_table.setItem(row, 3, QTableWidgetItem(unit_id_text))

    def _clear_results(self):
        self.results_table.setRowCount(0)
        self.output_text.clear()
        self.apply_btn.setEnabled(False)

    def _on_selection_changed(self):
        self.apply_btn.setEnabled(bool(self.results_table.selectedItems()))

    def _apply_selected(self):
        """Hand the selected match to Connection Settings, pre-filled but not yet saved
        -- Save Settings there is still the deliberate action that commits it, same as
        each original tool's own Apply button worked."""
        items = self.results_table.selectedItems()
        if not items:
            return
        row = items[0].row()
        kind, data = self.results_table.item(row, 0).data(Qt.UserRole)
        self.dialog.hide()
        if kind == TCP_ROW:
            self.parent._show_connection_settings(tcp_overrides=data)
        else:
            self.parent._show_connection_settings(serial_overrides=data)

    def stop_all_scans(self):
        """Called when the main window (or this dialog) is closing, so an in-progress
        scan doesn't keep a QThread running past it."""
        self._stop_scan()
        for worker in (self.tcp_scanner, self.serial_worker):
            if worker and worker.isRunning():
                worker.wait(10000)

    def _on_dialog_close(self, event):
        self.stop_all_scans()
        event.accept()
