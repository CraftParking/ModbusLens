<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Modbus TCP Client with Advanced Network Discovery & Diagnostics</p>

<p align="center">
  <a href="#overview">Overview</a> |
  <a href="#highlights">Highlights</a> |
  <a href="#features">Features</a> |
  <a href="#installation">Installation</a> |
  <a href="#usage">Usage</a> |
  <a href="#roadmap">Roadmap</a>
</p>

---

## Overview

**ModbusLens** is a desktop tool designed for engineers working with **Modbus TCP devices**, combining communication, monitoring, and network diagnostics in a single interface.

Unlike traditional Modbus tools, ModbusLens focuses on **device discovery and troubleshooting**, helping identify and interact with devices even when network details are unknown.

---

## Highlights

- **ARP-Based Device Discovery**  
  Discover devices without knowing their IP address — especially useful for unknown or misconfigured PLCs.

- **Live Continuous Scanning**  
  Devices appear in real-time without needing repeated scans.

- **Automatic Modbus Detection**  
  Identifies which discovered devices respond to Modbus TCP.

- **Clean, Non-Spam Output**  
  Uses a unique device registry to avoid duplicate entries during continuous scanning.

- **Subnet Awareness**  
  Detects subnet mismatches and explains connectivity issues instead of failing silently.

---

## Features

### Modbus TCP
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
- Automatic Modbus device detection  
- Filter to show only Modbus devices  
- Packet capture support (Npcap required)  
- Vendor identification from MAC address (where available)  
- Stop scan control with proper cleanup  

### User Interface
- PySide6-based desktop GUI  
- Connection status indicators  
- Dedicated diagnostics window  
- Responsive layout for efficient workflow  

---

## Installation

### Windows

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

- Enter target IP, port, and unit ID to connect to a Modbus device  
- Use Address Table for read/write operations  
- Configure tags and start live monitoring  
- Open **Diagnostics → Network Discovery & Diagnostics**  
- Start discovery to identify devices on the network  

---

## Notes

- Advanced packet capture requires **Npcap**  
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