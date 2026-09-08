"""
Build script for creating a ModbusLens AppImage on Linux -- the single-file,
double-click-and-run counterpart to build_exe.py's portable ModbusLens.exe on
Windows. No install, no root/sudo, no package manager: the user downloads one
file, marks it executable, and runs it directly.

Two steps:
1. PyInstaller onedir build (dist/ModbusLens/) -- same bundling approach as
   build_exe.py's onedir/build_deb.py's old .deb build, for the same reason: no
   runtime self-extraction to go wrong (unlike --onefile).
2. Wraps that folder into an AppDir (the standard AppImage source layout:
   AppRun entry point, a .desktop file, an icon) and runs `appimagetool` on it
   to produce dist/ModbusLens-<version>-x86_64.AppImage.

appimagetool itself is downloaded once (cached under .build_tools/, gitignored)
rather than requiring it preinstalled -- it's a ~40MB one-time download, and
keeping a stale local copy around indefinitely isn't worth avoiding that.

Usage: python build_appimage.py
Requires: PyInstaller (already in requirements.txt), Pillow, FUSE (for running
the downloaded appimagetool itself -- falls back to --appimage-extract-and-run
if FUSE isn't available), and internet access for the one-time appimagetool
download.

Known limitation, inherent to the AppImage format itself (not a bug in this
script): unlike a .deb, an AppImage has no dependency-declaration mechanism --
if the host system is missing a base X11/GL library PySide6's bundled Qt needs
(uncommon on any system with a desktop environment already installed, but not
impossible on a minimal server-like install), the app fails to launch with a
plain linker error instead of `apt` offering to install anything. Same class
of runtime-library risk as build_deb.py's Depends list, just with no
declaration or auto-resolution at all.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
PYINSTALLER_OUTPUT = DIST_DIR / "ModbusLens"
APPIMAGE_BUILD_DIR = ROOT / "appimage_build"
BUILD_TOOLS_DIR = ROOT / ".build_tools"

APPIMAGETOOL_PATH = BUILD_TOOLS_DIR / "appimagetool-x86_64.AppImage"
APPIMAGETOOL_URL = (
    "https://github.com/AppImage/appimagetool/releases/download/continuous/"
    "appimagetool-x86_64.AppImage"
)

APP_NAME = "ModbusLens"
DESKTOP_ID = "modbuslens"
SHORT_DESCRIPTION = "Free Modbus TCP & RTU client with network discovery & diagnostics"

# Shared with build_exe.py's COMMON_ARGS -- see that file's comments for why each of
# these is needed (bare `gui.` sibling imports, scapy's hidden submodules, etc.). No
# --icon/--runtime-tmpdir here: those are Windows PE-specific, meaningless on Linux.
PYINSTALLER_ARGS = [
    'gui_main.py',
    '--name=ModbusLens',
    '--windowed',
    f'--add-data=assets{os.pathsep}assets',
    f'--add-data=gui{os.pathsep}gui',
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
    '--onedir',
    '--clean',
    '--noconfirm',
]


def get_version():
    """Reads gui/main_window.py's own __version__ rather than hand-maintaining a
    second copy here that could drift out of sync with it."""
    text = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("Could not find __version__ in gui/main_window.py")
    return match.group(1)


def build_pyinstaller_onedir():
    print("Building ModbusLens onedir folder (Linux)...")
    PyInstaller.__main__.run(PYINSTALLER_ARGS)
    if not PYINSTALLER_OUTPUT.exists():
        raise RuntimeError(f"Expected PyInstaller output at {PYINSTALLER_OUTPUT}, not found")
    print(f"Onedir build complete: {PYINSTALLER_OUTPUT}")


def ensure_appimagetool():
    if APPIMAGETOOL_PATH.exists():
        return APPIMAGETOOL_PATH
    BUILD_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading appimagetool from {APPIMAGETOOL_URL} ...")
    urllib.request.urlretrieve(APPIMAGETOOL_URL, APPIMAGETOOL_PATH)
    APPIMAGETOOL_PATH.chmod(APPIMAGETOOL_PATH.stat().st_mode | stat.S_IEXEC)
    print(f"Cached appimagetool at {APPIMAGETOOL_PATH}")
    return APPIMAGETOOL_PATH


def write_icon(icon_dir_root):
    """Extracts assets/icon.ico's own 256x256 frame (a real square icon, unlike
    assets/icon.png's 1536x1024 banner shape) for the AppDir's top-level icon
    and .DirIcon -- both expected there by the AppImage spec/appimagetool."""
    from PIL import Image

    icon = Image.open(ROOT / "assets" / "icon.ico").convert("RGBA")  # Loads its largest (256x256) frame.
    icon_path = icon_dir_root / f"{DESKTOP_ID}.png"
    icon.save(icon_path)
    dir_icon = icon_dir_root / ".DirIcon"
    if dir_icon.exists() or dir_icon.is_symlink():
        dir_icon.unlink()
    dir_icon.symlink_to(icon_path.name)


def write_desktop_entry(app_dir):
    (app_dir / f"{DESKTOP_ID}.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Comment={SHORT_DESCRIPTION}\n"
        f"Exec={APP_NAME}\n"
        f"Icon={DESKTOP_ID}\n"
        "Terminal=false\n"
        # A single main category (per the freedesktop menu spec's fixed list) --
        # more than one makes some desktop environments list the app twice.
        "Categories=Development;\n"
        f"StartupWMClass={APP_NAME}\n",
        encoding="utf-8",
    )


def write_apprun(app_dir):
    apprun = app_dir / "AppRun"
    apprun.write_text(
        "#!/bin/sh\n"
        'HERE="$(dirname "$(readlink -f "${0}")")"\n'
        f'exec "${{HERE}}/usr/bin/{APP_NAME}" "$@"\n',
        encoding="utf-8",
    )
    apprun.chmod(0o755)


def write_app_bundle(app_dir):
    """Copies the PyInstaller onedir output under AppDir/usr/bin/, preserving the
    ModbusLens binary + its sibling _internal/ folder exactly as PyInstaller laid
    them out -- the binary looks for _internal/ relative to its own location."""
    bin_dir = app_dir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for item in PYINSTALLER_OUTPUT.iterdir():
        dest = bin_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    (bin_dir / APP_NAME).chmod(0o755)


def build_appimage():
    version = get_version()
    print(f"Building ModbusLens {version} AppImage (x86_64)...")

    if APPIMAGE_BUILD_DIR.exists():
        shutil.rmtree(APPIMAGE_BUILD_DIR)
    app_dir = APPIMAGE_BUILD_DIR / f"{APP_NAME}.AppDir"
    app_dir.mkdir(parents=True)

    write_app_bundle(app_dir)
    write_apprun(app_dir)
    write_desktop_entry(app_dir)
    write_icon(app_dir)

    appimagetool = ensure_appimagetool()
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DIST_DIR / f"ModbusLens-{version}-x86_64.AppImage"
    if output_path.exists():
        output_path.unlink()

    env = os.environ.copy()
    env["ARCH"] = "x86_64"
    try:
        subprocess.run([str(appimagetool), str(app_dir), str(output_path)], check=True, env=env)
    except subprocess.CalledProcessError:
        # appimagetool is itself distributed as an AppImage, which needs FUSE to
        # run directly -- if that's unavailable (common in containers/CI), this
        # extracts it to a temp dir and runs the extracted binary instead.
        print("Direct run failed (likely no FUSE available) -- retrying with --appimage-extract-and-run")
        subprocess.run(
            [str(appimagetool), "--appimage-extract-and-run", str(app_dir), str(output_path)],
            check=True, env=env,
        )

    output_path.chmod(0o755)
    print(f"\nAppImage build complete: {output_path}")
    return output_path


if __name__ == "__main__":
    if sys.platform != "linux":
        print("build_appimage.py only makes sense on Linux -- use build_exe.py on Windows.")
        sys.exit(1)

    build_pyinstaller_onedir()
    build_appimage()
