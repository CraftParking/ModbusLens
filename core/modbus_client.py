import logging
from typing import Optional, List, Union
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)


class ModbusClient:
    def __init__(self, ip="127.0.0.1", port=502, unit_id=1, timeout=1.5, retries=1):
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.retries = retries
        self.client: Optional[ModbusTcpClient] = None
        self._connected = False

    def connect(self):
        try:
            self.client = ModbusTcpClient(host=self.ip, port=self.port, timeout=self.timeout, retries=self.retries)
            self._connected = self.client.connect()
            if self._connected:
                logger.info(f"Connected to Modbus server at {self.ip}:{self.port}")
            else:
                logger.error(f"Failed to connect to Modbus server at {self.ip}:{self.port}")
            return self._connected
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self._connected = False
            return False

    def disconnect(self):
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("Disconnected from Modbus server")

    def is_connected(self):
        return self._connected

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def read_coils(self, address, count):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return None
        try:
            result = self.client.read_coils(address, count=count, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error reading coils at address {address}: {result}")
                return None
            return result.bits
        except Exception as e:
            logger.error(f"Exception reading coils: {e}")
            return None

    def read_discrete_inputs(self, address, count):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return None
        try:
            result = self.client.read_discrete_inputs(address, count=count, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error reading discrete inputs at address {address}: {result}")
                return None
            return result.bits
        except Exception as e:
            logger.error(f"Exception reading discrete inputs: {e}")
            return None

    def read_registers(self, address, count):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return None
        try:
            result = self.client.read_holding_registers(address, count=count, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error reading registers at address {address}: {result}")
                return None
            return result.registers
        except Exception as e:
            logger.error(f"Exception reading registers: {e}")
            return None

    def read_input_registers(self, address, count):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return None
        try:
            result = self.client.read_input_registers(address, count=count, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error reading input registers at address {address}: {result}")
                return None
            return result.registers
        except Exception as e:
            logger.error(f"Exception reading input registers: {e}")
            return None

    def write_coil(self, address, value):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return False
        try:
            result = self.client.write_coil(address, value, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error writing coil at address {address}: {result}")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception writing coil: {e}")
            return False

    def write_register(self, address, value):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return False
        try:
            result = self.client.write_register(address, value, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error writing register at address {address}: {result}")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception writing register: {e}")
            return False

    def write_coils(self, address, values):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return False
        try:
            result = self.client.write_coils(address, values, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error writing coils at address {address}: {result}")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception writing coils: {e}")
            return False

    def write_registers(self, address, values):
        if not self.is_connected():
            logger.error("Not connected to Modbus server")
            return False
        try:
            result = self.client.write_registers(address, values, device_id=self.unit_id)
            if result.isError():
                logger.error(f"Error writing registers at address {address}: {result}")
                return False
            return True
        except Exception as e:
            logger.error(f"Exception writing registers: {e}")
            return False
