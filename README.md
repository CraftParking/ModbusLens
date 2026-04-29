<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">🏭 Professional Modbus TCP Client with Advanced Network Diagnostics</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-roadmap">Roadmap</a>
</p>

---

## 📖 Overview

**ModbusLens** is a comprehensive industrial automation toolkit designed for professionals working with Modbus TCP networks. Built with precision engineering in mind, it combines powerful diagnostic capabilities with an intuitive interface for testing, monitoring, and debugging Modbus-enabled devices including PLCs, RTUs, and industrial controllers.

### 🎯 Mission Statement
To provide industrial automation engineers with a reliable, feature-rich Modbus TCP client that enhances productivity while maintaining the highest standards of safety and performance.

---

## ⭐ Key Features

### 🔧 **Advanced Modbus Communication**
- **Complete Modbus TCP Implementation**: Full support for all standard function codes
- **Real-time Operations**: Immediate write operations without monitoring requirements
- **Connection Management**: Robust connection handling with automatic reconnection
- **Write Function Support**: All write operations work independently without live monitoring

### 🖥️ **Professional GUI Interface**
- **Modern PySide6 Interface**: Clean, responsive, and professional design
- **Responsive Layout**: Proper window resizing without element overlapping
- **Address Table**: Configurable address ranges and function selection
- **Real-time Monitoring**: Live data updates with configurable intervals
- **Tag Management System**: Excel-style tag configuration and management
- **Network Interface Selection**: Choose specific network adapters for communication
- **Smart Control Logic**: Functions disabled until connection established
- **Clean Codebase**: Optimized and streamlined project structure

### 🔍 **Enterprise Network Diagnostics**
- **Wireshark-like Packet Capture**: Advanced network analysis capabilities
- **ARP Device Discovery**: Automatic network device identification
- **MAC Vendor Database**: 20+ PLC manufacturer identification via MAC addresses
- **Windows-Compatible**: Cross-platform packet analysis without administrator requirements
- **Network Scanner**: IP range scanning for Modbus device discovery
- **Real-time Packet Analysis**: Live Modbus traffic detection and function code analysis

### 🛡️ **Industrial Safety Features**
- **Safety Warning Dialogs**: Comprehensive safety notices before operations
- **Connection Validation**: Verified connections before allowing operations
- **Error Handling**: Robust error management with user-friendly messages
- **Write Protection**: Smart write-only operations for write functions
- **Read-Only Monitoring**: Live monitoring restricted to read functions only

---

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- Windows/Linux/macOS operating system

### Quick Install
```bash
# Clone the repository
git clone https://github.com/your-username/ModbusLens.git
cd ModbusLens

# Install dependencies
pip install -r requirements.txt

# Run the application
python gui_main.py
```

### Optional Dependencies
```bash
# For enhanced network diagnostics (optional)
pip install psutil

# Basic functionality works without psutil
# Automatic fallback to alternative detection methods
```

---

## 📖 Usage Guide

### 🖥️ **GUI Mode (Recommended)**
```bash
python gui_main.py
```

### 🎛️ **Main Interface Features**

#### **Connection Section**
- **Network Interface Selection**: Choose specific network adapter
- **IP Configuration**: Target device IP address
- **Port Configuration**: Modbus TCP port (default: 1700)
- **Unit ID**: Modbus device identifier (1-247)
- **Connection History**: Quick access to recent connections

#### **Address Table Tab**
- **ModScan-like Interface**: Familiar for industrial engineers
- **Function Selection**: All 8 standard Modbus functions
- **Address Range**: Configurable start address and count
- **Live Monitoring**: Real-time data updates (read functions only)
- **Write Operations**: Immediate write without monitoring requirement
- **Smart Editability**: Value column editable only for write functions

#### **Tags Tab**
- **Excel-style Management**: Professional tag configuration
- **Real-time Monitoring**: Live data updates with configurable intervals
- **Data Export**: Export monitoring results to external window
- **Tag Functions**: Support for read/write operations with different data types

### 🔧 **Network Diagnostics**
```bash
# Access from Tools → Network Diagnostics in the GUI
```

