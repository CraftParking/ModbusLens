from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Return a path that works both from source and from a PyInstaller bundle."""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir.joinpath(*parts)


def app_data_dir(app_name: str = "ModbusLens") -> Path:
    """Return a writable per-user application data directory."""
    if os.name == "nt":
        base_dir = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base_dir) / app_name

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    xdg_data_home = os.getenv("XDG_DATA_HOME")
    base_dir = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base_dir / app_name


def documents_dir() -> Path:
    """Return the user's real Documents folder, honoring OS-level redirection where
    it's reasonably easy to detect, falling back to ~/Documents everywhere else."""
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
            if value:
                return Path(os.path.expandvars(value))
        except OSError:
            pass
        return Path.home() / "Documents"

    if sys.platform == "darwin":
        return Path.home() / "Documents"

    # Linux: honor the XDG user-dirs config if present -- Documents can be renamed
    # (localized, e.g. "Dokumente") or moved to a different mount entirely.
    config_file = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "user-dirs.dirs"
    try:
        for line in config_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("XDG_DOCUMENTS_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
                return Path(raw)
    except OSError:
        pass
    return Path.home() / "Documents"
