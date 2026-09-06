"""
Phase 1: Unit ID sweep on discovery.

When a discovered host is confirmed Modbus (status == "YES") and the "Scan Unit
IDs" checkbox is on, this module sweeps Unit IDs 1-247 against that host and
reports which ones respond. Reuses the same `probe_modbus_device()` used by the
main discovery scan, just called once per Unit ID against a single host instead
of once per host on a fixed Unit ID.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

MIN_UNIT_ID = 1
MAX_UNIT_ID = 247


class UnitIdSweepWorker(QThread):
    """One worker per discovered host -- probes every Unit ID 1-247 against it
    and emits each one that answers as Modbus, then a final summary."""

    unit_found = Signal(str, int)  # ip, unit_id
    finished = Signal(str, list)  # ip, sorted list of responding unit ids

    def __init__(self, ip, port, timeout=1.0, max_workers=20):
        super().__init__()
        self.ip = ip
        self.port = int(port)
        self.timeout = timeout
        self.max_workers = max_workers
        self._should_stop = False

    def stop(self):
        self._should_stop = True

    def run(self):
        from gui.network.network_diagnostics import probe_modbus_device

        found = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    probe_modbus_device, self.ip, self.port, self.timeout, unit_id
                ): unit_id
                for unit_id in range(MIN_UNIT_ID, MAX_UNIT_ID + 1)
            }
            for future in as_completed(futures):
                if self._should_stop:
                    break
                unit_id = futures[future]
                try:
                    status = future.result()
                except Exception:
                    status = "ERROR"
                if status == "YES":
                    found.append(unit_id)
                    self.unit_found.emit(self.ip, unit_id)

        found.sort()
        self.finished.emit(self.ip, found)
        logger.debug("Unit ID sweep %s:%s -> %s", self.ip, self.port, found)
