import logging
from typing import Optional, Union
from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ConnectionException, ModbusIOException

logger = logging.getLogger(__name__)


class ModbusClient:
    """Wraps a pymodbus TCP or serial (RTU/ASCII) client behind one interface.

    Every read/write method below only ever touches self.client, so the rest of the app
    (Address Table, Tags, Trend, Server, Script) works unchanged regardless of transport --
    only connect() needs to know the difference between TCP and serial, and RTU vs ASCII framing.
    """

    def __init__(self, ip="127.0.0.1", port=502, unit_id=1, timeout=1.5, retries=1,
                 mode="tcp", serial_port="COM1", baudrate=19200, parity="N", stopbits=1, bytesize=8,
                 serial_framer="rtu", source_address=None):
        self.mode = mode  # "tcp" or "serial"
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.retries = retries
        # IP of the local interface to bind the outgoing TCP socket to (e.g. so a VPN +
        # Ethernet + Wi-Fi machine goes out the NIC the user picked); None lets the OS
        # pick the route as before. Meaningless for mode == "serial".
        self.source_address = source_address
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.serial_framer = serial_framer  # "rtu" or "ascii" -- only meaningful when mode == "serial"
        self.client: Optional[Union[ModbusTcpClient, ModbusSerialClient]] = None
        self._connected = False
        self.last_error: Optional[str] = None
        # Numeric Modbus exception code (1=Illegal Function, 2=Illegal Data Address, ...)
        # from the device's own exception response, when last_error came from one.
        self.last_exception_code: Optional[int] = None
        # Coarse bucket for the per-tag/device error counters (MonitoringManager.
        # tag_error_counts): "connection", "timeout", "device_exception", "rejected", or
        # "other" -- see _set_error/_categorize_exception below.
        self.last_error_category: Optional[str] = None
        # Optional per-register (holding register) write bounds: address -> (min, max).
        # Enforced here so every write path -- Address Table, Tags, Script -- is
        # covered the same way, regardless of which one originated the write.
        self.write_bounds = {}
        # The literal bytes of the most recent request/response, captured via pymodbus's
        # trace_packet hook -- the actual wire data, distinct from the decoded values every
        # read/write method returns. Reset before each call so a timeout shows "no response"
        # rather than a stale value left over from a previous, unrelated transaction.
        self.last_tx_bytes: Optional[bytes] = None
        self.last_rx_bytes: Optional[bytes] = None

    def _trace_packet(self, sending, data):
        if sending:
            self.last_tx_bytes = bytes(data)
        else:
            self.last_rx_bytes = bytes(data)
        return data

    def _reset_trace(self):
        self.last_tx_bytes = None
        self.last_rx_bytes = None

    def set_write_bound(self, address, minimum, maximum):
        self.write_bounds[address] = (minimum, maximum)

    def clear_write_bound(self, address):
        self.write_bounds.pop(address, None)

    def _check_write_bounds(self, address, values):
        """Return an error string if any value at address, address+1, ... is out of its configured bound."""
        for offset, value in enumerate(values):
            bound = self.write_bounds.get(address + offset)
            if bound is None:
                continue
            minimum, maximum = bound
            if value < minimum or value > maximum:
                return (
                    f"value {value} at address {address + offset} is outside the configured "
                    f"write bound [{minimum}, {maximum}]"
                )
        return None

    def _set_error(self, message, exception_code=None, category="other"):
        """Central place to record a failed operation. last_error/last_exception_code
        behave exactly as before; last_error_category is the new coarse bucket the
        per-tag/device error counters group by:
        - "connection": not connected at all, or a socket-level failure (OSError/
          ConnectionException).
        - "timeout": pymodbus's ModbusIOException -- covers both a true timeout and an
          unparseable/garbled (e.g. CRC-failed) frame that never resolved to a valid
          response. pymodbus doesn't distinguish those two at the exception level, so
          this deliberately does NOT invent a separate "CRC" bucket it can't actually
          tell apart from a timeout.
        - "device_exception": the device replied, but with a real Modbus exception code
          (Illegal Data Address, etc.) -- not a communications failure at all.
        - "rejected": a write bound violation caught locally, before anything reached
          the wire.
        - "other": anything else."""
        self.last_error = message
        self.last_exception_code = exception_code
        self.last_error_category = category
        logger.error(message)

    @staticmethod
    def _categorize_exception(exc):
        if isinstance(exc, (ConnectionException, OSError)):
            return "connection"
        if isinstance(exc, ModbusIOException):
            return "timeout"
        return "other"

    def target_description(self):
        if self.mode == "serial":
            framer_label = "ASCII" if self.serial_framer == "ascii" else "RTU"
            return f"{self.serial_port} @ {self.baudrate} baud ({framer_label})"
        return f"{self.ip}:{self.port}"

    def connect(self):
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logger.error(f"Error closing previous connection: {e}")
        try:
            if self.mode == "serial":
                framer = FramerType.ASCII if self.serial_framer == "ascii" else FramerType.RTU
                self.client = ModbusSerialClient(
                    port=self.serial_port, framer=framer, baudrate=self.baudrate, parity=self.parity,
                    stopbits=self.stopbits, bytesize=self.bytesize,
                    timeout=self.timeout, retries=self.retries,
                    trace_packet=self._trace_packet,
                )
            else:
                self.client = ModbusTcpClient(
                    host=self.ip, port=self.port, timeout=self.timeout, retries=self.retries,
                    trace_packet=self._trace_packet,
                    source_address=(self.source_address, 0) if self.source_address else None,
                )

            self._connected = self.client.connect()
            if self._connected:
                self.last_error = None
                logger.info(f"Connected to Modbus server at {self.target_description()}")
            else:
                self.last_error = f"Failed to connect to Modbus server at {self.target_description()}"
                logger.error(self.last_error)
            return self._connected
        except Exception as e:
            self.last_error = f"Connection error: {e}"
            logger.error(self.last_error)
            self._connected = False
            return False

    def disconnect(self):
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            finally:
                self._connected = False
            logger.info("Disconnected from Modbus server")

    def is_connected(self):
        return self._connected

    def get_timeout(self):
        """The response-wait timeout actually in effect, including any override from
        set_timeout() -- not just the value the client was originally constructed with."""
        if self.client is not None and hasattr(self.client, "comm_params"):
            return self.client.comm_params.timeout_connect
        return self.timeout

    def set_timeout(self, seconds):
        """Override the response-wait timeout on an already-connected client without
        reconnecting -- pymodbus has no per-call timeout parameter, so this reaches into
        the live client's comm_params directly. Used by the Register Scanner to probe
        many addresses quickly; callers are responsible for restoring the original value
        (via get_timeout() beforehand) once they're done."""
        if self.client is not None and hasattr(self.client, "comm_params"):
            self.client.comm_params.timeout_connect = seconds

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def read_coils(self, address, count):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_coils(address, count=count, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading coils at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.bits[:count]
        except Exception as e:
            self._set_error(f"Exception reading coils: {e}", category=self._categorize_exception(e))
            return None

    def read_discrete_inputs(self, address, count):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_discrete_inputs(address, count=count, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading discrete inputs at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.bits[:count]
        except Exception as e:
            self._set_error(f"Exception reading discrete inputs: {e}", category=self._categorize_exception(e))
            return None

    def read_registers(self, address, count):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_holding_registers(address, count=count, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading registers at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.registers
        except Exception as e:
            self._set_error(f"Exception reading registers: {e}", category=self._categorize_exception(e))
            return None

    def read_input_registers(self, address, count):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_input_registers(address, count=count, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading input registers at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.registers
        except Exception as e:
            self._set_error(f"Exception reading input registers: {e}", category=self._categorize_exception(e))
            return None

    def write_coil(self, address, value):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        self._reset_trace()
        try:
            result = self.client.write_coil(address, value, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error writing coil at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception writing coil: {e}", category=self._categorize_exception(e))
            return False

    def write_register(self, address, value):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        bounds_error = self._check_write_bounds(address, [value])
        if bounds_error:
            self._set_error(f"Write rejected: {bounds_error}", category="rejected")
            return False
        self._reset_trace()
        try:
            result = self.client.write_register(address, value, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error writing register at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception writing register: {e}", category=self._categorize_exception(e))
            return False

    def write_coils(self, address, values):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        self._reset_trace()
        try:
            result = self.client.write_coils(address, values, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error writing coils at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception writing coils: {e}", category=self._categorize_exception(e))
            return False

    def write_registers(self, address, values):
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        bounds_error = self._check_write_bounds(address, values)
        if bounds_error:
            self._set_error(f"Write rejected: {bounds_error}", category="rejected")
            return False
        self._reset_trace()
        try:
            result = self.client.write_registers(address, values, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error writing registers at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception writing registers: {e}", category=self._categorize_exception(e))
            return False
