from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTextBrowser, QPushButton, QSplitter,
    QLineEdit, QLabel, QWidget, QCheckBox,
)

DOCS = [
    ("Getting Started", """
<h2>Getting Started</h2>
<p>ModbusLens is a Modbus TCP and RTU client built for testing, commissioning, and troubleshooting
industrial devices - PLCs, drives, meters, and gateways. It combines the things you'd normally
reach for several separate tools to do: reading and writing coils/registers, monitoring named
tags on several devices at once, graphing values over time, simulating a slave device, running
repeatable test scripts, and scanning a network for Modbus devices.</p>

<h3>What you need before you start</h3>
<ul>
<li>Each device's <b>Modbus TCP</b> address/port, or its <b>Modbus RTU</b> serial settings
(COM port, baud rate, parity) if it's a serial device.</li>
<li>Each device's <b>Unit ID</b> (also called Slave ID or Station Address) - commonly 1, but check
the device's manual or DIP switches/configuration. Several devices behind one gateway or on one
RS-485 line share the connection and differ only by Unit ID.</li>
<li>Ideally, the device's register map - which addresses hold which values, and in what format.
If you don't have one, the <b>Raw (Hex)</b> column and the Address Table are good tools for
reverse-engineering it safely (read-only first).</li>
</ul>

<h3>Basic workflow</h3>
<ol>
<li>Open the <b>Overview</b> tab (the first tab). A new window starts with one device, "Device 1".
Set its connection with <b>Device Settings</b> (top right), or its card's &#8942; menu &gt;
<b>Edit Device...</b> &gt; <b>Connection Settings...</b>: IP address, port (usually 502) and Unit
ID - or switch to Modbus Serial and enter the serial parameters instead.</li>
<li>Add any further devices with <b>Add Device</b>, <b>Add from Profile...</b> (a device plus a
saved profile's tags) or <b>Find Devices...</b> (asks each Unit ID over a connected device's
link).</li>
<li>Click <b>Connect All</b> (top right), or <b>Connect</b> on one device's card. Each device's
pill in the top bar and its card show its status - green when connected/online.</li>
<li>Use the tabs to work with the devices: <b>Address Table</b> for quick reads/writes,
<b>Profiles</b> for reusable device templates, <b>Tags</b> for named live monitoring,
<b>Raw Data</b> for the untouched bytes behind every transaction, <b>Trend</b> for graphing,
<b>Server</b> to act as a slave device yourself, <b>Script</b> to automate a test sequence, and
<b>Scanner</b> to find which addresses respond. With two or more devices, the single-device tools
(Address Table, Script, Scanner, Diagnostic Functions) each have their own <b>Device</b> dropdown;
Tags and Trend pens carry their own device.</li>
</ol>
<p>The status bar at the bottom shows "N of M device(s) connected" and the version.</p>

<h3>Menu bar</h3>
<p>See the <b>Menus &amp; Toolbars</b> topic on the left for a full, step-by-step list of every
menu and option and exactly where to find it.</p>

<p>See the topics on the left for details on each part of the app, and check
<b>Troubleshooting</b> if something isn't behaving the way you expect.</p>
"""),

    ("Menus & Toolbars", """
<h2>Menus &amp; Toolbars</h2>
<p>Every menu, every option, and exactly what it does - a full reference for navigating the app.
The menu bar sits at the very top of the window, below the title bar.</p>

<h3>File menu</h3>
<ol>
<li><b>New Connection Window</b> - opens a second, fully independent ModbusLens window with its
own device list, tabs, and Server tab. See <b>Multiple Windows</b> for details.</li>
<li><b>New Session</b> - disconnects every device, stops monitoring, and clears the current
window's logs and monitoring results. Doesn't close the window or remove your devices, Tags or
script - just resets the live state.</li>
<li><b>Save Session</b> / <b>Load Session</b> - saves or loads a single <code>.mlsession</code>
file bundling the <b>device list</b> (each device's name, Unit ID, its own connection - TCP or
serial, framing, Fast LAN Mode, interface binding - and its Overview settings: pinned values,
paused, profile), the Tags list (including each tag's device, group, scaling and bit names -
not alarm settings), the Address Table's current range config, and any write bounds - everything
<b>Export/Import CSV</b> doesn't cover on its own (CSV is Tags only). Loading a session disconnects
every device and replaces the device list, but deliberately does not connect for you, so loading a
file can never be the thing that reaches real equipment. A session saved before devices existed
loads as one device, "Device 1". Write bounds only exist on a live connection, so a loaded
session's bounds are applied when the first device in the list connects.</li>
<li><b>Export Data</b> - not implemented yet; currently shows a placeholder message. Use
<b>Log to CSV</b> on the Tags or Trend tab for live data logging in the meantime.</li>
<li><b>Exit</b> - closes this window (saving its settings first).</li>
</ol>

<h3>View menu</h3>
<ol>
<li><b>Theme</b> - a submenu with three options: <b>Light</b>, <b>Dark</b>, and
<b>Follow System</b> (matches your OS setting). Only one is active at a time. Picking a different
one asks to confirm, then restarts ModbusLens to apply it - the theme is set once at startup
rather than switched live.</li>
</ol>

<h3>Tools menu</h3>
<ol>
<li><b>Connection Settings</b> - the same as <b>Device Settings</b> on the top bar: edits one
device's connection (with several devices it asks which; a connected device has to be
disconnected first). See <b>Connecting to a Device</b>.</li>
<li><b>Data Templates</b> - not implemented yet; currently shows a placeholder message.</li>
<li><b>IP Configuration</b> - a quick, read-only ipconfig-style view of this machine's own network
adapters (name, IP, subnet). Useful for figuring out which subnet to scan or connect on before
you know a device's address.</li>
<li><b>Show Safety Warning Again</b> - re-shows the startup safety notice (if you ticked "Don't show
this warning again" on it) and saves whatever you choose there.</li>
</ol>

<h3>Diagnostics menu</h3>
<ol>
<li><b>Network Discovery &amp; Diagnostics</b> - opens the network scanning dialog (fast TCP scan,
optional ARP mode, Modbus detection). See <b>Troubleshooting &gt; Network Discovery</b>.</li>
<li><b>Find Devices</b> - one dialog for both kinds of discovery: <b>Transport</b> "TCP (Network
Scan)" or "Serial (Parameter Sweep)", <b>Start Scan</b> / <b>Stop Scan</b> / <b>Clear
Results</b>, and a results table (Transport, Target, Parameters, Unit ID). Select a result and
click <b>Apply to Connection Settings</b> (or double-click it) to open Connection Settings
pre-filled for the device you pick. Not the same as the Overview's <b>Find Devices...</b>, which
sweeps Unit IDs over an already connected link.</li>
<li><b>Serial Discovery</b> - sweeps common baud rate/parity/stop-bit/Unit ID combinations against
a COM port to find which one a serial device actually speaks. See <b>Serial Discovery</b>.</li>
<li><b>Modbus Diagnostic Functions</b> - the function codes beyond basic read/write: Read Exception
Status, Diagnostics (Loopback, Restart Communications, Read Diagnostic Register, Clear Counters),
Get Comm Event Counter/Log, Report Server ID, Read/Write File Record, Mask Write Register, Read FIFO
Queue, and Read Device Information. See <b>Diagnostic Functions</b>.</li>
<li><b>Decode Registers</b> - opens a standalone hex decoder, no connection required. See the
<b>Data Decoder</b> topic.</li>
<li><b>System Logs</b> - opens a dialog with the full, scrollable System Logs history (the same
color-coded write/connect/error log shown live in the app). Handy when you need to scroll back
further than fits on screen. <b>Ctrl+scroll wheel</b> zooms its text size in and out.</li>
<li><b>Clear All Logs</b> - clears the System Logs and the Raw Data tab's transaction history
(not the Show Statistics counters - those have their own Reset). This can't be undone.</li>
</ol>

<h3>Help menu</h3>
<ol>
<li><b>Documentation</b> - this dialog.</li>
<li><b>About</b> - version number, a feature list, the Support link, and an <b>Updates</b> tab
that checks GitHub Releases for a newer version.</li>
</ol>

<h3>Top bar (below the menu bar)</h3>
<p>Always visible: one <b>pill per device</b> - a status dot, the device's name and its status
word (Online, Disconnected, Reconnecting..., No response, ...). Click a pill to jump to that
device's card on the Overview (it's briefly highlighted). On the right:</p>
<ul>
<li><b>Device Settings</b> - edit a device's connection. With one device it opens straight away;
with several it shows a menu of "Name -- target, Unit N" (connected devices are greyed out -
disconnect first).</li>
<li><b>Connect All</b> - connects every device that isn't connected; any that fail are listed
together in one message.</li>
<li><b>Disconnect All</b> - disconnects every device (and stops monitoring).</li>
</ul>
<p>Each button is only enabled when there's something for it to do.</p>
"""),

    ("Connecting to a Device", """
<h2>Connecting to a Device</h2>
<p>Every device has its own connection and Unit ID. Open a device's connection from its Overview
card (&#8942; &gt; <b>Edit Device...</b> &gt; <b>Connection Settings...</b>), from the Add Device
dialog, or with <b>Device Settings</b> on the top bar (Tools &gt; Connection Settings does the
same). Choose <b>Modbus TCP</b> or <b>Modbus Serial (RTU/ASCII)</b> under <b>Connection Type</b>,
fill in the fields for that mode, and click <b>Save Settings</b>. A connected device can't be
edited - disconnect it first.</p>

<h3>Adding a device</h3>
<p><b>Add Device</b> (Overview, or the Tags tab) asks for a <b>Name</b> (required, unique - case
doesn't matter), its <b>Connection</b> (starts as a copy of the first device's; change it with
<b>Connection Settings...</b>) and its <b>Unit ID</b> (0-255, suggested as the next free one on
that connection). Two devices on the same connection need different Unit IDs; the same Unit ID on
two different gateways is fine. Devices with identical connection settings automatically share
one link - see <b>Overview</b>. A serial port can only carry one set of line settings, so a second
device on a COM port that's already in use with different baud/parity/framing is refused.</p>

<h3>Modbus TCP (Target Device (TCP))</h3>
<ul>
<li><b>IP Address</b> - the target device, PLC, or gateway's Modbus TCP address.</li>
<li><b>Port</b> - usually 502 for standard Modbus TCP (ModbusLens's own Server tab defaults to
5020).</li>
<li><b>Unit ID</b> - see below.</li>
<li><b>Network Interface</b> - <b>Auto (let OS choose route)</b> is the default: it fills in a
local interface's IP as a convenience when Target IP is blank (e.g. testing against ModbusLens's
own Server tab), but otherwise leaves routing entirely to the OS. Picking a specific interface
instead actually binds the outgoing TCP socket to it - useful on a multi-homed machine (VPN +
Ethernet + Wi-Fi all up at once) where the OS's default route isn't the NIC you actually want the
connection to go out of. If you need the full picture - every adapter's IP and subnet mask -
<b>Tools &gt; IP Configuration</b> shows all of them at once, like running <code>ipconfig</code>.</li>
<li><b>Fast LAN Mode</b> - a short (200ms) timeout and no retries, for a local network where a
timeout means the device is actually gone rather than just momentarily slow. It also changes how
Tags monitoring reacts to a failed poll - see <b>Tags Monitoring</b>. It's part of the device's
connection, so two devices at the same IP:port but with different Fast LAN, framing or interface
settings use two separate TCP connections.</li>
<li><b>Framing</b> - <b>Modbus TCP (standard)</b> is the default MBAP framing almost every device
uses. Switch to <b>RTU over TCP</b> only for a transparent serial-to-Ethernet gateway (e.g. a
Waveshare RS485-TO-ETH running in TCP Server/passthrough mode) that tunnels raw RTU frames
(with CRC16) over a plain TCP socket instead of translating them to real Modbus-TCP framing. Many of these gateways forward every reply to every connected client, so if another master (a SCADA, Node-RED, ...) polls the same gateway, its replies reach ModbusLens too - they're recognised and skipped, since a reply has to match the request's function code and register count (or write echo). A reply from the same unit with the same function and count can't be told apart in RTU, which carries no transaction ID, so keep polling slow on a shared bus.</li>
<li><b>Find Devices...</b> - closes the dialog and opens Diagnostics &gt; Find Devices with the
TCP network scan selected.</li>
</ul>

<h3>Modbus Serial (Target Device (Serial))</h3>
<ul>
<li><b>COM Port</b> - the port the device is connected to (via USB-RS485/RS232 adapter or a native
serial port); detected ports are listed, and you can type one too.</li>
<li><b>Baud Rate</b> (1200-115200, or type another), <b>Parity</b> (None/Even/Odd), <b>Stop
Bits</b> (1/2), <b>Byte Size</b> (7/8) - must match the device's configuration exactly, or
communication will fail or return garbage.</li>
<li><b>Framing</b> - <b>RTU (binary)</b> (the default and far more common) or <b>ASCII</b>
(hex-encoded, human-readable on the wire, framed with a leading <code>:</code> and trailing
CR/LF). The two are incompatible - a device speaking one will not respond correctly to the other,
so this has to match the device exactly, the same as baud rate and parity.</li>
<li><b>Find Devices...</b> - opens Diagnostics &gt; Find Devices with the serial parameter sweep
selected.</li>
</ul>
<p>A brand-new device starts at 127.0.0.1:502, or COM1 at 19200 8N1 RTU on the serial side.</p>

<h3>Unit ID and Recent Connections</h3>
<ul>
<li><b>Unit ID</b> - the Modbus slave/unit identifier (1 is common; some TCP gateways ignore it,
but RTU devices and gateways with several units behind them always need the right one). It
belongs to the device: changing it here changes the device's Unit ID. Values above 255 are clamped
to 255 with a warning.</li>
<li><b>Recent Connections</b> - picking an entry fills the form with a connection you've used
before (the last 10); it doesn't connect by itself. A connection is added to the list when you
save settings or connect.</li>
</ul>

<h3>Connecting and disconnecting</h3>
<p>Click <b>Connect</b> / <b>Disconnect</b> on a device's Overview card, or <b>Connect All</b> /
<b>Disconnect All</b> on the top bar. Each device's pill and card show its status:
<b>Disconnected</b>, <b>Connection failed</b>, <b>Reconnecting...</b>, <b>Connected</b> - and once
Tags monitoring is polling it, <b>Online</b>, <b>Device exception</b>, <b>Partly failing</b>,
<b>No response</b>, <b>Paused</b>, <b>Waiting for first poll</b> or <b>No tags</b>. If a card's
Connect fails, a "Connection Failed" message names the device and target, the error, and a short
checklist; Connect All lists every device that failed in one message instead. See
<b>Troubleshooting</b> for the details.</p>

<h3>Finding your own IP (IP Configuration)</h3>
<p><b>Tools &gt; IP Configuration</b> opens a small window listing every network adapter on this
machine - the same information <code>ipconfig</code> gives you at a command prompt, without
leaving the app. Each row shows the adapter name, its IPv4 address, subnet mask, and whether the
adapter is Up or Down.</p>
<p>This is mainly useful for two things: figuring out which of your adapters is on the same
network/subnet as the target device before you connect, and getting the right address to hand out
when <i>you're</i> the target - e.g. telling a colleague's PLC or SCADA system which of your IPs to
connect to when testing against ModbusLens's own Server tab. The Network Interface dropdown in
Connection Settings (above) covers the common case of "fill in my own IP"; IP Configuration is for
when you need to see every adapter and its subnet mask at once, such as confirming two adapters
aren't sharing a conflicting subnet.</p>

<h3>Auto-reconnect</h3>
<p>Once connected, ModbusLens watches every link in the background. If one drops - a cable pulled,
a device rebooting, a network blip - the devices on it show <b>Reconnecting...</b> and it keeps
retrying automatically, waiting a little longer between each attempt (2s, 4s, 8s... capped at
30s) so it doesn't hammer a device that's still coming back up. Other links keep working
meanwhile. If Tags monitoring stopped because every tag failed for several polls in a row (read
as: the connection itself was the problem, not one bad tag), it resumes automatically the moment
the connection recovers - you don't have to click Start Monitoring again. This only applies to an
unexpected drop; disconnecting yourself never triggers a reconnect attempt.</p>

<h3>0-based vs 1-based addressing</h3>
<p>Modbus devices are documented two different ways: some vendors say "register 40001" meaning
protocol offset 0 (1-based/traditional), others say "register 0" meaning the same offset
(0-based/raw). The <b>0-Based Addressing</b> checkbox on the Address Table and Tags tabs controls
which convention the address field uses:</p>
<ul>
<li><b>Unchecked (default)</b>: 1-based. Entering address 1 reads protocol offset 0, matching the
classic 40001-style convention.</li>
<li><b>Checked</b>: 0-based. Entering address 0 reads protocol offset 0 directly.</li>
</ul>
<p>If a value looks off by one compared to what you expect, this is almost always the cause -
toggle the checkbox and compare. See <b>Troubleshooting</b> for more on diagnosing this.</p>
"""),

    ("Address Table", """
<h2>Address Table</h2>
<p>A quick read/write grid for a contiguous range of one Modbus data type, similar to classic
tools like ModScan. This is usually the fastest way to sanity-check a connection or probe an
unfamiliar register map before setting up named Tags.</p>

<h3>Device</h3>
<p>With two or more devices, a <b>Device</b> dropdown ("Name (Unit N)") sits above the range
settings - the table reads and writes that device only, independently of what the other tabs are
pointed at. Changing it stops Live Monitoring and logs which device the table now talks to. The
controls are only enabled while that device is connected.</p>

<h3>Creating a table</h3>
<ol>
<li>Pick a <b>Function</b> (Read Coils, Read Discrete Inputs, Read Holding/Input Registers, Write
Single/Multiple Coil(s), Write Single/Multiple Register(s)).</li>
<li>Set <b>Start Address</b> and <b>Count</b> (Count is fixed at 1 for the Write Single
functions). A read can cover at most 125 registers or 2000 coils/inputs, and the range can't go
past address 65535.</li>
<li>Click <b>Create Table</b>. Changing the Function afterwards rebuilds the table.</li>
</ol>
<p>Each row shows the Modbus reference address (0xxxx coils, 1xxxx discrete inputs, 3xxxx input
registers, 4xxxx holding registers), the current value, and the same value in hex. For a Write
function, double-click the Value cell to edit and send it immediately (coil rows show a checkbox
instead).</p>
<ul>
<li><b>0-Based Addressing</b> - the same convention switch as on the Tags tab (1-65536 when
unchecked, 0-65535 when checked). See <b>Connecting to a Device</b>.</li>
<li><b>Display</b> - how register values are shown: U16, S16, HEX, or the 32-bit U32/S32/F32,
which pair adjacent rows and show the value on the first row of each pair. It doesn't apply to
coils/discrete inputs and re-renders immediately.</li>
</ul>

<h3>Write bounds</h3>
<p>For Write Single/Multiple Register functions, two extra columns appear: <b>Min</b> and
<b>Max</b>. Setting both on a row rejects any write to that register outside the range - a typo
like an extra zero gets refused instead of sent to the field device. This is enforced on the
connection itself, so it also protects writes to that same address from the Tags tab or a
Script, not just from this table. Bounds cover registers. Leave both blank for no limit. A
rejected write shows up as a failed write with a message like <i>"Write rejected: value 10000 at
address 99 is outside the configured write bound [0, 100]"</i>.</p>

<h3>Live Monitoring</h3>
<p>For Read functions, check <b>Enable Live Monitoring</b> and set an interval (100-10000 ms,
default 1000) to keep polling the whole range automatically. Address Table monitoring and Tags
monitoring don't run together: switching to the Address Table tab stops Tags monitoring, and
switching to the Tags tab stops Live Monitoring here, so the two don't compete for the
connection. (Tags monitoring is what feeds the Overview cards.)</p>

<h3>Status Log</h3>
<p>The panel on the right shows what the table is doing - reads, writes, and any errors,
each with a timestamp and color-coded so the right lines stand out: writes in blue, connection
events in green, errors in red, everything else in the default color. This is the first place
to look when a write doesn't seem to take effect. The same coloring applies to System Logs and
the Script console. <b>Ctrl+scroll wheel</b> over the log zooms its text size in and out.</p>
"""),

    ("Overview", """
<h2>Overview</h2>
<p>The first tab, and the place devices are set up. A <b>device</b> is one Modbus unit: a name,
its own connection (Modbus TCP - IP, port, framing including RTU over TCP - or a serial port with
its baud rate and framing) and its Unit ID. Devices with identical connection settings - several
meters behind one gateway, or on one RS-485 port - automatically share one link, and are polled
one at a time over it; a serial port can only carry one set of line settings.</p>

<h3>Adding and removing devices</h3>
<ul>
<li><b>Add Device</b> - the device dialog: Name, Connection (<b>Connection Settings...</b> opens
the usual connection dialog) and Unit ID. See <b>Connecting to a Device</b>.</li>
<li><b>Add from Profile...</b> - creates a device with a saved profile's tags in one step: pick a
<b>Profile</b> (only profiles that have tags are listed, as "Name (N tags)"), a <b>Device
name</b> (suggested from the profile), the <b>Connection</b> (starts as the first device's) and
the <b>Unit ID</b> (next free one on that connection). The card then shows the profile's name.</li>
<li><b>Find Devices...</b> - a Unit ID sweep over an already connected link (with several links it
asks "Sweep Unit IDs on which connection?"). Set the <b>Unit IDs</b> range (1-247, default 1-10)
and the <b>Timeout per unit</b> (100-3000 ms, default 500), then <b>Start Sweep</b>: each unit is
asked for holding register 0, and anything that answers - data or a Modbus exception - is listed.
Units already used on that link show greyed out as "(already: NAME)". Tick the ones you want and
click <b>Add Selected as Devices</b>; they're named "Unit N" (rename them later). Stop monitoring
first so the sweep has the line to itself, and keep the range small on a busy shared bus.</li>
<li><b>Remove All Devices</b> - after a confirmation that shows how many devices and tags will go,
disconnects and deletes every device and all their tags, alarms, scaling and pinned values, and
starts again with one blank "Device 1" (Unit 1) on the first device's connection settings. Export
CSV or Save Session first if you might need them.</li>
</ul>

<h3>Device cards</h3>
<p>Each device gets a card:</p>
<ul>
<li>Its name and status: <b>Disconnected</b>, <b>Connection failed</b>, <b>Reconnecting...</b>,
<b>Connected</b>, and while Tags monitoring is running <b>Waiting for first poll</b>,
<b>Online</b>, <b>Device exception</b> (it answered with a Modbus exception), <b>Partly
failing</b>, <b>No response</b>, <b>Paused</b> or <b>No tags</b>.</li>
<li>Its connection, profile (if it was added from one), Unit ID and tag count.</li>
<li>Up to six <b>pinned values</b> - its first four tags until you choose others with <b>Pin
Values...</b>. A pinned tag shows its Engineering Value if it has scaling, else its Read Value.</li>
<li>A detail line: "N% OK of M reads · last good read Xs ago · NN ms" plus the last error, or
"Not connected -- click Connect." / "Couldn't connect: ...".</li>
<li>Buttons: <b>Connect</b>/<b>Disconnect</b> (this device only), <b>Open Tags</b> (jumps to its
tab in Tags), <b>Pin Values...</b>, and <b>Pause</b>/<b>Resume</b> - leaves the device out of
Tags monitoring's polling (Trend pens on it are still read).</li>
<li>The &#8942; menu: <b>Edit Device...</b> (disconnect it first) and <b>Remove Device...</b> -
which asks whether to <b>Keep Tags</b> (moved to another device) or <b>Delete Its Tags Too</b>.
The last device can't be removed; edit it instead.</li>
</ul>
<p>The <b>Monitoring Controls</b> box at the top (Start/Stop Monitoring, Interval 100-10000 ms) is
the same control as on the Tags tab - the two stay in sync - and shows "N device(s), M
connected".</p>

<h3>Working with several devices</h3>
<p>The bar at the top of the window shows every device with its status - click one to jump to
its card here (it's highlighted for a moment). There's no single "active" device:
<b>Address Table</b>, <b>Script</b>, <b>Scanner</b> and the <b>Diagnostic Functions</b> dialog
each have their own <b>Device</b> dropdown (shown once there are two or more devices), so each can
work with a different device at the same time; Tags and Trend pens carry their own device, and
the Raw Data tab has a Device column and filter. <b>Device Settings</b> edits a device's
connection (pick which; it has to be disconnected). <b>Connect All</b> / <b>Disconnect All</b>
act on every device. A link that drops is reconnected automatically with back-off.</p>
<p>The device list is saved automatically (by the first ModbusLens window - see <b>Multiple
Windows</b>) and in Sessions; an older session's single connection becomes a device called
"Device 1".</p>
"""),

    ("Tags Monitoring", """
<h2>Tags Monitoring</h2>
<p>The Tags tab lets you name individual points scattered across different addresses and types,
and watch or write them all at once - unlike the Address Table, which is one contiguous range.
This is the tab you'll spend the most time in once you've mapped out a device: build the list
once, then monitor it continuously.</p>

<h3>Adding tags</h3>
<p><b>Add Tag</b> appends a new row (or inserts just below the selected row, so you're never stuck
adding things only at the end). Once a list is built, drag a row's number in the left-hand gutter
up or down to reorder it - a blue line shows exactly where it will land as you drag, and the row's
live values, comment, and alarm configuration (if any) all move with it. Reordering is only
available while monitoring is stopped, the same as adding or removing a tag. Each row has:</p>
<ul>
<li><b>Tag Name</b>, <b>Mode</b> (Read or Write), <b>Type</b> (Coil/Discrete Input/Holding
Register/Input Register), <b>Address</b>, <b>Count</b>, <b>Format</b>.</li>
<li><b>Read Value</b> - the decoded live value.</li>
<li><b>Raw (Hex)</b> - the same value in hex, straight from the register(s), independent of format.</li>
<li><b>Write Value</b> - type a value here and click <b>Write Selected</b> to send it (Write-mode
tags only), or just press <b>Enter</b> in the cell to write that one row immediately without
selecting it or clicking anything - mirrors the type-and-Enter workflow classic tools like Modbus
Poll use. Goes through the exact same confirmation and safety interlock as Write Selected.</li>
<li><b>Comment</b> and <b>Timestamp</b>.</li>
<li><b>Group</b> - which Tag Group the row belongs to (pick <b>+ Add Group...</b> to create one).
Groups are shown as collapsible header rows ("Name (N tags)").</li>
<li><b>Engineering Value</b> and <b>Scale</b> - see Engineering-unit scaling below.</li>
<li><b>Enabled</b> - unticked rows are skipped by monitoring (a manual write still works).</li>
<li><b>Device</b> (with two or more devices) - which device the tag belongs to; the dropdown ends
with <b>+ Add Device...</b>.</li>
</ul>
<p>Right-click the column header to show or hide columns; drag a header to reorder them.
Right-click a row for <b>Configure Alarm...</b>, <b>Bit View...</b>, <b>Show Bits Inline</b> and
<b>Copy Row(s)</b>. <b>Delete</b> removes the selected rows and <b>Ctrl+C</b> copies them.
<b>Remove Selected Tag</b> and <b>Remove All Tags</b> are next to Add Tag - with a device tab open,
Remove All Tags removes only that device's tags. Scrolling the table with the mouse wheel never
changes a dropdown or number under the pointer - it just scrolls; click a cell to edit it.</p>
<p>A duplicate start address on the same device (same type) is moved to the next free address
automatically, with a note in the log. Start Monitoring refuses to run with duplicate addresses
on one device and warns about overlapping ranges; the same address on two different devices is
fine.</p>

<h3>Devices in Tags</h3>
<p>Every tag belongs to a device (see <b>Overview</b>). With more than one device, the Tags table
shows a <b>Device</b> column next to Tag Name and a row of device tabs above it: <b>All</b>, one tab
per device, and <b>+</b> to add another. A device tab ("Name (unit)") only shows that device's tags, and a tag you
add while it's open belongs to that device; right-click a device tab for <b>Edit Device...</b> /
<b>Remove Device...</b>. <b>Add Device</b> next to Add Tag opens the same device dialog as the
Overview.
The same address can be used on every device - two identical meters simply share one register map.
Tags CSV exports carry <b>Device</b> and <b>Unit ID</b> columns, so an import recreates missing
devices. <b>Import CSV</b> while a device's tab is open imports into that device only - it replaces
that device's tags and leaves the others alone, so one meter-model CSV can be imported once per
meter (a tag name already on that device is skipped). On the <b>All</b> tab it replaces the whole
table, creating any device named in the file that doesn't exist yet (on the first device's
connection); an older CSV without a Device column loads onto the first device. <b>Write All</b>
and <b>Write Selected</b> also follow the open tab: with a device tab open, Write All writes only
that device's Write-mode tags. Profiles stay device-independent: they describe a device type, not
where it's connected.</p>

<h3>Naming a tag</h3>
<p>A tag name can only use letters, numbers, and underscores - no spaces or other symbols, and it
can't start with a digit. Script language keywords (WRITE, READ, HR, COIL, and so on) and common
reserved words are also blocked. Entering an invalid name shows a warning and clears the field
rather than letting it stick, since a tag's name is also how it's referenced by name in a Script
(see the Scripting topic) and in Trend's Add Pen picker.</p>

<h3>Data formats</h3>
<p><b>Bool</b>, <b>U16/S16</b>, <b>U32/S32/F32</b>, <b>U64/S64/F64</b> (plus <code>_SWAP</code>
variants of the 32/64-bit formats for the opposite word order), and <b>Hex</b>. BOOL on a
Coil/Discrete Input is a simple flag; BOOL on a Holding/Input Register instead shows the full
16-bit pattern (e.g. <code>0000000000000101</code>) so you can read individual status/alarm bits
out of a status word. 32-bit formats (U32/S32/F32) need a <b>Count</b> that's a multiple of 2;
64-bit formats (U64/S64/F64) need a multiple of 4 -- since they span 2 or 4 registers per value,
respectively.</p>

<h3>Bit View</h3>
<p>Right-click a Holding/Input Register tag and choose <b>Bit View...</b> for a live, per-bit
breakdown of its raw value - each of the register's bits shown on its own line with an editable
name and current 0/1 state, useful for VFD-style control/status words that pack several
independent booleans (running, ready, fault, at-speed, auto/manual, ...) into one register.</p>
<p>A Bool-format tag can also expand its bits directly inline, as rows in the Tags table itself -
click the row number to toggle. For a Holding Register (writable), each bit row gets its own
<b>Write Value</b> cell: type <code>1</code>/<code>0</code> (or <code>true</code>/<code>false</code>)
and press <b>Enter</b> to read-modify-write just that one bit, leaving the rest of the register
untouched. Input Registers are read-only, so their bit rows have no Write Value cell. Naming a bit
in either the popup or the inline rows updates the other immediately - they're the same underlying
bit names.</p>

<h3>Engineering-unit scaling</h3>
<p>Check the <b>Scale</b> box on a row to open a small popup with two modes:</p>
<ul>
<li><b>Linear (Min/Max)</b> - <b>Raw Min/Max</b> and <b>Scaled Min/Max</b> define a linear
transform from whatever the device actually sends to a meaningful engineering unit (e.g. raw ADC
counts 0-4095 mapped to 0-100 PSI).</li>
<li><b>Multiply by Constant</b> - a single factor (e.g. raw 151 x 0.1 = 15.1), for the common case
of a device sending a value scaled by a fixed power of ten.</li>
</ul>
<p>Either way, the result appears in the <b>Engineering Value</b> column alongside the normal Read
Value, live as the tag is polled - and in Trend, if a pen's tag has scaling enabled. Choose
<b>Real</b> or <b>Integer</b> for how the scaled result is displayed. Unchecking <b>Scale</b> (or
Cancelling the popup) turns scaling back off for that row.</p>

<h3>Alarms</h3>
<p>Right-click a tag row and choose <b>Configure Alarm...</b>. Numeric tags get a High and/or
Low limit; coils, discrete inputs, and BOOL-format registers get an ON/OFF trigger instead. The
Read Value cell turns red while the tag is in alarm.</p>

<h3>Logging</h3>
<p><b>Log to CSV</b> appends a timestamped row for every monitored tag on every poll tick to a
file you choose. <b>Export CSV</b>/<b>Import CSV</b> save or load the tag list itself (not the
live data) - handy for keeping a reusable tag set per device model.</p>

<h3>Resilience while monitoring</h3>
<p>A single tag that fails to read (bad address, wrong count for its format, device briefly
unresponsive) shows <code>ERROR</code> in its own Read Value cell but doesn't stop the rest of
the list from updating. Tags of a device that isn't connected, or is paused on the Overview,
are simply skipped. Monitoring only auto-stops if <i>every</i> polled tag fails for three polls in
a row, which is treated as a lost connection rather than a configuration mistake on one row; with
several devices, one device dropping doesn't stop monitoring - its tags show ERROR until its link
reconnects. Start Monitoring needs at least one connected device. The <b>Interval</b> (100-10000
ms, default 1000) is shared with the Overview.</p>
<p><b>Fast LAN Mode</b> (a device's Connection Settings, TCP only - see Connecting to a Device) changes this
slightly: after the first failed read in a poll cycle, it does one quick reachability check
against the device instead of moving straight to the next tag. If the device is actually gone,
every remaining tag in that cycle is marked <code>ERROR</code> immediately rather than each one
individually timing out. If the check finds the device still reachable, polling continues
normally - that one failure was specific to a single tag, not the connection.</p>

<h3>Safety interlock</h3>
<p>Writing is paused for the moment a value is being sent, then Read polling resumes automatically -
this stops a write and a read from overlapping on the same connection.</p>
"""),

    ("Device Profiles", """
<h2>Device Profiles</h2>
<p>The <b>Profiles</b> tab saves a device's Address Table range and Tags list together as one
named, reusable template - build it out once for a device model (e.g. a specific VFD or PLC),
then apply it to any device of that model instead of rebuilding it by hand every time.
Distinct from <b>File &gt; Save/Load Session</b>: a session also carries your devices' own
IP/port/serial settings and Unit IDs, a profile deliberately doesn't (its tags carry no Device or
Unit ID), since the same device model gets reused across many different installations. The
Overview's <b>Add from Profile...</b> creates a new device straight from a profile.</p>

<h3>Local profiles</h3>
<p><b>Create New Profile</b> opens a page-navigated dialog: <b>Profile Info</b> (Name,
Manufacturer, Type, Author), a <b>Tags</b> page where you check which of your currently
configured Tags to capture into the profile (<b>Select All</b> / <b>Select None</b>; tags of every
device are listed), and a placeholder <b>Datasheet</b> page. The
Address Table's current range is captured automatically. <b>Edit</b> reopens the same dialog
pre-filled with the profile's own saved contents - not just whatever happens to be live right
now - so editing a profile for a device you're not currently connected to doesn't wipe it out.
<b>Delete</b> removes a profile file permanently after confirming.</p>
<p>Double-clicking a profile card (or selecting it and pressing Enter) opens <b>View Profile</b>:
a read-only look at its Tags, each marked with a colored dot against your current live Tags
list - green means that tag is already there, red means it isn't, yellow (on a Tag Group header)
means the group is a mix of both. Check the ones you want and click
<b>Apply</b> to import them into your live Tags list - onto the device whose tab is open in Tags,
else the first device; a tag name already on that device is skipped; Apply doesn't close the dialog, so you can adjust the selection and
apply again, and the Address Table range is applied at the same time. Local profiles are stored
under your own Documents folder (<code>Documents/ModbusLens/Profiles</code>), one file per
profile, so they're easy to find, back up, or move by hand.</p>

<h3>Community profiles</h3>
<p>The <b>Local</b>/<b>Community</b> toggle at the top of the tab switches to profiles other
ModbusLens users have shared and a maintainer has verified - fetched over the network the first
time you open the Community tab (or click <b>Refresh</b>), no account or sign-in needed. Same as
Local, double-clicking a card opens a preview - but here, <b>Apply</b> and a separate
<b>Download</b> button are entirely independent: Apply imports the profile's tags into your live
Tags list without saving anything to disk, Download saves a copy into your own Local profiles
(picking it up in the Local tab), and you can do either, both, or neither before closing. A
profile you've downloaded shows a small <b>Community</b> badge on its Local card so it's not
mistaken for one you built by hand - the badge disappears if you later edit that profile, since
at that point it's no longer literally the shared file.</p>

<h3>Sharing a profile</h3>
<p>Select a local profile and click <b>Share to Community</b> to submit it for review - one
click, no GitHub account or sign-in required. A maintainer reviews every submission before it's
added to the public Community list, so it won't appear there immediately. Resubmitting the exact
same, unchanged profile a second time is silently skipped rather than sent again.</p>
"""),

    ("Raw Data", """
<h2>Raw Data</h2>
<p>One row per Modbus transaction - the untouched data behind every read and write, independent
of how a Tag or Address Table row happens to decode it. Useful when a decoded value looks wrong
and you want to see exactly what came back before ModbusLens interpreted it as U16, F32, or
anything else, and for spotting a device that's responding but slow.
<b>Ctrl+scroll wheel</b> over the table zooms its text size in and out.</p>

<h3>Columns</h3>
<ul>
<li><b>Time</b> and <b>Operation</b> - when it happened and what it was (which Tag, Address
Table function, or Script command triggered it). Tags polling and writes, the Address Table and
Scripts are logged here; Trend, Scanner, Diagnostic Functions and the Unit ID sweep are not.</li>
<li><b>Device</b> (shown second, with two or more devices) - which device the request went to.</li>
<li><b>Value</b> - the raw register/coil result in decimal, or the error message if it failed.</li>
<li><b>Raw (Hex)</b> - the same result in hex (registers as <code>0xNNNN</code>, coils as
<code>1</code>/<code>0</code>) - blank for a failed transaction, since there's nothing to show.</li>
<li><b>TX Bytes</b> / <b>RX Bytes</b> - the literal bytes ModbusLens sent and received on the
wire for that exact transaction, captured straight from the connection itself. This is one level
more raw than the Value/Raw (Hex) columns - those show the register values after pymodbus has
already parsed the response; TX/RX Bytes show the full frame as bytes, including the function
code, address, byte count, and (for serial) the CRC/LRC. RX is blank if the request timed out
with no response at all.</li>
<li><b>Status</b> - <span style="color:#2E7D32;">Success</span> or
<span style="color:#C62828;">Failed</span>, color-coded the same way as the other logs.</li>
<li><b>Exception</b> - the decoded Modbus exception description (e.g. "Illegal Data Address")
when the device itself replied but refused the request. Left blank for a plain communications
failure (timeout, no response at all), so you can tell "the device rejected this" apart from
"nothing answered" at a glance instead of both just showing Failed. Hover over an Exception
cell for a tooltip with the exception's plain-English meaning and a short list of likely
causes (e.g. for Illegal Data Address: wrong start address, a 0/1-based addressing mismatch,
the wrong register space) - a starting point for what to check next, not just a name to go
look up.</li>
<li><b>Latency (ms)</b> - how long that specific request took round-trip. A device that's
technically working but degrading usually shows up here first, before it starts failing outright.</li>
</ul>

<h3>Filter</h3>
<p>The text box filters by whatever's in the Operation, Value, or Exception columns - a tag name
(e.g. <code>pump</code>), an address, a specific value, or part of an exception message. The
dropdown next to it narrows to <b>All</b>, <b>Success</b> or <b>Failed</b> rows, and with two or
more devices a <b>Device</b> dropdown ("All devices" or one device) shows only that device's
transactions. All of them apply live as you
type/select, and to new rows as they arrive - useful for watching one specific tag during a busy
poll, or isolating every failure to see if they cluster around one address.</p>

<h3>Show Statistics</h3>
<p>Opens "Modbus Communication Statistics" for this window (all devices together): total
requests, successful vs. failed counts, exception responses, which function codes were used, a
breakdown of exception codes and failure causes, and average/min/max response times over the last
500 responses - counted across everything logged so far, not just what's currently visible in the
table, since old rows fall off after 1000. <b>Reset Statistics</b> zeroes the counters (Clear
Data and Clear All Logs don't). Useful for confirming a "slow" feeling is real and quantifying
it.</p>

<h3>Clear Data</h3>
<p>Empties the table (and the Frame Viewer panel below it) without affecting the connection or any
other tab. Do this before reproducing an intermittent issue so the table only contains the run you
care about.</p>

<h3>Export CSV</h3>
<p>Saves whatever rows are currently visible - i.e. respecting the text, status and device
filters - to a CSV file (the Device column comes last in the file).</p>

<h3>Right-click / Ctrl+C</h3>
<p>Right-click a row (or a multi-selection of rows) for <b>Copy Row(s) as Text</b> - every column,
tab-separated, ready to paste into a spreadsheet - or <b>Copy Row(s) as Hex Bytes (TX/RX)</b>,
which copies just the literal wire bytes without the decoded columns in the way. <b>Ctrl+C</b> does
the same as "Copy Row(s) as Text" on whatever's currently selected.</p>

<h3>Frame Viewer</h3>
<p>Below the table, decodes whichever transaction row is currently selected into its TX and RX
Modbus frames side by side - not just the register values, but the actual frame structure: the
MBAP header (Transaction ID, Protocol ID, Length, Unit ID) for TCP, or Unit ID plus CRC/LRC for
RTU/ASCII, then the function code, data bytes, and any exception code, plus the raw hex for both
directions along the bottom. Each row is decoded with the framing of the device it went to - so
an RTU-over-TCP gateway's traffic is shown as RTU frames, next to another device's Modbus TCP
frames.</p>
<p>Select a row by clicking it or by navigating with the arrow keys, Home/End, or Page Up/Page
Down - the Frame Viewer updates immediately either way, and the table scrolls to keep the selected
row visible even while new transactions keep arriving underneath you.</p>
<p>The <b>Hide Frame Viewer</b> button (next to Export CSV) collapses the panel so the table gets
the tab's full height when you just want to scan through transactions - click it again
(<b>Show Frame Viewer</b>) to bring it back; the last decoded frame is still there, not cleared.</p>
<p>Every part of the decoded frame can be selected and copied: right-click (or <b>Ctrl+C</b> on a
selection) either the TX or RX field table for <b>Copy Row(s)</b> - tab-separated, ready to paste
into a spreadsheet. The raw hex line along the bottom can be click-dragged to select and copied
directly (Ctrl+C or right-click) like any selectable text, for pasting straight into a hex viewer
or a bug report.</p>
"""),

    ("Trend", """
<h2>Trend</h2>
<p>Graphs up to 20 pens per page (up to 10 pages) over time, either following the live clock or
reviewing history. Useful
for spotting slow drift, verifying a control loop is actually responding, or capturing a transient
you can't watch a numeric table fast enough to catch.</p>

<h3>Pages</h3>
<p>The tabs above the graph are <b>pages</b>, each its own graph with its own 20 pens - e.g. one
page per meter. <b>+</b> adds a page (up to 10); double-click a page tab, or right-click it, to
rename it; right-click to delete it (the last page can't be deleted; a page with pens asks
first). Every page keeps polling while the trend runs, so switching
pages shows full live history; the time window, zoom, scroll and Graph Properties are shared.
Record / Replay records the page shown when recording starts.</p>

<h3>Running</h3>
<p><b>Start Trend</b> / <b>Stop Trend</b> poll every pen at the <b>Interval</b> (200-60000 ms,
default 1000). Each pen reads from its own tag's device; a pen whose device is offline is
skipped, and the trend only stops ("Trend Stopped") when no device at all is connected. Pens are
added while the trend is stopped. Each pen keeps its latest 20,000 points.</p>

<h3>Pens</h3>
<p><b>Add Pen</b> opens the <b>Trend Pens</b> grid for the shown page: 20 slots (SCADA-style)
with the columns <b>On</b>, <b>Tag</b>, <b>Label</b>, <b>Index</b>, <b>Scale</b> and <b>Color</b>.
Enable the ones you want, click the &#8942; button in the Tag column to pick a tag from the
<b>Select Tag</b> popup, and set a color. With two or more devices the popup has a <b>Device</b>
filter and lists each tag as "V1 (METER 2)"; the legend then shows the device too. A pen's type,
address, count, and format all come from whichever tag you pick, not from separate fields here.
Only tags on Holding or Input Registers with a numeric (or Hex) format show up in that list - Coils,
Discrete Inputs, and the Bool format are left out, since a trend line is meant for continuously
varying values rather than on/off state. If you need to watch a digital point over time, add it
as a Tag and check its Read Value column instead. If none exist yet, the popup's tag list is just
empty - click its <b>Add Tag...</b> button to jump straight to the Tags tab and create one (this
closes the Trend Pens grid, since adding a tag needs the Tags tab visible). </p>
<ul>
<li><b>Label</b> - an optional legend name instead of the tag's name.</li>
<li><b>Index</b> (0-124) - which decoded value to plot from a multi-register tag (0 = the first).</li>
<li><b>Scale</b> - <b>Auto</b> (default) plots the tag's engineering value if it has scaling
enabled (see Tags Monitoring), else the raw value - turning scaling on or off for the tag changes
what the pen shows immediately; <b>Raw</b> always plots the raw decoded value; <b>Scaled</b>
always uses the scaling and plots nothing if there is none. Scaling applies at Index 0 only.</li>
</ul>

<h3>Navigating</h3>
<p>The <b>View Range</b> row sits above the graph: Time Window, From/To + Go, Auto Scroll, Zoom
In/Out, and <b>Hide Stats</b>, which collapses the Min/Max/Average table below the graph so the
graph gets the whole height (the table is otherwise only as tall as its pens need).</p>
<p>The <b>Auto Scroll</b> checkbox shows and
controls whether the view is following the live edge. While checked, it keeps advancing to
"now" as new data arrives. Scrolling the history bar away from its live end, zooming, or jumping
to a From/To range all uncheck it automatically and leave the view exactly where you put it,
however long the trend keeps running - new data doesn't interrupt you. Checking it again jumps
straight back to the live edge and resumes following; dragging the scrollbar all the way back to
its live end does the same. Everything plotted is just what's been collected in the current
session - there's no separate historical database to switch into.</p>
<p>The scrollbar just below the graph pans through everything collected so far, including while
the trend is actively running - drag it right to catch up to the newest data, or left to look back.
<b>Time Window</b> picks how much time is visible at once (1 min to 24 hours). <b>Zoom In/Out</b> halves or doubles
that span around wherever you're currently looking (between 5 seconds and 7 days). <b>From</b>/<b>To</b> plus <b>Go</b> jumps
straight to a specific range.</p>
<p>Hovering the mouse over the graph drops a crosshair line and updates the legend below each
pen's name with its value at that point in time, so you can read an exact number off the trace
without switching to CSV logging. The Min/Max/Average table below the graph updates to match the
hovered point too; move the mouse away and everything goes back to showing the current live
values.</p>

<h3>Graph Properties</h3>
<p>Set the X and Y axis titles, background/axis/grid colors, whether gridlines are shown, and
whether the Y axis auto-ranges to the data or uses a fixed Min/Max. Gridlines default to black;
change them here if you'd rather have something more subtle for a printed report.</p>

<h3>Logging and printing</h3>
<p><b>Log to CSV</b> appends a timestamped row per pen on every poll tick (with several pages,
the pen name is prefixed with its page). <b>Print</b> saves the
current graph view as a PNG image or a PDF document - useful for attaching evidence of a fault
condition to a service report.</p>

<h3>Detach</h3>
<p><b>Detach</b> pops the whole Trend view out into its own resizable, maximizable window that
stays on top of the main window, so you can watch it while working in another tab (Tags,
Script, ...) instead of switching back and forth. The Trend tab itself shows a red X while
detached, as a reminder that the real view has moved. Click <b>Fixed</b> at
the bottom of the floating window (or just close it) to dock the view back into its tab.</p>
"""),

    ("Server Mode", """
<h2>Server Mode</h2>
<p>The Server tab makes ModbusLens act as a Modbus TCP <b>slave</b> device instead of a client -
useful for testing your own SCADA/PLC program against a fake device, without needing real
hardware on hand, or for validating a Script or Tag configuration before pointing it at
production equipment.</p>

<h3>Starting the server</h3>
<ol>
<li>Pick the <b>Mode</b>: <b>Simulate</b> (default) or <b>Gateway</b> (see below).</li>
<li>Set <b>Server Address</b> (default <code>0.0.0.0</code>, accepting connections on any network
interface), <b>Port</b> (default <b>5020</b>, 1-65535), and <b>Unit ID</b> (default 1). The server
only answers requests for that one Unit ID.</li>
<li>Click <b>Start Server</b>. Mode and these settings are locked while it runs.</li>
</ol>
<p>Once running, pick a <b>Data Space</b> (Coils, Discrete Inputs, Holding Registers, or Input
Registers), set a Start Address (0-999) and Count (1-200, default 20), and click <b>Load</b> to
view that range - each data space has 1000 addresses (0-999). Changing the Data Space reloads by
itself, and the table refreshes every half second (skipping a cell you're editing).</p>

<h3>Editing values</h3>
<p>Double-click a Value cell to set it directly, as if you were the field device generating
that reading. Any Modbus master that connects to this server sees the same value. Coils and
Holding Registers are also writable by a remote master; Discrete Inputs and Input Registers are
read-only from the network side (as in real Modbus), but you can still set them yourself from
the GUI to simulate a live sensor. A coil/discrete input cell takes <code>1</code>,
<code>true</code> or <code>on</code> (anything else is 0); a register cell takes a whole number,
kept to 16 bits.</p>

<h3>One server at a time</h3>
<p>Only one Server tab can be running at once, across every open window. ModbusLens builds the
simulator on <a href="https://github.com/pymodbus-dev/pymodbus">pymodbus</a>'s
<code>ModbusSimulatorContext</code>/<code>ModbusServerContext</code> for the datastore and its
<code>StartTcpServer</code> helper to run the listener. <code>StartTcpServer</code> spins up its
own asyncio event loop in the thread that calls it and is meant to run one instance per process -
it isn't designed to have two independent listeners active at the same time. ModbusLens runs it in
a background thread and tracks the single active instance itself; starting a second one while
another is running shows a <b>Server Already Running</b> message. Stop the first one to free it up.</p>

<h3>Connecting to your own server</h3>
<p>Add a device on the Overview pointing at <code>127.0.0.1</code> (or your machine's LAN IP)
on the server's port - remember the server defaults to <b>5020</b> while a new device defaults to
502, so change one of them - with the server's Unit ID, and connect it. You then have a complete
self-contained loop for testing Tags, Trend, or a Script with zero risk to real equipment, all in
one window. (A Script can also skip the network and talk to the server directly with Target
<b>Server (Local)</b>.)</p>

<h3>Gateway mode</h3>
<p>Switch <b>Mode</b> to <b>Gateway</b> to turn the Server tab from a simulator into a real
TCP-to-serial bridge: instead of answering from a local, manually-set datastore, every request
that arrives over TCP is relayed to a real downstream serial (RTU/ASCII) device, and the device's
actual response is returned - the same Unit ID is used on both sides, as a transparent
passthrough. This is how you make a serial-only device (an old PLC, energy meter, VFD, ...)
reachable from anywhere on the network, without buying dedicated gateway hardware.</p>
<p>Fill in the <b>Downstream Serial Device</b> group (COM Port, Baud, Parity, Stop Bits, Byte
Size, Framing - defaults 19200, None, 1, 8, RTU) the same way you would in a device's
Connection Settings, then <b>Start Server</b> as usual. Only function codes 1, 2, 3, 4, 5, 6, 15
and 16 are relayed (anything else gets Illegal Function), and only for the server's Unit ID - one
gateway relays to one downstream unit. The COM Port box also accepts a pyserial URL such as <code>socket://192.168.1.254:4196</code> for a device behind a transparent serial-to-Ethernet converter (raw RTU over TCP) - baud/parity are then set on the converter itself, not here. The <b>Gateway Activity</b> table replaces Data Space View while running,
logging every relayed request live: time, direction, function, address, and result - including a
real device exception (e.g. Illegal Data Address) passed straight through, or, if the downstream
device doesn't respond or the serial connection itself is down, the standard Modbus gateway
exception codes (<b>Gateway Path Unavailable</b> / <b>Gateway Target Device Failed to
Respond</b>). The table keeps the last 500 rows; <b>Clear Log</b> empties it.</p>
<p>Like every other feature in ModbusLens, Gateway mode only runs while the app itself stays
open - closing the window, or the PC sleeping or restarting, stops it. It's an interactive bridge
for testing, commissioning, or temporarily sharing access to a device, not an unattended 24/7
production gateway (which would need to run headless, auto-restart, and survive indefinitely
without a GUI open - a different kind of tool than ModbusLens is today).</p>
"""),

    ("Scripting", """
<h2>Scripting</h2>
<p>The Script tab runs small test sequences against a device using a purpose-built
command language - not a general-purpose one, just enough to write values, wait, read them back,
and repeat. It's meant for repeatable acceptance tests, burn-in sequences, and quick automated
checks you'd otherwise click through by hand every time.</p>

<h3>Commands</h3>
<table cellspacing="6">
<tr><td><code>WRITE COIL &lt;addr&gt; = ON|OFF</code></td><td>Write a coil.</td></tr>
<tr><td><code>WRITE HR &lt;addr&gt; = &lt;expr&gt;</code></td><td>Write a holding register.</td></tr>
<tr><td><code>WRITE &lt;tag name&gt; = &lt;expr&gt;</code></td><td>Write to whatever type/address that tag is configured for.</td></tr>
<tr><td><code>READ COIL|DI|HR|IR &lt;addr&gt;</code></td><td>Read a value and log it.</td></tr>
<tr><td><code>READ &lt;tag name&gt;</code></td><td>Same, by tag name instead of type/address.</td></tr>
<tr><td><code>DEVICE &lt;device name&gt;</code></td><td>Send the following commands to that device
(name as on the Overview, any case, spaces allowed, quotes optional). A script starts on the
device picked in the Script tab's <b>Device</b> dropdown. Client Connection target only. Add
Tag/Insert Tag add this line for you when the tag is on another device than the one in effect at
the cursor.</td></tr>
<tr><td><code>LET &lt;name&gt; = &lt;expr&gt;</code></td><td>Assign a variable.</td></tr>
<tr><td><code>LOG &lt;expr&gt;</code></td><td>Print text/numbers to the console.</td></tr>
<tr><td><code>WAIT &lt;expr, ms&gt;</code></td><td>Pause without freezing the UI.</td></tr>
<tr><td><code>REPEAT &lt;expr&gt; ... END</code></td><td>Loop a block of commands a fixed number of times.</td></tr>
<tr><td><code>REPEAT UNTIL &lt;expr&gt; &lt;op&gt; &lt;expr&gt; ... END</code></td>
<td>Loop until a condition becomes true, checked before each pass.</td></tr>
<tr><td><code>IF &lt;expr&gt; &lt;op&gt; &lt;expr&gt; THEN &lt;command&gt;</code></td>
<td>Run one command conditionally. op is <code>== != &gt; &lt; &gt;= &lt;=</code>.</td></tr>
<tr><td><code>ASSERT &lt;expr&gt; &lt;op&gt; &lt;expr&gt;</code></td>
<td>Check a condition and record PASS/FAIL in the Results panel. A FAIL is logged and
recorded but does <b>not</b> stop the script - it's a check, not a stop condition. A
genuine error while evaluating it (e.g. a failed read) still stops the script, same as
any other command.</td></tr>
</table>

<h3>Syntax basics</h3>
<ul>
<li>Lines starting with <code>#</code> or <code>//</code> are comments; blank lines are ignored.</li>
<li>Commands are case-insensitive. Numbers can be decimal (<code>12</code>, <code>1.5</code>,
<code>-3</code>) or hex (<code>0x1F</code>); addresses too.</li>
<li>Addresses in a script are always raw 0-based protocol offsets (<code>HR 0</code> is the first
holding register, 40001 in 1-based terms), whatever the Tags tab's 0-Based setting.</li>
<li>A coil value in <code>WRITE</code> is <code>ON</code>/<code>OFF</code>, <code>1</code>/<code>0</code>
or <code>TRUE</code>/<code>FALSE</code>. Inside expressions and comparisons use <code>1</code>/<code>0</code>
(<code>ON</code> there would be read as a name).</li>
<li>A register WRITE sends a whole 16-bit number: decimals are truncated and negatives wrap
(<code>-1</code> is written as 65535).</li>
<li><code>IF ... THEN</code> runs one command, which can't be REPEAT, END or another IF.</li>
</ul>

<h3>Expressions</h3>
<p>An expression can mix numbers, <code>"strings"</code>, variables, parentheses, and
<code>+ - * /</code> (<code>/</code> gives a decimal result). Writing a bare <code>HR 0</code> inside an expression reads that register
inline (shorthand for <code>READ HR 0</code>); a bare tag name works the same way (e.g.
<code>LET x = Boiler_Temp + 1</code> does a fresh read of the Boiler_Temp tag's register). The tag's Address is converted with the
Tags tab's 0-/1-based setting, so it hits the same register the Tags tab does. Tag names
are case-sensitive; with several devices, the current device's tag of that name is used (else the
first one found on any device), and the read always goes to the current device. A tag name is only tried if
the name isn't already a variable you've assigned with <code>LET</code> - a LET variable always
takes priority over a tag of the same name. <code>+</code> also concatenates text
with numbers, so <code>LOG "value is " + x</code> works as expected. Types: COIL, DI (Discrete
Input), HR (Holding Register), IR (Input Register).</p>

<h3>Compile and Run</h3>
<p><b>Compile</b> checks the script's syntax without touching the device - use it to catch typos
before running anything. <b>Run</b> executes the script step by step; because it can write to a
live device, Run on a Client Connection target shows a warning first (with a "Don't remind me
again" option, which is remembered even if you then Cancel) reminding you to be careful on
in-service equipment. <b>Stop</b> halts a running script at any point. <b>Open...</b> and
<b>Save...</b> load and save scripts (<code>.mls</code> or <code>.txt</code>), and <b>Clear
Console</b> empties the console (which keeps the last 5000 lines and is also copied to System Logs
with a <code>[Script]</code> prefix). Every script READ/WRITE also appears in the Raw Data tab as
"Script READ/WRITE &lt;type&gt; &lt;addr&gt;" with its device, and joins the same busy-range
safety interlock as Tags - a clash logs "... SKIPPED -- safety interlock: range busy".</p>

<h3>Target and Device</h3>
<p>The <b>Target</b> dropdown picks whether the script talks to a real device
(<b>Client Connection</b>) or to ModbusLens's own Server tab (<b>Server (Local)</b>), so you can
dry-run a sequence safely with no real device attached - start a server in Simulate mode, switch
the script to Server (Local), and run it exactly as it would run against the real thing. A Server
(Local) script can write all four types (it's simulating the device itself), uses the server's
0-999 addresses, and doesn't work while the Server tab is in Gateway mode.</p>
<p>With two or more devices, a <b>Device</b> dropdown next to Target picks which device a Client
Connection script starts on (it's disabled for Server (Local)); a <code>DEVICE</code> line switches
device mid-script, so one script can work with several meters. The device must be connected to
Run.</p>

<h3>Variables panel</h3>
<p>The panel on the right lists every variable your script assigns with <code>LET</code>, updating
live as the script runs - no need to sprinkle <code>LOG</code> lines everywhere just to see what a
variable currently holds. It populates as soon as you <b>Compile</b> (values blank until the script
actually runs), keeps updating on every step while running, and holds the last values after the
script finishes or is stopped, so you can still read them afterward.</p>

<h3>Assertion Results panel</h3>
<p>Below the Variables panel, this table logs every <code>ASSERT</code> outcome as the script
runs: the assertion text, a color-coded <b>PASS</b>/<b>FAIL</b>/<b>ERROR</b> status, and the actual
values compared. Unlike a failed read or write, a failed assertion doesn't stop the script - so a
single run can report every check's outcome, not just the first failure - which makes
<code>ASSERT</code> the right tool for a repeatable acceptance test where you want a full pass/fail
summary at the end. It's cleared each time you Compile or Run.</p>

<h3>Other tools in the editor</h3>
<ul>
<li><b>Add Tag</b> - opens a popup listing every tag on the Tags tab (any type, not just analog),
and picking one drops its name straight into the script at the cursor. If the tag you need doesn't
exist yet, the popup's own <b>Add Tag...</b> button jumps to the Tags tab with a new, blank row
ready to name and configure.</li>
<li><b>Insert Tag</b> - the right-click menu shortcut for the same thing: drops a tag's name
straight into the script at the cursor, so you don't have to remember or retype it - the script
then resolves it against whatever that tag is currently configured as (see WRITE/READ above), so
editing the tag later doesn't require touching the script.</li>
<li><b>CPU usage indicator</b> - shows live system CPU load ("CPU: --" if it can't be measured),
useful for spotting a runaway loop that's spinning the interpreter faster than intended.</li>
<li>With several devices, the tag popup has a <b>Device</b> filter and shows each tag's device.</li>
</ul>

<h3>Sample Scripts</h3>
<p>A few complete, working examples to adapt - copy one into the editor, adjust the addresses for
your device, and Compile before Run.</p>

<h4>1. Basic write/read/log sequence</h4>
<pre>LET x = HR 0 + 10
WRITE HR 1 = x
WAIT 500
LOG "HR1 is now " + x
IF HR 1 &gt;= 100 THEN LOG "over threshold"</pre>
<p>Reads holding register 0, adds 10, writes the result to register 1, waits half a second for
the device to settle, then logs and checks it against a threshold.</p>

<h4>2. Toggle a coil N times (blink test)</h4>
<pre>REPEAT 5
    WRITE COIL 0 = ON
    WAIT 250
    WRITE COIL 0 = OFF
    WAIT 250
END
LOG "Blink test complete"</pre>
<p>Good for a quick relay/output wiring check - watch the physical output or an LED toggle five
times, half a second per cycle.</p>

<h4>3. Poll a register until it reaches a target value</h4>
<pre>LET attempts = 0
REPEAT 60
    LET attempts = attempts + 1
    IF HR 2 &gt;= 500 THEN LOG "Target reached after " + attempts + " checks"
    WAIT 1000
END
LOG "Done polling"</pre>
<p>Checks holding register 2 once a second for up to a minute - useful for waiting on a startup
sequence, a warm-up temperature, or any value that changes slowly on its own. Plain
<code>REPEAT</code> doesn't have a break/exit, so this always runs the full 60 checks even after
the target is reached; it's a bounded polling window with a built-in timeout. See the next example
for a version that stops the instant the condition is met.</p>

<h4>4. Wait until a value is reached, no fixed check count</h4>
<pre>REPEAT UNTIL HR 2 &gt;= 500
    WAIT 1000
END
LOG "Target reached"</pre>
<p>Same idea as the previous example, but stops the moment holding register 2 hits 500 instead of
always running a fixed number of checks - and if it's already &gt;= 500 before the loop starts, the
body never runs at all (the condition is checked before each pass). If the condition never becomes
true, this stops on its own with a clear error after a very large number of iterations rather than
hanging forever - see Limits below.</p>

<h4>5. Ramp a setpoint up gradually</h4>
<pre>LET setpoint = HR 10
REPEAT 10
    LET setpoint = setpoint + 5
    WRITE HR 10 = setpoint
    LOG "Setpoint now " + setpoint
    WAIT 2000
END</pre>
<p>Steps a holding register up by 5 every 2 seconds instead of jumping straight to a final value -
useful for equipment that shouldn't see a large setpoint change all at once.</p>

<h4>6. Read several points and log them together</h4>
<pre>LET temp = HR 0
LET pressure = HR 1
LET running = COIL 0
LOG "Temp=" + temp + " Pressure=" + pressure + " Running=" + running</pre>
<p>A one-shot snapshot across mixed types (registers and a coil) in a single readable log line -
handy at the start or end of a longer script to record a baseline.</p>

<h4>7. Conditional checks with IF</h4>
<pre>LET temp = HR 0
IF temp &gt; 90 THEN LOG "WARNING: temperature high (" + temp + ")"
IF temp &lt; 10 THEN LOG "WARNING: temperature low (" + temp + ")"
IF temp == 0 THEN LOG "Sensor may be disconnected"
IF COIL 0 != 1 THEN WRITE COIL 1 = ON</pre>
<p>Each <code>IF</code> only runs <i>one</i> command when its condition is true, and there's no
ELSE - that's why this reads as a sequence of independent checks rather than a single branching
block. The last line shows an IF driving a WRITE instead of a LOG: turn on coil 1 (e.g. an alarm
lamp) whenever coil 0 (e.g. "running") isn't set. Valid comparisons are
<code>== != &gt; &lt; &gt;= &lt;=</code>, and either side can be a register/coil read, a
variable, or a literal number.</p>

<h4>8. The same thing, by tag name instead of type/address</h4>
<pre>IF Boiler_Temp &gt; 90 THEN LOG "WARNING: temperature high (" + Boiler_Temp + ")"
WRITE Pump_Enable = ON</pre>
<p>Assumes a <code>Boiler_Temp</code> (Holding/Input Register) and <code>Pump_Enable</code>
(Coil) tag already exist on the Tags tab - use <b>Insert Tag</b> to drop the name in without
retyping it. Reads a tag name like <code>HR 0</code>/<code>COIL 0</code> would (one raw register
or bit at the tag's address), but stays correct if that tag's address ever changes, since the
script only cares about the name.</p>

<h4>10. Two meters in one script</h4>
<pre>DEVICE METER 1
LET a = HR 1699
DEVICE METER 2
LET b = HR 1699
LOG "Raw V1 word: meter 1=" + a + " meter 2=" + b</pre>
<p>Reads the same register from two devices on one gateway by switching with <code>DEVICE</code>.</p>

<h4>9. Acceptance test with ASSERT</h4>
<pre>WRITE HR 0 = 100
WAIT 200
ASSERT HR 0 == 100
ASSERT COIL 0 == 1
LOG "Acceptance test complete - see Results panel"</pre>
<p>Writes a value, then checks it and a coil's state landed as expected. Both checks are recorded
in the Results panel with PASS/FAIL - a FAIL doesn't abort the script, so every assertion below it
still runs and reports, giving you a complete pass/fail summary in one run.</p>

<h3>Limits</h3>
<p>To keep a typo from hanging the app or running forever: a script can have at most 5000
instructions, a REPEAT count at most 1,000,000 (<code>REPEAT UNTIL</code> shares that iteration
cap - if the condition never becomes true, it stops with an error instead of looping forever), a
WAIT at most 86,400,000 ms (24 hours), and expressions at most 100 levels of nesting; WAIT and
REPEAT values can't be negative. A loop with no WAIT runs up to 200 instructions at a time, then
hands control back to the interface for at least 20ms before continuing - so it never freezes the
app, but a WAIT-less write loop still sends bursts of writes; put a WAIT in any loop that talks to
a real device. See <b>Troubleshooting</b> for what the
common error messages mean.</p>
"""),

    ("Scanner", """
<h2>Scanner</h2>
<p>Auto-discovers which addresses respond on a device - useful when you don't have a register map
yet. Works the same way over TCP or serial. With two or more devices, the <b>Device</b> dropdown
picks which device to scan; the line next to it shows "Scanning: &lt;target&gt; (Unit N)", or that
the device isn't connected yet.</p>

<p>Pick a <b>Function</b> (Coils/Discrete Inputs/Holding/Input Registers; default Holding
Registers), a <b>Start</b>/<b>End</b> address (raw 0-based offsets, 0-65535; default 0-999) and a
<b>Probe timeout</b> (50-5000 ms, default 300), then <b>Start Scan</b>; <b>Stop</b> ends it early
and <b>Clear Results</b> empties the output. Rather than checking one address at a time, it
probes the largest block the function allows first (125 registers or 2000 coils/inputs, with a
short pause between probes) - a clean read means every address in that block responds. If a block doesn't fully respond, it's split in half and each half is probed
again, narrowing down until it knows exactly which individual addresses do and don't respond.
This is far fewer requests than a naive one-by-one sweep whenever most of a range is
contiguous, which is the common case for a real device's register map.</p>
<p>The <b>Summary</b> line lists the responding addresses as merged ranges (e.g.
<code>0-15, 20, 45-99</code>). A device that returns <b>Illegal Function</b> for the whole
range stops the scan immediately with a clear message, since every address would fail the same
way - try a different Function instead. A genuine timeout or dropped connection also stops the
scan, since that means the device itself stopped responding, not that a particular address is
invalid.</p>
<p>Reuses the device's existing connection rather than opening a second one. So nothing else
polls while a scan is in progress, starting one stops Tags monitoring (for every device) and
Address Table Live Monitoring - restart them yourself afterwards - and pauses Trend polling and
the auto-reconnect watchdog, which resume when the scan ends. A scan is refused while a Script is
running ("stop it before starting a scan").</p>
<p>A shorter <b>Probe timeout</b> makes a scan faster but can misreport a slow-but-valid address
as not-responding, especially over a serial connection where every probe is one real bus
round-trip. If a scan seems to be missing an address you know exists, try a longer timeout.</p>
<p>Don't know the serial connection parameters (baud rate, parity, stop bits) for a device in
the first place? See <b>Serial Discovery</b>.</p>

<h3>Create Tags From Scan</h3>
<p>Once a scan finds responding addresses, <b>Create Tags...</b> opens a dialog listing the
merged ranges found - check the ones you want and click <b>Create Tags</b> to generate one new
row per individual address in the Tags tab, saving you from adding them one at a time by hand.
Each generated tag is named with the classic 5-digit Modicon convention (type digit plus a
4-digit 1-based address, e.g. <code>HR_40001</code> for a Holding Register, <code>COIL_00001</code>
for a Coil) so it stays addressable and unambiguous even without a real register map. An address
that already has a tag of that type on that device is skipped rather than creating a duplicate.
The tags are created on the device that was scanned, with the Function that was scanned, and use
the Tags tab's 0-/1-based setting for their Address; the Tags tab opens afterwards.</p>
"""),

    ("Serial Discovery", """
<h2>Serial Discovery</h2>
<p><b>Diagnostics &gt; Serial Discovery</b> sweeps common baud rate/parity/stop-bit/Unit ID
combinations against a COM port to find which one a serial device actually speaks, for when its
settings aren't documented. The same sweep is also available in <b>Diagnostics &gt; Find
Devices</b> (Transport: Serial (Parameter Sweep)), which the <b>Find Devices...</b> button in a
device's Connection Settings (Serial) opens.</p>
<p>Pick the <b>COM Port</b> and <b>Framing</b> (RTU/ASCII), a <b>Start</b>/<b>End Unit ID</b>
range (0-255) to also try, and a <b>Per-trial timeout</b> (50-2000 ms, default 200), then
<b>Start Scan</b>. It tries every combination of 8 common baud rates,
3 parity settings, 2 stop-bit settings, and each Unit ID in the range - byte size is fixed at
8, the near-universal default - opening a short-lived connection for each combination and
sending one Holding Register read. Any reply, including a Modbus exception response, counts as
a match, since that still proves the framing decoded correctly; a garbled response from a
mismatched baud rate won't parse as a valid Modbus frame at all.</p>
<p><b>A match isn't always unique.</b> Stop bits (and occasionally parity) are framing bits, not
data - many UART/USB-serial adapters only check for <i>at least</i> one high bit-time before the
next start bit, so a receiver set for 1 stop bit is easily satisfied by a sender actually using 2,
and vice versa. It's normal to see the same baud/parity/Unit ID reported as a match at both stop-bit
settings. When that happens, prefer whatever the device's own documentation or configuration
screen actually says over guessing from the scan alone - the scan proves "a read got a response,"
not "these are the device's exact settings."</p>
<p>Matches are listed under "Matches found (select one, then Apply)". Select one and click
<b>Apply to Connection Settings</b> (or double-click it) to open Connection Settings pre-filled with
it - for the device you pick, if there are several - then <b>Save Settings</b>. The dialog doesn't
block the main window; closing it stops the scan.</p>
<p>This doesn't reuse the app's shared connection - it opens its own for each combination,
since testing a physical serial setting means actually reopening the port with it. That also
means the port needs to be free: if a connected device in this window uses the port, the scan
refuses to start ("... is in use by a connected device -- disconnect it first"); also close any
other program (Modbus Poll, a terminal, another ModbusLens window) that
might have it open. If the port can't be opened at all, the scan stops immediately with that
message rather than repeating the same failure for every remaining combination.</p>
<p>Keep the Unit ID range narrow (it defaults to just 1) unless you actually need it wider -
each additional Unit ID multiplies the total combination count by 48.</p>
"""),

    ("Diagnostic Functions", """
<h2>Diagnostic Functions</h2>
<p><b>Diagnostics &gt; Modbus Diagnostic Functions</b> reaches the Modbus function codes beyond
basic reads/writes - niche next to everyday polling, but a real gap for compliance and interop
testing. With two or more devices, pick the <b>Device</b> at the top first. Then pick a function
from the dropdown, fill in the couple of parameters it needs (most need none at all), and
<b>Run</b>. The result - or "Failed: ..." with the device's error - shows in the box below and
is also written to System Logs. Hex fields accept spaces, commas and <code>0x</code>.</p>
<ul>
<li><b>Read Exception Status (FC07)</b> - an 8-bit vendor-specific status byte, a lightweight
"is anything wrong" poll some devices support without a full register read.</li>
<li><b>Diagnostics: Loopback / Query Data (FC08-00)</b> - sends bytes you type in <b>Message
(hex)</b> (default <code>1234</code>) and expects the device to echo them back unchanged - a pure comms sanity
check that never touches a real register.</li>
<li><b>Diagnostics: Restart Communications (FC08-01)</b> - asks the device to reinitialize its comm
port; <b>Clear event log/counters too</b> (ticked by default) also clears its event log.</li>
<li><b>Diagnostics: Read Diagnostic Register (FC08-02)</b> - device-specific status bits (e.g.
listen-only mode); the meaning beyond the raw bits is vendor-defined.</li>
<li><b>Diagnostics: Clear Counters (FC08-0A)</b> - clears the device's own diagnostic counters and
register.</li>
<li><b>Get Comm Event Counter (FC11)</b> / <b>Get Comm Event Log (FC12)</b> - a free-running
counter the device bumps on every completed transaction, plus (for the Log) a short history of
recent bus events and a ready/busy status flag.</li>
<li><b>Report Server ID (FC17)</b> - a vendor-defined identifier string plus a run/stop
indicator, historically called "Report Slave ID."</li>
<li><b>Read File Record (FC20)</b> / <b>Write File Record (FC21)</b> - reads or writes records in
the device's file storage, a second address space separate from registers/coils, mostly seen on
energy meters and similar data loggers. Specify the <b>File Number</b> (default 4), <b>Record
Number</b>, and (for a read) the <b>Register Count</b> (1-120), or (for a write) the <b>Data
(hex)</b> (default <code>0001 0002</code>).</li>
<li><b>Mask Write Register (FC22)</b> - sets a register to
<code>(current_value AND and_mask) OR (or_mask AND NOT and_mask)</code> atomically on the device,
so changing a few bits doesn't race against another master's write to the same register between a
plain read and write. Enter the <b>Address</b>, <b>AND Mask (hex)</b> (default FFFF) and <b>OR Mask
(hex)</b> (default 0000).</li>
<li><b>Read FIFO Queue (FC24)</b> - reads a FIFO queue's current contents (without removing them)
from a pointer register, for devices that buffer captured values faster than a master polls
them.</li>
<li><b>Read Device Information (FC43)</b> - vendor name/product code/version and similar text
objects, a standardized alternative to a vendor-specific register for "what device am I talking
to." <b>Read Code</b> selects Basic, Regular, Extended, or a single specific object via
<b>Object Id</b>.</li>
</ul>
<p>Every function here goes through the chosen device's connection like everything else in
ModbusLens - the device has to be connected ("... isn't connected -- connect it first"), and a
run briefly uses its link like any other read/write.</p>
"""),

    ("Data Decoder", """
<h2>Data Decoder</h2>
<p><b>Diagnostics &gt; Decode Registers</b> opens a standalone "paste hex, see every
interpretation" tool - no connection required, and no live Tag involved. Useful when you have a
raw value from somewhere (the Raw Data tab, a device's datasheet, a captured frame) and don't
know how to interpret it, without creating a Tags-tab row and guessing a Format against a live
device.</p>
<p>Type or paste the raw hex bytes - spaces, commas, and <code>0x</code> prefixes are all fine
(<code>41 48 00 00</code>, <code>0x41,0x48,0x00,0x00</code>, and <code>41480000</code> all work
the same). The results table updates live as you type: <b>U16</b>, <b>S16</b>, <b>HEX</b>, and
<b>Binary</b> per register, plus <b>U32</b>/<b>S32</b>/<b>F32</b> when the number of registers
is a multiple of 2 and <b>U64</b>/<b>S64</b>/<b>F64</b> when it's a multiple of 4, <b>ASCII</b> (only
shown when every byte is printable text) and <b>BCD</b> (only shown when every nibble is a valid
0-9 decimal digit), and each register's individual bits as a 16-character binary string. An odd
trailing byte (half a register) is ignored; an odd number of hex digits or a non-hex character is
reported right away.</p>
<p>The <b>Byte/word order</b> dropdown covers all four standard orderings - <b>ABCD</b> (plain
big-endian Modbus, the default), <b>BADC</b> (the two bytes within each register swapped),
<b>CDAB</b> (register order reversed - the same idea as the Tags table's <code>_SWAP</code>
formats), and <b>DCBA</b> (both). Switching it re-decodes the same bytes immediately, no
re-typing needed - useful for eyeballing which ordering actually makes a device's value make
sense (e.g. a plausible-looking float vs. an implausible one). ASCII and BCD are always read in
the order you typed them, independent of this dropdown, since reordering bytes doesn't make
sense for text or packed-decimal data the way it does for a number.</p>
<p>It doesn't block the main window (like Find Devices and Serial Discovery) - it's meant to sit
alongside the Raw Data tab or an external datasheet while you work.</p>
"""),

    ("Multiple Windows", """
<h2>Multiple Windows</h2>
<p>One window already handles any number of devices (see <b>Overview</b>), so you rarely need a
second one. <b>File &gt; New Connection Window</b> still opens a fully independent ModbusLens
window - its own device list, Overview, Address Table, Profiles, Tags, Raw Data, Trend, Server,
Script, and Scanner tab - for keeping two unrelated jobs apart.</p>
<p>Differences from the first window:</p>
<ul>
<li>A new window starts with a single "Device 1" (127.0.0.1:502, Unit 1). The first window
keeps its device list between runs; use Save Session to keep another window's devices.</li>
<li>Only one Server tab can be actively running at a time, across all open windows (see the
Server Mode topic for why).</li>
</ul>
"""),

    ("Troubleshooting", """
<h2>Troubleshooting</h2>
<p>Symptom-first reference for the problems you're most likely to run into. If something here
doesn't cover your case, the Status Log (Address Table) or the console (Script tab) usually has a
more specific message worth reading closely.</p>

<h3>Can't connect over TCP</h3>
<p>When a device's Connect fails, a "Connection Failed" message shows "Couldn't connect NAME --
target, Unit N", the error, and a short checklist ("Check the IP address and port, network
reachability (VPN/Tailscale routes too), and that the device/gateway accepts another
connection."); Connect All lists every device that failed under "These devices couldn't
connect:". The reasoning behind each check:</p>
<ul>
<li><b>Is the Modbus server actually running?</b> A gateway or PLC that's powered on but hasn't
started its Modbus service will refuse the connection outright.</li>
<li><b>IP address and port correct?</b> Double check for typos, and that you're not pointing at a
different device's management IP instead of its Modbus interface.</li>
<li><b>Network connectivity?</b> Try pinging the target first - if that fails, the problem is
routing/cabling, not Modbus.</li>
<li><b>Unit ID matches?</b> Some gateways route by Unit ID to different downstream serial
devices; a wrong ID can connect fine but every read/write then fails or returns the wrong
device's data.</li>
<li><b>Firewall?</b> Windows Firewall or a network firewall blocking outbound port 502 (or
whatever port you configured) will look identical to the device being offline.</li>
<li><b>Gateway connection limit?</b> Small serial-to-Ethernet gateways often accept only a few TCP
clients. Devices with identical settings share one connection, but two devices that differ in
Fast LAN Mode, framing or interface open two.</li>
</ul>

<h3>Can't connect over RTU (Serial)</h3>
<ul>
<li><b>Does the COM port exist and is it free?</b> Only one application can hold a serial port
open at a time - close Modbus Poll, a terminal program, or another ModbusLens window that might
already have it open.</li>
<li><b>Baud rate, parity, stop bits match the device?</b> A mismatch here doesn't always fail
cleanly - it can connect and then return garbage or timeouts instead of an obvious error.</li>
<li><b>Cable and power?</b> Check the USB-to-RS485/RS232 adapter is recognized by Windows (Device
Manager) and the device itself is powered.</li>
<li><b>Unit ID matches the device's configuration?</b> Same reasoning as TCP above.</li>
<li><b>"COMx is already used by "NAME" with different settings"</b> - in one window, every device
on a COM port must share its baud rate, parity, stop bits and framing (they're on the same wire).
Match the settings, or use a different port.</li>
</ul>

<h3>Values look exactly one address off</h3>
<p>This is almost always the 0-based vs 1-based addressing setting. Toggle the <b>0-Based
Addressing</b> checkbox on the Address Table or Tags tab and compare - see the Connecting topic
for the full explanation.</p>

<h3>A 32-bit or 64-bit value (U32/S32/F32, U64/S64/F64) looks like nonsense</h3>
<p>Try the <code>_SWAP</code> variant of the same format. Different vendors order the registers of
a multi-register value differently, and there's no reliable way to detect which one a device
uses - it's trial and error. The Tags table's <b>Raw (Hex)</b> column shows the untouched register
bits regardless of format, which is the fastest way to confirm your mapping once you find the
right combination.</p>

<h3>A write silently didn't happen</h3>
<ul>
<li>Check the Status Log (Address Table), the tag's row, or the Raw Data tab - a rejected write
shows a specific reason rather than just failing quietly, and Raw Data will show it as a Failed
row with the error in the Value column.</li>
<li>If you've configured a write bound (Min/Max) on that register, a rejected write logs
<i>"Write rejected: value ... is outside the configured write bound [...]"</i>. This applies no
matter whether the write came from the Address Table, a Tag, or a Script.</li>
<li>Discrete Inputs and Input Registers are read-only in the Modbus spec itself - no amount of
configuration in ModbusLens will make them writable, because the device won't accept it either.</li>
</ul>

<h3>A tag shows ERROR in Tags Monitoring</h3>
<ul>
<li>Check the tag's <b>Count</b> matches its <b>Format</b> - 32-bit formats (U32/S32/F32, and
their <code>_SWAP</code> variants) need a count that's a multiple of 2; 64-bit formats
(U64/S64/F64, and their <code>_SWAP</code> variants) need a multiple of 4.</li>
<li>Check the address is actually valid on the device - some devices have gaps in their register
map that return an exception rather than a value.</li>
<li>One failing tag no longer stops the rest of the list from updating, so if only one row shows
ERROR while the others keep ticking, the problem is specific to that tag's configuration, not the
connection.</li>
<li>If <i>every</i> tag shows ERROR at once, monitoring will auto-stop after three consecutive
failed polls - that's treated as a lost connection rather than a tag problem (with several
devices, one device dropping doesn't stop monitoring; only its tags show ERROR). ModbusLens will
retry the connection itself automatically (see the next entry); you shouldn't need to do
anything unless it can't recover.</li>
</ul>

<h3>Status shows "Reconnecting..." and it's taking a while</h3>
<p>This is expected - once connected, ModbusLens watches each link and auto-retries with
increasing delays (2s, 4s, 8s... capped at 30s, checked every few seconds) if it drops, rather
than requiring a manual reconnect. If Tags monitoring was running and stopped because every tag failed at once, it
resumes automatically the moment the connection recovers. If it's still stuck reconnecting after
a while, the underlying cause is the same as an initial connection failure - work through the
TCP or Serial checklist above (device power, cabling, IP/port, Unit ID). Clicking the device's
<b>Disconnect</b> (Overview card) or <b>Disconnect All</b> stops the retry loop, if you want to
give up on it.</p>

<h3>"Duplicate Addresses" or "Overlapping Ranges" when starting monitoring</h3>
<p>Two tags of the same Modbus type on the same device are pointing at the same address
("Duplicate Addresses" - monitoring won't start until you change them) or at overlapping ranges
("Overlapping Ranges" - a warning you can continue past). This is usually a copy-paste mistake
when building a large tag list - check the Address column against your register map. The same
address on two different devices is fine. ("Duplicate Address: No free address available" means a
new tag couldn't be moved to a free address of that type.)</p>

<h3>"Server Already Running"</h3>
<p>Only one Server tab can be active at a time, across every open ModbusLens window, because the
underlying Modbus library only supports one active server per process. Stop the other one first.</p>

<h3>A script won't Compile</h3>
<p>Compile errors describe exactly what's wrong and where, for example:</p>
<ul>
<li><code>REPEAT without matching END</code> / <code>END without matching REPEAT</code> - a
REPEAT block wasn't closed, or an extra END has nothing to close.</li>
<li><code>unrecognized command: ...</code> - a typo in a command keyword.</li>
<li><code>IF...THEN cannot contain REPEAT, END, or a nested IF</code> - IF runs a single
command.</li>
<li><code>unknown type 'X' (use COIL, DI, HR, or IR)</code>, <code>invalid ON/OFF value: ...</code>,
<code>REPEAT requires a count or 'UNTIL &lt;condition&gt;'</code>, <code>DEVICE requires a device
name, e.g. DEVICE METER 2</code>, <code>script exceeds the 5000-instruction limit</code>.</li>
<li><code>invalid address: ...</code> / <code>address ... out of range (0-65535)</code> - the
address after a type (COIL/DI/HR/IR) isn't a valid number in range.</li>
</ul>

<h3>A script won't Run (compiles fine, fails immediately)</h3>
<ul>
<li><b>Not Connected: "Connect NAME before running a Client-target script."</b> - the device in
the Script tab's Device dropdown isn't connected. Connect it first, or switch Target to Server
(Local) to test against the Server tab instead. If a device disconnects mid-run (or a
<code>DEVICE</code> line names one that isn't connected) the script stops with <code>NAME is not
connected</code>.</li>
<li><b>Server Not Running: "Start the Server tab before running a Server-target script."</b> - the
opposite case (<code>Server is not running - start it on the Server tab first</code> if it stops
mid-run).</li>
<li><code>unknown device '...'</code> / <code>DEVICE only applies to a Client Connection
script</code> - a DEVICE line names a device that doesn't exist, or the script targets the
Server.</li>
<li><code>unknown tag '...'</code> / <code>undefined variable or tag '...'</code> - a name that's
neither a LET variable nor a tag (tag names are case-sensitive; <code>ON</code>/<code>OFF</code>
aren't values inside an expression - use 1/0).</li>
<li><code>division by zero</code>, <code>expected a number here, got text</code>, <code>WAIT
duration exceeds the 86400000ms limit</code>, <code>REPEAT count exceeds the 1000000 limit</code>.</li>
<li><code>... cannot be written to a client connection</code> - a WRITE targeted a
Discrete Input or Input Register, which are read-only by the Modbus spec.</li>
<li><code>read failed for Holding Register 12</code> (or <code>read failed for tag '...'</code>) -
the read inside an expression failed against the live device (or the range was busy); check the
address is valid, the same way you would for a Tags tab ERROR.</li>
<li><code>REPEAT UNTIL exceeded the 1000000-iteration limit without the condition becoming true</code>
- the condition never became true; double-check the address/comparison, or that the device is
actually changing the value you're waiting on.</li>
</ul>

<h3>Network Discovery isn't finding a device, or feels slow</h3>
<p><b>Diagnostics &gt; Network Discovery &amp; Diagnostics</b> scans the local network and checks
which devices respond to Modbus - useful when you know a PLC is on the subnet but don't know its
current IP. It combines a few techniques:</p>
<ul>
<li><b>Fast TCP scan</b> (the default) - probes the subnet's addresses in parallel for an open
Modbus port and checks each hit really answers Modbus; a /24 takes about a second. No extra
software needed.</li>
<li><b>ARP Mode</b> (optional) - adds MAC address/vendor lookup and packet capture. This is the
part that needs <b>Npcap</b>; without it, ARP Mode falls back to a slower ping-and-ARP-table
sweep that misses devices on networks that block ICMP.</li>
<li><b>Device filtering</b> - "Show only Modbus devices" hides everything else from the list, and
<b>Scan Unit IDs (1-247)</b> asks each Modbus host which Unit IDs respond.</li>
</ul>
<p>The first device found fills in the dialog's own IP/Port fields for its diagnostics. To set a
found device up as a ModbusLens device, use <b>Diagnostics &gt; Find Devices</b>, whose
<b>Apply to Connection Settings</b> fills in a device's connection for you.</p>
<p>For ARP Mode, install Npcap with <i>WinPcap compatible mode</i> enabled during setup, then
restart ModbusLens - see the README's Notes section for the download link and exact install
options.</p>
<p>The scan range is sized to the selected interface's actual subnet mask, not always a flat /24
- on a /25 or smaller it only probes that real range, and on anything wider than /24 (e.g. a
VPN-routed /16) it's capped to the /24 containing that interface's own IP, since probing tens of
thousands of addresses one TCP connect at a time isn't practical. If a device you know exists on
a wider VPN subnet doesn't turn up, it may simply be outside that /24 - enter its IP directly
instead of relying on discovery. The progress bar shows the specific IP currently being probed,
not just a percentage, so you can see exactly where a scan is up to.</p>

<h3>"Check for Updates" fails or times out</h3>
<p>The Updates tab in Help &gt; About queries GitHub directly and needs outbound internet access.
If it can't reach GitHub (offline, a proxy, or a firewall blocking it), it reports the failure
rather than hanging, and gives you a direct link to the Releases page to check manually.</p>
"""),

    ("Tips & Safety", """
<h2>Tips &amp; Safety</h2>
<ul>
<li>ModbusLens can both read <i>and write</i> live Modbus values. An incorrect write to a
production device can cause unexpected motion, changed setpoints, or bypassed safety logic.
Know the device's register map and have authorization before writing to anything real.</li>
<li>Use <b>Server Mode</b> as a local practice target: start a server, add a device at
127.0.0.1 on the server's port (5020 by default) in the same window - or point a Script at
Target <b>Server (Local)</b> - and try things out, including a full Script or Tag list, before
pointing at real equipment.</li>
<li>For anything that writes automatically and repeatedly (a Script, or a Tag in Write mode with
monitoring active), consider setting a write bound (Min/Max) on the target register first - see
the Address Table topic. It costs nothing when everything is working, and catches a typo the
moment it would otherwise reach the device.</li>
<li>With several devices, check which device a tool is pointed at before writing: Address Table,
Script and Scanner each have their own Device dropdown, and Write All on the Tags tab writes the
open device tab's tags (or every device's, on the All tab).</li>
<li>If something isn't behaving as expected - wrong values, failed writes, a script that won't
run - check <b>Troubleshooting</b> before assuming it's a device problem; most of the common
causes are configuration mismatches on this end (addressing mode, word order, Unit ID) rather
than a fault on the device.</li>
</ul>
"""),
]


