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
import urllib.error
import urllib.request

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGroupBox, QMessageBox,
    QDialog, QListWidget, QStackedWidget, QLineEdit, QCheckBox,
)

from app_paths import documents_dir

CARD_COLUMNS = 4

PROFILE_FILE_VERSION = 1
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Verified community profiles live as plain files in this repo (community-profiles/),
# with index.json as a generated manifest (tools/build_community_index.py) the app
# reads first to render cards without fetching every profile's full tag list up
# front.
COMMUNITY_REPO = "CraftParking/ModbusLens"
COMMUNITY_BRANCH = "main"
COMMUNITY_BASE_URL = f"https://raw.githubusercontent.com/{COMMUNITY_REPO}/{COMMUNITY_BRANCH}/community-profiles/"
COMMUNITY_INDEX_URL = COMMUNITY_BASE_URL + "index.json"

# Submission (DeviceProfilesPanel._share_selected_to_community) goes straight to a
# Formspree form's endpoint as a background JSON POST -- no browser, no mail
# client, no server of our own to host. Formspree forwards each submission to the
# maintainer's inbox for review; its form ID isn't a secret the way an API token
# would be (leaking it only risks someone spamming that inbox through the form
# itself, which Formspree's own free-tier rate-limiting/spam filtering already
# guards against), unlike embedding a GitHub token or SMTP password in a public
# client, which would let an attacker act as this app anywhere, not just here.
# Replace YOUR_FORM_ID with the real one after creating the form at formspree.io.
COMMUNITY_FORM_ENDPOINT = "https://formspree.io/f/xjyvadqr"


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


class _HttpFetchWorker(QThread):
    """Does one HTTP request's worth of work off the GUI thread -- the community
    index fetch, a single profile's full-file download, and a Community
    submission POST are all quick one-shot requests, not a continuous poll like
    Tag Monitoring's pollers, so one generic worker covers all three instead of
    near-identical classes. A GET when `data` is None (the default), a POST of
    `data` (raw bytes) otherwise. Kept alive via normal Qt parent-child
    ownership (constructed with parent=<the panel>), not a Python reference --
    deleteLater on its own `finished` (QThread's built-in signal, once run()
    returns) is what actually cleans it up."""

    succeeded = Signal(str, bytes)  # url, response body
    failed = Signal(str, str)  # url, error message

    def __init__(self, url, data=None, headers=None, timeout=8, parent=None):
        super().__init__(parent)
        self.url = url
        self.data = data
        self.headers = {"User-Agent": "ModbusLens", **(headers or {})}
        self.timeout = timeout

    def run(self):
        try:
            request = urllib.request.Request(self.url, data=self.data, headers=self.headers)
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as e:
            # The server's own error body (e.g. Formspree's JSON {"errors": [...]}
            # on a rejected/rate-limited submission) is far more useful to show the
            # user than urllib's generic "HTTP Error 422: Unprocessable Entity".
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            self.failed.emit(self.url, detail or str(e))
            return
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.failed.emit(self.url, str(e))
            return
        self.succeeded.emit(self.url, body)


class ProfileCard(QFrame):
    """One saved profile shown as a card: name big and prominent at top, then
    Manufacturer/Type at normal size, then tag count and creation date centered
    underneath in smaller, muted text. Click to select it (for the Edit/Delete
    buttons below the grid); double-click opens a read-only view of it with a
    per-tag import picker (see DeviceProfilesPanel._open_view_profile_dialog)."""

    clicked = Signal()
    double_clicked = Signal()

    WIDTH = 170
    HEIGHT = 145

    def __init__(self, profile, colors, parent=None, tag_count=None):
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
        name_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {colors.get('text', '#000')}; background: transparent;")
        layout.addWidget(name_label)

        manufacturer = str(profile.get("manufacturer", "")).strip()
        device_type = str(profile.get("type", "")).strip()
        subtitle = " · ".join(part for part in (manufacturer, device_type) if part)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setAlignment(Qt.AlignCenter)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(f"font-size: 12px; color: {colors.get('text', '#000')}; background: transparent;")
            layout.addWidget(subtitle_label)

        # A profile downloaded from Community (see DeviceProfilesPanel.
        # _on_community_profile_downloaded) looks identical to a hand-made local one
        # otherwise -- same name/tags/author, nothing to tell them apart by. This
        # badge is the only thing that does; it disappears once the profile is
        # edited (source isn't one of the fields Edit's save carries forward),
        # which is correct: it's no longer literally the community file at that point.
        if str(profile.get("source", "")).strip() == "community":
            accent = colors.get("accent", "#f5a623")
            badge_label = QLabel("Community")
            badge_label.setAlignment(Qt.AlignCenter)
            badge_label.setStyleSheet(
                f"font-size: 10px; font-weight: 600; color: {accent}; "
                f"border: 1px solid {accent}; border-radius: 8px; padding: 1px 6px; "
                "background: transparent;"
            )
            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(0, 0, 0, 0)
            badge_row.addStretch()
            badge_row.addWidget(badge_label)
            badge_row.addStretch()
            layout.addLayout(badge_row)

        layout.addStretch()

        # A community card's manifest entry carries only tag_count (not the full tag
        # list), so it passes the count in explicitly rather than a fake tags list.
        tag_count = len(profile.get("tags", [])) if tag_count is None else tag_count
        created = profile.get("created") or profile.get("modified") or ""
        created_date = str(created).split(" ")[0] if created else "-"
        info_text = f"{tag_count} tag{'s' if tag_count != 1 else ''} · Created {created_date}"
        author = str(profile.get("author", "")).strip()
        if author:
            info_text += f"\nby {author}"
        info_label = QLabel(info_text)
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"font-size: 11px; color: {colors.get('text_secondary', '#666')}; background: transparent;")
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


