<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Professional Modbus TCP Client with Advanced Network Diagnostics</p>

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#v100-release">v1.0.0 Release</a> |
  <a href="#features">Features</a> |
  <a href="#installation">Installation</a> |
  <a href="#usage">Usage</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## Overview

**ModbusLens** is a desktop toolkit for engineers and technicians working with **Modbus TCP** devices. It provides a PySide6 GUI, a CLI entry point, live tag monitoring, diagnostics, and network discovery tools for testing and debugging PLCs, controllers, and other Modbus TCP equipment.

Current protocol support: **Modbus TCP only**.

## v1.0.0 Release

The first stable release is available on GitHub:

- Release tag: `v1.0.0`
- Windows build: `ModbusLens_V1.0.0.exe`
- Release page: https://github.com/professoroptimusprime/ModScope/releases/tag/v1.0.0

### Highlights

- Stable Modbus TCP read/write testing and live monitoring.
- PySide6 GUI with connection controls, address table, tag table, and status indicators.
- Real-time tag monitoring with configurable polling intervals.
- CSV import/export for reusable tag configurations.
- Detached monitoring results window for viewing live values and selected writes.
- Network diagnostics with interface selection, scanning, ARP/device discovery, and packet analysis.
- Diagnostics views for logs, raw data, results, and runtime statistics.
- Safety checks for connection validation, write/read separation, and operation warnings.
- Improved packaging support for creating a Windows executable.

## Features

### Modbus TCP Communication

- Read coils, discrete inputs, holding registers, and input registers.
- Write single/multiple coils and registers.
- Configure target IP, port, unit ID, address range, and register count.
- Run write operations without starting live monitoring.
- Keep live monitoring focused on read operations.

### GUI Application

- Modern PySide6 interface.
- Connection status indicator and recent connection history.
- Address table for quick Modbus operations.
- Tags tab for structured monitoring configurations.
- CSV import/export for tag tables.
- Detached results window for live monitoring output.
- Responsive layout improvements for desktop use.

### Network Diagnostics

- Select the network interface used for diagnostics.
- Scan IP ranges for Modbus devices.
- Discover devices through ARP information.
- Inspect packet-level Modbus traffic.
- Identify known industrial vendors from MAC address data.
- Stop scans manually when needed.

### Safety and Reliability

- Safety warnings before sensitive operations.
- Connection validation before reads/writes.
- Separate read and write workflows.
- Busy-range interlocks during polling.
- Error handling with user-facing messages and diagnostic logs.

## Installation

### Option 1: Download the v1.0.0 Windows Build

Download `ModbusLens_V1.0.0.exe` from the release page:

```text
https://github.com/professoroptimusprime/ModScope/releases/tag/v1.0.0
```

### Option 2: Run from Source

Requirements:

- Python 3.8 or higher
- Windows, Linux, or macOS

```bash
git clone https://github.com/professoroptimusprime/ModScope.git
cd ModScope
pip install -r requirements.txt
python gui_main.py
```

## Usage

### GUI Mode

```bash
python gui_main.py
```

Use the GUI to:

- Select a network interface.
- Enter target IP, port, and unit ID.
- Connect to a Modbus TCP device.
- Read or write values from the address table.
- Configure tags and start live monitoring.
- Import or export tag configurations as CSV.
- Open diagnostics from the menu.

### CLI Mode

```bash
python main.py
```

The CLI provides basic Modbus TCP read/write operations from the terminal.

## Project Structure

```text
ModbusLens/
|-- assets/                  # Icons and banner
|-- core/
|   `-- modbus_client.py      # Modbus TCP communication
|-- gui/
|   |-- main_window.py        # Main GUI application
|   |-- widgets/              # Address table, status, results window
|   |-- monitoring/           # Real-time monitoring manager
|   |-- diagnostics/          # Diagnostics dialogs and tools
|   `-- network/              # Network diagnostics
|-- app_paths.py              # Runtime path helpers
|-- build_exe.py              # PyInstaller build helper
|-- gui_main.py               # GUI entry point
|-- main.py                   # CLI entry point
|-- requirements.txt          # Python dependencies
`-- README.md
```

## Roadmap

Planned future work:

- Data logging and export improvements.
- Device configuration profiles.
- Advanced scripting and automated test sequences.
- Modbus RTU serial support.
- Modbus ASCII support.
- Multi-device management.
- Data visualization and reporting.

## Contributing

Bug reports and feature requests are welcome through GitHub Issues. Please include reproduction steps, expected behavior, actual behavior, and system details when reporting bugs.

## License

This project is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) for details.

## Author

**Alvin (CraftParking)** - Lead Developer
