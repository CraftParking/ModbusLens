import socket
import time
import struct
import re
import platform
import subprocess
import ipaddress
import os
import webbrowser
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QTextEdit, QLineEdit, QLabel, QSpinBox, QProgressBar, QComboBox, QCheckBox
from PySide6.QtCore import QTimer

NPCAP_DOWNLOAD_URL = "https://npcap.com/#download"


def get_local_subnet_info():
    """Get local IP and subnet mask for subnet matching."""
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Try to get subnet mask from psutil
        if PSUTIL_AVAILABLE:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and addr.address == local_ip:
                        return {
                            "ip": local_ip,
                            "netmask": addr.netmask,
                            "network": str(ipaddress.IPv4Network(f"{local_ip}/{addr.netmask}", strict=False))
                        }
        
        # Fallback: assume /24 subnet
        return {
            "ip": local_ip,
            "netmask": "255.255.255.0",
            "network": str(ipaddress.IPv4Network(f"{local_ip}/24", strict=False))
        }
    except Exception:
        return None


def is_ip_in_subnet(ip, subnet_info):
    """Check if an IP is in the local subnet."""
    if not subnet_info:
        return True  # Assume in subnet if we can't determine
    
    try:
        ip_obj = ipaddress.IPv4Address(ip)
        network = ipaddress.IPv4Network(subnet_info["network"])
        return ip_obj in network
    except Exception:
        return True  # Assume in subnet on error


def probe_modbus_device(ip, port=502, timeout=1.0):
    """Probe a device to check if it's a Modbus device."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        
        if result == 0:
            # Connection successful, try a safe read to validate Modbus
            try:
                from core.modbus_client import ModbusClient
                modbus = ModbusClient(ip, port, 1, timeout=timeout)
                if modbus.connect():
                    # Try to read a holding register (safe operation)
                    try:
                        data = modbus.read_registers(0, 1)
                        modbus.disconnect()
                        return "YES" if data is not None else "NO"
                    except Exception:
                        modbus.disconnect()
                        return "NO"
                else:
                    return "NO"
            except ImportError:
                # If ModbusClient not available, just check TCP connection
                return "YES" if result == 0 else "NO"
        else:
            return "TIMEOUT"
    except Exception:
        return "TIMEOUT"


class ModbusProbeWorker(QThread):
    """Worker thread for probing multiple devices for Modbus capability."""
    
    probe_complete = Signal(str, str)  # ip, status
    all_probes_complete = Signal()
    output = Signal(str)
    
    def __init__(self, devices, subnet_info=None, port=502, timeout=1.0):
        super().__init__()
        self.devices = devices  # List of (ip, mac, vendor) tuples
        self.subnet_info = subnet_info
        self.port = port
        self.timeout = timeout
        self.should_stop = False
    
    def run(self):
        """Probe all devices for Modbus capability."""
        if not self.devices:
            self.all_probes_complete.emit()
            return
            
        self.output.emit(f"Probing {len(self.devices)} devices for Modbus capability...")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {}
            for ip, mac, vendor in self.devices:
                if self.should_stop:
                    break
                
                # Check subnet first
                if not is_ip_in_subnet(ip, self.subnet_info):
                    self.probe_complete.emit(ip, "UNREACHABLE (Subnet mismatch)")
                    continue
                
                # Submit Modbus probe
                future = executor.submit(probe_modbus_device, ip, self.port, self.timeout)
                futures[future] = ip
            
            # Collect results
            for future in as_completed(futures):
                if self.should_stop:
                    break
                ip = futures[future]
                try:
                    status = future.result()
                    self.probe_complete.emit(ip, status)
                except Exception as e:
                    self.probe_complete.emit(ip, "TIMEOUT")
        
        self.all_probes_complete.emit()
    
    def stop(self):
        """Stop the probing process."""
        self.should_stop = True


def detect_packet_capture_capability():
    """Return runtime packet-capture capability information using actual Scapy pcap verification."""
    if platform.system().lower() != "windows":
        return {
            "advanced": True,
            "mode": "Advanced",
            "label": "Mode: Advanced",
            "reason": "Raw socket capture is available on supported Unix-like systems with proper privileges.",
            "npcap_installed": True,
            "scapy_available": True,
            "interfaces_available": True,
            "pcap_available": True,
            "failure_reason": None,
        }

    # Check 1: Scapy availability and pcap backend
    scapy_available = False
    pcap_available = False
    scapy_interfaces = []
    
    try:
        from scapy.all import get_if_list, conf
        scapy_available = True
        
        # Check if pcap backend is actually available
        # Scapy's conf.use_pcap indicates if pcap is usable
        pcap_available = conf.use_pcap if hasattr(conf, 'use_pcap') else False
        
        # Additional check: try to get interfaces - this will fail if pcap is not available
        if pcap_available:
            try:
                scapy_interfaces = get_if_list()
                # If we got interfaces, pcap is definitely working
                pcap_available = bool(scapy_interfaces)
            except Exception:
                # If get_if_list fails, pcap is not actually available
                pcap_available = False
    except Exception as e:
        scapy_available = False
        pcap_available = False

    # Debug logging
    print(f"[DEBUG] Scapy available: {scapy_available}")
    print(f"[DEBUG] pcap backend available: {pcap_available}")
    print(f"[DEBUG] Scapy interfaces found: {len(scapy_interfaces)}")

    # Check 2: Interface availability
    interfaces_available = bool(scapy_interfaces)

    # Determine advanced mode (requires Scapy AND working pcap backend AND interfaces)
    advanced = bool(scapy_available and pcap_available and interfaces_available)

    # Debug logging
    print(f"[DEBUG] Advanced mode: {advanced}")
    print(f"[DEBUG] - Scapy: {scapy_available}, pcap: {pcap_available}, Interfaces: {interfaces_available}")

    # Determine specific failure reason
    failure_reason = None
    if not advanced:
        if not scapy_available:
            failure_reason = "Scapy not installed"
        elif not pcap_available:
            failure_reason = "Packet capture backend unavailable (libpcap/Npcap not working)"
        elif not interfaces_available:
            failure_reason = "No capture interfaces available"

    # Build label with specific reason
    if advanced:
        label = "Mode: Advanced"
        reason = "Scapy with working pcap backend and capture interfaces are available."
    else:
        label = f"Mode: Basic ({failure_reason})"
        reason = f"Advanced capture unavailable: {failure_reason}."

    return {
        "advanced": advanced,
        "mode": "Advanced" if advanced else "Basic",
        "label": label,
        "reason": reason,
        "npcap_installed": pcap_available,  # Use actual pcap availability instead of installation check
        "scapy_available": scapy_available,
        "interfaces_available": interfaces_available,
        "pcap_available": pcap_available,
        "failure_reason": failure_reason,
        "interfaces": scapy_interfaces,
    }


class NetworkDiagnosticsWorker(QThread):
    output = Signal(str)
    done = Signal(bool)

    def __init__(self, host, port, unit_id):
        super().__init__()
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.should_stop = False

    def run(self):
        """Run network diagnostics tests."""
        ok = True
        try:
            # DNS resolution
            self.output.emit(f"Resolving {self.host}...")
            try:
                ip = socket.gethostbyname(self.host)
                self.output.emit(f"DNS OK: {self.host} -> {ip}")
            except socket.gaierror as e:
                self.output.emit(f"DNS FAILED: {e}")
                ok = False
                self.done.emit(ok)
                return

            # TCP connection test
            if self.should_stop:
                self.done.emit(False)
                return
                
            self.output.emit(f"Testing TCP connection to {ip}:{self.port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            try:
                start = time.time()
                sock.connect((ip, self.port))
                rtt = (time.time() - start) * 1000
                self.output.emit(f"TCP OK: Connected in {rtt:.2f}ms")
                sock.close()
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                self.output.emit(f"TCP FAILED: {e}")
                ok = False
                self.done.emit(ok)
                return

            # Optional Modbus test (if pymodbus is available)
            try:
                from core.modbus_client import ModbusClient
                if self.should_stop:
                    self.done.emit(False)
                    return
                    
                self.output.emit("Testing Modbus communication...")
                modbus = ModbusClient(ip, self.port, self.unit_id, timeout=3)
                if modbus.connect():
                    self.output.emit("Modbus OK: Connected successfully")
                    # Try a simple read
                    try:
                        result = modbus.read_registers(0, 1)
                        if result is not None:
                            self.output.emit("Modbus READ OK: Test register read successful")
                        else:
                            self.output.emit("Modbus READ FAILED: No data received")
                    except Exception as e:
                        self.output.emit(f"Modbus READ FAILED: {e}")
                    modbus.disconnect()
                else:
                    self.output.emit("Modbus FAILED: Connection failed")
                    ok = False
            except ImportError:
                self.output.emit("Modbus test skipped: pymodbus not available")
            except Exception as e:
                self.output.emit(f"Modbus FAILED: {e}")
                ok = False

        except Exception as e:
            self.output.emit(f"Unexpected error: {e}")
            ok = False

        self.done.emit(ok)


class NetworkScanner(QThread):
    """Network device scanner for discovering Modbus devices with continuous scanning."""
    
    device_found = Signal(str, str, str)  # ip, port, status
    progress = Signal(int)  # progress percentage
    scan_complete = Signal(int)  # number of devices found
    output = Signal(str)  # status messages
    
    def __init__(self, base_ip, port_range, modbus_port, continuous=False, scan_delay=2):
        super().__init__()
        self.base_ip = base_ip
        self.port_range = port_range
        self.modbus_port = modbus_port
        self.should_stop = False
        self.continuous = continuous  # Enable continuous scanning
        self.scan_delay = scan_delay  # Delay between scan cycles in seconds
        self.discovered_devices = set()  # Track discovered devices (IP addresses)
        
    def run(self):
        """Scan network for Modbus devices."""
        found_devices = 0
        
        # Parse base IP (e.g., 192.168.1.1)
        try:
            parts = self.base_ip.split('.')
            if len(parts) != 4:
                self.output.emit("Error: Invalid IP address format")
                self.scan_complete.emit(0)
                return
                
            network_prefix = '.'.join(parts[:3]) + '.'
            start_ip = int(parts[3])
            
        except ValueError:
            self.output.emit("Error: Invalid IP address format")
            self.scan_complete.emit(0)
            return
        
        self.output.emit(f"Starting network discovery: {network_prefix}{start_ip}-{start_ip + self.port_range - 1}")
        self.output.emit(f"Testing Modbus port {self.modbus_port}...")
        if self.continuous:
            self.output.emit("Continuous scanning enabled. Click 'Stop Scan' to stop.")
        
        total_ips = self.port_range
        scan_cycle = 0
        
        while not self.should_stop:
            scan_cycle += 1
            cycle_new_devices = 0
            
            for i in range(self.port_range):
                if self.should_stop:
                    break
                    
                current_ip = f"{network_prefix}{start_ip + i}"
                progress_percent = int((i / total_ips) * 100)
                self.progress.emit(progress_percent)
                
                # Check flag before network I/O
                if self.should_stop:
                    break
                    
                # Test connection to Modbus port with a short timeout
                if self.test_modbus_connection(current_ip, self.modbus_port, timeout=0.5):
                    # Check if this is a new device
                    if current_ip not in self.discovered_devices:
                        self.discovered_devices.add(current_ip)
                        found_devices += 1
                        cycle_new_devices += 1
                        self.device_found.emit(current_ip, str(self.modbus_port), "Modbus Device Found")
                        self.output.emit(f"✓ New device found: {current_ip}:{self.modbus_port}")
                
                # Small delay to prevent overwhelming the network
                self.msleep(50)  # 50ms delay between individual IP checks
            
            # Report cycle results
            if cycle_new_devices > 0:
                self.output.emit(f"Scan cycle {scan_cycle}: Found {cycle_new_devices} new device(s). Total: {found_devices}")
            
            # If not continuous, break after first cycle
            if not self.continuous:
                break
            
            # If continuous, wait before next cycle
            if not self.should_stop:
                self.output.emit(f"Waiting {self.scan_delay}s before next scan cycle...")
                for _ in range(self.scan_delay * 10):  # Check stop flag every 100ms
                    if self.should_stop:
                        break
                    self.msleep(100)
        
        self.output.emit(f"Scan stopped. Total devices found: {found_devices}")
        self.scan_complete.emit(found_devices)
    
    def test_modbus_connection(self, ip, port, timeout=1):
        """Test if a Modbus device is responding at the given IP and port."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def stop(self):
        """Stop the scanning process."""
        self.should_stop = True


