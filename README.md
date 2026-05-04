<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Professional Modbus TCP Client with Network Discovery & Diagnostics</p>

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#key-highlights">Key Highlights</a> |
  <a href="#features">Features</a> |
  <a href="#installation">Installation</a> |
  <a href="#usage">Usage</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## Overview

**ModbusLens** is a desktop toolkit for engineers and technicians working with **Modbus TCP devices**. It combines communication, monitoring, and network diagnostics into a single application, making it easier to test, analyze, and discover industrial devices.

---

## Key Highlights

These are the features that set ModbusLens apart from typical Modbus tools:

- **ARP-Based Device Discovery**  
  Discover devices on the network without knowing their IP address. This is especially useful when working with unknown or misconfigured PLCs.

- **Live Continuous Scanning (No Manual Re-scan)**  
  Devices appear in real-time as they are detected, eliminating the need to repeatedly trigger scans.

- **Automatic Modbus Device Detection**  
  Identifies which discovered devices actually respond to Modbus TCP.

- **Clean, Non-Spam Output**  
  Uses a unique device registry to avoid duplicate entries during continuous scanning.

- **Subnet Mismatch Detection**  
  Clearly indicates when a device is unreachable due to IP network mismatch, helping diagnose connection issues quickly.

---

## Features

### Modbus TCP Communication
- Read coils, discrete inputs, holding registers, and input registers  
- Write single and multiple coils/registers  
- Configure IP, port, unit ID, and address ranges  
- Address table for quick testing  

### Monitoring
- Real-time tag monitoring with configurable polling  
- Structured tag configuration  
- CSV import/export support  
- Detached monitoring results window  

### Network Discovery & Diagnostics
- Continuous ARP-based device discovery  
- Automatic Modbus detection  
- Filter to show only Modbus devices  
- Packet capture support (Npcap required)  
- Stop scan control and safe cleanup  
- Vendor identification from MAC address (where available)  

### User Interface
- PySide6 desktop interface  
- Connection status indicators  
- Dedicated diagnostics window  
- Responsive layout for efficient workflow  

---

## Installation

### Windows (Recommended)

Download the latest release:  
https://github.com/professoroptimusprime/ModScope/releases

Run:
```
ModbusLens.exe
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

- Enter target IP, port, and unit ID to connect  
- Use Address Table for read/write operations  
- Configure tags and start monitoring  
- Open **Diagnostics → Network Discovery & Diagnostics**  
- Start discovery to identify devices on the network  

---

## Notes

- Advanced packet capture features require **Npcap**  
- Restart the application after installing Npcap  

---

## Roadmap

- Modbus RTU support  
- Multi-device management  
- Data logging and export  
- Advanced scripting and automation  

---

## Author

**Alvin (CraftParking)**