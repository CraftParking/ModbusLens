"""
GUI Debugging System for ModbusLens
Tracks all GUI variables and provides detailed feedback for debugging
"""

import sys
import time
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest


class GUIDebugger:
    """Comprehensive GUI debugging system."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.debug_log = []
        self.variable_snapshots = {}
        self.current_step = 0
        
    def setup_logging(self):
        """Setup detailed logging for debugging."""
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('gui_debug.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def log(self, message: str, level: str = "INFO"):
        """Add message to debug log."""
        timestamp = time.strftime("[%H:%M:%S.%f]")[:-3]
        log_entry = timestamp + " " + message
        self.debug_log.append(log_entry)
        
        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)
            
        print(log_entry)
    
    def wait_for_ui(self, milliseconds: int = 100):
        """Wait for UI to process events."""
        if self.app:
            self.app.processEvents()
            QTest.qWait(milliseconds)
    
    def capture_variable_snapshot(self, context: str):
        """Capture snapshot of all GUI variables."""
        try:
            snapshot = {
                "context": context,
                "timestamp": time.time(),
                "main_window": self.debug_main_window(),
                "address_table": self.debug_address_table(),
                "monitoring": self.debug_monitoring(),
                "connection": self.debug_connection()
            }
            
            self.variable_snapshots[context] = snapshot
            self.log("=== VARIABLE SNAPSHOT: " + context + " ===")
            self.log("Main Window: " + str(snapshot['main_window']))
            self.log("Address Table: " + str(snapshot['address_table']))
            self.log("Monitoring: " + str(snapshot['monitoring']))
            self.log("Connection: " + str(snapshot['connection']))
            
        except Exception as e:
            self.log("Error capturing snapshot: " + str(e), "ERROR")
    
    def debug_main_window(self) -> Dict[str, Any]:
        """Debug main window variables."""
        try:
            if not self.main_window:
                return {"status": "None"}
                
            debug_info = {
                "type": str(type(self.main_window)),
                "visible": self.main_window.isVisible(),
                "enabled": self.main_window.isEnabled(),
                "window_title": self.main_window.windowTitle(),
                "window_size": str(self.main_window.width()) + "x" + str(self.main_window.height()),
                "tab_count": self.main_window.tab_widget.count() if hasattr(self.main_window, 'tab_widget') else 0,
                "current_tab": self.main_window.tab_widget.currentIndex() if hasattr(self.main_window, 'tab_widget') else -1
            }
            
            # Connection panel debug
            if hasattr(self.main_window, 'ip_input'):
                debug_info["connection_panel"] = {
                    "ip": self.main_window.ip_input.text(),
                    "port": self.main_window.port_input.value(),
                    "unit_id": self.main_window.unit_input.value(),
                    "connect_btn_enabled": self.main_window.connect_btn.isEnabled(),
                    "connect_btn_text": self.main_window.connect_btn.text()
                }
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e)}
    
    def debug_address_table(self) -> Dict[str, Any]:
        """Debug address table variables."""
        try:
            if not hasattr(self.main_window, 'address_table_widget') or not self.main_window.address_table_widget:
                return {"status": "Not Available"}
                
            address_table = self.main_window.address_table_widget
            
            debug_info = {
                "type": str(type(address_table)),
                "visible": address_table.isVisible(),
                "enabled": address_table.isEnabled(),
                "table_rows": address_table.table.rowCount(),
                "table_columns": address_table.table.columnCount(),
                "current_function": getattr(address_table, 'current_function', 'Not Set'),
                "current_start_address": getattr(address_table, 'current_start_address', 'Not Set'),
                "current_count": getattr(address_table, 'current_count', 'Not Set'),
                "monitoring_active": getattr(address_table, 'monitoring_active', False),
                "monitoring_timer_active": address_table.monitoring_timer.isActive() if hasattr(address_table, 'monitoring_timer') else False
            }
            
            # Control debug
            if hasattr(address_table, 'function_combo'):
                debug_info["controls"] = {
                    "function_index": address_table.function_combo.currentIndex(),
                    "function_text": address_table.function_combo.currentText(),
                    "address_value": address_table.address_input.value(),
                    "count_value": address_table.count_input.value(),
                    "create_btn_enabled": address_table.create_btn.isEnabled(),
                    "monitoring_checkbox_checked": address_table.monitoring_checkbox.isChecked(),
                    "monitoring_checkbox_enabled": address_table.monitoring_checkbox.isEnabled(),
                    "interval_value": address_table.interval_input.value(),
                    "interval_enabled": address_table.interval_input.isEnabled()
                }
            
            # Table data debug
            if hasattr(address_table, 'table'):
                table_data = []
                for i in range(min(5, address_table.table.rowCount())):  # First 5 rows only
                    row_data = {}
                    for j in range(address_table.table.columnCount()):
                        item = address_table.table.item(i, j)
                        row_data["col_" + str(j)] = item.text() if item else ""
                        row_data["col_" + str(j) + "_editable"] = bool(item and item.flags() & Qt.ItemIsEditable) if item else False
                    table_data.append(row_data)
                debug_info["sample_table_data"] = table_data
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e)}
    
    def debug_monitoring(self) -> Dict[str, Any]:
        """Debug monitoring system variables."""
        try:
            if not hasattr(self.main_window, 'address_table_widget') or not self.main_window.address_table_widget:
                return {"status": "No Address Table"}
                
            address_table = self.main_window.address_table_widget
            
            debug_info = {
                "monitoring_active": getattr(address_table, 'monitoring_active', False),
                "timer_active": address_table.monitoring_timer.isActive() if hasattr(address_table, 'monitoring_timer') else False,
                "timer_interval": address_table.monitoring_timer.interval() if hasattr(address_table, 'monitoring_timer') else 0,
                "current_data_size": len(getattr(address_table, 'current_data', {})),
                "log_output_length": len(address_table.log_output.toPlainText()) if hasattr(address_table, 'log_output') else 0
            }
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e)}
    
    def debug_connection(self) -> Dict[str, Any]:
        """Debug Modbus connection variables."""
        try:
            if not hasattr(self.main_window, 'modbus') or not self.main_window.modbus:
                return {"status": "No Modbus Client"}
                
            modbus = self.main_window.modbus
            
            debug_info = {
                "type": str(type(modbus)),
                "connected": modbus.is_connected(),
                "last_error": getattr(modbus, 'last_error', None),
                "socket": getattr(modbus, 'socket', None),
                "timeout": getattr(modbus, 'timeout', None)
            }
            
            return debug_info
            
        except Exception as e:
            return {"error": str(e)}
    
    def initialize_gui(self):
        """Initialize GUI for debugging."""
        try:
            self.log("=== INITIALIZING GUI FOR DEBUGGING ===")
            
            # Create QApplication if not exists
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()
                
            # Import and create main window
            from gui.main_window import ModbusGUI
            self.main_window = ModbusGUI()
            self.main_window.show()
            
            self.wait_for_ui(1000)
            self.capture_variable_snapshot("GUI_Initialized")
            
            self.log("GUI initialized successfully for debugging")
            return True
            
        except Exception as e:
            self.log("GUI initialization failed: " + str(e), "ERROR")
            return False
    
    def test_address_table_creation(self):
        """Test address table creation with debugging."""
        try:
            self.log("=== TESTING ADDRESS TABLE CREATION ===")
            
            # Switch to Address Table tab
            self.main_window.tab_widget.setCurrentIndex(0)
            self.wait_for_ui(500)
            self.capture_variable_snapshot("Tab_Switched")
            
            # Test table creation
            address_table = self.main_window.address_table_widget
            
            # Set parameters
            address_table.function_combo.setCurrentIndex(2)  # Read Holding Registers
            address_table.address_input.setValue(0)
            address_table.count_input.setValue(20)
            self.wait_for_ui(500)
            self.capture_variable_snapshot("Parameters_Set")
            
            # Create table
            address_table.create_btn.click()
            self.wait_for_ui(1000)
            self.capture_variable_snapshot("Table_Created")
            
            # Verify table
            if address_table.table.rowCount() == 20:
                self.log("Table creation successful")
                return True
            else:
                self.log("Table creation failed: expected 20 rows, got " + str(address_table.table.rowCount()), "ERROR")
                return False
                
        except Exception as e:
            self.log("Address table creation test failed: " + str(e), "ERROR")
            return False
    
    def test_monitoring_functionality(self):
        """Test monitoring functionality with debugging."""
        try:
            self.log("=== TESTING MONITORING FUNCTIONALITY ===")
            
            address_table = self.main_window.address_table_widget
            
            # Test checkbox click
            self.log("Testing checkbox click...")
            address_table.monitoring_checkbox.setChecked(True)
            self.wait_for_ui(500)
            self.capture_variable_snapshot("Checkbox_Checked")
            
            # Check if monitoring started
            if address_table.monitoring_active:
                self.log("Monitoring started successfully")
            else:
                self.log("Monitoring failed to start - trying direct call", "WARNING")
                address_table.start_monitoring()
                self.wait_for_ui(500)
                self.capture_variable_snapshot("Direct_Call_Made")
                
                if address_table.monitoring_active:
                    self.log("Monitoring started via direct call")
                else:
                    self.log("Monitoring failed to start completely", "ERROR")
                    return False
            
            # Wait for monitoring updates
            self.log("Waiting for monitoring updates...")
            for i in range(3):
                self.wait_for_ui(1000)
                self.capture_variable_snapshot("Monitoring_Update_" + str(i+1))
            
            # Stop monitoring
            address_table.monitoring_checkbox.setChecked(False)
            self.wait_for_ui(500)
            self.capture_variable_snapshot("Monitoring_Stopped")
            
            return True
            
        except Exception as e:
            self.log("Monitoring functionality test failed: " + str(e), "ERROR")
            return False
    
    def test_modbus_connection(self):
        """Test Modbus connection with debugging."""
        try:
            self.log("=== TESTING MODBUS CONNECTION ===")
            
            # Set connection parameters
            self.main_window.ip_input.setText("127.0.0.1")
            self.main_window.port_input.setValue(502)
            self.main_window.unit_input.setValue(1)
            self.wait_for_ui(500)
            self.capture_variable_snapshot("Connection_Parameters_Set")
            
            # Connect
            self.main_window.connect_btn.click()
            self.wait_for_ui(2000)
            self.capture_variable_snapshot("Connection_Attempted")
            
            # Check connection status
            if hasattr(self.main_window, 'modbus') and self.main_window.modbus:
                if self.main_window.modbus.is_connected():
                    self.log("Modbus connection successful")
                    return True
                else:
                    error = getattr(self.main_window.modbus, 'last_error', 'Unknown error')
                    self.log("Modbus connection failed: " + str(error), "WARNING")
                    return False
            else:
                self.log("Modbus client not initialized", "ERROR")
                return False
                
        except Exception as e:
            self.log("Modbus connection test failed: " + str(e), "ERROR")
            return False
    
    def run_comprehensive_debug(self):
        """Run comprehensive GUI debugging."""
        self.setup_logging()
        self.log("=== STARTING COMPREHENSIVE GUI DEBUGGING ===")
        
        try:
            # Initialize GUI
            if not self.initialize_gui():
                return False
            
            # Test Modbus connection
            connection_result = self.test_modbus_connection()
            
            # Test address table creation
            table_result = self.test_address_table_creation()
            
            # Test monitoring functionality
            monitoring_result = self.test_monitoring_functionality()
            
            # Generate final report
            self.generate_debug_report(connection_result, table_result, monitoring_result)
            
            self.log("=== COMPREHENSIVE GUI DEBUGGING COMPLETED ===")
            return True
            
        except Exception as e:
            self.log("Comprehensive debugging failed: " + str(e), "ERROR")
            return False
    
    def generate_debug_report(self, connection_result: bool, table_result: bool, monitoring_result: bool):
        """Generate comprehensive debug report."""
        self.log("\n" + "="*60)
        self.log("COMPREHENSIVE GUI DEBUG REPORT")
        self.log("="*60)
        
        # Test Results
        self.log("Modbus Connection: " + ("PASS" if connection_result else "FAIL"))
        self.log("Table Creation: " + ("PASS" if table_result else "FAIL"))
        self.log("Monitoring Functionality: " + ("PASS" if monitoring_result else "FAIL"))
        
        # Variable Snapshots Summary
        self.log("\nTotal Variable Snapshots: " + str(len(self.variable_snapshots)))
        for context in self.variable_snapshots.keys():
            self.log("  - " + context)
        
        # Final State
        if "Monitoring_Stopped" in self.variable_snapshots:
            final_state = self.variable_snapshots["Monitoring_Stopped"]
            self.log("\nFinal State Summary:")
            self.log("  Table Rows: " + str(final_state['address_table'].get('table_rows', 'Unknown')))
            self.log("  Monitoring Active: " + str(final_state['monitoring'].get('monitoring_active', 'Unknown')))
            self.log("  Connection Status: " + str(final_state['connection'].get('connected', 'Unknown')))
        
        self.log("\nFull debug log saved to: gui_debug.log")
        self.log("="*60)
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if self.main_window:
                self.main_window.close()
            if self.app:
                self.app.quit()
        except:
            pass


def main():
    """Main function to run GUI debugging."""
    print("ModbusLens GUI Debugging System")
    print("=" * 50)
    print("Tracking all GUI variables and providing detailed feedback")
    print("=" * 50)
    
    debugger = GUIDebugger()
    
    try:
        # Run comprehensive debugging
        success = debugger.run_comprehensive_debug()
        
        if success:
            print("\nGUI debugging completed successfully!")
        else:
            print("\nSome issues detected. Check the debug log for details.")
            
    except KeyboardInterrupt:
        print("\nDebugging interrupted by user")
    except Exception as e:
        print("\nUnexpected error: " + str(e))
    finally:
        debugger.cleanup()
        print("Cleanup completed")


if __name__ == "__main__":
    main()
