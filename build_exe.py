"""
Build script for creating ModbusLens EXE using PyInstaller
"""

import PyInstaller.__main__
import os
import sys

def build_exe():
    """Build the ModbusLens EXE file."""
    
    # PyInstaller arguments
    args = [
        'gui_main.py',
        '--name=ModbusLens',
        '--windowed',  # Hide console for cleaner GUI experience
        '--onefile',   # Create single EXE file
        '--icon=assets/icon.ico' if os.path.exists('assets/icon.ico') else '',
        '--add-data=assets:assets',
        '--hidden-import=pymodbus',
        '--hidden-import=pymodbus.client',
        '--hidden-import=PySide6',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=gui.main_window',
        '--hidden-import=gui.widgets.status_indicator',
        '--hidden-import=gui.widgets.monitoring_window',
        '--hidden-import=gui.widgets.address_table',
        '--hidden-import=gui.monitoring.monitoring_manager',
        '--hidden-import=gui.diagnostics.advanced_diagnostics',
        '--hidden-import=gui.diagnostics.diagnostics_dialogs',
        '--hidden-import=gui.network.network_diagnostics',
        '--hidden-import=core.modbus_client',
        '--hidden-import=app_paths',
        '--exclude-module=PySide6.QtWebEngine',
        '--exclude-module=PySide6.QtWebEngineCore',
        '--exclude-module=PySide6.QtWebEngineWidgets',
        '--exclude-module=PySide6.QtWebSockets',
        '--exclude-module=PySide6.QtQuick',
        '--exclude-module=PySide6.QtQml',
        '--exclude-module=PySide6.Qt3D',
        '--exclude-module=PySide6.QtCharts',
        '--exclude-module=PySide6.QtDataVisualization',
        '--exclude-module=PySide6.QtMultimedia',
        '--exclude-module=PySide6.QtNetwork',
        '--exclude-module=PySide6.QtOpenGL',
        '--exclude-module=PySide6.QtPrintSupport',
        '--exclude-module=PySide6.QtSql',
        '--exclude-module=PySide6.QtSvg',
        '--exclude-module=PySide6.QtTest',
        '--exclude-module=PySide6.QtXml',
        '--clean',
        '--noconfirm',
    ]
    
    # Remove empty arguments
    args = [arg for arg in args if arg]
    
    print("Building ModbusLens EXE...")
    print(f"Arguments: {' '.join(args)}")
    
    PyInstaller.__main__.run(args)
    
    print("\nBuild complete!")
    print("EXE file should be in the 'dist' directory.")

if __name__ == '__main__':
    build_exe()
