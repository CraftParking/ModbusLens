#!/usr/bin/env python3
"""
ModbusLens GUI Entry Point
"""

import sys
import os
import logging

# Add the directory containing this script to Python path
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    application_path = os.path.dirname(sys.executable)
else:
    # Running as script
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, application_path)

logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')

try:
    from gui.main_window import main as gui_main
    gui_main()
except ImportError as e:
    print(f"GUI dependencies not available: {e}")
    print("Make sure PySide6 is installed: pip install PySide6")
    print(f"Current path: {sys.path}")
    print(f"Application path: {application_path}")
    input("Press Enter to exit...")
    sys.exit(1)
except SystemExit:
    # GUI main() calls sys.exit(), so this is expected
    pass
except Exception as e:
    print(f"GUI failed to start: {e}")
    print("\nTroubleshooting:")
    print("- Make sure you're running on a system with graphical display")
    print("- If in an IDE, try running from command line")
    print("- For headless environments, use the CLI version: python main.py")
    print(f"Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
    input("Press Enter to exit...")
    sys.exit(1)