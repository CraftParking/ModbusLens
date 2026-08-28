"""Integrated Modbus frame viewer panel — shown below the Raw Data table.

When the user clicks a row in the Raw Data table, this panel decodes and displays
the TX and RX Modbus frames (MBAP for TCP, RTU, or LRC for ASCII) side by side
so the user can see exactly what was on the wire: unit ID, function code, data
bytes, CRC/LRC, and exception codes.
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QWidget, QSizePolicy,
)
from PySide6.QtGui import QColor
from PySide6.QtCore import Qt

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

PLACEHOLDER_TEXT = "Click any row in the Raw Data table above to view its decoded TX/RX frames."


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
    TX and RX Modbus frames into clean side-by-side table panels.

    Styled as a QGroupBox (like "Monitoring Controls", "Tags", etc. elsewhere in the
    app) rather than hand-rolled QFrames, so it matches the rest of the UI instead of
    looking like a bolted-on widget."""

    def __init__(self, parent):
        super().__init__(parent)
        self._main_window = parent
        self._colors = parent._colors() if hasattr(parent, "_colors") else {}
        self._transport = "tcp"
        self._setup_ui()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _setup_ui(self):
        c = self._colors
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 0)

        self._group = QGroupBox("Frame Viewer")
        if hasattr(self._main_window, "_get_groupbox_style"):
            self._group.setStyleSheet(self._main_window._get_groupbox_style())
        outer.addWidget(self._group)

        layout = QVBoxLayout(self._group)
        layout.setContentsMargins(15, 20, 15, 15)
        layout.setSpacing(8)

        self._status_label = QLabel(PLACEHOLDER_TEXT)
        self._status_label.setStyleSheet(f"color: {c['text_dim']}; font-size: 11px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # TX | RX side by side. Each side is a persistent container with its own
        # layout that gets cleared and repopulated on every row click -- never
        # replaced -- since Qt silently refuses a second setLayout() on a widget
        # that already has one.
        split = QHBoxLayout()
        split.setSpacing(15)
        self._tx_container, self._tx_layout = self._build_side_container()
        self._rx_container, self._rx_layout = self._build_side_container()
        split.addWidget(self._tx_container, 1)
        split.addWidget(self._rx_container, 1)
        layout.addLayout(split)
        self._tx_container.setVisible(False)
        self._rx_container.setVisible(False)

        # Raw hex footer
        self._hex_tx = QLabel("")
        self._hex_tx.setStyleSheet(
            f"color: {c['text_secondary']}; font-family: 'Consolas', 'Monaco', monospace; font-size: 10px;"
        )
        self._hex_tx.setWordWrap(True)
        self._hex_rx = QLabel("")
        self._hex_rx.setStyleSheet(
            f"color: {c['text_secondary']}; font-family: 'Consolas', 'Monaco', monospace; font-size: 10px;"
        )
        self._hex_rx.setWordWrap(True)
        self._hex_tx.setVisible(False)
        self._hex_rx.setVisible(False)
        layout.addWidget(self._hex_tx)
        layout.addWidget(self._hex_rx)

    def _build_side_container(self):
        container = QWidget()
        inner = QVBoxLayout(container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(4)
        return container, inner

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _populate_side(self, layout, direction, decoded):
        c = self._colors

        dir_label = QLabel(direction)
        dir_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {c['heading']};")
        layout.addWidget(dir_label)

        if decoded.get("error"):
            status = QLabel(decoded["error"])
            status.setStyleSheet(f"color: {c['log_error']}; font-size: 10px;")
            status.setWordWrap(True)
            layout.addWidget(status)
        elif decoded["success"] and direction == "RX":
            status = QLabel("OK")
            status.setStyleSheet(f"color: {c['log_connect']}; font-size: 10px;")
            layout.addWidget(status)

        fields = decoded.get("fields", [])
        table = QTableWidget(len(fields), 2)
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
                border: 1px solid {c['border']};
                gridline-color: {c['border_light']};
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
            QHeaderView::section {{
                background-color: {c['header_bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                padding: 3px 6px;
                font-size: 10px;
                font-weight: 600;
            }}
        """)

        for i, (label, value) in enumerate(fields):
            lbl = QTableWidgetItem(label)
            lbl.setForeground(QColor(c['text_dim']))
            val = QTableWidgetItem(value)
            if label == "Function Code" and "Exception" in value:
                val.setForeground(QColor(c['log_error']))
            table.setItem(i, 0, lbl)
            table.setItem(i, 1, val)

        table.verticalHeader().setDefaultSectionSize(24)
        row_height = table.verticalHeader().defaultSectionSize()
        table.setFixedHeight(table.horizontalHeader().height() + max(len(fields), 1) * row_height + 4)
        layout.addWidget(table)

    def update_from_row(self, table, row, transport="tcp"):
        """Decode and display the TX/RX frames for the given raw data table row."""
        if table is None or row < 0 or row >= table.rowCount():
            return
        self._transport = transport
        self._status_label.setText(f"Transport: {transport.upper()}")

        tx_text = table.item(row, 4).text() if table.item(row, 4) else ""
        rx_text = table.item(row, 5).text() if table.item(row, 5) else ""

        tx_bytes = self._parse_hex_bytes(tx_text) if tx_text else None
        rx_bytes = self._parse_hex_bytes(rx_text) if rx_text else None

        tx_decoded = _decode_modbus_frame(tx_bytes, transport)
        rx_decoded = _decode_modbus_frame(rx_bytes, transport)

        self._clear_layout(self._tx_layout)
        self._clear_layout(self._rx_layout)
        self._populate_side(self._tx_layout, "TX", tx_decoded)
        self._populate_side(self._rx_layout, "RX", rx_decoded)
        self._tx_container.setVisible(True)
        self._rx_container.setVisible(True)

        tx_hex = tx_decoded.get("raw_hex", "") or "(none)"
        rx_hex = rx_decoded.get("raw_hex", "") or "(none)"
        self._hex_tx.setText(f"TX:  {tx_hex}")
        self._hex_rx.setText(f"RX:  {rx_hex}")
        self._hex_tx.setVisible(True)
        self._hex_rx.setVisible(True)

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
        self._clear_layout(self._tx_layout)
        self._clear_layout(self._rx_layout)
        self._tx_container.setVisible(False)
        self._rx_container.setVisible(False)
        self._hex_tx.setVisible(False)
        self._hex_rx.setVisible(False)
        self._status_label.setText(PLACEHOLDER_TEXT)