# MAC Address Vendor Database for PLC Manufacturers
MAC_VENDOR_DB = {
    # Siemens
    '08:00:06': 'Siemens AG',
    '00:00:00': 'Siemens AG',
    '08:00:27': 'Siemens AG',
    
    # Rockwell Automation (Allen-Bradley)
    '00:00:bc': 'Rockwell Automation',
    '00:0a:bc': 'Rockwell Automation',
    '00:10:7b': 'Rockwell Automation',
    
    # Schneider Electric
    '00:80:f4': 'Schneider Electric',
    '00:90:f8': 'Schneider Electric',
    '00:bb:2c': 'Schneider Electric',
    
    # Mitsubishi Electric
    '00:00:0e': 'Mitsubishi Electric',
    '00:e0:4c': 'Mitsubishi Electric',
    
    # Omron
    '00:00:7e': 'Omron Corporation',
    '00:0d:bc': 'Omron Corporation',
    
    # ABB
    '00:00:0c': 'ABB Ltd',
    '08:00:69': 'ABB Ltd',
    
    # Honeywell
    '00:00:83': 'Honeywell',
    '00:1d:c1': 'Honeywell',
    
    # Yokogawa
    '00:00:fa': 'Yokogawa Electric',
    '00:e0:29': 'Yokogawa Electric',
    
    # Emerson
    '00:00:4d': 'Emerson Electric',
    '00:1c:23': 'Emerson Electric',
    
    # Bosch Rexroth
    '00:80:25': 'Bosch Rexroth',
    '00:1e:cf': 'Bosch Rexroth',
    
    # Beckhoff
    '00:01:05': 'Beckhoff Automation',
    '00:0d:93': 'Beckhoff Automation',
    
    # WAGO
    '00:30:de': 'WAGO Kontakttechnik',
    '00:11:66': 'WAGO Kontakttechnik',
    
    # Phoenix Contact
    '00:0c:d1': 'Phoenix Contact',
    '00:1b:1b': 'Phoenix Contact',
    
    # B&R
    '00:00:8b': 'B&R Industrial Automation',
    '00:0c:29': 'B&R Industrial Automation',
    
    # Keyence
    '00:00:da': 'Keyence Corporation',
    '00:1c:0f': 'Keyence Corporation',
    
    # SICK AG
    '00:02:54': 'SICK AG',
    '00:80:3f': 'SICK AG',
    
    # Pepperl+Fuchs
    '00:00:9d': 'Pepperl+Fuchs',
    '00:0e:5c': 'Pepperl+Fuchs',
    
    # Turck
    '00:80:6f': 'Hans Turck GmbH',
    '00:0c:0d': 'Hans Turck GmbH',
    
    # IFM Electronic
    '00:00:7a': 'IFM Electronic',
    '00:1e:5f': 'IFM Electronic',
}


