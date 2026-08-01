<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Free Modbus TCP &amp; RTU Client with Advanced Network Discovery &amp; Diagnostics</p>

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#highlights">Highlights</a> |
  <a href="#screenshots">Screenshots</a> |
  <a href="#features">Features</a> |
  <a href="#installation">Installation</a> |
  <a href="#notes">Notes</a> |
  <a href="#upcoming-features">Upcoming Features</a>
</p>

---

## Overview

**ModbusLens** is a **free desktop tool** built for engineers working with **Modbus devices**, combining communication, monitoring, and network diagnostics in one place.

> Supports **Modbus TCP/IP** and **Modbus Serial**, both RTU and ASCII framing

---

## Highlights

- Modbus TCP and Modbus Serial (RTU or ASCII framing) client, switchable per connection
- ARP-based device discovery (no IP needed)
- Automatic Modbus device detection
- Continuous live scanning (no repeated manual scans)
- Clean, non-spam device listing
- Integrated diagnostics + communication
- Live/historical trend graphing with up to 20 pens
- Act as a Modbus TCP slave for testing your own SCADA/PLC programs
- Talk to multiple devices at once, each in its own window
- Simple scripting for repeatable write/wait/read test sequences, against either a live device or ModbusLens's own Server simulator
- Serial Discovery: sweep common baud rate/parity/stop-bit/Unit ID combinations to find the settings a serial device actually uses
- Scanner: auto-discover which addresses actually respond on a connected device (TCP or serial)

---

## Screenshots

### Main Interface
<p align="center">
  <img src="assets/Main_window.PNG" width="90%">
</p>
<p align="center"><em>Address Table - quick read/write grid for a contiguous register range, with live monitoring and a status log alongside it.</em></p>

### Tag Monitoring
<p align="center">
  <img src="assets/tag_address.PNG" width="90%">
</p>
<p align="center"><em>Named tags across different addresses and types, monitored and written together in one list.</em></p>

### Raw Data
<p align="center">
  <img src="assets/Raw_data.PNG" width="90%">
</p>
<p align="center"><em>Every transaction's actual wire bytes, decoded value, latency, and status - the ground truth behind whatever a Tag or Address Table row shows.</em></p>

### Trend
<p align="center">
  <img src="assets/trend.PNG" width="90%">
</p>
<p align="center"><em>Live graphing of monitored values over time, up to 20 pens per graph.</em></p>

### Server Mode
<p align="center">
  <img src="assets/server.PNG" width="90%">
</p>
<p align="center"><em>ModbusLens acting as a Modbus TCP slave, so you can test a SCADA/PLC program - or another ModbusLens window - against it without real hardware.</em></p>

### Scripting
<p align="center">
  <img src="assets/script.PNG" width="90%">
</p>
<p align="center"><em>A write/wait/read test sequence running against the Server simulator, with the live Variables panel tracking state on the right.</em></p>

### Scanner
<p align="center">
  <img src="assets/Scanner.PNG" width="90%">
</p>
<p align="center"><em>Auto-discovering which Holding Register addresses respond on the connected device, in blocks rather than one address at a time.</em></p>

### Connection Settings
<p align="center">
  <img src="assets/connection_para.PNG" width="45%">
  <img src="assets/connection_para_serial.PNG" width="45%">
</p>
<p align="center"><em>Modbus TCP (left) and Modbus Serial RTU/ASCII (right) - one dialog, switchable per connection.</em></p>

### IP Configuration
<p align="center">
  <img src="assets/ip_config_window.PNG" width="70%">
</p>
<p align="center"><em>Read-only view of this machine's own network adapters, for figuring out which one to connect from.</em></p>

### Theme
<p align="center">
  <img src="assets/Theme.png" width="70%">
</p>
<p align="center"><em>Light, Dark, or Follow System, switchable from View > Theme (takes effect after restart).</em></p>

### Network Discovery & Diagnostics
<p align="center">
  <img src="assets/network_diag.PNG" width="90%">
</p>
<p align="center"><em>ARP-based device discovery plus Modbus detection, for finding a device's IP when you don't already know it.</em></p>

