import struct


MAX_TRACKED_RESPONSE_TIMES = 500


class AdvancedDiagnostics:
    """Advanced diagnostics and statistics for Modbus communication troubleshooting."""

    def __init__(self):
        self.advanced_diagnostics = False
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
            'exception_codes': {}
        }

    def create_advanced_diagnostics(self, title, data, modbus_client=None):
        """Create detailed diagnostics information for troubleshooting."""
        lines = []
        
        # Parse title for operation type
        if "Address[" in title:
            address = title.split("[")[1].split("]")[0]
            operation_type = "Modbus Address Monitoring"
        elif "Tag[" in title:
            tag_name = title.split("[")[1].split("]")[0]
            address = f"Tag: {tag_name}"
            operation_type = "Tags Monitoring"
        else:
            address = "Unknown"
            operation_type = "Unknown Operation"
        
        lines.append(f"Operation Type: {operation_type}")
        lines.append(f"Target Address: {address}")
        
        # Data analysis
        if data is None:
            lines.append("\nREAD FAILED")
            lines.append(f"Error: {getattr(modbus_client, 'last_error', 'Unknown error')}")
            self.modbus_stats['failed_requests'] += 1
            
            # Analyze common errors
            error_msg = getattr(modbus_client, 'last_error', '').lower()
            if 'illegal' in error_msg:
                lines.append("\nTROUBLESHOOTING:")
                lines.append("• Check if address exists in device Modbus map")
                lines.append("• Verify device supports this function code")
                lines.append("• Confirm address is within valid range")
            elif 'connection' in error_msg or 'timeout' in error_msg:
                lines.append("\nTROUBLESHOOTING:")
                lines.append("• Check network connectivity")
                lines.append("• Verify device IP address and port")
                lines.append("• Confirm device is powered and responding")
        else:
            lines.append("\nREAD SUCCESSFUL")
            self.modbus_stats['successful_requests'] += 1
            
            # Data type analysis
            if isinstance(data, list):
                lines.append(f"Data Type: Array ({len(data)} elements)")
                lines.append(f"Raw Values: {data}")
                
                # Analyze data patterns
                if all(isinstance(x, bool) for x in data):
                    lines.append("Modbus Type: Coils/Discrete Inputs")
                    lines.append(f"Binary Pattern: {''.join('1' if x else '0' for x in data)}")
                elif all(isinstance(x, int) for x in data):
                    lines.append("Modbus Type: Registers")
                    lines.append(f"Hex Values: {[hex(x) for x in data]}")
                    
                    # Check for common patterns
                    if len(data) >= 2:
                        combined = (data[0] << 16) | data[1]
                        lines.append(f"Combined 32-bit: 0x{combined:08X} ({combined})")
                        
                        # Float interpretation
                        try:
                            float_val = struct.unpack('>f', struct.pack('>I', combined))[0]
                            lines.append(f"Float32: {float_val}")
                        except struct.error:
                            pass
            else:
                lines.append("Data Type: Single Value")
                lines.append(f"Raw Value: {data}")
                if isinstance(data, int):
                    lines.append(f"Hex: 0x{data:04X} ({data})")
                else:
                    lines.append(f"Value: {data}")
        
        # Communication statistics
        lines.append("\nCOMMUNICATION STATS:")
        total = self.modbus_stats['total_requests']
        success = self.modbus_stats['successful_requests']
        failed = self.modbus_stats['failed_requests']
        success_rate = (success / total * 100) if total > 0 else 0
        
        lines.append(f"Total Requests: {total}")
        lines.append(f"Successful: {success} ({success_rate:.1f}%)")
        lines.append(f"Failed: {failed} ({100-success_rate:.1f}%)")
        
        # Recent performance
        if len(self.modbus_stats['response_times']) > 0:
            recent_times = self.modbus_stats['response_times'][-10:]  # Last 10 requests
            avg_time = sum(recent_times) / len(recent_times)
            lines.append(f"Avg Response Time: {avg_time:.2f}ms (last 10 requests)")
        
        return "\n".join(lines)

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
        """Get human-readable description for Modbus exception code."""
        exception_descriptions = {
            0x01: "Illegal Function - Function not supported by device",
            0x02: "Illegal Data Address - Address not valid or not configured",
            0x03: "Illegal Data Value - Value not acceptable for device",
            0x04: "Server Device Failure - Device cannot process request",
            0x05: "Acknowledge - Device accepted but processing will take time",
            0x06: "Server Device Busy - Device busy, try again later",
            0x08: "Memory Parity Error - Extended file area cannot be accessed",
            0x0A: "Gateway Path Unavailable - Gateway target device not responding",
            0x0B: "Gateway Target Failed - Gateway failed to process request"
        }
        return exception_descriptions.get(code, f"Unknown Exception (0x{code:02X})")

    def reset_statistics(self):
        """Reset all Modbus statistics."""
        self.modbus_stats = self._default_stats()

    def toggle_advanced_diagnostics(self, checked):
        """Toggle advanced diagnostics mode."""
        self.advanced_diagnostics = checked

    def show_statistics_dialog(self, modbus_client=None, parent=None):
        """Show statistics dialog."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QHBoxLayout, QPushButton

        stats_dialog = QDialog(parent)
        stats_dialog.setWindowTitle("Modbus Communication Statistics")
        stats_dialog.setGeometry(300, 300, 600, 500)
        
        layout = QVBoxLayout(stats_dialog)
        
        # Title
        title = QLabel("Modbus Communication Statistics")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #333333; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Statistics content
        stats_text = QTextEdit()
        stats_text.setReadOnly(True)
        stats_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                color: #333333;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
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

    def update_request_stats(self, success=True, response_time=None, function_code=None, exception_code=None):
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
