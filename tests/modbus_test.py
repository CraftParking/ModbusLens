from pymodbus.client import ModbusTcpClient

print("ModScope Test Starting..")
ip = input("Enter IP address (default 127.0.0.1): ") or "127.0.0.1"
port = input("Enter port (default 502): ") or "502"
port = int(port)
unit_id = 1
client = ModbusTcpClient(host=ip, port=port)
print("Connecting..")
if not client.connect():
    print("Failed to connect to Server")
    exit()
print("Connected to Server")
operation = input("Enter operation (read=0/write=1): ")
dtype = input("Enter data type (Coil=0/Registers=1): ")
if operation == "0":
    print(f"Reading {dtype}..")
    if dtype == "0":
        add = int(input("Enter coil address to read: "))
        result = client.read_coils(add, count=count, device_id=unit_id)
    elif dtype == "1":
        add = int(input("Enter register address to read: "))
        result = client.read_holding_registers(add, count=count, device_id=unit_id)
    else:
        print("Invalid data type selected for read.")
        client.close()
        exit()
    if result.isError():
        print("Error reading values.")
    else:
        print("Read result:", result.bits if dtype == "0" else result.registers)
elif operation == "1":
    print(f"Writing {dtype}..")
    if dtype == "0":
        add = int(input("Enter coil address to write: "))
        value = int(input("Enter coil value (0 or 1): "))
        write_result = client.write_coil(add, value, device_id=unit_id)
    elif dtype == "1":
        add = int(input("Enter register address to write: "))
        value = int(input("Enter register value: "))
        write_result = client.write_registers(add, [value], device_id=unit_id)
    else:
        print("Invalid data type selected for write.")
        client.close()
        exit()

    if write_result.isError():
        print("Error writing value.")
    else:
        print(f"Successfully wrote value {value} to address {add}")

else:
    print("Invalid operation selected.")

client.close()
print("Test Completed.")