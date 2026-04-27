import socket
import time
import threading
import struct
import binascii
import re
import platform
import subprocess
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QTextEdit, QLineEdit, QLabel, QSpinBox, QProgressBar, QComboBox


class NetworkDiagnosticsWorker(QThread):
    output = Signal(str)
    done = Signal(bool)

    def __init__(self, host, port, unit_id):
        super().__init__()
        self.host = host
        self.port = port
        self.unit_id = unit_id

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
                self.output.emit("Testing Modbus communication...")
                modbus = ModbusClient(ip, self.port, self.unit_id, timeout=3)
                if modbus.connect():
                    self.output.emit("Modbus OK: Connected successfully")
                    # Try a simple read
                    try:
                        result = modbus.read_holding_registers(0, 1)
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
    """Network device scanner for discovering Modbus devices."""
    
    device_found = Signal(str, str, str)  # ip, port, status
    progress = Signal(int)  # progress percentage
    scan_complete = Signal(int)  # number of devices found
    output = Signal(str)  # status messages
    
    def __init__(self, base_ip, port_range, modbus_port):
        super().__init__()
        self.base_ip = base_ip
        self.port_range = port_range
        self.modbus_port = modbus_port
        self.should_stop = False
        
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
        
        self.output.emit(f"Scanning network: {network_prefix}{start_ip}-{start_ip + self.port_range - 1}")
        self.output.emit(f"Testing Modbus port {self.modbus_port}...")
        
        total_ips = self.port_range
        
        for i in range(self.port_range):
            if self.should_stop:
                break
                
            current_ip = f"{network_prefix}{start_ip + i}"
            progress_percent = int((i / total_ips) * 100)
            self.progress.emit(progress_percent)
            
            # Test connection to Modbus port
            if self.test_modbus_connection(current_ip, self.modbus_port):
                found_devices += 1
                self.device_found.emit(current_ip, str(self.modbus_port), "Modbus Device Found")
                self.output.emit(f"✓ Device found: {current_ip}:{self.modbus_port}")
            
            # Small delay to prevent overwhelming the network
            self.msleep(50)  # 50ms delay between scans
        
        self.output.emit(f"Scan complete. Found {found_devices} devices.")
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


