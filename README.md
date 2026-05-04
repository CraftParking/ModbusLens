<p align="center">
  <img src="assets/modbuslens_banner.png" alt="ModbusLens Banner" width="100%">
</p>

<h1 align="center">ModbusLens</h1>
<p align="center">Free Modbus TCP Client with Advanced Network Discovery & Diagnostics</p>

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

**ModbusLens** is a **free desktop tool** built for engineers working with **Modbus TCP devices**, combining communication, monitoring, and network diagnostics in one place.

> Currently supports **Modbus TCP/IP only**

---

## Highlights

- ARP-based device discovery (no IP needed)
- Automatic Modbus device detection
- Continuous live scanning (no repeated manual scans)
- Clean, non-spam device listing
- Integrated diagnostics + communication

---

## Screenshots

### Main Interface
<p align="center">
  <img src="assets/Main_window.PNG" width="90%">
</p>

### Address Table (Read / Write)
<p align="center">
  <img src="assets/address_table.PNG" width="90%">
</p>

### Tag Monitoring
<p align="center">
  <img src="assets/tag_address.PNG" width="90%">
</p>

### Network Discovery & Diagnostics
<p align="center">
  <img src="assets/network_diag.PNG" width="90%">
</p>

### Communication Log (NEW)
<p align="center">
  <img src="assets/communication_log.PNG" width="90%">
</p>

### Connection Parameters (NEW)
<p align="center">
  <img src="assets/connection_para.PNG" width="90%">
</p>

### Combined Status & Monitoring View (NEW)
<p align="center">
  <img src="assets/com_and_stats.PNG" width="90%">
</p>

---

## Features

### Modbus TCP
- Read coils, inputs, holding & input registers  
- Write single/multiple coils & registers  
- Address table for quick testing  

### Data Handling
- BOOL, U16/S16, U32/S32, F32, HEX support  
- Word order handling (*_SWAP)  
- Improved 0-based / 1-based addressing  

### Monitoring
- Real-time tag monitoring  
- Detached results window  
- CSV import/export  
- Improved stability  

### Network Diagnostics
- ARP-based discovery  
- Modbus device detection  
- Packet capture (Npcap required)  
- Device filtering (Modbus only)  

### UI Improvements (v1.1.0)
- Cleaner layout with compact connection bar  
- Improved status indicators  
- Better spacing and readability  
- More focused workspace (Address/Tags priority)  

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

- Modbus RTU support  
- Multi-device management  
- Graphical visualization (charts/trends)  
- Data logging  
- Scripting & automation  

---

## Support

ModbusLens is **free software**.

If it helps you, consider supporting development:

<p>
  <a href="https://buymeacoffee.com/craftparking">
    <img src="assets/buy-me-a-coffee.png" height="45">
  </a>
</p>

---

## Author

**Alvin (CraftParking)**