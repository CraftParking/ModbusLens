"""
Device Profiles (roadmap phase 3): a named, reusable template of Address Table
range + Tags for a specific device model, applied to any connection in one step
instead of rebuilding it by hand. Distinct from Save/Load Session -- a session
also carries this connection's own IP/port/serial settings, a profile
deliberately doesn't, since the same device model gets reused across many
different physical connections.

Local profiles are stored on disk under the user's Documents folder (Documents/
ModbusLens/Profiles, on both Windows and Linux), one JSON file each -- somewhere
the user can find, back up, or move by hand, unlike the app-data directory used
for internal config/history. Community-shared profiles are a separate, later
phase -- format and hosting aren't decided yet, so that tab is still a
placeholder here.
"""
import json
import re
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGroupBox, QMessageBox,
    QDialog, QListWidget, QStackedWidget, QLineEdit, QCheckBox,
)

from app_paths import documents_dir

CARD_COLUMNS = 4

PROFILE_FILE_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name):
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return slug or "profile"


def profiles_dir():
    """Profiles live under the user's real Documents folder (not the app-data
    directory used for internal config/history) -- on both Windows and Linux, so
    they're somewhere the user can find, back up, or move by hand."""
    d = documents_dir() / "ModbusLens" / "Profiles"
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


class ProfileCard(QFrame):
    """One saved profile shown as a card: name big and prominent at top, then
    Manufacturer/Type at normal size, then tag count and creation date centered
    underneath in smaller, muted text. Click to select it (for the Apply/Edit/
    Delete buttons below the grid); double-click applies it immediately."""

    clicked = Signal()
    double_clicked = Signal()

    WIDTH = 170
    HEIGHT = 130

    def __init__(self, profile, colors, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.colors = colors
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(4)

        name_label = QLabel(str(profile.get("name", "(unnamed)")))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {colors.get('text', '#000')};")
        layout.addWidget(name_label)

        manufacturer = str(profile.get("manufacturer", "")).strip()
        device_type = str(profile.get("type", "")).strip()
        subtitle = " · ".join(part for part in (manufacturer, device_type) if part)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setAlignment(Qt.AlignCenter)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(f"font-size: 12px; color: {colors.get('text', '#000')};")
            layout.addWidget(subtitle_label)

        layout.addStretch()

        tag_count = len(profile.get("tags", []))
        created = profile.get("created") or profile.get("modified") or ""
        created_date = str(created).split(" ")[0] if created else "-"
        info_label = QLabel(f"{tag_count} tag{'s' if tag_count != 1 else ''} · Created {created_date}")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"font-size: 11px; color: {colors.get('text_secondary', '#666')};")
        layout.addWidget(info_label)

        self.set_selected(False)

    def set_selected(self, selected):
        self._selected = selected
        accent = self.colors.get('accent', '#f5a623')
        if selected:
            border = f"2px solid {accent}"
            bg = self.colors.get('hover_strong', self.colors.get('surface_alt', '#f0f0f0'))
        else:
            border = f"1px solid {self.colors.get('border', '#ccc')}"
            bg = self.colors.get('surface', '#ffffff')
        self.setStyleSheet(f"""
            ProfileCard {{
                background-color: {bg};
                border: {border};
                border-radius: 8px;
            }}
            ProfileCard:hover {{
                border: 2px solid {accent};
            }}
        """)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_clicked.emit()


