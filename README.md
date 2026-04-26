<p align="center">
  <img src="assets/banner.png" alt="ModScope Banner" width="100%">
</p>

<h1 align="center">ModScope</h1>
<p align="center">Lightweight and powerful Modbus diagnostic tool</p>

---

## 🚀 Overview

ModScope is a Modbus communication and diagnostic utility designed for engineers, technicians, and students working with industrial automation systems.

The tool enables **direct, low-level interaction** with Modbus-enabled devices such as PLCs, RTUs, and controllers. It provides a fast and reliable way to:

* Read register values in real time
* Write values for testing and validation
* Verify communication between systems
* Diagnose and debug Modbus-related issues

Unlike full-scale SCADA systems, ModScope focuses purely on **testing, validation, and diagnostics**, keeping the application lightweight and efficient.

---

## ✨ Key Capabilities (Planned & In Progress)

ModScope is being developed to support all major Modbus TCP function codes:

### 🔹 Read Operations

* Read Coils (FC01)
* Read Discrete Inputs (FC02)
* Read Holding Registers (FC03)
* Read Input Registers (FC04)

### 🔹 Write Operations

* Write Single Coil (FC05)
* Write Single Register (FC06)
* Write Multiple Coils (FC15)
* Write Multiple Registers (FC16)

### 🔹 Core Features

* Direct register-level access
* Real-time polling and monitoring
* Connection status handling
* Error detection and reporting
* Lightweight execution

---

## 🖥️ Application Design

ModScope follows a modular architecture:

### 1. Core Engine (Python)

Responsible for:

* Modbus communication
* Request/response handling
* Data validation and error handling

### 2. Graphical Interface (PySide6)

Provides:

* User-friendly interaction
* Data visualization
* Input controls for read/write operations

A packaged executable (`.exe`) will be provided for end users, allowing the application to run without requiring a Python environment.

---

## 🧱 Project Structure

```
modscope/
├── assets/        # UI resources (icons, images)
├── config/        # Device configuration files
├── core/          # Modbus communication logic
├── gui/           # PySide6 GUI implementation
├── tests/         # Testing scripts and experiments
├── utils/         # Helper utilities
├── main.py        # Application entry point
├── requirements.txt
```

---

## ⚙️ Installation (Development)

Clone the repository:

```
git clone https://github.com/CraftParking/ModScope.git
cd ModScope
```

Install dependencies:

```
pip install -r requirements.txt
```

---

## ▶️ Current Usage

At the current stage, ModScope is in core development.

```
python tests/test_modbus.py
```

Update the IP address and unit ID inside the script according to your Modbus device.

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

ModScope is currently under active development. Core communication features are implemented and being refined, with UI and advanced features under development.

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
