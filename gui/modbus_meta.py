FUNCTION_NAMES = {
    0x01: "Read Coils",
    0x02: "Read Discrete Inputs",
    0x03: "Read Holding Registers",
    0x04: "Read Input Registers",
    0x05: "Write Single Coil",
    0x06: "Write Single Register",
    0x0F: "Write Multiple Coils",
    0x10: "Write Multiple Registers",
}

_READ_CODES = {"Coil": 0x01, "Discrete Input": 0x02, "Holding Register": 0x03, "Input Register": 0x04}
_WRITE_SINGLE_CODES = {"Coil": 0x05, "Holding Register": 0x06}
_WRITE_MULTI_CODES = {"Coil": 0x0F, "Holding Register": 0x10}


def function_code_for(type_name, is_write, count=1):
    """Return (code, name) for a Modbus operation on the given register/coil type, based on
    what the caller already knows it just did -- not guessed from a free-form title string."""
    if is_write:
        codes = _WRITE_MULTI_CODES if count > 1 else _WRITE_SINGLE_CODES
    else:
        codes = _READ_CODES
    code = codes.get(type_name)
    if code is None:
        return None, None
    return code, FUNCTION_NAMES[code]
