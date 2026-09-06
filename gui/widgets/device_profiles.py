"""
Device Profiles (roadmap phase 3): a named, reusable template of Address Table
range + Tags for a specific device model, applied to any connection in one step
instead of rebuilding it by hand. Distinct from Save/Load Session -- a session
also carries this connection's own IP/port/serial settings, a profile
deliberately doesn't, since the same device model gets reused across many
different physical connections.

Local profiles are stored on disk under app_data_dir()/profiles, one JSON file
each. Community-shared profiles are a separate, later phase -- format and
hosting aren't decided yet, so that tab is still a placeholder here.
"""
import json
import re
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox, QInputDialog,
    QAbstractItemView,
)

from app_paths import app_data_dir

PROFILE_FILE_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name):
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "profile"


def profiles_dir():
    d = app_data_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_profiles():
    """Every saved local profile as a plain dict (plus its file path under '_path'),
    sorted by name. A file that fails to parse is skipped rather than raised -- one
    corrupt profile shouldn't make the whole list unusable."""
    profiles = []
    for path in profiles_dir().glob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        data["_path"] = path
        profiles.append(data)
    profiles.sort(key=lambda p: str(p.get("name", "")).lower())
    return profiles


def unique_profile_path(name, exclude=None):
    """A file path for `name` that doesn't collide with an existing profile file --
    appends -2, -3, ... on a slug collision instead of silently overwriting a
    different profile that happens to slugify the same. `exclude` (a path) is
    allowed to collide with itself, for renaming a profile in place."""
    base = _slugify(name)
    path = profiles_dir() / f"{base}.json"
    n = 2
    while path.exists() and path != exclude:
        path = profiles_dir() / f"{base}-{n}.json"
        n += 1
    return path


def _address_range_summary(at_data):
    if not at_data:
        return "-"
    start = at_data.get("start_address", 0)
    count = at_data.get("count", 1)
    end = start + max(count, 1) - 1
    function = at_data.get("function", "")
    return f"{function}: {start}-{end}" if count > 1 else f"{function}: {start}"


