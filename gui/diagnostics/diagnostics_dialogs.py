import csv
import time

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox, QMenu, QApplication,
    QFileDialog, QMessageBox,
)
from PySide6.QtGui import QColor, QShortcut, QKeySequence
from PySide6.QtCore import Qt

from theme import apply_dropdown_delegate
from zoom import install_ctrl_wheel_zoom
from diagnostics.frame_viewer import FrameViewerDialog

MAX_RAW_DATA_ROWS = 1000  # oldest rows are dropped past this so the table can't grow unbounded

DEFAULT_LOG_FONT_PX = 10
DEFAULT_RAW_TABLE_FONT_PX = 11

RAW_DATA_COLUMNS = [
    "Time", "Operation", "Value", "Raw (Hex)", "TX Bytes", "RX Bytes", "Status", "Exception", "Latency (ms)",
]
STATUS_COLUMN = 6
EXCEPTION_COLUMN = 7


def _format_wire_bytes(data):
    """The literal bytes that went over the wire, captured via pymodbus's trace_packet hook --
    the actual ground truth, one level below even the raw register/coil values above."""
    if not data:
        return ""
    return data.hex(" ").upper()


def _format_raw_value(data):
    """Plain decimal rendering of a raw register/coil read or write result."""
    if data is None:
        return ""
    if isinstance(data, list):
        return ", ".join(str(v) for v in data)
    return str(data)


def _format_raw_hex(data):
    """Hex rendering of the same data -- bits as 1/0, registers as 0xNNNN."""
    if data is None:
        return ""
    values = data if isinstance(data, list) else [data]
    if all(isinstance(v, bool) for v in values):
        return ", ".join("1" if v else "0" for v in values)
    try:
        return ", ".join(f"0x{int(v) & 0xFFFF:04X}" for v in values)
    except (TypeError, ValueError):
        return ", ".join(str(v) for v in values)


