import re
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QTextEdit, QFileDialog, QMessageBox, QSplitter
)

TYPE_ALIASES = {
    "COIL": "Coil",
    "DI": "Discrete Input",
    "HR": "Holding Register",
    "IR": "Input Register",
}
WRITABLE_TYPES = ("Coil", "Holding Register")
BIT_TYPES = ("Coil", "Discrete Input")

COMPARATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}

DEFAULT_SCRIPT_HELP = """# ModbusLens script - one command per line, # or // starts a comment
#
#   WRITE COIL <addr> = ON|OFF        WRITE HR <addr> = <number>
#   READ COIL|DI|HR|IR <addr>         LOG "message"
#   WAIT <milliseconds>
#   REPEAT <n>
#       ...
#   END
#   IF <TYPE> <addr> <op> <value> THEN <command>   (op: == != > < >= <=)
#
# Example:
# WRITE HR 0 = 100
# WAIT 1000
# READ HR 0
# REPEAT 3
#     WRITE COIL 0 = ON
#     WAIT 500
#     WRITE COIL 0 = OFF
#     WAIT 500
# END
"""


class ScriptError(Exception):
    pass


class Instruction:
    __slots__ = ("op", "args", "jump")

    def __init__(self, op, args=None, jump=None):
        self.op = op
        self.args = args or {}
        self.jump = jump  # REPEAT -> matching END index; END -> matching REPEAT index


def parse_type_token(token):
    key = token.strip().upper()
    if key not in TYPE_ALIASES:
        raise ScriptError(f"unknown type '{token}' (use COIL, DI, HR, or IR)")
    return TYPE_ALIASES[key]


def parse_value_token(token, is_bit):
    token = token.strip()
    if is_bit:
        lowered = token.lower()
        if lowered in ("on", "1", "true"):
            return 1
        if lowered in ("off", "0", "false"):
            return 0
        raise ScriptError(f"invalid ON/OFF value: {token}")
    try:
        return int(token, 0)
    except ValueError:
        raise ScriptError(f"invalid number: {token}")


def parse_script(text):
    """Compile script source into a flat instruction list. Raises ScriptError on bad syntax."""
    instructions = []
    repeat_stack = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        try:
            instructions.append(_parse_line(line))
        except ScriptError as e:
            raise ScriptError(f"line {line_number}: {e}")

        if instructions[-1].op == "REPEAT":
            repeat_stack.append(len(instructions) - 1)
        elif instructions[-1].op == "END":
            if not repeat_stack:
                raise ScriptError(f"line {line_number}: END without matching REPEAT")
            start_index = repeat_stack.pop()
            instructions[-1].jump = start_index
            instructions[start_index].jump = len(instructions) - 1

    if repeat_stack:
        raise ScriptError("REPEAT without matching END")

    return instructions


def _parse_line(line):
    upper = line.upper()

    if upper.startswith("WAIT "):
        ms_text = line[5:].strip()
        try:
            ms = int(ms_text)
        except ValueError:
            raise ScriptError(f"invalid WAIT duration: {ms_text}")
        if ms < 0:
            raise ScriptError("WAIT duration must be >= 0")
        return Instruction("WAIT", {"ms": ms})

    if upper.startswith("LOG "):
        text = line[4:].strip()
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return Instruction("LOG", {"text": text})

    if upper == "REPEAT" or upper.startswith("REPEAT "):
        count_text = line[6:].strip() if len(line) > 6 else ""
        try:
            count = int(count_text)
        except ValueError:
            raise ScriptError(f"invalid REPEAT count: {count_text!r}")
        if count < 1:
            raise ScriptError("REPEAT count must be at least 1")
        return Instruction("REPEAT", {"count": count})

    if upper == "END":
        return Instruction("END")

    if upper.startswith("WRITE "):
        return Instruction("WRITE", _parse_write_args(line[6:].strip()))

    if upper.startswith("READ "):
        return Instruction("READ", _parse_read_args(line[5:].strip()))

    if upper.startswith("IF "):
        return _parse_if(line[3:].strip())

    raise ScriptError(f"unrecognized command: {line}")