class DocumentationDialog(QDialog):
    """A simple two-pane Help viewer: topic list on the left, content on the right.

    The topic list already shows which topic is "current" via its own native selection
    highlight the moment one is picked -- there's no separate scroll-spy to add on top of
    that, since (unlike the website's single continuously-scrolled page) each topic here
    is its own freshly-loaded document in the viewer, not one long page you scroll through
    across topics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ModbusLens Documentation")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)

        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search this topic...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        # Plain Enter falls through to this and searches forward; Shift+Enter is caught by
        # the eventFilter below (consumed there, so it never also reaches returnPressed).
        self.search_input.returnPressed.connect(lambda: self._do_search(backward=False))
        self.search_input.installEventFilter(self)
        search_row.addWidget(self.search_input, 1)

        self.search_count_label = QLabel("")
        self.search_count_label.setMinimumWidth(36)
        self.search_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        search_row.addWidget(self.search_count_label)

        self.search_prev_btn = QPushButton("▲")
        self.search_prev_btn.setToolTip("Previous match (Shift+Enter)")
        self.search_prev_btn.setFixedWidth(28)
        self.search_prev_btn.setEnabled(False)
        self.search_prev_btn.clicked.connect(lambda: self._do_search(backward=True))
        search_row.addWidget(self.search_prev_btn)

        self.search_next_btn = QPushButton("▼")
        self.search_next_btn.setToolTip("Next match (Enter)")
        self.search_next_btn.setFixedWidth(28)
        self.search_next_btn.setEnabled(False)
        self.search_next_btn.clicked.connect(lambda: self._do_search(backward=False))
        search_row.addWidget(self.search_next_btn)

        sidebar_layout.addLayout(search_row)

        self.full_search_checkbox = QCheckBox("Full search")
        self.full_search_checkbox.setToolTip("Search every topic instead of just the one currently shown")
        self.full_search_checkbox.toggled.connect(self._on_full_search_toggled)
        sidebar_layout.addWidget(self.full_search_checkbox)

        self.topic_list = QListWidget()
        for title, _ in DOCS:
            self.topic_list.addItem(title)
        self.topic_list.currentRowChanged.connect(self._show_topic)
        sidebar_layout.addWidget(self.topic_list, 1)

        sidebar.setMaximumWidth(240)
        splitter.addWidget(sidebar)

        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        splitter.addWidget(self.viewer)

        splitter.setSizes([220, 680])
        layout.addWidget(splitter, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        main_window = self.parent()
        if hasattr(main_window, "_get_input_style"):
            self.search_input.setStyleSheet(main_window._get_input_style())
        if hasattr(main_window, "_get_button_style"):
            btn_style = main_window._get_button_style(small=True)
            self.search_prev_btn.setStyleSheet(btn_style)
            self.search_next_btn.setStyleSheet(btn_style)

        # Full-search state: a flat list of (topic_index, start_pos_in_that_topic's_plain_text)
        # tuples covering every topic, plus where we currently are in it. Kept separate from the
        # single-topic path (which just drives QTextBrowser.find() directly) since jumping to a
        # match here may also need to switch which topic is loaded.
        self._full_search_matches = []
        self._full_search_index = -1
        self._navigating_full_search = False  # sidesteps _show_topic's own re-sync while
                                               # a full-search jump is the thing switching topics

        self.topic_list.setCurrentRow(0)

    def eventFilter(self, obj, event):
        """Shift+Enter for the previous match -- plain QLineEdit only exposes a single
        returnPressed signal with no modifier info, so the modifier-aware case is caught
        here instead, before it reaches (and would otherwise separately trigger)
        returnPressed's own forward-search handler."""
        if obj is self.search_input and event.type() == QEvent.Type.KeyPress:
            if (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self._do_search(backward=True)
                return True
        return super().eventFilter(obj, event)

    def _show_topic(self, row):
        if 0 <= row < len(DOCS):
            self.viewer.setHtml(DOCS[row][1])
            if self._navigating_full_search:
                # A full-search jump is what triggered this topic switch -- it'll position
                # the selection/scroll itself right after, so don't let the single-topic
                # re-sync below fight it.
                return
            if self.full_search_checkbox.isChecked():
                # Topic was changed by clicking the list directly while in full-search mode
                # -- leave the existing whole-search count/results as they are; only a
                # search-text edit or Next/Previous should recompute them in this mode.
                return
            # A search typed before switching topics stays in the box (searching the same
            # term in a different topic is a normal thing to want) -- just re-sync the
            # count/highlight against whatever's now loaded instead of clearing it.
            self._on_search_text_changed(self.search_input.text())

    def _on_full_search_toggled(self, checked):
        self.search_input.setPlaceholderText(
            "Search every topic..." if checked else "Search this topic..."
        )
        # Re-run whatever's currently typed under the new mode, so toggling the checkbox with
        # an active query switches scope immediately instead of waiting for the next keystroke.
        self._on_search_text_changed(self.search_input.text())

    def _on_search_text_changed(self, text):
        if self.full_search_checkbox.isChecked():
            self._rebuild_full_search_matches(text)
            if self._full_search_matches:
                self._go_to_full_search_match(0)
            else:
                self._set_search_status(0, 0)
            return

        cursor = self.viewer.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.viewer.setTextCursor(cursor)
        if text:
            self._do_search(backward=False)
        else:
            self._set_search_status(0, 0)

    def _do_search(self, backward):
        """Uses QTextBrowser's own find() -- native text-cursor selection, so a match is
        highlighted with the app's normal selection color (already theme-correct via the
        global QPalette, no custom highlight styling needed) and scrolled into view for
        free. find() doesn't wrap around on its own, so a failed search retries once from
        the opposite end before actually reporting no match -- Enter/Next past the last
        match cycles back to the first, matching how the website's version behaves."""
        query = self.search_input.text()
        if not query:
            return

        if self.full_search_checkbox.isChecked():
            if not self._full_search_matches:
                return
            step = -1 if backward else 1
            self._go_to_full_search_match(self._full_search_index + step)
            return

        flags = QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0)
        found = self.viewer.find(query, flags)
        if not found:
            cursor = self.viewer.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self.viewer.setTextCursor(cursor)
            found = self.viewer.find(query, flags)
        self._update_search_count(query, found)

    def _update_search_count(self, query, found):
        plain = self.viewer.toPlainText()
        total = plain.lower().count(query.lower()) if query else 0
        if not found or total == 0:
            self._set_search_status(0, 0)
            return
        cursor = self.viewer.textCursor()
        current_index = plain[: cursor.selectionStart()].lower().count(query.lower()) + 1
        self._set_search_status(current_index, total)

    def _rebuild_full_search_matches(self, query):
        """Every occurrence of query across every topic, as (topic_index, start_pos) pairs --
        start_pos is a character offset into that topic's own plain text, recomputed fresh
        here via a throwaway QTextDocument rather than by actually loading each topic into
        the visible viewer just to count. Rebuilt on every query change; 16 topics/~60KB of
        text is cheap enough to rescan on every keystroke without a debounce."""
        self._full_search_matches = []
        self._full_search_index = -1
        if not query:
            return
        lower_query = query.lower()
        for topic_index, (_title, html) in enumerate(DOCS):
            scratch = QTextDocument()
            scratch.setHtml(html)
            lower_plain = scratch.toPlainText().lower()
            start = 0
            while True:
                pos = lower_plain.find(lower_query, start)
                if pos == -1:
                    break
                self._full_search_matches.append((topic_index, pos))
                start = pos + len(lower_query)

    def _go_to_full_search_match(self, index):
        if not self._full_search_matches:
            return
        self._full_search_index = index % len(self._full_search_matches)
        topic_index, start_pos = self._full_search_matches[self._full_search_index]
        query_len = len(self.search_input.text())

        if self.topic_list.currentRow() != topic_index:
            self._navigating_full_search = True
            self.topic_list.setCurrentRow(topic_index)
            self._navigating_full_search = False

        cursor = QTextCursor(self.viewer.document())
        cursor.setPosition(start_pos)
        cursor.setPosition(start_pos + query_len, QTextCursor.MoveMode.KeepAnchor)
        self.viewer.setTextCursor(cursor)
        self.viewer.ensureCursorVisible()
        self._set_search_status(self._full_search_index + 1, len(self._full_search_matches))

    def _set_search_status(self, current, total):
        self.search_count_label.setText(f"{current}/{total}" if total else ("0/0" if self.search_input.text() else ""))
        has_matches = total > 0
        self.search_prev_btn.setEnabled(has_matches)
        self.search_next_btn.setEnabled(has_matches)
