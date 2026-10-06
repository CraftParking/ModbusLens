"""Per-device connections.

Every device on the Overview has its own connection settings -- a Modbus TCP endpoint
(IP, port, framing, interface, Fast LAN Mode) or a serial port (port, baud, parity, stop
bits, byte size, RTU/ASCII) -- plus its own Unit ID. Devices whose settings point at the
same physical link (the same IP:port with the same framing, or the same COM port) share
ONE ModbusClient: a serial port can only be opened once, and small gateways (e.g. a
Waveshare RS485-TO-ETH) only accept a few TCP connections. Requests on a shared link go
one at a time, each carrying its own device's Unit ID.

Tools talk to a device through a DeviceView -- its link's client with the device's Unit ID
filled in on every request (each tool's Device selector, Trend pens, Tags polling).
"""

import time

from core.modbus_client import ModbusClient

CONNECTION_FIELDS = ("mode", "ip", "port", "serial_port", "baudrate", "parity", "stopbits", "bytesize",
                     "serial_framer", "tcp_framer", "fast_lan_mode", "interface_ip")

DEFAULT_CONNECTION = {
    "mode": "tcp", "ip": "127.0.0.1", "port": 502, "serial_port": "COM1", "baudrate": 19200,
    "parity": "N", "stopbits": 1, "bytesize": 8, "serial_framer": "rtu", "tcp_framer": "socket",
    "fast_lan_mode": False, "interface_ip": None,
}

# Every ModbusClient request method that takes a per-call unit_id (see core/modbus_client.py).
REQUEST_METHODS = frozenset({
    "read_coils", "read_discrete_inputs", "read_registers", "read_input_registers", "write_coil",
    "write_register", "write_coils", "write_registers", "read_exception_status", "diag_query_data",
    "diag_restart_communication", "diag_read_diagnostic_register", "diag_clear_counters",
    "get_comm_event_counter", "get_comm_event_log", "report_device_id", "read_file_record",
    "write_file_record", "mask_write_register", "read_fifo_queue", "read_device_information",
})


def normalize_connection(conn):
    """A complete connection dict (missing fields filled from DEFAULT_CONNECTION)."""
    out = dict(DEFAULT_CONNECTION)
    for key in CONNECTION_FIELDS:
        # interface_ip is legitimately None ("Auto"); any other None means "not given".
        if conn and key in conn and (conn[key] is not None or key == "interface_ip"):
            out[key] = conn[key]
    out["port"] = int(out["port"])
    out["baudrate"] = int(out["baudrate"])
    return out


def link_key(conn):
    """Identity of the physical link a connection uses. Serial: the port itself (it can
    only be opened once, so two devices on it MUST share it). TCP: endpoint + framing +
    interface + Fast LAN Mode (those change how the socket/client behaves)."""
    conn = normalize_connection(conn)
    if conn["mode"] == "serial":
        return ("serial", str(conn["serial_port"]).upper())
    return ("tcp", conn["ip"], conn["port"], conn["tcp_framer"], conn["interface_ip"] or "", bool(conn["fast_lan_mode"]))


def serial_settings(conn):
    conn = normalize_connection(conn)
    return (conn["baudrate"], conn["parity"], conn["stopbits"], conn["bytesize"], conn["serial_framer"])


def describe(conn):
    conn = normalize_connection(conn)
    if conn["mode"] == "serial":
        framer = "ASCII" if conn["serial_framer"] == "ascii" else "RTU"
        return f"{conn['serial_port']} @ {conn['baudrate']} baud ({framer})"
    if conn["tcp_framer"] == "rtu":
        return f"{conn['ip']}:{conn['port']} (RTU over TCP)"
    return f"{conn['ip']}:{conn['port']}"


def serial_conflict(conn, unit_name, devices):
    """Error text if `conn` puts a device on a serial port another device already uses
    with different line settings (one port has one baud rate), else None."""
    conn = normalize_connection(conn)
    if conn["mode"] != "serial":
        return None
    for other in devices:
        if other["name"] == unit_name:
            continue
        other_conn = normalize_connection(other.get("connection"))
        if link_key(other_conn) == link_key(conn) and serial_settings(other_conn) != serial_settings(conn):
            return (f"{conn['serial_port']} is already used by \"{other['name']}\" with different settings "
                    f"({describe(other_conn)}) -- devices on one serial port must share its line settings.")
    return None


