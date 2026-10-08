import math
from collections import deque

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QCheckBox,
    QComboBox, QSpinBox, QProgressBar, QGroupBox, QDialog, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QTabBar,
)

from theme import apply_dropdown_delegate
from widgets.device_selector import DeviceSelector

# Excel's own "Good"/"Bad" conditional-format colors -- the scan result grid deliberately
# looks like a spreadsheet regardless of the app's light/dark theme, the same way Excel's
# own red/green never changes with Windows' theme.
_PALETTE_STANDARD = {
    "ok": (QColor("#C6EFCE"), QColor("#006100"), "responds"),
    "bad": (QColor("#FFC7CE"), QColor("#9C0006"), "no response"),
}
# Blue/orange instead of green/red -- the classic colorblind-safe substitute (still
# distinguishable under deuteranopia, protanopia and tritanopia, unlike red/green).
_PALETTE_COLORBLIND = {
    "ok": (QColor("#BFE1F5"), QColor("#003C64"), "responds"),
    "bad": (QColor("#FFE1B3"), QColor("#7A4A00"), "no response"),
}

# Target cell size for working out how many addresses fit one Excel-like "sheet" page at
# the grid's current on-screen size -- a page's actual columns still stretch evenly to
# fill the width (QHeaderView.Stretch); this only decides where to split pages. Both grow
# with the user's chosen text size so a page's cells stay readable at that size.
_GRID_CELL_WIDTH_PER_PX = 6  # roughly how many px of cell width one px of font needs
_GRID_ROW_HEIGHT_PADDING = 12
_GRID_MIN_COLUMNS = 4
_GRID_MIN_ROWS = 3
_GRID_DEFAULT_FONT_PX = 10

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

# Bridges this file's own plural function names to the exact singular strings the shared
# busy/overlap interlock uses everywhere else (Tags' type_combo, Address Table's
# _SPACE_LABELS) -- without this, the interlock's overlap check would always compare
# unequal strings and never actually detect a real overlap against this scanner.
_SPACE_LABELS = {
    "Coils": "Coil",
    "Discrete Inputs": "Discrete Input",
    "Holding Registers": "Holding Register",
    "Input Registers": "Input Register",
}

# Default tag naming for Create Tags From Scan: classic 5-digit Modicon convention
# (COIL_00001/DI_10001/IR_30001/HR_40001 -- type digit + 4-digit 1-based address) --
# just a readable, addressable default label, never a guess at what the register means.
_TAG_NAME_PREFIX = {"Coils": "COIL", "Discrete Inputs": "DI", "Input Registers": "IR", "Holding Registers": "HR"}
_MODICON_DIGIT = {"Coils": "0", "Discrete Inputs": "1", "Input Registers": "3", "Holding Registers": "4"}


def _default_scanned_tag_name(function_name, protocol_offset):
    return f"{_TAG_NAME_PREFIX[function_name]}_{_MODICON_DIGIT[function_name]}{protocol_offset + 1:04d}"


# Consecutive busy-skips (interlock contention) before giving up on the scan entirely,
# rather than retrying forever -- _pause_shared_connection_monitoring already stops every
# other reader/writer before a scan starts, so sustained contention past this many retries
# (~1s at PROBE_DELAY_MS) means something is genuinely stuck, not a brief overlap.
MAX_CONSECUTIVE_BUSY_RETRIES = 50

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
    range_not_responding = Signal(int)  # address -- a single address confirmed not to respond
    progress = Signal(int)  # 0-100
    output = Signal(str)
    scan_complete = Signal(int, int)  # responding_count, probes_issued

    def __init__(self, modbus, function_name, start_address, end_address, probe_timeout,
                 reserve_range=None, release_range=None):
        super().__init__()
        self.modbus = modbus
        self.function_name = function_name
        # Not self.start/self.end -- QThread already defines a start() method, and
        # assigning over it here silently breaks the real start() call from the caller.
        self.start_address = start_address
        self.end_address = end_address  # inclusive
        self.probe_timeout = probe_timeout
        # Default to permissive no-ops so this stays usable standalone (e.g. in tests)
        # without a real main window -- same pattern ScriptRunner already uses.
        self.reserve_range = reserve_range or (lambda request_range: True)
        self.release_range = release_range or (lambda request_range: None)
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

            consecutive_busy = 0
            while pending and not self.should_stop:
                block_start, count = pending.popleft()

                request_range = {
                    "operation": "read", "space": _SPACE_LABELS[self.function_name],
                    "start": block_start, "end": block_start + count - 1,
                    "tag": f"RegisterScanner[{self.function_name}]",
                }
                if not self.reserve_range(request_range):
                    # Busy -- something else briefly holds this exact range. Should be rare:
                    # _pause_shared_connection_monitoring already stopped every other
                    # reader/writer before this scan started. Re-queue at the back rather
                    # than treating it as a device failure.
                    consecutive_busy += 1
                    if consecutive_busy > MAX_CONSECUTIVE_BUSY_RETRIES:
                        self.output.emit(
                            "Stopped: register range stayed busy too long -- another "
                            "operation may be stuck holding it."
                        )
                        aborted = True
                        break
                    pending.append((block_start, count))
                    self.msleep(PROBE_DELAY_MS)
                    continue
                consecutive_busy = 0

                probes += 1
                try:
                    result = _read_block(self.modbus, self.function_name, block_start, count)
                finally:
                    self.release_range(request_range)
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
                        self.range_not_responding.emit(block_start)
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


