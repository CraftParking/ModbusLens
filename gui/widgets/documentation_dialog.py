from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTextBrowser, QPushButton, QSplitter

DOCS = [
    ("Getting Started", """
<h2>Getting Started</h2>
<p>ModbusLens is a Modbus TCP and RTU client built for testing, commissioning, and troubleshooting
industrial devices - PLCs, drives, meters, and gateways. It combines the things you'd normally
reach for several separate tools to do: reading and writing coils/registers, monitoring named
tags, graphing values over time, simulating a slave device, running repeatable test scripts, and
scanning a network for Modbus devices.</p>

<h3>What you need before you start</h3>
<ul>
<li>The target device's <b>Modbus TCP</b> address/port, or its <b>Modbus RTU</b> serial settings
(COM port, baud rate, parity) if it's a serial device.</li>
<li>The device's <b>Unit ID</b> (also called Slave ID or Station Address) - commonly 1, but check
the device's manual or DIP switches/configuration.</li>
<li>Ideally, the device's register map - which addresses hold which values, and in what format.
If you don't have one, the <b>Raw (Hex)</b> column and the Address Table are good tools for
reverse-engineering it safely (read-only first).</li>
</ul>

<h3>Basic workflow</h3>
<ol>
<li>Click <b>Settings</b> (top right) and enter the target device's IP address, port (usually 502),
and Unit ID - or switch to Modbus RTU and enter the serial parameters instead.</li>
<li>Click <b>Connect</b>. The status indicator on the left turns green when connected.</li>
<li>Use the tabs below to work with the device: <b>Address Table</b> for quick reads/writes,
<b>Tags</b> for named live monitoring, <b>Raw Data</b> for the untouched bytes behind every
transaction, <b>Trend</b> for graphing, <b>Server</b> to act as a slave device yourself, and
<b>Script</b> to automate a test sequence.</li>
</ol>

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
own connection, tabs, and Server tab. See <b>Multiple Windows</b> for details.</li>
<li><b>New Session</b> - disconnects if connected, stops monitoring, and clears the current
window's logs and monitoring results. Doesn't close the window or lose your Tags/script - just
resets the live state.</li>
<li><b>Save Session</b> / <b>Load Session</b> - not implemented yet; currently show a placeholder
message. Use <b>Export/Import CSV</b> on the Tags tab to save/reload a tag list in the meantime.</li>
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
<li><b>Connection Settings</b> - opens the same dialog as the <b>Settings</b> button on the
connection bar: choose Modbus TCP or Serial (RTU/ASCII) and enter the target address/port or COM
port parameters. See <b>Connecting to a Device</b>.</li>
<li><b>Connection Profiles</b> / <b>Data Templates</b> - not implemented yet; currently show a
placeholder message. Reserved for saving/reusing connection setups and register layouts in a
future release.</li>
<li><b>IP Configuration</b> - a quick, read-only ipconfig-style view of this machine's own network
adapters (name, IP, subnet). Useful for figuring out which subnet to scan or connect on before
you know a device's address.</li>
</ol>

<h3>Diagnostics menu</h3>
<ol>
<li><b>Network Discovery &amp; Diagnostics</b> - opens the network scanning dialog (ARP-based
device discovery plus Modbus detection). See <b>Troubleshooting &gt; Network Discovery</b>.</li>
<li><b>Serial Discovery</b> - opens a dialog that sweeps common baud rate/parity/stop-bit/Unit ID
combinations against a COM port to find which one a serial device actually speaks. See the
<b>Scanner</b> topic.</li>
<li><b>System Logs</b> - opens a dialog with the full, scrollable System Logs history (the same
color-coded write/connect/error log shown live in the app). Handy when you need to scroll back
further than fits on screen.</li>
<li><b>Clear All Logs</b> - clears the System Logs and the Raw Data tab's transaction history.
This can't be undone.</li>
</ol>

<h3>Help menu</h3>
<ol>
<li><b>Documentation</b> - this dialog.</li>
<li><b>About</b> - version number, a feature list, the Support link, and an <b>Updates</b> tab
that checks GitHub Releases for a newer version.</li>
</ol>

<h3>Connection bar (below the menu bar)</h3>
<p>Not a menu, but always visible and worth listing here: the status indicator (left), current
target address, and on the right, <b>Settings</b> (same as Tools &gt; Connection Settings),
<b>Connect</b>, and <b>Disconnect</b>.</p>
"""),

    ("Connecting to a Device", """
<h2>Connecting to a Device</h2>
<p>Open <b>Settings</b> in the top-right of the connection bar. Choose <b>Modbus TCP</b> or
<b>Modbus Serial (RTU/ASCII)</b> at the top of the dialog, then fill in the fields for that mode.</p>

<h3>Modbus TCP</h3>
<ul>
<li><b>IP Address</b> - the target device, PLC, or gateway's Modbus TCP address.</li>
<li><b>Port</b> - usually 502 for standard Modbus TCP.</li>
<li><b>Network Interface</b> - a convenience dropdown that fills in a local interface's IP,
useful when testing against yourself (e.g. against ModbusLens's own Server tab). If you need the
full picture - every adapter's IP and subnet mask - <b>Tools &gt; IP Configuration</b> shows all
of them at once, like running <code>ipconfig</code>.</li>
</ul>

<h3>Modbus Serial (RTU/ASCII)</h3>
<ul>
<li><b>Serial Port</b> - the COM port the device is connected to (via USB-RS485/RS232 adapter or
a native serial port).</li>
<li><b>Baud Rate, Parity, Stop Bits, Byte Size</b> - must match the device's configuration exactly,
or communication will fail or return garbage.</li>
<li><b>Framing</b> - <b>RTU</b> (binary, the default and far more common) or <b>ASCII</b>
(hex-encoded, human-readable on the wire, framed with a leading <code>:</code> and trailing
CR/LF). The two are incompatible - a device speaking one will not respond correctly to the other,
so this has to match the device exactly, the same as baud rate and parity.</li>
</ul>

<h3>Both modes</h3>
<ul>
<li><b>Unit ID</b> - the Modbus slave/unit identifier (1 is common; some TCP gateways ignore it,
but RTU devices almost always require the correct one).</li>
<li><b>Recent Connections</b> - quickly reconnect to somewhere you've connected before.</li>
</ul>

<p>Click <b>Connect</b> to open the connection, <b>Disconnect</b> to close it. The status
indicator on the left shows Connected (green), Connecting (orange), or Disconnected/Error. If the
connection fails, ModbusLens shows a dialog with the specific error and a checklist of likely
causes - see <b>Troubleshooting</b> for the details behind that checklist.</p>

<h3>Finding your own IP (IP Configuration)</h3>
<p><b>Tools &gt; IP Configuration</b> opens a small window listing every network adapter on this
machine - the same information <code>ipconfig</code> gives you at a command prompt, without
leaving the app. Each row shows the adapter name, its IPv4 address, subnet mask, and whether the
adapter is Up or Down.</p>
<p>This is mainly useful for two things: figuring out which of your adapters is on the same
network/subnet as the target device before you connect, and getting the right address to hand out
when <i>you're</i> the target - e.g. telling a colleague's PLC or SCADA system which of your IPs to
connect to when testing against ModbusLens's own Server tab. The Network Interface dropdown in
Settings (above) covers the common case of "fill in my own IP"; IP Configuration is for when you
need to see every adapter and its subnet mask at once, such as confirming two adapters aren't
sharing a conflicting subnet.</p>

<h3>Auto-reconnect</h3>
<p>Once connected, ModbusLens watches the connection in the background. If it drops - a cable
pulled, a device rebooting, a network blip - the status indicator switches to
<b>Reconnecting... (attempt N)</b> and it keeps retrying automatically, waiting a little longer
between each attempt (2s, 4s, 8s... capped at 30s) so it doesn't hammer a device that's still
coming back up. If Tags monitoring was running and got stopped because every tag failed at once
(read as: the connection itself was the problem, not one bad tag), it resumes automatically the
moment the connection recovers - you don't have to click Start Monitoring again. This only applies
to an unexpected drop; clicking <b>Disconnect</b> yourself never triggers a reconnect attempt.</p>

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

<h3>Creating a table</h3>
<ol>
<li>Pick a <b>Function</b> (Read Coils, Read Holding Registers, Write Single Register, etc.).</li>
<li>Set <b>Start Address</b> and <b>Count</b>.</li>
<li>Click <b>Create Table</b>.</li>
</ol>
<p>Each row shows the Modbus reference address, the current value, and the same value in hex.
For a Write function, double-click the Value cell to edit and send it immediately (coil rows
show a checkbox instead).</p>

<h3>Write bounds</h3>
<p>For Write Single/Multiple Register functions, two extra columns appear: <b>Min</b> and
<b>Max</b>. Setting both on a row rejects any write to that register outside the range - a typo
like an extra zero gets refused instead of sent to the field device. This is enforced on the
connection itself, so it also protects writes to that same address from the Tags tab or a
Script, not just from this table. Leave both blank for no limit. A rejected write shows up as a
failed write with a message like <i>"Write rejected: value 10000 at address 99 is outside the
configured write bound [0, 100]"</i>.</p>

<h3>Live Monitoring</h3>
<p>For Read functions, check <b>Enable Live Monitoring</b> and set an interval to keep polling
the whole range automatically. Starting this auto-stops Tags monitoring, and vice versa, so the
two don't compete for the connection.</p>

<h3>Status Log</h3>
<p>The panel on the right shows what the table is doing - reads, writes, and any errors,
each with a timestamp and color-coded so the right lines stand out: writes in blue, connection
events in green, errors in red, everything else in the default color. This is the first place
to look when a write doesn't seem to take effect. The same coloring applies to System Logs and
the Script console.</p>
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
tags only).</li>
<li><b>Comment</b> and <b>Timestamp</b>.</li>
</ul>

<h3>Naming a tag</h3>
<p>A tag name can only use letters, numbers, and underscores - no spaces or other symbols, and it
can't start with a digit. Script language keywords (WRITE, READ, HR, COIL, and so on) and common
reserved words are also blocked. Entering an invalid name shows a warning and clears the field
rather than letting it stick, since a tag's name is also how it's referenced by name in a Script
(see the Scripting topic) and in Trend's Add Pen picker.</p>

<h3>Data formats</h3>
<p><b>Bool</b>, <b>U16/S16</b>, <b>U32/S32/F32</b> (plus <code>_SWAP</code> variants for the
opposite word order), and <b>Hex</b>. BOOL on a Coil/Discrete Input is a simple flag; BOOL on a
Holding/Input Register instead shows the full 16-bit pattern (e.g. <code>0000000000000101</code>)
so you can read individual status/alarm bits out of a status word. 32-bit formats (U32/S32/F32)
need an even <b>Count</b> (2, 4, ...) since they span two registers per value.</p>

<h3>Engineering-unit scaling</h3>
<p>Check the <b>Scale</b> box on a row to open a small popup asking for <b>Raw Min/Max</b> and
<b>Scaled Min/Max</b> - a linear transform from whatever the device actually sends to a
meaningful engineering unit (e.g. raw ADC counts 0-4095 mapped to 0-100 PSI). The result appears
in the <b>Engineering Value</b> column alongside the normal Read Value, live as the tag is
polled. Choose <b>Real</b> or <b>Integer</b> for how the scaled result is displayed. Unchecking
<b>Scale</b> (or Cancelling the popup) turns scaling back off for that row.</p>

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
the list from updating. Monitoring only auto-stops if <i>every</i> tag fails on the same poll,
which is treated as a lost connection rather than a configuration mistake on one row.</p>

<h3>Safety interlock</h3>
<p>Writing is paused for the moment a value is being sent, then Read polling resumes automatically -
this stops a write and a read from overlapping on the same connection.</p>
"""),

    ("Raw Data", """
<h2>Raw Data</h2>
<p>One row per Modbus transaction - the untouched data behind every read and write, independent
of how a Tag or Address Table row happens to decode it. Useful when a decoded value looks wrong
and you want to see exactly what came back before ModbusLens interpreted it as U16, F32, or
anything else, and for spotting a device that's responding but slow.</p>

<h3>Columns</h3>
<ul>
<li><b>Time</b> and <b>Operation</b> - when it happened and what it was (which Tag, Address
Table function, or Script command triggered it).</li>
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
<li><b>Latency (ms)</b> - how long that specific request took round-trip. A device that's
technically working but degrading usually shows up here first, before it starts failing outright.</li>
</ul>

<h3>Filter</h3>
<p>The text box filters by whatever's in the Operation or Value columns - a tag name (e.g.
<code>pump</code>), an address, or a specific value. The dropdown next to it narrows to just
<b>Success</b> or <b>Failed</b> rows. Both apply live as you type/select, and to new rows as they
arrive - useful for watching one specific tag during a busy poll, or isolating every failure to
see if they cluster around one address.</p>

<h3>Show Statistics</h3>
<p>Opens a summary of the current connection's traffic: total requests, successful vs. failed
counts, exception responses, and average/min/max response times across everything logged so far
(not just what's currently visible in the table, since old rows fall off after 1000). Useful for
confirming a "slow" feeling is real and quantifying it.</p>

<h3>Clear Data</h3>
<p>Empties the table without affecting the connection or any other tab. Do this before
reproducing an intermittent issue so the table only contains the run you care about.</p>
"""),

    ("Trend", """
<h2>Trend</h2>
<p>Graphs up to 20 pens over time, either following the live clock or reviewing history. Useful
for spotting slow drift, verifying a control loop is actually responding, or capturing a transient
you can't watch a numeric table fast enough to catch.</p>

<h3>Pens</h3>
<p><b>Add Pen</b> opens a grid of 20 slots (SCADA-style) - enable the ones you want, click the
&#8942; button in the Name column to pick a tag from a popup list, and set a color. A pen's type,
address, count, and format all come from whichever tag you pick, not from separate fields here.
Only tags on Holding or Input Registers with a numeric format show up in that list - Coils,
Discrete Inputs, and the Bool format are left out, since a trend line is meant for continuously
varying values rather than on/off state. If you need to watch a digital point over time, add it
as a Tag and check its Read Value column instead. If none exist yet, the popup's tag list is just
empty - click its <b>Add Tag...</b> button to jump straight to the Tags tab and create one (this
closes the Trend Pens grid, since adding a tag needs the Tags tab visible). If the tag has
engineering-unit scaling enabled (see Tags Monitoring), the pen plots that scaled value instead
of the raw one - turning scaling on or off for the tag changes what the pen shows immediately,
no need to re-pick it.</p>

<h3>Navigating</h3>
<p>If the view is sitting at the live edge (showing right up to "now"), it keeps following as new
data arrives, the same as before. As soon as you scroll or zoom away to look at something earlier,
it stops following and stays exactly where you left it, however long the trend keeps running -
new data doesn't interrupt you. Scroll back to the live edge and it picks up following again on
its own; there's no separate mode to switch. Everything plotted is just what's been collected in
the current session - there's no separate historical database to switch into.</p>
<p>The scrollbar just below the graph pans through everything collected so far, including while
the trend is actively running - drag it right to catch up to the newest data, or left to look back.
<b>Time Window</b> picks how much time is visible at once. <b>Zoom In/Out</b> halves or doubles
that span around wherever you're currently looking. <b>From</b>/<b>To</b> plus <b>Go</b> jumps
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
<p><b>Log to CSV</b> appends a timestamped row per pen on every poll tick. <b>Print</b> saves the
current graph view as a PNG image or a PDF document - useful for attaching evidence of a fault
condition to a service report.</p>

<h3>Detach</h3>
<p><b>Detach</b> pops the whole Trend view out into its own resizable, maximizable window that
stays on top of the main window, so you can watch it while working in another tab (Tags,
Script, ...) instead of switching back and forth. The Trend tab itself shows a red X while
detached, as a reminder that the real view has moved. The floating window's <b>Hide Stats</b>
button collapses the Min/Max/Average table to give the graph more room - this button only
appears while detached, since the docked tab isn't usually short on space. Click <b>Fixed</b> at
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
<li>Set <b>Server Address</b> (usually <code>0.0.0.0</code> to accept connections on any
network interface), <b>Port</b>, and <b>Unit ID</b>.</li>
<li>Click <b>Start Server</b>.</li>
</ol>
<p>Once running, pick a <b>Data Space</b> (Coils, Discrete Inputs, Holding Registers, or Input
Registers), set a Start Address/Count, and click <b>Load</b> to view that range.</p>

<h3>Editing values</h3>
<p>Double-click a Value cell to set it directly, as if you were the field device generating
that reading. Any Modbus master that connects to this server sees the same value. Coils and
Holding Registers are also writable by a remote master; Discrete Inputs and Input Registers are
read-only from the network side (as in real Modbus), but you can still set them yourself from
the GUI to simulate a live sensor.</p>

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
<p>Open a second ModbusLens window (<b>File &gt; New Connection Window</b>), connect it to
<code>127.0.0.1</code> (or your machine's LAN IP) on the port the server is listening on, and you
have a complete self-contained loop for testing Tags, Trend, or a Script with zero risk to real
equipment.</p>
"""),

    ("Scripting", """
<h2>Scripting</h2>
<p>The Script tab runs small test sequences against the connected device using a purpose-built
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
<tr><td><code>LET &lt;name&gt; = &lt;expr&gt;</code></td><td>Assign a variable.</td></tr>
<tr><td><code>LOG &lt;expr&gt;</code></td><td>Print text/numbers to the console.</td></tr>
<tr><td><code>WAIT &lt;expr, ms&gt;</code></td><td>Pause without freezing the UI.</td></tr>
<tr><td><code>REPEAT &lt;expr&gt; ... END</code></td><td>Loop a block of commands a fixed number of times.</td></tr>
<tr><td><code>REPEAT UNTIL &lt;expr&gt; &lt;op&gt; &lt;expr&gt; ... END</code></td>
<td>Loop until a condition becomes true, checked before each pass.</td></tr>
<tr><td><code>IF &lt;expr&gt; &lt;op&gt; &lt;expr&gt; THEN &lt;command&gt;</code></td>
<td>Run one command conditionally. op is <code>== != &gt; &lt; &gt;= &lt;=</code>.</td></tr>
</table>

<h3>Expressions</h3>
<p>An expression can mix numbers, <code>"strings"</code>, variables, parentheses, and
<code>+ - * /</code>. Writing a bare <code>HR 0</code> inside an expression reads that register
inline (shorthand for <code>READ HR 0</code>); a bare tag name works the same way (e.g.
<code>LET x = Boiler_Temp + 1</code> reads the Boiler_Temp tag's current value). A tag name is
only tried if the name isn't already a variable you've assigned with <code>LET</code> - a LET
variable always takes priority over a tag of the same name. <code>+</code> also concatenates text
with numbers, so <code>LOG "value is " + x</code> works as expected. Types: COIL, DI (Discrete
Input), HR (Holding Register), IR (Input Register).</p>

<h3>Compile and Run</h3>
<p><b>Compile</b> checks the script's syntax without touching the device - use it to catch typos
before running anything. <b>Run</b> executes the script step by step; because it can write to a
live device, Run shows a one-time-per-preference warning first (with a "don't remind me again"
option) reminding you to be careful on in-service equipment. <b>Stop</b> halts a running script
at any point.</p>

<h3>Target: Client vs Server</h3>
<p>The <b>Target</b> dropdown picks whether the script talks to your live connection
(<b>Client-target</b>) or to ModbusLens's own Server tab (<b>Server-target</b>), so you can dry-run
a sequence safely with no real device attached - start a server, switch the script to
Server-target, and run it exactly as it would run against the real thing.</p>

<h3>Variables panel</h3>
<p>The panel on the right lists every variable your script assigns with <code>LET</code>, updating
live as the script runs - no need to sprinkle <code>LOG</code> lines everywhere just to see what a
variable currently holds. It populates as soon as you <b>Compile</b> (values blank until the script
actually runs), keeps updating on every step while running, and holds the last values after the
script finishes or is stopped, so you can still read them afterward.</p>

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
<li><b>CPU usage indicator</b> - shows live system CPU load, useful for spotting a runaway loop
that's spinning the interpreter faster than intended.</li>
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
retyping it. Reads a tag name exactly like <code>HR 0</code>/<code>COIL 0</code> would, but stays
correct if that tag's address ever changes, since the script only cares about the name.</p>

<h3>Limits</h3>
<p>To keep a typo from hanging the app or running forever: a loop with no WAIT still hands
control back to the interface regularly instead of freezing it, and REPEAT counts, WAIT
durations, expression nesting, and total script length are all capped with a clear error if
exceeded. <code>REPEAT UNTIL</code> shares that same iteration cap - if the condition never
becomes true, it stops with an error instead of looping forever. Separately, consecutive steps are
never scheduled less than 20ms apart even if a script asks for <code>WAIT 0</code> or omits WAIT
entirely, so a typo can't flood the device or network. See <b>Troubleshooting</b> for what the
common error messages mean.</p>
"""),

    ("Scanner", """
<h2>Scanner</h2>
<p>Auto-discovers which addresses respond on the connected device - useful when you don't have
a register map yet. Works the same way regardless of whether the current connection is TCP or
serial, since it just reuses whatever's already connected.</p>

<p>Pick a <b>Function</b> (Coils/Discrete Inputs/Holding/Input Registers) and a <b>Start</b>/
<b>End</b> address, then <b>Start Scan</b>. Rather than checking one address at a time, it
probes the largest block the function allows first - a clean read means every address in that
block responds. If a block doesn't fully respond, it's split in half and each half is probed
again, narrowing down until it knows exactly which individual addresses do and don't respond.
This is far fewer requests than a naive one-by-one sweep whenever most of a range is
contiguous, which is the common case for a real device's register map.</p>
<p>The <b>Summary</b> line lists the responding addresses as merged ranges (e.g.
<code>0-15, 20, 45-99</code>). A device that returns <b>Illegal Function</b> for the whole
range stops the scan immediately with a clear message, since every address would fail the same
way - try a different Function instead. A genuine timeout or dropped connection also stops the
scan, since that means the device itself stopped responding, not that a particular address is
invalid.</p>
<p>Reuses the same connection as every other tab, rather than opening a second one. Starting a
scan automatically pauses Tags monitoring and Address Table Live Monitoring if either is
running, the same way those two already pause each other, so nothing else polls the connection
while a scan is in progress.</p>
<p>A shorter <b>Probe timeout</b> makes a scan faster but can misreport a slow-but-valid address
as not-responding, especially over a serial connection where every probe is one real bus
round-trip. If a scan seems to be missing an address you know exists, try a longer timeout.</p>
<p>Don't know the serial connection parameters (baud rate, parity, stop bits) for a device in
the first place? See <b>Serial Discovery</b>.</p>
"""),

    ("Serial Discovery", """
<h2>Serial Discovery</h2>
<p><b>Diagnostics &gt; Serial Discovery</b> sweeps common baud rate/parity/stop-bit/Unit ID
combinations against a COM port to find which one a serial device actually speaks, for when its
settings aren't documented. There's also a <b>Scan for Connection Parameters...</b> button in
<b>Tools &gt; Connection Settings</b>'s Serial section that closes that dialog and opens this
one directly, with the COM port already filled in.</p>
<p>Pick the <b>COM Port</b> and <b>Framing</b> (RTU/ASCII), a <b>Start</b>/<b>End Unit ID</b>
range to also try, then <b>Start Scan</b>. It tries every combination of 8 common baud rates,
3 parity settings, 2 stop-bit settings, and each Unit ID in the range - byte size is fixed at
8, the near-universal default - opening a short-lived connection for each combination and
sending one Holding Register read. Any reply, including a Modbus exception response, counts as
a match, since that still proves the framing decoded correctly; a garbled response from a
mismatched baud rate or parity won't parse as a valid Modbus frame at all.</p>
<p>This doesn't reuse the app's shared connection - it opens its own for each combination,
since testing a physical serial setting means actually reopening the port with it. That also
means the port needs to be free: disconnect ModbusLens first if it's the one connected to this
port, and close any other program (Modbus Poll, a terminal, another ModbusLens window) that
might have it open. If the port can't be opened at all, the scan stops immediately with that
message rather than repeating the same failure for every remaining combination.</p>
<p>Keep the Unit ID range narrow (it defaults to just 1) unless you actually need it wider -
each additional Unit ID multiplies the total combination count by 48.</p>
"""),

    ("Multiple Windows", """
<h2>Multiple Windows</h2>
<p><b>File &gt; New Connection Window</b> opens a second, fully independent ModbusLens window -
its own connection, Address Table, Tags, Raw Data, Trend, Server, Script, and Scanner tab. Use
this to talk to several devices at the same time side by side, or to run a Client against your
own Server tab from a second window (see Server Mode).</p>
<p>The one exception is Server mode: only one Server tab can be actively running at a time,
across all open windows (see the Server Mode topic for why). Everything else is fully
independent per window.</p>
"""),

    ("Troubleshooting", """
<h2>Troubleshooting</h2>
<p>Symptom-first reference for the problems you're most likely to run into. If something here
doesn't cover your case, the Status Log (Address Table) or the console (Script tab) usually has a
more specific message worth reading closely.</p>

<h3>Can't connect over TCP</h3>
<p>The connection dialog itself lists a checklist when a TCP connection fails; the reasoning
behind each item:</p>
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
</ul>

<h3>Values look exactly one address off</h3>
<p>This is almost always the 0-based vs 1-based addressing setting. Toggle the <b>0-Based
Addressing</b> checkbox on the Address Table or Tags tab and compare - see the Connecting topic
for the full explanation.</p>

<h3>A 32-bit value (U32/S32/F32) looks like nonsense</h3>
<p>Try the <code>_SWAP</code> variant of the same format. Different vendors order the high and low
register of a 32-bit value differently, and there's no reliable way to detect which one a device
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
their <code>_SWAP</code> variants) need an even count.</li>
<li>Check the address is actually valid on the device - some devices have gaps in their register
map that return an exception rather than a value.</li>
<li>One failing tag no longer stops the rest of the list from updating, so if only one row shows
ERROR while the others keep ticking, the problem is specific to that tag's configuration, not the
connection.</li>
<li>If <i>every</i> tag shows ERROR at once, monitoring will auto-stop after a few consecutive
failed polls - that's treated as a lost connection rather than a tag problem. ModbusLens will
retry the connection itself automatically (see the next entry); you shouldn't need to do
anything unless it can't recover.</li>
</ul>

<h3>Status shows "Reconnecting..." and it's taking a while</h3>
<p>This is expected - once connected, ModbusLens watches the connection and auto-retries with
increasing delays (2s, 4s, 8s... capped at 30s) if it drops, rather than requiring a manual
reconnect. If Tags monitoring was running and stopped because every tag failed at once, it
resumes automatically the moment the connection recovers. If it's still stuck reconnecting after
a while, the underlying cause is the same as an initial connection failure - work through the
TCP or Serial checklist above (device power, cabling, IP/port, Unit ID). Clicking
<b>Disconnect</b> stops the retry loop entirely, if you want to give up on it.</p>

<h3>"Duplicate Address" or "Overlapping Ranges" warning</h3>
<p>Two tags of the same Modbus type (e.g. two Holding Register tags) are pointing at the same or
overlapping addresses. This is usually a copy-paste mistake when building a large tag list -
check the Address column against your register map.</p>

<h3>"Server Already Running"</h3>
<p>Only one Server tab can be active at a time, across every open ModbusLens window, because the
underlying Modbus library only supports one active server per process. Stop the other one first.</p>

<h3>A script won't Compile</h3>
<p>Compile errors describe exactly what's wrong and where, for example:</p>
<ul>
<li><code>REPEAT without matching END</code> / <code>END without matching REPEAT</code> - a
REPEAT block wasn't closed, or an extra END has nothing to close.</li>
<li><code>unrecognized command: ...</code> - a typo in a command keyword, or a command used
outside where it's valid (e.g. REPEAT/IF nested somewhere they're not allowed).</li>
<li><code>invalid address: ...</code> / <code>address ... out of range (0-65535)</code> - the
address after a type (COIL/DI/HR/IR) isn't a valid number in range.</li>
</ul>

<h3>A script won't Run (compiles fine, fails immediately)</h3>
<ul>
<li><code>not connected to a Modbus server</code> - the script is set to Client-target but there's
no active connection. Connect first, or switch Target to Server-target to test against the
Server tab instead.</li>
<li><code>Server is not running - start it on the Server tab first</code> - the opposite case:
Target is Server-target but the Server tab hasn't been started.</li>
<li><code>... cannot be written to a client connection</code> - a WRITE targeted a
Discrete Input or Input Register, which are read-only by the Modbus spec.</li>
<li><code>read failed for HR 12</code> (or similar) - the read inside an expression failed against
the live device; check the address is valid, the same way you would for a Tags tab ERROR.</li>
<li><code>REPEAT UNTIL exceeded the 1000000-iteration limit without the condition becoming true</code>
- the condition never became true; double-check the address/comparison, or that the device is
actually changing the value you're waiting on.</li>
</ul>

<h3>Network Discovery isn't finding a device, or feels slow</h3>
<p><b>Diagnostics &gt; Network Discovery &amp; Diagnostics</b> scans the local network and checks
which devices respond to Modbus - useful when you know a PLC is on the subnet but don't know its
current IP. It combines a few techniques:</p>
<ul>
<li><b>ARP-based discovery</b> - finds devices on the local subnet without needing to know their
IP addresses in advance. This is the fast path, and it's what requires Npcap (below).</li>
<li><b>Modbus detection</b> - probes discovered devices to see which ones answer Modbus requests,
so you're not guessing which IP is the PLC.</li>
<li><b>Device filtering</b> - "Show only Modbus devices" hides everything else from the list.</li>
</ul>
<p>Selecting a discovered device fills in its IP/port for you in Connection Settings.</p>
<p>Advanced discovery (the fast ARP path) requires <b>Npcap</b>. Without it, ModbusLens falls back
to a ping-based scan, which is slower and misses devices on networks that block ICMP - if scanning
feels slow or misses a device you know is there, this is almost always why. Install Npcap with
<i>WinPcap compatible mode</i> enabled during setup, then restart ModbusLens - see the README's
Notes section for the download link and exact install options.</p>

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
<li>Use <b>Server Mode</b> as a local practice target: start a server in one window, connect to
it from another (or a second ModbusLens instance via a New Connection Window), and try things out
- including a full Script or Tag list - before pointing at real equipment.</li>
<li>For anything that writes automatically and repeatedly (a Script, or a Tag in Write mode with
monitoring active), consider setting a write bound (Min/Max) on the target register first - see
the Address Table topic. It costs nothing when everything is working, and catches a typo the
moment it would otherwise reach the device.</li>
<li>If something isn't behaving as expected - wrong values, failed writes, a script that won't
run - check <b>Troubleshooting</b> before assuming it's a device problem; most of the common
causes are configuration mismatches on this end (addressing mode, word order, Unit ID) rather
than a fault on the device.</li>
</ul>
"""),
]


class DocumentationDialog(QDialog):
    """A simple two-pane Help viewer: topic list on the left, content on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ModbusLens Documentation")
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        self.topic_list = QListWidget()
        for title, _ in DOCS:
            self.topic_list.addItem(title)
        self.topic_list.setMaximumWidth(220)
        self.topic_list.currentRowChanged.connect(self._show_topic)
        splitter.addWidget(self.topic_list)

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

        self.topic_list.setCurrentRow(0)

    def _show_topic(self, row):
        if 0 <= row < len(DOCS):
            self.viewer.setHtml(DOCS[row][1])
