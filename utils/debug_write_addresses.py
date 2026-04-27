"""
Debug Write Function Address Display
"""

import sys
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def debug_write_addresses():
    """Debug write function address display issues."""
    print("Debugging Write Function Address Display")
    print("=" * 45)
    
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
    
    # Test write functions specifically
    write_test_cases = [
        {"index": 4, "name": "Write Single Coil (5)", "expected_start": "000001"},
        {"index": 5, "name": "Write Single Register (6)", "expected_start": "400001"},
        {"index": 6, "name": "Write Multiple Coils (15)", "expected_start": "000001"},
        {"index": 7, "name": "Write Multiple Registers (16)", "expected_start": "400001"},
    ]
    
    for test_case in write_test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        # Set function
        address_table.function_combo.setCurrentIndex(test_case['index'])
        app.processEvents()
        QTest.qWait(200)
        
        # Get current function text
        current_function = address_table.function_combo.currentText()
        print(f"Current function text: '{current_function}'")
        
        # Test the get_modbus_address method directly
        test_address = 0
        calculated_address = address_table.get_modbus_address(test_address, current_function)
        print(f"get_modbus_address(0, '{current_function}') = '{calculated_address}'")
        print(f"Expected: '{test_case['expected_start']}'")
        
        # Set parameters
        address_table.address_input.setValue(0)
        address_table.count_input.setValue(3)
        app.processEvents()
        QTest.qWait(200)
        
        # Create table
        address_table.create_btn.click()
        app.processEvents()
        QTest.qWait(500)
        
        # Check addresses in table
        addresses = []
        for i in range(min(3, address_table.table.rowCount())):
            addr_item = address_table.table.item(i, 0)
            if addr_item:
                addresses.append(addr_item.text())
        
        print(f"Table addresses: {addresses}")
        
        # Check if they match
        if addresses and addresses[0] == test_case['expected_start']:
            print("PASS: Table shows correct addresses")
        else:
            print(f"FAIL: Table shows {addresses[0] if addresses else 'None'}, expected {test_case['expected_start']}")
    
    print("\n" + "=" * 45)
    print("Debug Complete")
    
    # Cleanup
    main_window.close()
    app.quit()


if __name__ == "__main__":
    debug_write_addresses()