class CreateProfileDialog(QDialog):
    """Create/Edit Profile: a left-hand page navigator (Profile Info / Tags /
    Datasheet) that switches the dialog's right-hand content, instead of one flat
    form. Datasheet is still a placeholder until its actual content is defined.

    `available_tags` is the live Tags tab's current rows (same shape
    `_build_tag_export_rows()` produces) -- the Tags page lets the user check which
    of those to actually import into the profile, rather than always capturing
    every current tag. `preset` (an existing profile dict) switches the dialog into
    Edit mode: title/button say "Edit"/"Save" instead of "Create", Profile Info
    starts filled in, and any live tag whose name matches one already in the
    profile starts checked."""

    PAGES = ["Profile Info", "Tags", "Datasheet"]

    def __init__(self, colors, button_style, available_tags=None, preset=None, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.button_style = button_style
        self.available_tags = available_tags or []
        self.preset = preset
        self.is_edit = preset is not None
        self.setWindowTitle("Edit Profile" if self.is_edit else "Create New Profile")
        self.setMinimumSize(560, 420)
        self._tag_checkboxes = []
        self._build_ui()

    def _build_ui(self):
        c = self.colors
        outer = QVBoxLayout(self)

        body = QHBoxLayout()
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(150)
        self.nav_list.addItems(self.PAGES)
        self.nav_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {c.get('surface_alt', '#f5f5f5')};
                color: {c.get('text', '#000')};
                border: 1px solid {c.get('border', '#ccc')};
            }}
            QListWidget::item {{
                padding: 10px;
            }}
            QListWidget::item:selected {{
                background-color: {c.get('accent', '#f5a623')};
                color: {c.get('accent_ink', c.get('text', '#000'))};
            }}
        """)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        body.addWidget(self.nav_list)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_info_page())
        self.stack.addWidget(self._build_tags_page())
        self.stack.addWidget(self._build_placeholder_page("Datasheet"))
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.accept_btn = QPushButton("Save" if self.is_edit else "Create")
        self.accept_btn.setStyleSheet(self.button_style)
        self.accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.accept_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(self.button_style)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

        self.nav_list.setCurrentRow(0)

    def _on_nav_changed(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def _build_info_page(self):
        preset = self.preset or {}
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        layout.addWidget(QLabel("Profile Name:"))
        self.name_input = QLineEdit(str(preset.get("name", "")))
        self.name_input.setPlaceholderText("e.g. Schneider ATV320 VFD")
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Manufacturer:"))
        self.manufacturer_input = QLineEdit(str(preset.get("manufacturer", "")))
        self.manufacturer_input.setPlaceholderText("e.g. Schneider Electric")
        layout.addWidget(self.manufacturer_input)

        layout.addWidget(QLabel("Type:"))
        self.type_input = QLineEdit(str(preset.get("type", "")))
        self.type_input.setPlaceholderText("e.g. VFD, PLC, Sensor")
        layout.addWidget(self.type_input)

        layout.addStretch()
        return page

    def _build_tags_page(self):
        """Checkbox list of every tag currently in the live Tags tab, clustered under
        collapsible group headers matching the Tags tab's own Groups (an ungrouped
        section too, for tags with no group) -- checked by default when creating a new
        profile (matches the old "capture everything" behavior unless the user opts
        out), or checked only where the name matches one already in the profile being
        edited. Group order is derived from first-appearance in available_tags, which
        already matches the live Tags tab's own visual cluster order."""
        preset_tag_names = None
        if self.preset is not None:
            preset_tag_names = {
                str(t.get("Tag Name", "")) for t in (self.preset.get("tags") or [])
            }

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not self.available_tags:
            label = QLabel(
                "No tags currently configured in the Tags tab. Add tags there first, "
                "then reopen this to include them in the profile."
            )
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {self.colors.get('text_secondary', '#666')};")
            layout.addWidget(label)
            return page

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Select which tags to include:"))
        select_row.addStretch()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setStyleSheet(self.button_style)
        select_all_btn.clicked.connect(lambda: self._set_all_tags_checked(True))
        select_row.addWidget(select_all_btn)
        select_none_btn = QPushButton("Select None")
        select_none_btn.setStyleSheet(self.button_style)
        select_none_btn.clicked.connect(lambda: self._set_all_tags_checked(False))
        select_row.addWidget(select_none_btn)
        layout.addLayout(select_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {self.colors.get("surface", "#fff")};
                border: 1px solid {self.colors.get("border", "#ccc")};
            }}
        """)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setAlignment(Qt.AlignTop)
        container_layout.setSpacing(2)

        # Cluster by Group, preserving first-appearance order.
        groups_order = []
        groups = {}
        for tag in self.available_tags:
            key = str(tag.get("Group", "") or "")
            if key not in groups:
                groups[key] = []
                groups_order.append(key)
            groups[key].append(tag)

        self._tag_checkboxes = []
        for key in groups_order:
            tags_in_group = groups[key]
            display_name = key or "(Ungrouped)"

            toggle_btn = QPushButton(f"▼  {display_name} ({len(tags_in_group)} tags)")
            toggle_btn.setStyleSheet(
                f"text-align: left; font-weight: 600; color: {self.colors.get('text', '#000')}; "
                f"background: transparent; border: none; padding: 4px;"
            )
            container_layout.addWidget(toggle_btn)

            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(24, 0, 0, 4)
            body_layout.setSpacing(2)

            for tag in tags_in_group:
                name = str(tag.get("Tag Name", ""))
                detail = f"{tag.get('Type', '')} @ {tag.get('Address', '')} ({tag.get('Format', '')})"
                checkbox = QCheckBox(f"{name}  —  {detail}")
                checkbox.setChecked(name in preset_tag_names if preset_tag_names is not None else True)
                body_layout.addWidget(checkbox)
                self._tag_checkboxes.append((checkbox, tag))

            container_layout.addWidget(body)
            toggle_btn.clicked.connect(
                lambda _checked=False, b=body, btn=toggle_btn, n=display_name, c=len(tags_in_group):
                    self._toggle_profile_group_section(b, btn, n, c)
            )

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        return page

    @staticmethod
    def _toggle_profile_group_section(body, toggle_btn, display_name, tag_count):
        """Collapse/expand one group's tag checkboxes -- purely a visibility toggle on
        the already-built body widget, no rebuild needed. Uses isHidden() (this widget's
        own explicit visibility flag) rather than isVisible() (which also depends on
        every ancestor being shown, and would misreport before the dialog itself is
        ever shown)."""
        collapsing = not body.isHidden()
        body.setVisible(not collapsing)
        arrow = "▶" if collapsing else "▼"
        toggle_btn.setText(f"{arrow}  {display_name} ({tag_count} tags)")

    def _set_all_tags_checked(self, checked):
        for checkbox, _tag in self._tag_checkboxes:
            checkbox.setChecked(checked)

    def _build_placeholder_page(self, page_name):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(f"{page_name} -- contents to be defined.")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"color: {self.colors.get('text_secondary', '#666')};")
        layout.addWidget(label)
        return page

    def _on_accept(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Name Required", "Enter a profile name first.")
            self.nav_list.setCurrentRow(0)
            self.name_input.setFocus()
            return
        self.accept()

    def profile_name(self):
        return self.name_input.text().strip()

    def manufacturer(self):
        return self.manufacturer_input.text().strip()

    def device_type(self):
        return self.type_input.text().strip()

    def selected_tags(self):
        """The subset of available_tags whose checkbox is checked, in original order."""
        return [tag for checkbox, tag in self._tag_checkboxes if checkbox.isChecked()]


class DeviceProfilesPanel(QWidget):
    """The Profiles tab's content: a Local/Community toggle over a stacked panel.
    Local is a real, working save/apply/edit/delete flow for on-disk profiles.
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

        self.empty_label = QLabel("No profiles saved yet -- use \"Create New Profile\" to create one.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {c.get('text_secondary', '#666')}; font-size: 13px; padding: 30px;")
        layout.addWidget(self.empty_label)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {c.get("surface", "#fff")};
                border: 1px solid {c.get("border", "#ccc")};
                border-radius: 6px;
            }}
        """)
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet(f"background-color: {c.get('surface', '#fff')};")
        self.cards_grid = QGridLayout(self.cards_container)
        self.cards_grid.setContentsMargins(16, 16, 16, 16)
        self.cards_grid.setSpacing(14)
        self.cards_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.cards_scroll.setWidget(self.cards_container)
        layout.addWidget(self.cards_scroll, 1)

        self._cards = []
        self._selected_path = None

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Create New Profile")
        self.save_btn.setStyleSheet(self._button_style())
        self.save_btn.clicked.connect(self._save_current_as_profile)
        btn_row.addWidget(self.save_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setStyleSheet(self._button_style())
        self.edit_btn.clicked.connect(self._edit_selected)
        btn_row.addWidget(self.edit_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setStyleSheet(self._button_style())
        self.apply_btn.clicked.connect(self._apply_selected)
        btn_row.addWidget(self.apply_btn)

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

    def refresh_local_profiles(self, reselect_path=None):
        """Rebuild the card grid from disk. `reselect_path` re-selects whichever
        profile now lives at that path (e.g. right after saving or renaming one) --
        plain refreshes (Delete, the Refresh button) just clear the selection instead,
        since there's nothing sensible to reselect."""
        self._profiles = list_profiles()

        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        self._selected_path = None

        self.empty_label.setVisible(not self._profiles)
        self.cards_scroll.setVisible(bool(self._profiles))

        colors = self._colors()
        for i, profile in enumerate(self._profiles):
            card = ProfileCard(profile, colors)
            card.clicked.connect(lambda p=profile["_path"]: self._select_path(p))
            card.double_clicked.connect(lambda p=profile["_path"]: self._apply_path(p))
            row, col = divmod(i, CARD_COLUMNS)
            self.cards_grid.addWidget(card, row, col)
            self._cards.append(card)

        if reselect_path is not None:
            self._select_path(reselect_path)
        else:
            self._update_button_states()

    def _select_path(self, path):
        self._selected_path = path
        for card in self._cards:
            card.set_selected(card.profile["_path"] == path)
        self._update_button_states()

    def _apply_path(self, path):
        """Double-clicking a card selects it and applies it in one action."""
        self._select_path(path)
        self._apply_selected()

    def _update_button_states(self):
        has_selection = self._selected_profile() is not None
        self.apply_btn.setEnabled(has_selection)
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _selected_profile(self):
        if self._selected_path is None:
            return None
        for profile in self._profiles:
            if profile["_path"] == self._selected_path:
                return profile
        return None

    def _save_current_as_profile(self):
        """Capture the Address Table's current range, plus whichever currently
        configured Tags the user checks on the Tags page, as a new named profile.
        Name/Manufacturer/Type come from the Create New Profile dialog's Profile
        Info page; Datasheet is still a placeholder."""
        mw = self.parent_window
        if mw is None:
            return
        available_tags = mw._build_tag_export_rows()
        dialog = CreateProfileDialog(self._colors(), self._button_style(), available_tags, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        name = dialog.profile_name()
        if not name:
            return

        path = unique_profile_path(name)
        data = {
            "version": PROFILE_FILE_VERSION,
            "name": name,
            "manufacturer": dialog.manufacturer(),
            "type": dialog.device_type(),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tags": dialog.selected_tags(),
            "address_table": mw._build_address_table_data(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "Save Profile Failed", f"Could not write profile file: {e}")
            return
        self.refresh_local_profiles(reselect_path=path)

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

    def _edit_selected(self):
        """Reopen the same page-navigated dialog Create uses, pre-filled from the
        selected profile -- Profile Info starts filled in, and the Tags page starts
        with whichever currently-live tags are already part of this profile checked
        (so a tag that no longer exists in the live Tags tab simply can't be
        re-checked, but doesn't block editing everything else). Address Table range
        is left as the profile's own saved value -- Edit doesn't re-capture it from
        whatever happens to be live right now, since that may be a different
        connection/device entirely."""
        profile = self._selected_profile()
        mw = self.parent_window
        if profile is None or mw is None:
            return
        old_path = profile["_path"]
        available_tags = mw._build_tag_export_rows()
        dialog = CreateProfileDialog(
            self._colors(), self._button_style(), available_tags, preset=profile, parent=self
        )
        if dialog.exec() != QDialog.Accepted:
            return
        new_name = dialog.profile_name()
        if not new_name:
            return

        new_path = unique_profile_path(new_name, exclude=old_path)
        data = {
            "version": profile.get("version", PROFILE_FILE_VERSION),
            "name": new_name,
            "manufacturer": dialog.manufacturer(),
            "type": dialog.device_type(),
            "created": profile.get("created", time.strftime("%Y-%m-%d %H:%M:%S")),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tags": dialog.selected_tags(),
            "address_table": profile.get("address_table"),
        }
        try:
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            if new_path != old_path:
                old_path.unlink()
        except OSError as e:
            QMessageBox.critical(self, "Save Profile Failed", f"Could not save profile: {e}")
            return
        self.refresh_local_profiles(reselect_path=new_path)

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
