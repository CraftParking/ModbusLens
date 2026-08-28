"""Modbus frame viewer — decode raw TX/RX bytes into human-readable frame fields.

When the user clicks any cell in the Raw Data table, this module shows a floating
popup that decodes the transaction's TX and RX frames (MBAP for TCP, RTU for serial
RTU, LRC for serial ASCII) side by side so the user can see exactly what was on the
wire: unit ID, function code, address, data bytes, CRC/LRC, and exception codes.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QApplication, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, Signal, QEvent, QObject
from PySide6.QtGui import QColor, QMouseEvent, QFont

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
        ("Transaction ID", f"{transaction_id}"),
        ("Protocol ID", f"{protocol_id}"),
        ("Length", f"{length}"),
        ("Unit ID", f"{unit_id}"),
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
        ("Unit ID", f"{unit_id}"),
        ("CRC", f"{crc_hi:02X}{crc_lo:02X}"),
    ]
    result["pdu_hex"] = pdu.hex(" ").upper() if pdu else ""
    _decode_pdu(pdu, result)


def _decode_ascii(raw, result):
    """ASCII frame: ':' (1) + Unit ID (2 ASCII hex chars) + PDU (N*2 ASCII chars) + LRC (2 ASCII) + CR LF (2).
    pymodbus's trace_packet emits the raw ASCII string bytes, not decoded characters."""
    result["direction"] = "ASCII"

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

    inner = text[1:]
    if len(inner) < 6:
        result["success"] = False
        result["error"] = f"Too short for ASCII ({len(inner)} chars, need >= 6)"
        return

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
        ("Unit ID", f"{unit_id}"),
        ("LRC", lrc_str.upper()),
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
        fc_display = f"{fc_name} (Exception)"
    else:
        fc_display = fc_name

    data = pdu[1:]

    result["fields"].append(("Function Code", fc_display))

    if is_exception and data:
        exc_code = data[0]
        exc_name = _EXCEPTION_NAMES.get(exc_code, f"Exception 0x{exc_code:02X}")
        result["exception_code"] = exc_code
        result["fields"].append(("Exception", exc_name))
        result["success"] = False
        result["error"] = exc_name
    elif data:
        result["fields"].append(("Data", data.hex(" ").upper()))
    else:
        result["fields"].append(("Data", "(none)"))


class _OutsideClickFilter(QObject):
    """Installs on QApplication to close the frame viewer when clicking outside it."""

    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.LeftButton
                and self._dialog.isVisible()):
            pos = self._dialog.mapFromGlobal(event.globalPos())
            if not self._dialog.rect().contains(pos):
                self._dialog.close()
                return True
        return super().eventFilter(obj, event)


