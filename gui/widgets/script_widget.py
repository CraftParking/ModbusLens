import re
import time

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QTextEdit, QFileDialog, QMessageBox, QSplitter, QCheckBox, QLabel, QComboBox, QMenu
)

HIDE_RUN_WARNING_KEY = "hide_script_run_warning"

TYPE_ALIASES = {
    "COIL": "Coil",
    "DI": "Discrete Input",
    "HR": "Holding Register",
    "IR": "Input Register",
}
WRITABLE_TYPES = ("Coil", "Holding Register")
BIT_TYPES = ("Coil", "Discrete Input")
REVERSE_TYPE_ALIASES = {full: short for short, full in TYPE_ALIASES.items()}
MIN_ADDRESS, MAX_ADDRESS = 0, 65535

COMPARATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}

# Safety bounds: a typo (an extra zero, a forgotten WAIT) should not be able to hang the
# UI, run forever, or blow the interpreter's stack -- it should fail with a clear message.
MAX_INSTRUCTIONS = 5000
MAX_REPEAT_COUNT = 1_000_000
MAX_WAIT_MS = 24 * 60 * 60 * 1000  # 24 hours
MAX_STEPS_PER_TICK = 200  # a loop with no WAIT still yields to the UI this often
MAX_EXPR_DEPTH = 100

DEFAULT_SCRIPT_HELP = """# ModbusLens script - one command per line, # or // starts a comment
#
#   WRITE COIL <addr> = ON|OFF          WRITE HR <addr> = <expr>
#   READ COIL|DI|HR|IR <addr>           LOG <expr>
#   LET <name> = <expr>
#   WAIT <expr, in ms>
#   REPEAT <expr>
#       ...
#   END
#   IF <expr> <op> <expr> THEN <command>   (op: == != > < >= <=)
#
#   <expr> can mix numbers, variables, "strings", + - * / ( ), and
#   inline reads (HR 0, or the equivalent READ HR 0). LOG concatenates
#   strings and numbers with +.
#
# Example:
# LET x = HR 0 + 10
# WRITE HR 1 = x
# WAIT 500
# LOG "HR1 is now " + x
# REPEAT 3
#     WRITE COIL 0 = ON
#     WAIT 250
#     WRITE COIL 0 = OFF
#     WAIT 250
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


def check_address(address):
    if not (MIN_ADDRESS <= address <= MAX_ADDRESS):
        raise ScriptError(f"address {address} out of range ({MIN_ADDRESS}-{MAX_ADDRESS})")
    return address


def parse_bit_keyword(token):
    lowered = token.strip().lower()
    if lowered in ("on", "1", "true"):
        return 1
    if lowered in ("off", "0", "false"):
        return 0
    raise ScriptError(f"invalid ON/OFF value: {token}")


# --- Expression tokenizer ---

_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<string>"(?:[^"\\]|\\.)*")
      | (?P<hex>0[xX][0-9a-fA-F]+)
      | (?P<number>\d+\.\d+|\d+)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>==|!=|>=|<=|[()+\-*/><])
    )""", re.VERBOSE)


def tokenize(text):
    tokens = []
    pos = 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        match = _TOKEN_RE.match(text, pos)
        if not match or match.end() == pos:
            raise ScriptError(f"unexpected character near: {text[pos:pos + 10]!r}")
        pos = match.end()
        if match.group("string") is not None:
            tokens.append(("STRING", match.group("string")[1:-1]))
        elif match.group("hex") is not None:
            tokens.append(("NUMBER", int(match.group("hex"), 16)))
        elif match.group("number") is not None:
            text_val = match.group("number")
            tokens.append(("NUMBER", float(text_val) if "." in text_val else int(text_val)))
        elif match.group("ident") is not None:
            tokens.append(("IDENT", match.group("ident")))
        elif match.group("op") is not None:
            tokens.append(("OP", match.group("op")))
    return tokens


