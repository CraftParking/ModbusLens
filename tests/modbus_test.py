from pymodbus.client import ModbusTcpClient
print("ModScope Test Starting..")
ip = "127.0.0.1"
port = 502
unit_id = 1
add = 0
count = 5
client = ModbusTcpClient(host=ip, port=port)
print("Connecting..")
if not client.connect():
    print("Failed to connect to Server")
    exit()
print("Connected to Server")
print("Reading Registers..")
result = client.read_holding_registers(add)
if result.isError():
    print("Error reading registers:")
else:
    print("Register Values:", result.registers)
write_add=0
value=123
write_result = client.write_registers(write_add,[value])
if write_result.isError():
    print("Error writing register:")
else:
    print(f"Successfully wrote value {value} to register {write_add}")
client.close()
print("Test Completed.")