def build_client(conn):
    """The ModbusClient for a connection -- the same construction _connect() always used."""
    conn = normalize_connection(conn)
    if conn["mode"] == "serial":
        return ModbusClient(mode="serial", serial_port=conn["serial_port"], baudrate=conn["baudrate"],
                            parity=conn["parity"], stopbits=conn["stopbits"], bytesize=conn["bytesize"],
                            serial_framer=conn["serial_framer"])
    if conn["fast_lan_mode"]:
        client = ModbusClient(conn["ip"], conn["port"], timeout=0.2, retries=0,
                              source_address=conn["interface_ip"], tcp_framer=conn["tcp_framer"])
    else:
        client = ModbusClient(conn["ip"], conn["port"], source_address=conn["interface_ip"],
                              tcp_framer=conn["tcp_framer"])
    client.fast_lan_mode = bool(conn["fast_lan_mode"])
    return client


class DeviceView:
    """One device's view of a (possibly shared) link: every request method gets the
    device's Unit ID unless the caller passes one; everything else -- is_connected(),
    last_error, last_tx_bytes, write_bounds, set_timeout() ... -- is the link client's."""

    def __init__(self, client, unit_id):
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "unit_id", unit_id)

    @property
    def client(self):
        return self._client

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if name in REQUEST_METHODS:
            unit = self.unit_id

            def call(*args, unit_id=None, **kwargs):
                return attr(*args, unit_id=unit if unit_id is None else unit_id, **kwargs)
            return call
        return attr

    def __setattr__(self, name, value):
        setattr(self._client, name, value)


class Link:
    def __init__(self, key, conn):
        self.key = key
        self.conn = normalize_connection(conn)
        self.client = None
        self.last_error = None
        # Auto-reconnect bookkeeping (see LinkPool.watchdog_tick)
        self.reconnecting = False
        self.attempt = 0
        self.next_retry = 0.0

    def is_connected(self):
        return bool(self.client and self.client.is_connected())


class LinkPool:
    """The open links, keyed by link_key(). A link is opened when its first device
    connects and closed when its last connected device disconnects."""

    RECONNECT_BASE_S = 2.0
    RECONNECT_MAX_S = 30.0

    def __init__(self, client_factory=build_client):
        self.links = {}
        self.client_factory = client_factory

    def link_for(self, conn):
        key = link_key(conn)
        if key not in self.links:
            self.links[key] = Link(key, conn)
        return self.links[key]

    def open(self, conn):
        """(ok, error) -- connect the link for `conn` if it isn't already."""
        link = self.link_for(conn)
        if link.is_connected():
            return True, None
        if link.client is None:
            link.client = self.client_factory(link.conn)
        try:
            ok = link.client.connect()
        except Exception as e:  # ModbusClient.connect already catches, belt and braces
            ok, link.client.last_error = False, str(e)
        link.last_error = None if ok else (link.client.last_error or "Connection failed")
        if ok:
            link.reconnecting, link.attempt = False, 0
        return ok, link.last_error

    def close(self, key):
        link = self.links.pop(key, None)
        if link and link.client:
            link.client.disconnect()

    def client_for(self, conn):
        link = self.links.get(link_key(conn))
        return link.client if link else None

    def watchdog_tick(self, wanted_keys, now=None):
        """Reconnect dropped links that still have connected devices, with exponential
        backoff. Returns [(key, event)] with event "lost", "reconnected" or "retrying"."""
        now = time.monotonic() if now is None else now
        events = []
        for key in wanted_keys:
            link = self.links.get(key)
            if link is None or link.client is None:
                continue
            if link.client.is_connected():
                if link.reconnecting:
                    link.reconnecting, link.attempt = False, 0
                    events.append((key, "reconnected"))
                continue
            if not link.reconnecting:
                link.reconnecting, link.attempt, link.next_retry = True, 0, now
                events.append((key, "lost"))
            if now < link.next_retry:
                continue
            link.attempt += 1
            if link.client.connect():
                link.reconnecting, link.attempt = False, 0
                events.append((key, "reconnected"))
            else:
                delay = min(self.RECONNECT_BASE_S * (2 ** (link.attempt - 1)), self.RECONNECT_MAX_S)
                link.next_retry = now + delay
                events.append((key, "retrying"))
        return events
