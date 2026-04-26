import logging
from core.modbus_client import ModbusClient

# Configure logging to only show errors (won't clutter CLI output)
logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')


def get_connection() -> ModbusClient:
    """Get connection parameters from user input."""
    ip = input("Enter IP (default 127.0.0.1): ") or "127.0.0.1"
    port = int(input("Enter Port (default 502): ") or "502")
    unit = int(input("Enter Unit ID (default 1): ") or "1")
    return ModbusClient(ip, port, unit)


def menu() -> None:
    """Display main menu."""
    print("\n=== ModbusLens CLI ===")
    print("1. Read Coils")
    print("2. Read Discrete Inputs")
    print("3. Read Holding Registers")
    print("4. Read Input Registers")
    print("5. Write Coil")
    print("6. Write Register")
    print("7. Write Multiple Coils")
    print("8. Write Multiple Registers")
    print("9. Exit")


def main():
    """Main CLI loop."""
    modbus = get_connection()

    print("\nConnecting...")
    if not modbus.connect():
        print("[ERROR] Connection failed. Check IP/Port and try again.")
        return

    print("[OK] Connected")

    try:
        while True:
            menu()
            choice = input("Select option: ").strip()

            try:
                if choice == "1":
                    addr = int(input("Address: "))
                    count = int(input("Count: "))
                    data = modbus.read_coils(addr, count)
                    if data is None:
                        print("[ERROR] Failed to read coils")
                    else:
                        print(f"[OK] Result: {data}")

                elif choice == "2":
                    addr = int(input("Address: "))
                    count = int(input("Count: "))
                    data = modbus.read_discrete_inputs(addr, count)
                    if data is None:
                        print("[ERROR] Failed to read discrete inputs")
                    else:
                        print(f"[OK] Result: {data}")

                elif choice == "3":
                    addr = int(input("Address: "))
                    count = int(input("Count: "))
                    data = modbus.read_registers(addr, count)
                    if data is None:
                        print("[ERROR] Failed to read registers")
                    else:
                        print(f"[OK] Result: {data}")

                elif choice == "4":
                    addr = int(input("Address: "))
                    count = int(input("Count: "))
                    data = modbus.read_input_registers(addr, count)
                    if data is None:
                        print("[ERROR] Failed to read input registers")
                    else:
                        print(f"[OK] Result: {data}")

                elif choice == "5":
                    addr = int(input("Address: "))
                    val = int(input("Value (0/1): "))
                    success = modbus.write_coil(addr, bool(val))
                    print("[OK] Success" if success else "[ERROR] Failed")

                elif choice == "6":
                    addr = int(input("Address: "))
                    val = int(input("Value: "))
                    success = modbus.write_register(addr, val)
                    print("[OK] Success" if success else "[ERROR] Failed")

                elif choice == "7":
                    addr = int(input("Start Address: "))
                    values = input("Values (comma separated 0/1): ")
                    values = [bool(int(v.strip())) for v in values.split(",")]
                    success = modbus.write_coils(addr, values)
                    print("[OK] Success" if success else "[ERROR] Failed")

                elif choice == "8":
                    addr = int(input("Start Address: "))
                    values = input("Values (comma separated integers): ")
                    values = [int(v.strip()) for v in values.split(",")]
                    success = modbus.write_registers(addr, values)
                    print("[OK] Success" if success else "[ERROR] Failed")

                elif choice == "9":
                    print("Exiting...")
                    break

                else:
                    print("[ERROR] Invalid choice")

            except ValueError as e:
                print(f"[ERROR] Input error: Please enter valid numbers. ({e})")
            except Exception as e:
                print(f"[ERROR] Error: {e}")

    finally:
        modbus.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    main()