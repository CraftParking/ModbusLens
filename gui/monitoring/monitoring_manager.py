import time


class MonitoringManager:
    """Manages Tags monitoring functionality including data caching and synchronization."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self._monitoring_write_value_cache = {}
        self._monitoring_read_value_cache = {}  # Store read values for Tags monitoring
        self._monitoring_poll_in_progress = False
        self._monitoring_failure_count = 0
        self._monitoring_max_failures = 3

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
            comment_widget = self.parent.monitoring_tag_table.cellWidget(row, 6)

            if not all((name_widget, mode_widget, type_widget, address_widget, count_widget, format_widget, comment_widget)):
                continue

            name = name_widget.text().strip() or f"Tag {row + 1}"
            mode = mode_widget.currentText()
            tag_type = type_widget.currentText()
            address = address_widget.value()
            count = count_widget.value()
            value_format = format_widget.currentText() if hasattr(format_widget, "currentText") else "U16"
            comment = comment_widget.text().strip()
            
            # Skip empty rows - only include rows with a non-zero address or a name that's not the default
            if address == 0 and name == f"Tag {row + 1}":
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

    def add_monitoring_row(self, tag_name, mode, data_type, address, read_value, write_value, comment, timestamp):
        """Add or update a tag row in the monitoring results table."""
        key = (tag_name, data_type, str(address))
        
        # Store read value in cache for Tags monitoring
        if read_value:
            self._monitoring_read_value_cache[key] = read_value
        
        if write_value:
            self._monitoring_write_value_cache[key] = write_value

        cached_write_value = self._monitoring_write_value_cache.get(key, "")
        initial_write_value = write_value if write_value else cached_write_value

        # Use diagnostics results table if main monitoring table doesn't exist
        target_table = None
        if hasattr(self.parent, 'monitoring_table'):
            target_table = self.parent.monitoring_table
        elif hasattr(self.parent, 'diagnostics_results_table'):
            target_table = self.parent.diagnostics_results_table
        
        if target_table is None:
            # For Tags monitoring, update the results window directly
            if self.parent.results_window is not None:
                self.parent.results_window.update_row(
                    tag_name, mode, data_type, address, read_value, write_value, comment, timestamp
                )
            return
            
        row_count = target_table.rowCount()

        self.parent._updating_monitoring_table = True
        try:
            for row in range(row_count):
                name_item = target_table.item(row, 0)
                type_item = target_table.item(row, 2)
                address_item = target_table.item(row, 3)
                if (
                    name_item and type_item and address_item
                    and name_item.text() == tag_name
                    and type_item.text() == data_type
                    and address_item.text() == str(address)
                ):
                    # Don't mutate the row while the user is typing a write value; it cancels the editor.
                    if (
                        target_table.state() == QAbstractItemView.EditingState
                        and target_table.currentRow() == row
                        and target_table.currentColumn() == 5
                    ):
                        return

                    target_table.setItem(row, 1, QTableWidgetItem(mode))
                    target_table.setItem(row, 3, QTableWidgetItem(str(address)))
                    if read_value:
                        target_table.setItem(row, 4, QTableWidgetItem(read_value))

                    # Only set the write column if we have a meaningful value to show.
                    # This avoids stomping on user edits during polling.
                    if write_value:
                        target_table.setItem(row, 5, QTableWidgetItem(write_value))
                    elif initial_write_value and target_table.item(row, 5) is None:
                        target_table.setItem(row, 5, QTableWidgetItem(initial_write_value))

                    target_table.setItem(row, 6, QTableWidgetItem(comment))
                    target_table.setItem(row, 7, QTableWidgetItem(timestamp))
                    if self.parent.results_window is not None:
                        self.parent.results_window.update_row(
                            tag_name, mode, data_type, address, read_value, write_value, comment, timestamp
                        )
                    return

            target_table.insertRow(row_count)
            target_table.setItem(row_count, 0, QTableWidgetItem(tag_name))
            target_table.setItem(row_count, 1, QTableWidgetItem(mode))
            target_table.setItem(row_count, 2, QTableWidgetItem(data_type))
            target_table.setItem(row_count, 3, QTableWidgetItem(str(address)))
            target_table.setItem(row_count, 4, QTableWidgetItem(read_value))
            target_table.setItem(row_count, 5, QTableWidgetItem(initial_write_value))
            target_table.setItem(row_count, 6, QTableWidgetItem(comment))
            target_table.setItem(row_count, 7, QTableWidgetItem(timestamp))
        finally:
            self.parent._updating_monitoring_table = False

        if self.parent.results_window is not None:
            self.parent.results_window.update_row(
                tag_name, mode, data_type, address, read_value, write_value, comment, timestamp
            )

    def get_current_result_values(self):
        """Get current values from monitoring results."""
        values = {}
        # Check if main monitoring table exists
        if hasattr(self.parent, 'monitoring_table'):
            for row in range(self.parent.monitoring_table.rowCount()):
                key = (
                    self.parent._table_item_text(self.parent.monitoring_table, row, 0),
                    self.parent._table_item_text(self.parent.monitoring_table, row, 1),
                    self.parent._table_item_text(self.parent.monitoring_table, row, 2),
                    self.parent._table_item_text(self.parent.monitoring_table, row, 3),
                )
                values[key] = {
                    "read_value": self.parent._table_item_text(self.parent.monitoring_table, row, 4),
                    "write_value": self.parent._table_item_text(self.parent.monitoring_table, row, 5),
                    "timestamp": self.parent._table_item_text(self.parent.monitoring_table, row, 7),
                }
        # Check if diagnostics results table exists
        elif hasattr(self.parent, 'diagnostics_results_table'):
            for row in range(self.parent.diagnostics_results_table.rowCount()):
                key = (
                    self.parent._table_item_text(self.parent.diagnostics_results_table, row, 0),
                    self.parent._table_item_text(self.parent.diagnostics_results_table, row, 1),
                    self.parent._table_item_text(self.parent.diagnostics_results_table, row, 2),
                    self.parent._table_item_text(self.parent.diagnostics_results_table, row, 3),
                )
                values[key] = {
                    "read_value": self.parent._table_item_text(self.parent.diagnostics_results_table, row, 4),
                    "write_value": self.parent._table_item_text(self.parent.diagnostics_results_table, row, 5),
                    "timestamp": self.parent._table_item_text(self.parent.diagnostics_results_table, row, 7),
                }
        else:
            # For Tags monitoring, use the cache
            for key, read_value in self._monitoring_read_value_cache.items():
                write_value = self._monitoring_write_value_cache.get(key, "")
                # Convert key from (tag_name, data_type, address) to (tag_name, mode, data_type, address)
                tag_name, data_type, address = key
                # Find the tag mode from the monitoring tags
                mode = "Read"  # Default to Read since we only cache read values
                for tag in self.get_monitoring_tags():
                    if tag["name"] == tag_name and str(tag["address"]) == address:
                        mode = tag["mode"]
                        break
                
                full_key = (tag_name, mode, data_type, address)
                values[full_key] = {
                    "read_value": read_value,
                    "write_value": write_value,
                    "timestamp": "",  # We don't store timestamps in cache
                }
        
        return values

    def clear_monitoring_results(self):
        """Clear monitoring results table."""
        # Clear caches
        self._monitoring_read_value_cache.clear()
        self._monitoring_write_value_cache.clear()
        
        # Check if diagnostics results table exists
        if hasattr(self.parent, 'diagnostics_results_table'):
            self.parent.diagnostics_results_table.setRowCount(0)
        # Check if main monitoring table exists (for backward compatibility)
        if hasattr(self.parent, 'monitoring_table'):
            self.parent.monitoring_table.setRowCount(0)
        if self.parent.results_window is not None:
            self.parent._sync_results_window()

    def get_tag_key(self, tag):
        """Generate a unique key for a tag."""
        return (tag["name"], tag["type"], str(tag["address"]))

    def read_tag_for_monitoring(self, tag):
        """Read data for a specific tag during monitoring."""
        if tag["type"] == "Coil":
            return self.parent.modbus.read_coils(tag["address"], tag["count"])
        if tag["type"] == "Discrete Input":
            return self.parent.modbus.read_discrete_inputs(tag["address"], tag["count"])
        if tag["type"] == "Holding Register":
            return self.parent.modbus.read_registers(tag["address"], tag["count"])
        return self.parent.modbus.read_input_registers(tag["address"], tag["count"])

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
                    
                    # Display raw data in diagnostics for Tags monitoring
                    self.parent._display_raw_data(f"Tag[{tag['name']}]", value)
                    
                    self.add_monitoring_row(
                        tag["name"], tag["mode"], tag["type"], tag["address"], display_value, "",
                        tag["comment"], timestamp
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

    def get_write_value_cache(self):
        """Get the write value cache."""
        return self._monitoring_write_value_cache

    def update_write_value_cache(self, key, value):
        """Update a value in the write cache."""
        self._monitoring_write_value_cache[key] = value