def _parse_write_args(rest):
    if "=" not in rest:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>'")
    lhs, value_text = rest.split("=", 1)
    parts = lhs.split()
    if len(parts) != 2:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>'")
    data_type = parse_type_token(parts[0])
    if data_type not in WRITABLE_TYPES:
        raise ScriptError(f"{data_type} cannot be written")
    try:
        address = int(parts[1], 0)
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")
    value = parse_value_token(value_text, is_bit=(data_type == "Coil"))
    return {"type": data_type, "address": address, "value": value}


def _parse_read_args(rest):
    parts = rest.split()
    if len(parts) != 2:
        raise ScriptError("READ requires '<TYPE> <ADDR>'")
    data_type = parse_type_token(parts[0])
    try:
        address = int(parts[1], 0)
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")
    return {"type": data_type, "address": address}


def _parse_if(rest):
    if " THEN " not in f" {rest.upper()} ":
        raise ScriptError("IF requires '<TYPE> <ADDR> <OP> <VALUE> THEN <command>'")
    then_pos = rest.upper().index("THEN")
    condition_part = rest[:then_pos].strip()
    then_part = rest[then_pos + 4:].strip()
    if not then_part:
        raise ScriptError("IF ... THEN is missing a command")

    match = re.match(r"^(\S+)\s+(\S+)\s*(==|!=|>=|<=|>|<)\s*(\S+)$", condition_part)
    if not match:
        raise ScriptError(f"invalid IF condition: {condition_part}")
    type_token, addr_token, op, value_token = match.groups()
    data_type = parse_type_token(type_token)
    try:
        address = int(addr_token, 0)
    except ValueError:
        raise ScriptError(f"invalid address: {addr_token}")
    compare_value = parse_value_token(value_token, is_bit=(data_type in BIT_TYPES))

    then_instruction = _parse_line(then_part)
    if then_instruction.op in ("REPEAT", "END", "IF"):
        raise ScriptError("IF...THEN cannot contain REPEAT, END, or a nested IF")

    return Instruction("IF", {
        "type": data_type, "address": address, "op": op, "value": compare_value,
        "then": then_instruction,
    })


class ScriptRunner:
    """Drives a compiled script one instruction at a time; WAIT hands control back instead of blocking."""

    def __init__(self, modbus_getter, log_callback):
        self.modbus_getter = modbus_getter
        self.log = log_callback
        self.instructions = []
        self.pc = 0
        self.repeat_counters = {}

    def load(self, instructions):
        self.instructions = instructions
        self.pc = 0
        self.repeat_counters = {}

    def finished(self):
        return self.pc >= len(self.instructions)

    def step(self):
        """Run instructions until a WAIT is hit (returns its ms) or the script ends (returns None)."""
        while self.pc < len(self.instructions):
            instr = self.instructions[self.pc]
            wait_ms = self._execute(instr)
            self.pc += 1
            if wait_ms is not None:
                return wait_ms
        return None

    def _execute(self, instr):
        if instr.op == "WAIT":
            return instr.args["ms"]

        if instr.op == "LOG":
            self.log(instr.args["text"])
            return None

        if instr.op == "REPEAT":
            if self.pc not in self.repeat_counters:
                self.repeat_counters[self.pc] = instr.args["count"]
            if self.repeat_counters[self.pc] > 0:
                self.repeat_counters[self.pc] -= 1
            else:
                del self.repeat_counters[self.pc]
                self.pc = instr.jump  # step() adds 1, landing just past END
            return None

        if instr.op == "END":
            self.pc = instr.jump - 1  # step() adds 1, landing back on REPEAT
            return None

        if instr.op == "WRITE":
            self._do_write(instr.args["type"], instr.args["address"], instr.args["value"])
            return None

        if instr.op == "READ":
            value = self._do_read(instr.args["type"], instr.args["address"])
            self.log(f"READ {instr.args['type']} {instr.args['address']} = {value}")
            return None

        if instr.op == "IF":
            value = self._do_read(instr.args["type"], instr.args["address"])
            if value is not None and COMPARATORS[instr.args["op"]](value, instr.args["value"]):
                return self._execute(instr.args["then"])
            return None

        raise ScriptError(f"unknown instruction {instr.op}")

    def _require_modbus(self):
        modbus = self.modbus_getter()
        if not modbus or not modbus.is_connected():
            raise ScriptError("not connected to a Modbus server")
        return modbus

    def _do_write(self, data_type, address, value):
        modbus = self._require_modbus()
        if data_type == "Coil":
            ok = modbus.write_coil(address, bool(value))
        else:
            ok = modbus.write_register(address, value)
        self.log(f"WRITE {data_type} {address} = {value} {'OK' if ok else 'FAILED'}")

    def _do_read(self, data_type, address):
        modbus = self._require_modbus()
        if data_type == "Coil":
            data = modbus.read_coils(address, 1)
        elif data_type == "Discrete Input":
            data = modbus.read_discrete_inputs(address, 1)
        elif data_type == "Input Register":
            data = modbus.read_input_registers(address, 1)
        else:
            data = modbus.read_registers(address, 1)
        if data is None:
            return None
        value = data[0] if isinstance(data, list) else data
        return int(value)


