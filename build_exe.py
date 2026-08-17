"""
Build script for creating ModbusLens builds using PyInstaller.

Two forms are produced:
- onefile: a single portable ModbusLens.exe (dist/ModbusLens.exe). Simple to hand out,
  but --onefile's self-extract-to-temp-on-every-launch behavior is fragile -- it's hit
  a non-ASCII-username bootloader bug and a mid-run file-disappearance bug on real
  machines (see notes.md), both traced to how onefile unpacks itself at runtime.
- onedir: a folder build (dist/ModbusLens/) with no runtime extraction at all, meant to
  be wrapped by installer.iss (Inno Setup) into a normal Windows installer -- avoids
  that whole bug class, and reads as a normal app install to AV heuristics instead of
  a suspicious self-extracting single exe.

Usage: python build_exe.py [onefile|onedir|both]  (default: both)
"""

import argparse
import os

import PyInstaller.__main__

# Shared by both build forms -- only the packaging mode itself (--onefile/--onedir)
# and onefile's --runtime-tmpdir differ, added by each build function below.
COMMON_ARGS = [
        'gui_main.py',
        '--name=ModbusLens',
        '--windowed',  # Hide console for cleaner GUI experience
        '--icon=assets/icon.ico' if os.path.exists('assets/icon.ico') else '',
        f'--add-data=assets{os.pathsep}assets',
        # main_window.py puts the gui/ folder itself on sys.path so its sibling modules
        # can use bare imports (import log_format, from widgets.x import y, ...) instead
        # of gui.widgets.x everywhere. In dev that folder is real on disk; --onefile only
        # bundles code inside a compiled archive under dotted names, so those bare
        # imports find nothing there unless the gui/ source tree is also copied in as
        # loose files at the same path.
        f'--add-data=gui{os.pathsep}gui',
        # Walk every module under gui/ at analysis time (not just the ones explicitly
        # listed below) so PyInstaller actually opens files like log_format.py/theme.py/
        # register_scanner.py and bundles THEIR imports too (e.g. log_format.py's plain
        # `import html`) -- hand-listing only the top-level ones above missed this.
        '--collect-submodules=gui',
        '--hidden-import=pymodbus',
        '--hidden-import=pymodbus.client',
        '--hidden-import=pymodbus.datastore',
        '--hidden-import=pymodbus.server',
        '--hidden-import=PySide6',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=PySide6.QtCharts',
        '--hidden-import=PySide6.QtPrintSupport',
        '--hidden-import=PySide6.QtNetwork',
        '--hidden-import=gui.main_window',
        '--hidden-import=gui.log_format',
        '--hidden-import=gui.theme',
        '--hidden-import=gui.modbus_meta',
        '--hidden-import=gui.widgets.status_indicator',
        '--hidden-import=gui.widgets.address_table',
        '--hidden-import=gui.widgets.trend_widget',
        '--hidden-import=gui.widgets.server_widget',
        '--hidden-import=gui.widgets.script_widget',
        '--hidden-import=gui.widgets.documentation_dialog',
        '--hidden-import=gui.widgets.about_dialog',
        '--hidden-import=gui.monitoring.monitoring_manager',
        '--hidden-import=gui.diagnostics.advanced_diagnostics',
        '--hidden-import=gui.diagnostics.diagnostics_dialogs',
        '--hidden-import=gui.diagnostics.register_scanner',
        '--hidden-import=gui.diagnostics.serial_discovery',
        '--hidden-import=gui.network.network_diagnostics',
        '--hidden-import=core.modbus_client',
        '--hidden-import=app_paths',
        '--hidden-import=serial',
        '--hidden-import=serial.tools.list_ports',
        '--hidden-import=psutil',
        # scapy is an optional runtime import (network_diagnostics.py falls back
        # gracefully if missing) but PyInstaller's analysis never sees it as a
        # real dependency, so a system-wide `pip install scapy` never reaches
        # the frozen onefile exe. collect-all pulls in its many submodules
        # (arch/, layers/) and data files (e.g. the MAC vendor list) that a
        # plain hidden-import would miss.
        '--collect-all=scapy',
        '--exclude-module=PySide6.QtWebEngine',
        '--exclude-module=PySide6.QtWebEngineCore',
        '--exclude-module=PySide6.QtWebEngineWidgets',
        '--exclude-module=PySide6.QtWebSockets',
        '--exclude-module=PySide6.QtQuick',
        '--exclude-module=PySide6.QtQml',
        '--exclude-module=PySide6.Qt3D',
        '--exclude-module=PySide6.QtDataVisualization',
        '--exclude-module=PySide6.QtMultimedia',
        '--exclude-module=PySide6.QtOpenGL',
        '--exclude-module=PySide6.QtSql',
        '--exclude-module=PySide6.QtSvg',
        '--exclude-module=PySide6.QtTest',
        '--exclude-module=PySide6.QtXml',
        '--clean',
        '--noconfirm',
]
# Remove empty entries (e.g. the icon flag when assets/icon.ico doesn't exist).
COMMON_ARGS = [arg for arg in COMMON_ARGS if arg]


def build_onefile():
    """Portable single .exe -- still offered as a direct download, but known to be
    fragile on some machines (non-ASCII usernames, AV interference with onefile's
    self-extract-to-temp behavior -- see notes.md). --runtime-tmpdir works around the
    username issue specifically; the onedir build below sidesteps the whole class."""
    args = [
        *COMMON_ARGS,
        '--onefile',
        # A --onefile exe normally extracts itself under the OS temp dir, which sits
        # under the user's own profile path (%TEMP% -> ...\Users\<username>\...) --
        # PyInstaller's bootloader (compiled C, runs before Python's own encoding
        # machinery exists yet) can fail entirely on a non-ASCII Windows username with
        # "Failed to import encodings module", since that username is part of the path
        # it has to extract to. C:\ProgramData is a fixed, all-users, username-free
        # location, so this sidesteps that whole bug class regardless of who's logged
        # in. Must NOT be anything under %USERPROFILE%/%APPDATA%/%LOCALAPPDATA% --
        # those still contain the same problematic username segment.
        r'--runtime-tmpdir=C:\ProgramData\ModbusLens\runtime',
    ]
    print("Building ModbusLens onefile EXE...")
    print(f"Arguments: {' '.join(args)}")
    PyInstaller.__main__.run(args)
    print("\nOnefile build complete! dist/ModbusLens.exe")


def build_onedir():
    """Folder build with no runtime extraction -- what installer.iss (Inno Setup)
    packages into a normal Windows installer."""
    args = [*COMMON_ARGS, '--onedir']
    print("Building ModbusLens onedir folder...")
    print(f"Arguments: {' '.join(args)}")
    PyInstaller.__main__.run(args)
    print("\nOnedir build complete! dist/ModbusLens/")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', choices=['onefile', 'onedir', 'both'], default='both')
    parsed = parser.parse_args()

    if parsed.mode in ('onefile', 'both'):
        build_onefile()
    if parsed.mode in ('onedir', 'both'):
        build_onedir()
