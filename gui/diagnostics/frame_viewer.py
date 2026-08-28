"""Modbus frame viewer — decode raw TX/RX bytes into human-readable frame fields.

When the user clicks any cell in the Raw Data table, this module shows a floating
popup that decodes the transaction's TX and RX frames (MBAP for TCP, RTU for serial
RTU, LRC for serial ASCII) side by side so the user can see exactly what was on the
wire: unit ID, function code, address, data bytes, CRC/LRC, and exception codes.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent

from modbus_meta import FUNCTION_NAMES

_EXCEPTION_NAMES = {
    0x01: "Illegal Function",
    0x02: "Illegal Data Address",
    0x03: "Illegal Data Value",
    0x04: "Server Device Failure",
    0x05: "Acknowledge",
    0x06: "Server Device Busy",
    0x07: "Memory Parity Error",
    0x0A: "Gateway Path Unavailable",
    0x0B: "Gateway Target Device Failed to Respond",
}


def _decode_modbus_frame(data_bytes, transport):
    """Decode a raw Modbus frame captured by pymodbus's trace_packet hook.

    transport is one of "tcp", "rtu", or "ascii" — the same values used by the app.
    Returns a dict with at minimum:
        - direction: "TX" or "RX"
        - raw_hex: full frame as space-separated hex
        - raw_bytes: the original bytes
        - success: bool
        - error: None or a short description string
      And one or more of:
        - fields: dict of field_name -> (value, sub_value) tuples for the key-value UI
        - pdu_hex: PDU portion as hex (for hex dump footer)
        - exception_code: numeric exception code (RX only, when function code has bit 7 set)
    """
    if not data_bytes:
        return {
            "direction": "",
            "raw_hex": "",
            "raw_bytes": b"",
            "success": False,
            "error": "No frame data",
            "fields": [],
            "pdu_hex": "",
        }

    raw = bytes(data_bytes)
    result = {
        "direction": "",
        "raw_hex": raw.hex(" ").upper(),
        "raw_bytes": raw,
        "success": True,
        "error": None,
        "fields": [],
        "pdu_hex": "",
        "exception_code": None,
    }

    if transport == "tcp":
        _decode_tcp(raw, result)
    elif transport == "ascii":
        _decode_ascii(raw, result)
    else:
        _decode_rtu(raw, result)

    return result


def _decode_tcp(raw, result):
    """MBAP header (7 bytes) + PDU. pymodbus's trace_packet for TCP emits the full MBAP frame."""
    result["direction"] = "TCP"
    if len(raw) < 7:
        result["success"] = False
        result["error"] = f"Too short for TCP ({len(raw)} bytes, need >= 7)"
        return

    transaction_id = int.from_bytes(raw[0:2], "big")
    protocol_id = int.from_bytes(raw[2:4], "big")
    length = int.from_bytes(raw[4:6], "big")
    unit_id = raw[6]

    result["fields"] = [
        ("Transaction ID", f"{transaction_id} ({transaction_id & 0xFFFF:04X})"),
        ("Protocol ID", f"{protocol_id} (0x{protocol_id:04X})"),
        ("Length", f"{length} bytes (Unit + PDU)"),
        ("Unit ID", f"{unit_id} (0x{unit_id:02X})"),
    ]

    pdu = raw[7:]
    result["pdu_hex"] = pdu.hex(" ").upper() if pdu else ""
    _decode_pdu(pdu, result)


def _decode_rtu(raw, result):
    """RTU frame: Unit ID (1 byte) + PDU (N bytes) + CRC (2 bytes, little-endian)."""
    result["direction"] = "RTU"
    if len(raw) < 4:
        result["success"] = False
        result["error"] = f"Too short for RTU ({len(raw)} bytes, need >= 4)"
        return

    unit_id = raw[0]
    pdu = raw[1:-2]
    crc_lo, crc_hi = raw[-2], raw[-1]

    result["fields"] = [
        ("Unit ID", f"{unit_id} (0x{unit_id:02X})"),
        ("CRC", f"{crc_hi:02X}{crc_lo:02X} (0x{crc_hi:02X}{crc_lo:02X})"),
    ]
    result["pdu_hex"] = pdu.hex(" ").upper() if pdu else ""
    _decode_pdu(pdu, result)


