from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QComboBox, QSpinBox, QProgressBar, QListWidget, QListWidgetItem,
)

from core.modbus_client import ModbusClient

# Floor between any two connection attempts, regardless of how short the per-trial
# timeout is configured -- mirrors the Script tab's MIN_STEP_INTERVAL_MS and the
# Network Scanner's 50ms IP-probe delay: a fast timeout shouldn't turn into flooding.
PROBE_DELAY_MS = 20


def modbus_rtu_t35_ms(baud):
    """Modbus RTU's own minimum inter-frame silent interval (3.5 character times).
    Fixed at 1.75ms above 19200 baud per spec; below that it scales with the baud rate,
    using the spec's own fixed 11-bit character time (start + 8 data + parity/stop)
    regardless of the parity/stopbits actually in use -- the spec makes that same
    simplification. At low baud (e.g. 1200) this is well past the flat PROBE_DELAY_MS
    floor above (~32ms vs. 20ms); at anything above ~2400 baud the floor already covers it."""
    if baud > 19200:
        return 1.75
    return (3.5 * 11 / baud) * 1000

# Common serial settings to sweep -- byte size is deliberately not swept, since 8 data
# bits is the near-universal default and a fourth dimension would multiply the already
# large combination count for little benefit.
BAUD_RATES_TO_TRY = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
PARITIES_TO_TRY = ["N", "E", "O"]
STOPBITS_TO_TRY = [1, 2]

# Human-readable labels for the parity codes above, matching how Connection Settings
# displays them (ConnectionSettingsDialog.PARITIES) -- kept as a local copy since
# main_window importing this module already goes the other way.
PARITY_LABELS = {"N": "None", "E": "Even", "O": "Odd"}

# Fixed probe: a single Holding Register read is supported by virtually every device,
# and this dialog is only about finding the serial settings, not about registers at all.
_PROBE_FUNCTION = "Holding Registers"
_PROBE_ADDRESS = 0


def detect_serial_ports():
    try:
        from serial.tools import list_ports
        ports = [p.device for p in list_ports.comports()]
        if ports:
            return ports
    except Exception:
        pass
    return ["COM1", "COM2", "COM3", "COM4"]


