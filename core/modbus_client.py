import logging
from typing import Optional, Union
from pymodbus import FramerType
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu.file_message import FileRecord

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

    # --- Diagnostic/advanced function codes (FC07/08/11/12/17/20/21/22/24/43) --
    # Niche next to the four basic read/write pairs above, but a real gap for
    # compliance/interop testing -- pymodbus's client already implements the wire
    # protocol for all of these, so each wrapper below only adds the same
    # connection-check/error-categorization/trace-reset convention every other
    # method here already follows.

    def read_exception_status(self):
        """FC07 -- an 8-bit vendor-specific status byte, a lightweight "is anything
        wrong" poll some devices support without a full register read."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_exception_status(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading exception status: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.status
        except Exception as e:
            self._set_error(f"Exception reading exception status: {e}", category=self._categorize_exception(e))
            return None

    def diag_query_data(self, message: bytes):
        """FC08 sub-function 0x00 (Return Query Data) -- a pure loopback test: the
        device must echo `message` back byte-for-byte. Good for confirming a serial
        link is alive without touching any real register."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.diag_query_data(msg=message, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error in diagnostic query data: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.message
        except Exception as e:
            self._set_error(f"Exception in diagnostic query data: {e}", category=self._categorize_exception(e))
            return None

    def diag_restart_communication(self, clear_log=True):
        """FC08 sub-function 0x01 (Restart Communications Option) -- asks the device
        to reinitialize its comm port. `clear_log` also clears its event log/counters,
        matching the Modbus spec's own toggle for this sub-function."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        self._reset_trace()
        try:
            result = self.client.diag_restart_communication(clear_log, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error restarting communication: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception restarting communication: {e}", category=self._categorize_exception(e))
            return False

    def diag_read_diagnostic_register(self):
        """FC08 sub-function 0x02 (Return Diagnostic Register) -- device-specific
        status bits (e.g. listen-only mode); meaning beyond raw bits is vendor-defined."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.diag_read_diagnostic_register(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading diagnostic register: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return result.message
        except Exception as e:
            self._set_error(f"Exception reading diagnostic register: {e}", category=self._categorize_exception(e))
            return None

    def diag_clear_counters(self):
        """FC08 sub-function 0x0A (Clear Counters and Diagnostic Register)."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        self._reset_trace()
        try:
            result = self.client.diag_clear_counters(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error clearing counters: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception clearing counters: {e}", category=self._categorize_exception(e))
            return False

    def get_comm_event_counter(self):
        """FC11 -- a free-running event counter devices bump on every completed
        transaction, plus a ready/busy status flag. Returns
        {"status": bool, "count": int} or None on failure."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.diag_get_comm_event_counter(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading comm event counter: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return {"status": result.status, "count": result.count}
        except Exception as e:
            self._set_error(f"Exception reading comm event counter: {e}", category=self._categorize_exception(e))
            return None

    def get_comm_event_log(self):
        """FC12 -- like get_comm_event_counter, plus a short history of recent bus
        events. Returns {"status", "event_count", "message_count", "events"} or None."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.diag_get_comm_event_log(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading comm event log: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return {
                "status": result.status,
                "event_count": result.event_count,
                "message_count": result.message_count,
                "events": list(result.events),
            }
        except Exception as e:
            self._set_error(f"Exception reading comm event log: {e}", category=self._categorize_exception(e))
            return None

    def report_device_id(self):
        """FC17 (Report Server ID, historically "Report Slave ID") -- a vendor-defined
        identifier string plus a run/stop indicator. Returns
        {"identifier": bytes, "status": bool} or None."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.report_device_id(device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reporting device ID: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return {"identifier": result.identifier, "status": result.status}
        except Exception as e:
            self._set_error(f"Exception reporting device ID: {e}", category=self._categorize_exception(e))
            return None

    def read_file_record(self, requests):
        """FC20 -- reads one or more records out of the device's file storage (a
        second, separate address space from registers/coils, rare outside energy
        meters and similar data loggers). `requests` is a list of
        (file_number, record_number, record_length) tuples; record_length is the
        number of 16-bit registers to read from that record. Returns a list of
        {"file_number", "record_number", "record_data"} dicts, or None on failure."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            # FileRecord.__post_init__ unconditionally halves whatever record_length it's
            # given (it's written for the record_data= case, where record_length starts as
            # a byte count and gets halved into a register count) -- so passing our
            # register count straight through here would silently request half as many
            # registers as asked for. Doubling it first is what actually gets `record_length`
            # registers onto the wire, verified against the real dataclass, not guessed.
            records = [
                FileRecord(file_number=file_number, record_number=record_number, record_length=record_length * 2)
                for file_number, record_number, record_length in requests
            ]
            result = self.client.read_file_record(records, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading file record: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return [
                {
                    "file_number": requested.file_number,
                    "record_number": requested.record_number,
                    "record_data": returned.record_data,
                }
                for requested, returned in zip(records, result.records)
            ]
        except Exception as e:
            self._set_error(f"Exception reading file record: {e}", category=self._categorize_exception(e))
            return None

    def write_file_record(self, requests):
        """FC21 -- writes one or more records into the device's file storage.
        `requests` is a list of (file_number, record_number, record_data) tuples,
        where record_data is raw bytes (an even number of bytes -- one 16-bit
        register each). Returns True on success (a correct write echoes the request
        back unchanged, which pymodbus already verifies via isError())."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return False
        self._reset_trace()
        try:
            records = [
                FileRecord(file_number=file_number, record_number=record_number, record_data=record_data)
                for file_number, record_number, record_data in requests
            ]
            result = self.client.write_file_record(records, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error writing file record: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return False
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return True
        except Exception as e:
            self._set_error(f"Exception writing file record: {e}", category=self._categorize_exception(e))
            return False

    def mask_write_register(self, address, and_mask, or_mask):
        """FC22 -- sets a register to (current_value AND and_mask) OR (or_mask AND
        NOT and_mask) atomically on the device, so setting a few bits doesn't race
        against another master's write to the same register between a read and a
        plain write_register. Returns {"address", "and_mask", "or_mask"} as echoed
        back by the device, or None on failure."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.mask_write_register(
                address=address, and_mask=and_mask, or_mask=or_mask, device_id=self.unit_id
            )
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error in mask write register at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return {"address": result.address, "and_mask": result.and_mask, "or_mask": result.or_mask}
        except Exception as e:
            self._set_error(f"Exception in mask write register: {e}", category=self._categorize_exception(e))
            return None

    def read_fifo_queue(self, address):
        """FC24 -- reads a FIFO queue's current contents (up to 31 16-bit values)
        without removing them, from a pointer register at `address`. Used by devices
        that buffer captured values (e.g. event timestamps) faster than a master
        polls them. Returns a list of ints, or None on failure."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_fifo_queue(address=address, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading FIFO queue at address {address}: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return list(result.values)
        except Exception as e:
            self._set_error(f"Exception reading FIFO queue: {e}", category=self._categorize_exception(e))
            return None

    def read_device_information(self, read_code=None, object_id=0):
        """FC43/14 (Read Device Identification) -- vendor name/product code/version
        and similar text objects, a standardized alternative to a vendor-specific
        register for "what device am I talking to." read_code selects Basic (0x01),
        Regular (0x02), Extended (0x03), or a single specific object_id (0x04);
        defaults to Basic. Returns {"information": {object_id: bytes, ...},
        "more_follows", "next_object_id"} or None -- a caller wanting Extended's full
        object set must re-call with object_id=next_object_id while more_follows
        is truthy, per the Modbus spec's own pagination for this function."""
        if not self.is_connected():
            self._set_error("Not connected to Modbus server", category="connection")
            return None
        self._reset_trace()
        try:
            result = self.client.read_device_information(read_code=read_code, object_id=object_id, device_id=self.unit_id)
            if result.isError():
                exception_code = getattr(result, "exception_code", None)
                self._set_error(
                    f"Error reading device information: {result}",
                    exception_code=exception_code,
                    category="device_exception" if exception_code is not None else "other",
                )
                return None
            self.last_error = None
            self.last_exception_code = None
            self.last_error_category = None
            return {
                "information": dict(result.information),
                "more_follows": bool(result.more_follows),
                "next_object_id": result.next_object_id,
            }
        except Exception as e:
            self._set_error(f"Exception reading device information: {e}", category=self._categorize_exception(e))
            return None
