MAX_TRACKED_RESPONSE_TIMES = 500

# Single source of truth for exception-code text -- get_exception_code_description's
# one-line label and get_exception_code_details' fuller (name, meaning, causes) tooltip
# both derive from this, so the two can't drift apart the way two separate dicts would.
# Covers every standard code 0x01-0x0B (including 0x07 Negative Acknowledge and 0x09,
# both undefined by the spec but listed for completeness); anything else -- including the
# vendor-specific range some devices use above 0x0B -- falls through to a generic entry
# below rather than a guessed meaning, since the spec doesn't define one.
EXCEPTION_CODE_DETAILS = {
    0x01: (
        "Illegal Function",
        "The function code in the request isn't supported by this device, or the device "
        "is currently in a state where it can't process it.",
        [
            "Device doesn't implement this function code at all",
            "Wrong function selected (e.g. tried to write a read-only register type)",
            "Device is in a mode that disallows this function (e.g. bootloader/config mode)",
        ],
    ),
    0x02: (
        "Illegal Data Address",
        "The register/coil address in the request isn't valid for this device, or isn't "
        "available in the combination requested.",
        [
            "Wrong start address",
            "0-based vs. 1-based addressing mismatch -- check the Tags/Address Table addressing toggle",
            "Wrong register space (Coil vs. Holding Register vs. Input Register vs. Discrete Input)",
            "Address plus count exceeds what the device actually exposes",
            "Device documentation's address numbering differs from the raw wire protocol offset",
        ],
    ),
    0x03: (
        "Illegal Data Value",
        "The value in the request is structurally valid but not acceptable to this "
        "device.",
        [
            "Value out of the device's valid range for this register",
            "Wrong data type/format (e.g. sent unsigned where the device expects signed)",
            "Count field doesn't match the byte count on a multiple-write request",
            "A device-specific validation rule was violated (e.g. must be an even value)",
        ],
    ),
    0x04: (
        "Server Device Failure",
        "An unrecoverable error occurred on the device itself while it was attempting "
        "the requested action.",
        [
            "Device-internal fault",
            "Hardware behind the requested register isn't ready or present (e.g. a disconnected sensor)",
            "Device firmware bug",
        ],
    ),
    0x05: (
        "Acknowledge",
        "The device accepted the request and is processing it, but the action will take "
        "longer than a normal response -- not necessarily a failure.",
        [
            "A long-running device operation is in progress (e.g. a firmware update, calibration cycle)",
            "Some clients should retry rather than treat this as an error",
        ],
    ),
    0x06: (
        "Server Device Busy",
        "The device is currently processing a long-duration command and can't accept "
        "this request right now.",
        [
            "Device is still mid-operation from a previous request",
            "Polling faster than this device can keep up with",
            "Multiple masters/clients contending for the same device",
        ],
    ),
    0x07: (
        "Negative Acknowledge",
        "The device can't perform the requested programming/diagnostic function.",
        [
            "The specific programming/diagnostic function isn't supported in the device's current state",
            "Rarely implemented -- check this device's own documentation for what triggers it",
        ],
    ),
    0x08: (
        "Memory Parity Error",
        "The device detected a parity error reading its extended memory area, usually in "
        "response to a Read/Write File Record request.",
        [
            "Corrupted or faulty extended memory area on the device",
            "Rare -- typically indicates a device hardware fault",
        ],
    ),
    0x0A: (
        "Gateway Path Unavailable",
        "A gateway device couldn't establish a path to the target device -- the gateway "
        "itself is misconfigured or overloaded, not the end device replying.",
        [
            "Wrong Unit ID for a device sitting behind a gateway",
            "Gateway misconfiguration",
            "Gateway's downstream bus/subsystem is overloaded or unreachable",
        ],
    ),
    0x0B: (
        "Gateway Target Device Failed to Respond",
        "A gateway forwarded the request, but the target device behind it never "
        "responded.",
        [
            "Target device is offline or disconnected from the gateway's bus",
            "Wrong Unit ID reaching the wrong device, or no device at all",
            "Serial bus wiring/termination issue behind the gateway",
        ],
    ),
}

_UNKNOWN_EXCEPTION_CAUSES = [
    "Not part of the standard Modbus specification (0x01-0x0B) -- check this device's own documentation",
    "Confirm the request itself was valid before assuming this code has a special vendor meaning",
]