class DeviceProfilesPanel(QWidget):
    """The Profiles tab's content: a Local/Community toggle over a stacked panel.
    Local is a real, working save/apply/rename/delete flow for on-disk profiles.
    Community is a placeholder -- scope and format for shared profiles are still
    being decided."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._build_ui()
        self.refresh_local_profiles()

    def _colors(self):
        return self.parent_window._colors() if self.parent_window and hasattr(self.parent_window, "_colors") else {}

    def _button_style(self):
        return self.parent_window._get_button_style() if self.parent_window and hasattr(self.parent_window, "_get_button_style") else ""

    def _groupbox_style(self):
        return self.parent_window._get_groupbox_style() if self.parent_window and hasattr(self.parent_window, "_get_groupbox_style") else ""

    def _build_ui(self):
        c = self._colors()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Local / Community mode toggle -- two mutually-exclusive checkable buttons
        # acting as a simple segmented control, rather than a combo box, since there
        # are exactly two modes and both should stay visible at all times.
        toggle_row = QHBoxLayout()
        self.local_btn = QPushButton("Local")
        self.community_btn = QPushButton("Community")
        for btn in (self.local_btn, self.community_btn):
            btn.setCheckable(True)
            btn.setStyleSheet(self._button_style())
            toggle_row.addWidget(btn)
        toggle_row.addStretch()
        self.local_btn.setChecked(True)
        self.local_btn.clicked.connect(lambda: self._set_mode("local"))
        self.community_btn.clicked.connect(lambda: self._set_mode("community"))
        layout.addLayout(toggle_row)

        self.local_page = self._build_local_page()
        self.community_page = self._build_community_page()
        layout.addWidget(self.local_page)
        layout.addWidget(self.community_page)
        self.community_page.setVisible(False)

    def _set_mode(self, mode):
        is_local = mode == "local"
        self.local_btn.setChecked(is_local)
        self.community_btn.setChecked(not is_local)
        self.local_page.setVisible(is_local)
        self.community_page.setVisible(not is_local)

    def _build_local_page(self):
        c = self._colors()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.profiles_table = QTableWidget(0, 4)
        self.profiles_table.setHorizontalHeaderLabels(["Name", "Tags", "Address Range", "Modified"])
        self.profiles_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c.get("surface", "#fff")};
                color: {c.get("text", "#000")};
                border: 1px solid {c.get("border", "#ccc")};
            }}
        """)
        self.profiles_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.profiles_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.profiles_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.profiles_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.profiles_table.itemSelectionChanged.connect(self._update_button_states)
        self.profiles_table.doubleClicked.connect(lambda _idx: self._apply_selected())
        layout.addWidget(self.profiles_table, 1)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Current as Profile...")
        self.save_btn.setStyleSheet(self._button_style())
        self.save_btn.clicked.connect(self._save_current_as_profile)
        btn_row.addWidget(self.save_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet(self._button_style())
        self.apply_btn.clicked.connect(self._apply_selected)
        btn_row.addWidget(self.apply_btn)

        self.rename_btn = QPushButton("Rename...")
        self.rename_btn.setStyleSheet(self._button_style())
        self.rename_btn.clicked.connect(self._rename_selected)
        btn_row.addWidget(self.rename_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(self._button_style())
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.delete_btn)

        btn_row.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(self._button_style())
        self.refresh_btn.clicked.connect(self.refresh_local_profiles)
        btn_row.addWidget(self.refresh_btn)
        layout.addLayout(btn_row)

        self._update_button_states()
        return page

    def _build_community_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)

        group = QGroupBox("Community Profiles")
        group.setStyleSheet(self._groupbox_style())
        group_layout = QVBoxLayout(group)
        info_label = QLabel(
            "Coming soon: browse and download device profiles shared by other "
            "ModbusLens users, and publish your own local profiles for others to use."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {self._colors().get('text_secondary', '#666')}; font-size: 13px;")
        group_layout.addWidget(info_label)
        layout.addWidget(group)
        return page

    # -- local profile management ----------------------------------------

    def refresh_local_profiles(self):
        self._profiles = list_profiles()
        self.profiles_table.setRowCount(0)
        for profile in self._profiles:
            row = self.profiles_table.rowCount()
            self.profiles_table.insertRow(row)
            self.profiles_table.setItem(row, 0, QTableWidgetItem(str(profile.get("name", "(unnamed)"))))
            self.profiles_table.setItem(row, 1, QTableWidgetItem(str(len(profile.get("tags", [])))))
            self.profiles_table.setItem(row, 2, QTableWidgetItem(_address_range_summary(profile.get("address_table"))))
            modified = profile.get("modified", "")
            self.profiles_table.setItem(row, 3, QTableWidgetItem(str(modified)))
        self._update_button_states()

    def _update_button_states(self):
        has_selection = bool(self.profiles_table.selectedItems())
        self.apply_btn.setEnabled(has_selection)
        self.rename_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _selected_profile(self):
        items = self.profiles_table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        if row < 0 or row >= len(self._profiles):
            return None
        return self._profiles[row]

    def _save_current_as_profile(self):
        """Capture the current Tags list and Address Table range as a new named
        profile, reusing the exact same serialization Save Session uses so the two
        can never drift out of sync with each other."""
        mw = self.parent_window
        if mw is None:
            return
        name, ok = QInputDialog.getText(self, "Save Current as Profile", "Profile name:")
        name = (name or "").strip()
        if not ok or not name:
            return

        path = unique_profile_path(name)
        data = {
            "version": PROFILE_FILE_VERSION,
            "name": name,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tags": mw._build_tag_export_rows(),
            "address_table": mw._build_address_table_data(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "Save Profile Failed", f"Could not write profile file: {e}")
            return
        self.refresh_local_profiles()

    def _apply_selected(self):
        """Replace the current Tags list and Address Table range with the selected
        profile's -- same "clear and repopulate" contract Load Session already uses,
        so behavior stays consistent between the two entry points."""
        profile = self._selected_profile()
        mw = self.parent_window
        if profile is None or mw is None:
            return
        tags = profile.get("tags")
        if tags is not None:
            mw._apply_imported_tag_rows(tags)
        mw._apply_address_table_data(profile.get("address_table"))
        if hasattr(mw, "_log"):
            mw._log(f"Applied device profile '{profile.get('name', '')}'")

    def _rename_selected(self):
        profile = self._selected_profile()
        if profile is None:
            return
        old_path = profile["_path"]
        new_name, ok = QInputDialog.getText(
            self, "Rename Profile", "New name:", text=str(profile.get("name", ""))
        )
        new_name = (new_name or "").strip()
        if not ok or not new_name:
            return

        new_path = unique_profile_path(new_name, exclude=old_path)
        profile_data = {k: v for k, v in profile.items() if k != "_path"}
        profile_data["name"] = new_name
        profile_data["modified"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, indent=2)
            if new_path != old_path:
                old_path.unlink()
        except OSError as e:
            QMessageBox.critical(self, "Rename Profile Failed", f"Could not rename profile: {e}")
            return
        self.refresh_local_profiles()

    def _delete_selected(self):
        profile = self._selected_profile()
        if profile is None:
            return
        name = profile.get("name", "(unnamed)")
        reply = QMessageBox.question(
            self, "Delete Profile", f"Delete profile '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            profile["_path"].unlink()
        except OSError as e:
            QMessageBox.critical(self, "Delete Profile Failed", f"Could not delete profile: {e}")
            return
        self.refresh_local_profiles()
