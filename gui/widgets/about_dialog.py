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
GITHUB_ISSUES_PAGE = f"https://github.com/{GITHUB_REPO}/issues"

ABOUT_HTML = """
<h3>ModbusLens</h3>
<p><b>ModbusLens is free software</b> - a professional Modbus TCP/RTU client designed for
engineers working with industrial automation systems. It combines Modbus communication,
real-time monitoring, scripting, a device simulator, and network diagnostics in one tool.</p>

<h4>Support</h4>
<p>If you find this tool useful, you can support development:<br>
<a href="https://buymeacoffee.com/craftparking">Buy Me a Coffee</a></p>
<p>Donations go strictly toward development of ModbusLens (time, tools, hardware for
testing) - nothing else.</p>

<h4>Found a Bug? Have Feedback?</h4>
<p>Report issues or suggest features on GitHub:<br>
<a href="{issues}">{issues}</a></p>

<h4>GitHub</h4>
<p><a href="https://github.com/{repo}">https://github.com/{repo}</a></p>

<h4>License</h4>
<p>Apache License 2.0</p>

<p style='margin-top: 15px;'><i>Note: Verify behavior before use in critical industrial systems.</i></p>
<hr>
<p align='center' style='color: #666666;'>&copy; 2026 ModbusLens | CraftParking</p>
""".format(repo=GITHUB_REPO, issues=GITHUB_ISSUES_PAGE)