---

## Features

### Modbus TCP & RTU
- Read coils, inputs, holding & input registers  
- Write single/multiple coils & registers  
- Modbus TCP (IP/Port/Unit ID) or Modbus Serial (COM port, baud, parity, stop bits, byte size, and RTU/ASCII framing) - pick per connection in Settings  
- Address table for quick testing  
- Optional Min/Max write bounds per register - a write outside the range is rejected before it reaches the device, no matter if it came from the Address Table, Tags, or a Script  
- Auto-reconnect with backoff after an unexpected drop, and automatic resume of Tags monitoring once the connection recovers  
- Multiple simultaneous connections via independent windows (File > New Connection Window)  

### Data Handling
- BOOL, U16/S16, U32/S32, F32, HEX support  
- BOOL on a register shows the full 16-bit pattern, not just a single flag  
- Word order handling (*_SWAP)  
- 0-based / 1-based addressing, selectable per Address Table range and per Tag  
- Raw hex value shown alongside the decoded value, in both the Address Table and Tags  

### Monitoring
- Real-time tag monitoring, with Read Value/Write Value/Timestamp built into the same Tags table  
- Insert new tags anywhere in the list (new tags drop in below the selected row), not just at the end  
- Drag and drop to reorder rows, preserving live values and alarm config  
- Write to a tag while monitoring stays active  
- A single misconfigured or failing tag no longer stops the rest of the list from updating  
- Per-tag alarms (High/Low limits, or ON/OFF for coils/discrete/BOOL) with red highlighting  
- Log live tag values to CSV  
- CSV import/export  
- Improved stability  

