"""Support for .mbmap register maps (https://github.com/nobrega8/mbmap-library).

A .mbmap.json file (format version 2, see SPEC.md in that repo) describes one device
model's Modbus registers: area, address, type, scaling, units, enums. This module turns
one into a ModbusLens Device Profile -- the same dict shape a saved profile has, with
the same per-tag row fields _build_tag_export_rows produces -- so a map can be previewed,
applied and saved through the normal Profiles flow without a second import path.

Pure Python on purpose (no Qt): the conversion is easy to test on its own, and the
Profiles panel only has to fetch bytes and hand them over.
"""
import json

# The library's own manifest, one entry per map: path, vendor, model, register count...
MBMAP_REPO = "nobrega8/mbmap-library"
MBMAP_BRANCH = "main"
MBMAP_BASE_URL = f"https://raw.githubusercontent.com/{MBMAP_REPO}/{MBMAP_BRANCH}/"
MBMAP_INDEX_URL = MBMAP_BASE_URL + "index.json"
MBMAP_WEB_URL = f"https://github.com/{MBMAP_REPO}"

_AREA_TYPES = {
    "coil": "Coil",
    "discrete": "Discrete Input",
    "input": "Input Register",
    "holding": "Holding Register",
}
_TYPE_FORMATS = {
    "uint16": "U16", "int16": "S16",
    "uint32": "U32", "int32": "S32", "float32": "F32",
    "uint64": "U64", "int64": "S64", "float64": "F64",
}
_TYPE_WIDTHS = {"uint16": 1, "int16": 1, "uint32": 2, "int32": 2, "float32": 2,
                "uint64": 4, "int64": 4, "float64": 4}

# Must match main_window.TAG_ROW_FIELDS (minus the per-installation Device/Unit ID).
_EMPTY_ROW = {
    "Tag Name": "", "Group": "", "Mode": "Read", "Type": "Holding Register", "Address": 0, "Count": 1,
    "Format": "U16", "Comment": "", "Enabled": True, "Scale Enabled": False, "Scale Mode": "",
    "Raw Min": "", "Raw Max": "", "Scaled Min": "", "Scaled Max": "", "Factor": "", "Value Type": "",
    "Bit Names": "", "Expression": "",
}


class MbmapError(ValueError):
    """The file isn't a .mbmap this version of ModbusLens can read."""


