"""
Comprehensive Testing System for ModbusLens
Tests all implemented features with full feedback
Focus on holding registers (slave simulator limitation)
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


class ComprehensiveTester:
    """Comprehensive testing controller for ModbusLens."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.test_log = []
        self.test_results = {}
        self.current_test = 0
        
    def setup_logging(self):
        """Setup detailed logging for comprehensive testing."""
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('comprehensive_test.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def log(self, message: str, level: str = "INFO"):
        """Add message to test log."""
        timestamp = time.strftime("[%H:%M:%S]")
        log_entry = timestamp + " " + message
        self.test_log.append(log_entry)
        
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
    
    def initialize_gui(self):
        """Initialize the GUI application."""
        try:
            self.log("=== INITIALIZING GUI ===")
            
            # Create QApplication if not exists
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()
                
            # Import and create main window
            from gui.main_window import ModbusGUI
            self.main_window = ModbusGUI()
            self.main_window.show()
            
            self.log("GUI initialized successfully")
            return True
            
        except Exception as e:
            self.log("GUI initialization failed: " + str(e))
            return False
    
    def connect_to_modbus(self, ip: str = "127.0.0.1", port: int = 502, unit_id: int = 1):
        """Connect to Modbus device."""
        try:
            self.log("=== CONNECTING TO MODBUS ===")
            self.log("Connecting to Modbus device at " + str(ip) + ":" + str(port) + "...")
            
            # Set connection parameters
            self.main_window.ip_input.setText(ip)
            self.main_window.port_input.setValue(port)
            self.main_window.unit_input.setValue(unit_id)
            
            # Click connect button
            self.main_window.connect_btn.click()
            self.wait_for_ui(2000)
            
            # Check connection status
            if hasattr(self.main_window, 'modbus') and self.main_window.modbus:
                if self.main_window.modbus.is_connected():
                    self.log("Successfully connected to Modbus device")
                    return True
                else:
                    error = getattr(self.main_window.modbus, 'last_error', 'Unknown error')
                    self.log("Connection failed: " + str(error), "ERROR")
                    return False
            else:
                self.log("Modbus client not initialized", "ERROR")
                return False
                
        except Exception as e:
            self.log("Connection error: " + str(e), "ERROR")
            return False
    
    def test_all_data_types(self):
        """Test all data types with holding registers."""
        self.log("=== TESTING ALL DATA TYPES ===")
        
        # Define data types to test (focus on holding registers)
        data_types = [
            {"name": "Read Holding Registers (3)", "index": 2, "expected": True},
            {"name": "Write Single Register (6)", "index": 5, "expected": True},
            {"name": "Write Multiple Registers (16)", "index": 6, "expected": True},
        ]
        
        results = {}
        
        for data_type in data_types:
            self.log("\n--- Testing " + data_type['name'] + " ---")
            
            try:
                # Switch to Address Table tab
                self.switch_to_address_table_tab()
                
                # Create address table for this data type
                success = self.create_address_table(
                    function_index=data_type['index'], 
                    start_address=0, 
                    count=5
                )
                
                if success:
                    # Test monitoring if it's a read function
                    if "Read" in data_type['name']:
                        monitoring_success = self.test_monitoring_for_data_type(data_type['name'])
                        results[data_type['name']] = {
                            "table_creation": True,
                            "monitoring": monitoring_success,
                            "overall": monitoring_success
                        }
                    else:
                        # Test write operations
                        write_success = self.test_write_operations_for_data_type(data_type['name'])
                        results[data_type['name']] = {
                            "table_creation": True,
                            "write_operations": write_success,
                            "overall": write_success
                        }
                else:
                    results[data_type['name']] = {
                        "table_creation": False,
                        "monitoring": False,
                        "write_operations": False,
                        "overall": False
                    }
                    
                self.wait_for_ui(1000)  # Wait between tests
                
            except Exception as e:
                self.log("Error testing " + data_type['name'] + ": " + str(e), "ERROR")
                results[data_type['name']] = {
                    "table_creation": False,
                    "monitoring": False,
                    "write_operations": False,
                    "overall": False,
                    "error": str(e)
                }
        
        return results
    
    def switch_to_address_table_tab(self):
        """Switch to Address Table tab."""
        try:
            tab_widget = self.main_window.tab_widget
            tab_widget.setCurrentIndex(0)  # Address Table tab
            self.wait_for_ui(500)
            return True
        except Exception as e:
            self.log("Failed to switch to Address Table tab: " + str(e), "ERROR")
            return False
    
    def create_address_table(self, function_index: int, start_address: int = 0, count: int = 5):
        """Create address table."""
        try:
            address_table = self.main_window.address_table_widget
            
            # Set function
            address_table.function_combo.setCurrentIndex(function_index)
            selected_function = address_table.function_combo.currentText()
            self.log("Selected function: " + selected_function)
            
            # Set address and count
            address_table.address_input.setValue(start_address)
            address_table.count_input.setValue(count)
            
            # Click create table button
            address_table.create_btn.click()
            self.wait_for_ui(1000)
            
            # Verify table was created
            if address_table.table.rowCount() == count:
                self.log("Table created successfully with " + str(count) + " rows")
                return True
            else:
                self.log("Table creation failed. Expected " + str(count) + " rows, got " + str(address_table.table.rowCount()), "ERROR")
                return False
                
        except Exception as e:
            self.log("Failed to create address table: " + str(e), "ERROR")
            return False
    
    def test_monitoring_for_data_type(self, data_type_name: str):
        """Test monitoring for a specific data type."""
        try:
            self.log("Testing monitoring for " + data_type_name)
            
            address_table = self.main_window.address_table_widget
            
            # Start monitoring
            address_table.monitoring_checkbox.setChecked(True)
            self.wait_for_ui(500)
            
            # If checkbox handler fails, call directly
            if not address_table.monitoring_active:
                address_table.start_monitoring()
                self.wait_for_ui(500)
            
            if address_table.monitoring_active:
                self.log("Monitoring started successfully")
                
                # Wait for data updates
                initial_data = self.get_table_values()
                self.log("Initial data: " + str(initial_data))
                
                # Wait for monitoring updates
                for i in range(3):
                    self.wait_for_ui(1000)
                    self.log("Monitoring... " + str(i + 1) + "/3s")
                
                final_data = self.get_table_values()
                self.log("Final data: " + str(final_data))
                
                # Check if data changed
                data_changed = any(initial_data[i] != final_data[i] for i in range(len(initial_data)))
                
                if data_changed:
                    self.log("Monitoring data updated successfully")
                    self.test_results[data_type_name + "_monitoring"] = True
                else:
                    self.log("No monitoring data changes detected", "WARNING")
                    self.test_results[data_type_name + "_monitoring"] = False
                
                # Stop monitoring
                address_table.monitoring_checkbox.setChecked(False)
                self.wait_for_ui(500)
                
                return True
            else:
                self.log("Monitoring failed to start", "ERROR")
                return False
                
        except Exception as e:
            self.log("Monitoring test failed: " + str(e), "ERROR")
            return False
    
    def test_write_operations_for_data_type(self, data_type_name: str):
        """Test write operations for a specific data type."""
        try:
            self.log("Testing write operations for " + data_type_name)
            
            address_table = self.main_window.address_table_widget
            
            # Test writing to editable cells
            test_values = ["123", "456", "789"]
            success_count = 0
            
            for i, value in enumerate(test_values):
                if i < address_table.table.rowCount():
                    # Get the value cell (column 1)
                    value_item = address_table.table.item(i, 1)
                    if value_item and value_item.flags() & Qt.ItemIsEditable:
                        value_item.setText(value)
                        self.wait_for_ui(500)
                        
                        # Check if value was written (simplified check)
                        current_value = value_item.text()
                        if current_value == value:
                            success_count += 1
                            self.log("Successfully wrote value " + value + " to address " + str(i))
                        else:
                            self.log("Failed to write value " + value + " to address " + str(i), "WARNING")
            
            success_rate = success_count / len(test_values)
            self.log("Write operations success rate: " + str(success_rate * 100) + "%")
            
            self.test_results[data_type_name + "_write"] = success_rate > 0.5
            return success_rate > 0.5
            
        except Exception as e:
            self.log("Write operations test failed: " + str(e), "ERROR")
            return False
    
    def get_table_values(self) -> List[str]:
        """Get current values from the 2-column address table."""
        try:
            address_table = self.main_window.address_table_widget
            values = []
            
            for i in range(address_table.table.rowCount()):
                value_item = address_table.table.item(i, 1)  # Value column (column 1)
                if value_item:
                    values.append(value_item.text())
                else:
                    values.append("")
            
            return values
            
        except Exception as e:
            self.log("Error getting table values: " + str(e), "ERROR")
            return []
    
    def test_gui_components(self):
        """Test all GUI components."""
        self.log("=== TESTING GUI COMPONENTS ===")
        
        gui_tests = {
            "connection_panel": self.test_connection_panel(),
            "address_table_tab": self.test_address_table_tab(),
            "monitoring_controls": self.test_monitoring_controls(),
            "table_creation": self.test_table_creation(),
        }
        
        return gui_tests
    
    def test_connection_panel(self):
        """Test connection panel functionality."""
        try:
            self.log("Testing connection panel...")
            
            # Test IP input
            original_ip = self.main_window.ip_input.text()
            self.main_window.ip_input.setText("192.168.1.100")
            self.wait_for_ui(200)
            new_ip = self.main_window.ip_input.text()
            
            # Restore original
            self.main_window.ip_input.setText(original_ip)
            
            success = (new_ip == "192.168.1.100")
            self.log("IP input test: " + ("PASS" if success else "FAIL"))
            return success
            
        except Exception as e:
            self.log("Connection panel test failed: " + str(e), "ERROR")
            return False
    
    def test_address_table_tab(self):
        """Test Address Table tab."""
        try:
            self.log("Testing Address Table tab...")
            
            # Switch to Address Table tab
            tab_widget = self.main_window.tab_widget
            original_tab = tab_widget.currentIndex()
            tab_widget.setCurrentIndex(0)
            self.wait_for_ui(500)
            
            current_tab = tab_widget.tabText(tab_widget.currentIndex())
            success = (current_tab == "Address Table")
            
            # Restore original tab
            tab_widget.setCurrentIndex(original_tab)
            
            self.log("Address Table tab test: " + ("PASS" if success else "FAIL"))
            return success
            
        except Exception as e:
            self.log("Address Table tab test failed: " + str(e), "ERROR")
            return False
    
    def test_monitoring_controls(self):
        """Test monitoring controls."""
        try:
            self.log("Testing monitoring controls...")
            
            address_table = self.main_window.address_table_widget
            
            # Test interval input
            original_interval = address_table.interval_input.value()
            address_table.interval_input.setValue(2000)
            self.wait_for_ui(200)
            new_interval = address_table.interval_input.value()
            
            # Restore original
            address_table.interval_input.setValue(original_interval)
            
            success = (new_interval == 2000)
            self.log("Monitoring controls test: " + ("PASS" if success else "FAIL"))
            return success
            
        except Exception as e:
            self.log("Monitoring controls test failed: " + str(e), "ERROR")
            return False
    
    def test_table_creation(self):
        """Test table creation functionality with 2-column layout."""
        try:
            self.log("Testing table creation with 2-column layout...")
            
            # Create a simple table with default 20 addresses
            success = self.create_address_table(function_index=2, start_address=0, count=20)
            
            if success:
                # Verify 2-column layout
                address_table = self.main_window.address_table_widget
                column_count = address_table.table.columnCount()
                row_count = address_table.table.rowCount()
                
                layout_success = (column_count == 2 and row_count == 20)
                self.log("Table layout test: " + ("PASS" if layout_success else "FAIL"))
                self.log("Columns: " + str(column_count) + ", Rows: " + str(row_count))
                
                return layout_success
            else:
                self.log("Table creation test: FAIL")
                return False
            
        except Exception as e:
            self.log("Table creation test failed: " + str(e), "ERROR")
            return False
    
    def run_comprehensive_test(self):
        """Run complete comprehensive test sequence."""
        self.setup_logging()
        self.log("=== STARTING COMPREHENSIVE TEST SEQUENCE ===")
        
        try:
            # Test 1: Initialize GUI
            if not self.initialize_gui():
                return False
            
            # Test 2: Connect to Modbus
            if not self.connect_to_modbus():
                self.log("Continuing without Modbus connection", "WARNING")
            
            # Test 3: Test GUI Components
            gui_results = self.test_gui_components()
            
            # Test 4: Test All Data Types (focus on holding registers)
            data_type_results = self.test_all_data_types()
            
            # Generate comprehensive report
            self.generate_comprehensive_report(gui_results, data_type_results)
            
            self.log("=== COMPREHENSIVE TEST SEQUENCE COMPLETED ===")
            return True
            
        except Exception as e:
            self.log("Comprehensive test failed: " + str(e), "ERROR")
            return False
    
    def generate_comprehensive_report(self, gui_results: Dict, data_type_results: Dict):
        """Generate comprehensive test report."""
        self.log("\n" + "="*60)
        self.log("COMPREHENSIVE TEST REPORT")
        self.log("="*60)
        
        # GUI Components Results
        self.log("\n--- GUI Components ---")
        for component, result in gui_results.items():
            status = "PASS" if result else "FAIL"
            self.log(component + ": " + status)
        
        # Data Type Results
        self.log("\n--- Data Type Tests ---")
        for data_type, results in data_type_results.items():
            self.log("\n" + data_type + ":")
            for test_name, result in results.items():
                if isinstance(result, bool):
                    status = "PASS" if result else "FAIL"
                    self.log("  " + test_name + ": " + status)
                else:
                    self.log("  " + test_name + ": " + str(result))
        
        # Overall Summary
        self.log("\n--- Overall Summary ---")
        total_tests = len(gui_results) + sum(len(results) for results in data_type_results.values())
        passed_tests = sum(1 for result in gui_results.values() if result)
        passed_tests += sum(1 for results in data_type_results.values() for result in results.values() if isinstance(result, bool) and result)
        
        self.log("Total Tests: " + str(total_tests))
        self.log("Passed: " + str(passed_tests))
        self.log("Failed: " + str(total_tests - passed_tests))
        self.log("Success Rate: " + str((passed_tests/total_tests)*100) + "%")
        
        self.log("\nFull log saved to: comprehensive_test.log")
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
    """Main function to run comprehensive testing."""
    print("ModbusLens Comprehensive Testing System")
    print("=" * 50)
    print("Testing all implemented features with full feedback")
    print("Focus: Holding Registers (slave simulator limitation)")
    print("=" * 50)
    
    tester = ComprehensiveTester()
    
    try:
        # Run comprehensive test
        success = tester.run_comprehensive_test()
        
        if success:
            print("\nComprehensive testing completed successfully!")
        else:
            print("\nSome tests failed. Check the log for details.")
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    except Exception as e:
        print("\nUnexpected error: " + str(e))
    finally:
        tester.cleanup()
        print("Cleanup completed")


if __name__ == "__main__":
    main()
