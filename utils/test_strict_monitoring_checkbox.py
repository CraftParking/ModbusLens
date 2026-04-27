"""
Test Strict Monitoring Checkbox Control
Tests that monitoring checkbox is strictly controlled and never enabled during table creation
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def test_strict_monitoring_checkbox():
    """Test strict monitoring checkbox control."""
    print("Testing Strict Monitoring Checkbox Control")
    print("=" * 50)
    
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
    
    # Test 1: Initial state - should be disabled
    print("Test 1: Initial State")
    initial_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  Monitoring checkbox enabled: {initial_enabled}")
    
    if not initial_enabled:
        print("  PASS: Checkbox initially disabled")
    else:
        print("  FAIL: Checkbox should be initially disabled")
    
    # Test 2: During table creation - should be disabled
    print("\nTest 2: During Table Creation")
    
    # Set parameters for table creation
    address_table.function_combo.setCurrentIndex(0)  # Read Coils
    address_table.address_input.setValue(0)
    address_table.count_input.setValue(5)
    app.processEvents()
    QTest.qWait(200)
    
    # Create table
    address_table.create_btn.click()
    app.processEvents()
    QTest.qWait(500)
    
    during_creation_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  During table creation - enabled: {during_creation_enabled}")
    
    if not during_creation_enabled:
        print("  PASS: Checkbox disabled during table creation")
    else:
        print("  FAIL: Checkbox should be disabled during table creation")
    
    # Test 3: After table creation - should still be disabled (no connection)
    print("\nTest 3: After Table Creation (No Connection)")
    
    after_creation_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  After table creation - enabled: {after_creation_enabled}")
    
    if not after_creation_enabled:
        print("  PASS: Checkbox still disabled after table creation (no connection)")
    else:
        print("  FAIL: Checkbox should be disabled after table creation without connection")
    
    # Test 4: Simulate successful connection - should be enabled
    print("\nTest 4: Simulate Successful Connection")
    
    # Simulate connection success
    main_window._set_connection_controls(connected=True)
    app.processEvents()
    QTest.qWait(200)
    
    connected_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  When connected - enabled: {connected_enabled}")
    
    if connected_enabled:
        print("  PASS: Checkbox enabled when connected")
    else:
        print("  FAIL: Checkbox should be enabled when connected")
    
    # Test 5: Simulate disconnection - should be disabled
    print("\nTest 5: Simulate Disconnection")
    
    # Simulate disconnection
    main_window._set_connection_controls(connected=False)
    app.processEvents()
    QTest.qWait(200)
    
    disconnected_enabled = address_table.monitoring_checkbox.isEnabled()
    disconnected_checked = address_table.monitoring_checkbox.isChecked()
    print(f"  When disconnected - enabled: {disconnected_enabled}")
    print(f"  When disconnected - checked: {disconnected_checked}")
    
    if not disconnected_enabled and not disconnected_checked:
        print("  PASS: Checkbox disabled and unchecked when disconnected")
    else:
        print("  FAIL: Checkbox should be disabled and unchecked when disconnected")
    
    # Test 6: Create another table while connected - should remain enabled
    print("\nTest 6: Create Table While Connected")
    
    # Simulate connection again
    main_window._set_connection_controls(connected=True)
    app.processEvents()
    QTest.qWait(200)
    
    # Create another table
    address_table.create_btn.click()
    app.processEvents()
    QTest.qWait(500)
    
    table_while_connected_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  Table creation while connected - enabled: {table_while_connected_enabled}")
    
    if table_while_connected_enabled:
        print("  PASS: Checkbox remains enabled during table creation when connected")
    else:
        print("  FAIL: Checkbox should remain enabled when connected")
    
    print("\n" + "=" * 50)
    print("Strict Monitoring Checkbox Test Complete")
    
    # Summary
    all_tests_pass = True
    
    if initial_enabled:
        print("FAIL: Initial state should be disabled")
        all_tests_pass = False
    
    if during_creation_enabled:
        print("FAIL: Should be disabled during table creation")
        all_tests_pass = False
    
    if after_creation_enabled:
        print("FAIL: Should be disabled after table creation without connection")
        all_tests_pass = False
    
    if not connected_enabled:
        print("FAIL: Should be enabled when connected")
        all_tests_pass = False
    
    if disconnected_enabled or disconnected_checked:
        print("FAIL: Should be disabled and unchecked when disconnected")
        all_tests_pass = False
    
    if not table_while_connected_enabled:
        print("FAIL: Should remain enabled during table creation when connected")
        all_tests_pass = False
    
    if all_tests_pass:
        print("\nSUCCESS: All strict monitoring checkbox tests passed!")
    else:
        print("\nISSUES: Some strict monitoring checkbox tests failed.")
    
    # Cleanup
    main_window.close()
    app.quit()
    
    return all_tests_pass


if __name__ == "__main__":
    test_strict_monitoring_checkbox()