class ExpressionParser:
    """Recursive-descent parser for a small arithmetic/string expression grammar."""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def _peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self):
        tok = self._peek()
        if tok is None:
            raise ScriptError("unexpected end of expression")
        self.pos += 1
        return tok

    def parse(self):
        node = self._parse_expr(0)
        if self._peek() is not None:
            raise ScriptError(f"unexpected token: {self._peek()[1]!r}")
        return node

    def _parse_expr(self, depth):
        if depth > MAX_EXPR_DEPTH:
            raise ScriptError("expression is too deeply nested")
        node = self._parse_term(depth)
        while self._peek() is not None and self._peek()[0] == "OP" and self._peek()[1] in ("+", "-"):
            op = self._advance()[1]
            rhs = self._parse_term(depth + 1)
            node = ("binop", op, node, rhs)
        return node

    def _parse_term(self, depth):
        node = self._parse_factor(depth)
        while self._peek() and self._peek()[0] == "OP" and self._peek()[1] in ("*", "/"):
            op = self._advance()[1]
            rhs = self._parse_factor(depth + 1)
            node = ("binop", op, node, rhs)
        return node

    def _is_type_keyword(self, tok):
        return tok[0] == "IDENT" and tok[1].upper() in TYPE_ALIASES

    def _parse_factor(self, depth):
        tok = self._peek()
        if tok is None:
            raise ScriptError("unexpected end of expression")

        if tok == ("OP", "("):
            self._advance()
            node = self._parse_expr(depth + 1)
            closing = self._advance()
            if closing != ("OP", ")"):
                raise ScriptError("missing closing ')'")
            return node

        if tok[0] == "OP" and tok[1] == "-":
            self._advance()
            return ("neg", self._parse_factor(depth + 1))

        if tok[0] == "STRING":
            self._advance()
            return ("str", tok[1])

        if tok[0] == "NUMBER":
            self._advance()
            return ("num", tok[1])

        if tok[0] == "IDENT" and tok[1].upper() == "READ":
            self._advance()
            return self._parse_read_ref()

        if self._is_type_keyword(tok):
            # sugar: "HR 0" means the same as "READ HR 0"
            return self._parse_read_ref()

        if tok[0] == "IDENT":
            self._advance()
            return ("var", tok[1])

        raise ScriptError(f"unexpected token: {tok[1]!r}")

    def _parse_read_ref(self):
        type_tok = self._advance()
        if type_tok[0] != "IDENT":
            raise ScriptError("expected a type (COIL, DI, HR, IR) after READ")
        data_type = parse_type_token(type_tok[1])
        addr_tok = self._advance()
        if addr_tok[0] != "NUMBER":
            raise ScriptError("expected an address after the type")
        address = check_address(int(addr_tok[1]))
        return ("read", data_type, address)


def parse_expression(text):
    tokens = tokenize(text)
    if not tokens:
        raise ScriptError("expected an expression")
    return ExpressionParser(tokens).parse()


def parse_script(text):
    """Compile script source into a flat instruction list. Raises ScriptError on bad syntax."""
    instructions = []
    repeat_stack = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if len(instructions) >= MAX_INSTRUCTIONS:
            raise ScriptError(f"line {line_number}: script exceeds the {MAX_INSTRUCTIONS}-instruction limit")

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
        return Instruction("WAIT", {"expr": parse_expression(line[5:].strip())})

    if upper.startswith("LOG "):
        return Instruction("LOG", {"expr": parse_expression(line[4:].strip())})

    if upper.startswith("LET "):
        return Instruction("LET", _parse_let_args(line[4:].strip()))

    if upper == "REPEAT" or upper.startswith("REPEAT "):
        count_text = line[6:].strip() if len(line) > 6 else ""
        if not count_text:
            raise ScriptError("REPEAT requires a count")
        return Instruction("REPEAT", {"expr": parse_expression(count_text)})

    if upper == "END":
        return Instruction("END")

    if upper.startswith("WRITE "):
        return Instruction("WRITE", _parse_write_args(line[6:].strip()))

    if upper.startswith("READ "):
        return Instruction("READ", _parse_read_args(line[5:].strip()))

    if upper.startswith("IF "):
        return _parse_if(line[3:].strip())

    raise ScriptError(f"unrecognized command: {line}")


def _parse_let_args(rest):
    if "=" not in rest:
        raise ScriptError("LET requires '<name> = <expr>'")
    name, expr_text = rest.split("=", 1)
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ScriptError(f"invalid variable name: {name!r}")
    if name.upper() in TYPE_ALIASES:
        raise ScriptError(f"'{name}' is a reserved type name and can't be used as a variable")
    return {"name": name, "expr": parse_expression(expr_text)}


