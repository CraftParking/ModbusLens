import time
from PySide6.QtWidgets import QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem


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
            })
        return tags

    def add_monitoring_row(self, tag_name, mode, data_type, address, read_value, write_value, comment, timestamp, raw_hex=""):
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

        if raw_hex:
            raw_hex_widget = target_table.cellWidget(target_row, 7)
            if raw_hex_widget:
                raw_hex_widget.setText(raw_hex)

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
        """Clear cached monitoring values and the diagnostics results table."""
        self._monitoring_read_value_cache.clear()
        self._monitoring_write_value_cache.clear()

        if hasattr(self.parent, 'diagnostics_results_table'):
            self.parent.diagnostics_results_table.setRowCount(0)

    def read_tag_for_monitoring(self, tag, is_one_based=None):
        """Read data for a specific tag during monitoring."""
        try:
            protocol_offset = self.parent._tag_user_address_to_offset(tag)
        except ValueError as e:
            self.parent._log(f"Address error for tag {tag['name']}: {e}")
            return None
        
        if tag["type"] == "Coil":
            return self.parent.modbus.read_coils(protocol_offset, tag["count"])
        if tag["type"] == "Discrete Input":
            return self.parent.modbus.read_discrete_inputs(protocol_offset, tag["count"])
        if tag["type"] == "Holding Register":
            return self.parent.modbus.read_registers(protocol_offset, tag["count"])
        return self.parent.modbus.read_input_registers(protocol_offset, tag["count"])

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

    def format_raw_hex(self, tag, value):
        """Format the raw register/bit value(s), independent of the tag's decoded format."""
        if value is None:
            return ""
        values = value[: tag["count"]] if isinstance(value, list) else [value]
        if tag["type"] in ("Coil", "Discrete Input"):
            return ", ".join("1" if bool(v) else "0" for v in values)
        return ", ".join(f"0x{int(v) & 0xFFFF:04X}" for v in values)

    def update_monitored_data(self):
        """Update monitored data in the table."""
        if not self.parent.modbus or not self.parent.monitoring_active:
            return
        if self._monitoring_poll_in_progress:
            self.parent._log("Safety interlock: skipped monitor tick because previous poll is still running")
            return

        tags = [tag for tag in self.get_monitoring_tags() if tag["mode"] == "Read"]
        if not tags:
            return

        self._monitoring_poll_in_progress = True
        self.parent.monitoring_timer.stop()
        poll_failed = False
        timestamp = time.strftime("%H:%M:%S")
        try:
            for tag in tags:
                try:
                    self.parent._validate_tag_request(tag, "read")
                    if not self.parent._begin_modbus_operation(tag, "read"):
                        self.parent._log(f"Safety interlock: skipped read for {tag['name']} because the range is busy")
                        continue

                    try:
                        value = self.read_tag_for_monitoring(tag)
                    finally:
                        self.parent._end_modbus_operation(tag, "read")

                    if value is None:
                        poll_failed = True
                        self.add_monitoring_row(
                            tag["name"], tag["mode"], tag["type"], tag["address"], "ERROR", "",
                            tag["comment"], timestamp
                        )
                        extra = ""
                        if self.parent.modbus is not None and getattr(self.parent.modbus, "last_error", None):
                            extra = f" ({self.parent.modbus.last_error})"
                        self.parent._log(f"Monitoring read failed for {tag['name']} at {tag['address']}{extra}")
                        break

                    display_value = self.format_monitoring_value(tag, value)
                    raw_hex = self.format_raw_hex(tag, value)

                    # Display raw data in diagnostics for Tags monitoring
                    self.parent._display_raw_data(f"Tag[{tag['name']}]", value)

                    self.add_monitoring_row(
                        tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                        tag["comment"], timestamp, raw_hex
                    )
                except Exception as e:
                    poll_failed = True
                    self.parent._log(f"Monitoring error for {tag['name']}: {e}")
                    break

            if poll_failed:
                self._monitoring_failure_count += 1
                if self._monitoring_failure_count >= self._monitoring_max_failures:
                    self.parent._log(f"Stopping monitoring after {self._monitoring_failure_count} consecutive failures")
                    self.parent._stop_monitoring()
                    return
            else:
                self._monitoring_failure_count = 0
        finally:
            self._monitoring_poll_in_progress = False
            self.parent.monitoring_timer.start()

