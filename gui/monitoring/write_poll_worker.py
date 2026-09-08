import time

from PySide6.QtCore import QThread, Signal


class WriteTagPollWorker(QThread):
    """Runs one Write-mode Tags poll cycle's Modbus reads off the GUI thread. Write-mode
    tags show the device's *current* value so a user can see what's there before deciding
    to write a new one -- this cycle only ever reads, it never writes -- but the read
    itself was still a plain blocking loop on the GUI thread (main_window.py
    `_update_write_tag_values`, pre-2026-08-29), so a single unreachable write-mode
    device could freeze the whole window, the same hazard already fixed for the read-mode
    poll by TagPollWorker (see poll_worker.py).

    Deliberately does not merge adjacent tags into shared block reads the way
    TagPollWorker does for read-mode tags -- this fix's scope is moving the existing
    per-tag reads off the GUI thread, not adding merging on top.

    Takes a snapshot of `modbus`/`tags` at construction, same reasoning as TagPollWorker:
    a disconnect/reconnect swapping out self.modbus mid-cycle must not change what an
    in-flight worker is talking to. The caller is responsible for stopping and waiting on
    this thread before actually tearing down that same client object (see
    MonitoringManager.stop_write_poll_worker/wait_for_idle)."""

    # tag, value (None on failure), elapsed_ms, status ("ok"/"exception"/"busy"), detail, category,
    # tx_bytes, rx_bytes (None on failure)
    # (category is only ever "validation" or "" here -- read_tag_value raises instead of
    # returning None on a wire failure, so there's no separate ModbusClient-categorized
    # failure to distinguish, unlike TagPollWorker's read-mode "read_failed" status)
    #
    # tx_bytes/rx_bytes are captured here, in this thread, immediately after the call that
    # produced them -- last_tx_bytes/last_rx_bytes live on the shared modbus client, and by
    # the time the GUI thread gets around to handling this signal a later tag's read
    # (already underway in this same loop) may have overwritten them, misattributing one
    # tag's actual wire bytes to a different tag's Raw Data row. Same reasoning already
    # applied to last_error/last_error_category in TagPollWorker/_display_raw_data.
    tag_result = Signal(dict, object, float, str, str, str, object, object)
    cycle_complete = Signal(int, int)  # failed_count, total_count

    def __init__(self, tags, modbus, offset_of, read_tag_value, validate_tag, reserve_range, release_range):
        super().__init__()
        self.tags = tags
        self.modbus = modbus
        self.offset_of = offset_of
        self.read_tag_value = read_tag_value
        self.validate_tag = validate_tag
        self.reserve_range = reserve_range
        self.release_range = release_range
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        failed_count = 0

        for tag in self.tags:
            if self.should_stop:
                break

            try:
                self.validate_tag(tag, "read")
                offset = self.offset_of(tag)
            except Exception as e:
                failed_count += 1
                self.tag_result.emit(tag, None, 0.0, "exception", str(e), "validation", None, None)
                continue

            request_range = {
                "operation": "read", "space": tag["type"],
                "start": offset, "end": offset + tag["count"] - 1, "tag": tag["name"],
            }
            if not self.reserve_range(request_range):
                # Matches the pre-threading behavior exactly: a busy range is skipped
                # without counting toward the cycle's failed_count -- auto-stop only ever
                # cared about genuine read failures, not transient interlock contention.
                self.tag_result.emit(tag, None, 0.0, "busy", "", "busy", None, None)
                continue

            start_time = time.perf_counter()
            try:
                value = self.read_tag_value(tag, modbus=self.modbus)
            except Exception as e:
                tx_bytes = getattr(self.modbus, "last_tx_bytes", None)
                rx_bytes = getattr(self.modbus, "last_rx_bytes", None)
                self.release_range(request_range)
                failed_count += 1
                self.tag_result.emit(tag, None, 0.0, "exception", str(e), "validation", tx_bytes, rx_bytes)
                continue
            tx_bytes = getattr(self.modbus, "last_tx_bytes", None)
            rx_bytes = getattr(self.modbus, "last_rx_bytes", None)
            self.release_range(request_range)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            self.tag_result.emit(tag, value, elapsed_ms, "ok", "", "", tx_bytes, rx_bytes)

        self.cycle_complete.emit(failed_count, len(self.tags))