# Every feature of the current build, grouped the same way as the README's Features section.
FEATURES_HTML = """
<h4>Modbus TCP & RTU</h4>
<ul>
<li>Read coils, discrete inputs, holding registers, and input registers</li>
<li>Write single/multiple coils & registers</li>
<li>Modbus TCP (IP/Port/Unit ID) or Modbus Serial (COM port, baud, parity, stop bits, byte size, and RTU/ASCII framing) - pick per connection in Settings</li>
<li>Address table for quick testing</li>
<li>Optional Min/Max write bounds per register - a write outside the range is rejected before it reaches the device, whether it came from the Address Table, Tags, or a Script</li>
<li>Auto-reconnect with backoff after an unexpected drop, and automatic resume of Tags monitoring once the connection recovers</li>
<li>Multiple simultaneous connections via independent windows (File > New Connection Window)</li>
</ul>

<h4>Data Handling</h4>
<ul>
<li>BOOL, U16/S16, U32/S32/F32, U64/S64/F64, HEX support</li>
<li>BOOL on a register shows the full 16-bit pattern, not just a single flag</li>
<li>Word order handling (*_SWAP)</li>
<li>0-based / 1-based addressing, selectable per Address Table range and per Tag</li>
<li>Raw hex value shown alongside the decoded value, in both the Address Table and Tags</li>
</ul>

<h4>Monitoring</h4>
<ul>
<li>Real-time tag monitoring, with Read Value/Write Value/Timestamp built into the same Tags table</li>
<li>Insert new tags anywhere in the list (new tags drop in below the selected row), not just at the end</li>
<li>Drag and drop to reorder rows, preserving live values and alarm config</li>
<li>Write to a tag while monitoring stays active</li>
<li>A single misconfigured or failing tag no longer stops the rest of the list from updating</li>
<li>Per-tag alarms (High/Low limits, or ON/OFF for coils/discrete/BOOL) with red highlighting</li>
<li>Log live tag values to CSV</li>
<li>CSV import/export</li>
</ul>

<h4>Raw Data</h4>
<ul>
<li>One row per Modbus transaction: time, operation, raw value in decimal and hex, Success/Failed status, and round-trip latency</li>
<li>TX/RX Bytes - the literal bytes sent and received on the wire for that transaction, one level more raw than the decoded register values</li>
<li>Color-coded status (green success, red failure) at a glance</li>
<li>Filter by tag name/address/value, and by Success/Failed status, live as new rows arrive</li>
<li>Show Statistics - total requests, success/failure counts, and average/min/max response times across everything logged</li>
<li>Capped at 1000 rows so it can't grow unbounded; oldest rows fall off automatically</li>
</ul>

<h4>Trend</h4>
<ul>
<li>Up to 20 pens, each bound to a Holding/Input Register address and numeric format</li>
<li>Live mode (follows the current time) or Historical mode (view stays put while data keeps recording)</li>
<li>Adjustable time window, zoom in/out, and a From/To jump to a specific past range</li>
<li>Graph Properties: axis titles, background/axis/grid colors, grid on/off, Y-axis auto or manual range</li>
<li>Log plotted values to CSV</li>
<li>Print to PNG or PDF</li>
</ul>

<h4>Server Mode</h4>
<ul>
<li>Act as a Modbus TCP slave so another master can poll ModbusLens directly, on the Unit ID you configure</li>
<li>Coils, Discrete Inputs, Holding Registers, and Input Registers are all editable live, as if you were the field device</li>
<li>Useful for testing your own SCADA/PLC program without real hardware</li>
</ul>

<h4>Scripting</h4>
<ul>
<li>A small, purpose-built test-sequence language instead of embedded Python - no imports, no client objects, no exception handling to write, just e.g. WRITE HR 1 = 100</li>
<li>WRITE, READ, WAIT, LOG, LET, REPEAT...END, REPEAT UNTIL...END, IF...THEN</li>
<li>Runs step by step without freezing the UI, with a console showing what ran</li>
<li>Target either a live connected device (Client-target) or ModbusLens's own Server simulator (Server-target)</li>
<li>Live Variables panel next to the editor shows every LET variable's current value while the script runs</li>
<li>Insert Tag menu drops a reference to any tag from your Tags list straight into the script</li>
<li>Live CPU usage indicator, useful for spotting a runaway loop</li>
<li>Steps never run faster than a 20ms floor, even if a script uses WAIT 0 or skips WAIT entirely</li>
</ul>

<h4>Network Diagnostics</h4>
<ul>
<li>ARP-based discovery (no IP needed)</li>
<li>Automatic Modbus device detection</li>
<li>Continuous live scanning (no repeated manual scans)</li>
<li>Packet capture (Npcap required)</li>
<li>Device filtering (Modbus only)</li>
<li>IP Configuration tool - read-only view of this machine's own network adapters</li>
</ul>

<h4>Serial Discovery</h4>
<ul>
<li>Diagnostics menu tool that sweeps common baud rate/parity/stop-bit combinations, plus a Unit ID range, against a COM port to find which one a serial device actually speaks</li>
<li>Opens its own short-lived connection per combination (byte size fixed at 8), so it needs the port free</li>
<li>A "Scan for Connection Parameters..." button in Connection Settings' Serial section opens Serial Discovery directly, with the COM port already filled in</li>
</ul>

<h4>Scanner</h4>
<ul>
<li>Auto-discovers which addresses respond for a chosen function type (Coils/Discrete Inputs/Holding/Input Registers) over a given range</li>
<li>Works the same way whether the current connection is TCP or serial</li>
<li>Probes the largest block the function allows first, and only narrows down address-by-address where a block doesn't fully respond</li>
<li>Reuses the app's existing connection, pausing Tags/Address Table live monitoring (and the reconnect watchdog) first</li>
<li>A configurable probe timeout keeps scanning fast over TCP; over serial each probe is one bus round-trip</li>
</ul>

<h4>UI</h4>
<ul>
<li>Light/Dark/Follow System theme, switchable from View > Theme (takes effect after restart)</li>
<li>Color-coded logs (Address Table, System Logs, Script console) - writes in blue, connection events in green, errors in red</li>
<li>Compact connection bar with clear status indicators</li>
<li>Help > About has an Updates tab that checks GitHub Releases for a newer version</li>
</ul>
"""