class CreateTagsFromScanDialog(QDialog):
    """Shown from "Create Tags..." after a scan finds responding addresses -- lets the
    user pick which of the found (merged, contiguous) ranges to import, one new Tags-tab
    row per individual address in the checked ranges. Confirming here IS the "don't
    auto-create tags without user confirmation" gate; there's no second nested confirm."""

    def __init__(self, function_name, merged_ranges, parent=None):
        super().__init__(parent)
        self.function_name = function_name
        self.setWindowTitle("Create Tags From Scan")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        total = sum(end - start + 1 for start, end in merged_ranges)
        layout.addWidget(QLabel(
            f"{function_name}: {len(merged_ranges)} responding range(s), {total} address(es) total.\n"
            "Choose which ranges to import -- one new Tags-tab row per address, named\n"
            f"{_TAG_NAME_PREFIX[function_name]}_{_MODICON_DIGIT[function_name]}xxxx. An address that\n"
            "already has a tag of this type is skipped rather than duplicated."
        ))

        self.list_widget = QListWidget()
        for start, end in merged_ranges:
            count = end - start + 1
            label = f"{start} (1 address)" if count == 1 else f"{start}-{end} ({count} addresses)"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, (start, end))
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        create_btn = QPushButton("Create Tags")
        create_btn.clicked.connect(self.accept)
        button_row.addWidget(create_btn)
        layout.addLayout(button_row)

    def selected_addresses(self):
        """Every individual protocol-offset address across the checked ranges, in order."""
        addresses = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                start, end = item.data(Qt.UserRole)
                addresses.extend(range(start, end + 1))
        return addresses


