"""
Test Monitoring Checkbox State Management
Tests that monitoring checkbox is disabled until successful connection
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def test_monitoring_checkbox_state():
    """Test monitoring checkbox state management."""
    print("Testing Monitoring Checkbox State Management")
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
    initial_checked = address_table.monitoring_checkbox.isChecked()
    print(f"  Monitoring checkbox enabled: {initial_enabled}")
    print(f"  Monitoring checkbox checked: {initial_checked}")
    
    if not initial_enabled and not initial_checked:
        print("  PASS: Checkbox initially disabled and unchecked")
    else:
        print("  FAIL: Checkbox should be initially disabled and unchecked")
    
    # Test 2: During connection - should be disabled
    print("\nTest 2: During Connection")
    
    # Set connection parameters
    main_window.ip_input.setText("127.0.0.1")
    main_window.port_input.setValue(502)
    main_window.unit_input.setValue(1)
    
    # Start connection (this will fail, but we can test the state)
    main_window.connect_btn.click()
    app.processEvents()
    QTest.qWait(500)
    
    during_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  During connection - enabled: {during_enabled}")
    
    if not during_enabled:
        print("  PASS: Checkbox disabled during connection")
    else:
        print("  FAIL: Checkbox should be disabled during connection")
    
    # Wait for connection to fail
    QTest.qWait(2000)
    
    # Test 3: After failed connection - should be disabled
    print("\nTest 3: After Failed Connection")
    after_failed_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  After failed connection - enabled: {after_failed_enabled}")
    
    if not after_failed_enabled:
        print("  PASS: Checkbox disabled after failed connection")
    else:
        print("  FAIL: Checkbox should be disabled after failed connection")
    
    # Test 4: Test connection controls method directly
    print("\nTest 4: Direct Connection Controls Test")
    
    # Test setting connected state (simulating successful connection)
    main_window._set_connection_controls(connected=True)
    app.processEvents()
    QTest.qWait(200)
    
    connected_enabled = address_table.monitoring_checkbox.isEnabled()
    print(f"  When connected - enabled: {connected_enabled}")
    
    if connected_enabled:
        print("  PASS: Checkbox enabled when connected")
    else:
        print("  FAIL: Checkbox should be enabled when connected")
    
    # Test setting disconnected state
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
    
    print("\n" + "=" * 50)
    print("Monitoring Checkbox State Test Complete")
    
    # Cleanup
    main_window.close()
    app.quit()


if __name__ == "__main__":
    test_monitoring_checkbox_state()
