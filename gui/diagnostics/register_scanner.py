from collections import deque

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget,
    QComboBox, QSpinBox, QProgressBar,
)

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
    """Scanner tab: auto-discover which addresses respond on the connected device.
    Works the same way for a TCP or serial connection -- whichever is currently
    connected -- since it just reuses the app's single shared connection (like Address
    Table/Tags/Script all already do) rather than opening a second one. That means it
    pauses Tags/Address Table live monitoring first, the same way those two already
    pause each other, so nothing else polls the connection while a scan is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.address_worker = None
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

    def refresh_connection_state(self):
        connected = bool(self.parent_window.modbus and self.parent_window.modbus.is_connected())
        in_progress = self._scan_in_progress()
        self.addr_start_btn.setEnabled(connected and not in_progress)
        self.status_label.setText(
            f"Scanning: {self.parent_window.modbus.target_description()} (Unit {self.parent_window.modbus.unit_id})"
            if connected else
            "Not connected -- connect to a device first (File/Settings > Connect)."
        )

    def _pause_shared_connection_monitoring(self):
        """The Scanner reuses the app's single shared connection, so anything else
        that's polling it needs to be paused first -- otherwise two threads issue Modbus
        requests on the same socket/serial port at once. Mirrors how Address Table's Live
        Monitoring and Tags monitoring already stop one another for the same reason. The
        reconnect watchdog is the same hazard from the other direction: if it fires mid-scan
        it can call connect() and swap out self.parent_window.modbus.client out from under
        the worker thread that's mid-read on it. Trend's poll_timer is the same GUI-thread
        timer shape as Tags/Address Table monitoring, just easy to miss since it lives on a
        separate tab -- stopped directly rather than via its own Stop Trend button so the
        Start/Stop button states don't flip and confuse the user mid-scan."""
        if getattr(self.parent_window, "monitoring_active", False):
            self.parent_window._stop_monitoring()
            self.output_text.append("Paused Tags monitoring for the scan.")
        monitoring_manager = getattr(self.parent_window, "monitoring_manager", None)
        if monitoring_manager is not None:
            # Tags monitoring's own poll worker now runs its reads on a background
            # thread and doesn't finish the instant _stop_monitoring() returns -- this
            # worker bypasses the range interlock entirely (see class docstring), so it
            # needs every other reader/writer of self.modbus to be truly, provably done,
            # not just told to stop. Also covers a worker still retiring from an earlier,
            # unrelated Stop Monitoring click, which monitoring_active alone wouldn't
            # catch since that flag is already False by then.
            monitoring_manager.wait_for_idle()
        address_table = getattr(self.parent_window, "address_table_widget", None)
        if address_table is not None and getattr(address_table, "monitoring_active", False):
            address_table.monitoring_checkbox.setChecked(False)
            self.output_text.append("Paused Address Table live monitoring for the scan.")
        trend_widget = getattr(self.parent_window, "trend_widget", None)
        self._trend_was_running = bool(trend_widget and trend_widget.poll_timer.isActive())
        if self._trend_was_running:
            trend_widget.poll_timer.stop()
            self.output_text.append("Paused Trend polling for the scan.")
        watchdog = getattr(self.parent_window, "_reconnect_watchdog_timer", None)
        self._watchdog_was_active = bool(watchdog and watchdog.isActive())
        if watchdog is not None:
            watchdog.stop()

    def _start_address_scan(self):
        if not (self.parent_window.modbus and self.parent_window.modbus.is_connected()):
            self.refresh_connection_state()
            return
        if self._scan_in_progress():
            self.output_text.append("A scan is already running -- wait for it to finish first.")
            return
        script_widget = getattr(self.parent_window, "script_widget", None)
        if script_widget is not None and getattr(script_widget, "running", False):
            # Unlike Tags/Address Table monitoring or Trend, a Script run is a
            # user-directed sequence, not a background poll -- silently pausing its
            # step_timer would leave no clean, timing-safe way to resume mid-WAIT, so
            # this refuses the scan instead of pausing the script out from under it.
            self.output_text.append("A script is currently running -- stop it before starting a scan.")
            return

        start = self.addr_start_input.value()
        end = self.addr_end_input.value()
        if start > end:
            self.output_text.append("Start address must not be greater than End address.")
            return

        self._pause_shared_connection_monitoring()
        self._found_ranges = []
        self.output_text.append(
            f"Scanning {self.addr_function_combo.currentText()} {start}-{end}..."
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.addr_start_btn.setEnabled(False)
        self.addr_stop_btn.setEnabled(True)

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

        # Resume the reconnect watchdog we paused before the scan, if the connection it
        # was watching is still the live one.
        if getattr(self, "_watchdog_was_active", False):
            self._watchdog_was_active = False
            watchdog = getattr(self.parent_window, "_reconnect_watchdog_timer", None)
            if watchdog is not None and self.parent_window.modbus and self.parent_window.modbus.is_connected():
                watchdog.start(self.parent_window.WATCHDOG_HEALTHY_INTERVAL_MS)

        # Resume Trend polling we paused before the scan, same live-connection guard as
        # the watchdog above -- if the connection dropped during the scan there's nothing
        # to resume polling against.
        if getattr(self, "_trend_was_running", False):
            self._trend_was_running = False
            trend_widget = getattr(self.parent_window, "trend_widget", None)
            if trend_widget is not None and self.parent_window.modbus and self.parent_window.modbus.is_connected():
                trend_widget.poll_timer.start(trend_widget.interval_input.value())
                self.output_text.append("Resumed Trend polling.")

    def _scan_in_progress(self):
        return bool(self.address_worker and self.address_worker.isRunning())

    def stop_all_scans(self):
        """Called when the main window is closing or disconnecting, so an in-progress
        scan doesn't keep a QThread running -- and, more importantly, doesn't touch the
        shared connection after the caller has moved on to closing/replacing it. Blocks
        until the worker thread has actually exited (it checks should_stop at least once
        per probe, so this returns within one probe timeout, not indefinitely)."""
        self._stop_address_scan()
        if self.address_worker and self.address_worker.isRunning():
            self.address_worker.wait(10000)
