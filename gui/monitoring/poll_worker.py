import time

from PySide6.QtCore import QThread, Signal


class TagPollWorker(QThread):
    """Runs one Tag Monitoring poll cycle's Modbus reads off the GUI thread, so a single
    unreachable device blocks this worker for timeout*retries seconds instead of freezing
    the whole window every poll cycle. Mirrors AddressScanWorker's split: only the
    blocking wire I/O and pure logic (address validation, the busy/overlap interlock,
    Fast LAN Mode's reachability check) happen here; every widget-touching side effect
    (table updates, System Log lines, Raw Data display) is left to the GUI thread, via
    signals.

    Takes a snapshot of `modbus` and `tags` at construction time rather than reaching back
    into the main window's live attributes on every tag -- a disconnect/reconnect that
    swaps out self.modbus mid-cycle must not change what this in-flight worker is talking
    to. The caller is responsible for stopping and waiting on this thread before actually
    tearing down that same client object (see MonitoringManager.stop_poll_worker)."""

    # tag, value (None on failure), elapsed_ms, status ("ok"/"read_failed"/"exception"/"busy"/"unreachable"), detail
    tag_result = Signal(dict, object, float, str, str)
    device_unreachable = Signal()  # Fast LAN Mode: emitted once per cycle, at most
    cycle_complete = Signal(int, int)  # failed_count, total_count

    def __init__(self, tags, modbus, read_tag, validate_tag, reserve_range, release_range,
                 operation_range, device_reachable, fast_lan_mode):
        super().__init__()
        self.tags = tags
        self.modbus = modbus
        self.read_tag = read_tag
        self.validate_tag = validate_tag
        self.reserve_range = reserve_range
        self.release_range = release_range
        self.operation_range = operation_range
        self.device_reachable = device_reachable
        self.fast_lan_mode = fast_lan_mode
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        failed_count = 0
        device_unreachable = False
        for tag in self.tags:
            if self.should_stop:
                break

            if device_unreachable:
                failed_count += 1
                self.tag_result.emit(tag, None, 0.0, "unreachable", "")
                continue

            try:
                self.validate_tag(tag, "read")
                request_range = self.operation_range(tag, "read")
                if not self.reserve_range(request_range):
                    failed_count += 1
                    self.tag_result.emit(tag, None, 0.0, "busy", "")
                    continue

                start_time = time.perf_counter()
                try:
                    value = self.read_tag(tag, self.modbus)
                finally:
                    self.release_range(request_range)
                elapsed_ms = (time.perf_counter() - start_time) * 1000
            except Exception as e:
                failed_count += 1
                self.tag_result.emit(tag, None, 0.0, "exception", str(e))
                continue

            if value is None:
                failed_count += 1
                # Captured now, in this thread, right after the call that produced it --
                # last_error lives on the shared modbus client, and by the time the GUI
                # thread gets around to handling this signal a later tag's read (already
                # underway in this same loop) may have overwritten it.
                last_error = getattr(self.modbus, "last_error", None) or ""
                self.tag_result.emit(tag, None, elapsed_ms, "read_failed", last_error)
                if self.fast_lan_mode and not self.device_reachable(self.modbus):
                    device_unreachable = True
                    self.device_unreachable.emit()
                continue

            self.tag_result.emit(tag, value, elapsed_ms, "ok", "")

        self.cycle_complete.emit(failed_count, len(self.tags))