def get_network_interfaces():
    """Get list of available network interfaces."""
    interfaces = []
    
    if PSUTIL_AVAILABLE:
        try:
            # Use psutil to get network interfaces
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            
            for interface_name, addresses in net_if_addrs.items():
                # Get interface stats
                stats = net_if_stats.get(interface_name)
                if stats and stats.isup:  # Only include active interfaces
                    # Get IPv4 addresses for this interface
                    ipv4_addresses = []
                    for addr in addresses:
                        if addr.family == socket.AF_INET:
                            ipv4_addresses.append(addr.address)
                    
                    if ipv4_addresses:  # Only include interfaces with IPv4 addresses
                        # Get MAC address
                        mac_address = 'Unknown'
                        for addr in addresses:
                            if hasattr(addr, 'family') and addr.family == psutil.AF_LINK:
                                mac_address = addr.address
                                break
                        
                        # Format display name
                        display_name = f"{interface_name} ({ipv4_addresses[0]})"
                        if mac_address != 'Unknown':
                            vendor = lookup_mac_vendor(mac_address)
                            if vendor != 'Unknown':
                                display_name += f" - {vendor}"
                        
                        interfaces.append({
                            'name': interface_name,
                            'display_name': display_name,
                            'ipv4': ipv4_addresses[0],
                            'mac': mac_address,
                            'vendor': lookup_mac_vendor(mac_address)
                        })
            
        except Exception as e:
            pass  # Fall back to basic detection
    
    # Fallback method without psutil
    if not interfaces:
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Add default interface
            interfaces.append({
                'name': 'default',
                'display_name': f'Default Interface ({local_ip})',
                'ipv4': local_ip,
                'mac': '00:00:00:00:00:00',
                'vendor': 'Unknown'
            })
            
            # Try to get additional interfaces using system commands
            if platform.system().lower() == 'windows':
                try:
                    # Use ipconfig to get network interfaces
                    result = subprocess.run(['ipconfig'], capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        lines = result.stdout.split('\n')
                        current_interface = None
                        
                        for line in lines:
                            line = line.strip()
                            if line and not line.startswith(' '):
                                # Interface name line
                                if ':' in line:
                                    current_interface = line.split(':')[0].strip()
                            elif 'IPv4 Address' in line and current_interface:
                                # Extract IP address
                                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                                if ip_match:
                                    ip = ip_match.group(1)
                                    if ip != local_ip:  # Don't duplicate default
                                        interfaces.append({
                                            'name': current_interface,
                                            'display_name': f'{current_interface} ({ip})',
                                            'ipv4': ip,
                                            'mac': 'Unknown',
                                            'vendor': 'Unknown'
                                        })
                except:
                    pass
            
        except Exception as e:
            # Ultimate fallback
            interfaces.append({
                'name': 'loopback',
                'display_name': 'Loopback (127.0.0.1)',
                'ipv4': '127.0.0.1',
                'mac': '00:00:00:00:00:00',
                'vendor': 'Unknown'
            })
    
    return interfaces


class PacketCapture(QThread):
    """Advanced packet capture for network analysis like Wireshark."""
    
    packet_captured = Signal(str, str, str, str)  # src_ip, dst_ip, protocol, info
    arp_discovered = Signal(str, str, str)  # ip, mac, vendor
    modbus_detected = Signal(str, str, int)  # src_ip, dst_ip, function
    capture_complete = Signal(int)  # number of packets captured
    output = Signal(str)  # status messages
    
    def __init__(self, interface=None, duration=30):
        super().__init__()
        self.interface = interface
        self.duration = duration
        self.should_stop = False
        self.packet_count = 0
        self.is_windows = platform.system().lower() == 'windows'
        
    def run(self):
        """Capture and analyze network packets."""
        try:
            self.output.emit("Starting packet capture...")
            
            if self.is_windows:
                # Windows-compatible packet capture using ARP scanning and network discovery
                self.run_windows_capture()
            else:
                # Linux/Unix packet capture using raw sockets
                self.run_unix_capture()
                
        except Exception as e:
            self.output.emit(f"Capture error: {e}")
            self.capture_complete.emit(0)
    
    def run_windows_capture(self):
        """Windows-compatible packet capture using ARP scanning and ping."""
        self.output.emit("Using Windows-compatible packet analysis...")
        
        try:
            # Get local network information
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
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
            
        self.output.emit(f"Windows packet analysis complete. Total devices found: {len(self.arp_devices)}")
        self.capture_complete.emit(len(self.arp_devices))
    
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
                        
                        # Lookup vendor
                        vendor = lookup_mac_vendor(mac_str)
                        
                        # Emit discovered device
                        self.arp_discovered.emit(ip_addr, mac_str, vendor)
                        self.output.emit(f"ARP: {ip_addr} -> {mac_str} ({vendor})")
                        
                        # Check if this might be a Modbus device
                        if self.check_modbus_device_windows(ip_addr):
                            self.modbus_detected.emit(ip_addr, local_ip, 1)  # Assume read coils
                            self.output.emit(f"🔧 Potential Modbus device: {ip_addr}")
                        
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
                    vendor = lookup_mac_vendor(mac) if mac else 'Unknown'
                    
                    self.arp_discovered.emit(ip, mac, vendor)
                    self.output.emit(f"🔍 Active device: {ip} -> {mac} ({vendor})")
                    
                    # Check for Modbus
                    if self.check_modbus_device_windows(ip):
                        self.modbus_detected.emit(ip, ip, 1)
                        self.output.emit(f"🔧 Potential Modbus device: {ip}")
                        
                # Update progress
                progress = int((i / 254) * 100)
                self.output.emit(f"Scanning progress: {progress}%")
                
                # Small delay to prevent overwhelming network
                self.msleep(50)
                
            except subprocess.TimeoutExpired:
                continue
            except Exception as e:
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
        
        return '00:00:00:00:00:00'  # Default MAC
    
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
            self.output.emit("Socket created successfully")
            
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
                    
                    # Update progress every 100 packets
                    if self.packet_count % 100 == 0:
                        elapsed = time.time() - start_time
                        self.output.emit(f"Captured {self.packet_count} packets in {elapsed:.1f}s...")
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    self.output.emit(f"Error processing packet: {e}")
                    continue
            
            self.raw_socket.close()
            self.output.emit(f"Packet capture complete. Total packets: {self.packet_count}")
            self.capture_complete.emit(self.packet_count)
            
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
                # ARP header structure
                        arp_hw_type = struct.unpack('!H', arp_data[0:2])[0]
                        arp_proto_type = struct.unpack('!H', arp_data[2:4])[0]
                        arp_hw_len = arp_data[4]
                        arp_proto_len = arp_data[5]
                        arp_opcode = struct.unpack('!H', arp_data[6:8])[0]
                        
                        if arp_proto_type == 0x0800:  # ARP for IP
                            sender_mac = ':'.join([f'{arp_data[i+8]:02x}' for i in range(0, 6)])
                            sender_ip = socket.inet_ntoa(arp_data[14:18])
                            target_mac = ':'.join([f'{arp_data[i+18]:02x}' for i in range(0, 6)])
                            target_ip = socket.inet_ntoa(arp_data[24:28])
                            
                            # Discover device from ARP request/reply
                            if arp_opcode in [1, 2]:  # ARP request or reply
                                vendor = lookup_mac_vendor(sender_mac)
                                self.arp_discovered.emit(sender_ip, sender_mac, vendor)
                                self.output.emit(f"ARP: {sender_ip} -> {sender_mac} ({vendor})")
                                
        except Exception as e:
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
                                    self.output.emit(f"Modbus: {src_ip}:{src_port} -> {dst_ip}:{dst_port} (Function: {modbus_func})")
                                
                        self.packet_captured.emit(src_ip, dst_ip, 'TCP', f"{src_port}->{dst_port}")
                    
                # UDP packet
                elif ip_proto == 17:
                    self.packet_captured.emit(src_ip, dst_ip, 'UDP', 'Data')
                    
        except Exception as e:
            pass  # Silently ignore IP parsing errors
    
    def stop(self):
        """Stop packet capture."""
        self.should_stop = True
        if hasattr(self, 'raw_socket'):
            try:
                self.raw_socket.close()
            except:
                pass


class NetworkDiagnosticsDialog:
    """Network diagnostics dialog functionality."""

    def __init__(self, parent_window):
        self.parent = parent_window
        self.dialog = None
        self.worker = None
        self.scanner = None
        self.capturer = None
        self.output_text = None
        self.discovered_devices = []
        self.captured_packets = []
        self.arp_devices = []
        self.selected_interface = None
        self.interfaces = []

    def show_diagnostics(self, host, port, unit_id):
        """Show network diagnostics dialog."""
        if self.dialog is None:
            self.dialog = QDialog(self.parent)
            self.dialog.setWindowTitle("Network Diagnostics")
            self.dialog.setGeometry(300, 300, 600, 600)

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
                    font-size: 12px;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    image: none;
                    border-left: 5px solid transparent;
                    border-right: 5px solid transparent;
                    border-top: 5px solid #666;
                    margin-right: 5px;
                }
            """)
            
            # Populate network interfaces
            self.interfaces = get_network_interfaces()
            for interface in self.interfaces:
                self.interface_combo.addItem(interface['display_name'], interface['name'])
            
            self.interface_combo.currentTextChanged.connect(self.on_interface_changed)
            interface_layout.addWidget(self.interface_combo)
            
            # Refresh button for interfaces
            refresh_btn = QPushButton("Refresh")
            refresh_btn.setStyleSheet(self.parent._get_button_style())
            refresh_btn.clicked.connect(self.refresh_interfaces)
            refresh_btn.setMaximumWidth(80)
            interface_layout.addWidget(refresh_btn)
            
            layout.addLayout(interface_layout)
            
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
            
            self.capture_btn = QPushButton("Capture Packets")
            self.capture_btn.setStyleSheet(self.parent._get_button_style())
            self.capture_btn.clicked.connect(lambda: self.capture_packets())
            button_layout.addWidget(self.capture_btn)
            
            self.stop_btn = QPushButton("Stop Scan")
            self.stop_btn.setStyleSheet(self.parent._get_button_style())
            self.stop_btn.clicked.connect(lambda: self.stop_scan())
            self.stop_btn.setEnabled(False)
            button_layout.addWidget(self.stop_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(self.parent._get_button_style())
            close_btn.clicked.connect(self.dialog.close)
            button_layout.addWidget(close_btn)

            layout.addLayout(button_layout)

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
    
    def on_interface_changed(self, display_name):
        """Handle network interface selection change."""
        # Find the selected interface
        for interface in self.interfaces:
            if interface['display_name'] == display_name:
                self.selected_interface = interface
                # Auto-fill IP with interface's IPv4 address
                self.ip_input.setText(interface['ipv4'])
                self.output_text.append(f"Selected interface: {interface['name']} - {interface['ipv4']}")
                break
    
    def refresh_interfaces(self):
        """Refresh the list of network interfaces."""
        try:
            # Save current selection
            current_name = self.interface_combo.currentText()
            
            # Refresh interfaces
            self.interfaces = get_network_interfaces()
            
            # Update combo box
            self.interface_combo.clear()
            for interface in self.interfaces:
                self.interface_combo.addItem(interface['display_name'], interface['name'])
            
            # Try to restore previous selection
            index = self.interface_combo.findText(current_name)
            if index >= 0:
                self.interface_combo.setCurrentIndex(index)
            
            self.output_text.append(f"Network interfaces refreshed. Found {len(self.interfaces)} interfaces.")
            
        except Exception as e:
            self.output_text.append(f"Error refreshing interfaces: {e}")

    def run_tests(self):
        """Run network diagnostics tests using user-provided IP and port."""
        if self.worker and self.worker.isRunning():
            return
        
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
        
        # Show progress bar and disable buttons
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.discover_btn.setEnabled(False)
        self.discover_btn.setText("Scanning...")
        self.test_btn.setEnabled(False)
        
        # Start scanner (scan 254 addresses in the network)
        self.scanner = NetworkScanner(base_ip, 254, port)
        self.scanner.device_found.connect(self.on_device_found)
        self.scanner.progress.connect(self.on_scan_progress)
        self.scanner.output.connect(self.output_text.append)
        self.scanner.scan_complete.connect(self.on_scan_complete)
        self.scanner.start()
        
        # Enable stop button
        self.stop_btn.setEnabled(True)
    
    def on_device_found(self, ip, port, status):
        """Handle device discovery."""
        self.discovered_devices.append((ip, port, status))
    
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
        
        self.output_text.clear()
        self.captured_packets.clear()
        self.arp_devices.clear()
        
        # Show progress bar and disable buttons
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Capturing packets...")
        
        self.capture_btn.setEnabled(False)
        self.capture_btn.setText("Capturing...")
        self.test_btn.setEnabled(False)
        self.discover_btn.setEnabled(False)
        
        # Start packet capture (30 seconds)
        self.capturer = PacketCapture(duration=30)
        self.capturer.packet_captured.connect(self.on_packet_captured)
        self.capturer.arp_discovered.connect(self.on_arp_discovered)
        self.capturer.modbus_detected.connect(self.on_modbus_detected)
        self.capturer.output.connect(self.output_text.append)
        self.capturer.capture_complete.connect(self.on_capture_complete)
        self.capturer.start()
        
        # Enable stop button
        self.stop_btn.setEnabled(True)
    
    def stop_scan(self):
        """Stop any ongoing scan or capture."""
        try:
            # Stop packet capture
            if self.capturer and self.capturer.isRunning():
                self.capturer.stop()
                self.output_text.append("Packet capture stopped by user")
            
            # Stop network scanner
            if self.scanner and self.scanner.isRunning():
                self.scanner.stop()
                self.output_text.append("Network scan stopped by user")
            
            # Reset buttons
            self.stop_btn.setEnabled(False)
            self.capture_btn.setEnabled(True)
            self.capture_btn.setText("Capture Packets")
            self.discover_btn.setEnabled(True)
            self.discover_btn.setText("Discover Devices")
            self.test_btn.setEnabled(True)
            
            # Hide progress bar
            self.progress_bar.setVisible(False)
            
        except Exception as e:
            self.output_text.append(f"Error stopping scan: {e}")
    
    def on_packet_captured(self, src_ip, dst_ip, protocol, info):
        """Handle captured packet."""
        self.captured_packets.append((src_ip, dst_ip, protocol, info))
    
    def on_arp_discovered(self, ip, mac, vendor):
        """Handle ARP device discovery."""
        self.arp_devices.append((ip, mac, vendor))
        self.output_text.append(f"🔍 Device discovered via ARP: {ip} -> {mac} ({vendor})")
    
    def on_modbus_detected(self, src_ip, dst_ip, function):
        """Handle Modbus traffic detection."""
        func_names = {
            1: "Read Coils", 2: "Read Discrete Inputs", 3: "Read Holding Registers",
            4: "Read Input Registers", 5: "Write Single Coil", 6: "Write Single Register",
            15: "Write Multiple Coils", 16: "Write Multiple Registers"
        }
        func_name = func_names.get(function, f"Unknown ({function})")
        self.output_text.append(f"🔧 Modbus traffic: {src_ip} -> {dst_ip} ({func_name})")
    
    def on_capture_complete(self, packet_count):
        """Handle packet capture completion."""
        self.progress_bar.setVisible(False)
        self.capture_btn.setEnabled(True)
        self.capture_btn.setText("Capture Packets")
        self.test_btn.setEnabled(True)
        self.discover_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # Disable stop button when complete
        
        # Display summary
        self.output_text.append(f"\n=== CAPTURE SUMMARY ===")
        self.output_text.append(f"Total packets captured: {packet_count}")
        self.output_text.append(f"Devices discovered via ARP: {len(self.arp_devices)}")
        
        if self.arp_devices:
            self.output_text.append(f"\n=== DEVICES IDENTIFIED BY MAC VENDOR ===")
            for ip, mac, vendor in self.arp_devices:
                if vendor != 'Unknown':
                    self.output_text.append(f"🏭 {vendor}: {ip} ({mac})")
                    
            # Auto-fill first identified PLC device
            for ip, mac, vendor in self.arp_devices:
                if vendor != 'Unknown' and any(plc in vendor.lower() for plc in ['siemens', 'rockwell', 'schneider', 'mitsubishi', 'omron', 'abb']):
                    self.ip_input.setText(ip)
                    self.output_text.append(f"\nAuto-filled IP with identified PLC device: {vendor} at {ip}")
                    break

    def on_tests_done(self, ok):
        """Handle test completion."""
        self.test_btn.setEnabled(True)
        self.test_btn.setText("Run Tests")
        if ok:
            self.output_text.append("\nAll tests completed successfully!")
        else:
            self.output_text.append("\nSome tests failed. Check the output above.")
