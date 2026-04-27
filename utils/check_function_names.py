"""
Check exact function names in combo box
"""

import sys
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def check_function_names():
    """Check exact function names in combo box."""
    print("Checking Function Names in Combo Box")
    print("=" * 40)
    
    # Create QApplication
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()
    
    # Import and create main window
    from gui.main_window import ModbusGUI
    main_window = ModbusGUI()
    main_window.show()
    app.processEvents()
    QTest.qWait(1000)
    
    address_table = main_window.address_table_widget
    
    # Check all function names
    for i in range(address_table.function_combo.count()):
        function_text = address_table.function_combo.itemText(i)
        print(f"Index {i}: '{function_text}'")
        
        # Test get_modbus_address for each function
        test_address = address_table.get_modbus_address(0, function_text)
        print(f"  get_modbus_address(0, '{function_text}') = '{test_address}'")
    
    print("\n" + "=" * 40)
    print("Function Name Check Complete")
    
    # Cleanup
    main_window.close()
    app.quit()


if __name__ == "__main__":
    check_function_names()