class RegisterScannerWidget(QWidget):
    """Scanner tab: auto-discover which addresses respond on the device picked in its
    Device selector, over TCP or serial. It reuses that device's existing link rather
    than opening a second one, so it stops Tags/Address Table live monitoring and pauses
    Trend and the reconnect watchdog first -- nothing else polls while a scan runs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.address_worker = None
        self._found_ranges = []
        self._cell_font_px = _GRID_DEFAULT_FONT_PX
        self._colorblind = False
        self._scan_range = None  # (start, end) of the last prepared/run scan, for repagination
        self._setup_ui()
        self.refresh_connection_state()

    def _setup_ui(self):
        c = self.parent_window._colors()
        layout = QVBoxLayout(self)

        status_row = QHBoxLayout()
        self.device_selector = DeviceSelector(self.parent_window, tooltip="The device to scan")
        self.device_selector.changed.connect(lambda _name: self.refresh_connection_state())
        status_row.addWidget(self.device_selector)
        self.status_label = QLabel()
        self.status_label.setStyleSheet(f"color: {c['text_secondary']};")
        status_row.addWidget(self.status_label, 1)
        layout.addLayout(status_row)

        control_group = QGroupBox("Scan Configuration")
        control_layout = QVBoxLayout(control_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Function:"))
        self.addr_function_combo = QComboBox()
        self.addr_function_combo.setStyleSheet(self.parent_window._get_input_style())
        self.addr_function_combo.addItems(FUNCTION_TYPES)
        self.addr_function_combo.setCurrentText("Holding Registers")
        row1.addWidget(self.addr_function_combo)
        apply_dropdown_delegate(self.addr_function_combo, getattr(self.parent_window, "_theme_mode", "light"))

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
        control_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Probe timeout (ms):"))
        self.addr_timeout_input = QSpinBox()
        self.addr_timeout_input.setStyleSheet(self.parent_window._get_input_style())
        self.addr_timeout_input.setRange(50, 5000)
        self.addr_timeout_input.setValue(300)
        row2.addWidget(self.addr_timeout_input)

        row2.addWidget(QLabel("Text size (px):"))
        self.grid_font_size_input = QSpinBox()
        self.grid_font_size_input.setStyleSheet(self.parent_window._get_input_style())
        self.grid_font_size_input.setRange(8, 32)
        self.grid_font_size_input.setValue(self._cell_font_px)
        self.grid_font_size_input.setToolTip("Grid text size -- cell size grows to match, for readability")
        self.grid_font_size_input.valueChanged.connect(self._on_grid_font_size_changed)
        row2.addWidget(self.grid_font_size_input)

        self.colorblind_checkbox = QCheckBox("Colorblind-friendly colors")
        self.colorblind_checkbox.setToolTip(
            "Blue/orange instead of green/red, distinguishable under color vision deficiency"
        )
        self.colorblind_checkbox.toggled.connect(self._on_colorblind_toggled)
        row2.addWidget(self.colorblind_checkbox)
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

        self.clear_results_btn = QPushButton("Clear Results")
        self.clear_results_btn.setStyleSheet(self.parent_window._get_button_style())
        self.clear_results_btn.setToolTip("Clear the scanner output log and any found ranges.")
        self.clear_results_btn.clicked.connect(self._clear_results)
        row2.addWidget(self.clear_results_btn)

        self.create_tags_btn = QPushButton("Create Tags...")
        self.create_tags_btn.setStyleSheet(self.parent_window._get_button_style())
        self.create_tags_btn.setEnabled(False)
        self.create_tags_btn.setToolTip(
            "Create a new Tags-tab row for each responding address found by the scan"
        )
        self.create_tags_btn.clicked.connect(self._create_tags_from_scan)
        row2.addWidget(self.create_tags_btn)
        control_layout.addLayout(row2)
        layout.addWidget(control_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Result grid: one cell per scanned address, colored once the scan resolves it --
        # light green responding, light red not -- so the whole range's shape is visible
        # at a glance instead of read line by line out of a log.
        self.result_grid = QTableWidget()
        self.result_grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_grid.setSelectionMode(QAbstractItemView.NoSelection)
        self.result_grid.horizontalHeader().setVisible(False)
        self.result_grid.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_grid.verticalHeader().setVisible(False)
        self.result_grid.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                gridline-color: {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: {self._cell_font_px}px;
            }}
        """)
        layout.addWidget(self.result_grid, 1)

        # Page strip: one tab per "sheet" of addresses, Excel-style -- as many as fit the
        # grid's current on-screen size, labeled with that page's own address range.
        self.page_tabbar = QTabBar()
        self.page_tabbar.setExpanding(False)
        self.page_tabbar.currentChanged.connect(self._on_page_tab_changed)
        layout.addWidget(self.page_tabbar)

        self._grid_items = {}  # protocol address -> QTableWidgetItem, for the page on screen
        self._address_status = {}  # protocol address -> "ok"/"bad", for the whole scanned range
        self._pages = []  # [(page_start, page_end), ...] covering the whole scanned range
        self._current_page = 0

    def _cell_width(self):
        return max(40, self._cell_font_px * _GRID_CELL_WIDTH_PER_PX)

    def _row_height(self):
        return self._cell_font_px + _GRID_ROW_HEIGHT_PADDING

    def _status_colors(self, status):
        """(bg, fg, tooltip word) for a cell -- the colorblind-friendly palette swaps in
        when that checkbox is on, same statuses either way."""
        palette = _PALETTE_COLORBLIND if self._colorblind else _PALETTE_STANDARD
        c = self.parent_window._colors()
        return palette.get(status, (QColor(c["surface"]), QColor(c["text"]), "not yet resolved"))

    def _on_grid_font_size_changed(self, value):
        self._cell_font_px = value
        c = self.parent_window._colors()
        self.result_grid.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                gridline-color: {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: {value}px;
            }}
        """)
        self._repaginate()

    def _on_colorblind_toggled(self, checked):
        self._colorblind = checked
        if self._pages:
            self._show_page(self._current_page)  # recolor what's on screen, same layout

    def _repaginate(self):
        """Re-split the current scan's range into pages sized for the (changed) text
        size, without losing already-resolved results or re-running the scan."""
        if self._scan_range is not None:
            self._prepare_scan_pages(*self._scan_range, reset=False)

    def _prepare_scan_pages(self, start, end, reset=True):
        """Split [start, end] into however many addresses fit one page at the grid's
        current on-screen size and text size, Excel-sheet style. `reset` clears earlier
        results for a genuinely new scan; a text-size change instead repaginates the same
        results (reset=False), trying to keep showing the same address range."""
        self._scan_range = (start, end)
        viewport = self.result_grid.viewport()
        cols = max(_GRID_MIN_COLUMNS, viewport.width() // self._cell_width())
        rows = max(_GRID_MIN_ROWS, viewport.height() // self._row_height())
        per_page = cols * rows

        keep_address = None
        if not reset and self._pages and 0 <= self._current_page < len(self._pages):
            keep_address = self._pages[self._current_page][0]
        else:
            self._address_status = {}

        self._pages = []
        page_start = start
        while page_start <= end:
            page_end = min(end, page_start + per_page - 1)
            self._pages.append((page_start, page_end))
            page_start = page_end + 1
        self._page_columns = cols

        self.page_tabbar.blockSignals(True)
        while self.page_tabbar.count():
            self.page_tabbar.removeTab(0)
        for page_start, page_end in self._pages:
            label = f"{page_start}" if page_start == page_end else f"{page_start}-{page_end}"
            self.page_tabbar.addTab(label)
        self.page_tabbar.blockSignals(False)

        target_index = 0
        if keep_address is not None:
            for i, (page_start, page_end) in enumerate(self._pages):
                if page_start <= keep_address <= page_end:
                    target_index = i
                    break
        self._current_page = target_index
        self.page_tabbar.setCurrentIndex(target_index)
        self._show_page(target_index)

    def _on_page_tab_changed(self, index):
        if index >= 0:
            self._show_page(index)

    def _show_page(self, index):
        """(Re)populate the grid with one page's addresses, colored from whatever's
        already resolved in _address_status -- a page keeps showing earlier results
        correctly when the user flips back to it mid- or post-scan."""
        if not (0 <= index < len(self._pages)):
            return
        self._current_page = index
        page_start, page_end = self._pages[index]
        cols = getattr(self, "_page_columns", _GRID_MIN_COLUMNS)
        total = page_end - page_start + 1
        cols = min(cols, total)
        rows = math.ceil(total / cols)

        table = self.result_grid
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(0)  # drop stale items from whichever page was shown before
            table.setColumnCount(cols)
            table.setRowCount(rows)
            self._grid_items = {}
            address = page_start
            row_height = self._row_height()
            for row in range(rows):
                for col in range(cols):
                    if address > page_end:
                        break
                    bg, fg, tip = self._status_colors(self._address_status.get(address))
                    item = QTableWidgetItem(str(address))
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setBackground(bg)
                    item.setForeground(fg)
                    item.setToolTip(f"Protocol address {address} -- {tip}")
                    table.setItem(row, col, item)
                    self._grid_items[address] = item
                    address += 1
            for row in range(rows):
                table.setRowHeight(row, row_height)
        finally:
            table.setUpdatesEnabled(True)

    def _color_grid_range(self, start, count, responding):
        status = "ok" if responding else "bad"
        bg, fg, label = self._status_colors(status)
        for address in range(start, start + count):
            self._address_status[address] = status
            item = self._grid_items.get(address)
            if item is None:
                continue  # resolved address is on a page that isn't the one on screen
            item.setBackground(bg)
            item.setForeground(fg)
            item.setToolTip(f"Protocol address {address} -- {label}")

    def _log(self, message):
        """Scan status/errors go to the app's own System Logs (Diagnostics tab) -- the
        same already-existing channel connect/disconnect/device events use -- rather than
        a scanner-local text box."""
        if self.parent_window is not None and hasattr(self.parent_window, "_log"):
            self.parent_window._log(message)

    def _clear_results(self):
        """Clear the result grid, its page tabs, and any ranges the last scan found."""
        self._found_ranges = []
        self.result_grid.setRowCount(0)
        self.result_grid.setColumnCount(0)
        self._grid_items = {}
        self._address_status = {}
        self._pages = []
        self._scan_range = None
        self.page_tabbar.blockSignals(True)
        while self.page_tabbar.count():
            self.page_tabbar.removeTab(0)
        self.page_tabbar.blockSignals(False)
        self.create_tags_btn.setEnabled(False)

    def _modbus(self):
        """The device picked in this tab's Device selector (None while it's offline)."""
        return self.device_selector.modbus()

    def refresh_connection_state(self):
        modbus = self._modbus()
        connected = bool(modbus and modbus.is_connected())
        in_progress = self._scan_in_progress()
        self.addr_start_btn.setEnabled(connected and not in_progress)
        self.device_selector.combo.setEnabled(not in_progress)
        name = self.device_selector.device() or "the device"
        self.status_label.setText(
            f"Target: {modbus.target_description()} (Unit {modbus.unit_id})"
            if connected else
            f"{name} isn't connected -- connect it first (Overview tab, or Connect All)."
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
            self._log("Stopped Tags monitoring for the scan (restart it afterwards).")
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
            self._log("Stopped Address Table live monitoring for the scan (restart it afterwards).")
        trend_widget = getattr(self.parent_window, "trend_widget", None)
        self._trend_was_running = bool(trend_widget and trend_widget.poll_timer.isActive())
        if self._trend_was_running:
            trend_widget.poll_timer.stop()
            self._log("Paused Trend polling for the scan.")
        watchdog = getattr(self.parent_window, "_reconnect_watchdog_timer", None)
        self._watchdog_was_active = bool(watchdog and watchdog.isActive())
        if watchdog is not None:
            watchdog.stop()

    def _start_address_scan(self):
        modbus = self._modbus()
        if not (modbus and modbus.is_connected()):
            self.refresh_connection_state()
            return
        if self._scan_in_progress():
            self._log("A scan is already running -- wait for it to finish first.")
            return
        script_widget = getattr(self.parent_window, "script_widget", None)
        if script_widget is not None and getattr(script_widget, "running", False):
            # Unlike Tags/Address Table monitoring or Trend, a Script run is a
            # user-directed sequence, not a background poll -- silently pausing its
            # step_timer would leave no clean, timing-safe way to resume mid-WAIT, so
            # this refuses the scan instead of pausing the script out from under it.
            self._log("A script is currently running -- stop it before starting a scan.")
            return

        start = self.addr_start_input.value()
        end = self.addr_end_input.value()
        if start > end:
            self._log("Start address must not be greater than End address.")
            return

        self._pause_shared_connection_monitoring()
        self._found_ranges = []
        self._prepare_scan_pages(start, end)
        self._log(
            f"Scanning {self.addr_function_combo.currentText()} {start}-{end}..."
        )
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.addr_start_btn.setEnabled(False)
        self.addr_stop_btn.setEnabled(True)
        self.create_tags_btn.setEnabled(False)

        self._scanned_device = self.device_selector.device()
        self._scanned_function = self.addr_function_combo.currentText()
        self.device_selector.combo.setEnabled(False)
        self.address_worker = AddressScanWorker(
            modbus, self.addr_function_combo.currentText(), start, end,
            self.addr_timeout_input.value() / 1000.0,
            reserve_range=getattr(self.parent_window, "_reserve_range", None),
            release_range=getattr(self.parent_window, "_release_range", None),
        )
        self.address_worker.range_found.connect(self._on_address_range_found)
        self.address_worker.range_not_responding.connect(self._on_address_range_not_responding)
        self.address_worker.progress.connect(self.progress_bar.setValue)
        self.address_worker.output.connect(self._log)
        self.address_worker.scan_complete.connect(self._on_address_scan_complete)
        self.address_worker.start()

    def _stop_address_scan(self):
        if self.address_worker and self.address_worker.isRunning():
            self.address_worker.stop()

    def _on_address_range_found(self, start, count):
        self._found_ranges.append((start, count))
        self._color_grid_range(start, count, responding=True)

    def _on_address_range_not_responding(self, address):
        self._color_grid_range(address, 1, responding=False)

    def _on_address_scan_complete(self, responding_count, probes_issued):
        merged = _merge_ranges(self._found_ranges)
        if merged:
            summary = ", ".join(f"{s}" if s == e else f"{s}-{e}" for s, e in merged)
            self._log(f"Summary: {responding_count} responding address(es): {summary}")
        else:
            self._log("Summary: no responding addresses found in range.")
        self._log(f"({probes_issued} request(s) issued)")
        self.progress_bar.setVisible(False)
        self.addr_stop_btn.setEnabled(False)
        self.create_tags_btn.setEnabled(bool(merged))
        self.refresh_connection_state()

        # Resume the reconnect watchdog we paused before the scan, if the connection it
        # was watching is still the live one.
        if getattr(self, "_watchdog_was_active", False):
            self._watchdog_was_active = False
            watchdog = getattr(self.parent_window, "_reconnect_watchdog_timer", None)
            if watchdog is not None and self.parent_window._any_device_connected():
                watchdog.start(self.parent_window.WATCHDOG_HEALTHY_INTERVAL_MS)

        # Resume Trend polling we paused before the scan, same live-connection guard as
        # the watchdog above -- if the connection dropped during the scan there's nothing
        # to resume polling against.
        if getattr(self, "_trend_was_running", False):
            self._trend_was_running = False
            trend_widget = getattr(self.parent_window, "trend_widget", None)
            if trend_widget is not None and self.parent_window._any_device_connected():
                trend_widget.poll_timer.start(trend_widget.interval_input.value())
                self._log("Resumed Trend polling.")

    def _create_tags_from_scan(self):
        """"Create Tags..." -- lets the user pick which found ranges to import, then adds
        one new Tags-tab row per address via _add_monitoring_tag (never write_bounds/wire
        access, this is a purely local table edit). An address that already has a tag of
        the same type is skipped rather than duplicated or silently moved -- _add_
        monitoring_tag's own duplicate-address nudging would otherwise land a tag with a
        scan-derived name at the wrong address."""
        merged = _merge_ranges(self._found_ranges)
        if not merged:
            return

        function_name = getattr(self, "_scanned_function", None) or self.addr_function_combo.currentText()
        dialog = CreateTagsFromScanDialog(function_name, merged, self)
        if dialog.exec() != QDialog.Accepted:
            return
        addresses = dialog.selected_addresses()
        if not addresses:
            return

        tag_type = _SPACE_LABELS[function_name]
        one_based = getattr(self.parent_window, "tag_address_one_based", True)

        device = getattr(self, "_scanned_device", None) or self.device_selector.device()
        existing_offsets = set()
        for tag in self.parent_window._get_monitoring_tags():
            if tag["type"] != tag_type or (device and tag.get("device", "") != device):
                continue
            try:
                existing_offsets.add(self.parent_window._tag_user_address_to_offset(tag))
            except ValueError:
                continue

        created = 0
        skipped = 0
        for protocol_offset in addresses:
            if protocol_offset in existing_offsets:
                skipped += 1
                continue
            user_address = protocol_offset + (1 if one_based else 0)
            name = _default_scanned_tag_name(function_name, protocol_offset)
            self.parent_window._add_monitoring_tag(tag_name=name, tag_type=tag_type, address=user_address, count=1,
                                                   device=device)
            existing_offsets.add(protocol_offset)
            created += 1

        if created and getattr(self.parent_window, "tag_group_names", None):
            self.parent_window._rebuild_tag_table_grouped()

        message = f"Created {created} tag(s) from scan results"
        if skipped:
            message += f", skipped {skipped} address(es) that already had a tag"
        self._log(message + ".")

        if created:
            tab_widget = getattr(self.parent_window, "tab_widget", None)
            if tab_widget is not None:
                for i in range(tab_widget.count()):
                    if tab_widget.tabText(i) == "Tags":
                        tab_widget.setCurrentIndex(i)
                        break

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