# View Profile's per-tag/group status dots: red means a profile tag that isn't in the
# live Tags tab at all (importing it adds a new tag), green means it's already there
# (nothing to import), yellow is group-header-only and means that group is a mix of both.
_STATUS_COLORS = {"red": "#e53935", "green": "#43a047", "yellow": "#fbc02d"}
_STATUS_LABELS = {"red": "Only in this profile", "green": "Already in Tags", "yellow": "Mixed"}


def _status_dot(status):
    dot = QLabel()
    dot.setFixedSize(10, 10)
    dot.setStyleSheet(f"background-color: {_STATUS_COLORS[status]}; border-radius: 5px;")
    dot.setToolTip(_STATUS_LABELS[status])
    return dot


def _group_status(tag_names, live_tag_names):
    """Aggregate status for a group header from its member tags' individual statuses --
    green if every one is already live, red if none are, yellow if it's a mix."""
    statuses = {"green" if name in live_tag_names else "red" for name in tag_names}
    return statuses.pop() if len(statuses) == 1 else "yellow"


class _GroupSelectCheckBox(QCheckBox):
    """A group header's "select all in this group" checkbox. Tristate so it can *display*
    PartiallyChecked when only some of the group's tags are checked, but a user click
    always resolves straight to Checked/Unchecked -- Qt's default tristate click-cycle
    (Unchecked -> PartiallyChecked -> Checked -> Unchecked) would otherwise let a click
    land the header itself on PartiallyChecked, which doesn't mean anything as a click
    target."""

    def nextCheckState(self):
        self.setCheckState(Qt.Unchecked if self.checkState() == Qt.Checked else Qt.Checked)