class FrameViewerDialog(QDialog):
    """Floating popup that decodes and displays the TX/RX Modbus frame for one raw data row."""

    closed = Signal()

    def __init__(self, parent, tx_bytes, rx_bytes, transport, row_index):
        super().__init__(parent)
        self.transport = transport
        self.row_index = row_index

        self.tx_decoded = _decode_modbus_frame(tx_bytes, transport)
        self.rx_decoded = _decode_modbus_frame(rx_bytes, transport)

        # Solid bordered window, no title bar, stays on top
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        colors = parent._colors() if hasattr(parent, "_colors") else {}
        self._colors = colors

        self._setup_ui()
        self._position_popup(parent)

        self._outside_filter = _OutsideClickFilter(self)
        QApplication.instance().installEventFilter(self._outside_filter)

    def _setup_ui(self):
        """Build the popup: header bar + TX/RX table panels + hex footer."""
        c = self._colors

        # Main border around the entire dialog
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {c['surface']};
                border: 2px solid #000000;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Header bar ---
        header = QFrame()
        header.setStyleSheet(f"background-color: {c['header_bg']}; border-bottom: 1px solid {c['border']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)
        h_layout.setSpacing(10)

        title = QLabel("Frame Viewer")
        title.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {c['heading']};")
        h_layout.addWidget(title)

        badge = QLabel(self.transport.upper())
        badge.setStyleSheet(f"""
            background-color: {c['surface']};
            color: {c['text_dim']};
            border: 1px solid {c['border']};
            padding: 1px 8px;
            font-size: 10px;
            font-weight: 600;
        """)
        h_layout.addWidget(badge)
        h_layout.addStretch()

        close_btn = QLabel("\u2715")
        close_btn.setStyleSheet(f"font-size: 12px; color: {c['text_dim']};")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.mousePressEvent = lambda e: self.close()
        h_layout.addWidget(close_btn)

        layout.addWidget(header)

        # --- TX | RX table panels ---
        split = QHBoxLayout()
        split.setSpacing(0)

        tx_panel = self._build_table_panel("TX", self.tx_decoded)
        rx_panel = self._build_table_panel("RX", self.rx_decoded)

        split.addWidget(tx_panel, 1)
        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet(f"background-color: {c['border']};")
        split.addWidget(div)
        split.addWidget(rx_panel, 1)

        body = QFrame()
        body.setStyleSheet(f"background-color: {c['surface']};")
        body.setLayout(split)
        layout.addWidget(body, 1)

        # --- Hex dump footer ---
        footer = self._build_hex_footer()
        layout.addWidget(footer)

        self.setMinimumSize(500, 340)

    def _build_table_panel(self, direction, decoded):
        """Build a TX or RX panel as a clean table widget."""
        c = self._colors
        panel = QFrame()
        panel.setStyleSheet(f"background-color: {c['surface']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)

        # Direction label
        dir_label = QLabel(direction)
        dir_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: {c['text_dim']};
            padding: 0 0 4px 0;
            border-bottom: 1px solid {c['border_light']};
        """)
        layout.addWidget(dir_label)

        # Status row
        if decoded.get("error"):
            status = QLabel(f"  {decoded['error']}")
            status.setStyleSheet(f"color: {c['log_error']}; font-size: 10px; padding: 3px 0;")
            layout.addWidget(status)
        elif decoded["success"] and direction == "RX":
            status = QLabel("  OK")
            status.setStyleSheet(f"color: {c['log_connect']}; font-size: 10px; padding: 3px 0;")
            layout.addWidget(status)

        # Table for decoded fields
        table = QTableWidget(len(decoded.get("fields", [])), 2)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setHorizontalHeaderLabels(["Field", "Value"])
        table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c['surface']};
                color: {c['text']};
                border: none;
                gridline-color: {c['border_light']};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                padding: 2px 0;
            }}
            QHeaderView::section {{
                background-color: {c['header_bg']};
                color: {c['text']};
                border: none;
                border-bottom: 1px solid {c['border']};
                padding: 3px 6px;
                font-size: 10px;
                font-weight: 600;
            }}
            QTableWidget::item {{
                padding: 4px 6px;
                border-bottom: 1px solid {c['border_light']};
            }}
        """)

        for i, (label, value) in enumerate(decoded.get("fields", [])):
            lbl = QTableWidgetItem(label)
            lbl.setForeground(QColor(c['text_dim']))
            lbl.setFont(QFont('Consolas', 10))
            val = QTableWidgetItem(value)
            val.setFont(QFont('Consolas', 10))
            if label == "Function Code" and "Exception" in value:
                val.setForeground(QColor(c['log_error']))
            table.setItem(i, 0, lbl)
            table.setItem(i, 1, val)

        table.verticalHeader().setDefaultSectionSize(26)
        layout.addWidget(table)
        layout.addStretch()

        return panel

    def _build_hex_footer(self):
        """Build the hex dump footer as a clean monospace table."""
        c = self._colors
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {c['surface_alt']};
                border-top: 1px solid {c['border']};
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(4)

        title = QLabel("Raw Hex")
        title.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {c['text_dim']};")
        layout.addWidget(title)

        # TX hex
        tx_line = QLabel(f"TX:  {self.tx_decoded.get('raw_hex', '(none)')}")
        tx_line.setStyleSheet(f"""
            color: {c['text_secondary']};
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 10px;
        """)
        layout.addWidget(tx_line)

        # RX hex
        rx_line = QLabel(f"RX:  {self.rx_decoded.get('raw_hex', '(none)')}")
        rx_line.setStyleSheet(f"""
            color: {c['text_secondary']};
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 10px;
        """)
        layout.addWidget(rx_line)

        return frame

    def _position_popup(self, parent):
        """Position the popup near the bottom-right of the parent window."""
        if parent is None:
            self.move(100, 100)
            return

        geo = parent.geometry()
        popup_w = min(600, geo.width() // 2)
        popup_h = 360

        x = geo.right() - popup_w - 16
        y = geo.bottom() - popup_h - 80
        screen = parent.screen()
        if screen is not None:
            sg = screen.availableGeometry()
            x = max(sg.left(), min(x, sg.right() - popup_w))
            y = max(sg.top(), min(y, sg.bottom() - popup_h))

        self.setGeometry(x, y, popup_w, popup_h)

    def closeEvent(self, event):
        """Clean up app-level event filter when closed and notify the owner."""
        app = QApplication.instance()
        if app is not None and hasattr(self, '_outside_filter'):
            try:
                app.removeEventFilter(self._outside_filter)
            except Exception:
                pass
        self.closed.emit()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        """Close on Escape."""
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
