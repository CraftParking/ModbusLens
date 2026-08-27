"""
Phase 1, item 3: Auto-identify discovered Modbus devices.

When a NetworkScanner probe confirms a host is Modbus (status == "YES"), this
module fans out a background Read Device Identification (FC43) request per
device and emits (ip, manufacturer, product, version, error). Results are
written into the NetworkDiagnosticsDialog results view (output_text) with a
"IDENT" prefix so they're visually distinct from the scan results.

No connection state is shared between parallel identify calls -- each device
gets its own short-lived ModbusClient, same as the existing per-host probe
path. A 2s timeout keeps the identification round-trip from blocking the UI
during a slow network.
"""
import logging
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class DeviceIdentificationWorker(QThread):
    """One worker per discovered device -- fires FC43 Basic device identification
    and emits the manufacturer/product/version strings (or an error message) when
    it completes."""

    finished = Signal(str, str, str, str, str)  # ip, manufacturer, product, version, error
    # error is empty on success; manufacturer/product/version are empty strings when
    # the device doesn't support FC43 or returns nothing for a particular object.

    def __init__(self, ip, port, unit_id=1, timeout=2.0):
        super().__init__()
        self.ip = ip
        self.port = int(port)
        self.unit_id = unit_id
        self.timeout = timeout
        self._should_stop = False

    def stop(self):
        self._should_stop = True

    def run(self):
        manufacturer = ""
        product = ""
        version = ""
        error = ""

        try:
            from core.modbus_client import ModbusClient
            modbus = ModbusClient(
                self.ip, self.port, self.unit_id, timeout=self.timeout
            )
            if self._should_stop:
                return
            if not modbus.connect():
                error = "connect-failed"
                self.finished.emit(self.ip, manufacturer, product, version, error)
                return

            result = modbus.read_device_information(read_code=0x01)  # Basic
            if self._should_stop:
                modbus.disconnect()
                return

            if result is None:
                error = modbus.last_error or "FC43 returned None"
            else:
                info = result.get("information", {})
                if not info:
                    error = "no-id"
                else:
                    # pymodbus 3.x reads BASIC as objects 1,2,3 (VendorName,
                    # ProductCode, MajorMinorRevision).  Object ids are int
                    # keys; values are the raw bytes already decoded by the
                    # ModbusClient wrapper (it stores them as str).
                    for obj_id, text in info.items():
                        if obj_id == 1:
                            manufacturer = str(text).strip()
                        elif obj_id == 2:
                            product = str(text).strip()
                        elif obj_id == 3:
                            version = str(text).strip()
                    if not manufacturer and not product and not version:
                        error = "no-id"
            modbus.disconnect()
        except Exception as e:
            error = str(e)

        self.finished.emit(self.ip, manufacturer, product, version, error)
        logger.debug("Identify %s:%s unit=%s -> mfr=%r prod=%r ver=%r err=%r",
                     self.ip, self.port, self.unit_id, manufacturer, product, version, error)


def identify_device(ip, port, unit_id=1, timeout=2.0):
    """Synchronous convenience for tests -- same logic as the worker, no threading.
    Returns (manufacturer, product, version, error)."""
    manufacturer = ""
    product = ""
    version = ""
    error = ""
    try:
        from core.modbus_client import ModbusClient
        modbus = ModbusClient(ip, port, unit_id, timeout=timeout)
        if modbus.connect():
            result = modbus.read_device_information(read_code=0x01)
            if result is None:
                error = modbus.last_error or "FC43 returned None"
            else:
                info = result.get("information", {})
                if not info:
                    error = "no-id"
                else:
                    for obj_id, text in info.items():
                        if obj_id == 1:
                            manufacturer = str(text).strip()
                        elif obj_id == 2:
                            product = str(text).strip()
                        elif obj_id == 3:
                            version = str(text).strip()
                    if not manufacturer and not product and not version:
                        error = "no-id"
            modbus.disconnect()
        else:
            error = "connect-failed"
    except Exception as e:
        error = str(e)
    return manufacturer, product, version, error
