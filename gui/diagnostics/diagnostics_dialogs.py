from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QComboBox,
)
from PySide6.QtGui import QColor

from log_format import ERROR_COLOR, CONNECT_COLOR

MAX_RAW_DATA_ROWS = 1000  # oldest rows are dropped past this so the table can't grow unbounded

RAW_DATA_COLUMNS = ["Time", "Operation", "Value", "Raw (Hex)", "TX Bytes", "RX Bytes", "Status", "Latency (ms)"]
STATUS_COLUMN = 6


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

    def setup_diagnostics_widgets(self):
        """Initialize diagnostics widgets early to ensure they exist when needed."""
        # Initialize diagnostics log output widget
        if not hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output = QTextEdit()
            self.parent.diagnostics_log_output.setReadOnly(True)
            self.parent.diagnostics_log_output.setStyleSheet("""
                QTextEdit {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 10px;
                }
            """)

        # Initialize the Raw Data transaction table
        if not hasattr(self.parent, 'raw_data_table'):
            table = QTableWidget()
            table.setColumnCount(len(RAW_DATA_COLUMNS))
            table.setHorizontalHeaderLabels(RAW_DATA_COLUMNS)
            # Interactive (not Stretch) since TX/RX Bytes need room to vary with frame size --
            # forcing every column to share the width equally would crush the hex dumps.
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            column_widths = [70, 170, 130, 130, 190, 190, 70, 90]
            for col, width in enumerate(column_widths):
                table.setColumnWidth(col, width)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setAlternatingRowColors(True)
            table.setStyleSheet("""
                QTableWidget {
                    background-color: #FFFFFF;
                    color: #000000;
                    gridline-color: #D0D0D0;
                    border: 1px solid #CCCCCC;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 11px;
                }
                QHeaderView::section {
                    background-color: #E9E9E9;
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    padding: 4px;
                    font-weight: bold;
                }
            """)
            self.parent.raw_data_table = table

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
                self.parent.diagnostics_log_output.setStyleSheet("""
                    QTextEdit {
                        background-color: #FFFFFF;
                        color: #000000;
                        border: 1px solid #CCCCCC;
                        font-family: 'Consolas', 'Monaco', monospace;
                        font-size: 10px;
                    }
                """)
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
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")
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
            # Search Operation (tag name/address) and Value, since either is a reasonable
            # thing to search for -- "did this tag show up" or "did this value show up".
            haystack = (table.item(row, 1).text() + " " + table.item(row, 2).text()).lower()
            if self.filter_text not in haystack:
                return False
        return True

    def _apply_raw_data_filter(self):
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return
        for row in range(table.rowCount()):
            table.setRowHidden(row, not self._row_matches_filter(table, row))

    def add_raw_data_row(self, timestamp, title, data, elapsed_ms, error_text, tx_bytes=None, rx_bytes=None):
        """Append one transaction row to the Raw Data table."""
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return

        success = data is not None
        value_text = _format_raw_value(data) if success else (error_text or "ERROR")
        hex_text = _format_raw_hex(data) if success else ""
        tx_text = _format_wire_bytes(tx_bytes)
        rx_text = _format_wire_bytes(rx_bytes)
        status_text = "Success" if success else "Failed"
        latency_text = f"{elapsed_ms:.1f}" if elapsed_ms is not None else ""
        status_color = QColor(CONNECT_COLOR) if success else QColor(ERROR_COLOR)

        scrollbar = table.verticalScrollBar()
        # Only follow new rows if already scrolled to the bottom -- otherwise a scroll-up
        # to inspect an earlier transaction gets yanked back down on the next poll tick.
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2

        row = table.rowCount()
        table.insertRow(row)
        columns = (timestamp, title, value_text, hex_text, tx_text, rx_text, status_text, latency_text)
        for col, text in enumerate(columns):
            item = QTableWidgetItem(text)
            if col == STATUS_COLUMN:
                item.setForeground(status_color)
            table.setItem(row, col, item)

        table.setRowHidden(row, not self._row_matches_filter(table, row))

        overflow = table.rowCount() - MAX_RAW_DATA_ROWS
        if overflow > 0:
            table.removeRow(0)  # oldest row falls off the front, not the one just added

        if was_at_bottom:
            table.scrollToBottom()

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
        if hasattr(self.parent, 'raw_data_table'):
            self.parent.raw_data_table.setRowCount(0)

    def clear_all_diagnostics_logs(self):
        """Clear all diagnostics data."""
        self.clear_diagnostics_log()
        self.clear_diagnostics_raw_data()
