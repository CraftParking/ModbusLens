"""
Direct Fix for Modbus Address Display Issues
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def fix_modbus_addresses():
    """Direct fix for Modbus address display issues."""
    print("Direct Fix for Modbus Address Display Issues")
    print("=" * 50)
    
    try:
        # Read the current file
        with open('gui/widgets/address_table.py', 'r') as f:
            content = f.read()
        
        # Find the problematic method
        old_method = '''    def get_modbus_address(self, address: int, function: str) -> str:
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
            return str(address)  # Fallback to simple address'''
        
        # Create the fixed method with explicit function name checks
        fixed_method = '''    def get_modbus_address(self, address: int, function: str) -> str:
        """Get proper Modbus address format based on function type.
        
        Modbus Address Formats:
        - Coils (Read/Write): 000001-065536
        - Discrete Inputs: 100001-165536
        - Holding Registers: 400001-465536
        - Input Registers: 300001-365536
        """
        # Explicit function name matching for all 8 functions
        if function == "Read Coils (1)" or function == "Write Single Coil (5)" or function == "Write Multiple Coils (15)":
            return f"{address + 1:06d}"  # 000001 format
        elif function == "Read Holding Registers (3)" or function == "Write Single Register (6)" or function == "Write Multiple Registers (16)":
            return f"{400000 + address + 1:06d}"  # 400001 format
        elif function == "Read Discrete Inputs (2)":
            return f"{100000 + address + 1:06d}"  # 100001 format
        elif function == "Read Input Registers (4)":
            return f"{300000 + address + 1:06d}"  # 300001 format
        else:
            return str(address)  # Fallback to simple address'''
        
        # Replace the method
        if old_method in content:
            new_content = content.replace(old_method, fixed_method)
            
            # Write the fixed file
            with open('gui/widgets/address_table.py', 'w') as f:
                f.write(new_content)
            
            print("Fixed get_modbus_address method with explicit function name matching")
        else:
            print("Could not find the exact method to replace")
            return False
        
        # Test the fix
        print("\n" + "=" * 50)
        print("Testing the fix...")
        
        # Initialize GUI
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        from gui.main_window import ModbusGUI
        main_window = ModbusGUI()
        main_window.show()
        app.processEvents()
        QTest.qWait(1000)
        
        address_table = main_window.address_table_widget
        
        # Test all problematic functions
        test_functions = [
            ("Write Single Coil (5)", "000001"),
            ("Write Single Register (6)", "400001"),
            ("Write Multiple Registers (16)", "400001")
        ]
        
        all_passed = True
        for function, expected in test_functions:
            result = address_table.get_modbus_address(0, function)
            status = "PASS" if result == expected else "FAIL"
            print(f"Function: '{function}' -> '{result}' (expected '{expected}') - {status}")
            if result != expected:
                all_passed = False
        
        # Cleanup
        main_window.close()
        app.quit()
        
        if all_passed:
            print("All tests passed! The fix is working correctly.")
        else:
            print("Some tests failed. The fix needs more work.")
        
        return all_passed
        
    except Exception as e:
        print(f"Error: {e}")
        return False


if __name__ == "__main__":
    fix_modbus_addresses()
