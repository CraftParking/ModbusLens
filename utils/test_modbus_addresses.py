"""
Test Modbus Address Display
Tests that proper Modbus addresses are displayed in the table
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def test_modbus_addresses():
    """Test Modbus address display for all function types."""
    print("Testing Modbus Address Display")
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
    
    # Test data: function index -> expected address format
    test_cases = [
        {"index": 0, "name": "Read Coils (1)", "expected_start": "000001"},
        {"index": 1, "name": "Read Discrete Inputs (2)", "expected_start": "100001"},
        {"index": 2, "name": "Read Holding Registers (3)", "expected_start": "400001"},
        {"index": 3, "name": "Read Input Registers (4)", "expected_start": "300001"},
        {"index": 4, "name": "Write Single Coil (5)", "expected_start": "000001"},
        {"index": 5, "name": "Write Single Register (6)", "expected_start": "400001"},
        {"index": 6, "name": "Write Multiple Coils (15)", "expected_start": "000001"},
        {"index": 7, "name": "Write Multiple Registers (16)", "expected_start": "400001"},
    ]
    
    address_table = main_window.address_table_widget
    
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        
        # Set function
        address_table.function_combo.setCurrentIndex(test_case['index'])
        app.processEvents()
        QTest.qWait(200)
        
        # Set parameters
        address_table.address_input.setValue(0)
        address_table.count_input.setValue(5)
        app.processEvents()
        QTest.qWait(200)
        
        # Create table
        address_table.create_btn.click()
        app.processEvents()
        QTest.qWait(500)
        
        # Check addresses
        addresses = []
        for i in range(min(3, address_table.table.rowCount())):  # Check first 3 rows
            addr_item = address_table.table.item(i, 0)
            if addr_item:
                addresses.append(addr_item.text())
        
        # Verify first address
        if addresses and addresses[0] == test_case['expected_start']:
            print(f"PASS: {addresses[0]} (expected {test_case['expected_start']})")
        else:
            print(f"FAIL: Got {addresses[0] if addresses else 'None'}, expected {test_case['expected_start']}")
        
        # Show first few addresses
        print(f"   Addresses: {addresses}")
    
    print("\n" + "=" * 40)
    print("Modbus Address Display Test Complete")
    
    # Cleanup
    main_window.close()
    app.quit()


if __name__ == "__main__":
    test_modbus_addresses()