# Newest first. Older releases are summarized at a higher level than the current one -
# see the git history/README for exact commit-level detail on those.
CHANGELOG_HTML = """
<h3>v2.1.0 <span style='color:#888;font-size:small;'>(current)</span></h3>
<p><u>New</u></p>
<ul>
<li>Light/dark theme, with a "follow system" option</li>
<li>Scanner tab: auto-discover which register/coil addresses actually respond on a connected device</li>
<li>Diagnostics > Serial Discovery: sweep baud rate, parity, stop bits, and Unit ID to find a serial device's connection settings when they're not documented</li>
<li>Auto-reconnect with backoff, and monitoring auto-resumes once the connection comes back</li>
<li>Modbus ASCII framing support for serial connections (previously RTU only)</li>
<li>Raw Data is now its own tab: a transaction table showing wire bytes and real request/response diagnostics for every read/write, filterable by tag/address/status</li>
<li>Scripting: REPEAT UNTIL loops and a live variables panel</li>
<li>Drag-and-drop row reordering in the Tags table</li>
<li>Write bounds for registers (reject a write outside a configured min/max)</li>
<li>IP Configuration tool added to the Tools menu</li>
<li>Update checker on the About page</li>
<li>Modbus exception codes (Illegal Function, Illegal Data Address, etc.) are now tracked and shown, not just a generic error</li>
</ul>
<p><u>Fixed</u></p>
<ul>
<li>Scanner and Serial Discovery could race with the auto-reconnect watchdog or a manual Disconnect while a scan was running, and closing the app mid-scan could abort the process instead of shutting down cleanly</li>
<li>Server tab's Unit ID field did nothing - the simulator answered on any unit ID regardless of what was configured</li>
<li>Server tab: viewing a wide Start Address + Count range could silently read/write into the next data space's storage</li>
<li>Server tab: stopping and immediately restarting on the same port could spuriously fail with "address already in use"</li>
<li>Network Discovery's subnet check always used the machine's hostname instead of the network interface you actually selected, so real devices could be wrongly marked unreachable on a multi-homed PC</li>
<li>Network Discovery's IP address field accepted invalid input (like 10.0.0.999) without validation</li>
<li>Monitoring's auto-stop-after-repeated-failures didn't actually stop - it restarted itself immediately, so polling never really died</li>
<li>Importing an empty/malformed CSV showed a raw Python error instead of a clear message</li>
<li>One bad tag address could stop polling for every other tag</li>
<li>Missing spinbox up/down arrows on Windows</li>
<li>Crash in exception-code lookup when there was no last error</li>
<li>Log auto-scroll would force-follow even when you'd scrolled up to read something</li>
<li>Tags table row drag-and-drop wasn't working, and row reordering was off by one</li>
<li>Tags table stayed resizable/writable while monitoring was active, and right-click "Configure Alarm" could fail to appear</li>
<li>Tag address field blocked typing certain values</li>
<li>Tag order in the Tags table</li>
<li>About dialog still listed serial support as "upcoming" after it shipped</li>
<li>A packaged (--windowed) build had no visible feedback if it failed to start - now falls back to a log file and a message box</li>
</ul>

<h3>v2.0.0</h3>
<ul>
<li>Modbus Serial (RTU) support, alongside TCP</li>
<li>Scripting tab: a small test-sequence language with WRITE/READ/WAIT/LOG/LET, math and variables, a compile/check step, and a safety warning before running against a live device</li>
<li>Server tab can be scripted too (Server-target scripts), and the script editor can insert a Tag reference directly</li>
<li>Multi-window support - connect to more than one device at once, each in its own window</li>
<li>Live CPU usage indicator on the Script tab</li>
<li>Built-in documentation page (Help menu)</li>
<li>Fixed the recent-connections list not working correctly for serial mode</li>
<li>Fixed the Settings dialog not resizing correctly when switching between TCP and Serial</li>
</ul>

<h3>v1.1.0</h3>
<ul>
<li>Server / slave mode - act as a Modbus TCP device so another master (or another ModbusLens window) can poll it</li>
<li>Trend tab with live graphing, plus a hex value column</li>
<li>Per-tag alarms (high/low limits) and CSV logging of live tag values</li>
<li>ARP-based network discovery and Modbus device detection</li>
<li>Insert-inbetween support for the Tags table</li>
<li>Major UI overhaul and a round of stability/dark-mode fixes</li>
<li>Major bug fixes around 1-based addressing</li>
</ul>

<h3>v1.0.0</h3>
<ul>
<li>Initial public release</li>
<li>Modbus TCP client: connect, read, and write coils/registers from an address table</li>
<li>Tag table for monitoring named addresses</li>
<li>Safety interlocks around live writes</li>
<li>Standalone Windows executable</li>
</ul>
"""


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

        features_tab = QTextBrowser()
        features_tab.setOpenExternalLinks(True)
        features_tab.setHtml(FEATURES_HTML)
        tabs.addTab(features_tab, "Features")

        changelog_tab = QTextBrowser()
        changelog_tab.setOpenExternalLinks(True)
        changelog_tab.setHtml(CHANGELOG_HTML)
        tabs.addTab(changelog_tab, "Changelog")

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
