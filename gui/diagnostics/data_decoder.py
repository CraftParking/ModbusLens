from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

BYTE_ORDER_LABELS = [
    "ABCD (big-endian, normal Modbus)",
    "BADC (byte-swap within each register)",
    "CDAB (word-swap across registers)",
    "DCBA (byte-swap + word-swap)",
]
BYTE_ORDER_CODES = ["ABCD", "BADC", "CDAB", "DCBA"]


def parse_hex_bytes(text):
    """Parse a free-form hex string -- spaces, commas, newlines, and 0x/0X prefixes are
    all tolerated so "41 48 00 00", "0x41,0x48,0x00,0x00", and "41480000" all work the
    same. Raises ValueError with a message meant to be shown directly to the user."""
    cleaned = text.strip()
    if not cleaned:
        return b""
    for token in (",", "0x", "0X", "\n", "\t"):
        cleaned = cleaned.replace(token, " ")
    hex_digits = "".join(cleaned.split())
    if len(hex_digits) % 2 != 0:
        raise ValueError("Odd number of hex digits -- bytes must come in pairs.")
    try:
        return bytes.fromhex(hex_digits)
    except ValueError:
        raise ValueError("Not valid hex -- only 0-9 and A-F are allowed.")


def bytes_to_registers(raw_bytes, order_code):
    """Group raw bytes into 16-bit registers under the selected byte/word ordering.
    ABCD is plain big-endian Modbus (no reordering); BADC swaps the two bytes within
    each register; CDAB reverses register order across the whole value; DCBA does both.
    A trailing odd byte (total length not a multiple of 2) is dropped -- a real Modbus
    register is always 2 bytes, so a stray final byte can't form one on its own."""
    usable = raw_bytes[: len(raw_bytes) - (len(raw_bytes) % 2)]
    registers = []
    for i in range(0, len(usable), 2):
        b0, b1 = usable[i], usable[i + 1]
        if order_code in ("BADC", "DCBA"):
            b0, b1 = b1, b0
        registers.append((b0 << 8) | b1)
    if order_code in ("CDAB", "DCBA"):
        registers.reverse()
    return registers


def decode_ascii(raw_bytes):
    """Every byte must be printable ASCII (0x20-0x7E) for this to return anything -- one
    non-printable byte makes the whole string meaningless as text, so this deliberately
    returns None rather than a string full of replacement characters. Always read in the
    order the bytes were typed -- a text string isn't meaningfully affected by a
    register's numeric byte/word-swap convention the way a number is."""
    if not raw_bytes or any(b < 0x20 or b > 0x7E for b in raw_bytes):
        return None
    return raw_bytes.decode("ascii")


def decode_bcd(raw_bytes):
    """Packed BCD: each byte holds two decimal digits, one per nibble. Returns None if
    any nibble is outside 0-9 (not valid BCD) -- a partially-garbled BCD reading isn't
    more useful than no reading at all. Same as ASCII, read in typed byte order."""
    if not raw_bytes:
        return None
    digits = []
    for b in raw_bytes:
        hi, lo = (b >> 4) & 0xF, b & 0xF
        if hi > 9 or lo > 9:
            return None
        digits.append(f"{hi}{lo}")
    return "".join(digits)


class DataDecoderDialog(QDialog):
    """Standalone 'paste hex, see every interpretation' tool -- no live tag or Modbus
    connection needed. Reuses main_window._decode_register_values() for the actual
    numeric decode math (so it can never drift from what the Tags table itself would show
    for the same bytes/format); this dialog only turns raw hex text into a register list
    under the selected byte/word order and lays out the results.

    Deliberately modeless (.show(), not .exec()) -- unlike every other dialog in this
    app, there's no live device state to serialize against here, and the point is to
    keep it open side-by-side with the Raw Data tab or an external datasheet while
    working, not block the main window."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Decode Registers")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)
        self.resize(480, 520)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Raw hex bytes (spaces, commas, 0x prefixes all fine):"))
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("e.g. 41 48 00 00")
        self.hex_input.textChanged.connect(self._refresh)
        layout.addWidget(self.hex_input)

        order_row = QHBoxLayout()
        order_row.addWidget(QLabel("Byte/word order:"))
        self.order_combo = QComboBox()
        self.order_combo.addItems(BYTE_ORDER_LABELS)
        self.order_combo.currentIndexChanged.connect(self._refresh)
        order_row.addWidget(self.order_combo)
        order_row.addStretch()
        layout.addLayout(order_row)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        self.results_table = QTableWidget(0, 2)
        self.results_table.setHorizontalHeaderLabels(["Interpretation", "Value"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results_table)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self._refresh()

    def _refresh(self):
        text = self.hex_input.text()
        order_code = BYTE_ORDER_CODES[self.order_combo.currentIndex()]
        self.results_table.setRowCount(0)

        if not text.strip():
            self.error_label.setText("")
            return

        try:
            raw_bytes = parse_hex_bytes(text)
        except ValueError as e:
            self.error_label.setText(str(e))
            return

        self.error_label.setText("")
        registers = bytes_to_registers(raw_bytes, order_code)
        if not registers:
            return

        rows = self._build_rows(registers, raw_bytes)
        self.results_table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            self.results_table.setItem(i, 0, QTableWidgetItem(label))
            self.results_table.setItem(i, 1, QTableWidgetItem(value))
        self.results_table.resizeRowsToContents()

    def _build_rows(self, registers, raw_bytes):
        decode = self.main_window._decode_register_values
        rows = [
            ("U16 (per register)", ", ".join(str(v) for v in decode(registers, "U16"))),
            ("S16 (per register)", ", ".join(str(v) for v in decode(registers, "S16"))),
            ("HEX (per register)", ", ".join(decode(registers, "HEX"))),
            ("Binary (per register)", ", ".join(decode(registers, "BOOL"))),
        ]

        if len(registers) >= 2 and len(registers) % 2 == 0:
            rows.append(("U32", ", ".join(str(v) for v in decode(registers, "U32"))))
            rows.append(("S32", ", ".join(str(v) for v in decode(registers, "S32"))))
            rows.append(("F32", ", ".join(f"{v:g}" for v in decode(registers, "F32"))))

        if len(registers) >= 4 and len(registers) % 4 == 0:
            rows.append(("U64", ", ".join(str(v) for v in decode(registers, "U64"))))
            rows.append(("S64", ", ".join(str(v) for v in decode(registers, "S64"))))
            rows.append(("F64", ", ".join(f"{v:g}" for v in decode(registers, "F64"))))

        ascii_text = decode_ascii(raw_bytes)
        if ascii_text:
            rows.append(("ASCII (raw byte order, as typed)", ascii_text))

        bcd_text = decode_bcd(raw_bytes)
        if bcd_text is not None:
            rows.append(("BCD (raw byte order, as typed)", bcd_text))

        for idx, reg in enumerate(registers):
            rows.append((f"Register {idx} bits (15→0)", format(reg, "016b")))

        return rows
