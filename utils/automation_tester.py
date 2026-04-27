"""
Automated GUI Testing System for ModbusLens
Allows programmatic control of the GUI for automated testing
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


class AutomationTester:
    """Automated controller for ModbusLens GUI testing."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.test_log = []
        self.current_step = 0
        self.test_results = {}
        
    def setup_logging(self):
        """Setup detailed logging for automation."""
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('automation_test.log'),
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
            self.log("Initializing GUI application...")
            
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
        """Automatically connect to Modbus device."""
        try:
            self.log("Connecting to Modbus device at " + str(ip) + ":" + str(port) + "...")
            
            # Set connection parameters
            self.main_window.ip_input.setText(ip)
            self.main_window.port_input.setValue(port)
            self.main_window.unit_input.setValue(unit_id)
            
            # Click connect button
            self.main_window.connect_btn.click()
            self.wait_for_ui(2000)  # Wait for connection
            
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
    
    def switch_to_address_table_tab(self):
        """Switch to Address Table tab."""
        try:
            self.log("Switching to Address Table tab...")
            
            # Find Address Table tab (index 0)
            tab_widget = self.main_window.tab_widget
            tab_widget.setCurrentIndex(0)  # Address Table should be first tab
            
            self.wait_for_ui(500)
            
            current_tab = tab_widget.tabText(tab_widget.currentIndex())
            self.log("Switched to tab: " + current_tab)
            return True
            
        except Exception as e:
            self.log("Failed to switch to Address Table tab: " + str(e), "ERROR")
            return False
    
    def create_address_table(self, function_index: int = 2, start_address: int = 0, count: int = 10):
        """Create address table with specified parameters."""
        try:
            self.log("Creating address table: function=" + str(function_index) + ", start=" + str(start_address) + ", count=" + str(count))
            
            # Get address table widget
            if not hasattr(self.main_window, 'address_table_widget'):
                self.log("Address Table widget not found", "ERROR")
                return False
                
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
    
    def start_monitoring(self, interval_ms: int = 1000):
        """Start monitoring the address table."""
        try:
            self.log("Starting monitoring with " + str(interval_ms) + "ms interval...")
            
            address_table = self.main_window.address_table_widget
            
            # Set monitoring interval
            address_table.interval_input.setValue(interval_ms)
            
            # Enable monitoring checkbox
            address_table.monitoring_checkbox.setChecked(True)
            self.wait_for_ui(500)
            
            # Check if monitoring is active
            if address_table.monitoring_active:
                self.log("Monitoring started successfully")
                return True
            else:
                self.log("Monitoring failed to start", "ERROR")
                return False
                
        except Exception as e:
            self.log("Failed to start monitoring: " + str(e), "ERROR")
            return False
    
    def wait_for_monitoring_updates(self, seconds: int = 5):
        """Wait for monitoring updates and collect data."""
        try:
            self.log("Waiting " + str(seconds) + " seconds for monitoring updates...")
            
            address_table = self.main_window.address_table_widget
            initial_data = []
            
            # Collect initial data
            for i in range(address_table.table.rowCount()):
                value_item = address_table.table.item(i, 1)
                if value_item:
                    initial_data.append(value_item.text())
                else:
                    initial_data.append("")
            
            self.log("Initial data: " + str(initial_data[:3]) + "...")  # Show first 3 values
            
            # Wait for updates
            for second in range(seconds):
                self.wait_for_ui(1000)
                self.log("Monitoring... " + str(second + 1) + "/" + str(seconds) + "s")
            
            # Collect final data
            final_data = []
            for i in range(address_table.table.rowCount()):
                value_item = address_table.table.item(i, 1)
                if value_item:
                    final_data.append(value_item.text())
                else:
                    final_data.append("")
            
            self.log("Final data: " + str(final_data[:3]) + "...")  # Show first 3 values
            
            # Check if data changed
            data_changed = initial_data != final_data
            if data_changed:
                self.log("Monitoring data updated successfully")
                self.test_results['monitoring_updates'] = True
            else:
                self.log("No monitoring data changes detected", "WARNING")
                self.test_results['monitoring_updates'] = False
            
            return final_data
            
        except Exception as e:
            self.log("Error during monitoring wait: " + str(e), "ERROR")
            return None
    
    def stop_monitoring(self):
        """Stop monitoring."""
        try:
            self.log("Stopping monitoring...")
            
            address_table = self.main_window.address_table_widget
            address_table.monitoring_checkbox.setChecked(False)
            self.wait_for_ui(500)
            
            if not address_table.monitoring_active:
                self.log("Monitoring stopped successfully")
                return True
            else:
                self.log("Monitoring failed to stop", "ERROR")
                return False
                
        except Exception as e:
            self.log("Failed to stop monitoring: " + str(e), "ERROR")
            return False
    
    def get_address_table_data(self) -> Dict[str, List[str]]:
        """Get current address table data."""
        try:
            address_table = self.main_window.address_table_widget
            data = {
                'addresses': [],
                'values': []
            }
            
            for i in range(address_table.table.rowCount()):
                # Address column
                addr_item = address_table.table.item(i, 0)
                data['addresses'].append(addr_item.text() if addr_item else "")
                
                # Value column
                value_item = address_table.table.item(i, 1)
                data['values'].append(value_item.text() if value_item else "")
            
            return data
            
        except Exception as e:
            self.log("Error getting table data: " + str(e), "ERROR")
            return {}
    
    def run_automated_test(self):
        """Run complete automated test sequence."""
        self.setup_logging()
        self.log("Starting automated GUI test sequence...")
        
        try:
            # Step 1: Initialize GUI
            if not self.initialize_gui():
                return False
            
            # Step 2: Connect to Modbus (optional - will work in demo mode if not connected)
            connected = self.connect_to_modbus()
            if not connected:
                self.log("Continuing without Modbus connection (demo mode)")
            
            # Step 3: Switch to Address Table tab
            if not self.switch_to_address_table_tab():
                return False
            
            # Step 4: Create address table
            if not self.create_address_table(function_index=2, start_address=0, count=10):
                return False
            
            # Step 5: Start monitoring
            if not self.start_monitoring(interval_ms=1000):
                return False
            
            # Step 6: Wait for monitoring updates
            monitoring_data = self.wait_for_monitoring_updates(seconds=5)
            
            # Step 7: Get final table data
            final_data = self.get_address_table_data()
            self.log("Final table data: " + str(final_data))
            
            # Step 8: Stop monitoring
            self.stop_monitoring()
            
            # Generate test report
            self.generate_test_report()
            
            self.log("Automated test sequence completed successfully!")
            return True
            
        except Exception as e:
            self.log("Automated test failed: " + str(e), "ERROR")
            return False
    
    def generate_test_report(self):
        """Generate detailed test report."""
        self.log("\n" + "="*50)
        self.log("AUTOMATED TEST REPORT")
        self.log("="*50)
        
        for key, value in self.test_results.items():
            status = "PASS" if value else "FAIL"
            self.log(key + ": " + status)
        
        self.log("Total test steps: " + str(len(self.test_log)))
        self.log("Full log saved to: automation_test.log")
        self.log("="*50)
    
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
    """Main function to run automated GUI testing."""
    print("ModbusLens Automated GUI Testing System")
    print("=" * 50)
    
    tester = AutomationTester()
    
    try:
        # Run the automated test
        success = tester.run_automated_test()
        
        if success:
            print("\nAll tests completed successfully!")
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
