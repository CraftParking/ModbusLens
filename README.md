<p align="center">
  <img src="assets/banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Professional Modbus TCP Client with Diagnostic Capabilities</p>

---

## 📖 Overview

ModbusLens is a Modbus TCP communication and diagnostic tool designed for industrial automation engineers, technicians, and students.

It provides a clean interface for testing, monitoring, and debugging Modbus-enabled devices such as PLCs, RTUs, and controllers.

---

## ⚙️ Features

### 🔹 Modbus Communication
- Full Modbus TCP client implementation  
- Configurable IP, Port, and Unit ID  
- Support for standard function codes:
  - FC01 – Read Coils  
  - FC02 – Read Discrete Inputs  
  - FC03 – Read Holding Registers  
  - FC04 – Read Input Registers  
  - FC05 – Write Single Coil  
  - FC06 – Write Single Register  
  - FC15 – Write Multiple Coils  
  - FC16 – Write Multiple Registers  

---

### 🖥️ Graphical Interface (GUI)
- PySide6-based interface  
- Structured read/write operation panels  
- Connection status display  
- Real-time output console  
- Error handling with dialogs  

---

### 💻 Command-Line Interface (CLI)
- Interactive menu-based tool  
- Quick testing and debugging  
- Lightweight execution  

---

## 🚀 Usage

### GUI Mode
    python main.py --gui

### CLI Mode
    python main.py

---

## 🧪 Use Cases

- PLC communication testing  
- Modbus register verification  
- Commissioning and troubleshooting  
- Educational and lab experiments  

---

## 📁 Project Structure

    modbuslens/
    ├── assets/
    ├── config/
    ├── core/
    │   └── modbus_client.py
    ├── gui/
    │   └── main_window.py
    ├── tests/
    ├── utils/
    ├── main.py
    ├── requirements.txt
    └── README.md

---

## 🛠️ Tech Stack

- Python 3.8+  
- PySide6 (GUI)  
- pymodbus (communication)  

---

## 📌 Current Status

- Core communication layer complete  
- CLI interface stable  
- GUI interface functional  
- Suitable for testing and demonstration  

---

## 🔮 Future Improvements

- Continuous polling / live monitoring  
- Data logging and export  
- UI enhancements  
- Device configuration profiles  

---

## ⚠️ Safety Notice

This tool allows direct read/write access to Modbus devices.

Improper usage may:
- Trigger unintended machine behavior  
- Affect live industrial systems  
- Cause equipment malfunction  

Use only in controlled environments when possible.  
Ensure you understand the device register map before writing values.

---

## 📜 License

Apache License 2.0

---

## 👤 Author

Alvin (CraftParking)