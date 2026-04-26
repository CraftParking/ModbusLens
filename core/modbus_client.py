import logging
from typing import Optional, List, Union
from pymodbus.client import ModbusTcpClient

logger = logging.getLogger(__name__)


class ModbusClient:
    """Wrapper for ModbusTcp client with connection management and error handling."""

    def __init__(self, ip: str = "127.0.0.1", port: int = 502, unit_id: int = 1):
        """
        Initialize ModbusClient.

        Args:
            ip: Modbus server IP address (default: 127.0.0.1)
            port: Modbus server port (default: 502)
            unit_id: Modbus unit ID (default: 1)
        """
        self.ip = ip
        self.port = port
        self.unit_id = unit_id
        self.client: Optional[ModbusTcpClient] = None
        self._connected = False

    def connect(self) -> bool:
        """
        Connect to Modbus server.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.client = ModbusTcpClient(host=self.ip, port=self.port)
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

    def disconnect(self) -> None:
        """Disconnect from Modbus server."""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("Disconnected from Modbus server")

    def is_connected(self) -> bool:
        """
        Check if connected to Modbus server.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    # -------- READ --------

    def read_coils(self, address: int, count: int) -> Optional[List[bool]]:
        """
        Read coils (0x values) from Modbus server.

        Args:
            address: Starting address
            count: Number of coils to read

        Returns:
            List of boolean values or None on error.
        """
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

    def read_discrete_inputs(self, address: int, count: int) -> Optional[List[bool]]:
        """
        Read discrete inputs (1x values) from Modbus server.

        Args:
            address: Starting address
            count: Number of inputs to read

        Returns:
            List of boolean values or None on error.
        """
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

    def read_registers(self, address: int, count: int) -> Optional[List[int]]:
        """
        Read holding registers (4x values) from Modbus server.

        Args:
            address: Starting address
            count: Number of registers to read

        Returns:
            List of register values or None on error.
        """
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

    def read_input_registers(self, address: int, count: int) -> Optional[List[int]]:
        """
        Read input registers (3x values) from Modbus server.

        Args:
            address: Starting address
            count: Number of registers to read

        Returns:
            List of register values or None on error.
        """
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

    # -------- WRITE --------

    def write_coil(self, address: int, value: bool) -> bool:
        """
        Write single coil (0x value) to Modbus server.

        Args:
            address: Coil address
            value: Boolean value to write

        Returns:
            True if successful, False otherwise.
        """
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

    def write_register(self, address: int, value: int) -> bool:
        """
        Write single register (4x value) to Modbus server.

        Args:
            address: Register address
            value: Integer value to write

        Returns:
            True if successful, False otherwise.
        """
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

    def write_coils(self, address: int, values: List[bool]) -> bool:
        """
        Write multiple coils (0x values) to Modbus server.

        Args:
            address: Starting address
            values: List of boolean values to write

        Returns:
            True if successful, False otherwise.
        """
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

    def write_registers(self, address: int, values: List[int]) -> bool:
        """
        Write multiple registers (4x values) to Modbus server.

        Args:
            address: Starting address
            values: List of integer values to write

        Returns:
            True if successful, False otherwise.
        """
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