def lookup_mac_vendor(mac_address):
    """Lookup vendor by MAC address OUI."""
    # Remove separators and convert to lowercase
    clean_mac = mac_address.replace(':', '').replace('-', '').lower()
    
    # Get first 3 octets (OUI)
    if len(clean_mac) >= 6:
        oui = clean_mac[:6]
        # Format with colons for lookup
        oui_formatted = ':'.join([oui[i:i+2] for i in range(0, 6, 2)])
        return MAC_VENDOR_DB.get(oui_formatted, 'Unknown')
    return 'Unknown'


def is_valid_interface_ipv4(ip_address):
    """Return True for usable adapter IPv4 addresses."""
    try:
        ip = ipaddress.ip_address(ip_address)
    except ValueError:
        return False

    return (
        ip.version == 4
        and not ip.is_unspecified
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and str(ip) != "255.255.255.255"
    )


def format_interface_name(raw_name):
    """Normalize platform adapter section names for display."""
    name = raw_name.strip().rstrip(":")
    match = re.match(r"^(?:Ethernet|Wireless LAN|Bluetooth Network|PPP|Tunnel)\s+adapter\s+(.+)$", name, re.IGNORECASE)
    return match.group(1).strip() if match else name


def normalize_mac_address(mac_address):
    """Normalize a MAC address to AA:BB:CC:DD:EE:FF, or Unknown."""
    if not mac_address:
        return "Unknown"

    match = re.search(r"([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})", mac_address)
    if not match:
        return "Unknown"
    return match.group(0).replace("-", ":").upper()


def build_interface_record(name, ipv4, mac_address="Unknown"):
    """Build the structured interface object consumed by the UI."""
    mac_address = normalize_mac_address(mac_address)
    vendor = lookup_mac_vendor(mac_address) if mac_address != "Unknown" else "Unknown"
    display_name = f"{name} ({ipv4})"
    if vendor != "Unknown":
        display_name += f" - {vendor}"

    return {
        "name": name,
        "display_name": display_name,
        "ipv4": ipv4,
        "ip": ipv4,
        "mac": mac_address,
        "vendor": vendor,
        "status": "active",
    }


def get_network_interfaces_from_psutil():
    """Get active IPv4 network interfaces using psutil."""
    interfaces = []
    if not PSUTIL_AVAILABLE:
        return interfaces

    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()

    for interface_name, addresses in net_if_addrs.items():
        stats = net_if_stats.get(interface_name)
        if stats and not stats.isup:
            continue

        ipv4_addresses = [
            addr.address
            for addr in addresses
            if addr.family == socket.AF_INET and is_valid_interface_ipv4(addr.address)
        ]
        if not ipv4_addresses:
            continue

        mac_address = "Unknown"
        for addr in addresses:
            if getattr(addr, "family", None) == getattr(psutil, "AF_LINK", object()):
                mac_address = addr.address
                break

        interfaces.append(build_interface_record(interface_name, ipv4_addresses[0], mac_address))

    return interfaces


def parse_windows_ipconfig_interfaces(output):
    """Parse active IPv4 interfaces from Windows ipconfig /all output."""
    interfaces = []
    seen_names = set()
    section = None

    adapter_header_re = re.compile(r"^\s*(?P<name>.+?\badapter\b.+?):\s*$", re.IGNORECASE)
    ipv4_re = re.compile(r"IPv4 Address.*?:\s*([\d.]+)", re.IGNORECASE)
    mac_re = re.compile(r"Physical Address.*?:\s*(([0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2})", re.IGNORECASE)

    def flush_section():
        if not section:
            return
        if section["media_disconnected"]:
            return
        if not section["ipv4"]:
            return
        name = section["name"]
        if name in seen_names:
            return
        seen_names.add(name)
        interfaces.append(build_interface_record(name, section["ipv4"], section["mac"]))

    for line in output.splitlines():
        header = adapter_header_re.match(line)
        if header:
            flush_section()
            section = {
                "name": format_interface_name(header.group("name")),
                "ipv4": None,
                "mac": "Unknown",
                "media_disconnected": False,
            }
            continue

        if section is None:
            continue

        if "Media disconnected" in line:
            section["media_disconnected"] = True
            continue

        mac_match = mac_re.search(line)
        if mac_match:
            section["mac"] = mac_match.group(1)
            continue

        ipv4_match = ipv4_re.search(line)
        if ipv4_match:
            candidate_ip = ipv4_match.group(1)
            if is_valid_interface_ipv4(candidate_ip):
                section["ipv4"] = candidate_ip

    flush_section()
    return interfaces


def get_network_interfaces_from_ipconfig():
    """Get active IPv4 network interfaces from Windows ipconfig output."""
    if platform.system().lower() != "windows":
        return []

    result = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return []
    return parse_windows_ipconfig_interfaces(result.stdout)


def get_network_interfaces():
    """Get active network interfaces with valid IPv4 addresses."""
    try:
        interfaces = get_network_interfaces_from_psutil()
    except Exception:
        interfaces = []

    if not interfaces:
        try:
            interfaces = get_network_interfaces_from_ipconfig()
        except Exception:
            interfaces = []

    if not interfaces:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if is_valid_interface_ipv4(local_ip):
                interfaces.append(build_interface_record("Default Interface", local_ip))
        except Exception:
            pass
    
    return interfaces


