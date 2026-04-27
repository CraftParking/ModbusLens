"""
Debug Monitoring Checkbox State Management
"""

import sys
import time
from pathlib import Path

# Add gui directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'gui'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest


def debug_monitoring_checkbox():
    """Debug monitoring checkbox state management."""
    print("Debug Monitoring Checkbox State Management")
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
    
    print("Debug Info:")
    print(f"  main_window.hasattr('address_table_widget'): {hasattr(main_window, 'address_table_widget')}")
    print(f"  address_table: {type(address_table)}")
    print(f"  address_table.monitoring_checkbox: {type(address_table.monitoring_checkbox)}")
    print(f"  Initial enabled: {address_table.monitoring_checkbox.isEnabled()}")
    
    # Test direct method call
    print("\nTesting direct _set_connection_controls calls:")
    
    print("  Calling _set_connection_controls(connected=False, connecting=True)")
    main_window._set_connection_controls(connected=False, connecting=True)
    app.processEvents()
    QTest.qWait(200)
    print(f"    After call - enabled: {address_table.monitoring_checkbox.isEnabled()}")
    
    print("  Calling _set_connection_controls(connected=True)")
    main_window._set_connection_controls(connected=True)
    app.processEvents()
    QTest.qWait(200)
    print(f"    After call - enabled: {address_table.monitoring_checkbox.isEnabled()}")
    
    print("  Calling _set_connection_controls(connected=False)")
    main_window._set_connection_controls(connected=False)
    app.processEvents()
    QTest.qWait(200)
    print(f"    After call - enabled: {address_table.monitoring_checkbox.isEnabled()}")
    print(f"    After call - checked: {address_table.monitoring_checkbox.isChecked()}")
    
    # Test connection simulation
    print("\nTesting connection simulation:")
    
    # Set connection parameters
    main_window.ip_input.setText("127.0.0.1")
    main_window.port_input.setValue(502)
    main_window.unit_input.setValue(1)
    
    print("  Before connection - enabled:", address_table.monitoring_checkbox.isEnabled())
    
    # Start connection
    main_window.connect_btn.click()
    app.processEvents()
    QTest.qWait(200)
    
    print("  During connection - enabled:", address_table.monitoring_checkbox.isEnabled())
    
    # Wait for connection to complete
    QTest.qWait(3000)
    app.processEvents()
    
    print("  After connection - enabled:", address_table.monitoring_checkbox.isEnabled())
    print("  After connection - checked:", address_table.monitoring_checkbox.isChecked())
    
    # Cleanup
    main_window.close()
    app.quit()


if __name__ == "__main__":
    debug_monitoring_checkbox()