#### **Diagnostic Capabilities**
- **Interface Selection**: Choose network interface for analysis
- **Device Discovery**: Scan network for Modbus devices
- **Packet Capture**: Wireshark-like network analysis
- **ARP Analysis**: MAC address vendor identification
- **PLC Detection**: Automatic manufacturer identification
- **Stop Control**: User-controlled scan termination

---

## 🏗️ Architecture

### 📁 **Project Structure**
```
ModbusLens/
├── 📁 gui/
│   ├── � main_window.py           # Main GUI application
│   ├── 📁 widgets/
│   │   ├── � address_table.py     # Address table interface
│   │   ├── � monitoring_window.py # Results display
│   │   └── � status_indicator.py  # Connection status
│   ├── 📁 monitoring/
│   │   └── � monitoring_manager.py # Real-time data management
│   └── 📁 network/
│       └── � network_diagnostics.py # Advanced network analysis
├── 📁 core/
│   └── � modbus_client.py         # Modbus TCP communication
├── 📁 diagnostics/
│   ├── � advanced_diagnostics.py  # Advanced diagnostic tools
│   └── � diagnostics_dialogs.py   # Diagnostic interface
├── 📁 assets/                      # Images and resources
├── � app_paths.py                # Application path utilities
├── � gui_main.py                  # Main application entry
├── 📄 main.py                      # CLI application entry
├── 📄 requirements.txt             # Python dependencies
└── 📄 README.md                    # This file
```

### 🔧 **Technology Stack**
- **Frontend**: PySide6 (Qt6) for professional GUI
- **Communication**: Custom Modbus TCP client implementation
- **Network Analysis**: Raw socket programming with Windows compatibility
- **Data Processing**: Threading for real-time operations
- **Cross-platform**: Windows, Linux, and macOS support

---

## 📊 Current Status

### ✅ **Completed Features**
- [x] Full Modbus TCP client implementation
- [x] Professional GUI with modern design
- [x] Address table interface
- [x] Real-time monitoring system
- [x] Advanced network diagnostics
- [x] Packet capture and analysis
- [x] ARP device discovery with vendor lookup
- [x] Network interface selection
- [x] Windows-compatible implementation
- [x] Safety warning systems
- [x] Smart write/read function separation
- [x] Connection history management
- [x] Error handling and recovery
- [x] Responsive layout design (no element overlapping)
- [x] Clean and optimized codebase
- [x] Cross-platform path management

### 🔄 **In Development**
- [ ] Data logging and export functionality
- [ ] Device configuration profiles
- [ ] Advanced scripting capabilities
- [ ] Modbus RTU support
- [ ] Multi-device management

---

## 🚀 Roadmap

### 🎯 **Future Development**

#### **Enhanced Data Management**
- CSV/Excel export capabilities
- Historical data logging
- Data visualization charts
- Custom report generation

#### **Advanced Scripting**
- Python scripting integration
- Automated test sequences
- Custom function development
- Batch operation support

#### **Multi-Protocol Support**
- Modbus RTU (Serial)
- Modbus ASCII
- Multi-device management
- Device topology mapping

#### **Enterprise Features**
- User management and permissions
- Audit logging
- Remote monitoring capabilities
- API integration for third-party tools

---

## 🤝 Contributing

We welcome contributions from the community! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### 🐛 **Bug Reports**
- Use GitHub Issues for bug reports
- Provide detailed reproduction steps
- Include system information and error logs

### 💡 **Feature Requests**
- Submit feature requests via GitHub Issues
- Provide use case descriptions

---

## 📜 License

This project is licensed under **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

---

## 👥 Development Team

**Alvin (CraftParking)**
- Lead Developer

### 🤝 **Contributors**
We thank all contributors who help make ModbusLens better for the community.

---

## 🙏 Acknowledgments

- **Qt/PySide6 Team**: For the excellent GUI framework
- **Community**: For valuable feedback and suggestions
- **Open Source Contributors**: For making this project possible
- **Beta Testers**: For thorough testing and bug reports