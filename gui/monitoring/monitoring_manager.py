import csv
import os
import socket
import time

from PySide6.QtWidgets import QMessageBox

from modbus_meta import function_code_for

from .poll_worker import TagPollWorker
from .write_poll_worker import WriteTagPollWorker


class MonitoringManager:
    """Manages Tags monitoring functionality including data caching and synchronization."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self._monitoring_write_value_cache = {}
        self._monitoring_read_value_cache = {}  # Store read values for Tags monitoring
        self._monitoring_poll_in_progress = False
        self._monitoring_failure_count = 0
        self._monitoring_max_failures = 3
        self._write_poll_in_progress = False
        self.tag_alarms = {}  # row index -> alarm config dict
        self.tag_scaling = {}  # row index -> engineering-unit scaling config dict
        self._log_file = None
        self._log_writer = None
        self._poll_worker = None  # the in-flight TagPollWorker, if a poll cycle is running
        self._write_poll_worker = None  # the in-flight WriteTagPollWorker, if one is running
        # Workers told to stop (Stop Monitoring, disconnect) but not yet actually finished
        # -- held here so nothing drops the last Python reference to a still-running
        # QThread, which crashes. Each one removes itself via its own `finished` signal.
        # Shared between the read-mode and write-mode poll workers -- this set doesn't
        # care which kind of worker it's holding, only that it isn't finished yet.
        self._retiring_poll_workers = set()
        self._current_poll_timestamp = None
        self._current_poll_log_timestamp = None
        self._current_write_poll_timestamp = None

    def start_csv_logging(self, file_path):
        """Start appending one row per poll tick to file_path."""
        is_new_or_empty = True
        try:
            is_new_or_empty = os.path.getsize(file_path) == 0
        except OSError:
            pass  # file doesn't exist yet -- treat as new

        self._log_file = open(file_path, "a", newline="", encoding="utf-8")
        self._log_writer = csv.writer(self._log_file)
        if is_new_or_empty:
            self._log_writer.writerow(["Timestamp", "Tag Name", "Mode", "Type", "Address", "Value", "Raw Hex"])
            self._log_file.flush()

    def stop_csv_logging(self):
        if self._log_file:
            self._log_file.close()
        self._log_file = None
        self._log_writer = None

    def is_logging(self):
        return self._log_writer is not None

    def _log_row(self, tag, timestamp, value_text, raw_hex):
        if not self._log_writer:
            return
        self._log_writer.writerow([timestamp, tag["name"], tag["mode"], tag["type"], tag["address"], value_text, raw_hex])
        self._log_file.flush()

    def handle_row_inserted(self, row):
        """Keep tag_alarms/tag_scaling aligned with table rows after a new row is inserted at `row`."""
        self.tag_alarms = {(r + 1 if r >= row else r): cfg for r, cfg in self.tag_alarms.items()}
        self.tag_scaling = {(r + 1 if r >= row else r): cfg for r, cfg in self.tag_scaling.items()}

    def handle_row_removed(self, row):
        """Keep tag_alarms/tag_scaling aligned with table rows after the row at `row` is removed."""
        self.tag_alarms.pop(row, None)
        self.tag_alarms = {(r - 1 if r > row else r): cfg for r, cfg in self.tag_alarms.items()}
        self.tag_scaling.pop(row, None)
        self.tag_scaling = {(r - 1 if r > row else r): cfg for r, cfg in self.tag_scaling.items()}

    def check_alarm(self, tag, value):
        """Return True if this tag's current value violates its configured alarm."""
        alarm = self.tag_alarms.get(tag["row"])
        if not alarm or not alarm.get("enabled") or value is None:
            return False

        is_bool_like = tag["type"] in ("Coil", "Discrete Input") or (tag.get("format") or "").strip().upper() == "BOOL"
        if is_bool_like:
            raw = value[0] if isinstance(value, list) else value
            return bool(raw) == alarm.get("bool_state", True)

        registers = value[: tag["count"]] if isinstance(value, list) else [value]
        value_format = (tag.get("format") or "U16").strip().upper()
        try:
            decoded = self.parent._decode_register_values(registers, value_format)
            numeric = float(decoded[0] if isinstance(decoded, list) else decoded)
        except (ValueError, TypeError):
            return False

        if alarm.get("high_enabled") and numeric > alarm.get("high", float("inf")):
            return True
        if alarm.get("low_enabled") and numeric < alarm.get("low", float("-inf")):
            return True
        return False

    def _apply_alarm_style(self, widget, in_alarm):
        if widget is None:
            return
        if in_alarm:
            widget.setStyleSheet(
                "background-color: #FFCDD2; color: #B71C1C; font-weight: bold; "
                "border: 1px solid #E57373; padding: 5px;"
            )
        else:
            widget.setStyleSheet(self.parent._get_input_style())

    def get_monitoring_tags(self):
        """Get all configured monitoring tags from the tag table."""
        tags = []
        for row in range(self.parent.monitoring_tag_table.rowCount()):
            name_widget = self.parent.monitoring_tag_table.cellWidget(row, 0)
            mode_widget = self.parent.monitoring_tag_table.cellWidget(row, 1)
            type_widget = self.parent.monitoring_tag_table.cellWidget(row, 2)
            address_widget = self.parent.monitoring_tag_table.cellWidget(row, 3)
            count_widget = self.parent.monitoring_tag_table.cellWidget(row, 4)
            format_widget = self.parent.monitoring_tag_table.cellWidget(row, 5)
            read_value_widget = self.parent.monitoring_tag_table.cellWidget(row, 6)
            raw_hex_widget = self.parent.monitoring_tag_table.cellWidget(row, 7)
            write_value_widget = self.parent.monitoring_tag_table.cellWidget(row, 8)
            comment_widget = self.parent.monitoring_tag_table.cellWidget(row, 9)
            enabled_widget = self.parent.monitoring_tag_table.cellWidget(row, 13)

            if not all((name_widget, mode_widget, type_widget, address_widget, count_widget, format_widget, read_value_widget, raw_hex_widget, write_value_widget, comment_widget)):
                continue

            name = name_widget.text().strip()
            mode = mode_widget.currentText()
            tag_type = type_widget.currentText()
            address = address_widget.value()
            count = count_widget.value()
            value_format = format_widget.currentText() if hasattr(format_widget, "currentText") else "U16"
            comment = comment_widget.text().strip()
            
            # Skip rows without names - this prevents duplicate tags
            if not name:
                continue
            
            # Skip default placeholder names like Tag_1, Tag_2, etc.
            if name.startswith("Tag_") and name.split("_")[-1].isdigit():
                continue
            
            tags.append({
                "row": row,
                "name": name,
                "mode": mode,
                "type": tag_type,
                "address": address,
                "count": count,
                "format": value_format,
                "comment": comment,
                "enabled": enabled_widget.checkbox.isChecked() if enabled_widget else True,
            })
        return tags

    def add_monitoring_row(self, tag_name, mode, data_type, address, read_value, write_value, comment, timestamp, raw_hex="", in_alarm=False, engineering_value=""):
        """Add or update a tag row in the integrated Tags table."""
        key = (tag_name, data_type, str(address))
        
        # Store read value in cache for Tags monitoring
        if read_value:
            self._monitoring_read_value_cache[key] = read_value
        
        if write_value:
            self._monitoring_write_value_cache[key] = write_value

        cached_write_value = self._monitoring_write_value_cache.get(key, "")
        initial_write_value = write_value if write_value else cached_write_value

        # Update the integrated Tags table directly
        target_table = self.parent.monitoring_tag_table

        # Find the row for this tag
        target_row = None
        for row in range(target_table.rowCount()):
            name_widget = target_table.cellWidget(row, 0)
            if name_widget and name_widget.text().strip() == tag_name:
                type_widget = target_table.cellWidget(row, 2)
                address_widget = target_table.cellWidget(row, 3)
                if (type_widget and type_widget.currentText() == data_type and 
                    address_widget and address_widget.value() == address):
                    target_row = row
                    break

        if target_row is None:
            return  # Tag not found in table

        if read_value:
            read_value_widget = target_table.cellWidget(target_row, 6)
            if read_value_widget:
                read_value_widget.setText(read_value)
                self._apply_alarm_style(read_value_widget, in_alarm)

        if raw_hex:
            raw_hex_widget = target_table.cellWidget(target_row, 7)
            if raw_hex_widget:
                raw_hex_widget.setText(raw_hex)

        eng_value_widget = target_table.cellWidget(target_row, 11)
        if eng_value_widget:
            eng_value_widget.setText(engineering_value)

        # Only touch the write column if we have something meaningful to show,
        # so polling doesn't stomp on a value the user is currently typing.
        if write_value:
            write_value_widget = target_table.cellWidget(target_row, 8)
            if write_value_widget:
                write_value_widget.setText(write_value)
        elif initial_write_value:
            write_value_widget = target_table.cellWidget(target_row, 8)
            if write_value_widget and not write_value_widget.text():
                write_value_widget.setText(initial_write_value)

        timestamp_widget = target_table.cellWidget(target_row, 10)
        if timestamp_widget:
            timestamp_widget.setText(timestamp)

    def clear_monitoring_results(self):
        """Clear cached monitoring values."""
        self._monitoring_read_value_cache.clear()
        self._monitoring_write_value_cache.clear()

    def _device_reachable(self, modbus, timeout=0.2):
        """Bare TCP connect check against the current target -- used in Fast LAN Mode to
        tell 'device unplugged' from 'this one register errored' after a poll failure,
        without paying pymodbus's own connect+read cost a second time. Serial links have
        no equivalent cheap check, so they're always treated as reachable. Takes `modbus`
        explicitly (rather than reading self.parent.modbus) so it checks the exact client
        TagPollWorker started its cycle with, even though this runs on that worker's
        thread -- self.parent.modbus can be replaced by a disconnect/reconnect on the GUI
        thread while a cycle is still in flight."""
        if modbus is None or getattr(modbus, "mode", "tcp") != "tcp":
            return True
        try:
            with socket.create_connection((modbus.ip, modbus.port), timeout=timeout):
                return True
        except OSError:
            return False

    def format_monitoring_value(self, tag, value):
        """Format a monitoring value for display."""
        if value is None:
            return "ERROR"

        if tag["type"] in ("Coil", "Discrete Input"):
            if isinstance(value, list):
                visible_values = value[: tag["count"]]
                if tag["count"] == 1 and visible_values:
                    return str(bool(visible_values[0]))
                return ", ".join(str(bool(v)) for v in visible_values)
            return str(bool(value))

        if not isinstance(value, list):
            return str(value)

        registers = value[: tag["count"]]
        value_format = (tag.get("format") or "U16").strip().upper()
        try:
            decoded = self.parent._decode_register_values(registers, value_format)
        except Exception:
            decoded = registers

        if tag["count"] == 1:
            return str(decoded[0]) if isinstance(decoded, list) else str(decoded)
        else:
            return ", ".join(str(v) for v in decoded)

    def _decode_numeric_value(self, tag, value):
        """The single decoded number behind a tag's Read Value, for scaling -- None for bit
        types or a value that doesn't resolve to exactly one number."""
        if tag["type"] in ("Coil", "Discrete Input") or value is None:
            return None

        registers = value[: tag["count"]] if isinstance(value, list) else [value]
        value_format = (tag.get("format") or "U16").strip().upper()
        try:
            decoded = self.parent._decode_register_values(registers, value_format)
        except Exception:
            return None
        result = decoded[0] if isinstance(decoded, list) else decoded
        try:
            return float(result)
        except (TypeError, ValueError):
            return None

    def compute_engineering_value(self, tag, value):
        """Raw-to-scaled transform configured via tag_scaling -- either linear (raw
        min/max -> scaled min/max) or multiply-by-constant. Returns "" if scaling isn't
        enabled for this tag or the value can't be decoded to a single number.
        Configs saved before the "mode" field existed have no such key -- treat those as
        linear, since that was the only mode available when they were written."""
        config = self.tag_scaling.get(tag["row"])
        if not config or not config.get("enabled"):
            return ""
        raw = self._decode_numeric_value(tag, value)
        if raw is None:
            return ""
        if config.get("mode") == "multiply":
            scaled = raw * config.get("factor", 1.0)
        else:
            raw_min, raw_max = config["raw_min"], config["raw_max"]
            scaled_min, scaled_max = config["scaled_min"], config["scaled_max"]
            if raw_max == raw_min:
                return ""
            scaled = (raw - raw_min) / (raw_max - raw_min) * (scaled_max - scaled_min) + scaled_min
        if config.get("value_type") == "Integer":
            return str(int(round(scaled)))
        return f"{scaled:g}"

    def format_raw_hex(self, tag, value):
        """Format the raw register/bit value(s), independent of the tag's decoded format."""
        if value is None:
            return ""
        values = value[: tag["count"]] if isinstance(value, list) else [value]
        if tag["type"] in ("Coil", "Discrete Input"):
            return ", ".join("1" if bool(v) else "0" for v in values)
        return ", ".join(f"0x{int(v) & 0xFFFF:04X}" for v in values)

    def update_monitored_data(self):
        """Launch one Tag Monitoring poll cycle on a background TagPollWorker instead of
        reading every tag right here on the GUI thread -- a single unreachable device used
        to freeze the whole window for timeout*retries seconds, every cycle, since this
        ran as a plain blocking loop on a QTimer tick. The actual per-tag results and the
        cycle-level wrap-up arrive later via _on_tag_poll_result/_on_poll_cycle_complete,
        reproducing exactly what this loop used to do inline, just off the GUI thread for
        the parts that block (validation, the interlock, and the wire call itself)."""
        if not self.parent.modbus or not self.parent.monitoring_active:
            return
        if self._monitoring_poll_in_progress:
            self.parent._log("Safety interlock: skipped monitor tick because previous poll is still running")
            return

        tags = [tag for tag in self.get_monitoring_tags() if tag["mode"] == "Read" and tag["enabled"]]
        if not tags:
            return

        self._monitoring_poll_in_progress = True
        self.parent.monitoring_timer.stop()
        self._current_poll_timestamp = time.strftime("%H:%M:%S")
        self._current_poll_log_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        worker = TagPollWorker(
            tags, self.parent.modbus, self.parent._tag_user_address_to_offset, self.parent._validate_tag_request,
            self.parent._reserve_range, self.parent._release_range,
            self._device_reachable, getattr(self.parent, "fast_lan_mode", False),
            shared_cache=getattr(self.parent, "_shared_read_cache", None),
        )
        worker.tag_result.connect(self._on_tag_poll_result)
        worker.cycle_complete.connect(self._on_poll_cycle_complete)
        worker.device_unreachable.connect(self._on_poll_device_unreachable)
        self._poll_worker = worker
        worker.start()

    def _on_tag_poll_result(self, tag, value, elapsed_ms, status, detail, category):
        """GUI-thread handler for one tag's result from the poll worker -- does exactly
        what the old inline loop body did after getting a value back, since all of this
        touches Qt widgets (the Tags table, the System Log, the Raw Data tab) and must
        stay off the worker thread."""
        timestamp = self._current_poll_timestamp
        log_timestamp = self._current_poll_log_timestamp

        if status == "ok":
            display_value = self.format_monitoring_value(tag, value)
            raw_hex = self.format_raw_hex(tag, value)
            in_alarm = self.check_alarm(tag, value)
            engineering_value = self.compute_engineering_value(tag, value)
            self.parent._display_raw_data(
                f"Tag[{tag['name']}]", value, elapsed_ms, function_code_for(tag["type"], is_write=False)
            )
            self.add_monitoring_row(
                tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                tag["comment"], timestamp, raw_hex, in_alarm, engineering_value
            )
            self._log_row(tag, log_timestamp, display_value, raw_hex)
            return

        self.add_monitoring_row(
            tag["name"], tag["mode"], tag["type"], tag["address"], "ERROR", "", tag["comment"], timestamp
        )
        self._log_row(tag, log_timestamp, "ERROR", "")

        if status == "read_failed":
            extra = f" ({detail})" if detail else ""
            self.parent._log(f"Monitoring read failed for {tag['name']} at {tag['address']}{extra}")
            self.parent._display_raw_data(
                f"Tag[{tag['name']}]", None, elapsed_ms, function_code_for(tag["type"], is_write=False),
                error_category=category,
            )
        elif status == "busy":
            self.parent._log(f"Safety interlock: skipped read for {tag['name']} because the range is busy")
        elif status == "exception":
            self.parent._log(f"Monitoring error for {tag['name']}: {detail}")
        # status == "unreachable": the one-time transition message already went out via
        # _on_poll_device_unreachable -- nothing more to log for each tag skipped after it.

    def _on_poll_device_unreachable(self):
        self.parent._log("Fast LAN Mode: device unreachable, skipping remaining tags this cycle")

    def _retire_worker(self, worker):
        """A poll cycle's own completion signal (cycle_complete) is delivered to the GUI
        thread as a queued connection from the worker thread, emitted as the very last
        thing run() does -- but a queued delivery reaching the GUI thread's event loop
        doesn't guarantee Qt has already finished internally marking that QThread as
        no-longer-running. If the handler here were the *only* place still holding a
        Python reference to the worker (which it is, once the caller's own
        _poll_worker/_write_poll_worker slot is set to None), dropping that reference
        would drop the object's refcount to zero and trigger its C++ destructor right
        then -- and destroying a QThread Qt still considers running is undefined
        behavior (can abort the process: "QThread: Destroyed while thread is still
        running"). Confirmed reproducible, not just theoretical, while verifying the
        write-mode poll fix. Same reasoning stop_poll_worker already applies on the
        explicit-stop path -- this covers the natural-completion path the same way,
        keeping a strong reference alive in _retiring_poll_workers until the QThread's
        own finished signal proves it's actually done."""
        if worker is None or worker.isFinished():
            return
        self._retiring_poll_workers.add(worker)
        worker.finished.connect(lambda w=worker: self._retiring_poll_workers.discard(w))

    def _on_poll_cycle_complete(self, failed_count, total_count):
        """GUI-thread handler for the end of a poll cycle -- the auto-stop-after-N-failures
        logic and restarting monitoring_timer, exactly as the old inline loop's finally
        block did, just triggered by the worker finishing instead of falling out of a loop."""
        self._retire_worker(self._poll_worker)
        self._poll_worker = None
        self._monitoring_poll_in_progress = False

        # Only treat this as a lost-connection-style failure (and count toward auto-stop)
        # when every tag failed -- a single bad tag (e.g. a newly added one with a bad
        # address/format) shouldn't halt polling for the rest, nor trip the auto-stop
        # interlock.
        if total_count and failed_count == total_count:
            self._monitoring_failure_count += 1
            if self._monitoring_failure_count >= self._monitoring_max_failures:
                self.parent._log(f"Stopping monitoring after {self._monitoring_failure_count} consecutive failures")
                self.parent._monitoring_paused_by_disconnect = True
                self.parent._stop_monitoring()
                return
        else:
            self._monitoring_failure_count = 0

        if self.parent.monitoring_active:
            self.parent.monitoring_timer.start()

    def update_write_tag_values(self):
        """Launch one Write-mode Tags poll cycle on a background WriteTagPollWorker
        instead of reading every write-mode tag right here on the GUI thread -- mirrors
        update_monitored_data's 2026-08-12 read-mode fix: a single unreachable write-mode
        device used to freeze the whole window for timeout*retries seconds, every cycle,
        since this ran as a plain blocking loop on write_poll_timer. The actual per-tag
        results and the cycle-level wrap-up arrive later via
        _on_write_tag_poll_result/_on_write_poll_cycle_complete, reproducing exactly what
        this loop used to do inline, just off the GUI thread for the parts that block
        (validation and the wire call itself)."""
        if not self.parent.modbus or not self.parent.monitoring_active:
            return
        if self._write_poll_in_progress:
            self.parent._log("Safety interlock: skipped write-tag poll because previous poll is still running")
            return
        if self.parent._modbus_busy:
            return

        tags = [tag for tag in self.get_monitoring_tags() if tag["mode"] == "Write" and tag["enabled"]]
        if not tags:
            return

        self._write_poll_in_progress = True
        self.parent.write_poll_timer.stop()
        self._current_write_poll_timestamp = time.strftime("%H:%M:%S")

        worker = WriteTagPollWorker(
            tags, self.parent.modbus, self.parent._tag_user_address_to_offset, self.parent._read_tag_value,
            self.parent._validate_tag_request, self.parent._reserve_range, self.parent._release_range,
        )
        worker.tag_result.connect(self._on_write_tag_poll_result)
        worker.cycle_complete.connect(self._on_write_poll_cycle_complete)
        self._write_poll_worker = worker
        worker.start()

    def _on_write_tag_poll_result(self, tag, value, elapsed_ms, status, detail, category):
        """GUI-thread handler for one write-mode tag's result from the poll worker -- does
        exactly what the old inline loop body did after getting a value back, since all of
        this touches Qt widgets (the Tags table, Raw Data tab, System Log) and must stay
        off the worker thread. Matches the pre-threading behavior's minimal error handling
        exactly: unlike the read-mode poll, a failed write-mode tag never touches the Tags
        table or Raw Data tab at all -- it just logs and leaves the row at its
        last-known value."""
        if status == "ok":
            timestamp = self._current_write_poll_timestamp
            display_value = self.parent._format_monitoring_value(tag, value)
            raw_hex = self.format_raw_hex(tag, value)
            self.parent._display_raw_data(
                f"Tag[{tag['name']}] (write-mode, current value)", value, elapsed_ms,
                function_code_for(tag["type"], is_write=False),
            )
            self.add_monitoring_row(
                tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                tag["comment"], timestamp, raw_hex
            )
            return

        if status == "busy":
            self.parent._log(f"Safety interlock: skipped write-tag read for {tag['name']} because the range is busy")
            return

        # status == "exception": address/validation error, an unwritable tag type, or a
        # failed pre-read -- the old inline try/except produced the exact same single
        # generic log line for all of these, so detail (str(e)) reproduces it here too.
        self.parent._log(f"Write-tag value polling error for {tag['name']}: {detail}")

    def _on_write_poll_cycle_complete(self, failed_count, total_count):
        """GUI-thread handler for the end of a write-mode poll cycle -- the
        auto-stop-after-N-failures logic and restarting write_poll_timer, exactly as the
        old inline loop's finally block did, just triggered by the worker finishing
        instead of falling out of a loop. Deliberately shares _monitoring_failure_count
        with the read-mode poll's own cycle-complete handler, matching the original's
        behavior exactly -- read-mode and write-mode failures were already counted
        against the same auto-stop threshold before this fix, not tracked separately."""
        self._retire_worker(self._write_poll_worker)
        self._write_poll_worker = None
        self._write_poll_in_progress = False

        # Only a fully failed tick (every write tag failed) counts toward auto-stop --
        # one bad tag shouldn't halt polling for the rest.
        if total_count and failed_count == total_count:
            self._monitoring_failure_count += 1
            if self._monitoring_failure_count >= self._monitoring_max_failures:
                self.parent._log(
                    f"Monitoring stopped after {self._monitoring_failure_count} consecutive failed poll(s)"
                )
                self.parent._monitoring_paused_by_disconnect = True
                self.parent._stop_monitoring()
                QMessageBox.warning(
                    self.parent,
                    "Monitoring Stopped",
                    "Monitoring was stopped after repeated Modbus failures. ModbusLens will keep trying to "
                    "reconnect in the background and resume monitoring automatically once it succeeds. If it "
                    "doesn't recover, check write tag type, address, unit ID, and server status.",
                )
                return
        else:
            self._monitoring_failure_count = 0

        if self.parent.monitoring_active:
            self.parent.write_poll_timer.start(1000)

    def stop_write_poll_worker(self, wait=False):
        """Write-mode counterpart of stop_poll_worker -- see its docstring for the full
        reasoning (non-blocking by default so a still-running worker can finish its
        current tag in the background; wait=True, or wait_for_idle() below, for a hard
        guarantee nothing is still touching self.modbus)."""
        worker = self._write_poll_worker
        self._write_poll_worker = None
        if worker is None:
            return

        worker.stop()
        for signal, slot in (
            (worker.tag_result, self._on_write_tag_poll_result),
            (worker.cycle_complete, self._on_write_poll_cycle_complete),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

        if wait:
            worker.wait(10000)
        elif worker.isRunning():
            self._retiring_poll_workers.add(worker)
            worker.finished.connect(lambda w=worker: self._retiring_poll_workers.discard(w))

    def stop_poll_worker(self, wait=False):
        """Stop the in-flight poll worker, if any. Non-blocking by default (Stop
        Monitoring button click): self.modbus stays alive either way, so there's nothing
        unsafe about letting a worker finish its current tag in the background --
        disconnecting its signals here is what actually matters, so a late-arriving result
        from a stopped cycle can't resurrect the Tags table or restart monitoring_timer
        after the user asked for it to stop. wait=True additionally blocks until this
        specific worker (not any earlier one still retiring -- see wait_for_idle) has
        actually finished; callers that need a hard guarantee nothing is still touching
        self.modbus (disconnect, Register Scanner's pause) should call wait_for_idle()
        instead, since a *previous* Stop Monitoring click's worker could still be retiring
        in the background when this one starts."""
        worker = self._poll_worker
        self._poll_worker = None
        if worker is None:
            return

        worker.stop()
        for signal, slot in (
            (worker.tag_result, self._on_tag_poll_result),
            (worker.cycle_complete, self._on_poll_cycle_complete),
            (worker.device_unreachable, self._on_poll_device_unreachable),
        ):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

        if wait:
            worker.wait(10000)
        elif worker.isRunning():
            # Keep a strong reference until it actually finishes -- dropping the last
            # Python reference to a still-running QThread is undefined behavior.
            self._retiring_poll_workers.add(worker)
            worker.finished.connect(lambda w=worker: self._retiring_poll_workers.discard(w))

    def wait_for_idle(self, timeout_ms=10000):
        """Block until every poll worker this manager knows about -- the current
        read-mode and write-mode workers, if any, plus any still-retiring ones from an
        earlier non-blocking stop -- has actually finished touching self.modbus. Needed
        before anything that tears down or replaces the shared client (disconnect) or
        starts a second thread against it with no interlock of its own (Register Scanner,
        which relies entirely on everything else being truly stopped first, not on the
        range interlock)."""
        self.stop_poll_worker(wait=False)
        self.stop_write_poll_worker(wait=False)
        for worker in list(self._retiring_poll_workers):
            worker.wait(timeout_ms)

