"""Integrated Modbus frame viewer panel — shown below the Raw Data table.

When the user clicks a row in the Raw Data table, this panel decodes and displays
the TX and RX Modbus frames (MBAP for TCP, RTU, or LRC for ASCII) side by side
so the user can see exactly what was on the wire: unit ID, function code, data
bytes, CRC/LRC, and exception codes.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

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

    transport is one of "tcp", "rtu", or "ascii".
    Returns a dict with fields, error, success, raw_hex, pdu_hex, exception_code.
    """
    if not data_bytes:
        return {
            "fields": [], "error": "No frame data", "success": False,
            "raw_hex": "", "pdu_hex": "", "exception_code": None,
        }

    raw = bytes(data_bytes)
    result = {
        "fields": [], "error": None, "success": True,
        "raw_hex": raw.hex(" ").upper(), "pdu_hex": "", "exception_code": None,
    }

    if transport == "tcp":
        _decode_tcp(raw, result)
    elif transport == "ascii":
        _decode_ascii(raw, result)
    else:
        _decode_rtu(raw, result)

    return result


def _decode_tcp(raw, result):
    """MBAP header (7 bytes) + PDU."""
    if len(raw) < 7:
        result["success"] = False
        result["error"] = f"Too short for TCP ({len(raw)} bytes)"
        return
    transaction_id = int.from_bytes(raw[0:2], "big")
    protocol_id = int.from_bytes(raw[2:4], "big")
    length = int.from_bytes(raw[4:6], "big")
    unit_id = raw[6]
    result["fields"] = [
        ("Transaction ID", str(transaction_id)),
        ("Protocol ID", str(protocol_id)),
        ("Length", f"{length} bytes"),
        ("Unit ID", str(unit_id)),
    ]
    pdu = raw[7:]
    result["pdu_hex"] = pdu.hex(" ").upper() if pdu else ""
    _decode_pdu(pdu, result)


def _decode_rtu(raw, result):
    """RTU frame: Unit ID (1) + PDU (N) + CRC (2)."""
    if len(raw) < 4:
        result["success"] = False
        result["error"] = f"Too short for RTU ({len(raw)} bytes)"
        return
    unit_id = raw[0]
    pdu = raw[1:-2]
    crc_lo, crc_hi = raw[-2], raw[-1]
    result["fields"] = [
        ("Unit ID", str(unit_id)),
        ("CRC", f"{crc_hi:02X}{crc_lo:02X}"),
    ]
    result["pdu_hex"] = pdu.hex(" ").upper() if pdu else ""
    _decode_pdu(pdu, result)


def _decode_ascii(raw, result):
    """ASCII frame: ':' + Unit ID (2 hex chars) + PDU + LRC (2 hex chars) + CR LF."""
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        result["success"] = False
        result["error"] = "Non-ASCII bytes"
        return
    if not text.startswith(":"):
        result["success"] = False
        result["error"] = "Missing ':'"
        return
    inner = text[1:].rstrip("\r\n")
    if len(inner) < 4:
        result["success"] = False
        result["error"] = "Too short for ASCII"
        return
    lrc_str = inner[-2:]
    unit_and_pdu = inner[:-2]
    if len(unit_and_pdu) < 2:
        result["success"] = False
        result["error"] = "No unit ID or PDU"
        return
    unit_id = int(unit_and_pdu[:2], 16)
    try:
        pdu_bytes = bytes.fromhex(unit_and_pdu[2:])
    except ValueError:
        result["success"] = False
        result["error"] = "Invalid PDU hex"
        return
    result["fields"] = [
        ("Unit ID", str(unit_id)),
        ("LRC", lrc_str.upper()),
    ]
    result["pdu_hex"] = pdu_bytes.hex(" ").upper() if pdu_bytes else ""
    _decode_pdu(pdu_bytes, result)


def _decode_pdu(pdu, result):
    """Decode PDU: function code + data (or exception)."""
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


