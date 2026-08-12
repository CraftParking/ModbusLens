import time

from PySide6.QtCore import QThread, Signal

from .read_merge import merge_tag_reads


def _read_block(modbus, plan):
    if plan["type"] == "Coil":
        return modbus.read_coils(plan["start"], plan["count"])
    if plan["type"] == "Discrete Input":
        return modbus.read_discrete_inputs(plan["start"], plan["count"])
    if plan["type"] == "Holding Register":
        return modbus.read_registers(plan["start"], plan["count"])
    return modbus.read_input_registers(plan["start"], plan["count"])


class TagPollWorker(QThread):
    """Runs one Tag Monitoring poll cycle's Modbus reads off the GUI thread, so a single
    unreachable device blocks this worker for timeout*retries seconds instead of freezing
    the whole window every poll cycle. Mirrors AddressScanWorker's split: only the
    blocking wire I/O and pure logic (address validation, read merging, the busy/overlap
    interlock, Fast LAN Mode's reachability check) happen here; every widget-touching side
    effect (table updates, System Log lines, Raw Data display) is left to the GUI thread,
    via signals.

    Coalesces adjacent/overlapping same-type tags into shared block reads (see
    read_merge.merge_tag_reads) before issuing anything on the wire -- on a slow serial
    link, N individually-addressed tags covering a contiguous register range become one
    request instead of N. Each tag still gets its own tag_result signal, sliced back out
    of whichever block covered it, so callers never need to know merging happened.

    Takes a snapshot of `modbus` and `tags` at construction time rather than reaching back
    into the main window's live attributes on every tag -- a disconnect/reconnect that
    swaps out self.modbus mid-cycle must not change what this in-flight worker is talking
    to. The caller is responsible for stopping and waiting on this thread before actually
    tearing down that same client object (see MonitoringManager.stop_poll_worker)."""

    # tag, value (None on failure), elapsed_ms, status ("ok"/"read_failed"/"exception"/"busy"/"unreachable"), detail
    tag_result = Signal(dict, object, float, str, str)
    device_unreachable = Signal()  # Fast LAN Mode: emitted once per cycle, at most
    cycle_complete = Signal(int, int)  # failed_count, total_count

    def __init__(self, tags, modbus, offset_of, validate_tag, reserve_range, release_range,
                 device_reachable, fast_lan_mode):
        super().__init__()
        self.tags = tags
        self.modbus = modbus
        self.offset_of = offset_of
        self.validate_tag = validate_tag
        self.reserve_range = reserve_range
        self.release_range = release_range
        self.device_reachable = device_reachable
        self.fast_lan_mode = fast_lan_mode
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        failed_count = 0

        # Validate every tag individually first, exactly like the old per-tag loop did --
        # one tag's bad address/count must only fail that tag, never its neighbors, so a
        # failing tag is excluded from merging rather than poisoning whatever block it
        # would have joined.
        valid_tags = []
        for tag in self.tags:
            try:
                self.validate_tag(tag, "read")
                valid_tags.append(tag)
            except Exception as e:
                failed_count += 1
                self.tag_result.emit(tag, None, 0.0, "exception", str(e))

        plans = merge_tag_reads(valid_tags, self.offset_of)

        device_unreachable = False
        for plan in plans:
            if self.should_stop:
                break

            if device_unreachable:
                failed_count += len(plan["members"])
                for tag, _local_offset in plan["members"]:
                    self.tag_result.emit(tag, None, 0.0, "unreachable", "")
                continue

            request_range = {
                "operation": "read", "space": plan["type"], "start": plan["start"],
                "end": plan["start"] + plan["count"] - 1,
                "tag": f"Merged[{plan['type']}] x{len(plan['members'])}",
            }
            if not self.reserve_range(request_range):
                failed_count += len(plan["members"])
                for tag, _local_offset in plan["members"]:
                    self.tag_result.emit(tag, None, 0.0, "busy", "")
                continue

            start_time = time.perf_counter()
            try:
                block_values = _read_block(self.modbus, plan)
            finally:
                self.release_range(request_range)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if block_values is None:
                failed_count += len(plan["members"])
                # Captured now, in this thread, right after the call that produced it --
                # last_error lives on the shared modbus client, and by the time the GUI
                # thread gets around to handling this signal a later block's read (already
                # underway in this same loop) may have overwritten it.
                last_error = getattr(self.modbus, "last_error", None) or ""
                for tag, _local_offset in plan["members"]:
                    self.tag_result.emit(tag, None, elapsed_ms, "read_failed", last_error)
                if self.fast_lan_mode and not self.device_reachable(self.modbus):
                    device_unreachable = True
                    self.device_unreachable.emit()
                continue

            for tag, local_offset in plan["members"]:
                value = block_values[local_offset: local_offset + tag["count"]]
                self.tag_result.emit(tag, value, elapsed_ms, "ok", "")

        self.cycle_complete.emit(failed_count, len(self.tags))
