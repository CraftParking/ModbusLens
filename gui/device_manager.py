"""Devices and their connections, mixed into the main window (ModbusGUI).

Every device is a dict -- {"name", "unit", "connection": {...}} plus Overview settings
("pinned", "paused", "profile") -- configured on the Overview tab. There is always at
least one device: a fresh window starts with "Device 1" built from the classic
connection settings, and old sessions/CSVs migrate onto it. Devices with identical
connection settings share one link (see device_links.LinkPool).

Each tool picks its own device (widgets/device_selector.py); there is no user-facing active
device. `active_device` survives internally as the *default* device: `self.modbus` is a
DeviceView of it and the classic connection attributes (connection_mode, target_ip, ...)
mirror its settings for the Connection Settings dialog and other legacy single-device code.
"""

import json
import os
import sys

from PySide6.QtWidgets import QComboBox, QDialog, QInputDialog, QLineEdit, QMenu, QMessageBox

from app_paths import app_data_dir
from device_links import DeviceView, LinkPool, describe, link_key, normalize_connection
from widgets.tag_devices import ADD_DEVICE_SENTINEL, TAG_DEVICE_COLUMN, DeviceDialog
from widgets.overview_widget import DEFAULT_PINNED

DEVICES_FILE = "devices.json"


class DeviceManagerMixin:
    _devices_file_owner = None  # the one window that loads/saves devices.json

    # ------------------------------------------------------------------ model --
    def _init_devices(self):
        """Called once at the end of __init__: restore the saved device list (first
        window only -- extra windows are independent), else start with "Device 1"."""
        self.link_pool = getattr(self, "link_pool", None) or LinkPool()
        self._connected_devices = set()
        if DeviceManagerMixin._devices_file_owner is None and not os.environ.get("MODBUSLENS_NO_DEVICE_FILE"):
            DeviceManagerMixin._devices_file_owner = self
        if DeviceManagerMixin._devices_file_owner is self:
            for saved in self._read_devices_file():
                self._add_device_record(saved)
        self._ensure_default_device()
        self.active_device = self.tag_devices[0]["name"]
        self._refresh_tag_device_ui()
        self._sync_active_device()

    def _device(self, name):
        return next((d for d in self.tag_devices if d["name"] == name), None)

    def _device_meta(self, key):
        return self._device(key) or {}

    def _legacy_connection(self):
        return normalize_connection({
            "mode": self.connection_mode, "ip": self.target_ip, "port": self.target_port,
            "serial_port": self.serial_port, "baudrate": self.baudrate, "parity": self.parity,
            "stopbits": self.stopbits, "bytesize": self.bytesize, "serial_framer": self.serial_framer,
            "tcp_framer": self.tcp_framer, "fast_lan_mode": self.fast_lan_mode, "interface_ip": self.interface_ip,
        })

    def _device_connection(self, name):
        device = self._device(name)
        return normalize_connection(device.get("connection") if device else None)

    def _add_device_record(self, saved, default_connection=None):
        """Append a device from saved/imported data; returns the stored dict or None."""
        name = str(saved.get("name", "")).strip()
        try:
            unit = int(saved.get("unit"))
        except (TypeError, ValueError):
            return None
        if not name or self._device(name):
            return None
        device = {"name": name, "unit": unit,
                  "connection": normalize_connection(saved.get("connection") or default_connection
                                                     or self._legacy_connection())}
        for key in ("pinned", "paused", "profile"):
            if key in saved:
                device[key] = saved[key]
        self.tag_devices.append(device)
        return device

    def _ensure_default_device(self):
        if not self.tag_devices:
            self.tag_devices.append({"name": "Device 1", "unit": int(self.target_unit_id),
                                     "connection": self._legacy_connection()})

    def _tag_device_unit(self, name):
        device = self._device(name)
        return device["unit"] if device else None

    def _device_is_connected(self, name):
        if name not in self._connected_devices:
            return False
        link = self.link_pool.links.get(link_key(self._device_connection(name)))
        return bool(link and link.is_connected())

    def _device_client(self, name):
        """The raw link client a device's requests go through, or None if the device
        isn't connected (its tags are then skipped by polling, and writes refuse)."""
        if name not in self._connected_devices:
            return None
        link = self.link_pool.links.get(link_key(self._device_connection(name)))
        return link.client if link and link.client else None

    def _device_view(self, name):
        """A DeviceView (the device's link + its Unit ID) for `name`, or None while it
        isn't connected -- what each tool's Device selector talks through."""
        client = self._device_client(name)
        unit = self._tag_device_unit(name)
        return DeviceView(client, unit) if client is not None and unit is not None else None

    def _describe_device(self, name):
        device = self._device(name)
        if device is None:
            return ""
        return f"{name} -- {describe(normalize_connection(device['connection']))}, Unit {device['unit']}"

    def _refresh_device_selectors(self, renamed=None):
        for selector in list(getattr(self, "_device_selectors", [])):
            try:
                selector.refresh(renamed)
            except RuntimeError:  # its widget was deleted
                self._device_selectors.remove(selector)

    def _serial_port_in_use(self, port):
        """True if a connected device's link holds this COM port open."""
        port = (port or "").strip().upper()
        for name in self._connected_devices:
            conn = self._device_connection(name)
            if conn["mode"] == "serial" and (conn["serial_port"] or "").strip().upper() == port:
                return True
        return False

    def _any_device_connected(self):
        return any(self._device_is_connected(d["name"]) for d in self.tag_devices)

    def _device_link_state(self, name):
        """"connected" / "reconnecting" / "failed" / "disconnected" for status displays."""
        if name in self._connected_devices:
            link = self.link_pool.links.get(link_key(self._device_connection(name)))
            if link and link.is_connected():
                return "connected"
            return "reconnecting"
        return "failed" if name in getattr(self, "_failed_devices", set()) else "disconnected"

    def _device_paused(self, key):
        return bool(self._device_meta(key).get("paused"))

    def _device_pinned(self, key):
        meta = self._device_meta(key)
        if "pinned" in meta:
            return list(meta["pinned"])
        names = [t["name"] for t in self._get_monitoring_tags() if t.get("device", "") == key]
        return names[:DEFAULT_PINNED]

    def _tag_display_value(self, tag):
        table = self.monitoring_tag_table
        for column in (12, 7):
            widget = table.cellWidget(tag["row"], column)
            text = widget.text().strip() if isinstance(widget, QLineEdit) else ""
            if text:
                return text
        return ""

    # --------------------------------------------------------- default device --
    # There's no user-facing "active device": every tool has its own Device selector.
    # `active_device` survives internally as the *default* device -- where a tag goes
    # when nothing else says, whose settings the classic single-connection attributes
    # (connection_mode, target_ip, ... and self.modbus) mirror for the Connection
    # Settings dialog, connection history and other legacy single-device code.
    def _ask_device_for_settings(self):
        """Which device a Connection Settings change is for: the only device, else the
        user's pick among the disconnected ones (None = cancelled / nothing editable)."""
        if len(self.tag_devices) == 1:
            return self.tag_devices[0]["name"]
        free = [d["name"] for d in self.tag_devices if d["name"] not in self._connected_devices]
        if not free:
            QMessageBox.information(self, "Connection Settings",
                                    "Every device is connected -- disconnect the one to change first.")
            return None
        labels = {f"{n} -- {describe(self._device_connection(n))}, Unit {self._tag_device_unit(n)}": n for n in free}
        choice, ok = QInputDialog.getItem(self, "Connection Settings", "Apply to which device?", list(labels), 0, False)
        return labels[choice] if ok else None

    def _device_settings_clicked(self):
        """Top bar Device Settings: edit one device's connection (pick which when there
        are several; connected devices are disabled -- disconnect first)."""
        if len(self.tag_devices) == 1:
            name = self.tag_devices[0]["name"]
        else:
            menu = QMenu(self)
            for d in self.tag_devices:
                action = menu.addAction(f"{d['name']} -- {describe(normalize_connection(d['connection']))}, "
                                        f"Unit {d['unit']}")
                action.setData(d["name"])
                if d["name"] in self._connected_devices:
                    action.setEnabled(False)
                    action.setText(action.text() + "  (connected)")
            chosen = menu.exec(self.settings_btn.mapToGlobal(self.settings_btn.rect().bottomLeft()))
            if chosen is None:
                return
            name = chosen.data()
        if name in self._connected_devices:
            QMessageBox.information(self, "Device Settings", f"Disconnect {name} before changing its settings.")
            return
        self._show_connection_settings(device=name)

    def _sync_active_device(self):
        """Point the classic single-connection state at the default device."""
        device = self._device(self.active_device)
        if device is None:
            device = self.tag_devices[0]
            self.active_device = device["name"]
        conn = normalize_connection(device["connection"])
        self.connection_mode = conn["mode"]
        self.target_ip, self.target_port = conn["ip"], conn["port"]
        self.serial_port, self.baudrate, self.parity = conn["serial_port"], conn["baudrate"], conn["parity"]
        self.stopbits, self.bytesize, self.serial_framer = conn["stopbits"], conn["bytesize"], conn["serial_framer"]
        self.tcp_framer, self.fast_lan_mode, self.interface_ip = conn["tcp_framer"], conn["fast_lan_mode"], conn["interface_ip"]
        self.target_unit_id = device["unit"]
        client = self._device_client(device["name"])
        self.modbus = DeviceView(client, device["unit"]) if client is not None else None
        self._update_connection_info()
        if hasattr(self, "connection_status"):
            n_connected = sum(1 for d in self.tag_devices if self._device_is_connected(d["name"]))
            self.connection_status.setText(f"{n_connected} of {len(self.tag_devices)} device(s) connected")
        self._refresh_connection_controls()
        if hasattr(self, "device_status_bar"):
            self.device_status_bar.refresh()
        if hasattr(self, "overview_widget"):
            self.overview_widget.refresh()

    def _refresh_connection_controls(self):
        active_connected = self.modbus is not None and self.modbus.is_connected()
        any_connected = self._any_device_connected()
        self._set_connection_controls(connected=active_connected)
        # Top bar: Connect All / Disconnect All / Device Settings (of the active device).
        self.connect_btn.setEnabled(any(d["name"] not in self._connected_devices for d in self.tag_devices))
        self.disconnect_btn.setEnabled(bool(self._connected_devices))
        self.settings_btn.setEnabled(any(d["name"] not in self._connected_devices for d in self.tag_devices))
        if hasattr(self, "tag_start_monitoring_btn"):
            self.tag_start_monitoring_btn.setEnabled(any_connected and not self.monitoring_active)
            self.tag_stop_monitoring_btn.setEnabled(self.monitoring_active)

    # ---------------------------------------------------------------- connect --
    def _connect_device(self, name, interactive=True):
        device = self._device(name)
        if device is None:
            return False
        failed = getattr(self, "_failed_devices", set())
        self._failed_devices = failed
        conn = normalize_connection(device["connection"])
        ok, error = self.link_pool.open(conn)
        if ok:
            self._connected_devices.add(name)
            failed.discard(name)
            self._log(f"Connected {name} -- {describe(conn)} (Unit {device['unit']})")
            if name == self.active_device:
                self._write_confirm_suppressed = False
            self._reconnect_watchdog_timer.start(self.WATCHDOG_HEALTHY_INTERVAL_MS)
        else:
            failed.add(name)
            self._log(f"Failed to connect {name} -- {describe(conn)}: {error}")
            if interactive:
                self._show_device_connection_error(device, error)
        self._sync_active_device()
        if ok and name == self.active_device:
            self._apply_pending_write_bounds()
        if ok:
            self._record_device_history(device)
        return ok

    def _record_device_history(self, device):
        if device["name"] != self.active_device:
            return
        self._record_connection_history()
        self._save_settings()

    def _disconnect_device(self, name):
        if name not in self._connected_devices:
            return
        key = link_key(self._device_connection(name))
        others = [d for d in self._connected_devices
                  if d != name and link_key(self._device_connection(d)) == key]
        self._connected_devices.discard(name)
        if not others:
            # Nothing else uses this link: make sure no worker is mid-request on it.
            if hasattr(self, "register_scanner_widget"):
                self.register_scanner_widget.stop_all_scans()
            self.monitoring_manager.wait_for_idle()
            self.link_pool.close(key)
        self._log(f"Disconnected {name}")
        if not self._connected_devices:
            self._reconnect_watchdog_timer.stop()
            if self.monitoring_active:
                self._stop_monitoring()
        self._sync_active_device()

    def _connect(self):
        """Connect All."""
        failures = []
        for device in list(self.tag_devices):
            if device["name"] not in self._connected_devices and not self._connect_device(device["name"], interactive=False):
                failures.append(f"{device['name']} ({describe(device['connection'])}): "
                                f"{self.link_pool.link_for(device['connection']).last_error}")
        if failures:
            QMessageBox.warning(self, "Connect All", "These devices couldn't connect:\n\n" + "\n".join(failures))

    def _disconnect(self):
        """Disconnect All."""
        self._reconnect_watchdog_timer.stop()
        self._monitoring_paused_by_disconnect = False
        if hasattr(self, "register_scanner_widget"):
            self.register_scanner_widget.stop_all_scans()
        self.monitoring_manager.wait_for_idle()
        if self.monitoring_active:
            self._stop_monitoring()
        for key in list(self.link_pool.links):
            self.link_pool.close(key)
        had = bool(self._connected_devices)
        self._connected_devices.clear()
        if had:
            self._log("Disconnected all devices")
        self._sync_active_device()

    def _check_connection_watchdog(self):
        """Auto-reconnect, per link: a dropped link with connected devices is retried with
        backoff; monitoring auto-stopped by the drop restarts once it's back."""
        wanted = {link_key(self._device_connection(n)) for n in self._connected_devices}
        if not wanted:
            return
        for key, event in self.link_pool.watchdog_tick(wanted):
            names = ", ".join(sorted(n for n in self._connected_devices
                                     if link_key(self._device_connection(n)) == key))
            if event == "lost":
                self._log(f"Connection lost ({names}) - reconnecting")
            elif event == "reconnected":
                self._log(f"Reconnected ({names})")
                if self._monitoring_paused_by_disconnect:
                    self._monitoring_paused_by_disconnect = False
                    self._start_monitoring()
        self._sync_active_device()
        self._reconnect_watchdog_timer.start(self.WATCHDOG_HEALTHY_INTERVAL_MS)

    def _show_device_connection_error(self, device, error):
        conn = normalize_connection(device["connection"])
        if conn["mode"] == "serial":
            tips = ("Check that the COM port exists and isn't open in another program, that baud/parity/"
                    "stop bits match the device, and the cable/adapter.")
        else:
            tips = ("Check the IP address and port, network reachability (VPN/Tailscale routes too), "
                    "and that the device/gateway accepts another connection.")
        QMessageBox.warning(self, "Connection Failed",
                            f"Couldn't connect {device['name']} -- {describe(conn)}, Unit {device['unit']}.\n\n"
                            f"{error or 'Connection failed'}\n\n{tips}")

    # ------------------------------------------------------------ persistence --
    def _devices_path(self):
        return app_data_dir() / DEVICES_FILE

    def _read_devices_file(self):
        try:
            with open(self._devices_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return [d for d in data.get("devices", []) if isinstance(d, dict)]
        except (OSError, ValueError, AttributeError):
            return []

    def _save_devices(self):
        if DeviceManagerMixin._devices_file_owner is not self:
            return
        try:
            path = self._devices_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "devices": [dict(d) for d in self.tag_devices]}, f, indent=2)
        except OSError as e:
            self._log(f"Couldn't save devices: {e}")

    # ------------------------------------------------------- Tags device UI --
    def _row_device(self, row):
        widget = self.monitoring_tag_table.cellWidget(row, TAG_DEVICE_COLUMN)
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            if data and data != ADD_DEVICE_SENTINEL:
                return data
        return self.active_device if getattr(self, "active_device", None) else ""

    def _default_tag_device(self):
        """Where a new tag goes: the open device tab, else the active device."""
        return self._tag_device_filter or self.active_device

    def _fill_device_combo(self, combo, selected):
        combo.blockSignals(True)
        combo.clear()
        for device in self.tag_devices:
            combo.addItem(f"{device['name']} ({device['unit']})", device["name"])
        combo.addItem(ADD_DEVICE_SENTINEL, ADD_DEVICE_SENTINEL)
        index = combo.findData(selected)
        if index < 0:
            index = combo.findData(getattr(self, "active_device", None))
        combo.setCurrentIndex(max(index, 0))
        combo.blockSignals(False)

    def _refresh_tag_device_ui(self, renamed=None):
        """Re-sync everything that shows the device list (row combos following a
        rename, the Device column + device tabs -- shown once there are 2+ devices),
        then persist the list."""
        renamed = renamed or {}
        names = {d["name"] for d in self.tag_devices}
        table = self.monitoring_tag_table
        for row in range(table.rowCount()):
            widget = table.cellWidget(row, TAG_DEVICE_COLUMN)
            if isinstance(widget, QComboBox):
                data = widget.currentData()
                current = renamed.get(data, data)
                self._fill_device_combo(widget, current if current in names else self.active_device)
        multi = len(self.tag_devices) > 1
        table.setColumnHidden(TAG_DEVICE_COLUMN, not multi)
        if self._tag_device_filter:
            self._tag_device_filter = renamed.get(self._tag_device_filter, self._tag_device_filter)
            if self._tag_device_filter not in names:
                self._tag_device_filter = None
        if getattr(self, "active_device", None) in renamed:
            self.active_device = renamed[self.active_device]
        self._rebuild_tag_device_tabs()
        self._apply_tag_row_visibility()
        if hasattr(self, "diagnostics_dialogs"):
            self.diagnostics_dialogs.refresh_device_filter(renamed)
        self._refresh_device_selectors(renamed)
        self._save_devices()
        if hasattr(self, "device_status_bar"):
            self.device_status_bar.refresh()

    def _rebuild_tag_device_tabs(self):
        tabs = self.tag_device_tabs
        tabs.blockSignals(True)
        while tabs.count():
            tabs.removeTab(0)
        multi = len(self.tag_devices) > 1
        if multi:
            entries = [("All", None)] + [(f"{d['name']} ({d['unit']})", d["name"]) for d in self.tag_devices]
            for label, key in entries:
                tabs.setTabData(tabs.addTab(label), key)
            tabs.setTabData(tabs.addTab("+"), ADD_DEVICE_SENTINEL)
            tabs.setTabToolTip(tabs.count() - 1, "Add a device")
            current = next((i for i in range(tabs.count()) if tabs.tabData(i) == self._tag_device_filter), 0)
            tabs.setCurrentIndex(current)
        tabs.setVisible(multi)
        tabs.blockSignals(False)

    def _on_tag_device_tab_changed(self, index):
        key = self.tag_device_tabs.tabData(index)
        if key == ADD_DEVICE_SENTINEL:
            if self._add_tag_device_interactive() is None:
                self._rebuild_tag_device_tabs()
            return
        self._tag_device_filter = key
        self._apply_tag_row_visibility()

    def _show_tags_for_device(self, key):
        """Overview's Open Tags: switch to the Tags tab, on that device's own tab."""
        self._tag_device_filter = key if len(self.tag_devices) > 1 else None
        self._rebuild_tag_device_tabs()
        self._apply_tag_row_visibility()
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Tags":
                self.tab_widget.setCurrentIndex(i)
                break

    def _show_device_card(self, key):
        """Top-bar click: open the Overview tab on that device's card."""
        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == "Overview":
                self.tab_widget.setCurrentIndex(i)
                break
        if hasattr(self, "overview_widget"):
            self.overview_widget.show_device(key)

    def _show_tag_device_tab_menu(self, pos):
        index = self.tag_device_tabs.tabAt(pos)
        name = self.tag_device_tabs.tabData(index) if index >= 0 else None
        if not name or name == ADD_DEVICE_SENTINEL:
            return
        menu = QMenu(self)
        edit_action = menu.addAction("Edit Device...")
        remove_action = menu.addAction("Remove Device...")
        chosen = menu.exec(self.tag_device_tabs.mapToGlobal(pos))
        if chosen == edit_action:
            self._edit_tag_device(name)
        elif chosen == remove_action:
            self._remove_tag_device(name)

    def _on_monitoring_tag_device_changed(self, _index=None):
        if self._updating_tag_table:
            return
        sender = self.sender()
        row = self._find_monitoring_tag_row(sender, TAG_DEVICE_COLUMN)
        if row is None:
            return
        if sender.currentData() == ADD_DEVICE_SENTINEL:
            device = self._add_tag_device_interactive()
            combo = self.monitoring_tag_table.cellWidget(row, TAG_DEVICE_COLUMN)
            if isinstance(combo, QComboBox):
                self._fill_device_combo(combo, device["name"] if device else self.active_device)
        self._ensure_unique_monitoring_tag_address(row)
        self._apply_tag_row_visibility()

    # ------------------------------------------------------------ device CRUD --
    def _edit_connection_dialog(self, conn, unit):
        """The classic Connection Settings dialog, for one device's connection.
        Returns (connection, unit) or None on Cancel."""
        conn = normalize_connection(conn)
        current = _ConnectionView(conn, unit)
        dialog_cls = sys.modules[type(self).__module__].ConnectionSettingsDialog
        dialog = dialog_cls(self, self.connection_history, current)
        if dialog.exec() != QDialog.Accepted:
            return None
        vals = dialog.get_values()
        self.connection_history = vals.get("history", self.connection_history)
        self._save_settings()
        return normalize_connection(vals), int(vals["unit"])

    def _new_device_dialog(self, device=None):
        default_conn = self._device_connection(self.active_device) if getattr(self, "active_device", None) else None
        return DeviceDialog(self.tag_devices, device=device, input_style=self._get_input_style(), parent=self,
                            default_connection=default_conn, edit_connection=self._edit_connection_dialog)

    def _add_tag_device_interactive(self):
        dialog = self._new_device_dialog()
        if dialog.exec() != QDialog.Accepted:
            return None
        device = dialog.device()
        self._add_tag_device(device, show_tab=True)
        self._log(f"Added device '{device['name']}' -- {describe(device['connection'])}, Unit {device['unit']}")
        return device

    def _add_tag_device(self, device, show_tab=False):
        device.setdefault("connection", self._device_connection(self.active_device)
                          if getattr(self, "active_device", None) else self._legacy_connection())
        device["connection"] = normalize_connection(device["connection"])
        self.tag_devices.append(device)
        if show_tab and len(self.tag_devices) > 1:
            self._tag_device_filter = device["name"]
        self._refresh_tag_device_ui()

    def _edit_tag_device(self, name):
        device = self._device(name)
        if device is None:
            return
        if name in self._connected_devices:
            QMessageBox.information(self, "Edit Device", f"Disconnect {name} before changing its settings.")
            return
        dialog = self._new_device_dialog(device=device)
        if dialog.exec() != QDialog.Accepted:
            return
        updated = dialog.device()
        device.update(updated)
        stats = self.monitoring_manager.device_stats
        renamed = {name: updated["name"]} if updated["name"] != name else None
        if renamed and name in stats:
            stats[updated["name"]] = stats.pop(name)
        self._refresh_tag_device_ui(renamed=renamed)
        self._sync_active_device()
        self._log(f"Device '{updated['name']}' -- {describe(updated['connection'])}, Unit {updated['unit']}")

    def _remove_tag_device(self, name, choice=None):
        """choice skips the dialog (tests): "keep" moves the device's tags to the active
        (or first remaining) device, "delete" removes them along with the device."""
        if len(self.tag_devices) <= 1:
            QMessageBox.information(self, "Remove Device", "The last device can't be removed -- edit it instead.")
            return
        rows = [r for r in range(self.monitoring_tag_table.rowCount())
                if r not in self.monitoring_manager.group_header_rows
                and r not in self.monitoring_manager.tag_bit_rows and self._row_device(r) == name]
        remaining = [d["name"] for d in self.tag_devices if d["name"] != name]
        heir = self.active_device if self.active_device != name else remaining[0]
        if choice is None:
            box = QMessageBox(self)
            box.setWindowTitle("Remove Device")
            box.setIcon(QMessageBox.Question)
            keep_btn = delete_btn = None
            if rows:
                box.setText(f"Remove device '{name}'? It has {len(rows)} tag(s).")
                keep_btn = box.addButton(f"Keep Tags (move to {heir})", QMessageBox.AcceptRole)
                delete_btn = box.addButton("Delete Its Tags Too", QMessageBox.DestructiveRole)
            else:
                box.setText(f"Remove device '{name}'?")
                keep_btn = box.addButton("Remove", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked is keep_btn:
                choice = "keep"
            elif delete_btn is not None and clicked is delete_btn:
                choice = "delete"
            else:
                return
        self._disconnect_device(name)
        if choice == "delete" and rows:
            self._remove_tag_rows(rows)
        elif choice == "keep":
            for row in rows:
                combo = self.monitoring_tag_table.cellWidget(row, TAG_DEVICE_COLUMN)
                if isinstance(combo, QComboBox):
                    self._fill_device_combo(combo, heir)
        self.tag_devices = [d for d in self.tag_devices if d["name"] != name]
        self.monitoring_manager.device_stats.pop(name, None)
        if self.active_device == name:
            self.active_device = heir
        self._refresh_tag_device_ui()
        if choice == "keep":
            for row in rows:
                self._ensure_unique_monitoring_tag_address(row)
        self._sync_active_device()
        self._log(f"Removed device '{name}'" + (" and its tags" if choice == "delete" else f"; its tags moved to {heir}"))

    def _remove_all_tag_devices(self, confirm=True):
        """Overview's Remove All Devices: disconnect and delete every device and all their
        tags, leaving a blank "Device 1" (there is always one) on the active device's
        connection settings. Returns True if done."""
        tag_count = sum(1 for r in range(self.monitoring_tag_table.rowCount())
                        if r not in self.monitoring_manager.group_header_rows
                        and r not in self.monitoring_manager.tag_bit_rows)
        if confirm:
            box = QMessageBox(self)
            box.setWindowTitle("Remove All Devices")
            box.setIcon(QMessageBox.Warning)
            box.setText(f"Remove all {len(self.tag_devices)} device(s) and their {tag_count} tag(s)?")
            box.setInformativeText(
                "Every device is disconnected and deleted, along with all of its tags, alarms, "
                "scaling and pinned values. This can't be undone -- Export CSV or Save Session first "
                "if you might need them.\n\nYou'll start again with one blank device (Device 1) "
                "using the first device's connection settings.")
            remove_btn = box.addButton("Remove All Devices", QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is not remove_btn:
                return False
        conn = self._device_connection(self.tag_devices[0]["name"])
        self._disconnect()
        self._remove_tag_rows([r for r in range(self.monitoring_tag_table.rowCount())
                               if r not in self.monitoring_manager.group_header_rows
                               and r not in self.monitoring_manager.tag_bit_rows])
        self.monitoring_manager.tag_alarms.clear()
        self.monitoring_manager.device_stats.clear()
        self.tag_devices = [{"name": "Device 1", "unit": 1, "connection": conn}]
        self.active_device = "Device 1"
        self._tag_device_filter = None
        self._refresh_tag_device_ui()
        self._sync_active_device()
        self._log(f"Removed all devices and {tag_count} tag(s); started over with Device 1")
        return True

    def _ensure_tag_devices(self, entries, connection=None):
        """Create devices referenced by imported rows that don't exist yet. entries:
        (name, unit) pairs; new ones use `connection` (default: the active device's)."""
        added = False
        conn = connection or self._device_connection(self.active_device)
        for name, unit in entries:
            if name and not self._device(str(name).strip()):
                if self._add_device_record({"name": name, "unit": unit}, default_connection=conn):
                    added = True
                elif str(name).strip():
                    self._log(f"Device '{name}' has no valid Unit ID -- its tags go to {self.active_device}")
        return added


class _ConnectionView:
    """The attribute shape ConnectionSettingsDialog reads its initial values from."""

    def __init__(self, conn, unit):
        self.connection_mode = conn["mode"]
        self.target_ip, self.target_port, self.target_unit_id = conn["ip"], conn["port"], unit
        self.serial_port, self.baudrate, self.parity = conn["serial_port"], conn["baudrate"], conn["parity"]
        self.stopbits, self.bytesize, self.serial_framer = conn["stopbits"], conn["bytesize"], conn["serial_framer"]
        self.tcp_framer, self.fast_lan_mode, self.interface_ip = conn["tcp_framer"], conn["fast_lan_mode"], conn["interface_ip"]
