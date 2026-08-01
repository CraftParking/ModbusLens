from collections import deque

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget,
    QComboBox, QSpinBox, QProgressBar, QTabWidget,
)

from core.modbus_client import ModbusClient

# Floor between any two Modbus requests the scanner issues, regardless of how short a
# probe timeout is configured -- mirrors the Script tab's MIN_STEP_INTERVAL_MS and the
# Network Scanner's 50ms IP-probe delay: a fast timeout shouldn't turn into flooding.
PROBE_DELAY_MS = 20

# Modbus spec maximums per read function -- the largest single request a scan can try
# before it has to bisect down to find exactly which addresses respond.
_MAX_BLOCK = {
    "Coils": 2000,
    "Discrete Inputs": 2000,
    "Holding Registers": 125,
    "Input Registers": 125,
}
FUNCTION_TYPES = ["Coils", "Discrete Inputs", "Holding Registers", "Input Registers"]

# Illegal Function -- the one exception code that means the whole function isn't
# supported by this device at all, not just this address range. Every address would
# come back the same way, so there's no point bisecting down to find out.
_ILLEGAL_FUNCTION = 1


def _read_block(modbus, function_name, address, count):
    if function_name == "Coils":
        return modbus.read_coils(address, count)
    if function_name == "Discrete Inputs":
        return modbus.read_discrete_inputs(address, count)
    if function_name == "Input Registers":
        return modbus.read_input_registers(address, count)
    return modbus.read_registers(address, count)


def detect_serial_ports():
    try:
        from serial.tools import list_ports
        ports = [p.device for p in list_ports.comports()]
        if ports:
            return ports
    except Exception:
        pass
    return ["COM1", "COM2", "COM3", "COM4"]


# Common serial settings to sweep for the Serial Parameter Scanner -- byte size is
# deliberately not swept, since 8 data bits is the near-universal default and adding a
# fourth dimension would multiply the already-large combination count for little benefit.
BAUD_RATES_TO_TRY = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
PARITIES_TO_TRY = ["N", "E", "O"]
STOPBITS_TO_TRY = [1, 2]


class AddressScanWorker(QThread):
    """Auto-discovers which addresses respond on the connected device, for one function
    type over [start, end]. Reads the largest block the function allows first; a clean
    read means every address in it responds, an Illegal Data Address exception means at
    least one address in the block doesn't, and the block is bisected to find exactly
    which addresses do -- far fewer requests than probing one address at a time for a
    mostly-contiguous register map, while still resolving individually where it matters."""

    range_found = Signal(int, int)  # start, count -- a confirmed contiguous responding run
    progress = Signal(int)  # 0-100
    output = Signal(str)
    scan_complete = Signal(int, int)  # responding_count, probes_issued

    def __init__(self, modbus, function_name, start_address, end_address, probe_timeout):
        super().__init__()
        self.modbus = modbus
        self.function_name = function_name
        # Not self.start/self.end -- QThread already defines a start() method, and
        # assigning over it here silently breaks the real start() call from the caller.
        self.start_address = start_address
        self.end_address = end_address  # inclusive
        self.probe_timeout = probe_timeout
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        total = self.end_address - self.start_address + 1
        max_block = _MAX_BLOCK[self.function_name]
        original_timeout = self.modbus.get_timeout()
        self.modbus.set_timeout(self.probe_timeout)

        responding = 0
        probes = 0
        resolved = 0
        aborted = False
        try:
            pending = deque()
            addr = self.start_address
            while addr <= self.end_address:
                block = min(max_block, self.end_address - addr + 1)
                pending.append((addr, block))
                addr += block

            while pending and not self.should_stop:
                block_start, count = pending.popleft()
                probes += 1
                result = _read_block(self.modbus, self.function_name, block_start, count)
                self.msleep(PROBE_DELAY_MS)

                if result is not None:
                    responding += count
                    resolved += count
                    self.range_found.emit(block_start, count)
                elif self.modbus.last_exception_code == _ILLEGAL_FUNCTION:
                    self.output.emit(
                        f"{self.function_name} is not supported by this device "
                        f"(Illegal Function) -- stopping."
                    )
                    aborted = True
                    break
                elif self.modbus.last_exception_code is not None:
                    # Any other exception -- Illegal Data Address, Illegal Data Value, or
                    # a non-compliant device's own error code for "not here" -- means this
                    # block isn't fully readable, not that the device stopped responding.
                    # Keep narrowing rather than treating it as fatal.
                    if count == 1:
                        resolved += 1  # confirmed: this single address doesn't respond
                    else:
                        left = count // 2
                        pending.appendleft((block_start + left, count - left))
                        pending.appendleft((block_start, left))
                else:
                    # No exception code at all -- a real timeout/connection failure, not
                    # the device telling us "not here." Continuing would just probe a
                    # dead connection.
                    self.output.emit(
                        f"Stopped at address {block_start}: {self.modbus.last_error or 'no response'}"
                    )
                    aborted = True
                    break

                self.progress.emit(int(resolved / total * 100) if total else 100)
        finally:
            self.modbus.set_timeout(original_timeout)

        if not aborted:
            self.output.emit("Scan stopped." if self.should_stop else "Scan complete.")
        self.scan_complete.emit(responding, probes)


