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


def _report_startup_failure(message):
    """A --windowed/--noconsole build has no stdin/stdout/stderr (they're None), so a
    startup failure's print()/input() calls raise their own exception instead of showing
    anything -- the app just vanishes with zero feedback. Fall back to a crash-log file
    and, on Windows, a native message box, and only wait for a keypress if there's
    actually a console attached to wait on."""
    try:
        log_path = os.path.join(application_path, "modbuslens_startup_error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        log_path = None

    try:
        if sys.stdout is not None:
            print(message)
    except Exception:
        pass

    if sys.stdout is None and sys.platform == "win32":
        try:
            import ctypes
            footer = f"\n\nDetails saved to:\n{log_path}" if log_path else ""
            ctypes.windll.user32.MessageBoxW(0, message + footer, "ModbusLens failed to start", 0x10)
        except Exception:
            pass

    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Enter to exit...")
        except Exception:
            pass


try:
    from gui.main_window import main as gui_main
    gui_main()
except ImportError as e:
    _report_startup_failure(
        f"GUI dependencies not available: {e}\n"
        "Make sure PySide6 is installed: pip install PySide6\n"
        f"Current path: {sys.path}\n"
        f"Application path: {application_path}"
    )
    sys.exit(1)
except SystemExit:
    # GUI main() calls sys.exit(), so this is expected
    pass
except Exception as e:
    import traceback
    _report_startup_failure(
        f"GUI failed to start: {e}\n"
        "\nTroubleshooting:\n"
        "- Make sure you're running on a system with graphical display\n"
        "- If in an IDE, try running from command line\n"
        "- For headless environments, use the CLI version: python main.py\n"
        f"Error type: {type(e).__name__}\n\n"
        f"{traceback.format_exc()}"
    )
    sys.exit(1)