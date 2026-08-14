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


# Base (no "_SWAP" suffix) multi-register numeric formats and how many 16-bit registers one
# value occupies -- single source of truth so a wider format only needs adding here, not to
# every scattered "value_format in (...)" check across main_window.py/trend_widget.py.
MULTI_WORD_FORMAT_WIDTHS = {
    "U32": 2, "S32": 2, "F32": 2,
    "U64": 4, "S64": 4, "F64": 4,
}

# Every valid multi-word format name, base and "_SWAP", for membership checks (format combo
# boxes, count validation) that need the full set rather than just the width.
MULTI_WORD_FORMATS = tuple(
    f"{base}{suffix}" for base in MULTI_WORD_FORMAT_WIDTHS for suffix in ("", "_SWAP")
)


def format_word_width(value_format):
    """Registers needed for one value of `value_format` (with or without a trailing
    "_SWAP"). 1 for every 16-bit-or-narrower format (U16/S16/Bool/Hex/etc.)."""
    base = (value_format or "U16").strip().upper().replace("_SWAP", "")
    return MULTI_WORD_FORMAT_WIDTHS.get(base, 1)