class SerialParamScanWorker(QThread):
    """Tries common baud rate / parity / stop-bit combinations against a serial port to
    find which one a device actually speaks, for when its settings aren't documented.
    Unlike the other two scan modes, this doesn't reuse the app's shared connection --
    it opens and closes its own short-lived connection per combination, since testing a
    physical serial setting means actually reopening the port with it. That also means
    it can't run while ModbusLens (or anything else) already holds the same port open."""

    combo_matched = Signal(int, str, int)  # baud, parity, stopbits
    progress = Signal(int)
    output = Signal(str)
    scan_complete = Signal(int)  # matches found

    def __init__(self, serial_port, framer, unit_id, probe_function, probe_address, per_trial_timeout):
        super().__init__()
        self.serial_port = serial_port
        self.framer = framer
        self.unit_id = unit_id
        self.probe_function = probe_function
        self.probe_address = probe_address
        self.per_trial_timeout = per_trial_timeout
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        combos = [
            (baud, parity, stopbits)
            for baud in BAUD_RATES_TO_TRY
            for parity in PARITIES_TO_TRY
            for stopbits in STOPBITS_TO_TRY
        ]
        total = len(combos)
        matches = 0

        for i, (baud, parity, stopbits) in enumerate(combos):
            if self.should_stop:
                break
            label = f"{baud} baud, parity={parity}, stop bits={stopbits}"
            client = ModbusClient(
                unit_id=self.unit_id, timeout=self.per_trial_timeout, retries=0,
                mode="serial", serial_port=self.serial_port, baudrate=baud,
                parity=parity, stopbits=stopbits, bytesize=8, serial_framer=self.framer,
            )
            if not client.connect():
                # The port itself couldn't be opened at all -- likely already held open
                # by ModbusLens's own connection or another program. No combination can
                # work until that's resolved, so stop instead of repeating the same
                # failure for every remaining combo.
                self.output.emit(
                    f"Could not open {self.serial_port}: {client.last_error or 'unknown error'}. "
                    f"Make sure nothing else (including ModbusLens's own connection) has this "
                    f"port open, then try again."
                )
                break

            result = _read_block(client, self.probe_function, self.probe_address, 1)
            present = result is not None or client.last_exception_code is not None
            client.disconnect()
            if present:
                matches += 1
                self.combo_matched.emit(baud, parity, stopbits)
                self.output.emit(f"  MATCH: {label}")

            self.progress.emit(int((i + 1) / total * 100))
            self.msleep(PROBE_DELAY_MS)

        self.output.emit("Scan stopped." if self.should_stop else "Scan complete.")
        self.scan_complete.emit(matches)


