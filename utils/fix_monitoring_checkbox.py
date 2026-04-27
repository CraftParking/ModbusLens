"""
Fix Monitoring Checkbox State Management
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def fix_and_test_monitoring_checkbox():
    """Fix and test monitoring checkbox state management."""
    print("Fix and Test Monitoring Checkbox State Management")
    print("=" * 55)
    
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
    
    # Test 1: Initial state
    print("Test 1: Initial State")
    initial_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  Monitoring checkbox enabled: {initial_enabled}")
    
    # Test 2: Direct connection control test
    print("\nTest 2: Direct Connection Control Test")
    
    # Test disabled state
    main_window._set_connection_controls(connected=False)
    app.processEvents()
    QTest.qWait(200)
    
    disabled_enabled = address_table.monitoring_checkbox.isEnabled()
    disabled_checked = address_table.monitoring_checkbox.isChecked()
    print(f"  Disabled state - enabled: {disabled_enabled}, checked: {disabled_checked}")
    
    # Test enabled state
    main_window._set_connection_controls(connected=True)
    app.processEvents()
    QTest.qWait(200)
    
    enabled_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  Enabled state - enabled: {enabled_enabled}")
    
    # Test back to disabled state
    main_window._set_connection_controls(connected=False)
    app.processEvents()
    QTest.qWait(200)
    
    back_disabled_enabled = address_table.monitoring_checkbox.isEnabled()
    back_disabled_checked = address_table.monitoring_checkbox.isChecked()
    print(f"  Back to disabled - enabled: {back_disabled_enabled}, checked: {back_disabled_checked}")
    
    # Test 3: Connection simulation
    print("\nTest 3: Connection Simulation")
    
    # Set connection parameters
    main_window.ip_input.setText("127.0.0.1")
    main_window.port_input.setValue(502)
    main_window.unit_input.setValue(1)
    
    # Check state before connection
    before_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  Before connection - enabled: {before_enabled}")
    
    # Start connection
    print("  Starting connection...")
    main_window.connect_btn.click()
    app.processEvents()
    QTest.qWait(300)
    
    # Check state during connection
    during_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  During connection - enabled: {during_enabled}")
    
    # Wait for connection to complete (will fail)
    QTest.qWait(3000)
    app.processEvents()
    
    # Check state after connection
    after_enabled = address_table.monitoring_checkbox.isEnabled()
    after_checked = address_table.monitoring_checkbox.isChecked()
    print(f"  After connection - enabled: {after_enabled}, checked: {after_checked}")
    
    # Verify the fix works
    print("\n" + "=" * 55)
    print("Results Summary:")
    
    all_tests_pass = True
    
    if initial_enabled:
        print("  FAIL: Checkbox should be initially disabled")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox initially disabled")
    
    if disabled_enabled or disabled_checked:
        print("  FAIL: Checkbox should be disabled and unchecked")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox properly disabled and unchecked")
    
    if not enabled_enabled:
        print("  FAIL: Checkbox should be enabled when connected")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox enabled when connected")
    
    if back_disabled_enabled or back_disabled_checked:
        print("  FAIL: Checkbox should be disabled and unchecked when disconnected")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox properly disabled when disconnected")
    
    if during_enabled:
        print("  FAIL: Checkbox should be disabled during connection")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox disabled during connection")
    
    if after_enabled or after_checked:
        print("  FAIL: Checkbox should be disabled and unchecked after failed connection")
        all_tests_pass = False
    else:
        print("  PASS: Checkbox properly disabled after failed connection")
    
    if all_tests_pass:
        print("\nSUCCESS: All tests passed! Monitoring checkbox state management is working correctly.")
    else:
        print("\nISSUES: Some tests failed. Monitoring checkbox state management needs fixes.")
    
    # Cleanup
    main_window.close()
    app.quit()
    
    return all_tests_pass


if __name__ == "__main__":
    fix_and_test_monitoring_checkbox()
