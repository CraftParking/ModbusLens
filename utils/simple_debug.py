"""
Simple GUI Debugging System for ModbusLens
Tracks all GUI variables and provides detailed feedback
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


class SimpleGUIDebugger:
    """Simple GUI debugging system."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        
    def log(self, message: str):
        """Simple log function."""
        timestamp = time.strftime("[%H:%M:%S]")
        print(timestamp + " " + message)
    
    def wait_for_ui(self, milliseconds: int = 100):
        """Wait for UI to process events."""
        if self.app:
            self.app.processEvents()
            QTest.qWait(milliseconds)
    
    def debug_gui_state(self, step_name: str):
        """Debug current GUI state."""
        try:
            self.log("=== DEBUG STEP: " + step_name + " ===")
            
            if not self.main_window:
                self.log("Main window: None")
                return
            
            # Main window debug
            self.log("Main Window:")
            self.log("  Type: " + str(type(self.main_window)))
            self.log("  Visible: " + str(self.main_window.isVisible()))
            self.log("  Enabled: " + str(self.main_window.isEnabled()))
            self.log("  Title: " + self.main_window.windowTitle())
            
            if hasattr(self.main_window, 'tab_widget'):
                self.log("  Tab Count: " + str(self.main_window.tab_widget.count()))
                self.log("  Current Tab: " + str(self.main_window.tab_widget.currentIndex()))
            
            # Connection panel debug
            if hasattr(self.main_window, 'ip_input'):
                self.log("Connection Panel:")
                self.log("  IP: " + self.main_window.ip_input.text())
                self.log("  Port: " + str(self.main_window.port_input.value()))
                self.log("  Unit ID: " + str(self.main_window.unit_input.value()))
                self.log("  Connect Button Enabled: " + str(self.main_window.connect_btn.isEnabled()))
            
            # Address table debug
            if hasattr(self.main_window, 'address_table_widget') and self.main_window.address_table_widget:
                address_table = self.main_window.address_table_widget
                self.log("Address Table:")
                self.log("  Type: " + str(type(address_table)))
                self.log("  Visible: " + str(address_table.isVisible()))
                self.log("  Table Rows: " + str(address_table.table.rowCount()))
                self.log("  Table Columns: " + str(address_table.table.columnCount()))
                
                if hasattr(address_table, 'current_function'):
                    self.log("  Current Function: " + str(getattr(address_table, 'current_function', 'Not Set')))
                if hasattr(address_table, 'current_start_address'):
                    self.log("  Start Address: " + str(getattr(address_table, 'current_start_address', 'Not Set')))
                if hasattr(address_table, 'current_count'):
                    self.log("  Count: " + str(getattr(address_table, 'current_count', 'Not Set')))
                
                # Controls debug
                if hasattr(address_table, 'function_combo'):
                    self.log("  Function Index: " + str(address_table.function_combo.currentIndex()))
                    self.log("  Function Text: " + address_table.function_combo.currentText())
                    self.log("  Address Value: " + str(address_table.address_input.value()))
                    self.log("  Count Value: " + str(address_table.count_input.value()))
                    self.log("  Create Button Enabled: " + str(address_table.create_btn.isEnabled()))
                    self.log("  Monitoring Checkbox Checked: " + str(address_table.monitoring_checkbox.isChecked()))
                    self.log("  Monitoring Checkbox Enabled: " + str(address_table.monitoring_checkbox.isEnabled()))
                    self.log("  Interval Value: " + str(address_table.interval_input.value()))
                    self.log("  Interval Enabled: " + str(address_table.interval_input.isEnabled()))
                
                # Monitoring debug
                if hasattr(address_table, 'monitoring_active'):
                    self.log("  Monitoring Active: " + str(address_table.monitoring_active))
                if hasattr(address_table, 'monitoring_timer'):
                    self.log("  Timer Active: " + str(address_table.monitoring_timer.isActive()))
                    self.log("  Timer Interval: " + str(address_table.monitoring_timer.interval()))
            
            # Modbus connection debug
            if hasattr(self.main_window, 'modbus') and self.main_window.modbus:
                modbus = self.main_window.modbus
                self.log("Modbus Connection:")
                self.log("  Type: " + str(type(modbus)))
                self.log("  Connected: " + str(modbus.is_connected()))
                self.log("  Last Error: " + str(getattr(modbus, 'last_error', 'None')))
            else:
                self.log("Modbus Connection: Not Available")
            
            self.log("")
            
        except Exception as e:
            self.log("Error in debug_gui_state: " + str(e))
    
    def initialize_gui(self):
        """Initialize GUI for debugging."""
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
            
            self.wait_for_ui(1000)
            self.debug_gui_state("GUI_Initialized")
            
            self.log("GUI initialized successfully")
            return True
            
        except Exception as e:
            self.log("GUI initialization failed: " + str(e))
            return False
    
    def run_debug(self):
        """Run complete debugging."""
        self.log("=== STARTING GUI DEBUGGING ===")
        
        try:
            # Initialize
            if not self.initialize_gui():
                return False
            
            # Final state
            self.debug_gui_state("Final_State")
            
            self.log("=== DEBUGGING COMPLETED ===")
            return True
            
        except Exception as e:
            self.log("Debugging failed: " + str(e))
            return False
    
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
    """Main function to run debugging."""
    print("ModbusLens Simple GUI Debugging System")
    print("=" * 50)
    
    debugger = SimpleGUIDebugger()
    
    try:
        success = debugger.run_debug()
        
        if success:
            print("\nDebugging completed!")
        else:
            print("\nSome issues detected.")
            
    except Exception as e:
        print("\nError: " + str(e))
    finally:
        debugger.cleanup()
        print("Cleanup completed")


if __name__ == "__main__":
    main()
