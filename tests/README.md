# ModScope Test Script

Simple interactive Modbus TCP test script for reading and writing coils and holding registers.

---

## 🚀 Overview

This script is a basic command-line utility used to test Modbus TCP communication.

It allows users to:

* Connect to a Modbus device (PLC/RTU)
* Read values from coils or holding registers
* Write values to coils or registers

This is part of the core development phase of ModScope.

---

## ⚙️ Requirements

* Python 3.x
* pymodbus

Install dependencies:

```bash id="gy2k4k"
pip install pymodbus
```

---

## ▶️ Usage

Run the script:

```bash id="6z0j25"
python tests/test_modbus.py
```

---

## 🧾 Inputs

The script will prompt you for:

* IP address (default: 127.0.0.1)
* Port (default: 502)
* Unit ID (default: 1)

Then:

### Operation Selection

* `1` → Read
* `2` → Write

### Data Type Selection

* `1` → Coils
* `2` → Holding Registers

---

## 🔍 Read Operation

You will be asked:

* Start address
* Number of values (count)

Output:

* Displays values with corresponding addresses

---

## ✏️ Write Operation

You will be asked:

* Address
* Value

Notes:

* Coils accept values `0` or `1`
* Registers accept integer values

---

## 📌 Notes

* This is a development/testing script
* Not intended as a final application
* Will be integrated into the main ModScope core later