class ScriptWidget(QWidget):
    """A small, purpose-built test-sequence language: WRITE/READ/WAIT/LOG/REPEAT/IF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.runner = None
        self.running = False

        self.step_timer = QTimer(self)
        self.step_timer.setSingleShot(True)
        self.step_timer.timeout.connect(self._resume)

        self._setup_ui()

    def _button_style(self):
        if self.parent_window is not None and hasattr(self.parent_window, "_get_button_style"):
            return self.parent_window._get_button_style()
        return ""

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()

        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet(self._button_style())
        self.run_btn.clicked.connect(self._run)
        toolbar.addWidget(self.run_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet(self._button_style())
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(lambda: self._stop(user_initiated=True))
        toolbar.addWidget(self.stop_btn)

        self.open_btn = QPushButton("Open...")
        self.open_btn.setStyleSheet(self._button_style())
        self.open_btn.clicked.connect(self._open_file)
        toolbar.addWidget(self.open_btn)

        self.save_btn = QPushButton("Save...")
        self.save_btn.setStyleSheet(self._button_style())
        self.save_btn.clicked.connect(self._save_file)
        toolbar.addWidget(self.save_btn)

        self.clear_console_btn = QPushButton("Clear Console")
        self.clear_console_btn.setStyleSheet(self._button_style())
        self.clear_console_btn.clicked.connect(lambda: self.console.clear())
        toolbar.addWidget(self.clear_console_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Vertical)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setPlaceholderText(DEFAULT_SCRIPT_HELP)
        splitter.addWidget(self.editor)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.document().setMaximumBlockCount(5000)
        splitter.addWidget(self.console)

        splitter.setSizes([420, 150])
        layout.addWidget(splitter, 1)

    def _log_console(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        self.console.append(f"{timestamp} {message}")

    def _check_connection(self):
        modbus = getattr(self.parent_window, "modbus", None)
        if modbus and modbus.is_connected():
            return True
        QMessageBox.warning(self, "Not Connected", "Connect to a Modbus server before running a script.")
        return False

    def _run(self):
        if self.running:
            return
        if not self._check_connection():
            return

        try:
            instructions = parse_script(self.editor.toPlainText())
        except ScriptError as e:
            QMessageBox.warning(self, "Script Error", str(e))
            return
        if not instructions:
            QMessageBox.warning(self, "Empty Script", "Nothing to run.")
            return

        self.runner = ScriptRunner(lambda: getattr(self.parent_window, "modbus", None), self._log_console)
        self.runner.load(instructions)
        self.running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.editor.setReadOnly(True)
        self._log_console("Script started")
        self._resume()

    def _resume(self):
        if not self.running or self.runner is None:
            return
        try:
            wait_ms = self.runner.step()
        except ScriptError as e:
            self._log_console(f"Error: {e}")
            self._stop()
            return

        if self.runner.finished():
            self._log_console("Script finished")
            self._stop()
            return

        self.step_timer.start(max(0, wait_ms or 0))

    def _stop(self, user_initiated=False):
        self.step_timer.stop()
        self.running = False
        self.runner = None
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.editor.setReadOnly(False)
        if user_initiated:
            self._log_console("Script stopped")

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Script", "", "ModbusLens Scripts (*.mls);;Text Files (*.txt);;All Files (*)")
        if not file_path:
            return
        try:
            with open(file_path, encoding="utf-8") as f:
                self.editor.setPlainText(f.read())
        except OSError as e:
            QMessageBox.warning(self, "Open Failed", str(e))

    def _save_file(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Script", "script.mls", "ModbusLens Scripts (*.mls);;Text Files (*.txt)")
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except OSError as e:
            QMessageBox.warning(self, "Save Failed", str(e))
