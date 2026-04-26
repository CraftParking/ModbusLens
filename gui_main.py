#!/usr/bin/env python3
"""
ModbusLens GUI Entry Point
"""

import sys
import logging

logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')

try:
    from gui.main_window import main as gui_main
    gui_main()
except ImportError as e:
    print(f"GUI dependencies not available: {e}")
    print("Make sure PySide6 is installed: pip install PySide6")
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
    sys.exit(1)