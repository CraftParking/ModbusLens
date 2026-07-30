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
<ul>
<li><b>File</b> - open another independent connection window, start a new session, save/load a
session, export data, exit.</li>
<li><b>View</b> - display options (the interface is currently fixed to a light theme, listed here
for visibility).</li>
<li><b>Tools</b> - connection settings, and IP Configuration (a quick ipconfig-style view of this
machine's network adapters). Connection Profiles and Data Templates are placeholders reserved for
a future release and aren't functional yet.</li>
<li><b>Diagnostics</b> - network discovery, system logs, clear logs. The Raw Data view lives in
its own tab now rather than under this menu - see the tab list above.</li>
<li><b>Help</b> - this documentation and the About dialog (which also checks GitHub for updates).</li>
</ul>

<p>See the topics on the left for details on each part of the app, and check
<b>Troubleshooting</b> if something isn't behaving the way you expect.</p>
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

<h3>Data formats</h3>
<p><b>Bool</b>, <b>U16/S16</b>, <b>U32/S32/F32</b> (plus <code>_SWAP</code> variants for the
opposite word order), and <b>Hex</b>. BOOL on a Coil/Discrete Input is a simple flag; BOOL on a
Holding/Input Register instead shows the full 16-bit pattern (e.g. <code>0000000000000101</code>)
so you can read individual status/alarm bits out of a status word. 32-bit formats (U32/S32/F32)
need an even <b>Count</b> (2, 4, ...) since they span two registers per value.</p>

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

<h3>Advanced Diagnostics toggle</h3>
<p>Off by default. Checking it reveals three more columns: <b>Function</b> (the Modbus function
code actually used, e.g. <code>0x03 Read Holding Registers</code>), <b>Unit ID</b>, and
<b>Details</b> (a register/bit count on success, or the specific classified exception - e.g.
"Illegal Data Address" - on failure). History already logged is populated too, not just new rows
going forward, so turning it on retroactively reveals detail on everything currently in the
table. Turn it on when you're chasing an intermittent fault and a one-line result isn't enough.</p>

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
<p><b>Add Pen</b> opens a grid of 20 slots (SCADA-style) - enable the ones you want, and set a
name, type, address, count, format, and color for each. Pens are analog values only (Holding or
Input Registers with a numeric format) - Coils, Discrete Inputs, and the Bool format aren't
offered here, since a trend line is meant for continuously varying values rather than on/off
state. If you need to watch a digital point over time, add it as a Tag and check its Read Value
column instead.</p>

<h3>Live vs Historical mode</h3>
<ul>
<li><b>Live</b> - the visible window always ends at "now"; new data appears at the right edge as
it arrives.</li>
<li><b>Hist</b> - the view stays where you left it while data keeps recording in the background,
so you can scroll/zoom through history without it jumping around.</li>
</ul>
<p>Newest data is always plotted at the current time, regardless of mode - what differs is
whether the visible window automatically follows it.</p>

<h3>Navigating</h3>
<p><b>Time Window</b> picks how much time is visible at once. <b>Zoom In/Out</b> halves or
doubles that span around wherever you're currently looking. <b>From</b>/<b>To</b> plus <b>Go</b>
jumps straight to a specific historical range (this switches to Hist mode).</p>

<h3>Graph Properties</h3>
<p>Set the X and Y axis titles, background/axis/grid colors, whether gridlines are shown, and
whether the Y axis auto-ranges to the data or uses a fixed Min/Max. Gridlines default to black;
change them here if you'd rather have something more subtle for a printed report.</p>

<h3>Logging and printing</h3>
<p><b>Log to CSV</b> appends a timestamped row per pen on every poll tick. <b>Print</b> saves the
current graph view as a PNG image or a PDF document - useful for attaching evidence of a fault
condition to a service report.</p>
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
<tr><td><code>READ COIL|DI|HR|IR &lt;addr&gt;</code></td><td>Read a value and log it.</td></tr>
<tr><td><code>LET &lt;name&gt; = &lt;expr&gt;</code></td><td>Assign a variable.</td></tr>
<tr><td><code>LOG &lt;expr&gt;</code></td><td>Print text/numbers to the console.</td></tr>
<tr><td><code>WAIT &lt;expr, ms&gt;</code></td><td>Pause without freezing the UI.</td></tr>
<tr><td><code>REPEAT &lt;expr&gt; ... END</code></td><td>Loop a block of commands.</td></tr>
<tr><td><code>IF &lt;expr&gt; &lt;op&gt; &lt;expr&gt; THEN &lt;command&gt;</code></td>
<td>Run one command conditionally. op is <code>== != &gt; &lt; &gt;= &lt;=</code>.</td></tr>
</table>

<h3>Expressions</h3>
<p>An expression can mix numbers, <code>"strings"</code>, variables, parentheses, and
<code>+ - * /</code>. Writing a bare <code>HR 0</code> inside an expression reads that register
inline (shorthand for <code>READ HR 0</code>). <code>+</code> also concatenates text with numbers,
so <code>LOG "value is " + x</code> works as expected. Types: COIL, DI (Discrete Input),
HR (Holding Register), IR (Input Register).</p>

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

<h3>Other tools in the editor</h3>
<ul>
<li><b>Insert Tag</b> - drops a reference (type and address) for any tag from your Tags list
straight into the script at the cursor, so you don't have to remember or retype addresses.</li>
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
sequence, a warm-up temperature, or any value that changes slowly on its own. Note that
<code>REPEAT</code> doesn't have a break/exit, so this always runs the full 60 checks; it's meant
as a bounded polling window rather than a wait-until-true loop.</p>

<h4>4. Ramp a setpoint up gradually</h4>
<pre>LET setpoint = HR 10
REPEAT 10
    LET setpoint = setpoint + 5
    WRITE HR 10 = setpoint
    LOG "Setpoint now " + setpoint
    WAIT 2000
END</pre>
<p>Steps a holding register up by 5 every 2 seconds instead of jumping straight to a final value -
useful for equipment that shouldn't see a large setpoint change all at once.</p>

<h4>5. Read several points and log them together</h4>
<pre>LET temp = HR 0
LET pressure = HR 1
LET running = COIL 0
LOG "Temp=" + temp + " Pressure=" + pressure + " Running=" + running</pre>
<p>A one-shot snapshot across mixed types (registers and a coil) in a single readable log line -
handy at the start or end of a longer script to record a baseline.</p>

<h4>6. Conditional checks with IF</h4>
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

<h3>Limits</h3>
<p>To keep a typo from hanging the app or running forever: a loop with no WAIT still hands
control back to the interface regularly instead of freezing it, and REPEAT counts, WAIT
durations, expression nesting, and total script length are all capped with a clear error if
exceeded. Separately, consecutive steps are never scheduled less than 20ms apart even if a
script asks for <code>WAIT 0</code> or omits WAIT entirely, so a typo can't flood the device or
network. See <b>Troubleshooting</b> for what the common error messages mean.</p>
"""),

    ("Multiple Windows", """
<h2>Multiple Windows</h2>
<p><b>File &gt; New Connection Window</b> opens a second, fully independent ModbusLens window -
its own connection, Address Table, Tags, Raw Data, Trend, and Server tab. Use this to talk to
several devices at the same time side by side, or to run a Client against your own Server tab from
a second window (see Server Mode).</p>
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
