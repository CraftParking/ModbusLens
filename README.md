<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Modbus TCP Client with Network Discovery & Diagnostics</p>

---

## Overview

**ModbusLens** is a desktop tool for testing and diagnosing **Modbus TCP devices** such as PLCs and controllers.

It combines:
- Modbus communication tools
- Real-time monitoring
- Network discovery (ARP-based)

---

## v1.0.0 Release

- Stable Modbus TCP read/write support  
- GUI-based testing and monitoring  
- Network discovery and diagnostics  

Download:  
https://github.com/professoroptimusprime/ModScope/releases/tag/v1.0.0

---

## Key Features

### Modbus TCP
- Read/write coils and registers  
- Configure IP, port, unit ID  
- Address table for quick testing  

### Monitoring
- Real-time tag monitoring  
- Configurable polling  
- CSV import/export  

### Network Discovery & Diagnostics
- Continuous ARP-based device discovery  
- Automatic Modbus device detection  
- Filter to show only Modbus devices  
- Live scanning (no repeated manual scans)  
- Subnet mismatch detection  
- Packet capture support (Npcap required)  

### UI
- PySide6 desktop interface  
- Connection status and controls  
- Dedicated diagnostics window  

---

## Installation

### Windows (Recommended)

Download:  
https://github.com/professoroptimusprime/ModScope/releases/tag/v1.0.0

Run:
```
ModbusLens_V1.0.0.exe
```

---

### From Source

```bash
git clone https://github.com/professoroptimusprime/ModScope.git
cd ModScope
pip install -r requirements.txt
python gui_main.py
```

---

## Usage

- Connect to a Modbus device using IP and port  
- Use Address Table for read/write  
- Use Tags tab for monitoring  
- Open **Diagnostics → Network Discovery & Diagnostics**  
- Start device discovery  

---

## Notes

- Packet capture features require **Npcap**  
- Restart the application after installing Npcap  

---

## Roadmap

- Modbus RTU support  
- Multi-device management  
- Data logging and visualization  

---

## Author

**Alvin (CraftParking)**