class CreateProfileDialog(QDialog):
    """Create/Edit Profile: a left-hand page navigator (Profile Info / Tags /
    Datasheet) that switches the dialog's right-hand content, instead of one flat
    form. Datasheet is still a placeholder until its actual content is defined.

    `available_tags` is the live Tags tab's current rows (same shape
    `_build_tag_export_rows()` produces) -- the Tags page lets the user check which
    of those to actually import into the profile, rather than always capturing
    every current tag. `preset` (an existing profile dict) switches the dialog into
    Edit mode: title/button say "Edit"/"Save" instead of "Create", Profile Info
    starts filled in, and the Tags page is seeded with the profile's own saved tags
    (checked) plus any live tag not already in the profile (unchecked) -- NOT just
    whatever happens to be live right now. The profile's tags are very often not the
    live Tags tab's tags at all (e.g. right after reopening the app, or after
    connecting to a different device), and building the Tags page from live tags
    alone meant Edit would show an empty list and, if saved, silently wipe out the
    profile's real tags entirely.

    `view_only=True` is a third mode, used by the Profiles tab's card popup: Profile
    Info becomes read-only (nothing here is being changed), the title/button say "View
    Profile"/"Apply", and the Tags page shows only the profile's own saved tags (never
    merged with extra live ones -- there's nothing to add TO the profile here) each
    marked with a red/green status dot against `live_tag_names` (the current Tags tab's
    tag names) so the user can see at a glance which tags would actually be new. Apply
    does NOT close the dialog in this mode -- it calls `on_apply(selected_tags())` right
    away (the caller's chance to actually import them), then refreshes the Tags page
    against `on_apply`'s return value (the live tag names after that import) so status
    dots update in place and Apply can be clicked again for a second batch. Only Close
    (Cancel, relabeled) ends the dialog. Non-view-only modes are unaffected: Accept still
    closes immediately and the caller reads selected_tags()/profile_name() etc. after
    exec() returns, same as always."""

    PAGES = ["Profile Info", "Tags", "Datasheet"]

    def __init__(self, colors, button_style, available_tags=None, preset=None, parent=None,
                 view_only=False, live_tag_names=None, input_style="", on_apply=None):
        super().__init__(parent)
        self.colors = colors
        self.button_style = button_style
        self.input_style = input_style
        self.view_only = view_only
        self.live_tag_names = live_tag_names or set()
        self.on_apply = on_apply
        if view_only:
            self.available_tags = list((preset or {}).get("tags") or [])
        else:
            self.available_tags = self._merge_preset_tags(available_tags or [], preset)
        self.preset = preset
        self.is_edit = preset is not None
        if view_only:
            self.setWindowTitle("View Profile")
        elif self.is_edit:
            self.setWindowTitle("Edit Profile")
        else:
            self.setWindowTitle("Create New Profile")
        self.setMinimumSize(560, 420)
        self._tag_checkboxes = []
        self._group_checkboxes = {}  # group key -> its header QCheckBox
        self._group_tag_checkboxes = {}  # group key -> list of member tag QCheckBoxes
        self._updating_group_checkbox = False  # reentrancy guard, see _on_group_checkbox_changed
        self._build_ui()

    @staticmethod
    def _merge_preset_tags(live_tags, preset):
        """The profile's own saved tags first (in their own saved order/data), then any
        live tag not already in the profile appended after -- so Edit always shows the
        real contents of the profile being edited, never just whatever's live right now.
        A tag present in both is only listed once, using the profile's saved copy (this
        is a snapshot of the profile, not a live re-sync of that tag's current address/
        format from the Tags tab)."""
        if preset is None:
            return list(live_tags)
        preset_tags = preset.get("tags") or []
        preset_names = {str(t.get("Tag Name", "")) for t in preset_tags}
        extra_live = [t for t in live_tags if str(t.get("Tag Name", "")) not in preset_names]
        return list(preset_tags) + extra_live

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
                outline: 0;
            }}
            QListWidget::item {{
                padding: 10px;
            }}
            QListWidget::item:selected {{
                background-color: {c.get('accent', '#f5a623')};
                color: {c.get('accent_ink', c.get('text', '#000'))};
                outline: 0;
                border: none;
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
        accept_text = "Apply" if self.view_only else ("Save" if self.is_edit else "Create")
        self.accept_btn = QPushButton(accept_text)
        self.accept_btn.setStyleSheet(self.button_style)
        self.accept_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.accept_btn)
        cancel_btn = QPushButton("Close" if self.view_only else "Cancel")
        cancel_btn.setStyleSheet(self.button_style)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

        self.nav_list.setCurrentRow(0)

    def _on_nav_changed(self, row):
        if row >= 0:
            self.stack.setCurrentIndex(row)

    def _make_info_field(self, value, placeholder):
        """An editable QLineEdit in Create/Edit mode, or a plain QLabel in view_only --
        View Profile shows nothing that looks editable, since nothing on this page can
        actually be changed there. QLabel also has .text(), so profile_name() etc. below
        work unchanged regardless of which one this returns."""
        if self.view_only:
            label = QLabel(value)
            label.setStyleSheet(f"color: {self.colors.get('text', '#000')};")
            return label
        field = QLineEdit(value)
        field.setPlaceholderText(placeholder)
        field.setStyleSheet(self.input_style)
        return field

    def _build_info_page(self):
        preset = self.preset or {}
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignTop)
        # Tight between a field's own label and value; addSpacing below adds the bigger
        # gap between one field group and the next, so groups read as visually distinct.
        layout.setSpacing(2)
        FIELD_GAP = 14

        layout.addWidget(QLabel("Profile Name:"))
        self.name_input = self._make_info_field(str(preset.get("name", "")), "e.g. Schneider ATV320 VFD")
        layout.addWidget(self.name_input)
        layout.addSpacing(FIELD_GAP)

        layout.addWidget(QLabel("Manufacturer:"))
        self.manufacturer_input = self._make_info_field(str(preset.get("manufacturer", "")), "e.g. Schneider Electric")
        layout.addWidget(self.manufacturer_input)
        layout.addSpacing(FIELD_GAP)

        layout.addWidget(QLabel("Type:"))
        self.type_input = self._make_info_field(str(preset.get("type", "")), "e.g. VFD, PLC, Sensor")
        layout.addWidget(self.type_input)
        layout.addSpacing(FIELD_GAP)

        layout.addWidget(QLabel("Author:"))
        self.author_input = self._make_info_field(str(preset.get("author", "")), "e.g. your name")
        layout.addWidget(self.author_input)

        layout.addStretch()
        return page

    def _build_tags_page(self):
        """Checkbox list of every tag in self.available_tags (already merged with the
        profile's own saved tags in Edit mode -- see _merge_preset_tags), clustered under
        collapsible group headers matching the Tags tab's own Groups (an ungrouped
        section too, for tags with no group) -- checked by default when creating a new
        profile (matches the old "capture everything" behavior unless the user opts
        out), or checked only where the name matches one already in the profile being
        edited. Group order is derived from first-appearance in available_tags: when
        creating, that matches the live Tags tab's own visual cluster order; when
        editing, the profile's own saved tags come first (see _merge_preset_tags), so any
        of its groups appear in the order they were originally saved."""
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
                "This profile has no saved tags." if self.view_only else
                "No tags currently configured in the Tags tab. Add tags there first, "
                "then reopen this to include them in the profile."
            )
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {self.colors.get('text_secondary', '#666')};")
            layout.addWidget(label)
            return page

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Select which tags to import:" if self.view_only else "Select which tags to include:"))
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

        # Cluster by Group, preserving first-appearance order -- computed here (rather
        # than right before the loop that consumes it) so the view_only legend below can
        # count mixed (yellow) groups without duplicating this same clustering logic.
        groups_order = []
        groups = {}
        for tag in self.available_tags:
            key = str(tag.get("Group", "") or "")
            if key not in groups:
                groups[key] = []
                groups_order.append(key)
            groups[key].append(tag)

        if self.view_only:
            red_count = sum(1 for t in self.available_tags if str(t.get("Tag Name", "")) not in self.live_tag_names)
            green_count = sum(1 for t in self.available_tags if str(t.get("Tag Name", "")) in self.live_tag_names)
            yellow_count = sum(
                1 for key in groups_order
                if _group_status([str(t.get("Tag Name", "")) for t in groups[key]], self.live_tag_names) == "yellow"
            )
            legend_counts = {"red": red_count, "green": green_count, "yellow": yellow_count}

            legend_row = QHBoxLayout()
            legend_row.setSpacing(16)
            for status in ("red", "green", "yellow"):
                legend_row.addWidget(_status_dot(status))
                legend_label = QLabel(f"{_STATUS_LABELS[status]} ({legend_counts[status]})")
                legend_label.setStyleSheet(f"color: {self.colors.get('text_secondary', '#666')}; font-size: 11px;")
                legend_row.addWidget(legend_label)
            legend_row.addStretch()
            layout.addLayout(legend_row)

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

        self._tag_checkboxes = []
        self._group_checkboxes = {}
        self._group_tag_checkboxes = {}
        for key in groups_order:
            tags_in_group = groups[key]
            display_name = key or "(Ungrouped)"

            header_row = QWidget()
            header_layout = QHBoxLayout(header_row)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(4)

            if self.view_only:
                tag_names_in_group = [str(t.get("Tag Name", "")) for t in tags_in_group]
                header_layout.addWidget(_status_dot(_group_status(tag_names_in_group, self.live_tag_names)))

            group_checkbox = _GroupSelectCheckBox()
            group_checkbox.setTristate(True)
            group_checkbox.setToolTip(f"Select/deselect every tag in {display_name}")
            header_layout.addWidget(group_checkbox)

            toggle_btn = QPushButton(f"▼  {display_name} ({len(tags_in_group)} tags)")
            toggle_btn.setStyleSheet(
                f"text-align: left; font-weight: 600; color: {self.colors.get('text', '#000')}; "
                f"background: transparent; border: none; padding: 4px;"
            )
            header_layout.addWidget(toggle_btn, 1)
            container_layout.addWidget(header_row)

            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(24, 0, 0, 4)
            body_layout.setSpacing(2)

            member_checkboxes = []
            for tag in tags_in_group:
                name = str(tag.get("Tag Name", ""))
                detail = f"{tag.get('Type', '')} @ {tag.get('Address', '')} ({tag.get('Format', '')})"
                checkbox = QCheckBox(f"{name}  —  {detail}")
                checkbox.setChecked(name in preset_tag_names if preset_tag_names is not None else True)
                checkbox.toggled.connect(lambda _checked=False, gk=key: self._update_group_checkbox_state(gk))
                if self.view_only:
                    tag_row = QWidget()
                    tag_row_layout = QHBoxLayout(tag_row)
                    tag_row_layout.setContentsMargins(0, 0, 0, 0)
                    tag_row_layout.setSpacing(6)
                    status = "green" if name in self.live_tag_names else "red"
                    tag_row_layout.addWidget(_status_dot(status))
                    tag_row_layout.addWidget(checkbox, 1)
                    body_layout.addWidget(tag_row)
                else:
                    body_layout.addWidget(checkbox)
                self._tag_checkboxes.append((checkbox, tag))
                member_checkboxes.append(checkbox)

            container_layout.addWidget(body)
            self._group_tag_checkboxes[key] = member_checkboxes
            self._group_checkboxes[key] = group_checkbox
            self._update_group_checkbox_state(key)
            group_checkbox.stateChanged.connect(lambda state, gk=key: self._on_group_checkbox_changed(gk, state))

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

    def _on_group_checkbox_changed(self, group_key, state):
        """A group's own header checkbox was clicked -- fan the change out to every tag
        checkbox in that group. Guarded by _updating_group_checkbox so the member
        checkboxes' own toggled->_update_group_checkbox_state calls (fired as a side
        effect of setChecked below) don't fight this method over the header's tri-state,
        which _update_group_checkbox_state would otherwise immediately recompute back to
        Qt.PartiallyChecked mid-update."""
        if self._updating_group_checkbox:
            return
        checked = Qt.CheckState(state) != Qt.Unchecked
        self._updating_group_checkbox = True
        try:
            for checkbox in self._group_tag_checkboxes.get(group_key, []):
                checkbox.setChecked(checked)
        finally:
            self._updating_group_checkbox = False

    def _update_group_checkbox_state(self, group_key):
        """Recompute one group's header checkbox (checked/unchecked/partial) from its
        member tags' current state -- called after any member checkbox toggles, so the
        header always reflects reality even when a member was (un)checked individually
        rather than via the header."""
        if self._updating_group_checkbox:
            return
        checkboxes = self._group_tag_checkboxes.get(group_key)
        group_checkbox = self._group_checkboxes.get(group_key)
        if not checkboxes or group_checkbox is None:
            return
        checked_count = sum(1 for c in checkboxes if c.isChecked())
        self._updating_group_checkbox = True
        try:
            if checked_count == 0:
                group_checkbox.setCheckState(Qt.Unchecked)
            elif checked_count == len(checkboxes):
                group_checkbox.setCheckState(Qt.Checked)
            else:
                group_checkbox.setCheckState(Qt.PartiallyChecked)
        finally:
            self._updating_group_checkbox = False

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
        if self.view_only:
            self._on_apply_clicked()
            return
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "Name Required", "Enter a profile name first.")
            self.nav_list.setCurrentRow(0)
            self.name_input.setFocus()
            return
        self.accept()

    def _on_apply_clicked(self):
        """view_only's Apply -- unlike Create/Edit's Accept, this never closes the
        dialog: it runs on_apply() right away (the caller's real import), then rebuilds
        the Tags page against on_apply's return value (the live tag names right after
        that import) so status dots update in place and the user can adjust the
        selection and click Apply again for a second batch. Only Close ends the
        dialog."""
        if self.on_apply is not None:
            new_live_names = self.on_apply(self.selected_tags())
            if new_live_names is not None:
                self.live_tag_names = new_live_names
        self._refresh_tags_page()

    def _refresh_tags_page(self):
        """Rebuilds the Tags page from scratch (needed to recompute every status dot),
        while preserving each tag's current checked state across the rebuild -- without
        this, re-checking status dots would also silently reset any manual check/uncheck
        the user made back to _build_tags_page's default (everything checked)."""
        checked_state = {str(tag.get("Tag Name", "")): checkbox.isChecked() for checkbox, tag in self._tag_checkboxes}
        old_page = self.stack.widget(1)
        new_page = self._build_tags_page()
        for checkbox, tag in self._tag_checkboxes:
            name = str(tag.get("Tag Name", ""))
            if name in checked_state:
                checkbox.setChecked(checked_state[name])
        self.stack.removeWidget(old_page)
        old_page.deleteLater()
        self.stack.insertWidget(1, new_page)
        self.stack.setCurrentIndex(1)

    def profile_name(self):
        return self.name_input.text().strip()

    def manufacturer(self):
        return self.manufacturer_input.text().strip()

    def device_type(self):
        return self.type_input.text().strip()

    def author(self):
        return self.author_input.text().strip()

    def selected_tags(self):
        """The subset of available_tags whose checkbox is checked, in original order."""
        return [tag for checkbox, tag in self._tag_checkboxes if checkbox.isChecked()]