class AdvancedDiagnostics:
    """Statistics for Modbus communication troubleshooting, surfaced via Show Statistics."""

    def __init__(self):
        self.modbus_stats = self._default_stats()

    @staticmethod
    def _default_stats():
        return {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'exception_responses': 0,
            'response_times': [],
            'function_codes': {},
            'exception_codes': {},
            # Coarse failure-cause breakdown (see ModbusClient._set_error): "connection",
            # "timeout", "device_exception", "other". Device-wide, matching the granularity
            # ModbusTools itself tracks at (mbClientDevice::Statistics is per-device, not
            # per-tag) -- deliberately not broken out per-tag on top of this.
            'error_categories': {},
        }

    def generate_statistics_report(self, modbus_client=None):
        """Generate a comprehensive statistics report."""
        lines = []
        
        # Overall statistics
        total = self.modbus_stats['total_requests']
        success = self.modbus_stats['successful_requests']
        failed = self.modbus_stats['failed_requests']
        success_rate = (success / total * 100) if total > 0 else 0
        
        lines.append("OVERALL COMMUNICATION STATISTICS")
        lines.append("=" * 50)
        lines.append(f"Total Requests: {total}")
        lines.append(f"Successful: {success} ({success_rate:.1f}%)")
        lines.append(f"Failed: {failed} ({100-success_rate:.1f}%)")
        lines.append(f"Exception Responses: {self.modbus_stats['exception_responses']}")
        
        # Performance metrics
        if len(self.modbus_stats['response_times']) > 0:
            response_times = self.modbus_stats['response_times']
            avg_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            
            lines.append("\nPERFORMANCE METRICS")
            lines.append("=" * 50)
            lines.append(f"Average Response Time: {avg_time:.2f}ms")
            lines.append(f"Minimum Response Time: {min_time:.2f}ms")
            lines.append(f"Maximum Response Time: {max_time:.2f}ms")
            lines.append(f"Total Requests Tracked: {len(response_times)}")
            
            # Recent performance
            if len(response_times) >= 10:
                recent = response_times[-10:]
                recent_avg = sum(recent) / len(recent)
                lines.append(f"Recent Avg (last 10): {recent_avg:.2f}ms")
        
        # Function code analysis
        if self.modbus_stats['function_codes']:
            lines.append("\nFUNCTION CODE USAGE")
            lines.append("=" * 50)
            for func_code, count in sorted(self.modbus_stats['function_codes'].items()):
                func_name = self.get_function_code_name(func_code)
                percentage = (count / total * 100) if total > 0 else 0
                lines.append(f"{func_name} (0x{func_code:02X}): {count} requests ({percentage:.1f}%)")
        
        # Exception code analysis
        if self.modbus_stats['exception_codes']:
            lines.append("\nEXCEPTION CODE ANALYSIS")
            lines.append("=" * 50)
            for exc_code, count in sorted(self.modbus_stats['exception_codes'].items()):
                exc_desc = self.get_exception_code_description(exc_code)
                lines.append(f"Exception 0x{exc_code:02X} ({exc_desc}): {count} occurrences")

        # Failure-cause breakdown (timeout vs. connection vs. device-returned exception, etc.)
        if self.modbus_stats['error_categories']:
            lines.append("\nFAILURE CAUSE BREAKDOWN")
            lines.append("=" * 50)
            for category, count in sorted(self.modbus_stats['error_categories'].items(), key=lambda kv: -kv[1]):
                lines.append(f"{self.get_error_category_label(category)}: {count}")
        
        # Connection status
        lines.append("\nCONNECTION STATUS")
        lines.append("=" * 50)
        if modbus_client and modbus_client.is_connected():
            lines.append(f"Status: Connected to {modbus_client.ip}:{modbus_client.port}")
            lines.append(f"Unit ID: {modbus_client.unit_id}")
            lines.append(f"Timeout: {modbus_client.timeout}s")
        else:
            lines.append("Status: Not connected")
        
        # Recommendations
        lines.append("\nRECOMMENDATIONS")
        lines.append("=" * 50)
        
        if success_rate < 90:
            lines.append("Success rate is below 90%. Check:")
            lines.append("   • Network connectivity")
            lines.append("   • Device availability")
            lines.append("   • Address configuration")
        
        if len(self.modbus_stats['response_times']) > 0:
            avg_time = sum(self.modbus_stats['response_times']) / len(self.modbus_stats['response_times'])
            if avg_time > 500:
                lines.append("Average response time is high. Consider:")
                lines.append("   • Network latency optimization")
                lines.append("   • Device performance tuning")
                lines.append("   • Reducing request frequency")
        
        if self.modbus_stats['exception_codes']:
            most_common = max(self.modbus_stats['exception_codes'].items(), key=lambda x: x[1])
            lines.append(f"Most common exception: 0x{most_common[0]:02X}")
            lines.append(f"   {self.get_exception_code_description(most_common[0])}")
        
        if success_rate >= 90 and (not self.modbus_stats['response_times'] or sum(self.modbus_stats['response_times']) / len(self.modbus_stats['response_times']) <= 500):
            lines.append("Communication is performing well!")
        
        return "\n".join(lines)

    def get_function_code_name(self, code):
        """Get human-readable name for Modbus function code."""
        function_names = {
            0x01: "Read Coils",
            0x02: "Read Discrete Inputs",
            0x03: "Read Holding Registers",
            0x04: "Read Input Registers",
            0x05: "Write Single Coil",
            0x06: "Write Single Register",
            0x0F: "Write Multiple Coils",
            0x10: "Write Multiple Registers"
        }
        return function_names.get(code, f"Unknown Function (0x{code:02X})")

    def get_exception_code_description(self, code):
        """One-line 'Name - meaning' label, e.g. for the Statistics report and the Raw
        Data tab's plain-text Exception cell. See get_exception_code_details for the
        fuller (name, meaning, causes) breakdown this derives from."""
        details = self.get_exception_code_details(code)
        return f"{details['name']} - {details['meaning']}"

    def get_exception_code_details(self, code):
        """Full explainer for a Modbus exception code: {name, meaning, causes}. Powers the
        Raw Data tab's Exception column tooltip (see DiagnosticsDialogs.add_raw_data_row) --
        get_exception_code_description above derives its own shorter one-line text from
        this same data instead of a separate dict, so the two can't drift apart."""
        entry = EXCEPTION_CODE_DETAILS.get(code)
        if entry is None:
            return {
                "name": f"Unknown/Vendor-Specific Exception (0x{code:02X})",
                "meaning": "This exception code isn't defined by the standard Modbus specification.",
                "causes": _UNKNOWN_EXCEPTION_CAUSES,
            }
        name, meaning, causes = entry
        return {"name": name, "meaning": meaning, "causes": causes}

    def get_error_category_label(self, category):
        """Human-readable label for a ModbusClient._set_error category."""
        labels = {
            'connection': "Connection (not connected / socket-level failure)",
            'timeout': "Timeout / no valid response (includes unparseable/garbled frames -- "
                       "pymodbus doesn't distinguish these from a plain timeout)",
            'device_exception': "Device-returned exception (see Exception Code Analysis above)",
            'rejected': "Rejected locally (e.g. a write bound violation, never reached the wire)",
            'other': "Other",
        }
        return labels.get(category, category)

    def reset_statistics(self):
        """Reset all Modbus statistics."""
        self.modbus_stats = self._default_stats()

    def show_statistics_dialog(self, modbus_client=None, parent=None):
        """Show statistics dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton

        stats_dialog = QDialog(parent)
        stats_dialog.setWindowTitle("Modbus Communication Statistics")
        stats_dialog.setGeometry(300, 300, 600, 500)
        
        layout = QVBoxLayout(stats_dialog)

        c = parent._colors() if parent is not None and hasattr(parent, "_colors") else {}

        # Title
        title = QLabel("Modbus Communication Statistics")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {c.get('text_secondary', '#333333')}; margin-bottom: 10px;")
        layout.addWidget(title)

        # Statistics content
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {c.get("surface_alt2", "#f8f9fa")};
                color: {c.get("text_secondary", "#333333")};
                border: 1px solid {c.get("border", "#dee2e6")};
                border-radius: 6px;
                padding: 10px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }}
        """)
        
        # Generate statistics report
        stats_report = self.generate_statistics_report(modbus_client)
        stats_text.setPlainText(stats_report)
        layout.addWidget(stats_text)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        def reset_and_refresh():
            self.reset_statistics()
            stats_text.setPlainText(self.generate_statistics_report(modbus_client))

        reset_btn = QPushButton("Reset Statistics")
        reset_btn.clicked.connect(reset_and_refresh)
        button_layout.addWidget(reset_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(stats_dialog.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        stats_dialog.exec()

    def update_request_stats(self, success=True, response_time=None, function_code=None, exception_code=None,
                              error_category=None):
        """Update statistics for a request."""
        self.modbus_stats['total_requests'] += 1
        if success:
            self.modbus_stats['successful_requests'] += 1
        else:
            self.modbus_stats['failed_requests'] += 1

        if response_time is not None:
            self.modbus_stats['response_times'].append(response_time)
            if len(self.modbus_stats['response_times']) > MAX_TRACKED_RESPONSE_TIMES:
                self.modbus_stats['response_times'] = self.modbus_stats['response_times'][-MAX_TRACKED_RESPONSE_TIMES:]

        if function_code is not None:
            self.modbus_stats['function_codes'][function_code] = self.modbus_stats['function_codes'].get(function_code, 0) + 1

        if exception_code is not None:
            self.modbus_stats['exception_responses'] += 1
            self.modbus_stats['exception_codes'][exception_code] = self.modbus_stats['exception_codes'].get(exception_code, 0) + 1

        if not success and error_category:
            categories = self.modbus_stats['error_categories']
            categories[error_category] = categories.get(error_category, 0) + 1