class SerialParamScanWorker(QThread):
    """Tries common baud rate / parity / stop-bit / Unit ID combinations against a
    serial port to find which one a device actually speaks, for when its settings
    aren't documented. Opens and closes its own short-lived connection per combination,
    since testing a physical serial setting means actually reopening the port with it --
    that also means it can't run while ModbusLens (or anything else) already holds the
    same port open."""

    combo_matched = Signal(int, str, int, int)  # baud, parity, stopbits, unit_id
    progress = Signal(int)
    output = Signal(str)
    scan_complete = Signal(int)  # matches found

    def __init__(self, serial_port, framer, start_unit, end_unit, per_trial_timeout):
        super().__init__()
        self.serial_port = serial_port
        self.framer = framer
        self.start_unit = start_unit
        self.end_unit = end_unit
        self.per_trial_timeout = per_trial_timeout
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        combos = [
            (baud, parity, stopbits, unit_id)
            for baud in BAUD_RATES_TO_TRY
            for parity in PARITIES_TO_TRY
            for stopbits in STOPBITS_TO_TRY
            for unit_id in range(self.start_unit, self.end_unit + 1)
        ]
        total = len(combos)
        matches = 0

        for i, (baud, parity, stopbits, unit_id) in enumerate(combos):
            if self.should_stop:
                break
            label = f"{baud} baud, parity={parity}, stop bits={stopbits}, unit {unit_id}"
            client = ModbusClient(
                unit_id=unit_id, timeout=self.per_trial_timeout, retries=0,
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

            result = client.read_registers(_PROBE_ADDRESS, 1)
            present = result is not None or client.last_exception_code is not None
            client.disconnect()
            if present:
                matches += 1
                self.combo_matched.emit(baud, parity, stopbits, unit_id)
                self.output.emit(f"  MATCH: {label}")

            self.progress.emit(int((i + 1) / total * 100))
            self.msleep(int(round(max(PROBE_DELAY_MS, modbus_rtu_t35_ms(baud)))))

        self.output.emit("Scan stopped." if self.should_stop else "Scan complete.")
        self.scan_complete.emit(matches)


class SerialDiscoveryDialog:
    """Diagnostics > Serial Discovery: sweeps common baud rate/parity/stop-bit/Unit ID
    combinations against a COM port to find which one a device actually speaks. Doesn't
    reuse the app's shared connection -- it opens its own for each combination, since
    testing a physical serial setting means actually reopening the port with it, so it
    can't run while ModbusLens's own connection (or anything else) holds the same port."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.dialog = None
        self.worker = None
        self.output_text = None

    def show_discovery(self, initial_port=None):
        if self.dialog is None:
            self._build_dialog()
        if initial_port:
            self.port_combo.setCurrentText(initial_port)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _build_dialog(self):
        c = self.parent._colors()
        self.dialog = QDialog(self.parent)
        self.dialog.setWindowTitle("Serial Discovery")
        self.dialog.setGeometry(300, 300, 620, 520)
        self.dialog.closeEvent = self._on_dialog_close

        layout = QVBoxLayout(self.dialog)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("COM Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setStyleSheet(self.parent._get_input_style())
        self.port_combo.addItems(detect_serial_ports())
        row1.addWidget(self.port_combo)

        row1.addWidget(QLabel("Framing:"))
        self.framer_combo = QComboBox()
        self.framer_combo.setStyleSheet(self.parent._get_input_style())
        self.framer_combo.addItems(["RTU", "ASCII"])
        row1.addWidget(self.framer_combo)
        layout.addLayout(row1)

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
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addStretch()
        self.start_btn = QPushButton("Start Scan")
        self.start_btn.setStyleSheet(self.parent._get_button_style())
        self.start_btn.clicked.connect(self._start_scan)
        row3.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(self.parent._get_button_style())
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_scan)
        row3.addWidget(self.stop_btn)
        layout.addLayout(row3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Matches found (select one, then Apply):"))
        self.matches_list = QListWidget()
        self.matches_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}
        """)
        self.matches_list.setMaximumHeight(90)
        self.matches_list.itemSelectionChanged.connect(self._on_match_selection_changed)
        self.matches_list.itemDoubleClicked.connect(lambda _item: self._apply_selected_match())
        layout.addWidget(self.matches_list)

        apply_row = QHBoxLayout()
        apply_row.addStretch()
        self.apply_btn = QPushButton("Apply to Connection Settings")
        self.apply_btn.setStyleSheet(self.parent._get_button_style())
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply_selected_match)
        apply_row.addWidget(self.apply_btn)
        layout.addLayout(apply_row)

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

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self.parent._get_button_style())
        close_btn.clicked.connect(self.dialog.hide)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def _start_scan(self):
        if self.worker and self.worker.isRunning():
            self.output_text.append("A scan is already running -- wait for it to finish first.")
            return

        port = self.port_combo.currentText().strip()
        if not port:
            self.output_text.append("Enter or select a COM port first.")
            return

        modbus = getattr(self.parent, "modbus", None)
        if (
            modbus and modbus.is_connected() and modbus.mode == "serial"
            and modbus.serial_port.strip().upper() == port.upper()
        ):
            # This worker opens its own connection per combination instead of reusing
            # the shared one (see class docstring) -- on the same port as the app's live
            # connection, every open attempt would just fail against the OS's exclusive
            # serial lock, wasting the whole sweep on false negatives instead of the
            # real settings. Catching it here gives a clear reason instead of a scan
            # that silently "finds" nothing.
            self.output_text.append(
                f"{port} is the app's current connection -- disconnect first, or scan a different port."
            )
            return

        start_unit = self.start_unit_input.value()
        end_unit = self.end_unit_input.value()
        if start_unit > end_unit:
            self.output_text.append("Start Unit ID must not be greater than End Unit ID.")
            return

        total_combos = (
            len(BAUD_RATES_TO_TRY) * len(PARITIES_TO_TRY) * len(STOPBITS_TO_TRY)
            * (end_unit - start_unit + 1)
        )
        self.output_text.append(f"Scanning serial settings on {port} ({total_combos} combination(s))...")
        self.matches_list.clear()
        self.apply_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.worker = SerialParamScanWorker(
            port, self.framer_combo.currentText().lower(), start_unit, end_unit,
            self.timeout_input.value() / 1000.0,
        )
        self.worker.combo_matched.connect(self._on_combo_matched)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.output.connect(self.output_text.append)
        self.worker.scan_complete.connect(self._on_scan_complete)
        self.worker.start()

    def _on_combo_matched(self, baud, parity, stopbits, unit_id):
        port = self.port_combo.currentText().strip()
        framer_value = self.framer_combo.currentText().lower()
        parity_label = PARITY_LABELS.get(parity, parity)
        item = QListWidgetItem(
            f"{port} @ {baud} baud ({parity_label} parity, 8/{stopbits}, "
            f"{self.framer_combo.currentText()}, Unit {unit_id})"
        )
        item.setData(Qt.UserRole, (port, baud, parity, stopbits, unit_id, framer_value))
        self.matches_list.addItem(item)

    def _on_match_selection_changed(self):
        self.apply_btn.setEnabled(self.matches_list.currentItem() is not None)

    def _apply_selected_match(self):
        """Hand a chosen match to Connection Settings, pre-filled but not yet saved --
        mirrors picking a Recent Connections entry there: Save Settings is still the
        deliberate action that commits it, this just fills the form."""
        item = self.matches_list.currentItem()
        if item is None:
            return
        port, baud, parity, stopbits, unit_id, framer = item.data(Qt.UserRole)
        self.dialog.hide()
        self.parent._show_connection_settings(serial_overrides={
            "serial_port": port,
            "baudrate": baud,
            "parity": parity,
            "stopbits": stopbits,
            "unit_id": unit_id,
            "framer": framer,
        })

    def _stop_scan(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()

    def _on_scan_complete(self, matches_found):
        self.output_text.append(f"Summary: {matches_found} working combination(s) found.")
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def stop_all_scans(self):
        """Called when the main window is closing (or the dialog itself is), so an
        in-progress scan doesn't keep a QThread running -- and, on app exit, doesn't get
        torn down by Qt/Python mid-run, which can abort the process. Blocks until the
        worker has actually exited (it checks should_stop at least once per trial, so
        this returns within one probe timeout, not indefinitely)."""
        self._stop_scan()
        if self.worker and self.worker.isRunning():
            self.worker.wait(10000)

    def _on_dialog_close(self, event):
        self.stop_all_scans()
        event.accept()
