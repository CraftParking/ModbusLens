from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QCheckBox, QTableWidget, QHeaderView, QAbstractItemView
from PySide6.QtCore import Qt


class DiagnosticsDialogs:
    """Handles all diagnostics dialogs and their management."""
    
    def __init__(self, parent_window):
        self.parent = parent_window
        self.diagnostics_dialog = None
        self.logs_dialog = None
        self.raw_data_dialog = None
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
        
        # Initialize diagnostics data output widget
        if not hasattr(self.parent, 'diagnostics_data_output'):
            self.parent.diagnostics_data_output = QTextEdit()
            self.parent.diagnostics_data_output.setReadOnly(True)
            self.parent.diagnostics_data_output.setStyleSheet("""
                QTextEdit {
                    background-color: #FFFFFF;
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 10px;
                }
            """)

    def show_diagnostics_results(self):
        """Show diagnostics dialog with results data."""
        if not self.diagnostics_dialog:
            self.diagnostics_dialog = QDialog(self.parent)
            self.diagnostics_dialog.setWindowTitle("Diagnostics - Results")
            self.diagnostics_dialog.setGeometry(200, 200, 800, 600)
            
            layout = QVBoxLayout(self.diagnostics_dialog)
            
            # Create results table if it doesn't exist
            if not hasattr(self.parent, 'diagnostics_results_table'):
                self.parent.diagnostics_results_table = QTableWidget()
                self.parent.diagnostics_results_table.setColumnCount(8)
                self.parent.diagnostics_results_table.setHorizontalHeaderLabels([
                    "Tag Name", "Mode", "Type", "Address", "Read Value", "Write Value", "Comment", "Timestamp"
                ])
                self.parent.diagnostics_results_table.setAlternatingRowColors(True)
                self.parent.diagnostics_results_table.setSortingEnabled(False)
                self.parent.diagnostics_results_table.setSelectionBehavior(QTableWidget.SelectRows)
                self.parent.diagnostics_results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                self.parent.diagnostics_results_table.setStyleSheet("""
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
            
            layout.addWidget(self.parent.diagnostics_results_table)
            
            # Buttons
            button_layout = QHBoxLayout()
            clear_btn = QPushButton("Clear Results")
            clear_btn.setStyleSheet(self.parent._get_button_style())
            clear_btn.clicked.connect(self.clear_diagnostics_results)
            button_layout.addWidget(clear_btn)
            
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.diagnostics_dialog.hide)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
        
        self.diagnostics_dialog.show()
        self.diagnostics_dialog.raise_()
        self.diagnostics_dialog.activateWindow()

    def show_diagnostics_logs(self):
        """Show diagnostics dialog with communication logs."""
        if not self.logs_dialog:
            self.logs_dialog = QDialog(self.parent)
            self.logs_dialog.setWindowTitle("Diagnostics - Communication Log")
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

    def show_diagnostics_raw_data(self, advanced_diagnostics):
        """Show diagnostics dialog with raw data."""
        if not self.raw_data_dialog:
            self.raw_data_dialog = QDialog(self.parent)
            self.raw_data_dialog.setWindowTitle("Diagnostics - Raw Data")
            self.raw_data_dialog.setGeometry(200, 200, 800, 600)
            
            layout = QVBoxLayout(self.raw_data_dialog)
            
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
            self.advanced_toggle.toggled.connect(advanced_diagnostics.toggle_advanced_diagnostics)
            header_layout.addWidget(self.advanced_toggle)
            
            layout.addLayout(header_layout)
            
            # Use the pre-initialized diagnostics data output widget
            if hasattr(self.parent, 'diagnostics_data_output'):
                # Remove from its current parent if it has one
                if self.parent.diagnostics_data_output.parent():
                    self.parent.diagnostics_data_output.setParent(None)
                layout.addWidget(self.parent.diagnostics_data_output)
            else:
                # Fallback: create new widget if initialization failed
                self.parent.diagnostics_data_output = QTextEdit()
                self.parent.diagnostics_data_output.setReadOnly(True)
                self.parent.diagnostics_data_output.setStyleSheet("""
                    QTextEdit {
                        background-color: #FFFFFF;
                        color: #000000;
                        border: 1px solid #CCCCCC;
                        font-family: 'Consolas', 'Monaco', monospace;
                        font-size: 10px;
                    }
                """)
                layout.addWidget(self.parent.diagnostics_data_output)
            
            # Buttons
            button_layout = QHBoxLayout()
            
            # Statistics button
            stats_btn = QPushButton("Show Statistics")
            stats_btn.setStyleSheet(self.parent._get_button_style())
            stats_btn.clicked.connect(advanced_diagnostics.show_statistics_dialog)
            button_layout.addWidget(stats_btn)
            
            clear_btn = QPushButton("Clear Data")
            clear_btn.setStyleSheet(self.parent._get_button_style())
            clear_btn.clicked.connect(self.clear_diagnostics_raw_data)
            button_layout.addWidget(clear_btn)
            
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.raw_data_dialog.hide)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
        
        self.raw_data_dialog.show()
        self.raw_data_dialog.raise_()
        self.raw_data_dialog.activateWindow()

    def clear_diagnostics_logs(self):
        """Clear all diagnostics logs."""
        if hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output.clear()
        if hasattr(self.parent, 'log_output'):
            self.parent.log_output.clear()
        self.parent._log("Diagnostics logs cleared")

    def clear_diagnostics_log(self):
        """Clear communication log."""
        if hasattr(self.parent, 'diagnostics_log_output'):
            self.parent.diagnostics_log_output.clear()

    def clear_diagnostics_raw_data(self):
        """Clear raw data."""
        if hasattr(self.parent, 'diagnostics_data_output'):
            self.parent.diagnostics_data_output.clear()
        if hasattr(self.parent, 'data_output'):
            self.parent.data_output.clear()

    def clear_diagnostics_results(self):
        """Clear diagnostics results."""
        if hasattr(self.parent, 'diagnostics_results_table'):
            self.parent.diagnostics_results_table.setRowCount(0)
        self.parent._log("Diagnostics results cleared")

    def clear_all_diagnostics_logs(self):
        """Clear all diagnostics data."""
        self.clear_diagnostics_log()
        self.clear_diagnostics_raw_data()

    def update_advanced_toggle_state(self, checked):
        """Update the advanced toggle checkbox state."""
        if self.advanced_toggle:
            self.advanced_toggle.setChecked(checked)