class FrameViewerPanel(QWidget):
    """Integrated panel shown below the Raw Data table, decoding the selected row's
    TX and RX Modbus frames into clean side-by-side table panels."""

    def __init__(self, parent):
        super().__init__(parent)
        self._colors = parent._colors() if hasattr(parent, "_colors") else {}
        self._transport = "tcp"
        self._setup_ui()

    def _setup_ui(self):
        c = self._colors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(0)

        # Section header
        header = QFrame()
        header.setStyleSheet(f"background-color: {c['header_bg']}; border-top: 1px solid {c['border']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 5, 10, 5)
        h_layout.setSpacing(8)
        title = QLabel("Frame Viewer")
        title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {c['heading']};")
        h_layout.addWidget(title)
        self._transport_label = QLabel("(—)")
        self._transport_label.setStyleSheet(f"font-size: 10px; color: {c['text_dim']};")
        h_layout.addWidget(self._transport_label)
        h_layout.addStretch()
        layout.addWidget(header)

        # Placeholder text
        self._placeholder = QLabel(
            "Click any row in the Raw Data table above to view the decoded Modbus frames."
        )
        self._placeholder.setStyleSheet(f"""
            color: {c['text_dim']};
            font-size: 11px;
            padding: 20px;
            text-align: center;
        """)
        self._placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._placeholder)

        # TX | RX split (hidden until a row is selected)
        self._split = QHBoxLayout()
        self._split.setSpacing(0)
        self._tx_panel = self._build_empty_panel("TX")
        self._rx_panel = self._build_empty_panel("RX")
        self._split.addWidget(self._tx_panel)
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet(f"background-color: {c['border']};")
        self._split.addWidget(div)
        self._split.addWidget(self._rx_panel)

        self._body = QFrame()
        self._body.setStyleSheet(f"background-color: {c['surface']};")
        self._body.setLayout(self._split)
        self._body.setVisible(False)
        layout.addWidget(self._body)

        # Hex footer
        self._hex_footer = QFrame()
        self._hex_footer.setStyleSheet(f"""
            QFrame {{
                background-color: {c['surface_alt']};
                border-top: 1px solid {c['border']};
            }}
        """)
        hf_layout = QVBoxLayout(self._hex_footer)
        hf_layout.setContentsMargins(10, 6, 10, 8)
        hf_layout.setSpacing(3)
        self._hex_title = QLabel("Raw Hex")
        self._hex_title.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {c['text_dim']};")
        hf_layout.addWidget(self._hex_title)
        self._hex_tx = QLabel("TX:  —")
        self._hex_tx.setStyleSheet(f"color: {c['text_secondary']}; font-family: 'Consolas', 'Monaco', monospace; font-size: 10px;")
        hf_layout.addWidget(self._hex_tx)
        self._hex_rx = QLabel("RX:  —")
        self._hex_rx.setStyleSheet(f"color: {c['text_secondary']}; font-family: 'Consolas', 'Monaco', monospace; font-size: 10px;")
        hf_layout.addWidget(self._hex_rx)
        self._hex_footer.setVisible(False)
        layout.addWidget(self._hex_footer)

    def _build_empty_panel(self, direction):
        c = self._colors
        panel = QFrame()
        panel.setStyleSheet(f"background-color: {c['surface']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)
        dir_label = QLabel(direction)
        dir_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: {c['text_dim']};
            padding: 0 0 4px 0;
            border-bottom: 1px solid {c['border_light']};
        """)
        layout.addWidget(dir_label)
        placeholder = QLabel("—")
        placeholder.setStyleSheet(f"color: {c['text_dim']}; font-size: 11px; padding: 10px 0;")
        layout.addWidget(placeholder)
        layout.addStretch()
        return panel

    def _build_table_panel(self, direction, decoded):
        c = self._colors
        panel = QFrame()
        panel.setStyleSheet(f"background-color: {c['surface']};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(0)

        dir_label = QLabel(direction)
        dir_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 600;
            color: {c['text_dim']};
            padding: 0 0 4px 0;
            border-bottom: 1px solid {c['border_light']};
        """)
        layout.addWidget(dir_label)

        if decoded.get("error"):
            status = QLabel(f"  {decoded['error']}")
            status.setStyleSheet(f"color: {c['log_error']}; font-size: 10px; padding: 3px 0;")
            layout.addWidget(status)
        elif decoded["success"] and direction == "RX":
            status = QLabel("  OK")
            status.setStyleSheet(f"color: {c['log_connect']}; font-size: 10px; padding: 3px 0;")
            layout.addWidget(status)

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

    def update_from_row(self, table, row, transport="tcp"):
        """Decode and display the TX/RX frames for the given raw data table row."""
        if table is None or row < 0 or row >= table.rowCount():
            return
        self._transport = transport
        self._transport_label.setText(f"({transport.upper()})")

        tx_text = table.item(row, 4).text() if row < table.columnCount() else ""
        rx_text = table.item(row, 5).text() if row < table.columnCount() else ""

        tx_bytes = self._parse_hex_bytes(tx_text) if tx_text else None
        rx_bytes = self._parse_hex_bytes(rx_text) if rx_text else None

        tx_decoded = _decode_modbus_frame(tx_bytes, transport)
        rx_decoded = _decode_modbus_frame(rx_bytes, transport)

        self._tx_panel = self._build_table_panel("TX", tx_decoded)
        self._rx_panel = self._build_table_panel("RX", rx_decoded)

        # Rebuild the split layout
        old_split = self._split
        new_split = QHBoxLayout()
        new_split.setSpacing(0)
        new_split.addWidget(self._tx_panel)
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet(f"background-color: {self._colors['border']};")
        new_split.addWidget(div)
        new_split.addWidget(self._rx_panel)

        self._body.setLayout(new_split)

        # Update hex footer
        tx_hex = tx_decoded.get("raw_hex", "") or "(none)"
        rx_hex = rx_decoded.get("raw_hex", "") or "(none)"
        self._hex_tx.setText(f"TX:  {tx_hex}")
        self._hex_rx.setText(f"RX:  {rx_hex}")

        self._placeholder.setVisible(False)
        self._body.setVisible(True)
        self._hex_footer.setVisible(True)

    @staticmethod
    def _parse_hex_bytes(text):
        if not text:
            return None
        cleaned = text.strip().replace(" ", "").replace("-", "")
        if len(cleaned) < 2 or len(cleaned) % 2 != 0:
            return None
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            return None

    def clear(self):
        """Clear the panel back to placeholder state."""
        self._tx_panel = self._build_empty_panel("TX")
        self._rx_panel = self._build_empty_panel("RX")
        old_split = self._split
        new_split = QHBoxLayout()
        new_split.setSpacing(0)
        new_split.addWidget(self._tx_panel)
        div = QFrame()
        div.setFrameShape(QFrame.VLine)
        div.setFrameShadow(QFrame.Sunken)
        div.setStyleSheet(f"background-color: {self._colors['border']};")
        new_split.addWidget(div)
        new_split.addWidget(self._rx_panel)
        self._body.setLayout(new_split)

        self._transport_label.setText("(—)")
        self._hex_tx.setText("TX:  —")
        self._hex_rx.setText("RX:  —")
        self._placeholder.setVisible(True)
        self._body.setVisible(False)
        self._hex_footer.setVisible(False)


from PySide6.QtCore import Qt