### Raw Data
- One row per Modbus transaction: time, operation, raw value in decimal and hex, Success/Failed status, and round-trip latency  
- TX/RX Bytes - the literal bytes sent and received on the wire for that transaction (captured via pymodbus's trace hook), one level more raw than the decoded register values  
- Color-coded status (green success, red failure) at a glance, same coloring as the other logs  
- Filter by tag name/address/value, and by Success/Failed status, live as new rows arrive  
- Show Statistics - total requests, success/failure counts, and average/min/max response times across everything logged, not just what's currently visible  
- Capped at 1000 rows so it can't grow unbounded; oldest rows fall off automatically  

### Trend
- Up to 20 pens, each bound to a Holding/Input Register address and numeric format (analog values only - Coils/Discrete Inputs and Bool aren't plottable pens)  
- Live mode (follows the current time) or Historical mode (view stays put while data keeps recording)  
- Adjustable time window, zoom in/out, and a From/To jump to a specific past range  
- Graph Properties: axis titles, background/axis/grid colors, grid on/off, Y-axis auto or manual range  
- Log plotted values to CSV  
- Print to PNG or PDF  

### Server Mode
- Act as a Modbus TCP slave so another master can poll ModbusLens directly  
- Coils, Discrete Inputs, Holding Registers, and Input Registers are all editable live, as if you were the field device  
- Useful for testing your own SCADA/PLC program without real hardware  

### Scripting
- A small, purpose-built test-sequence language instead of embedded Python - built so a controls/automation engineer can write a test sequence without knowing how to program: no imports, no client objects, no exception handling to write, just `WRITE HR 1 = 100`. The tradeoff is deliberate - it can only do Modbus reads/writes/waits/logging/arithmetic, never arbitrary code, which is also what makes the safety limits below possible in the first place  
- `WRITE`, `READ`, `WAIT`, `LOG`, `LET`, `REPEAT...END`, `REPEAT UNTIL...END`, `IF...THEN`  
- Runs step by step without freezing the UI, with a console showing what ran  
- Target either a live connected device (Client-target) or ModbusLens's own Server simulator (Server-target), so you can dry-run a script safely before pointing it at real hardware  
- Live Variables panel next to the editor shows every `LET` variable's current value while the script runs, no extra `LOG` lines needed just to watch state  
- Insert Tag menu drops a reference to any tag from your Tags list straight into the script  
- Live CPU usage indicator, useful for spotting a runaway loop  
- Steps never run faster than a 20ms floor, even if a script uses `WAIT 0` or skips WAIT entirely, so a typo can't flood the device or network  

### Network Diagnostics
- ARP-based discovery  
- Modbus device detection  
- Packet capture (Npcap required)  
- Device filtering (Modbus only)  

### Serial Discovery
- Diagnostics menu tool that sweeps common baud rate/parity/stop-bit combinations - plus a Unit ID range - against a COM port to find which one a serial device actually speaks, for when its settings aren't documented  
- Opens its own short-lived connection per combination (byte size fixed at 8), so it needs the port free - disconnect ModbusLens first if it's the one holding it open  
- A **Scan for Connection Parameters...** button in Connection Settings' Serial section closes that dialog and opens Serial Discovery directly, with the COM port already filled in  

### Scanner
- Auto-discovers which addresses respond for a chosen function type (Coils/Discrete Inputs/Holding/Input Registers) over a given range - works the same way whether the current connection is TCP or serial  
- Probes the largest block the function allows first, and only narrows down address-by-address where a block doesn't fully respond - far fewer requests than checking one address at a time  
- Reuses the app's existing connection (like Address Table/Tags/Script), pausing Tags/Address Table live monitoring first so nothing else is polling the same connection at the same time  
- A configurable probe timeout keeps scanning fast over TCP; over a serial connection each probe is one bus round-trip, so a large range takes noticeably longer  

### UI Improvements
- Cleaner layout with compact connection bar  
- Improved status indicators  
- Better spacing and readability  
- More focused workspace (Address/Tags/Trend priority)  
- Light/Dark/Follow System theme, switchable from View > Theme (takes effect after restart)  
- Help > About has an Updates tab that checks GitHub Releases for a newer version  
- Color-coded logs (Address Table, System Logs, Script console) - writes in blue, connection events in green, errors in red  

---

## Installation

Download latest release:  
https://github.com/CraftParking/ModbusLens/releases

Run:
ModbusLens.exe

---

## Notes

- Advanced diagnostics require **Npcap**  
  https://npcap.com/#download  

- Enable during install:
  - WinPcap compatible mode  
  - Raw 802.11 (optional)

- Restart app after install  

- If errors:
  No libpcap provider available  
  or  
  Scapy not available  

Install dependency:
pip install scapy

---

## Upcoming Features

- Unified multi-device dashboard (currently one window per device)  
- Register maps with mixed data types per device profile  
- Multiple Unit IDs over a single connection (useful for RTU/ASCII sharing one serial line, or a TCP-to-RTU gateway fanning out to several devices)  
- Server tab simulating multiple devices/unit addresses at once, not just one  
- Auto-varying simulated values in Server mode (sine wave, ramp, random noise) instead of only static manually-set values  
- Broader Modbus function-code coverage beyond core read/write (diagnostics, file record access, device identification)  
- Raw byte injection - send a custom/malformed frame by hand, for testing non-standard device behavior or protocol compliance  
- Gateway mode - relay real traffic between RTU/ASCII serial and TCP instead of only simulating a device  
- 64-bit numeric formats and a string/text data type, beyond the current 32-bit cap  
- Single-bit read/write within a register, plus Masked Bit Write (FC22) support for legacy devices  
- RTU/ASCII framing encapsulated over TCP/UDP, for serial-to-Ethernet converters that tunnel raw framing instead of translating it  
- Engineering-unit scaling per tag/register (linear scale + offset, e.g. raw 0-4095 -> 0-100 PSI)  
- Trend markers - select a time range and see min/max/average for the pens in it  
- Calculated tags combining multiple registers via an expression, as a persistent Tag/Trend source (Scripting can already do this ad hoc; this would make it a saved, always-on tag)  

---

## Support

ModbusLens is **free software**.

If it helps you, consider supporting development:

<p>
  <a href="https://buymeacoffee.com/craftparking">
    <img src="assets/buy-me-a-coffee.png" height="45">
  </a>
</p>

Donations go strictly toward development of ModbusLens (time, tools, hardware for testing) — nothing else.

---

## Author

**Alvin (CraftParking)**