def _decode_ascii(raw, result):
    """ASCII frame: ':' (1) + Unit ID (2 ASCII hex chars) + PDU (N*2 ASCII chars) + LRC (2 ASCII) + CR LF (2).
    pymodbus's trace_packet emits the raw ASCII string bytes, not decoded characters."""
    result["direction"] = "ASCII"

    # Decode the ASCII representation to get the logical bytes
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        result["success"] = False
        result["error"] = "Non-ASCII bytes in ASCII frame"
        return

    if not text.startswith(":"):
        result["success"] = False
        result["error"] = "Missing leading ':'"
        return

    inner = text[1:]  # strip leading colon
    if len(inner) < 6:
        result["success"] = False
        result["error"] = f"Too short for ASCII ({len(inner)} chars, need >= 6)"
        return

    # The last 4 chars are LRC (2 hex chars) + CR + LF (or just LRC if stripped)
    # Strip trailing CR/LF if present
    inner = inner.rstrip("\r\n")
    if len(inner) < 4:
        result["success"] = False
        result["error"] = f"Too short after stripping CR/LF ({len(inner)} chars)"
        return

    lrc_str = inner[-2:]
    unit_and_pdu = inner[:-2]

    if len(unit_and_pdu) < 2:
        result["success"] = False
        result["error"] = "No unit ID or PDU"
        return

    unit_id = int(unit_and_pdu[:2], 16)
    pdu_hex_str = unit_and_pdu[2:]

    try:
        pdu_bytes = bytes.fromhex(pdu_hex_str)
    except ValueError:
        result["success"] = False
        result["error"] = f"Invalid hex in PDU: {pdu_hex_str}"
        return

    result["fields"] = [
        ("Unit ID", f"{unit_id} (0x{unit_id:02X})"),
        ("LRC", f"{lrc_str.upper()} (0x{int(lrc_str, 16):02X})"),
    ]
    result["pdu_hex"] = pdu_bytes.hex(" ").upper() if pdu_bytes else ""
    _decode_pdu(pdu_bytes, result)


def _decode_pdu(pdu, result):
    """Decode the PDU portion (function code + data) common to all transports."""
    if not pdu:
        result["error"] = "Empty PDU"
        result["success"] = False
        return

    fc_byte = pdu[0]
    is_exception = (fc_byte & 0x80) != 0
    normal_fc = fc_byte & 0x7F

    fc_name = FUNCTION_NAMES.get(normal_fc, f"FC 0x{normal_fc:02X}")
    if is_exception:
        fc_display = f"0x{fc_byte:02X} ({fc_name}, Exception)"
    else:
        fc_display = f"0x{fc_byte:02X} ({fc_name})"

    data = pdu[1:]

    result["fields"].append(("Function Code", fc_display))

    if is_exception and data:
        exc_code = data[0]
        exc_name = _EXCEPTION_NAMES.get(exc_code, f"Exception 0x{exc_code:02X}")
        result["exception_code"] = exc_code
        result["fields"].append(("Exception", f"0x{exc_code:02X} — {exc_name}"))
        result["success"] = False
        result["error"] = exc_name
    elif data:
        result["fields"].append(("Data", data.hex(" ").upper()))
    else:
        result["fields"].append(("Data", "(none)"))


