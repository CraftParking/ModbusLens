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
        '--windowed',  # Hide console for GUI app
        '--onefile',   # Create single EXE file
        '--icon=assets/icon.ico' if os.path.exists('assets/icon.ico') else '',
        '--add-data=assets:assets',
        '--hidden-import=pymodbus',
        '--hidden-import=pymodbus.client',
        '--hidden-import=pymodbus.register',
        '--hidden-import=PySide6',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=PySide6.QtGui',
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