def parse_int(value):
    """An .mbmap integer: a JSON number, or a string holding decimal or 0x hex."""
    if isinstance(value, bool):
        raise ValueError("not an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    raise ValueError("not an integer")


def load_document(data):
    """Parse raw bytes/str into an .mbmap document, checking only what the conversion
    relies on -- full validation is the library's own validator's job."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8-sig")
    try:
        doc = json.loads(data)
    except json.JSONDecodeError as e:
        raise MbmapError(f"not valid JSON ({e})") from e
    if not isinstance(doc, dict):
        raise MbmapError("not a JSON object")
    if doc.get("mbmap") != 2:
        raise MbmapError(f"unsupported .mbmap format version {doc.get('mbmap')!r} (this version reads version 2)")
    if not isinstance(doc.get("registers"), list):
        raise MbmapError("no 'registers' list")
    return doc


def _number_text(value):
    """Scale numbers as short text: 0.1 not 0.1000000000000000055."""
    return f"{float(value):.12g}"


def _enum_table(doc, reg):
    enum = reg.get("enum")
    if isinstance(enum, str):
        enum = (doc.get("enums") or {}).get(enum)
    return enum if isinstance(enum, dict) else None


def _comment(doc, reg, extra=()):
    parts = list(extra)
    unit = reg.get("unit")
    if unit:
        parts.append(f"[{unit}]")
    if reg.get("description"):
        parts.append(str(reg["description"]))
    enum = _enum_table(doc, reg)
    if enum:
        parts.append("Values: " + ", ".join(f"{k}={v}" for k, v in enum.items()))
    if reg.get("scale_factor"):
        parts.append(f"Multiply by 10^({reg['scale_factor']})")
    return " | ".join(parts)


def _word_order(doc, reg):
    return reg.get("word_order", doc.get("word_order", "big"))


def _byte_order(doc, reg):
    return reg.get("byte_order", doc.get("byte_order", "big"))


def _scaling_fields(reg):
    scale = reg.get("scale", 1)
    offset = reg.get("offset", 0)
    try:
        scale, offset = float(scale), float(offset)
    except (TypeError, ValueError):
        return {}
    if scale == 1 and offset == 0:
        return {}
    if offset == 0:
        return {"Scale Enabled": True, "Scale Mode": "multiply", "Factor": _number_text(scale), "Value Type": "Real"}
    # raw x scale + offset as a straight line through (0, offset) and (1, scale + offset).
    return {"Scale Enabled": True, "Scale Mode": "linear", "Raw Min": "0", "Raw Max": "1",
            "Scaled Min": _number_text(offset), "Scaled Max": _number_text(scale + offset), "Value Type": "Real"}


def to_profile(doc, one_based=True, source_path=""):
    """Convert a parsed .mbmap document into a ModbusLens profile dict.

    `one_based` is the Tags table's current addressing mode: tag addresses are user-facing
    and the protocol offset is derived from them, so the same map must land as offset + 1
    in 1-based mode and as the plain offset in 0-based mode. Returns (profile, skipped)
    where `skipped` lists what couldn't be represented."""
    base = parse_int(doc.get("address_base", 0))
    shift = 1 if one_based else 0
    rows, skipped = [], []
    # Bits of one register (bool + bit) become ONE Bool tag with Bit Names, which is how
    # ModbusLens shows individual bits (Bit View) -- not one tag per bit.
    bit_rows = {}

    for reg in doc["registers"]:
        if not isinstance(reg, dict):
            continue
        name = str(reg.get("name", "")).strip()
        area = reg.get("area")
        typ = reg.get("type")
        try:
            offset = parse_int(reg.get("address")) - base
        except (TypeError, ValueError):
            skipped.append(f"{name or '?'}: invalid address")
            continue
        if area not in _AREA_TYPES or offset < 0 or offset > 65535:
            skipped.append(f"{name or '?'}: unsupported area or address")
            continue
        access = reg.get("access", "R")
        row = dict(_EMPTY_ROW)
        row.update({
            "Tag Name": name,
            "Group": str(reg.get("group", "")).strip(),
            "Mode": "Write" if access == "W" else "Read",
            "Type": _AREA_TYPES[area],
            "Address": offset + shift,
        })
        extra = []

        if typ == "bool" and area in ("coil", "discrete"):
            row.update({"Format": "Bool", "Comment": _comment(doc, reg)})
            rows.append(row)
            continue

        if typ == "bool":
            key = (area, offset)
            target = bit_rows.get(key)
            if target is None:
                target = dict(row)
                target.update({"Tag Name": f"{row['Group'] or 'Bits'} @ {offset + shift}", "Format": "Bool", "Count": 1,
                               "Comment": "Bit field"})
                target["_bits"] = {}
                bit_rows[key] = target
                rows.append(target)
            bit = reg.get("bit")
            try:
                target["_bits"][str(int(bit))] = name
            except (TypeError, ValueError):
                skipped.append(f"{name}: bool without a bit")
            continue

        if typ == "string":
            try:
                length = parse_int(reg.get("length"))
            except (TypeError, ValueError):
                skipped.append(f"{name}: string without a length")
                continue
            row.update({"Format": "Hex", "Count": length,
                        "Comment": _comment(doc, reg, [f"Text, {length * 2} characters (2 per register)"])})
            rows.append(row)
            continue

        fmt = _TYPE_FORMATS.get(typ)
        if fmt is None:
            skipped.append(f"{name}: unsupported type {typ!r}")
            continue
        if reg.get("bits") is not None:
            extra.append(f"Bit field: bits {reg.get('bit', 0)}..{int(reg.get('bit', 0)) + int(reg['bits']) - 1}")
        width = _TYPE_WIDTHS[typ]
        if width > 1 and _word_order(doc, reg) == "little":
            fmt += "_SWAP"
        if _byte_order(doc, reg) == "little":
            extra.append("Bytes swapped inside each register (not decoded by ModbusLens)")
        row.update({"Format": fmt, "Count": width, "Comment": _comment(doc, reg, extra)})
        row.update(_scaling_fields(reg))
        rows.append(row)

    for target in bit_rows.values():
        bits = target.pop("_bits")
        if bits:
            target["Bit Names"] = json.dumps(dict(sorted(bits.items(), key=lambda kv: int(kv[0]))))
            if len(bits) == 1:
                target["Tag Name"] = next(iter(bits.values()))

    vendor = str(doc.get("vendor", "")).strip()
    model = str(doc.get("model", "")).strip()
    profile = {
        "version": 1,
        "name": model or "(unnamed)",
        "manufacturer": vendor,
        "type": str(doc.get("description", "")).strip(),
        "author": "mbmap library",
        "tags": rows,
        "source": "mbmap",
        "source_file": source_path,
        "mbmap": {
            "revision": doc.get("revision"),
            "status": doc.get("x_status"),
            "connection": {k: doc[k] for k in ("protocol", "unit_id", "port", "baudrate", "parity", "databits", "stopbits")
                           if k in doc},
            "notes": doc.get("notes") or [],
        },
    }
    return profile, skipped


def load_profile(data, one_based=True, source_path=""):
    """Shortcut: raw .mbmap bytes -> (profile, skipped)."""
    return to_profile(load_document(data), one_based=one_based, source_path=source_path)


def index_entries(data):
    """The library's index.json as a list of card entries in the shape ProfileCard and
    the Community view already use (name/manufacturer/type/tag_count/file)."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    index = json.loads(data)
    entries = []
    for m in index.get("maps", []) if isinstance(index, dict) else []:
        if not isinstance(m, dict) or not m.get("path"):
            continue
        description = str(m.get("description") or "")
        if len(description) > 40:
            description = description[:38].rstrip() + "…"
        entries.append({
            "library": "mbmap",
            "file": m["path"],
            "name": m.get("model") or m["path"],
            "manufacturer": m.get("vendor") or "",
            "type": description,
            "description": str(m.get("description") or ""),
            "tag_count": m.get("registers") or 0,
            "status": m.get("status") or "",
        })
    entries.sort(key=lambda e: (e["manufacturer"].lower(), e["name"].lower()))
    return entries