class DeviceProfilesPanel(QWidget):
    """The Profiles tab's content: a Local/Community toggle over a stacked panel.
    Local is a real, working save/import/edit/delete flow for on-disk profiles.
    Community browses profiles verified and published to this repo's
    community-profiles/ folder (fetched over HTTPS from raw.githubusercontent.com,
    no backend server) and downloads a chosen one straight into the Local list --
    submitting a local profile FOR review is a separate action, see
    _share_selected_to_community."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._community_profiles = []
        self._community_cards = []
        self._community_selected_file = None
        self._community_loaded = False
        self._community_loading = False
        self._build_ui()
        self.refresh_local_profiles()

    def _colors(self):
        return self.parent_window._colors() if self.parent_window and hasattr(self.parent_window, "_colors") else {}

    def _button_style(self):
        return self.parent_window._get_button_style() if self.parent_window and hasattr(self.parent_window, "_get_button_style") else ""

    def _input_style(self):
        return self.parent_window._get_input_style() if self.parent_window and hasattr(self.parent_window, "_get_input_style") else ""

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
        if not is_local and not self._community_loaded and not self._community_loading:
            self._fetch_community_index()

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

        hint_label = QLabel("Double-click a profile to view it and choose which tags to import.")
        hint_label.setStyleSheet(f"color: {c.get('text_secondary', '#666')}; font-size: 11px;")
        layout.addWidget(hint_label)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Create New Profile")
        self.save_btn.setStyleSheet(self._button_style())
        self.save_btn.clicked.connect(self._save_current_as_profile)
        btn_row.addWidget(self.save_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setStyleSheet(self._button_style())
        self.edit_btn.clicked.connect(self._edit_selected)
        btn_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(self._button_style())
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.delete_btn)

        self.share_btn = QPushButton("Share to Community")
        self.share_btn.setStyleSheet(self._button_style())
        self.share_btn.clicked.connect(self._share_selected_to_community)
        btn_row.addWidget(self.share_btn)

        btn_row.addStretch()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(self._button_style())
        self.refresh_btn.clicked.connect(self.refresh_local_profiles)
        btn_row.addWidget(self.refresh_btn)
        layout.addLayout(btn_row)

        self._update_button_states()
        return page

    def _build_community_page(self):
        c = self._colors()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.community_status_label = QLabel("")
        self.community_status_label.setAlignment(Qt.AlignCenter)
        self.community_status_label.setWordWrap(True)
        self.community_status_label.setStyleSheet(f"color: {c.get('text_secondary', '#666')}; font-size: 13px; padding: 30px;")
        self.community_status_label.setVisible(False)
        layout.addWidget(self.community_status_label)

        self.community_empty_label = QLabel("No community profiles published yet -- check back later.")
        self.community_empty_label.setAlignment(Qt.AlignCenter)
        self.community_empty_label.setStyleSheet(f"color: {c.get('text_secondary', '#666')}; font-size: 13px; padding: 30px;")
        self.community_empty_label.setVisible(False)
        layout.addWidget(self.community_empty_label)

        self.community_cards_scroll = QScrollArea()
        self.community_cards_scroll.setWidgetResizable(True)
        self.community_cards_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {c.get("surface", "#fff")};
                border: 1px solid {c.get("border", "#ccc")};
                border-radius: 6px;
            }}
        """)
        self.community_cards_container = QWidget()
        self.community_cards_container.setStyleSheet(f"background-color: {c.get('surface', '#fff')};")
        self.community_cards_grid = QGridLayout(self.community_cards_container)
        self.community_cards_grid.setContentsMargins(16, 16, 16, 16)
        self.community_cards_grid.setSpacing(14)
        self.community_cards_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.community_cards_scroll.setWidget(self.community_cards_container)
        self.community_cards_scroll.setVisible(False)
        layout.addWidget(self.community_cards_scroll, 1)

        hint_label = QLabel("Double-click a profile to download it into your Local profiles.")
        hint_label.setStyleSheet(f"color: {c.get('text_secondary', '#666')}; font-size: 11px;")
        layout.addWidget(hint_label)

        btn_row = QHBoxLayout()
        self.community_download_btn = QPushButton("Download")
        self.community_download_btn.setStyleSheet(self._button_style())
        self.community_download_btn.setEnabled(False)
        self.community_download_btn.clicked.connect(
            lambda: self._download_community_profile(self._community_selected_file)
        )
        btn_row.addWidget(self.community_download_btn)

        btn_row.addStretch()
        self.community_refresh_btn = QPushButton("Refresh")
        self.community_refresh_btn.setStyleSheet(self._button_style())
        self.community_refresh_btn.clicked.connect(self._fetch_community_index)
        btn_row.addWidget(self.community_refresh_btn)
        layout.addLayout(btn_row)

        return page

    # -- community profile browsing ---------------------------------------

    def _fetch_community_index(self):
        """Fetches index.json (see COMMUNITY_INDEX_URL) in the background and
        rebuilds the card grid on success. Safe to call again while a fetch is
        already in flight (Refresh button) -- the stale worker just finishes and
        deletes itself; only the most recent one's result reaches the UI, since
        the older one's signals were never connected to anything after this
        reassigns the button states below."""
        self._community_loading = True
        self.community_download_btn.setEnabled(False)
        self.community_refresh_btn.setEnabled(False)
        self.community_empty_label.setVisible(False)
        self.community_status_label.setText("Loading community profiles...")
        self.community_status_label.setVisible(True)

        worker = _HttpFetchWorker(COMMUNITY_INDEX_URL, parent=self)
        worker.succeeded.connect(self._on_community_index_loaded)
        worker.failed.connect(self._on_community_index_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_community_index_loaded(self, url, body):
        self._community_loading = False
        self.community_refresh_btn.setEnabled(True)
        try:
            data = json.loads(body.decode("utf-8"))
            profiles = data.get("profiles") if isinstance(data, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            profiles = None
        if not isinstance(profiles, list):
            self.community_status_label.setText("Couldn't parse the community profile list -- try Refresh.")
            return

        self._community_loaded = True
        self._community_profiles = profiles
        self.community_status_label.setVisible(False)
        self._rebuild_community_cards()

    def _on_community_index_failed(self, url, error):
        self._community_loading = False
        self.community_refresh_btn.setEnabled(True)
        self.community_status_label.setText(
            f"Couldn't reach the community profile list ({error}). Check your "
            "connection and try Refresh."
        )
        self.community_status_label.setVisible(True)

    def _rebuild_community_cards(self):
        for card in self._community_cards:
            card.setParent(None)
            card.deleteLater()
        self._community_cards = []
        self._community_selected_file = None

        self.community_empty_label.setVisible(not self._community_profiles)
        self.community_cards_scroll.setVisible(bool(self._community_profiles))

        colors = self._colors()
        for i, profile in enumerate(self._community_profiles):
            card = ProfileCard(profile, colors, tag_count=profile.get("tag_count", 0))
            card.clicked.connect(lambda f=profile["file"]: self._select_community(f))
            card.double_clicked.connect(lambda f=profile["file"]: self._download_community_profile(f))
            row, col = divmod(i, CARD_COLUMNS)
            self.community_cards_grid.addWidget(card, row, col)
            self._community_cards.append(card)
        self._update_community_button_states()

    def _select_community(self, file):
        self._community_selected_file = file
        for card in self._community_cards:
            card.set_selected(card.profile.get("file") == file)
        self._update_community_button_states()

    def _update_community_button_states(self):
        self.community_download_btn.setEnabled(self._community_selected_file is not None)

    def _download_community_profile(self, file):
        """Fetches one profile's full JSON and saves it as a new local profile --
        reuses `unique_profile_path` (same as Create/Edit) so downloading a profile
        that collides by name with an existing local one gets its own -2/-3 file
        rather than silently overwriting it. Opens the same, already-proven
        View Profile/per-tag-import dialog on it afterward instead of building a
        second one just for community profiles."""
        if file is None:
            return
        entry = next((p for p in self._community_profiles if p.get("file") == file), None)
        if entry is None:
            return
        self._select_community(file)

        self.community_download_btn.setEnabled(False)
        self.community_refresh_btn.setEnabled(False)
        self.community_status_label.setText(f"Downloading \"{entry.get('name', file)}\"...")
        self.community_status_label.setVisible(True)

        worker = _HttpFetchWorker(COMMUNITY_BASE_URL + file, parent=self)
        worker.succeeded.connect(lambda u, body, entry=entry: self._on_community_profile_downloaded(entry, body))
        worker.failed.connect(self._on_community_download_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_community_profile_downloaded(self, entry, body):
        self.community_download_btn.setEnabled(True)
        self.community_refresh_btn.setEnabled(True)
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.community_status_label.setText("Downloaded file wasn't valid JSON -- not saved.")
            return
        if not isinstance(data, dict) or not isinstance(data.get("tags"), list):
            self.community_status_label.setText("Downloaded profile has an unexpected format -- not saved.")
            return

        # Marks this local copy as coming from Community verbatim, so its card
        # can show that (see ProfileCard) instead of looking identical to a
        # hand-made local profile with the same content -- lost on the next Edit
        # save (_edit_selected writes a fixed set of fields), which is correct:
        # once modified it's no longer literally the community file.
        data["source"] = "community"
        data["source_file"] = entry.get("file", "")

        name = str(data.get("name") or entry.get("name") or "profile")
        path = unique_profile_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.community_status_label.setVisible(False)
        self.refresh_local_profiles(reselect_path=path)
        self._set_mode("local")
        self._open_view_profile_dialog(path)

    def _on_community_download_failed(self, url, error):
        self.community_download_btn.setEnabled(True)
        self.community_refresh_btn.setEnabled(True)
        self.community_status_label.setText(f"Download failed ({error}). Try again.")
        self.community_status_label.setVisible(True)

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
            card.double_clicked.connect(lambda p=profile["_path"]: self._open_view_profile_dialog(p))
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

    def _open_view_profile_dialog(self, path):
        """Double-clicking a card selects it and opens a read-only view of it, with a
        per-tag import picker -- replaces the old instant "double-click applies
        everything" behavior. Tags already in the live Tags tab are marked green (see
        _status_dot/_group_status), so the user can tell at a glance which of the
        profile's tags would actually be new before choosing what to bring in.

        Apply doesn't close this dialog (see CreateProfileDialog's view_only docs) --
        on_apply below runs the actual import immediately, on every click, and hands
        back the fresh set of live tag names so the dialog can re-color its dots and the
        user can keep adjusting the selection and importing more in the same session."""
        self._select_path(path)
        profile = self._selected_profile()
        mw = self.parent_window
        if profile is None or mw is None:
            return

        def on_apply(selected_tags):
            imported_count, skipped_count = mw._import_additional_tag_rows(selected_tags)
            mw._apply_address_table_data(profile.get("address_table"))
            if hasattr(mw, "_log"):
                message = f"Imported {imported_count} tag(s) from profile '{profile.get('name', '')}'"
                if skipped_count:
                    message += f" ({skipped_count} already present, skipped)"
                mw._log(message)
            return {t.get("Tag Name", "") for t in mw._build_tag_export_rows()}

        live_tag_names = {t.get("Tag Name", "") for t in mw._build_tag_export_rows()}
        dialog = CreateProfileDialog(
            self._colors(), self._button_style(), preset=profile, parent=self,
            view_only=True, live_tag_names=live_tag_names, input_style=self._input_style(),
            on_apply=on_apply,
        )
        dialog.exec()

    def _update_button_states(self):
        has_selection = self._selected_profile() is not None
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)
        self.share_btn.setEnabled(has_selection)

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
        dialog = CreateProfileDialog(
            self._colors(), self._button_style(), available_tags, parent=self,
            input_style=self._input_style(),
        )
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
            "author": dialog.author(),
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
            self._colors(), self._button_style(), available_tags, preset=profile, parent=self,
            input_style=self._input_style(),
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
            "author": dialog.author(),
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

    def _share_selected_to_community(self):
        """Submits the profile directly to COMMUNITY_FORM_ENDPOINT (a Formspree
        form) as a background JSON POST -- one click, no browser, no mail
        client. Formspree emails the submission to the maintainer, who reviews
        it before adding it to community-profiles/ (see
        tools/build_community_index.py) by hand."""
        profile = self._selected_profile()
        if profile is None:
            return

        name = str(profile.get("name", "")).strip() or "Unnamed device"
        export = {k: v for k, v in profile.items() if not k.startswith("_")}
        payload = {
            "_subject": f"ModbusLens profile submission: {name}",
            "name": name,
            "manufacturer": str(profile.get("manufacturer", "")).strip(),
            "type": str(profile.get("type", "")).strip(),
            "author": str(profile.get("author", "")).strip(),
            "tag_count": len(export.get("tags") or []),
            "profile_json": json.dumps(export, indent=2),
        }
        data = json.dumps(payload).encode("utf-8")

        self.share_btn.setEnabled(False)
        self.share_btn.setText("Submitting...")

        worker = _HttpFetchWorker(
            COMMUNITY_FORM_ENDPOINT, data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            parent=self,
        )
        worker.succeeded.connect(lambda u, body, name=name: self._on_share_submitted(name))
        worker.failed.connect(self._on_share_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_share_submitted(self, name):
        self.share_btn.setEnabled(True)
        self.share_btn.setText("Share to Community")
        QMessageBox.information(
            self, "Submitted",
            f"\"{name}\" was submitted for review. A maintainer will add it to "
            "the Community list if it's accepted.",
        )
        mw = self.parent_window
        if mw is not None and hasattr(mw, "_log"):
            mw._log(f"Submitted profile '{name}' to the Community list for review")

    def _on_share_failed(self, url, error):
        self.share_btn.setEnabled(True)
        self.share_btn.setText("Share to Community")
        QMessageBox.warning(
            self, "Submission Failed",
            f"Couldn't submit this profile ({error}). Check your connection and try again.",
        )