class DiagnosticsDialogs:
    """Handles diagnostics dialogs/tabs and their management."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.logs_dialog = None
        self.filter_text = ""
        self.filter_status = "All"
        self._frame_viewer = None
        self._last_raw_row = -1

    def _log_text_style(self, font_px=DEFAULT_LOG_FONT_PX):
        c = self.parent._colors()
        return f"""
            QTextEdit {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: {font_px}px;
            }}
        """

    def _raw_table_style(self, font_px=DEFAULT_RAW_TABLE_FONT_PX):
        c = self.parent._colors()
        return f"""
            QTableWidget {{
                background-color: {c["surface"]};
                color: {c["text"]};
                gridline-color: {c["pressed"]};
                border: 1px solid {c["border"]};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: {font_px}px;
            }}
            QHeaderView::section {{
                background-color: {c["header_bg"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                padding: 4px;
                font-weight: bold;
                font-size: {font_px}px;
            }}
        """

    def setup_diagnostics_widgets(self):
        """Initialize diagnostics widgets early to ensure they exist when needed."""
        # Initialize diagnostics log output widget
        if not hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output = QTextEdit()
            self.parent.diagnostics_log_output.setReadOnly(True)
            self.parent.diagnostics_log_output.setStyleSheet(self._log_text_style())
            install_ctrl_wheel_zoom(
                self.parent.diagnostics_log_output, DEFAULT_LOG_FONT_PX,
                lambda px: self.parent.diagnostics_log_output.setStyleSheet(self._log_text_style(px)),
            )

        # Initialize the Raw Data transaction table
        if not hasattr(self.parent, 'raw_data_table'):
            table = QTableWidget()
            table.setColumnCount(len(RAW_DATA_COLUMNS))
            table.setHorizontalHeaderLabels(RAW_DATA_COLUMNS)
            # Interactive (not Stretch) since TX/RX Bytes need room to vary with frame size --
            # forcing every column to share the width equally would crush the hex dumps.
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            column_widths = [70, 170, 130, 130, 190, 190, 70, 220, 90]
            for col, width in enumerate(column_widths):
                table.setColumnWidth(col, width)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setAlternatingRowColors(True)
            table.setStyleSheet(self._raw_table_style())
            table.setContextMenuPolicy(Qt.CustomContextMenu)
            table.customContextMenuRequested.connect(self._show_raw_data_context_menu)
            table.itemClicked.connect(self._on_raw_data_cell_clicked)
            # Ctrl+C copies the current selection as text, same as the context menu's
            # "Copy Row(s) as Text" -- WidgetWithChildrenShortcut since the table itself
            # (not a child editor) normally holds focus here, unlike the Tags table.
            self._raw_data_copy_shortcut = QShortcut(QKeySequence.Copy, table)
            self._raw_data_copy_shortcut.setContext(Qt.WidgetWithChildrenShortcut)
            self._raw_data_copy_shortcut.activated.connect(lambda: self._copy_selected_raw_data_rows(table))
            self.parent.raw_data_table = table

            def _restyle_raw_table(px, table=table):
                table.setStyleSheet(self._raw_table_style(px))
                table.resizeRowsToContents()

            install_ctrl_wheel_zoom(table, DEFAULT_RAW_TABLE_FONT_PX, _restyle_raw_table)

    def show_diagnostics_logs(self):
        """Show diagnostics dialog with system logs."""
        if not self.logs_dialog:
            self.logs_dialog = QDialog(self.parent)
            self.logs_dialog.setWindowTitle("Diagnostics - System Logs")
            self.logs_dialog.setGeometry(200, 200, 800, 600)

            layout = QVBoxLayout(self.logs_dialog)

            # Use the pre-initialized diagnostics log output widget
            if hasattr(self.parent, 'diagnostics_log_output'):
                # Remove from its current parent if it has one
                if self.parent.diagnostics_log_output.parent():
                    self.parent.diagnostics_log_output.setParent(None)
                layout.addWidget(self.parent.diagnostics_log_output)
            else:
                # Fallback: create new widget if initialization failed
                self.parent.diagnostics_log_output = QTextEdit()
                self.parent.diagnostics_log_output.setReadOnly(True)
                self.parent.diagnostics_log_output.setStyleSheet(self._log_text_style())
                layout.addWidget(self.parent.diagnostics_log_output)

            # Buttons
            button_layout = QHBoxLayout()
            clear_btn = QPushButton("Clear Log")
            clear_btn.setStyleSheet(self.parent._get_button_style())
            clear_btn.clicked.connect(self.clear_diagnostics_logs)
            button_layout.addWidget(clear_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.logs_dialog.hide)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

        self.logs_dialog.show()
        self.logs_dialog.raise_()
        self.logs_dialog.activateWindow()

    def build_raw_data_tab(self, advanced_diagnostics):
        """Build the Raw Data tab widget: one row per Modbus transaction, showing the
        untouched register/coil bytes behind every read/write (independent of how a Tag or
        Address Table row happens to decode them), whether it succeeded, and its latency."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header with advanced toggle
        header_layout = QHBoxLayout()

        title_label = QLabel("Raw Modbus Data")
        title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self.parent._colors()['heading']};")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Filter row: text search (matches tag name/address in Operation and Value) + status
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by tag name or address...")
        self.filter_input.setStyleSheet(self.parent._get_input_style())
        self.filter_input.setText(self.filter_text)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_input, 1)

        self.filter_status_combo = QComboBox()
        self.filter_status_combo.setStyleSheet(self.parent._get_input_style())
        self.filter_status_combo.addItems(["All", "Success", "Failed"])
        self.filter_status_combo.setCurrentText(self.filter_status)
        self.filter_status_combo.currentTextChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_status_combo)
        apply_dropdown_delegate(self.filter_status_combo, getattr(self.parent, "_theme_mode", "light"))
        layout.addLayout(filter_layout)

        # Use the pre-initialized raw data table
        if not hasattr(self.parent, 'raw_data_table'):
            self.setup_diagnostics_widgets()
        if self.parent.raw_data_table.parent():
            self.parent.raw_data_table.setParent(None)
        layout.addWidget(self.parent.raw_data_table)
        self._apply_raw_data_filter()

        # Buttons
        button_layout = QHBoxLayout()

        # Statistics button
        stats_btn = QPushButton("Show Statistics")
        stats_btn.setStyleSheet(self.parent._get_button_style())
        stats_btn.clicked.connect(
            lambda: advanced_diagnostics.show_statistics_dialog(getattr(self.parent, 'modbus', None), self.parent)
        )
        button_layout.addWidget(stats_btn)

        clear_btn = QPushButton("Clear Data")
        clear_btn.setStyleSheet(self.parent._get_button_style())
        clear_btn.clicked.connect(self.clear_diagnostics_raw_data)
        button_layout.addWidget(clear_btn)

        export_btn = QPushButton("Export CSV")
        export_btn.setStyleSheet(self.parent._get_button_style())
        export_btn.clicked.connect(self._export_raw_data_csv)
        button_layout.addWidget(export_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return tab

    def _on_filter_changed(self, _value=None):
        self.filter_text = self.filter_input.text().strip().lower()
        self.filter_status = self.filter_status_combo.currentText()
        self._apply_raw_data_filter()

    def _row_matches_filter(self, table, row):
        if self.filter_status != "All" and table.item(row, STATUS_COLUMN).text() != self.filter_status:
            return False
        if self.filter_text:
            # Search Operation (tag name/address), Value, and Exception -- "did this tag
            # show up", "did this value show up", or "did this exception show up" are all
            # reasonable things to filter for.
            haystack = " ".join((
                table.item(row, 1).text(), table.item(row, 2).text(), table.item(row, EXCEPTION_COLUMN).text(),
            )).lower()
            if self.filter_text not in haystack:
                return False
        return True

    def _apply_raw_data_filter(self):
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return
        for row in range(table.rowCount()):
            table.setRowHidden(row, not self._row_matches_filter(table, row))

    def add_raw_data_row(self, timestamp, title, data, elapsed_ms, error_text, tx_bytes=None, rx_bytes=None,
                          exception_text=""):
        """Append one transaction row to the Raw Data table. exception_text is the decoded
        Modbus exception description (e.g. "Illegal Data Address - ...") when the device
        itself replied with an exception response -- left blank for a plain communications
        failure (timeout, no response), so the Exception column distinguishes "the device
        refused this" from "nothing answered at all" at a glance, not just a shared red
        Failed status for both."""
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return

        success = data is not None
        value_text = _format_raw_value(data) if success else (error_text or "ERROR")
        hex_text = _format_raw_hex(data) if success else ""
        tx_text = _format_wire_bytes(tx_bytes)
        rx_text = _format_wire_bytes(rx_bytes)
        status_text = "Success" if success else "Failed"
        latency_text = f"{elapsed_ms:.2f}" if elapsed_ms is not None else ""
        c = self.parent._colors()
        status_color = QColor(c["log_connect"]) if success else QColor(c["log_error"])
        warning_color = QColor(c["log_warning"])

        scrollbar = table.verticalScrollBar()
        # Only follow new rows if already scrolled to the bottom -- otherwise a scroll-up
        # to inspect an earlier transaction gets yanked back down on the next poll tick.
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2

        row = table.rowCount()
        table.insertRow(row)
        columns = (
            timestamp, title, value_text, hex_text, tx_text, rx_text, status_text, exception_text, latency_text,
        )
        for col, text in enumerate(columns):
            item = QTableWidgetItem(text)
            if col == STATUS_COLUMN:
                item.setForeground(status_color)
            elif col == EXCEPTION_COLUMN and exception_text:
                item.setForeground(warning_color)
            table.setItem(row, col, item)

        table.setRowHidden(row, not self._row_matches_filter(table, row))

        overflow = table.rowCount() - MAX_RAW_DATA_ROWS
        if overflow > 0:
            table.removeRow(0)  # oldest row falls off the front, not the one just added

        if was_at_bottom:
            table.scrollToBottom()

    def _show_raw_data_context_menu(self, pos):
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return

        rows = sorted({index.row() for index in table.selectedIndexes()})
        clicked_row = table.rowAt(pos.y())
        if clicked_row >= 0 and clicked_row not in rows:
            # Right-clicking a row that isn't already selected should act on that row,
            # not whatever was selected before -- same convention as most desktop tables.
            table.selectRow(clicked_row)
            rows = [clicked_row]
        if not rows:
            return

        menu = QMenu(table)
        copy_text_action = menu.addAction("Copy Row(s) as Text")
        copy_bytes_action = menu.addAction("Copy Row(s) as Hex Bytes (TX/RX)")
        chosen = menu.exec(table.viewport().mapToGlobal(pos))
        if chosen == copy_text_action:
            self._copy_raw_data_rows(table, rows, as_bytes=False)
        elif chosen == copy_bytes_action:
            self._copy_raw_data_rows(table, rows, as_bytes=True)

    def _on_raw_data_cell_clicked(self, item):
        """When the user clicks any cell in the Raw Data table, show a floating popup
        that decodes the TX and RX Modbus frames for that transaction."""
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return

        row = item.row()
        # Reuse the same popup for the same row; open a new one for a different row.
        if self._frame_viewer is not None and self._last_raw_row == row:
            return

        self._close_frame_viewer()
        self._last_raw_row = row

        tx_text = table.item(row, 4).text() if row < table.columnCount() else ""
        rx_text = table.item(row, 5).text() if row < table.columnCount() else ""
        tx_bytes = self._parse_hex_bytes(tx_text) if tx_text else None
        rx_bytes = self._parse_hex_bytes(rx_text) if rx_text else None

        transport = "tcp"
        if hasattr(self.parent, 'modbus') and self.parent.modbus is not None:
            if self.parent.modbus.mode == "serial":
                transport = "ascii" if self.parent.modbus.serial_framer == "ascii" else "rtu"

        self._frame_viewer = FrameViewerDialog(
            self.parent, tx_bytes, rx_bytes, transport, row,
        )
        self._frame_viewer.closed.connect(self._close_frame_viewer)
        self._frame_viewer.show()

    @staticmethod
    def _parse_hex_bytes(text):
        """Convert a space-separated hex string like '01 03 00 0A 00 01 6C 0B' back
        to raw bytes, or return None if the input is blank or unparseable."""
        if not text:
            return None
        cleaned = text.strip().replace(" ", "").replace("-", "")
        if len(cleaned) < 2 or len(cleaned) % 2 != 0:
            return None
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            return None

    def _close_frame_viewer(self):
        """Close and clean up the currently-open frame viewer popup, if any."""
        if self._frame_viewer is not None:
            self._frame_viewer.close()
            self._frame_viewer = None
            self._last_raw_row = -1

    def _copy_selected_raw_data_rows(self, table):
        rows = sorted({index.row() for index in table.selectedIndexes()})
        if not rows:
            return
        self._copy_raw_data_rows(table, rows, as_bytes=False)

    @staticmethod
    def _copy_raw_data_rows(table, rows, as_bytes):
        """as_bytes=False copies every column, tab-separated -- a full record of the
        transaction, pasteable straight into a spreadsheet. as_bytes=True copies just the
        literal TX/RX wire bytes each row already carries (see _trace_packet in
        core/modbus_client.py) -- the actual frame bytes, for pasting into a hex viewer or
        a bug report, without the decoded columns in the way."""
        lines = []
        for row in rows:
            if as_bytes:
                tx = table.item(row, 4).text()
                rx = table.item(row, 5).text()
                lines.append(f"TX: {tx}\nRX: {rx}")
            else:
                lines.append("\t".join(table.item(row, col).text() for col in range(table.columnCount())))
        QApplication.clipboard().setText("\n".join(lines))

    def _export_raw_data_csv(self):
        """Export the currently visible Raw Data rows (respects the text/status filter) to
        CSV -- mirrors the Tags tab's existing Export CSV, which this table never had."""
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return
        rows = [row for row in range(table.rowCount()) if not table.isRowHidden(row)]
        if not rows:
            QMessageBox.warning(self.parent, "No Data", "No raw data rows to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self.parent, "Export Raw Data CSV", f"raw_data_{time.strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(RAW_DATA_COLUMNS)
                for row in rows:
                    writer.writerow([table.item(row, col).text() for col in range(table.columnCount())])
        except OSError as e:
            self.parent._log(f"Error exporting raw data CSV: {e}")
            QMessageBox.critical(self.parent, "Error", f"Failed to export raw data: {e}")
            return

        self.parent._log(f"Exported {len(rows)} raw data rows to {file_path}")
        QMessageBox.information(self.parent, "Export Complete", f"Successfully exported {len(rows)} rows to CSV file!")

    def clear_diagnostics_logs(self):
        """Clear all diagnostics logs."""
        if hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output.clear()
        self.parent._log("Diagnostics logs cleared")

    def clear_diagnostics_log(self):
        """Clear communication log."""
        if hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output.clear()

    def clear_diagnostics_raw_data(self):
        """Clear raw data."""
        self._close_frame_viewer()
        if hasattr(self.parent, 'raw_data_table'):
            self.parent.raw_data_table.setRowCount(0)

    def clear_all_diagnostics_logs(self):
        """Clear all diagnostics data."""
        self.clear_diagnostics_log()
        self.clear_diagnostics_raw_data()