def _merge_ranges(ranges):
    """Collapse a list of (start, count) tuples, in the order they were found, into
    merged (start, end) spans for a clean final summary."""
    merged = []
    for start, count in ranges:
        end = start + count - 1
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


class RegisterScannerWidget(QWidget):
    """Scanner tab: auto-discover which addresses respond on the connected device (Register),
    or sweep serial settings to find which one a device actually speaks (Serial). The
    Register scan reuses the app's single shared connection (like Address Table/Tags/Script
    all already do) rather than opening a second one -- so it pauses Tags/Address Table live
    monitoring first, the same way those two already pause each other to avoid sharing the
    connection concurrently. The Serial scan is different: it opens its own short-lived
    connection per combination, so it can't run while the shared connection holds the same
    port."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.address_worker = None
        self.serial_worker = None
        self.output_text = None
        self._found_ranges = []
        self._setup_ui()
        self.refresh_connection_state()

    def _setup_ui(self):
        c = self.parent_window._colors()
        layout = QVBoxLayout(self)

        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {c['text_secondary']};")
        layout.addWidget(self.status_label)

        tabs = QTabWidget()
        tabs.addTab(self._build_address_scan_tab(), "Register")
        tabs.addTab(self._build_serial_scan_tab(), "Serial")
        layout.addWidget(tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.document().setMaximumBlockCount(5000)
        self.output_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
        """)
        layout.addWidget(self.output_text, 1)

    def _build_address_scan_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Function:"))
        self.addr_function_combo = QComboBox()
        self.addr_function_combo.setStyleSheet(self.parent_window._get_input_style())
        self.addr_function_combo.addItems(FUNCTION_TYPES)
        self.addr_function_combo.setCurrentText("Holding Registers")
        row1.addWidget(self.addr_function_combo)

        row1.addWidget(QLabel("Start:"))
        self.addr_start_input = QSpinBox()
        self.addr_start_input.setStyleSheet(self.parent_window._get_input_style())
        self.addr_start_input.setRange(0, 65535)
        self.addr_start_input.setValue(0)
        row1.addWidget(self.addr_start_input)

        row1.addWidget(QLabel("End:"))
        self.addr_end_input = QSpinBox()
        self.addr_end_input.setStyleSheet(self.parent_window._get_input_style())
        self.addr_end_input.setRange(0, 65535)
        self.addr_end_input.setValue(999)
        row1.addWidget(self.addr_end_input)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Probe timeout (ms):"))
        self.addr_timeout_input = QSpinBox()
        self.addr_timeout_input.setStyleSheet(self.parent_window._get_input_style())
        self.addr_timeout_input.setRange(50, 5000)
        self.addr_timeout_input.setValue(300)
        row2.addWidget(self.addr_timeout_input)
        row2.addStretch()

        self.addr_start_btn = QPushButton("Start Scan")
        self.addr_start_btn.setStyleSheet(self.parent_window._get_button_style())
        self.addr_start_btn.clicked.connect(self._start_address_scan)
        row2.addWidget(self.addr_start_btn)

        self.addr_stop_btn = QPushButton("Stop")
        self.addr_stop_btn.setStyleSheet(self.parent_window._get_button_style())
        self.addr_stop_btn.setEnabled(False)
        self.addr_stop_btn.clicked.connect(self._stop_address_scan)
        row2.addWidget(self.addr_stop_btn)
        layout.addLayout(row2)

        layout.addStretch()
        return tab

    def _build_serial_scan_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("COM Port:"))
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setEditable(True)
        self.serial_port_combo.setStyleSheet(self.parent_window._get_input_style())
        self.serial_port_combo.addItems(detect_serial_ports())
        row1.addWidget(self.serial_port_combo)

        row1.addWidget(QLabel("Framing:"))
        self.serial_framer_combo = QComboBox()
        self.serial_framer_combo.setStyleSheet(self.parent_window._get_input_style())
        self.serial_framer_combo.addItems(["RTU", "ASCII"])
        row1.addWidget(self.serial_framer_combo)

        row1.addWidget(QLabel("Unit ID:"))
        self.serial_unit_input = QSpinBox()
        self.serial_unit_input.setStyleSheet(self.parent_window._get_input_style())
        self.serial_unit_input.setRange(0, 247)
        self.serial_unit_input.setValue(1)
        row1.addWidget(self.serial_unit_input)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Probe:"))
        self.serial_probe_function_combo = QComboBox()
        self.serial_probe_function_combo.setStyleSheet(self.parent_window._get_input_style())
        self.serial_probe_function_combo.addItems(FUNCTION_TYPES)
        self.serial_probe_function_combo.setCurrentText("Holding Registers")
        row2.addWidget(self.serial_probe_function_combo)

        row2.addWidget(QLabel("Address:"))
        self.serial_probe_address_input = QSpinBox()
        self.serial_probe_address_input.setStyleSheet(self.parent_window._get_input_style())
        self.serial_probe_address_input.setRange(0, 65535)
        row2.addWidget(self.serial_probe_address_input)

        row2.addWidget(QLabel("Per-trial timeout (ms):"))
        self.serial_timeout_input = QSpinBox()
        self.serial_timeout_input.setStyleSheet(self.parent_window._get_input_style())
        self.serial_timeout_input.setRange(50, 2000)
        self.serial_timeout_input.setValue(200)
        row2.addWidget(self.serial_timeout_input)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addStretch()
        self.serial_start_btn = QPushButton("Start Scan")
        self.serial_start_btn.setStyleSheet(self.parent_window._get_button_style())
        self.serial_start_btn.clicked.connect(self._start_serial_scan)
        row3.addWidget(self.serial_start_btn)

        self.serial_stop_btn = QPushButton("Stop")
        self.serial_stop_btn.setStyleSheet(self.parent_window._get_button_style())
        self.serial_stop_btn.setEnabled(False)
        self.serial_stop_btn.clicked.connect(self._stop_serial_scan)
        row3.addWidget(self.serial_stop_btn)
        layout.addLayout(row3)

        layout.addStretch()
        return tab

    def refresh_connection_state(self):
        connected = bool(self.parent_window.modbus and self.parent_window.modbus.is_connected())
        in_progress = self._scan_in_progress()
        self.addr_start_btn.setEnabled(connected and not in_progress)
        # The Serial scan doesn't use the shared connection at all -- it just can't run
        # alongside the Register scan, which does.
        self.serial_start_btn.setEnabled(not in_progress)
        self.status_label.setText(
            f"Scanning: {self.parent_window.modbus.target_description()} (Unit {self.parent_window.modbus.unit_id})"
            if connected else
            "Not connected -- connect to a device first (File/Settings > Connect)."
        )

    def _pause_shared_connection_monitoring(self):
        """Register Scanner reuses the app's single shared connection, so anything else
        that's polling it needs to be paused first -- otherwise two threads issue Modbus
        requests on the same socket/serial port at once. Mirrors how Address Table's Live
        Monitoring and Tags monitoring already stop one another for the same reason."""
        if getattr(self.parent_window, "monitoring_active", False):
            self.parent_window._stop_monitoring()
            self.output_text.append("Paused Tags monitoring for the scan.")
        address_table = getattr(self.parent_window, "address_table_widget", None)
        if address_table is not None and getattr(address_table, "monitoring_active", False):
            address_table.monitoring_checkbox.setChecked(False)
            self.output_text.append("Paused Address Table live monitoring for the scan.")

    def _start_address_scan(self):
        if not (self.parent_window.modbus and self.parent_window.modbus.is_connected()):
            self.refresh_connection_state()
            return
        if self._scan_in_progress():
            self.output_text.append("A scan is already running -- wait for it to finish first.")
            return
        self._pause_shared_connection_monitoring()

        start = self.addr_start_input.value()
        end = self.addr_end_input.value()
        if start > end:
            self.output_text.append("Start address must not be greater than End address.")
            return

        self._found_ranges = []
        self.output_text.append(
            f"Scanning {self.addr_function_combo.currentText()} {start}-{end}..."
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.addr_start_btn.setEnabled(False)
        self.addr_stop_btn.setEnabled(True)
        self.serial_start_btn.setEnabled(False)  # only one scan mode at a time

        self.address_worker = AddressScanWorker(
            self.parent_window.modbus, self.addr_function_combo.currentText(), start, end,
            self.addr_timeout_input.value() / 1000.0,
        )
        self.address_worker.range_found.connect(self._on_address_range_found)
        self.address_worker.progress.connect(self.progress_bar.setValue)
        self.address_worker.output.connect(self.output_text.append)
        self.address_worker.scan_complete.connect(self._on_address_scan_complete)
        self.address_worker.start()

    def _stop_address_scan(self):
        if self.address_worker and self.address_worker.isRunning():
            self.address_worker.stop()

    def _on_address_range_found(self, start, count):
        self._found_ranges.append((start, count))
        end = start + count - 1
        self.output_text.append(f"  responding: {start}" if count == 1 else f"  responding: {start}-{end}")

    def _on_address_scan_complete(self, responding_count, probes_issued):
        merged = _merge_ranges(self._found_ranges)
        if merged:
            summary = ", ".join(f"{s}" if s == e else f"{s}-{e}" for s, e in merged)
            self.output_text.append(f"Summary: {responding_count} responding address(es): {summary}")
        else:
            self.output_text.append("Summary: no responding addresses found in range.")
        self.output_text.append(f"({probes_issued} request(s) issued)")
        self.progress_bar.setVisible(False)
        self.addr_stop_btn.setEnabled(False)
        self.refresh_connection_state()

    def _start_serial_scan(self):
        if self._scan_in_progress():
            self.output_text.append("A scan is already running -- wait for it to finish first.")
            return

        port = self.serial_port_combo.currentText().strip()
        if not port:
            self.output_text.append("Enter or select a COM port first.")
            return

        self.output_text.append(f"Scanning serial settings on {port}...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.serial_start_btn.setEnabled(False)
        self.serial_stop_btn.setEnabled(True)
        self.addr_start_btn.setEnabled(False)  # only one scan mode at a time

        self.serial_worker = SerialParamScanWorker(
            port, self.serial_framer_combo.currentText().lower(), self.serial_unit_input.value(),
            self.serial_probe_function_combo.currentText(), self.serial_probe_address_input.value(),
            self.serial_timeout_input.value() / 1000.0,
        )
        self.serial_worker.progress.connect(self.progress_bar.setValue)
        self.serial_worker.output.connect(self.output_text.append)
        self.serial_worker.scan_complete.connect(self._on_serial_scan_complete)
        self.serial_worker.start()

    def _stop_serial_scan(self):
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.stop()

    def _on_serial_scan_complete(self, matches_found):
        self.output_text.append(f"Summary: {matches_found} working combination(s) found.")
        self.progress_bar.setVisible(False)
        self.serial_stop_btn.setEnabled(False)
        self.refresh_connection_state()

    def _scan_in_progress(self):
        return (
            (self.address_worker and self.address_worker.isRunning())
            or (self.serial_worker and self.serial_worker.isRunning())
        )

    def stop_all_scans(self):
        """Called when the main window is closing, so an in-progress scan doesn't keep a
        QThread running (and the connection's Unit ID/timeout unrestored) after exit."""
        self._stop_address_scan()
        self._stop_serial_scan()