class PacketCapture(QThread):
    """Advanced packet capture for network analysis like Wireshark."""
    
    packet_captured = Signal(str, str, str, str)  # src_ip, dst_ip, protocol, info
    arp_discovered = Signal(str, str, str)  # ip, mac, vendor
    modbus_detected = Signal(str, str, int)  # src_ip, dst_ip, function
    capture_complete = Signal(int)  # number of packets captured
    output = Signal(str)  # status messages
    progress = Signal(int)  # discovery progress percentage
    
    def __init__(self, interface=None, duration=30, capture_capability=None):
        super().__init__()
        self.interface = interface
        self.duration = duration
        self.capture_capability = capture_capability or detect_packet_capture_capability()
        self.should_stop = False
        self.packet_count = 0
        self.local_ip = None
        self.debug = False
        self.devices = {}
        self._last_progress_bucket = 0
        self.is_windows = platform.system().lower() == 'windows'

    def _debug(self, message):
        if self.debug:
            self.output.emit(message)

    def _normalize_mac(self, mac_address):
        if not mac_address:
            return None
        match = re.fullmatch(r'([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})', mac_address.strip())
        if not match:
            return None
        return mac_address.replace('-', ':').upper()

    def _is_valid_device_ip(self, ip_address):
        try:
            ip = ipaddress.ip_address(ip_address)
        except ValueError:
            return False
        if ip.version != 4:
            return False
        if ip.is_unspecified or ip.is_multicast or str(ip) == "255.255.255.255":
            return False
        first_octet = int(str(ip).split('.', 1)[0])
        if first_octet == 0:
            return False
        return True

    def _register_device(self, ip_address, mac_address):
        if not self._is_valid_device_ip(ip_address):
            self._debug(f"Ignored noisy ARP IP: {ip_address}")
            return False

        normalized_mac = self._normalize_mac(mac_address)
        if normalized_mac is None:
            self._debug(f"Ignored malformed ARP MAC for {ip_address}: {mac_address}")
            return False
        if normalized_mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            self._debug(f"Ignored unusable ARP MAC for {ip_address}: {normalized_mac}")
            return False

        vendor = lookup_mac_vendor(normalized_mac)
        first_seen = self.devices.get(ip_address, {}).get("first_seen", time.time())
        existing = self.devices.get(ip_address)
        changed = existing is None or existing.get("mac") != normalized_mac

        self.devices[ip_address] = {
            "mac": normalized_mac,
            "vendor": vendor,
            "first_seen": first_seen,
        }

        if changed:
            self.arp_discovered.emit(ip_address, normalized_mac, vendor)
        return changed
        
    def run(self):
        """Capture and analyze network packets."""
        try:
            self.output.emit("Capturing ARP traffic...")
            
            if self.is_windows:
                if self.capture_capability.get("advanced"):
                    self.output.emit("Starting advanced ARP sniffing...")
                    self.run_scapy_capture()
                else:
                    self.run_windows_capture()
            else:
                # Linux/Unix packet capture using raw sockets
                self.run_unix_capture()
                
        except Exception as e:
            self.output.emit(f"Capture error: {e}")
            self.capture_complete.emit(0)

    def run_scapy_capture(self):
        """Capture ARP packets with scapy/Npcap when available."""
        self.output.emit("Advanced ARP capture enabled.")
        try:
            from scapy.all import ARP, sniff

            def handle_packet(packet):
                if self.should_stop:
                    return
                if packet.haslayer(ARP):
                    arp_layer = packet[ARP]
                    if int(getattr(arp_layer, "op", 0)) in (1, 2):
                        self._register_device(str(arp_layer.psrc), str(arp_layer.hwsrc))

            sniff(
                filter="arp",
                prn=handle_packet,
                timeout=self.duration,
                store=False,
                stop_filter=lambda x: self.should_stop
            )
            self.capture_complete.emit(len(self.devices))
        except Exception as e:
            self.output.emit(f"Advanced capture failed; using fallback discovery. ({e})")
            self.run_windows_capture()
    
    def run_windows_capture(self):
        """Windows-compatible packet capture using ARP scanning and ping."""
        self.output.emit("Scanning network...")
        
        try:
            # Get local network information
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            self.local_ip = local_ip
            
            # Extract network segment (e.g., 192.168.1.100 -> 192.168.1)
            network_parts = local_ip.split('.')
            if len(network_parts) >= 3:
                network_base = '.'.join(network_parts[:3])
                self.output.emit(f"Scanning network: {network_base}.x")
                
                # Scan network for active devices
                self.scan_network_windows(network_base)
            else:
                self.output.emit("Error: Could not determine network segment")
                
        except Exception as e:
            self.output.emit(f"Windows scan error: {e}")
            
        self.capture_complete.emit(len(self.devices))
    
    def scan_network_windows(self, network_base):
        """Scan network using ping and ARP table on Windows."""
        import ctypes
        from ctypes import wintypes
        
        # Windows ARP table structures
        class MIB_IPNETROW(ctypes.Structure):
            _fields_ = [
                ('dwIndex', wintypes.DWORD),
                ('dwPhysAddrLen', wintypes.DWORD),
                ('bPhysAddr', wintypes.BYTE * 8),
                ('dwAddr', wintypes.DWORD),
                ('dwType', wintypes.DWORD)
            ]
        
        # Get ARP table
        try:
            arp_table = (MIB_IPNETROW * 100)()
            size = wintypes.DWORD(ctypes.sizeof(arp_table))
            
            # Call Windows API to get ARP table
            iphlpapi = ctypes.windll.iphlpapi
            result = iphlpapi.GetIpNetTable(arp_table, ctypes.byref(size), False)
            
            if result == 0:  # NO_ERROR
                # Parse ARP table
                table_size = size.value // ctypes.sizeof(MIB_IPNETROW)
                for i in range(min(table_size, 100)):
                    row = arp_table[i]
                    if row.dwPhysAddrLen > 0:
                        # Convert IP address
                        ip_addr = socket.inet_ntoa(struct.pack('!I', row.dwAddr))
                        
                        # Convert MAC address
                        mac_bytes = bytes(row.bPhysAddr[:row.dwPhysAddrLen])
                        mac_str = ':'.join(f'{b:02x}' for b in mac_bytes)
                        
                        self._register_device(ip_addr, mac_str)
                        
                        # Check if this might be a Modbus device
                        if self.check_modbus_device_windows(ip_addr):
                            self.modbus_detected.emit(ip_addr, self.local_ip or "", 1)  # Assume read coils
                        
            else:
                self.output.emit("Could not access ARP table. Trying alternative method...")
                self.fallback_network_scan(network_base)
                
        except Exception as e:
            self.output.emit(f"ARP table access failed: {e}")
            self.fallback_network_scan(network_base)
    
    def fallback_network_scan(self, network_base):
        """Fallback network scan using ping for Windows."""
        self.output.emit("Using ping-based network discovery...")
        
        for i in range(1, 255):
            if self.should_stop:
                break
                
            # Calculate and emit progress for percentage mode
            self.progress.emit(int((i / 254) * 100))
                
            ip = f"{network_base}.{i}"
            
            # Ping the host
            try:
                result = subprocess.run(
                    ['ping', '-n', '1', '-w', '1000', ip],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    # Host is alive, try to get MAC via ARP
                    mac = self.get_mac_via_arp_windows(ip)
                    self._register_device(ip, mac)
                    
                    # Check for Modbus
                    if self.check_modbus_device_windows(ip):
                        self.modbus_detected.emit(ip, ip, 1)
                        
                # Update progress
                progress = int((i / 254) * 100)
                self.progress.emit(progress)
                bucket = (progress // 25) * 25
                if bucket in (25, 50, 75, 100) and bucket > self._last_progress_bucket:
                    self._last_progress_bucket = bucket
                    self.output.emit(f"Scanning network... {bucket}%")
                
                # Small delay to prevent overwhelming network
                self.msleep(50)
                
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
    
    def get_mac_via_arp_windows(self, ip):
        """Get MAC address for IP using ARP command on Windows."""
        try:
            result = subprocess.run(
                ['arp', '-a', ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Parse ARP output for MAC address
                for line in result.stdout.split('\n'):
                    if ip in line:
                        # Extract MAC address (format: 00-11-22-33-44-55)
                        import re
                        mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})', line)
                        if mac_match:
                            mac = mac_match.group(0)
                            # Convert to consistent format
                            return mac.replace('-', ':').upper()
            
        except Exception:
            pass
        
        return None
    
    def check_modbus_device_windows(self, ip):
        """Check if device at IP might be a Modbus device."""
        try:
            # Try to connect to Modbus port (502)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((ip, 502))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def run_unix_capture(self):
        """Unix/Linux packet capture using raw sockets."""
        try:
            # Create raw socket for packet capture
            self.raw_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0003))
            self.output.emit("Listening for ARP traffic...")
            
            start_time = time.time()
            
            while not self.should_stop and (time.time() - start_time) < self.duration:
                try:
                    # Receive packet
                    packet, addr = self.raw_socket.recvfrom(65536)
                    self.packet_count += 1
                    
                    # Parse Ethernet header
                    if len(packet) >= 14:
                        eth_header = packet[:14]
                        eth_protocol = struct.unpack('!H', eth_header[12:14])[0]
                        
                        # ARP packet
                        if eth_protocol == 0x0806:
                            self.parse_arp_packet(packet[14:], addr[0])
                        
                        # IPv4 packet
                        elif eth_protocol == 0x0800:
                            self.parse_ipv4_packet(packet[14:], addr[0])
                    
                    if self.packet_count % 100 == 0:
                        elapsed = time.time() - start_time
                        self._debug(f"Captured {self.packet_count} packets in {elapsed:.1f}s...")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    self.output.emit(f"Error processing packet: {e}")
                    continue
            
            self.raw_socket.close()
            self.capture_complete.emit(len(self.devices))
            
        except PermissionError:
            self.output.emit("Error: Requires administrator privileges for packet capture")
            self.capture_complete.emit(0)
        except Exception as e:
            self.output.emit(f"Error creating socket: {e}")
            self.capture_complete.emit(0)
    
    def parse_arp_packet(self, arp_data, interface):
        """Parse ARP packet to discover devices."""
        try:
            if len(arp_data) >= 28:  # Minimum ARP packet size
                arp_proto_type = struct.unpack('!H', arp_data[2:4])[0]
                arp_opcode = struct.unpack('!H', arp_data[6:8])[0]

                if arp_proto_type == 0x0800 and arp_opcode in (1, 2):
                    sender_mac = ':'.join(f'{arp_data[i + 8]:02x}' for i in range(6))
                    sender_ip = socket.inet_ntoa(arp_data[14:18])
                    self._register_device(sender_ip, sender_mac)

        except Exception:
            pass  # Silently ignore ARP parsing errors
    
    def parse_ipv4_packet(self, ip_data, interface):
        """Parse IPv4 packet for Modbus traffic."""
        try:
            if len(ip_data) >= 20:
                # IP header
                ip_header = struct.unpack('!BBHHHBBH4s4s', ip_data[:20])
                ip_proto = ip_header[6]
                src_ip = socket.inet_ntoa(ip_data[12:16])
                dst_ip = socket.inet_ntoa(ip_data[16:20])
                
                # TCP packet
                if ip_proto == 6 and len(ip_data) >= 40:
                    tcp_data = ip_data[20:]
                    if len(tcp_data) >= 20:
                        tcp_header = struct.unpack('!HHLLBBHHH', tcp_data[:20])
                        src_port = tcp_header[0]
                        dst_port = tcp_header[1]
                        
                        # Check for Modbus traffic (port 502)
                        if src_port == 502 or dst_port == 502:
                            # Try to extract Modbus function code
                            if len(tcp_data) > 20:
                                modbus_data = tcp_data[20:]
                                if len(modbus_data) >= 8:
                                    # Modbus TCP header + function
                                    modbus_func = modbus_data[7]
                                    self.modbus_detected.emit(src_ip, dst_ip, modbus_func)
                                    self._debug(f"Modbus: {src_ip}:{src_port} -> {dst_ip}:{dst_port} (Function: {modbus_func})")
                                
                        self.packet_captured.emit(src_ip, dst_ip, 'TCP', f"{src_port}->{dst_port}")
                    
                # UDP packet
                elif ip_proto == 17:
                    self.packet_captured.emit(src_ip, dst_ip, 'UDP', 'Data')
                    
        except Exception:
            pass  # Silently ignore IP parsing errors
    
    def stop(self):
        """Stop packet capture."""
        self.should_stop = True
        if hasattr(self, 'raw_socket'):
            try:
                self.raw_socket.close()
            except Exception:
                pass


