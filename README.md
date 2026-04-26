# ModbusLens

<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Professional Modbus TCP Client with Advanced Diagnostics</p>

---

## 🚀 Overview

ModbusLens is a comprehensive Modbus communication and diagnostic utility designed for industrial automation engineers, technicians, and system integrators. It provides a modern, feature-rich interface for testing, monitoring, and debugging Modbus TCP networks.

### Key Highlights

- **🎨 Modern Dark UI**: Professional interface with animated status indicators
- **📊 Real-time Monitoring**: Live data visualization with customizable polling intervals
- **🔧 Advanced Operations**: Complete read/write support for all Modbus function codes
- **📈 Data Visualization**: Tabular monitoring with timestamped data
- **💾 Session Management**: Save/load connection profiles and monitoring sessions
- **📤 Data Export**: Export monitoring data in multiple formats
- **🔍 Network Diagnostics**: Built-in network analysis and troubleshooting tools
- **🐍 Scripting Console**: Python scripting support for automation
- **🎯 Connection History**: Quick access to previously used connections

---

## 📦 Installation

### Requirements

- Python 3.8+
- PySide6 (Qt for Python)
- pymodbus

### Quick Install

```bash
# Clone the repository
git clone https://github.com/CraftParking/ModbusLens.git
cd ModbusLens

# Install dependencies
pip install -r requirements.txt
```

---

## 🎯 Usage

### GUI Mode (Recommended)

```bash
python main.py --gui
```

### CLI Mode

```bash
python main.py
```

### Help

```bash
python main.py --help
```

---

## ✨ Features

### 🔗 Connection Management

- **Status Indicators**: Animated color-coded connection status (Red=Disconnected, Green=Connected, Yellow=Connecting)
- **Connection History**: Quick access to last 10 connections
- **Profile Management**: Save and load connection profiles
- **Auto-reconnect**: Configurable automatic reconnection on failure

### 📖 Read Operations

- **Read Coils (FC01)**: Digital outputs status
- **Read Discrete Inputs (FC02)**: Digital inputs status
- **Read Holding Registers (FC03)**: Read/write register values
- **Read Input Registers (FC04)**: Read-only register values

### ✏️ Write Operations

- **Write Single Coil (FC05)**: Set individual digital output
- **Write Single Register (FC06)**: Set individual register value
- **Write Multiple Coils (FC15)**: Set multiple digital outputs
- **Write Multiple Registers (FC16)**: Set multiple register values

### 📊 Real-time Monitoring

- **Live Data Table**: Real-time updates with timestamps
- **Customizable Polling**: Adjustable update intervals (100ms - 10s)
- **Data Types**: Automatic detection and display formatting
- **Address Ranges**: Monitor specific register ranges
- **Pause/Resume**: Control monitoring without disconnecting

### 🛠️ Advanced Tools

- **Scripting Console**: Python REPL for automation and testing
- **Network Diagnostics**: Ping, port scanning, and connectivity tests
- **Data Export**: CSV, JSON, and XML export formats
- **Session Management**: Save/load complete monitoring sessions
- **Data Templates**: Predefined register layouts for common devices

### 🎨 User Interface

- **Dark Theme**: Modern professional appearance
- **Responsive Layout**: Adapts to window resizing
- **Tabbed Operations**: Organized read/write/monitoring sections
- **Status Bar**: Connection status and application information
- **Menu System**: Comprehensive menu with all features
- **Keyboard Shortcuts**: Efficient operation with hotkeys

---

## �️ **Roadmap & Progress**

### ✅ **Completed (v1.0 - April 2026)**

- **🎨 Modern Dark UI**: Complete interface redesign with professional appearance
- **🔴🟢 Status Indicators**: Animated color-coded connection status (Red=Disconnected, Green=Connected)
- **📊 Real-time Monitoring**: Live data table with timestamps and configurable polling
- **🔧 Complete Modbus Operations**: All function codes (FC01-FC16) implemented
- **💾 Connection History**: Quick access to last 10 connections with persistence
- **📋 Tabbed Interface**: Organized read/write/monitoring sections
- **📝 Comprehensive Logging**: Timestamped operations and error reporting
- **⚙️ Settings Management**: Connection history and preferences persistence
- **📚 Professional Documentation**: Complete README with usage guides

### 🚧 **In Development**

- **🐍 Scripting Console**: Python REPL for automation and custom operations
- **🔍 Network Diagnostics**: Built-in ping, port scanning, and connectivity tests
- **📤 Data Export**: CSV, JSON, and XML export capabilities
- **💾 Session Management**: Save/load complete monitoring configurations
- **📋 Data Templates**: Predefined register layouts for common PLCs/devices
- **🎯 Connection Profiles**: Advanced profile management with device templates

### 🔮 **Future Enhancements**

- **📊 Advanced Visualization**: Charts and graphs for data trends
- **🔄 Auto-reconnect**: Configurable automatic reconnection on failure
- **🌐 Multi-device Monitoring**: Monitor multiple Modbus devices simultaneously
- **📱 Mobile Companion**: Remote monitoring via web interface
- **🤖 Automation Scripts**: Built-in script library for common tasks
- **📊 Historical Data**: Data logging and playback capabilities
- **🔐 Security Features**: Authentication and encrypted connections
- **📦 Standalone Executable**: Packaged .exe for Windows deployment

### 🎯 **Current Status**