def _make_widget(colors, label, value, accent_color=None):
    """Create a label/value row for the frame viewer."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    lbl = QLabel(label)
    lbl.setStyleSheet(f"color: {accent_color or colors['accent']}; font-weight: 600; font-size: 11px;")
    lbl.setMinimumWidth(100)

    val = QLabel(value)
    val.setStyleSheet(f"color: {colors['text']}; font-size: 11px; font-family: 'Consolas', 'Monaco', monospace;")
    val.setWordWrap(True)

    row.addWidget(lbl)
    row.addWidget(val)
    row.addStretch()
    return row


def _make_hex_dump(colors, hex_str, label="Hex Dump"):
    """Create a hex dump footer showing the raw frame bytes."""
    group = QFrame()
    group.setStyleSheet(f"""
        QFrame {{
            background-color: {colors['surface_alt']};
            border: 1px solid {colors['border']};
            border-radius: 3px;
        }}
    """)
    layout = QVBoxLayout(group)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(2)

    header = QLabel(f"{label}")
    header.setStyleSheet(f"color: {colors['text_dim']}; font-size: 10px; font-weight: 600;")
    layout.addWidget(header)

    dump = QLabel(hex_str if hex_str else "(empty)")
    dump.setStyleSheet(f"""
        color: {colors['text_secondary']};
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 11px;
        padding: 2px 0;
    """)
    dump.setWordWrap(True)
    layout.addWidget(dump)

    return group


class FrameViewerDialog(QDialog):
    """Floating popup that decodes and displays the TX/RX Modbus frame for one raw data row."""

    closed = Signal()

    def __init__(self, parent, tx_bytes, rx_bytes, transport, row_index):
        super().__init__(parent)
        self.transport = transport
        self.row_index = row_index

        # Store decoded data for later reference
        self.tx_decoded = _decode_modbus_frame(tx_bytes, transport)
        self.rx_decoded = _decode_modbus_frame(rx_bytes, transport)

        # Window flags: no title bar, stays on top, tool window so it doesn't clutter the taskbar
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        colors = parent._colors() if hasattr(parent, "_colors") else {}
        self._colors = colors
        self._tx_color = colors.get("log_write", "#1565C0")
        self._rx_success_color = colors.get("log_connect", "#2E7D32")
        self._rx_fail_color = colors.get("log_error", "#C62828")

        self._setup_ui()

        # Click-outside-to-close: install an event filter on the parent
        if parent is not None:
            parent.installEventFilter(self)

    def _setup_ui(self):
        """Build the TX | RX panel layout."""
        c = self._colors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Title bar
        title = QLabel("Modbus Frame Viewer")
        title.setStyleSheet(f"""
            font-size: 13px;
            font-weight: bold;
            color: {c['heading']};
            padding-bottom: 4px;
            border-bottom: 1px solid {c['border']};
        """)
        layout.addWidget(title)

        # Transport badge
        badge = QLabel(self.transport.upper())
        badge.setStyleSheet(f"""
            background-color: {c['surface_alt']};
            color: {c['accent']};
            border: 1px solid {c['border']};
            border-radius: 3px;
            padding: 2px 8px;
            font-size: 10px;
            font-weight: 600;
        """)
        layout.addWidget(badge)

        # TX | RX split
        split = QHBoxLayout()
        split.setSpacing(10)

        tx_panel = self._build_panel("TX", self.tx_decoded, self._tx_color)
        rx_panel = self._build_panel("RX", self.rx_decoded, self._rx_success_color if self.rx_decoded["success"] else self._rx_fail_color)

        split.addWidget(tx_panel, 1)
        split.addWidget(rx_panel, 1)
        layout.addLayout(split)

        # Set minimum size
        self.setMinimumWidth(420)
        self.setMaximumWidth(640)

    def _build_panel(self, direction, decoded, accent_color):
        """Build a single TX or RX panel with fields and hex dump."""
        panel = QFrame()
        panel.setStyleSheet(f"""
            QFrame {{
                background-color: {self._colors['surface']};
                border: 1px solid {accent_color};
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Direction header
        dir_label = QLabel(direction)
        dir_label.setStyleSheet(f"""
            font-size: 12px;
            font-weight: bold;
            color: {accent_color};
            padding: 2px 0;
        """)
        layout.addWidget(dir_label)

        # Status indicator
        if decoded.get("error"):
            status = QLabel(f"  {decoded['error']}")
            status.setStyleSheet(f"color: {self._colors['log_error']}; font-size: 10px; font-style: italic;")
            layout.addWidget(status)
        elif decoded["success"] and direction == "RX":
            status = QLabel("  OK")
            status.setStyleSheet(f"color: {self._colors['log_connect']}; font-size: 10px; font-weight: 600;")
            layout.addWidget(status)

        # Field rows
        for label, value in decoded.get("fields", []):
            row = _make_widget(self._colors, label, value, accent_color)
            layout.addLayout(row)

        layout.addStretch()

        # Hex dump footer
        if decoded.get("pdu_hex") or decoded.get("raw_hex"):
            hex_str = decoded.get("pdu_hex", "") or decoded.get("raw_hex", "")
            hex_label = f"Hex — {direction}"
            dump = _make_hex_dump(self._colors, hex_str, hex_label)
            layout.addWidget(dump)

        return panel

    def _position_popup(self, parent):
        """Position the popup near the bottom-right of the parent window."""
        if parent is None:
            self.move(100, 100)
            return

        geo = parent.geometry()
        popup_w = min(560, geo.width() // 2)
        popup_h = 320

        x = geo.right() - popup_w - 16
        y = geo.bottom() - popup_h - 80
        # Keep within screen bounds
        screen = parent.screen()
        if screen is not None:
            sg = screen.availableGeometry()
            x = max(sg.left(), min(x, sg.right() - popup_w))
            y = max(sg.top(), min(y, sg.bottom() - popup_h))

        self.setGeometry(x, y, popup_w, popup_h)

    def closeEvent(self, event):
        """Clean up event filter when closed and notify the owner."""
        if self.parent() is not None:
            try:
                self.parent().removeEventFilter(self)
            except Exception:
                pass
        self.closed.emit()
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        """Close when the user clicks anywhere outside this popup."""
        if event.type() == QMouseEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            if self.isVisible() and obj != self:
                global_pos = self.mapFromGlobal(event.globalPos())
                if not self.rect().contains(global_pos):
                    self.close()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Close on Escape."""
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
