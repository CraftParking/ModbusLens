import sys
import logging
from typing import Optional
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile, QIODevice

from core.modbus_client import ModbusClient

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')


class ModbusGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        ui_file = Path(__file__).parent / "main_window.ui"
        ui_file = ui_file.resolve()

        loader = QUiLoader()
        ui_file_handle = QFile(str(ui_file))
        if not ui_file_handle.open(QIODevice.ReadOnly):
            raise RuntimeError(f"Cannot open UI file: {ui_file}")

        self.ui = loader.load(ui_file_handle, self)
        ui_file_handle.close()

        if self.ui is None:
            raise RuntimeError("Failed to load UI file")

        self.setCentralWidget(self.ui.centralwidget)
        self.setWindowTitle("ModbusLens")

        self.modbus = None

        self._connect_signals()

    def _connect_signals(self):
        self.ui.connect_btn.clicked.connect(self.toggle_connection)

        self.ui.read_coils_btn.clicked.connect(self.read_coils)
        self.ui.read_discrete_inputs_btn.clicked.connect(self.read_discrete_inputs)
        self.ui.read_holding_registers_btn.clicked.connect(self.read_holding_registers)
        self.ui.read_input_registers_btn.clicked.connect(self.read_input_registers)

        self.ui.write_coil_btn.clicked.connect(self.write_coil)
        self.ui.write_register_btn.clicked.connect(self.write_register)
        self.ui.write_coils_btn.clicked.connect(self.write_coils)
        self.ui.write_registers_btn.clicked.connect(self.write_registers)

    def toggle_connection(self):
        if self.modbus and self.modbus.is_connected():
            self.modbus.disconnect()
            self.ui.connect_btn.setText("Connect")
            self.ui.status_label.setText("Disconnected")
            self._log("Disconnected from Modbus server")
        else:
            try:
                ip = self.ui.ip_input.text().strip() or "127.0.0.1"
                port = int(self.ui.port_input.text().strip() or "502")
                unit_id = int(self.ui.unit_input.text().strip() or "1")

                self.modbus = ModbusClient(ip, port, unit_id)

                if self.modbus.connect():
                    self.ui.connect_btn.setText("Disconnect")
                    self.ui.status_label.setText(f"Connected to {ip}:{port}")
                    self._log(f"Connected to Modbus server at {ip}:{port}")
                else:
                    self._show_error("Connection failed. Check IP/Port and try again.")
                    self.modbus = None

            except ValueError as e:
                self._show_error(f"Invalid input: {e}")
            except Exception as e:
                self._show_error(f"Connection error: {e}")
                self.modbus = None

    def _get_address_count(self):
        try:
            address = int(self.ui.address_input.text().strip())
            count = int(self.ui.count_input.text().strip())
            return address, count
        except ValueError:
            self._show_error("Please enter valid address and count")
            return None, None

    def _get_single_value(self):
        try:
            return int(self.ui.value_input.text().strip())
        except ValueError:
            self._show_error("Please enter a valid value")
            return None

    def _get_multiple_values(self, as_bool=False):
        try:
            text = self.ui.values_input.text().strip()
            if not text:
                self._show_error("Please enter values")
                return None

            values = []
            for v in text.split(","):
                v = v.strip()
                if as_bool:
                    values.append(bool(int(v)))
                else:
                    values.append(int(v))
            return values
        except ValueError:
            self._show_error("Please enter valid comma-separated values")
            return None

    def read_coils(self):
        if not self._check_connection():
            return

        address, count = self._get_address_count()
        if address is None:
            return

        data = self.modbus.read_coils(address, count)
        if data is None:
            self._show_error("Failed to read coils")
        else:
            self._log(f"Coils at {address}: {data}")

    def read_discrete_inputs(self):
        if not self._check_connection():
            return

        address, count = self._get_address_count()
        if address is None:
            return

        data = self.modbus.read_discrete_inputs(address, count)
        if data is None:
            self._show_error("Failed to read discrete inputs")
        else:
            self._log(f"Discrete inputs at {address}: {data}")

    def read_holding_registers(self):
        if not self._check_connection():
            return

        address, count = self._get_address_count()
        if address is None:
            return

        data = self.modbus.read_registers(address, count)
        if data is None:
            self._show_error("Failed to read holding registers")
        else:
            self._log(f"Holding registers at {address}: {data}")

    def read_input_registers(self):
        if not self._check_connection():
            return

        address, count = self._get_address_count()
        if address is None:
            return

        data = self.modbus.read_input_registers(address, count)
        if data is None:
            self._show_error("Failed to read input registers")
        else:
            self._log(f"Input registers at {address}: {data}")

    def write_coil(self):
        if not self._check_connection():
            return

        address, _ = self._get_address_count()
        if address is None:
            return

        value = self._get_single_value()
        if value is None:
            return

        success = self.modbus.write_coil(address, bool(value))
        if success:
            self._log(f"Successfully wrote coil {address} = {bool(value)}")
        else:
            self._show_error("Failed to write coil")

    def write_register(self):
        if not self._check_connection():
            return

        address, _ = self._get_address_count()
        if address is None:
            return

        value = self._get_single_value()
        if value is None:
            return

        success = self.modbus.write_register(address, value)
        if success:
            self._log(f"Successfully wrote register {address} = {value}")
        else:
            self._show_error("Failed to write register")

    def write_coils(self):
        if not self._check_connection():
            return

        address, _ = self._get_address_count()
        if address is None:
            return

        values = self._get_multiple_values(as_bool=True)
        if values is None:
            return

        success = self.modbus.write_coils(address, values)
        if success:
            self._log(f"Successfully wrote coils starting at {address}: {values}")
        else:
            self._show_error("Failed to write coils")

    def write_registers(self):
        if not self._check_connection():
            return

        address, _ = self._get_address_count()
        if address is None:
            return

        values = self._get_multiple_values(as_bool=False)
        if values is None:
            return

        success = self.modbus.write_registers(address, values)
        if success:
            self._log(f"Successfully wrote registers starting at {address}: {values}")
        else:
            self._show_error("Failed to write registers")

    def _check_connection(self):
        if not self.modbus or not self.modbus.is_connected():
            self._show_error("Not connected to Modbus server")
            return False
        return True

    def _log(self, message):
        current_text = self.ui.output_text.toPlainText()
        if current_text:
            current_text += "\n"
        current_text += message
        self.ui.output_text.setPlainText(current_text)

        scrollbar = self.ui.output_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _show_error(self, message):
        QMessageBox.critical(self, "Error", message)
        self._log(f"ERROR: {message}")

    def closeEvent(self, event):
        if self.modbus:
            self.modbus.disconnect()
        event.accept()


def main():
    app = QApplication(sys.argv)

    app.setApplicationName("ModbusLens")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("ModbusLens")

    window = ModbusGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()