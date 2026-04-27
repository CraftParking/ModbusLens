"""
Comprehensive Debugging System for Modbus Address Display Issues
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


class ComprehensiveDebugger:
    """Comprehensive debugging system with anti-looping protection."""
    
    def __init__(self):
        self.app = None
        self.main_window = None
        self.debug_count = 0
        self.max_debug_attempts = 10  # Anti-looping protection
        
    def log(self, message: str):
        """Simple logging with timestamp."""
        timestamp = time.strftime("[%H:%M:%S]")
        print(f"{timestamp} {message}")
        
    def check_looping(self, operation: str) -> bool:
        """Check if we're looping too many times."""
        self.debug_count += 1
        if self.debug_count > self.max_debug_attempts:
            self.log(f"ANTI-LOOP: Too many attempts ({self.debug_count}) on {operation}")
            self.log("PAUSING to prevent infinite loop...")
            return True
        return False
    
    def initialize_gui(self):
        """Initialize GUI for debugging."""
        if self.check_looping("initialize_gui"):
            return False
            
        try:
            self.log("=== INITIALIZING GUI FOR DEBUGGING ===")
            
            if not QApplication.instance():
                self.app = QApplication(sys.argv)
            else:
                self.app = QApplication.instance()
                
            from gui.main_window import ModbusGUI
            self.main_window = ModbusGUI()
            self.main_window.show()
            
            self.wait_for_ui(1000)
            self.log("GUI initialized successfully")
            return True
            
        except Exception as e:
            self.log(f"GUI initialization failed: {e}")
            return False
    
    def wait_for_ui(self, milliseconds: int = 100):
        """Wait for UI to process events."""
        if self.app:
            self.app.processEvents()
            QTest.qWait(milliseconds)
    
    def debug_get_modbus_address_method(self):
        """Debug the get_modbus_address method directly."""
        if self.check_looping("debug_get_modbus_address"):
            return False
            
        try:
            self.log("=== DEBUGGING get_modbus_address METHOD ===")
            
            address_table = self.main_window.address_table_widget
            
            # Test all function names
            test_functions = [
                "Read Coils (1)",
                "Read Discrete Inputs (2)", 
                "Read Holding Registers (3)",
                "Read Input Registers (4)",
                "Write Single Coil (5)",
                "Write Single Register (6)",
                "Write Multiple Coils (15)",
                "Write Multiple Registers (16)"
            ]
            
            for function in test_functions:
                result = address_table.get_modbus_address(0, function)
                self.log(f"Function: '{function}' -> Address: '{result}'")
                
                # Check if result is correct
                if "Coils" in function:
                    expected = "000001"
                elif "Discrete Inputs" in function:
                    expected = "100001"
                elif "Holding Registers" in function:
                    expected = "400001"
                elif "Input Registers" in function:
                    expected = "300001"
                else:
                    expected = "0"
                
                status = "PASS" if result == expected else "FAIL"
                self.log(f"  Expected: {expected} - {status}")
            
            return True
            
        except Exception as e:
            self.log(f"Error debugging get_modbus_address: {e}")
            return False
    
    def debug_function_name_matching(self):
        """Debug why function names are not matching."""
        if self.check_looping("debug_function_name_matching"):
            return False
            
        try:
            self.log("=== DEBUGGING FUNCTION NAME MATCHING ===")
            
            address_table = self.main_window.address_table_widget
            
            # Test problematic functions specifically
            problematic_functions = [
                "Write Single Coil (5)",
                "Write Single Register (6)",
                "Write Multiple Registers (16)"
            ]
            
            for function in problematic_functions:
                self.log(f"Testing function: '{function}'")
                
                # Test each condition separately
                tests = [
                    ("Coils", "Coils" in function),
                    ("Holding Registers", "Holding Registers" in function),
                    ("Discrete Inputs", "Discrete Inputs" in function),
                    ("Input Registers", "Input Registers" in function)
                ]
                
                for test_name, test_result in tests:
                    status = "MATCH" if test_result else "NO MATCH"
                    self.log(f"  '{test_name}' in function: {status}")
                
                # Show what get_modbus_address returns
                result = address_table.get_modbus_address(0, function)
                self.log(f"  Final result: '{result}'")
                self.log("")
            
            return True
            
        except Exception as e:
            self.log(f"Error debugging function name matching: {e}")
            return False
    
    def create_fixed_get_modbus_address(self):
        """Create a fixed version of get_modbus_address method."""
        if self.check_looping("create_fixed_get_modbus_address"):
            return False
            
        try:
            self.log("=== CREATING FIXED get_modbus_address METHOD ===")
            
            # Read the current file
            with open('gui/widgets/address_table.py', 'r') as f:
                content = f.read()
            
            # Find the current get_modbus_address method
            start_marker = "def get_modbus_address(self, address: int, function: str) -> str:"
            end_marker = "def create_address_table(self):"
            
            start_idx = content.find(start_marker)
            end_idx = content.find(end_marker)
            
            if start_idx == -1 or end_idx == -1:
                self.log("Could not find get_modbus_address method in file")
                return False
            
            # Create the fixed method
            fixed_method = '''    def get_modbus_address(self, address: int, function: str) -> str:
        """Get proper Modbus address format based on function type.
        
        Modbus Address Formats:
        - Coils (Read/Write): 000001-065536
        - Discrete Inputs: 100001-165536
        - Holding Registers: 400001-465536
        - Input Registers: 300001-365536
        """
        # Check for Coils (both read and write)
        if "Coils" in function:
            result = f"{address + 1:06d}"  # 000001 format
            return result
        # Check for Holding Registers (both read and write)
        elif "Holding Registers" in function:
            result = f"{400000 + address + 1:06d}"  # 400001 format
            return result
        # Check for Discrete Inputs
        elif "Discrete Inputs" in function:
            result = f"{100000 + address + 1:06d}"  # 100001 format
            return result
        # Check for Input Registers
        elif "Input Registers" in function:
            result = f"{300000 + address + 1:06d}"  # 300001 format
            return result
        else:
            return str(address)  # Fallback to simple address
'''
            
            # Replace the method
            new_content = content[:start_idx] + fixed_method + content[end_idx:]
            
            # Write the fixed file
            with open('gui/widgets/address_table.py', 'w') as f:
                f.write(new_content)
            
            self.log("Fixed get_modbus_address method written to file")
            return True
            
        except Exception as e:
            self.log(f"Error creating fixed method: {e}")
            return False
    
    def test_fixed_addresses(self):
        """Test the fixed address display."""
        if self.check_looping("test_fixed_addresses"):
            return False
            
        try:
            self.log("=== TESTING FIXED ADDRESS DISPLAY ===")
            
            # Re-initialize GUI to pick up changes
            self.main_window.close()
            self.app.quit()
            
            time.sleep(1)
            
            if not self.initialize_gui():
                return False
            
            # Test all functions
            from utils.test_modbus_addresses import test_modbus_addresses
            test_modbus_addresses()
            
            return True
            
        except Exception as e:
            self.log(f"Error testing fixed addresses: {e}")
            return False
    
    def run_comprehensive_debug(self):
        """Run comprehensive debugging sequence."""
        self.log("=== STARTING COMPREHENSIVE DEBUG SEQUENCE ===")
        
        try:
            # Step 1: Initialize GUI
            if not self.initialize_gui():
                return False
            
            # Step 2: Debug get_modbus_address method
            if not self.debug_get_modbus_address_method():
                return False
            
            # Step 3: Debug function name matching
            if not self.debug_function_name_matching():
                return False
            
            # Step 4: Create fixed method
            if not self.create_fixed_get_modbus_address():
                return False
            
            # Step 5: Test fixed addresses
            if not self.test_fixed_addresses():
                return False
            
            self.log("=== COMPREHENSIVE DEBUG COMPLETED ===")
            return True
            
        except Exception as e:
            self.log(f"Comprehensive debug failed: {e}")
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
    """Main function to run comprehensive debugging."""
    print("Comprehensive Modbus Address Debugging System")
    print("=" * 50)
    print("With anti-looping protection")
    print("=" * 50)
    
    debugger = ComprehensiveDebugger()
    
    try:
        success = debugger.run_comprehensive_debug()
        
        if success:
            print("\nDebugging completed successfully!")
        else:
            print("\nDebugging encountered issues. Check the log for details.")
            
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        debugger.cleanup()
        print("Cleanup completed")


if __name__ == "__main__":
    main()