def _parse_write_args(rest):
    """Parsed independently of the eventual run target: WRITE to any of the four types
    compiles fine here, and WRITABLE_TYPES is enforced at runtime instead, since a
    Client-target script may only write Coil/Holding Register while a Server-target
    script (simulating the device itself) may write all four."""
    if "=" not in rest:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>'")
    lhs, value_text = rest.split("=", 1)
    parts = lhs.split()
    if len(parts) != 2:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>'")
    data_type = parse_type_token(parts[0])
    try:
        address = check_address(int(parts[1], 0))
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")

    value_text = value_text.strip()
    if data_type in BIT_TYPES:
        return {"type": data_type, "address": address, "bit_value": parse_bit_keyword(value_text)}
    return {"type": data_type, "address": address, "expr": parse_expression(value_text)}


def _parse_read_args(rest):
    parts = rest.split()
    if len(parts) != 2:
        raise ScriptError("READ requires '<TYPE> <ADDR>'")
    data_type = parse_type_token(parts[0])
    try:
        address = check_address(int(parts[1], 0))
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")
    return {"type": data_type, "address": address}


def _parse_if(rest):
    if " THEN " not in f" {rest.upper()} ":
        raise ScriptError("IF requires '<expr> <op> <expr> THEN <command>'")
    then_pos = rest.upper().index("THEN")
    condition_part = rest[:then_pos].strip()
    then_part = rest[then_pos + 4:].strip()
    if not then_part:
        raise ScriptError("IF ... THEN is missing a command")

    op_match = re.search(r"(==|!=|>=|<=|>|<)", condition_part)
    if not op_match:
        raise ScriptError(f"invalid IF condition (missing comparison operator): {condition_part}")
    op = op_match.group(1)
    left_expr = parse_expression(condition_part[:op_match.start()])
    right_expr = parse_expression(condition_part[op_match.end():])

    then_instruction = _parse_line(then_part)
    if then_instruction.op in ("REPEAT", "END", "IF"):
        raise ScriptError("IF...THEN cannot contain REPEAT, END, or a nested IF")

    return Instruction("IF", {"left": left_expr, "op": op, "right": right_expr, "then": then_instruction})