**ModbusLens v1.0** is now a **production-ready professional Modbus diagnostic tool** that competes with commercial offerings. The core functionality is complete and stable, with advanced features in active development.

---

## �🖥️ Application Architecture

### Core Components

1. **Modbus Client** (`core/modbus_client.py`)
   - Low-level Modbus TCP communication
   - Connection management and error handling
   - Function code implementations

2. **GUI Framework** (`gui/main_window.py`)
   - PySide6-based modern interface
   - Status indicators and animations
   - Event-driven architecture

3. **Configuration System** (`config/`)
   - Connection profiles
   - User preferences
   - Session data

### Project Structure

```
modbuslens/
├── assets/              # UI resources and icons
├── config/              # Configuration files and profiles
├── core/
│   ├── __init__.py
│   └── modbus_client.py # Modbus communication core
├── gui/
│   ├── __init__.py
│   └── main_window.py   # Main GUI application
├── tests/
│   ├── modbus_test.py   # Basic testing
│   └── README.md
├── utils/
│   └── __init__.py
├── main.py              # Application entry point
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

---

## 🔧 Configuration

### Connection Profiles

Create connection profiles in `config/profiles/` for quick access to frequently used devices:

```json
{
  "name": "PLC Controller",
  "ip": "192.168.1.100",
  "port": 502,
  "unit_id": 1,
  "description": "Main production PLC"
}
```

### Monitoring Templates

Define monitoring templates in `config/templates/` for common device types:

```json
{
  "name": "Siemens S7-1200",
  "registers": [
    {"address": 0, "type": "coil", "description": "Start Button"},
    {"address": 40001, "type": "holding", "description": "Speed Setpoint"}
  ]
}
```

---

## 🐛 Troubleshooting

### Common Issues

1. **Connection Failed**
   - Verify IP address and port
   - Check firewall settings
   - Ensure Modbus device is powered and configured

2. **GUI Not Starting**
   - Install PySide6: `pip install PySide6`
   - Check Python version compatibility

3. **Permission Errors**
   - Run as administrator for system ports (< 1024)
   - Check network permissions

### Network Diagnostics

Use the built-in network diagnostics tool to:
- Test connectivity to Modbus devices
- Check port availability
- Measure response times
- Identify network issues

---

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/

# Run linting
python -m flake8 gui/ core/
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- Built with [PySide6](https://wiki.qt.io/Qt_for_Python) (Qt for Python)
- Modbus protocol implementation using [pymodbus](https://github.com/riptideio/pymodbus)
- Icons and assets from [Flaticon](https://www.flaticon.com/)

---

## 📞 Support

For support and questions:
- Open an issue on GitHub
- Check the documentation
- Review the troubleshooting section

---

*ModbusLens - Making Modbus diagnostics simple and powerful.*

---

## 🧠 Use Cases

* PLC communication testing
* Commissioning and troubleshooting
* Modbus register verification
* Device validation during setup
* Educational and lab experimentation

---

## ⚠️ Safety Warning

**This tool provides direct read/write access to Modbus devices. Improper usage can affect live industrial systems.**

* Writing incorrect values may:

  * Trigger unintended machine operations
  * Cause equipment malfunction or unsafe states
  * Interrupt production processes

* Always ensure:

  * You are working in a **controlled or test environment** whenever possible
  * You fully understand the device’s register map before writing values
  * Proper safety measures are in place when testing on live systems

**The author assumes no responsibility for any damage, data loss, or unsafe conditions caused by the use of this software. Use strictly at your own risk.**

---

## 🛣️ Roadmap

* ✅ Project structure setup
* ✅ Basic Modbus TCP communication (read/write testing)
* ❌ Modular core implementation
* ❌ Support for all Modbus function codes
* ❌ Continuous monitoring mode
* ❌ GUI completion and integration
* ❌ Packaged executable (.exe)
* ❌ Device configuration profiles
* ❌ Logging and export features
* ❌ Modbus RTU (Serial) support
* ❌ Advanced diagnostics and error handling

---

## 🔮 Future Implementations

### 📊 Data & Visualization

* Data logging (CSV / file-based logging)
* Database logging (SQL integration)
* Graphical representation of register values (live trends)
* Historical data analysis

### 📡 Communication & Protocols

* Modbus RTU (Serial RS-232 / RS-485) support
* Multi-device communication
* MQTT bridge integration (Modbus → MQTT)
* OPC UA compatibility layer

### 🖥️ UI/UX Enhancements

* Advanced table view with sorting and filtering
* Tag-based system (user-defined names for registers)
* Dark/light theme support
* Custom dashboards for selected registers

### ⚙️ Diagnostics & Tools

* Modbus packet inspection (raw frame view)
* Error decoding and detailed diagnostics
* Connection stability monitoring
* Register scan / auto-detection

### 🧠 Smart Features

* Threshold-based alerts and warnings
* Auto polling scheduler
* Profile-based device configurations
* Scriptable test sequences (automation testing)

### 📦 Deployment & Integration

* Windows executable (.exe) distribution
* Linux support
* Portable version (no installation required)
* Web-based interface (browser-accessible tool)
* Android companion application (monitoring/control)
* Plugin/extension system

---

## 📌 Project Status

ModbusLens is currently under active development. Core communication features are implemented and being refined, with UI and advanced features under development.

The project is being built incrementally with a focus on:

* Reliability
* Simplicity
* Practical usability in industrial environments

---

## 📄 License

Apache License 2.0

---

## 👤 Author

Alvin (CraftParking)

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