class NetworkDiagnosticsDialog:
    """Network diagnostics dialog functionality."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.dialog = None
        self.worker = None
        self.scanner = None
        self.capturer = None
        self.modbus_prober = None
        self.output_text = None
        self.discovered_devices = []
        self.captured_packets = []
        self.arp_devices = {}
        self.selected_interface = None
        self.interfaces = []
        self.capture_capability = None  # Will be checked on each dialog open
        self.npcap_notice_shown = False
        self.npcap_notice_dialog = None
        self.capture_mode_label = None
        self.modbus_devices = {}  # Store Modbus probe results: {ip: status}
        self.show_modbus_only = False  # Filter checkbox state
        self.subnet_info = None  # Local subnet information

    def show_diagnostics(self, host, port, unit_id):
        """Show network diagnostics dialog."""
        if self.dialog is None:
            self.dialog = QDialog(self.parent)
            self.dialog.setWindowTitle("Network Discovery & Diagnostics")
            self.dialog.setGeometry(300, 300, 600, 600)
            
            # Override close event to stop all scanning
            self.dialog.closeEvent = self.on_dialog_close

            layout = QVBoxLayout(self.dialog)
            
            # Network Interface Selection
            interface_layout = QHBoxLayout()
            interface_layout.addWidget(QLabel("Network Interface:"))
            
            self.interface_combo = QComboBox()
            self.interface_combo.setMinimumWidth(300)
            self.interface_combo.setStyleSheet("""
                QComboBox {
                    padding: 5px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }
            """)
            
            # Populate network interfaces
            self.interfaces = get_network_interfaces()
            for interface in self.interfaces:
                self.interface_combo.addItem(interface['display_name'], interface['name'])
            self.interface_combo.setEnabled(bool(self.interfaces))
            
            self.interface_combo.currentTextChanged.connect(self.on_interface_changed)
            interface_layout.addWidget(self.interface_combo)
            
            # Refresh button for interfaces
            refresh_btn = QPushButton("Refresh")
            refresh_btn.setStyleSheet(self.parent._get_button_style())
            refresh_btn.clicked.connect(self.refresh_interfaces)
            refresh_btn.setMaximumWidth(80)
            interface_layout.addWidget(refresh_btn)
            
            layout.addLayout(interface_layout)

            # Re-check packet capture capability on each dialog open (no caching)
            self.capture_capability = detect_packet_capture_capability()
            
            self.capture_mode_label = QLabel(self.capture_capability["label"])
            self.capture_mode_label.setStyleSheet("""
                QLabel {
                    color: #333333;
                    background-color: #F1F3F5;
                    border: 1px solid #D0D0D0;
                    padding: 6px;
                    font-size: 12px;
                }
            """)
            layout.addWidget(self.capture_mode_label)
            
            # Install Npcap button (always visible, state-aware)
            mode_layout = QHBoxLayout()
            mode_layout.addStretch()
            
            self.install_npcap_btn = QPushButton("Install Npcap")
            self.install_npcap_btn.setStyleSheet(self.parent._get_button_style())  # Use normal button style
            
            # Set button state based on actual pcap availability
            if self.capture_capability.get("pcap_available"):
                self.install_npcap_btn.setEnabled(False)
                self.install_npcap_btn.setToolTip("Packet capture backend is available")
            else:
                self.install_npcap_btn.setEnabled(True)
                self.install_npcap_btn.setToolTip("Required for advanced ARP packet capture")
                self.install_npcap_btn.clicked.connect(self.show_npcap_installation_guide)
            
            mode_layout.addWidget(self.install_npcap_btn)
            
            layout.addLayout(mode_layout)
            
            # Update Install Npcap button state based on capability
            self.update_install_npcap_button_state()
            
            # Input fields for IP and Port
            input_layout = QHBoxLayout()
            
            # IP Address input
            input_layout.addWidget(QLabel("IP Address:"))
            self.ip_input = QLineEdit(host)
            self.ip_input.setPlaceholderText("Enter IP address (e.g., 192.168.1.100)")
            self.ip_input.setStyleSheet("""
                QLineEdit {
                    padding: 5px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)
            input_layout.addWidget(self.ip_input)
            
            # Port input
            input_layout.addWidget(QLabel("Port:"))
            self.port_input = QSpinBox()
            self.port_input.setRange(1, 65535)
            self.port_input.setValue(port)
            self.port_input.setStyleSheet("""
                QSpinBox {
                    padding: 5px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    font-size: 12px;
                }
            """)
            input_layout.addWidget(self.port_input)
            
            layout.addLayout(input_layout)
            
            # Progress bar for device discovery
            self.progress_bar = QProgressBar()
            self.progress_bar.setVisible(False)
            self.progress_bar.setStyleSheet("""
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    text-align: center;
                    font-size: 11px;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    border-radius: 3px;
                }
            """)
            layout.addWidget(self.progress_bar)

            # Output text
            self.output_text = QTextEdit()
            self.output_text.setReadOnly(True)
            self.output_text.setStyleSheet("""
                QTextEdit {
                    background-color: #f8f9fa;
                    color: #333333;
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    padding: 10px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 12px;
                }
            """)
            layout.addWidget(self.output_text)

            # Buttons
            button_layout = QHBoxLayout()
            self.test_btn = QPushButton("Run Tests")
            self.test_btn.setStyleSheet(self.parent._get_button_style())
            self.test_btn.clicked.connect(lambda: self.run_tests())
            button_layout.addWidget(self.test_btn)
            
            self.discover_btn = QPushButton("Discover Devices")
            self.discover_btn.setStyleSheet(self.parent._get_button_style())
            self.discover_btn.clicked.connect(lambda: self.discover_devices())
            button_layout.addWidget(self.discover_btn)
            
            self.capture_btn = QPushButton("ARP Mode")
            self.capture_btn.setStyleSheet(self.parent._get_button_style())
            self.capture_btn.clicked.connect(lambda: self.capture_packets())
            button_layout.addWidget(self.capture_btn)
            
            self.stop_btn = QPushButton("Stop Scan")
            self.stop_btn.setStyleSheet(self.parent._get_button_style())
            self.stop_btn.clicked.connect(lambda: self.stop_scan())
            self.stop_btn.setEnabled(False)
            button_layout.addWidget(self.stop_btn)

            # Modbus filter checkbox (disabled by default, enabled during ARP mode)
            self.modbus_filter_checkbox = QCheckBox("Show only Modbus devices")
            self.modbus_filter_checkbox.setEnabled(False)  # Disabled by default
            self.modbus_filter_checkbox.stateChanged.connect(self.on_modbus_filter_changed)
            button_layout.addWidget(self.modbus_filter_checkbox)

            # Clear Results button
            self.clear_results_btn = QPushButton("Clear Results")
            self.clear_results_btn.setStyleSheet(self.parent._get_button_style())
            self.clear_results_btn.clicked.connect(self.clear_results)
            button_layout.addWidget(self.clear_results_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
    
    def show_npcap_installation_guide(self):
        """Show Npcap installation guidance popup before opening download page."""
        dialog = QDialog(self.dialog)
        dialog.setWindowTitle("Npcap Required for Advanced Network Features")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        message = QLabel(
            "This application requires Npcap for advanced packet capture (ARP scanning).\n\n"
            "Follow these steps:\n\n"
            "1. Click \"Open Download Page\"\n"
            "2. Download Npcap for Windows\n"
            "3. Run the installer\n"
            "4. During installation:\n"
            "   - Enable \"Install Npcap in WinPcap API-compatible Mode\"\n"
            "   - Enable \"Support raw 802.11 traffic (optional but recommended)\"\n"
            "5. Complete the installation\n"
            "6. Restart this application after installation"
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        open_btn = QPushButton("Open Download Page")
        open_btn.setMinimumWidth(140)
        open_btn.clicked.connect(lambda: webbrowser.open(NPCAP_DOWNLOAD_URL))
        open_btn.clicked.connect(dialog.accept)
        buttons.addWidget(open_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(dialog.reject)
        buttons.addWidget(cancel_btn)
        
        layout.addLayout(buttons)
        dialog.exec()
    
    def on_dialog_close(self, event):
        """Handle dialog close event - stop all scanning."""
        # Stop all active scanning processes
        self.stop_all_scanning()
        
        # Accept the close event
        event.accept()
    
    def stop_all_scanning(self):
        """Stop all scanning processes (shared stop logic)."""
        try:
            # Stop packet capture
            if self.capturer and self.capturer.isRunning():
                self.capturer.stop()
                self.capturer.wait()
            
            # Stop device scanner
            if self.scanner and self.scanner.isRunning():
                self.scanner.stop()
                self.scanner.wait()
            
            # Stop Modbus prober
            if self.modbus_prober and self.modbus_prober.isRunning():
                self.modbus_prober.stop()
                self.modbus_prober.wait()
            
            # Stop diagnostics worker
            if self.worker and self.worker.isRunning():
                self.worker.should_stop = True
                self.worker.quit()
                self.worker.wait()
            
            # Disable Modbus filter
            self.disable_modbus_filter()
            
            # Reset progress bar
            self.progress_bar.setVisible(False)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            
            # Re-enable buttons
            self.capture_btn.setEnabled(True)
            self.capture_btn.setText("Capture Packets")
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Run Tests")
            self.discover_btn.setEnabled(True)
            self.discover_btn.setText("Discover Devices")
            self.stop_btn.setEnabled(False)
            
        except Exception as e:
            # Log error but don't prevent close
            pass
    
    def on_modbus_filter_changed(self, state):
        """Handle Modbus filter checkbox change."""
        self.show_modbus_only = (state == 2)  # Qt.Checked is 2
        # Refresh the display if we have results
        if self.arp_devices:
            self.display_arp_results()
    
    def clear_results(self):
        """Clear all displayed results without resetting configuration."""
        self.output_text.clear()
        self.arp_devices.clear()
        self.modbus_devices.clear()
        self.captured_packets.clear()
        self.discovered_devices.clear()
        
        # Disable and reset Modbus filter
        self.modbus_filter_checkbox.setEnabled(False)
        self.modbus_filter_checkbox.setChecked(False)
        self.show_modbus_only = False
        
        self.output_text.append("Results cleared.")
    
    def enable_modbus_filter(self):
        """Enable Modbus filter checkbox when ARP mode is active."""
        self.modbus_filter_checkbox.setEnabled(True)
    
    def disable_modbus_filter(self):
        """Disable and reset Modbus filter checkbox when ARP mode is inactive."""
        self.modbus_filter_checkbox.setEnabled(False)
        self.modbus_filter_checkbox.setChecked(False)
        self.show_modbus_only = False
        # Refresh display to show all devices
        if self.arp_devices:
            self.display_arp_results()
    
    def display_arp_results(self):
        """Display ARP discovery results with Modbus status."""
        self.output_text.append("\n=== DISCOVERED DEVICES ===")
        
        if not self.arp_devices:
            self.output_text.append("No valid ARP devices found.")
            self.output_text.append("\nTotal unique devices: 0")
            return
        
        # Filter devices based on Modbus filter
        devices_to_display = []
        for ip, device in self.arp_devices.items():
            modbus_status = self.modbus_devices.get(ip, "UNKNOWN")
            
            # Apply filter if enabled
            if self.show_modbus_only and modbus_status != "YES":
                continue
            
            devices_to_display.append((ip, device, modbus_status))
        
        if not devices_to_display:
            self.output_text.append("No devices match the current filter.")
            return
        
        # Sort by IP
        sorted_devices = sorted(
            devices_to_display,
            key=lambda item: tuple(int(part) for part in item[0].split("."))
        )
        
        for index, (ip, device, modbus_status) in enumerate(sorted_devices, start=1):
            self.output_text.append(
                f"{index}. IP: {ip} | MAC: {device['mac']} | Vendor: {device['vendor']} | Modbus: {modbus_status}"
            )
        
        self.output_text.append(f"\nTotal displayed devices: {len(sorted_devices)}")
        
        # Check for subnet mismatches and show guidance
        subnet_mismatches = [ip for ip, _, status in sorted_devices if "Subnet mismatch" in status]
        if subnet_mismatches:
            self.output_text.append("\nNote: Some devices are on a different subnet.")
            self.output_text.append("Consider changing your PC IP to match the device network.")
    
    def on_modbus_probe_complete(self, ip, status):
        """Handle Modbus probe completion for a single device."""
        self.modbus_devices[ip] = status
        # Update progress bar
        if self.progress_bar.isVisible():
            current_val = self.progress_bar.value()
            self.progress_bar.setValue(current_val + 1)
    
    def on_modbus_probing_complete(self):
        """Handle completion of all Modbus probes."""
        self.output_text.append("Modbus probing complete.")
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)
        # Enable Modbus filter after probing is complete
        self.enable_modbus_filter()
        self.display_arp_results()
    
    def on_interface_changed(self, display_name):
        """Handle network interface selection change."""
        # Find the selected interface
        for interface in self.interfaces:
            if interface['display_name'] == display_name:
                self.selected_interface = interface
                self.ip_input.setText(interface['ipv4'])
                self.output_text.append(f"Selected interface: {interface['name']} - {interface['ipv4']}")
                break
    
    def update_install_npcap_button_state(self):
        """Update Install Npcap button state based on actual pcap availability."""
        if self.install_npcap_btn and self.capture_capability:
            if self.capture_capability.get("pcap_available"):
                # pcap is working, disable button
                self.install_npcap_btn.setEnabled(False)
                self.install_npcap_btn.setToolTip("Packet capture backend is available")
            else:
                # pcap is not working, enable button
                self.install_npcap_btn.setEnabled(True)
                self.install_npcap_btn.setToolTip("Required for advanced ARP packet capture")
    
    def refresh_interfaces(self):
        """Refresh the list of network interfaces and re-check packet capture capability."""
        try:
            # Re-check packet capture capability on refresh
            self.capture_capability = detect_packet_capture_capability()
            if self.capture_mode_label:
                self.capture_mode_label.setText(self.capture_capability["label"])
            
            # Update Install Npcap button state
            self.update_install_npcap_button_state()
            
            # Log detection results for debugging
            self.output_text.append(f"Packet capture capability check:")
            self.output_text.append(f"  - Scapy available: {self.capture_capability.get('scapy_available')}")
            self.output_text.append(f"  - pcap backend available: {self.capture_capability.get('pcap_available')}")
            self.output_text.append(f"  - Interfaces available: {self.capture_capability.get('interfaces_available')}")
            self.output_text.append(f"  - Mode: {self.capture_capability['label']}")
            
            # Save current selection
            current_name = self.interface_combo.currentText()
            
            # Refresh interfaces
            self.interfaces = get_network_interfaces()
            
            # Update combo box
            self.interface_combo.clear()
            for interface in self.interfaces:
                self.interface_combo.addItem(interface['display_name'], interface['name'])
            self.interface_combo.setEnabled(bool(self.interfaces))
            
            # Try to restore previous selection
            index = self.interface_combo.findText(current_name)
            if index >= 0:
                self.interface_combo.setCurrentIndex(index)
            
            self.output_text.append(f"Network interfaces refreshed. Found {len(self.interfaces)} interfaces.")
            
        except Exception:
            self.output_text.append("Network interface refresh not available")

    def show_npcap_notice_once(self):
        """Show a one-time non-modal notice when advanced ARP capture is unavailable."""
        # Check if advanced packet capture is actually available
        if self.capture_capability.get("advanced") or self.npcap_notice_shown:
            return

        self.npcap_notice_shown = True
        failure_reason = self.capture_capability.get("failure_reason", "Unknown")
        
        # Build reason-specific message
        if failure_reason == "Npcap not installed":
            message = (
                "Real-time ARP packet capture requires Npcap.\n\n"
                "The application will continue using a fallback discovery method.\n\n"
                f"Download Npcap: {NPCAP_DOWNLOAD_URL}"
            )
            show_download_button = True
        elif failure_reason == "Scapy not installed":
            message = (
                "Real-time ARP packet capture requires Scapy.\n\n"
                "The application will continue using a fallback discovery method.\n\n"
                "Install Scapy using: pip install scapy"
            )
            show_download_button = False
        elif failure_reason == "No capture interfaces available":
            message = (
                "No capture interfaces are available for packet capture.\n\n"
                "The application will continue using a fallback discovery method.\n\n"
                "Please check your network adapter settings."
            )
            show_download_button = False
        else:
            message = (
                "Real-time ARP packet capture is not available.\n\n"
                f"Reason: {failure_reason}\n\n"
                "The application will continue using a fallback discovery method."
            )
            show_download_button = False

        dialog = QDialog(self.dialog)
        dialog.setWindowTitle("Advanced ARP Capture Not Available")
        dialog.setModal(False)
        dialog.setMinimumWidth(520)

        layout = QVBoxLayout(dialog)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setOpenExternalLinks(True)
        layout.addWidget(message_label)

        buttons = QHBoxLayout()
        buttons.addStretch()

        # Continue button (default, first as per requirements)
        continue_btn = QPushButton("Continue")
        continue_btn.setDefault(True)
        continue_btn.setMinimumWidth(100)
        continue_btn.clicked.connect(dialog.accept)
        buttons.addWidget(continue_btn)

        # Open Download Page button (only for Npcap missing)
        if show_download_button:
            open_btn = QPushButton("Open Download Page")
            open_btn.setMinimumWidth(140)
            open_btn.clicked.connect(lambda: webbrowser.open(NPCAP_DOWNLOAD_URL))
            buttons.addWidget(open_btn)

        layout.addLayout(buttons)
        self.npcap_notice_dialog = dialog
        dialog.show()

    def run_tests(self):
        """Run network diagnostics tests using user-provided IP and port."""
        if self.worker and self.worker.isRunning():
            return
        
        # Disable Modbus filter when starting tests (different mode)
        self.disable_modbus_filter()
        
        # Get user-provided IP and port
        host = self.ip_input.text().strip()
        port = self.port_input.value()
        unit_id = 1  # Default unit ID for diagnostics
        
        # Validate IP address
        if not host:
            self.output_text.setText("Error: Please enter an IP address")
            return

        self.output_text.clear()
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing...")

        self.worker = NetworkDiagnosticsWorker(host, port, unit_id)
        self.worker.output.connect(self.output_text.append)
        self.worker.done.connect(self.on_tests_done)
        self.worker.start()
    
    def discover_devices(self):
        """Start network device discovery."""
        if self.scanner and self.scanner.isRunning():
            return
        
        # Check packet capture capability and show popup if needed
        self.capture_capability = detect_packet_capture_capability()
        if self.capture_mode_label:
            self.capture_mode_label.setText(self.capture_capability["label"])
        self.show_npcap_notice_once()
        
        # Get user-provided IP and port
        host = self.ip_input.text().strip()
        port = self.port_input.value()
        
        # Validate IP address
        if not host:
            self.output_text.setText("Error: Please enter an IP address")
            return
        
        # Parse IP to get base network (e.g., 192.168.1.1 -> 192.168.1.0)
        try:
            parts = host.split('.')
            if len(parts) != 4:
                self.output_text.setText("Error: Invalid IP address format")
                return
            
            # Use the first 3 octets and set last to 0 for network base
            base_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.0"
            
        except ValueError:
            self.output_text.setText("Error: Invalid IP address format")
            return
        
        self.output_text.clear()
        self.discovered_devices.clear()
        self.modbus_devices.clear()  # Clear previous Modbus probe results
        
        # Get local subnet info for Modbus probing
        self.subnet_info = get_local_subnet_info()
        
        # Show progress bar and disable buttons
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.discover_btn.setEnabled(False)
        self.discover_btn.setText("Scanning...")
        self.test_btn.setEnabled(False)
        
        # Start scanner (scan 254 addresses in the network with continuous scanning)
        self.scanner = NetworkScanner(base_ip, 254, port, continuous=True, scan_delay=2)
        self.scanner.device_found.connect(self.on_device_found)
        self.scanner.progress.connect(self.on_scan_progress)
        self.scanner.output.connect(self.output_text.append)
        self.scanner.scan_complete.connect(self.on_scan_complete)
        self.scanner.start()
        
        # Enable stop button
        self.stop_btn.setEnabled(True)
    
    def on_device_found(self, ip, port, status):
        """Handle device discovery and trigger Modbus probing for new devices."""
        self.discovered_devices.append((ip, port, status))
        
        # Trigger Modbus probing for newly discovered devices (only once per device)
        if ip not in self.modbus_devices:
            self.probe_modbus_for_device(ip, int(port))
    
    def probe_modbus_for_device(self, ip, port):
        """Probe a single device for Modbus capability."""
        try:
            # Check subnet first
            if not is_ip_in_subnet(ip, self.subnet_info):
                self.modbus_devices[ip] = "UNREACHABLE (Subnet mismatch)"
                return
            
            # Probe the device
            status = probe_modbus_device(ip, port, timeout=1.0)
            self.modbus_devices[ip] = status
            
            # Log result
            if status == "YES":
                self.output_text.append(f"  → Modbus device confirmed: {ip}")
            elif status == "NO":
                self.output_text.append(f"  → Not a Modbus device: {ip}")
            else:
                self.output_text.append(f"  → Modbus probe: {ip} - {status}")
            
        except Exception as e:
            self.modbus_devices[ip] = "ERROR"
            self.output_text.append(f"  → Modbus probe error for {ip}: {e}")
    
    def on_scan_progress(self, percentage):
        """Update scan progress."""
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(f"Scanning... {percentage}%")
    
    def on_scan_complete(self, device_count):
        """Handle scan completion."""
        self.progress_bar.setVisible(False)
        self.discover_btn.setEnabled(True)
        self.discover_btn.setText("Discover Devices")
        self.test_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # Disable stop button when complete
        
        if device_count > 0:
            self.output_text.append(f"\n=== DISCOVERED DEVICES ===")
            for ip, port, status in self.discovered_devices:
                self.output_text.append(f"• {ip}:{port} - {status}")
                
            # Auto-fill first discovered device
            first_device = self.discovered_devices[0]
            self.ip_input.setText(first_device[0])
            self.port_input.setValue(int(first_device[1]))
            self.output_text.append(f"\nAuto-filled IP and port with first discovered device")
    
    def capture_packets(self):
        """Start packet capture for network analysis."""
        if self.capturer and self.capturer.isRunning():
            return

        # Disable Modbus filter when starting capture (different mode)
        self.disable_modbus_filter()

        self.capture_capability = detect_packet_capture_capability()
        if self.capture_mode_label:
            self.capture_mode_label.setText(self.capture_capability["label"])
        self.show_npcap_notice_once()
        
        self.output_text.clear()
        self.captured_packets.clear()
        self.arp_devices.clear()
        
        # Show progress bar and disable buttons
        self.progress_bar.setVisible(True)
        if self.capture_capability.get("advanced"):
            # For advanced sniffing, we don't know the "total", so use indeterminate
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("Sniffing network traffic...")
        else:
            # For fallback scanning, use 0-100%
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
        
        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing...")
        self.test_btn.setEnabled(False)
        self.discover_btn.setEnabled(False)
        
        # Start packet capture (30 seconds)
        interface_name = self.selected_interface["name"] if self.selected_interface else None
        self.capturer = PacketCapture(
            interface=interface_name,
            duration=30,
            capture_capability=self.capture_capability,
        )
        self.capturer.packet_captured.connect(self.on_packet_captured)
        self.capturer.arp_discovered.connect(self.on_arp_discovered)
        self.capturer.progress.connect(self.on_scan_progress)
        self.capturer.modbus_detected.connect(self.on_modbus_detected)
        self.capturer.output.connect(self.output_text.append)
        self.capturer.capture_complete.connect(self.on_capture_complete)
        self.capturer.start()
        
        # Enable stop button
        self.stop_btn.setEnabled(True)
    
    def stop_scan(self):
        """Stop any ongoing scan or capture."""
        self.stop_all_scanning()
        self.output_text.append("Scan stopped.")
    
    def on_packet_captured(self, src_ip, dst_ip, protocol, info):
        """Handle captured packet."""
        self.captured_packets.append((src_ip, dst_ip, protocol, info))
    
    def on_arp_discovered(self, ip, mac, vendor):
        """Handle ARP device discovery."""
        first_seen = self.arp_devices.get(ip, {}).get("first_seen", time.time())
        self.arp_devices[ip] = {
            "mac": mac,
            "vendor": vendor or "Unknown",
            "first_seen": first_seen,
        }
    
    def on_modbus_detected(self, src_ip, dst_ip, function):
        """Handle Modbus traffic detection."""
        self.captured_packets.append((src_ip, dst_ip, "Modbus", str(function)))
    
    def on_capture_complete(self, packet_count):
        """Handle packet capture completion."""
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 100)  # Reset to default range
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("Capture Packets")
        self.test_btn.setEnabled(True)
        self.discover_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # Disable stop button when complete
        
        # Start Modbus probing after ARP discovery
        if self.arp_devices:
            self.start_modbus_probing()
        else:
            self.output_text.append("\n=== DISCOVERED DEVICES ===")
            self.output_text.append("No valid ARP devices found.")
            self.output_text.append("\nTotal unique devices: 0")
    
    def start_modbus_probing(self):
        """Start Modbus probing for discovered devices."""
        # Get local subnet info
        self.subnet_info = get_local_subnet_info()
        
        # Prepare device list for probing
        device_list = [(ip, device['mac'], device['vendor']) for ip, device in self.arp_devices.items()]
        
        # Start Modbus probe worker
        self.modbus_prober = ModbusProbeWorker(
            devices=device_list,
            subnet_info=self.subnet_info,
            port=502,
            timeout=1.0
        )
        self.modbus_prober.probe_complete.connect(self.on_modbus_probe_complete)
        self.modbus_prober.all_probes_complete.connect(self.on_modbus_probing_complete)
        self.modbus_prober.output.connect(self.output_text.append)
        self.modbus_prober.start()
        
        # Update progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(device_list))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Probing Modbus devices...")

    def on_tests_done(self, ok):
        """Handle test completion."""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Run Tests")
        if ok:
            self.output_text.append("\nAll tests completed successfully!")
        else:
            self.output_text.append("\nSome tests failed. Check the output above.")
