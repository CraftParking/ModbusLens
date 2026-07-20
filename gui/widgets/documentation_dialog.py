from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTextBrowser, QPushButton, QSplitter

DOCS = [
    ("Getting Started", """
<h2>Getting Started</h2>
<p>ModbusLens is a Modbus TCP client for reading and writing coils/registers, monitoring named
tags, graphing values over time, simulating a slave device, running test scripts, and scanning
a network for Modbus devices.</p>

<h3>Basic workflow</h3>
<ol>
<li>Click <b>Settings</b> (top right) and enter the target device's IP address, port (usually 502),
and Unit ID.</li>
<li>Click <b>Connect</b>. The status indicator on the left turns green when connected.</li>
<li>Use the tabs below to work with the device: <b>Address Table</b> for quick reads/writes,
<b>Tags</b> for named live monitoring, <b>Trend</b> for graphing, <b>Server</b> to act as a
slave device yourself, and <b>Script</b> to automate a test sequence.</li>
</ol>

<h3>Menu bar</h3>
<ul>
<li><b>File</b> - open another independent connection window, session save/load, export, exit.</li>
<li><b>View</b> - display options.</li>
<li><b>Tools</b> - connection settings, profiles, templates.</li>
<li><b>Diagnostics</b> - network discovery, communication log, raw data, clear logs.</li>
<li><b>Help</b> - this documentation and the About dialog.</li>
</ul>

<p>See the other topics on the left for details on each part of the app.</p>
"""),

    ("Connecting to a Device", """
<h2>Connecting to a Device</h2>
<p>Open <b>Settings</b> in the top-right of the connection bar to configure:</p>
<ul>
<li><b>IP Address</b> - the target device or PLC's Modbus TCP address.</li>
<li><b>Port</b> - usually 502 for standard Modbus TCP.</li>
<li><b>Unit ID</b> - the Modbus slave/unit identifier (1 is common; some gateways ignore it).</li>
<li><b>Network Interface</b> - a convenience dropdown that fills in a local interface's IP,
useful when testing against yourself.</li>
<li><b>Recent Connections</b> - quickly reconnect to somewhere you've connected before.</li>
</ul>
<p>Click <b>Connect</b> to open the connection, <b>Disconnect</b> to close it. The status
indicator on the left shows Connected (green), Connecting (orange), or Disconnected/Error.</p>

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
toggle the checkbox and compare.</p>
"""),

    ("Address Table", """
<h2>Address Table</h2>
<p>A quick read/write grid for a contiguous range of one Modbus data type, similar to classic
tools like ModScan.</p>

<h3>Creating a table</h3>
<ol>
<li>Pick a <b>Function</b> (Read Coils, Read Holding Registers, Write Single Register, etc.).</li>
<li>Set <b>Start Address</b> and <b>Count</b>.</li>
<li>Click <b>Create Table</b>.</li>
</ol>
<p>Each row shows the Modbus reference address, the current value, and the same value in hex.
For a Write function, double-click the Value cell to edit and send it immediately (coil rows
show a checkbox instead).</p>

<h3>Live Monitoring</h3>
<p>For Read functions, check <b>Enable Live Monitoring</b> and set an interval to keep polling
the whole range automatically. Starting this auto-stops Tags monitoring, and vice versa, so the
two don't compete for the connection.</p>

<h3>Status Log</h3>
<p>The panel on the right shows what the table is doing - reads, writes, and any errors,
each with a timestamp.</p>
"""),

    ("Tags Monitoring", """
<h2>Tags Monitoring</h2>
<p>The Tags tab lets you name individual points scattered across different addresses and types,
and watch or write them all at once - unlike the Address Table, which is one contiguous range.</p>

<h3>Adding tags</h3>
<p><b>Add Tag</b> appends a new row (or inserts above the selected row, so you're never stuck
adding things only at the end). Each row has:</p>
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
so you can read individual status/alarm bits out of a status word.</p>

<h3>Alarms</h3>
<p>Right-click a tag row and choose <b>Configure Alarm...</b>. Numeric tags get a High and/or
Low limit; coils, discrete inputs, and BOOL-format registers get an ON/OFF trigger instead. The
Read Value cell turns red while the tag is in alarm.</p>

<h3>Logging</h3>
<p><b>Log to CSV</b> appends a timestamped row for every monitored tag on every poll tick to a
file you choose. <b>Export CSV</b>/<b>Import CSV</b> save or load the tag list itself (not the
live data).</p>

<h3>Safety interlock</h3>
<p>Writing is paused for the moment a value is being sent, then Read polling resumes automatically -
this stops a write and a read from overlapping on the same connection.</p>
"""),

    ("Trend", """
<h2>Trend</h2>
<p>Graphs up to 20 pens over time, either following the live clock or reviewing history.</p>

<h3>Pens</h3>
<p><b>Add Pen</b> opens a grid of 20 slots (SCADA-style) - enable the ones you want, and set a
name, type, address, count, format, and color for each.</p>

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
whether the Y axis auto-ranges to the data or uses a fixed Min/Max.</p>

<h3>Logging and printing</h3>
<p><b>Log to CSV</b> appends a timestamped row per pen on every poll tick. <b>Print</b> saves the
current graph view as a PNG image or a PDF document.</p>
"""),

    ("Server Mode", """
<h2>Server Mode</h2>
<p>The Server tab makes ModbusLens act as a Modbus TCP <b>slave</b> device instead of a client -
useful for testing your own SCADA/PLC program against a fake device, without needing real
hardware on hand.</p>

<h3>Starting the server</h3>
<ol>
<li>Set <b>Listen Address</b> (usually <code>0.0.0.0</code> to accept connections on any
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
<p>Only one Server tab can be running at once, across every open window - the underlying
library only supports a single active server per process. Starting a second one while another is
running is refused with a clear message; stop the first one to free it up.</p>
"""),

    ("Scripting", """
<h2>Scripting</h2>
<p>The Script tab runs small test sequences against the connected device using a purpose-built
command language - not a general-purpose one, just enough to write values, wait, read them back,
and repeat.</p>

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

<h3>Example</h3>
<pre>LET x = HR 0 + 10
WRITE HR 1 = x
WAIT 500
LOG "HR1 is now " + x
REPEAT 3
    WRITE COIL 0 = ON
    WAIT 250
    WRITE COIL 0 = OFF
    WAIT 250
END
IF HR 1 &gt;= 100 THEN LOG "over threshold"</pre>

<h3>Compile and Run</h3>
<p><b>Compile</b> checks the script's syntax without touching the device - use it to catch typos
before running anything. <b>Run</b> executes the script step by step; because it can write to a
live device, Run shows a one-time-per-preference warning first (with a "don't remind me again"
option) reminding you to be careful on in-service equipment. <b>Stop</b> halts a running script
at any point.</p>

<h3>Limits</h3>
<p>To keep a typo from hanging the app or running forever: a loop with no WAIT still hands
control back to the interface regularly instead of freezing it, and REPEAT counts, WAIT
durations, expression nesting, and total script length are all capped with a clear error if
exceeded.</p>
"""),

    ("Network Diagnostics", """
<h2>Network Diagnostics</h2>
<p>Available from <b>Diagnostics &gt; Network Discovery &amp; Diagnostics</b>. Scans the local
network for devices and checks which ones respond to Modbus.</p>
<ul>
<li><b>ARP-based discovery</b> - finds devices on the local subnet without needing to know their
IP addresses in advance.</li>
<li><b>Modbus detection</b> - probes discovered devices to see which ones answer Modbus requests,
so you're not guessing which IP is the PLC.</li>
<li><b>Packet capture</b> - deeper ARP sniffing, requires Npcap
(<a href="https://npcap.com/#download">npcap.com</a>) to be installed; without it, ModbusLens
falls back to a ping-based scan.</li>
<li><b>Device filtering</b> - "Show only Modbus devices" hides everything else from the list.</li>
</ul>
<p>Selecting a discovered device can fill in its IP/port for you in Connection Settings.</p>
"""),

    ("Multiple Windows", """
<h2>Multiple Windows</h2>
<p><b>File &gt; New Connection Window</b> opens a second, fully independent ModbusLens window -
its own connection, Address Table, Tags, Trend, and Server tab. Use this to talk to several
devices at the same time side by side.</p>
<p>The one exception is Server mode: only one Server tab can be actively running at a time,
across all open windows (see the Server Mode topic for why). Everything else is fully
independent per window.</p>
"""),

    ("Tips & Safety", """
<h2>Tips &amp; Safety</h2>
<ul>
<li>ModbusLens can both read <i>and write</i> live Modbus values. An incorrect write to a
production device can cause unexpected motion, changed setpoints, or bypassed safety logic.
Know the device's register map and have authorization before writing to anything real.</li>
<li>Use <b>Server Mode</b> as a local practice target: start a server in one window, connect to
it from another (or a second ModbusLens instance via a New Connection Window), and try things out
before pointing at real equipment.</li>
<li>If a value looks exactly one address off from what you expect, check the
<b>0-Based Addressing</b> checkbox - see the Connecting topic.</li>
<li>If a 32-bit value (U32/S32/F32) looks like nonsense, try the <code>_SWAP</code> variant of the
same format - different vendors order the two registers differently.</li>
<li>The Tags table's <b>Raw (Hex)</b> column is useful for exactly this kind of debugging, since
it shows the untouched register bits regardless of what format you've selected.</li>
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
