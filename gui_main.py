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


def _wait_for_previous_instance(argv):
    """If launched via ModbusGUI._restart_application() (theme-change relaunch), wait for
    the previous instance to fully exit before this process touches Qt at all.

    A --onefile PyInstaller build extracts its Qt platform plugins to a temp _MEIxxxxxx
    folder on every launch and deletes that folder again on exit. Relaunching immediately
    (the old behavior -- spawn the new process, then close windows and quit) raced this
    process's Qt DLL loading against the old process's temp-folder cleanup, intermittently
    producing "no Qt platform plugin" together with "failed to remove temp directory" on
    the same restart -- worse on a slower/more loaded machine than the one it was built on.
    Waiting for the old PID to actually disappear first means its cleanup has already
    finished (or failed on its own, without contention from this process) before this one
    starts extracting/loading anything Qt-related."""
    pid = None
    for arg in list(argv):
        if arg.startswith("--wait-for-pid="):
            argv.remove(arg)
            try:
                pid = int(arg.split("=", 1)[1])
            except ValueError:
                pid = None
    if pid is None:
        return
    try:
        import psutil
        psutil.Process(pid).wait(timeout=10)
    except Exception:
        pass  # already gone, psutil unavailable, or timed out -- proceed either way


_wait_for_previous_instance(sys.argv)


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