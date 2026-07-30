from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QCheckBox, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtGui import QColor

from log_format import ERROR_COLOR, CONNECT_COLOR

MAX_RAW_DATA_ROWS = 1000  # oldest rows are dropped past this so the table can't grow unbounded

RAW_DATA_COLUMNS = [
    "Time", "Operation", "Value", "Raw (Hex)", "TX Bytes", "RX Bytes", "Status", "Latency (ms)",
    "Function", "Unit ID", "Details",
]
STATUS_COLUMN = 6
# These three are only useful for protocol-level troubleshooting, so they stay hidden until
# the Advanced Diagnostics checkbox is on -- toggling it now visibly reveals real columns
# instead of only changing a hover tooltip.
ADVANCED_COLUMNS = (8, 9, 10)


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


def _format_function(function_code, function_name):
    if function_code is None:
        return ""
    if function_name:
        return f"0x{function_code:02X} {function_name}"
    return f"0x{function_code:02X}"


def _format_details(data, exception_desc):
    """A short, structural note: bit/register count on success, the classified exception
    reason on failure (when the specific error text was recognized)."""
    if data is None:
        return exception_desc or "-"
    values = data if isinstance(data, list) else [data]
    if all(isinstance(v, bool) for v in values):
        return f"{len(values)} bit(s)"
    return f"{len(values)} register(s)"


class DiagnosticsDialogs:
    """Handles diagnostics dialogs/tabs and their management."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.logs_dialog = None
        self.advanced_toggle = None

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
            column_widths = [70, 170, 130, 130, 190, 190, 70, 90, 170, 60, 160]
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
            for col in ADVANCED_COLUMNS:
                table.setColumnHidden(col, True)
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

        # Advanced diagnostics toggle
        self.advanced_toggle = QCheckBox("Advanced Diagnostics")
        self.advanced_toggle.setStyleSheet("""
            QCheckBox {
                color: #333333;
                font-size: 12px;
                padding: 5px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #f0f0f0;
                border: 2px solid #cccccc;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                border: 2px solid #4CAF50;
                border-radius: 4px;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTQiIGhlaWdodD0iMTQiIHZpZXdCb3g9IjAgMCAxNCAxNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEyIDVMMTAuNTkgNi40MUw3LjUgMy4zMUw2LjQxIDYuNDFMMyA1TDEuNTkgNi40MUwzLjQxIDguNTlMNi40MSAxMS41OUw3LjUgMTAuNjlMMTAuNTkgOC41OUwxMiAxMFYxMkgxMFY5LjQxTDguNTkgNy41TDUuNDEgMTAuNjlMNCAxMkgyVjEwTDNlLjQxIDguNTlMMS41OSA2LjQxTDNUNi40MUw1LjQxIDMuMzFMNy41IDUuNDFMMTAuNTkgMi41TDEyIDVWNy41OUwxMC41OSA5LjQxTDcuNSA2LjQxTDYuNDEgOS40MUwzLjUgOEwxLjU5IDkuNDFMMy40MSAxMS41OUw2LjQxIDE0LjU5TDcuNSAxMy42OUwxMC41OSAxMS41OUwxMiAxM1YxNEgxMFYxMi41OUw4LjU5IDEwLjVMNS40MSAxMy42OUw0IDE1SDJWMTNMMi41OSAxMS41OUwxLjU5IDkuNDFMMy41IDhMNS40MSA5LjQxTDcuNSA2LjQxTDEwLjU5IDMuNDFMMTIgNloiIGZpbGw9IndoaXRlIi8+Cjwvc3ZnPgo=);
            }
        """)
        self.advanced_toggle.setChecked(advanced_diagnostics.advanced_diagnostics)
        self.advanced_toggle.toggled.connect(lambda checked: self._on_advanced_toggled(checked, advanced_diagnostics))
        header_layout.addWidget(self.advanced_toggle)

        layout.addLayout(header_layout)

        # Use the pre-initialized raw data table
        if not hasattr(self.parent, 'raw_data_table'):
            self.setup_diagnostics_widgets()
        if self.parent.raw_data_table.parent():
            self.parent.raw_data_table.setParent(None)
        layout.addWidget(self.parent.raw_data_table)
        # Sync column visibility to whatever the toggle's current state already is.
        self._on_advanced_toggled(advanced_diagnostics.advanced_diagnostics, advanced_diagnostics)

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

    def _on_advanced_toggled(self, checked, advanced_diagnostics):
        advanced_diagnostics.toggle_advanced_diagnostics(checked)
        table = getattr(self.parent, 'raw_data_table', None)
        if table is None:
            return
        for col in ADVANCED_COLUMNS:
            table.setColumnHidden(col, not checked)

    def add_raw_data_row(self, timestamp, title, data, elapsed_ms, error_text,
                          function_code=None, function_name=None, unit_id=None, exception_desc=None,
                          tx_bytes=None, rx_bytes=None):
        """Append one transaction row to the Raw Data table. The Function/Unit ID/Details
        columns are always populated (so toggling Advanced Diagnostics on shows history too),
        just hidden until that checkbox is on."""
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
        function_text = _format_function(function_code, function_name)
        unit_text = str(unit_id) if unit_id is not None else ""
        details_text = _format_details(data, exception_desc)

        row = table.rowCount()
        table.insertRow(row)
        columns = (timestamp, title, value_text, hex_text, tx_text, rx_text, status_text, latency_text,
                   function_text, unit_text, details_text)
        for col, text in enumerate(columns):
            item = QTableWidgetItem(text)
            if col == STATUS_COLUMN:
                item.setForeground(status_color)
            table.setItem(row, col, item)

        overflow = table.rowCount() - MAX_RAW_DATA_ROWS
        if overflow > 0:
            table.removeRow(0)  # oldest row falls off the front, not the one just added

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
