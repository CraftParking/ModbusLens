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
engineers working with industrial automation systems. It combines Modbus communication with
several devices at once, real-time monitoring, trending, scripting, a device simulator and
gateway, and network diagnostics in one tool.</p>

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
<h4>Devices &amp; Connections</h4>
<ul>
<li>Several devices in one window - each with its own name, connection and Unit ID: Modbus TCP, RTU over TCP (for transparent serial-to-Ethernet gateways), or Modbus Serial (COM port, baud, parity, stop bits, byte size, RTU/ASCII framing)</li>
<li>Devices with identical connection settings share one link automatically - several meters behind one gateway or on one RS-485 line, told apart by Unit ID</li>
<li>Overview tab: a live card per device - status (Online, Device exception, No response, Reconnecting, Paused...), success rate, last good read, latency, last error, and up to six pinned values</li>
<li>Add Device, Add from Profile (a device plus a saved profile's tags in one step), Find Unit IDs (Unit ID sweep over a connected link), and Remove All Devices</li>
<li>Top bar with every device's status; Connect/Disconnect per device or Connect All / Disconnect All</li>
<li>Address Table, Script, Scanner and Diagnostic Functions each pick their own device, so different tabs can work with different devices at the same time</li>
<li>Auto-reconnect per link with backoff after an unexpected drop, and automatic resume of Tags monitoring once the connection recovers</li>
<li>Optional interface binding - "Auto" leaves routing to the OS (default); picking a NIC binds the outgoing TCP socket to it</li>
<li>Fast LAN Mode (TCP) - short timeout, no retries, and an instant reachability check instead of retrying every tag when a device drops off</li>
<li>Save/Load Session - every device and its connection, Tags (with scaling), the Address Table range and write bounds together in one file</li>
<li>Separate, independent windows via File &gt; New Window</li>
</ul>

<h4>Address Table</h4>
<ul>
<li>Read coils, discrete inputs, holding registers and input registers; write single/multiple coils and registers</li>
<li>Live monitoring of a whole range, running alongside Tags monitoring</li>
<li>Optional Min/Max write bounds per register - a write outside the range is rejected before it reaches the device, whether it came from the Address Table, Tags, or a Script</li>
<li>U16/S16/HEX/U32/S32/F32 display, 0-based or 1-based addressing</li>
</ul>

<h4>Data Handling</h4>
<ul>
<li>BOOL, U16/S16, U32/S32/F32, U64/S64/F64, HEX support</li>
<li>BOOL on a register shows the full 16-bit pattern, not just a single flag</li>
<li>Word order handling (*_SWAP)</li>
<li>0-based / 1-based addressing, selectable per Address Table range and per Tag</li>
<li>Raw hex value shown alongside the decoded value, in both the Address Table and Tags</li>
</ul>

<h4>Tags Monitoring</h4>
<ul>
<li>Real-time monitoring of every device's tags, with Read Value/Write Value/Timestamp built into the same Tags table</li>
<li>Device column and per-device tabs; the same addresses can be used on every device; Import CSV on a device tab imports into that device only</li>
<li>Tag Groups as collapsible header rows; show/hide and reorder columns</li>
<li>Insert new tags anywhere in the list, and drag and drop to reorder rows, preserving live values and alarm config</li>
<li>Write to a tag while monitoring stays active, or press Enter in the Write Value cell to write just that row immediately</li>
<li>A single misconfigured or failing tag doesn't stop the rest of the list from updating</li>
<li>Per-tag alarms (High/Low limits, or ON/OFF for coils/discrete/BOOL) with red highlighting</li>
<li>Engineering-unit scaling per tag - linear (Raw/Scaled Min/Max) or multiply-by-constant, shown live in the Engineering Value column</li>
<li>Calculated tags (Mode Calc) - an expression over other tags' values, e.g. P1 + P2 + P3, or [METER 2].P1 across devices, usable in alarms, Trend, Overview pins and Scripts</li>
<li>Bit View - a live, per-bit breakdown of a Holding/Input Register tag's raw value, each bit individually named; a Bool-format tag can also expand its bits inline as rows in the Tags table, with a Write Value cell per bit (Holding Register only) to read-modify-write just that one bit</li>
<li>Log live tag values to CSV; CSV import/export of the tag list (with Device and Unit ID)</li>
</ul>

<h4>Device Profiles</h4>
<ul>
<li>Save a device's Address Table range and selected Tags as one named, reusable profile (Name/Manufacturer/Type/Author) - build it once per device model, apply it to any device of that model</li>
<li>View Profile marks each tag red/green (yellow on a Tag Group header for a mix) against your live Tags list, so you can tell at a glance which would actually be new before importing</li>
<li>Apply imports the checked tags without closing the dialog, so you can adjust the selection and apply again</li>
<li>Community: browse and download profiles shared by other users - no account needed; Apply and Download are independent, so you can import a profile's tags without ever saving it locally</li>
<li>Share to Community submits a local profile for review in one click; a maintainer reviews every submission before it's published</li>
</ul>

<h4>Raw Data</h4>
<ul>
<li>One row per Modbus transaction: time, device, operation, raw value in decimal and hex, Success/Failed status, and round-trip latency</li>
<li>TX/RX Bytes - the literal bytes sent and received on the wire for that transaction, one level more raw than the decoded register values</li>
<li>Exception column distinguishing a device-returned error (e.g. Illegal Data Address) from a plain communications timeout, with a tooltip explaining the exception's plain-English meaning and likely causes</li>
<li>Filter by tag name/address/value, by Success/Failed status, and by device, live as new rows arrive</li>
<li>Show Statistics - total requests, success/failure counts, function and exception codes, failure causes, and average/min/max response times</li>
<li>Export CSV, and right-click (or Ctrl+C) to copy selected rows as text or as raw TX/RX hex bytes</li>
<li>Capped at 1000 rows so it can't grow unbounded; oldest rows fall off automatically</li>
<li>Integrated Frame Viewer decodes the selected row's TX/RX Modbus frames (MBAP/Unit ID/CRC/LRC, function code, data, exception) side by side, using that device's framing; collapsible, and every field and the raw hex footer can be selected and copied</li>
</ul>

<h4>Trend</h4>
<ul>
<li>Pages - up to 10 graphs, each with up to 20 pens, all polled while the trend runs</li>
<li>Each pen bound to a Holding/Input Register tag on any device, with an optional label, index and Auto/Raw/Scaled mode; the legend shows the device</li>
<li>Auto Scroll: follows "now" while checked; scrolling away, zooming, or a From/To jump unchecks it, and checking it again jumps straight back to the live edge</li>
<li>Adjustable time window, zoom in/out, a From/To jump to a past range, and a live hover crosshair with per-pen values</li>
<li>Graph Properties: axis titles, background/axis/grid colors, grid on/off, Y-axis auto or manual range</li>
<li>Detach into its own always-on-top window; Record / Replay; log plotted values to CSV; print to PNG or PDF</li>
</ul>

<h4>Server Mode</h4>
<ul>
<li>Act as a Modbus TCP slave so another master can poll ModbusLens directly, on the Unit ID you configure</li>
<li>Coils, Discrete Inputs, Holding Registers, and Input Registers are all editable live, as if you were the field device</li>
<li>Useful for testing your own SCADA/PLC program without real hardware</li>
<li>Gateway mode - relay real requests to a real downstream serial (RTU/ASCII) device and return its actual response instead of simulating one, turning a serial-only device into one reachable over TCP; a Gateway Activity log shows every relayed request and result</li>
</ul>

<h4>Scripting</h4>
<ul>
<li>A small, purpose-built test-sequence language instead of embedded Python - no imports, no client objects, no exception handling to write, just e.g. WRITE HR 1 = 100</li>
<li>WRITE, READ, WAIT, LOG, LET, REPEAT...END, REPEAT UNTIL...END, IF...THEN, ASSERT, DEVICE</li>
<li>Target a real device (Client Connection) or ModbusLens's own Server simulator (Server (Local)); a DEVICE line switches device mid-script, so one script can work with several meters</li>
<li>Runs step by step without freezing the UI, with a console showing what ran</li>
<li>Live Variables panel shows every LET variable's current value while the script runs</li>
<li>Assertion Results panel logs every ASSERT as PASS/FAIL/ERROR - a FAIL doesn't stop the script, so one run reports every check</li>
<li>Add Tag / Insert Tag drop a reference to any tag straight into the script (adding a DEVICE line when the tag is on another device)</li>
<li>Live CPU usage indicator, useful for spotting a runaway loop</li>
</ul>

<h4>Network Diagnostics</h4>
<ul>
<li>Fast parallel TCP discovery scan sized to your real subnet, each hit checked for Modbus</li>
<li>Optional ARP Mode (MAC/vendor lookup) and packet capture via Npcap</li>
<li>Optional Unit ID sweep (1-247) per discovered host; "Show only Modbus devices" filter</li>
<li>Find Devices - TCP network scan and serial parameter sweep in one results table, with Apply to Device</li>
<li>IP Configuration tool - read-only view of this machine's own network adapters</li>
</ul>

<h4>Serial Discovery</h4>
<ul>
<li>Diagnostics menu tool that sweeps common baud rate/parity/stop-bit combinations, plus a Unit ID range, against a COM port to find which one a serial device actually speaks</li>
<li>Opens its own short-lived connection per combination (byte size fixed at 8), so it needs the port free</li>
<li>Apply to Device fills in a device's serial settings from a match</li>
</ul>

<h4>Diagnostic Functions</h4>
<ul>
<li>FC07 Read Exception Status, FC08 Diagnostics (Loopback, Restart Communications, Read Diagnostic Register, Clear Counters), FC11/12 Get Comm Event Counter/Log, FC17 Report Server ID, FC20/21 Read/Write File Record, FC22 Mask Write Register, FC24 Read FIFO Queue, and FC43 Read Device Information</li>
<li>One dialog covering all of them under Diagnostics &gt; Modbus Diagnostic Functions - pick a device and a function, fill in the couple of parameters it needs, Run</li>
</ul>

<h4>Data Decoder</h4>
<ul>
<li>Diagnostics &gt; Decode Registers - paste/type raw hex and see every interpretation at once: U16, S16, U32, S32, U64, S64, F32, F64, HEX, binary, ASCII (where printable), BCD (where valid), and individual register bits</li>
<li>All four byte/word orderings (ABCD/BADC/CDAB/DCBA), switchable live with no re-typing</li>
<li>No Modbus connection needed; stays open alongside the Raw Data tab or an external datasheet without blocking the main window</li>
</ul>

<h4>Scanner</h4>
<ul>
<li>Auto-discovers which addresses respond on the chosen device for a function type (Coils/Discrete Inputs/Holding/Input Registers) over a given range</li>
<li>Works the same way over TCP or serial</li>
<li>Probes the largest block the function allows first, and only narrows down address-by-address where a block doesn't fully respond</li>
<li>A configurable probe timeout keeps scanning fast over TCP; over serial each probe is one bus round-trip</li>
<li>Create Tags From Scan - pick which found ranges to import and generate one new Tags-tab row per address on the scanned device, named with the classic 5-digit Modicon convention; an address that already has a tag of that type is skipped</li>
</ul>

<h4>UI</h4>
<ul>
<li>Light/Dark/Follow System theme, switchable from View &gt; Theme (takes effect after restart)</li>
<li>Color-coded logs (Address Table, System Logs, Script console) - writes in blue, connection events in green, errors in red</li>
<li>Ctrl+scroll wheel zooms text size in the Status Log, System Logs, and Raw Data table</li>
<li>Scrolling a table with the mouse wheel never changes a dropdown or number under the pointer</li>
<li>Help &gt; Documentation for every tab and tool; Help &gt; About has an Updates tab that checks GitHub Releases for a newer version</li>
</ul>
"""

# Newest first. Older releases are summarized at a higher level than the current one -
# see the git history/README for exact commit-level detail on those.
CHANGELOG_HTML = """
<h3>v2.4.0</h3>
<p><u>New</u></p>
<ul>
<li>Multiple devices in one window - each with its own name, connection (Modbus TCP, RTU over TCP or serial) and Unit ID; devices with identical settings share one link, so several meters behind one gateway or on one RS-485 line just work</li>
<li>Overview tab - a live status card per device (status, success rate, latency, pinned values), with Add Device, Add from Profile, Find Unit IDs (Unit ID sweep), and Remove All or Remove Selected Devices (a checkbox per card)</li>
<li>Top bar: select one or more devices there (click to highlight, separate from the Overview tab) for Device Settings, Connect Selected and Disconnect Selected, alongside the existing Connect All/Disconnect All</li>
<li>Device dropdowns in Address Table, Script, Scanner and Diagnostic Functions - each tool works with its own device; scripts can switch device mid-run with a DEVICE line</li>
<li>Devices in Tags - a Device column and per-device tabs, per-device CSV import, and devices travel in Sessions and Tags CSVs; Trend pens and Raw Data gained the same per-device awareness</li>
<li>Trend pages - up to 10 graphs, each with its own 20 pens, all polled while the trend runs</li>
<li>Calculated tags - a Calc mode in the Tags table: an expression over other tags' values (P1 + P2 + P3, V1 * I1 / 1000, or [METER 2].P1 for another device), worked out after every poll cycle with no extra bus traffic, usable anywhere a tag is (alarms, Trend, Overview pins, CSV, Script)</li>
<li>Workspace auto-save, and per-device write bounds (Min/Max) that survive reconnects and restarts</li>
<li>Script tag names read and write like the Tags tab - Count, Format (F32, *_SWAP...) and scaling</li>
<li>Address Table live monitoring and Tags monitoring run at the same time instead of stopping each other</li>
<li>TCP Framing option - "Modbus TCP (standard)" or "RTU over TCP", for transparent serial-to-Ethernet gateways (e.g. Waveshare RS485-TO-ETH)</li>
<li>Gateway mode (Server tab) - relay real requests to a real downstream serial device and return its actual response</li>
<li>Bit View - a live, per-bit breakdown of a register tag's raw value, with inline bit expansion and single-bit read-modify-write</li>
<li>Scanner reworked: an Excel-style color-coded results grid (light green responds, light red doesn't) replaces the text log, each cell labeled with its address and a legend above explaining the colors; a large range splits into spreadsheet-style page tabs sized to fit the screen; adjustable text size and a colorblind-friendly color option; Create Tags From Scan turns a result straight into Tags rows</li>
<li>Export CSV... on the Scanner, Find Devices and Serial Discovery - save what a scan found to a file you can open in Excel</li>
<li>Theme switching (View &gt; Theme) no longer force-disconnects a live device to restart - it queues the switch and asks "Restart now?" only once every device is manually disconnected, reverting cleanly if you say no</li>
<li>Profiles tab relaid out like the other tabs; documentation rewritten for multiple devices</li>
</ul>
<p><u>Fixed</u></p>
<ul>
<li>Replies on a shared line are matched to their request - on an RTU-over-TCP gateway (or RS-485 bus) shared with another master, a reply meant for that master was previously accepted as this request's answer and shown as Success with the wrong data</li>
<li>Auto-reconnect now actually notices a dropped TCP link - the connection stayed flagged as connected after the peer reset it, so the watchdog never retried</li>
<li>Script tag-name reads/writes hit the right register - a tag's 1-based Address was sent as the raw protocol offset, one register too high</li>
<li>Scrolling the Tags table with the mouse wheel no longer changes the dropdowns and number boxes under the pointer - same for Trend's pen grid</li>
<li>Raw Data Frame Viewer no longer flickers or pops its TX/RX tables out as empty windows past 1000 rows</li>
<li>Share to Community works again, with clearer failure messages instead of the submission service's raw error</li>
<li>Scanner no longer aborts the whole scan on a single address that times out with no response (common on a flaky link) - it narrows down the same way as a device exception, and if an address still can't get a clean answer it's marked a third color ("inconclusive") instead of stopping the rest of the range; that color is also distinguished from the colorblind palette's own orange "no response" instead of sitting too close to it</li>
</ul>

<h3>v2.3.0</h3>
<p><u>New</u></p>
<ul>
<li>Device Profiles tab: save a device's Address Table range and Tags as a named, reusable profile (Name/Manufacturer/Type/Author) - View Profile shows which tags are already in your live list (red/green, yellow for a mixed Tag Group) before importing any, and Apply doesn't close the dialog so you can adjust and import again</li>
<li>Community Profiles: browse and download profiles shared by other users, and share your own back for review - no account needed either way. Apply and Download are independent: import a profile's tags without ever saving it locally, or download without applying anything</li>
<li>Trend gained an Auto Scroll checkbox: an explicit, visible control for live-following vs. viewing history, instead of an invisible heuristic - travels into the detached window too</li>
<li>Modbus Diagnostic Functions dialog: FC07 Read Exception Status, FC08 Diagnostics, FC11/12 Get Comm Event Counter/Log, FC17 Report Server ID, FC20/21 Read/Write File Record, FC22 Mask Write Register, FC24 Read FIFO Queue, and FC43 Read Device Information</li>
<li>Save/Load Session: connection settings, Tags (with scaling), Address Table range, and live write bounds together in one file, not just Tags on their own</li>
<li>U64/S64/F64 numeric formats, alongside the existing U32/S32/F32</li>
<li>Fast LAN Mode (Connection Settings, TCP) - short timeout, no retries, and an instant reachability check instead of retrying every tag when a device drops off</li>
<li>Tags table: drag-to-reorder columns, a show/hide column picker, per-tag enable/disable</li>
<li>Raw Data gained an Exception column (now with a hover tooltip explaining likely causes) and an integrated Frame Viewer decoding TX/RX frames side by side - every field and the raw hex can be selected and copied</li>
<li>Diagnostics > Decode Registers: a standalone hex decoder (U16 through F64, HEX, binary, ASCII, BCD, individual bits, all four byte/word orderings) - no connection needed, stays open alongside other work</li>
<li>A shared read cache and coalesced adjacent tag reads cut duplicate traffic between Tags/Trend/Address Table on the same poll cycle</li>
<li>Script engine gained ASSERT and an Assertion Results panel - checks are logged as PASS/FAIL/ERROR without stopping the script on a FAIL, so one run reports every check</li>
<li>In-app documentation gained a "Full search" option - search every topic at once instead of just the one currently open</li>
<li>Network Discovery gained a "Scan Unit IDs (1-247)" option - sweeps every Unit ID on each confirmed Modbus host to report which ones respond</li>
<li>New "Find Devices" dialog - TCP network scan and serial parameter sweep in one shared results table, with a single Apply to Connection Settings for either</li>
</ul>
<p><u>Fixed</u></p>
<ul>
<li>Tag Monitoring's polling (both read-mode and write-mode) moved off the GUI thread - a single unreachable device no longer freezes the whole window</li>
<li>Write-mode tags with a signed format (S16/S32) showed the raw unsigned register instead of the signed value in Read Value</li>
<li>Tags table selection was invisible, with a related write-safety gap where a row could stay logically "selected" after being visually deselected</li>
<li>Script tab's grey example/help text is now real, scrollable document content instead of clipped placeholder text</li>
<li>Run Script's live-system safety warning dialog now follows the app's theme instead of a stock system dialog</li>
<li>Connection Settings: selecting a Recent Connections entry - including the most recent one - now actually applies it</li>
<li>Tag Monitoring could crash whenever Tag Groups were used, which also showed up as Read Values getting stuck blank; group headers were also unclickable (uncollapsible) while monitoring was active</li>
<li>Typing into a tag's Read Value field while monitoring was running got overwritten by the next poll tick before you could act on it</li>
<li>Raw Data's TX/RX byte columns could show one tag's bytes on a different tag's row during fast back-to-back polling</li>
<li>A write cancelled at the confirmation prompt only appeared in the System Log - now also flashes a clear status bar message, since a reflexive second Enter (the same key that triggers the type-and-Enter write shortcut) lands on the dialog's No-default button and can cancel a write silently</li>
<li>Script tab: right-clicking selected text to copy it collapsed the selection first, so Copy had nothing to act on</li>
<li>Local/Community Profiles toggle buttons gave no visual indication of which one was currently selected</li>
<li>Trend's Record/Replay feature could silently fail to log a tick due to a timestamp overflow in its internal signal</li>
</ul>

<h3>v2.2.0</h3>
<p><u>New</u></p>
<ul>
<li>Modbus Diagnostic Functions dialog - the function codes beyond basic read/write (exception status, diagnostics, comm event log, report server ID, file records, mask write, FIFO queue, device identification)</li>
<li>Save/Load Session - connection settings, Tags, Address Table range, and write bounds together in one file</li>
<li>U64/S64/F64 numeric formats, alongside the existing U32/S32/F32</li>
<li>Fast LAN Mode - instant unreachable-device detection instead of retrying every tag</li>
<li>Raw Data gained an Exception column and an integrated Frame Viewer decoding TX/RX frames side by side</li>
<li>Tags table: drag-to-reorder columns, a show/hide column picker, per-tag enable/disable</li>
<li>A shared read cache and coalesced adjacent reads cut duplicate traffic on the wire</li>
</ul>
<p><u>Fixed</u></p>
<ul>
<li>Tag Monitoring's polling moved off the GUI thread - a single unreachable device no longer freezes the whole window</li>
<li>Write-mode tags with a signed format showed the raw unsigned value instead of the signed one</li>
<li>Tags table selection was invisible, with a related write-safety gap around deselected rows</li>
</ul>

<h3>v2.1.0</h3>
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
