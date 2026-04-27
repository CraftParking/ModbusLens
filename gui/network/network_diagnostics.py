import socket
import time
from PySide6.QtCore import QThread, Signal


class NetworkDiagnosticsWorker(QThread):
    output = Signal(str)
    done = Signal(bool)

    def __init__(self, host, port, unit_id):
        super().__init__()
        self.host = host
        self.port = port
        self.unit_id = unit_id

    def run(self):
        """Run network diagnostics tests."""
        ok = True
        try:
            # DNS resolution
            self.output.emit(f"Resolving {self.host}...")
            try:
                ip = socket.gethostbyname(self.host)
                self.output.emit(f"DNS OK: {self.host} -> {ip}")
            except socket.gaierror as e:
                self.output.emit(f"DNS FAILED: {e}")
                ok = False
                self.done.emit(ok)
                return

            # TCP connection test
            self.output.emit(f"Testing TCP connection to {ip}:{self.port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                start = time.time()
                sock.connect((ip, self.port))
                rtt = (time.time() - start) * 1000
                self.output.emit(f"TCP OK: Connected in {rtt:.2f}ms")
                sock.close()
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                self.output.emit(f"TCP FAILED: {e}")
                ok = False
                self.done.emit(ok)
                return

            # Optional Modbus test (if pymodbus is available)
            try:
                from core.modbus_client import ModbusClient
                self.output.emit("Testing Modbus communication...")
                modbus = ModbusClient(ip, self.port, self.unit_id, timeout=3)
                if modbus.connect():
                    self.output.emit("Modbus OK: Connected successfully")
                    # Try a simple read
                    try:
                        result = modbus.read_holding_registers(0, 1)
                        if result is not None:
                            self.output.emit("Modbus READ OK: Test register read successful")
                        else:
                            self.output.emit("Modbus READ FAILED: No data received")
                    except Exception as e:
                        self.output.emit(f"Modbus READ FAILED: {e}")
                    modbus.disconnect()
                else:
                    self.output.emit("Modbus FAILED: Connection failed")
                    ok = False
            except ImportError:
                self.output.emit("Modbus test skipped: pymodbus not available")
            except Exception as e:
                self.output.emit(f"Modbus FAILED: {e}")
                ok = False

        except Exception as e:
            self.output.emit(f"Unexpected error: {e}")
            ok = False

        self.done.emit(ok)


class NetworkDiagnosticsDialog:
    """Network diagnostics dialog functionality."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.dialog = None
        self.worker = None
        self.output_text = None

    def show_diagnostics(self, host, port, unit_id):
        """Show network diagnostics dialog."""
        if self.dialog is None:
            self.dialog = QDialog(self.parent)
            self.dialog.setWindowTitle("Network Diagnostics")
            self.dialog.setGeometry(300, 300, 600, 500)

            layout = QVBoxLayout(self.dialog)

            # Output text
            self.output_text = QTextEdit()
            self.output_text.setReadOnly(True)
            self.output_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f8f9fa;
                    color: #333333;
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    padding: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                }
            """)
            layout.addWidget(self.output_text)

            # Buttons
            button_layout = QHBoxLayout()
            self.test_btn = QPushButton("Run Tests")
            self.test_btn.setStyleSheet(self.parent._get_button_style())
            self.test_btn.clicked.connect(lambda: self.run_tests(host, port, unit_id))
            button_layout.addWidget(self.test_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def run_tests(self, host, port, unit_id):
        """Run network diagnostics tests."""
        if self.worker and self.worker.isRunning():
            return

        self.output_text.clear()
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")

        self.worker = NetworkDiagnosticsWorker(host, port, unit_id)
        self.worker.output.connect(self.output_text.append)
        self.worker.done.connect(self.on_tests_done)
        self.worker.start()

    def on_tests_done(self, ok):
        """Handle test completion."""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Run Tests")
        if ok:
            self.output_text.append("\nAll tests completed successfully!")
        else:
            self.output_text.append("\nSome tests failed. Check the output above.")