class ScriptRunner:
    """Drives a compiled script one instruction at a time; WAIT hands control back instead of blocking."""

    def __init__(self, modbus_getter, server_getter, target_mode, log_callback):
        self.modbus_getter = modbus_getter
        self.server_getter = server_getter
        self.target_mode = target_mode  # "client" or "server"
        self.log = log_callback
        self.instructions = []
        self.pc = 0
        self.repeat_counters = {}
        self.variables = {}

    def load(self, instructions):
        self.instructions = instructions
        self.pc = 0
        self.repeat_counters = {}
        self.variables = {}

    def finished(self):
        return self.pc >= len(self.instructions)

    def step(self):
        """Run instructions until a WAIT is hit (returns its ms), the script ends (returns
        None), or MAX_STEPS_PER_TICK instructions have run (returns 0) -- a tight loop with
        no WAIT still has to hand control back to the UI regularly instead of freezing it."""
        executed = 0
        while self.pc < len(self.instructions):
            instr = self.instructions[self.pc]
            wait_ms = self._execute(instr)
            self.pc += 1
            executed += 1
            if wait_ms is not None:
                return wait_ms
            if executed >= MAX_STEPS_PER_TICK:
                return 0
        return None

    def _execute(self, instr):
        if instr.op == "WAIT":
            ms = self._eval_int(instr.args["expr"])
            if ms < 0:
                raise ScriptError("WAIT duration must be >= 0")
            if ms > MAX_WAIT_MS:
                raise ScriptError(f"WAIT duration exceeds the {MAX_WAIT_MS}ms limit")
            return ms

        if instr.op == "LOG":
            self.log(str(self._eval(instr.args["expr"])))
            return None

        if instr.op == "LET":
            self.variables[instr.args["name"]] = self._eval(instr.args["expr"])
            return None

        if instr.op == "REPEAT":
            if self.pc not in self.repeat_counters:
                count = self._eval_int(instr.args["expr"])
                if count < 0:
                    raise ScriptError("REPEAT count must be >= 0")
                if count > MAX_REPEAT_COUNT:
                    raise ScriptError(f"REPEAT count exceeds the {MAX_REPEAT_COUNT} limit")
                self.repeat_counters[self.pc] = count
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
            if instr.args["type"] in BIT_TYPES:
                value = instr.args["bit_value"]
            else:
                value = self._eval_int(instr.args["expr"]) & 0xFFFF
            self._do_write(instr.args["type"], instr.args["address"], value)
            return None

        if instr.op == "READ":
            value = self._do_read(instr.args["type"], instr.args["address"])
            self.log(f"READ {instr.args['type']} {instr.args['address']} = {value}")
            return None

        if instr.op == "IF":
            left = self._eval(instr.args["left"])
            right = self._eval(instr.args["right"])
            if COMPARATORS[instr.args["op"]](left, right):
                return self._execute(instr.args["then"])
            return None

        raise ScriptError(f"unknown instruction {instr.op}")

    # --- expression evaluation ---

    def _eval_int(self, node):
        value = self._eval(node)
        if isinstance(value, str):
            raise ScriptError("expected a number here, got text")
        return int(value)

    def _eval(self, node):
        try:
            return self._eval_node(node, depth=0)
        except RecursionError:
            raise ScriptError("expression is too deeply nested")

    def _eval_node(self, node, depth):
        if depth > MAX_EXPR_DEPTH:
            raise ScriptError("expression is too deeply nested")
        kind = node[0]

        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "var":
            name = node[1]
            if name not in self.variables:
                raise ScriptError(f"undefined variable '{name}'")
            return self.variables[name]
        if kind == "read":
            _, data_type, address = node
            value = self._do_read(data_type, address)
            if value is None:
                raise ScriptError(f"read failed for {data_type} {address}")
            return value
        if kind == "neg":
            value = self._eval_node(node[1], depth + 1)
            if isinstance(value, str):
                raise ScriptError("cannot negate text")
            return -value
        if kind == "binop":
            _, op, left_node, right_node = node
            left = self._eval_node(left_node, depth + 1)
            right = self._eval_node(right_node, depth + 1)
            return self._apply_binop(op, left, right)

        raise ScriptError(f"cannot evaluate expression node '{kind}'")

    @staticmethod
    def _apply_binop(op, left, right):
        if op == "+":
            if isinstance(left, str) or isinstance(right, str):
                return f"{left}{right}"
            return left + right
        if isinstance(left, str) or isinstance(right, str):
            raise ScriptError(f"'{op}' cannot be used with text")
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise ScriptError("division by zero")
            return left / right
        raise ScriptError(f"unknown operator '{op}'")

    def _require_modbus(self):
        modbus = self.modbus_getter()
        if not modbus or not modbus.is_connected():
            raise ScriptError("not connected to a Modbus server")
        return modbus

    def _require_server(self):
        server = self.server_getter()
        if not server or not server.running:
            raise ScriptError("Server is not running - start it on the Server tab first")
        return server

    def _do_write(self, data_type, address, value):
        if self.target_mode == "server":
            server = self._require_server()
            ok = server.write_value(data_type, address, value)
            self.log(f"WRITE {data_type} {address} = {value} (server) {'OK' if ok else 'FAILED'}")
            return

        if data_type not in WRITABLE_TYPES:
            raise ScriptError(f"{data_type} cannot be written to a client connection")
        modbus = self._require_modbus()
        if data_type == "Coil":
            ok = modbus.write_coil(address, bool(value))
        else:
            ok = modbus.write_register(address, value)
        self.log(f"WRITE {data_type} {address} = {value} {'OK' if ok else 'FAILED'}")

    def _do_read(self, data_type, address):
        if self.target_mode == "server":
            server = self._require_server()
            return server.read_value(data_type, address)

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
    """A small, purpose-built test-sequence language: WRITE/READ/WAIT/LOG/LET/REPEAT/IF."""

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

    def _input_style(self):
        if self.parent_window is not None and hasattr(self.parent_window, "_get_input_style"):
            return self.parent_window._get_input_style()
        return ""

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Target:"))
        self.target_combo = QComboBox()
        self.target_combo.setStyleSheet(self._input_style())
        self.target_combo.addItem("Client Connection", "client")
        self.target_combo.addItem("Server (Local)", "server")
        self.target_combo.setToolTip(
            "Client Connection: WRITE/READ talk to the remote device via the Connection tab.\n"
            "Server (Local): WRITE/READ act directly on this app's own Server tab datastore, "
            "letting a script simulate a device instead of controlling one."
        )
        toolbar.addWidget(self.target_combo)
        toolbar.addSpacing(10)

        self.compile_btn = QPushButton("Compile")
        self.compile_btn.setStyleSheet(self._button_style())
        self.compile_btn.clicked.connect(self._compile)
        toolbar.addWidget(self.compile_btn)

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
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_editor_context_menu)
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

    def _show_editor_context_menu(self, pos):
        cursor = self.editor.cursorForPosition(pos)
        self.editor.setTextCursor(cursor)

        menu = self.editor.createStandardContextMenu()
        menu.addSeparator()

        tags_menu = menu.addMenu("Insert Tag")
        tags = []
        if self.parent_window is not None and hasattr(self.parent_window, "_get_monitoring_tags"):
            tags = self.parent_window._get_monitoring_tags()

        if not tags:
            no_tags_action = tags_menu.addAction("No tags configured")
            no_tags_action.setEnabled(False)
        else:
            for tag in tags:
                alias = REVERSE_TYPE_ALIASES.get(tag["type"], tag["type"])
                action = tags_menu.addAction(f"{tag['name']}  ({alias} {tag['address']})")
                action.triggered.connect(lambda checked=False, t=tag: self._insert_tag_reference(t))

        menu.exec(self.editor.mapToGlobal(pos))

    def _insert_tag_reference(self, tag):
        alias = REVERSE_TYPE_ALIASES.get(tag["type"], tag["type"])
        self.editor.insertPlainText(f"{alias} {tag['address']}")

    def _target_mode(self):
        return self.target_combo.currentData()

    def _check_target_ready(self):
        if self._target_mode() == "server":
            server = getattr(self.parent_window, "server_widget", None)
            if server and server.running:
                return True
            QMessageBox.warning(self, "Server Not Running", "Start the Server tab before running a Server-target script.")
            return False

        modbus = getattr(self.parent_window, "modbus", None)
        if modbus and modbus.is_connected():
            return True
        QMessageBox.warning(self, "Not Connected", "Connect to a Modbus server before running a Client-target script.")
        return False

    def _compile(self):
        """Validate the script's syntax without running it against a device."""
        try:
            instructions = parse_script(self.editor.toPlainText())
        except ScriptError as e:
            self._log_console(f"Compile failed: {e}")
            QMessageBox.warning(self, "Compile Error", str(e))
            return
        except Exception as e:
            self._log_console(f"Compile failed: {e}")
            QMessageBox.warning(self, "Compile Error", f"Could not parse script: {e}")
            return

        self._log_console(f"Compiled OK - {len(instructions)} instruction(s)")
        QMessageBox.information(self, "Compile", f"Script compiled successfully ({len(instructions)} instruction(s)).")

    def _confirm_run_on_live_system(self):
        settings = QSettings("ModbusLens", "ModbusLens")
        if settings.value(HIDE_RUN_WARNING_KEY, False, type=bool):
            return True

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Run Script")
        box.setText(
            "This script can WRITE to a live Modbus device.\n\n"
            "Running it against a real, in-service system can change outputs, setpoints, "
            "or coils unexpectedly. Review the script and make sure you understand what "
            "it does before running it against live equipment."
        )
        remember_checkbox = QCheckBox("Don't remind me again")
        box.setCheckBox(remember_checkbox)
        box.addButton("Run", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()

        if remember_checkbox.isChecked():
            settings.setValue(HIDE_RUN_WARNING_KEY, True)
        return box.clickedButton() is not cancel_btn

    def _run(self):
        if self.running:
            return
        if not self._check_target_ready():
            return

        try:
            instructions = parse_script(self.editor.toPlainText())
        except ScriptError as e:
            QMessageBox.warning(self, "Script Error", str(e))
            return
        except Exception as e:
            # A parser bug should not crash the app -- fail the run with a message instead.
            QMessageBox.warning(self, "Script Error", f"Could not parse script: {e}")
            return
        if not instructions:
            QMessageBox.warning(self, "Empty Script", "Nothing to run.")
            return

        target_mode = self._target_mode()
        # A Server-target script only ever touches this app's own local simulator, so the
        # live-equipment warning (meant for a real remote device) doesn't apply to it.
        if target_mode == "client" and not self._confirm_run_on_live_system():
            return

        self.runner = ScriptRunner(
            lambda: getattr(self.parent_window, "modbus", None),
            lambda: getattr(self.parent_window, "server_widget", None),
            target_mode,
            self._log_console,
        )
        self.runner.load(instructions)
        self.running = True
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.target_combo.setEnabled(False)
        self.editor.setReadOnly(True)
        self._log_console(f"Script started (target: {self.target_combo.currentText()})")
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
        except Exception as e:
            # Anything unexpected stops the script cleanly rather than propagating out of
            # a timer callback and potentially destabilizing the rest of the application.
            self._log_console(f"Unexpected error, stopping script: {e}")
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
        self.target_combo.setEnabled(True)
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
