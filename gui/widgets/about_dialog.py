import json

from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QTextBrowser, QWidget,
)

GITHUB_REPO = "CraftParking/ModbusLens"
GITHUB_API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"

ABOUT_HTML = """
<h3>ModbusLens</h3>
<p><b>ModbusLens is free software</b> - a professional Modbus TCP/RTU client designed for
engineers working with industrial automation systems.</p>

<h4>Key Features</h4>
<ul>
<li>Modbus TCP and serial (RTU or ASCII) read/write (coils, inputs, registers)</li>
<li>Tag-based real-time monitoring, with alarms and CSV logging</li>
<li>Live/historical trend graphing</li>
<li>Server mode - act as a Modbus TCP slave</li>
<li>Scripting language for repeatable test sequences, targeting either your live connection or the local Server tab</li>
<li>Multiple simultaneous connections (one per window)</li>
<li>Network discovery & diagnostics (ARP + Modbus detection)</li>
<li>Light, Dark, and Follow-System themes</li>
</ul>

<h4>Upcoming Features</h4>
<ul>
<li>Unified multi-device dashboard</li>
<li>Register maps with mixed data types per device profile</li>
</ul>

<h4>Support</h4>
<p>If you find this tool useful, you can support development:<br>
<a href="https://buymeacoffee.com/craftparking">Buy Me a Coffee</a></p>

<h4>Links</h4>
<p>GitHub: <a href="https://github.com/{repo}">https://github.com/{repo}</a></p>

<h4>License</h4>
<p>License: Apache License 2.0</p>

<p style='margin-top: 15px;'><i>Note: Verify behavior before use in critical industrial systems.</i></p>
<hr>
<p align='center' style='color: #666666;'>&copy; 2026 ModbusLens | CraftParking</p>
""".format(repo=GITHUB_REPO)


def _parse_version(text):
    """Turn 'v2.1.0', '2.1.0-beta', etc. into a comparable tuple of ints, e.g. (2, 1, 0)."""
    text = text.strip().lstrip("vV")
    # Drop anything after the numeric dotted part (e.g. "-beta", "+build3").
    numeric = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            numeric += ch
        else:
            break
    parts = [p for p in numeric.split(".") if p != ""]
    if not parts:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


class AboutDialog(QDialog):
    """About dialog with an About tab and an Updates tab that checks GitHub Releases."""

    def __init__(self, current_version, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self._reply = None

        self.setWindowTitle("About ModbusLens")
        self.resize(560, 480)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        about_tab = QTextBrowser()
        about_tab.setOpenExternalLinks(True)
        about_tab.setHtml(f"<h3>ModbusLens v{current_version}</h3>" + ABOUT_HTML)
        tabs.addTab(about_tab, "About")

        tabs.addTab(self._build_updates_tab(), "Updates")

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

    def _build_updates_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        current_label = QLabel(f"<b>Current version:</b> {self.current_version}")
        layout.addWidget(current_label)

        self.status_label = QLabel("Click \"Check for Updates\" to see if a newer version is available.")
        self.status_label.setWordWrap(True)
        self.status_label.setOpenExternalLinks(True)
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.check_btn = QPushButton("Check for Updates")
        self.check_btn.clicked.connect(self._check_for_updates)
        button_row.addWidget(self.check_btn)

        self.releases_btn = QPushButton("Open Releases Page")
        self.releases_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(GITHUB_RELEASES_PAGE))
        )
        button_row.addWidget(self.releases_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        layout.addStretch()
        return tab

    def _check_for_updates(self):
        self.check_btn.setEnabled(False)
        self.status_label.setText("Checking GitHub for the latest release...")

        self._manager = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(GITHUB_API_LATEST_RELEASE))
        # The GitHub API rejects unauthenticated requests with no User-Agent header.
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "ModbusLens-UpdateChecker")
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._on_check_finished)

        # Unauthenticated GitHub API requests can hang past a reasonable UI wait;
        # abort instead of leaving the button disabled and the user staring at it.
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_check_timeout)
        self._timeout_timer.start(10000)

    def _on_check_timeout(self):
        if self._reply is not None:
            self._reply.abort()

    def _on_check_finished(self):
        self._timeout_timer.stop()
        self.check_btn.setEnabled(True)
        reply = self._reply
        self._reply = None
        if reply is None:
            return

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.status_label.setText(
                    f"Could not check for updates ({reply.errorString()}). "
                    f"You can check manually on the <a href='{GITHUB_RELEASES_PAGE}'>Releases page</a>."
                )
                return

            try:
                data = json.loads(bytes(reply.readAll().data()).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.status_label.setText(
                    f"Unexpected response from GitHub. You can check manually on the "
                    f"<a href='{GITHUB_RELEASES_PAGE}'>Releases page</a>."
                )
                return

            latest_tag = data.get("tag_name", "")
            release_url = data.get("html_url", GITHUB_RELEASES_PAGE)
            latest_version = _parse_version(latest_tag)
            current_version = _parse_version(self.current_version)

            if latest_version is None or current_version is None:
                self.status_label.setText(
                    f"Latest release on GitHub is <b>{latest_tag or 'unknown'}</b>. "
                    f"<a href='{release_url}'>View it here</a>."
                )
            elif latest_version > current_version:
                self.status_label.setText(
                    f"<b>A new version is available: {latest_tag}</b> (you have {self.current_version}).<br>"
                    f"<a href='{release_url}'>Download the latest release</a>."
                )
            elif latest_version < current_version:
                self.status_label.setText(
                    f"You're running {self.current_version}, newer than the latest published "
                    f"release ({latest_tag})."
                )
            else:
                self.status_label.setText(f"You're up to date - {self.current_version} is the latest version.")
        finally:
            reply.deleteLater()
