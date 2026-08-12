import keyword
import re
import time

try:
    import psutil
except ImportError:
    psutil = None

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QPlainTextEdit,
    QTextEdit, QFileDialog, QMessageBox, QSplitter, QCheckBox, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QDialog
)

from log_format import format_log_html
from modbus_meta import function_code_for
from widgets.trend_widget import TagPickerDialog

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

TAG_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SCRIPT_KEYWORDS = {"WRITE", "READ", "WAIT", "LOG", "LET", "REPEAT", "UNTIL", "END", "IF", "THEN", "ON", "OFF", "TRUE", "FALSE"}
RESERVED_TAG_NAMES = (
    SCRIPT_KEYWORDS
    | set(TYPE_ALIASES.keys())
    | {kw.upper() for kw in keyword.kwlist}
    | {"EVAL", "EXEC", "IMPORT", "OPEN", "COMPILE", "GLOBALS", "LOCALS", "GETATTR", "SETATTR", "DELATTR"}
)


def validate_tag_name(name):
    name = name.strip()
    if not name:
        return None
    if not TAG_NAME_RE.fullmatch(name):
        return (
            "Tag names can only use letters, numbers, and underscores (no spaces or "
            "other symbols), and can't start with a digit."
        )
    if name.upper() in RESERVED_TAG_NAMES:
        return f"'{name}' is a reserved word and can't be used as a tag name."
    return None

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
MIN_STEP_INTERVAL_MS = 20  # write-rate floor: no matter what a script's WAIT says (or
# omits), consecutive steps are never scheduled closer together than this, so a
# WAIT 0/1 typo -- or a tight loop with no WAIT at all -- can't flood the device/network.
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
#   REPEAT UNTIL <expr> <op> <expr>        (op: == != > < >= <=)
#       ...
#   END
#   IF <expr> <op> <expr> THEN <command>   (op: == != > < >= <=)
#
#   <expr> can mix numbers, variables, "strings", + - * / ( ), and
#   inline reads (HR 0, or the equivalent READ HR 0). LOG concatenates
#   strings and numbers with +.
#
#   REPEAT UNTIL checks the condition before each pass (so the body can run
#   zero times if it's already true), and stops with an error rather than
#   looping forever if it never becomes true.
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
#
# REPEAT UNTIL HR 0 == 100
#     WAIT 200
# END
# LOG "HR0 reached 100"
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

        if instructions[-1].op in ("REPEAT", "REPEAT_UNTIL"):
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


def collect_variable_names(instructions):
    """Every name a LET assigns, in first-seen order -- drives the Script tab's live
    watch panel. Looks inside IF...THEN too, since its single command can itself be a LET."""
    names = []
    seen = set()
    for instr in instructions:
        target = instr.args["then"] if instr.op == "IF" else instr
        if target.op == "LET" and target.args["name"] not in seen:
            seen.add(target.args["name"])
            names.append(target.args["name"])
    return names


def _parse_line(line):
    upper = line.upper()

    if upper.startswith("WAIT "):
        return Instruction("WAIT", {"expr": parse_expression(line[5:].strip())})

    if upper.startswith("LOG "):
        return Instruction("LOG", {"expr": parse_expression(line[4:].strip())})

    if upper.startswith("LET "):
        return Instruction("LET", _parse_let_args(line[4:].strip()))

    if upper == "REPEAT" or upper.startswith("REPEAT "):
        rest = line[6:].strip() if len(line) > 6 else ""
        if not rest:
            raise ScriptError("REPEAT requires a count or 'UNTIL <condition>'")
        if rest[:5].upper() == "UNTIL":
            condition_text = rest[5:].strip()
            if not condition_text:
                raise ScriptError("REPEAT UNTIL requires a condition")
            return Instruction("REPEAT_UNTIL", _parse_condition(condition_text))
        return Instruction("REPEAT", {"expr": parse_expression(rest)})

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
    script (simulating the device itself) may write all four.

    '<TYPE> <ADDR> = <VALUE>' and '<TAG_NAME> = <VALUE>' are both accepted; a tag name
    only resolves to a type/address at run time (against whatever's on the Tags tab then),
    so its value text is stored unparsed and interpreted once the type is known."""
    if "=" not in rest:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>' or '<TAG NAME> = <VALUE>'")
    lhs, value_text = rest.split("=", 1)
    parts = lhs.split()
    value_text = value_text.strip()

    if len(parts) == 1:
        name = parts[0]
        if not TAG_NAME_RE.fullmatch(name) or name.upper() in TYPE_ALIASES:
            raise ScriptError(f"invalid tag name: {name}")
        return {"tag_name": name, "value_text": value_text}

    if len(parts) != 2:
        raise ScriptError("WRITE requires '<TYPE> <ADDR> = <VALUE>' or '<TAG NAME> = <VALUE>'")
    data_type = parse_type_token(parts[0])
    try:
        address = check_address(int(parts[1], 0))
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")

    if data_type in BIT_TYPES:
        return {"type": data_type, "address": address, "bit_value": parse_bit_keyword(value_text)}
    return {"type": data_type, "address": address, "expr": parse_expression(value_text)}


def _parse_read_args(rest):
    parts = rest.split()
    if len(parts) == 1:
        name = parts[0]
        if not TAG_NAME_RE.fullmatch(name) or name.upper() in TYPE_ALIASES:
            raise ScriptError(f"invalid tag name: {name}")
        return {"tag_name": name}
    if len(parts) != 2:
        raise ScriptError("READ requires '<TYPE> <ADDR>' or '<TAG NAME>'")
    data_type = parse_type_token(parts[0])
    try:
        address = check_address(int(parts[1], 0))
    except ValueError:
        raise ScriptError(f"invalid address: {parts[1]}")
    return {"type": data_type, "address": address}


def _parse_condition(text):
    """Parse '<expr> <op> <expr>', shared by IF...THEN and REPEAT UNTIL."""
    op_match = re.search(r"(==|!=|>=|<=|>|<)", text)
    if not op_match:
        raise ScriptError(f"invalid condition (missing comparison operator): {text}")
    op = op_match.group(1)
    left_expr = parse_expression(text[:op_match.start()])
    right_expr = parse_expression(text[op_match.end():])
    return {"left": left_expr, "op": op, "right": right_expr}


def _parse_if(rest):
    if " THEN " not in f" {rest.upper()} ":
        raise ScriptError("IF requires '<expr> <op> <expr> THEN <command>'")
    then_pos = rest.upper().index("THEN")
    condition_part = rest[:then_pos].strip()
    then_part = rest[then_pos + 4:].strip()
    if not then_part:
        raise ScriptError("IF ... THEN is missing a command")

    condition = _parse_condition(condition_part)

    then_instruction = _parse_line(then_part)
    if then_instruction.op in ("REPEAT", "REPEAT_UNTIL", "END", "IF"):
        raise ScriptError("IF...THEN cannot contain REPEAT, END, or a nested IF")

    return Instruction("IF", {**condition, "then": then_instruction})


class ScriptRunner:
    """Drives a compiled script one instruction at a time; WAIT hands control back instead of blocking."""

    def __init__(self, modbus_getter, server_getter, target_mode, log_callback, raw_data_callback=None,
                 tags_getter=None, reserve_range=None, release_range=None):
        self.modbus_getter = modbus_getter
        self.server_getter = server_getter
        self.target_mode = target_mode  # "client" or "server"
        self.tags_getter = tags_getter or (lambda: [])
        self.log = log_callback
        self.raw_data_callback = raw_data_callback
        # Join the same busy/overlap interlock Tags-table writes and reads use
        # (main_window._reserve_range/_release_range) -- a script's step_timer lets
        # the Qt event loop run other timers (Tags Monitoring, Trend) between steps,
        # so without this a script WRITE can genuinely land mid-poll of the same
        # register range. Only relevant for target_mode == "client" (the shared live
        # ModbusClient); a Server-target script writes to its own local simulator
        # datastore, a separate object nothing else polls, so no reservation is
        # needed there. Default to permissive no-ops so ScriptRunner stays usable
        # standalone (e.g. in tests) without a real main window behind it.
        self.reserve_range = reserve_range or (lambda request_range: True)
        self.release_range = release_range or (lambda request_range: None)
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

        if instr.op == "REPEAT_UNTIL":
            if self._eval_condition(instr.args):
                self.repeat_counters.pop(self.pc, None)
                self.pc = instr.jump  # step() adds 1, landing just past END
                return None
            iterations = self.repeat_counters.get(self.pc, 0) + 1
            if iterations > MAX_REPEAT_COUNT:
                raise ScriptError(
                    f"REPEAT UNTIL exceeded the {MAX_REPEAT_COUNT}-iteration limit "
                    "without the condition becoming true"
                )
            self.repeat_counters[self.pc] = iterations
            return None

        if instr.op == "END":
            self.pc = instr.jump - 1  # step() adds 1, landing back on REPEAT
            return None

        if instr.op == "WRITE":
            data_type, address = self._resolve_type_address(instr.args)
            if "tag_name" in instr.args:
                if data_type in BIT_TYPES:
                    value = parse_bit_keyword(instr.args["value_text"])
                else:
                    value = self._eval_int(parse_expression(instr.args["value_text"])) & 0xFFFF
            elif data_type in BIT_TYPES:
                value = instr.args["bit_value"]
            else:
                value = self._eval_int(instr.args["expr"]) & 0xFFFF
            self._do_write(data_type, address, value)
            return None

        if instr.op == "READ":
            data_type, address = self._resolve_type_address(instr.args)
            value = self._do_read(data_type, address)
            self.log(f"READ {data_type} {address} = {value}")
            return None

        if instr.op == "IF":
            if self._eval_condition(instr.args):
                return self._execute(instr.args["then"])
            return None

        raise ScriptError(f"unknown instruction {instr.op}")

    def _eval_condition(self, cond):
        left = self._eval(cond["left"])
        right = self._eval(cond["right"])
        return COMPARATORS[cond["op"]](left, right)

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
            if name in self.variables:
                return self.variables[name]
            tag = self._find_tag(name)
            if tag is not None:
                value = self._do_read(tag["type"], tag["address"])
                if value is None:
                    raise ScriptError(f"read failed for tag '{name}'")
                return value
            raise ScriptError(f"undefined variable or tag '{name}'")
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

    def _find_tag(self, name):
        for tag in self.tags_getter():
            if tag["name"] == name:
                return tag
        return None

    def _resolve_type_address(self, args):
        if "tag_name" in args:
            tag = self._find_tag(args["tag_name"])
            if tag is None:
                raise ScriptError(f"unknown tag '{args['tag_name']}'")
            return tag["type"], tag["address"]
        return args["type"], args["address"]

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

        # data_type is already one of the exact space strings the Tags table and
        # Address Table use ("Coil"/"Holding Register"/etc, see TYPE_ALIASES), and
        # `address` is already the raw 0-based protocol offset (scripts have no
        # separate one/zero-based addressing mode) -- both match the interlock's
        # range-dict shape with no conversion needed.
        request_range = {"operation": "write", "space": data_type, "start": address, "end": address, "tag": "Script"}
        if not self.reserve_range(request_range):
            self.log(f"WRITE {data_type} {address} = {value} SKIPPED -- safety interlock: range busy")
            return
        try:
            start_time = time.perf_counter()
            if data_type == "Coil":
                ok = modbus.write_coil(address, bool(value))
            else:
                ok = modbus.write_register(address, value)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
        finally:
            self.release_range(request_range)

        self.log(f"WRITE {data_type} {address} = {value} {'OK' if ok else 'FAILED'}")
        if self.raw_data_callback:
            self.raw_data_callback(
                f"Script WRITE {data_type} {address}", value if ok else None, elapsed_ms,
                function_code_for(data_type, is_write=True),
            )

    def _do_read(self, data_type, address):
        if self.target_mode == "server":
            server = self._require_server()
            return server.read_value(data_type, address)

        modbus = self._require_modbus()
        start_time = time.perf_counter()
        if data_type == "Coil":
            data = modbus.read_coils(address, 1)
        elif data_type == "Discrete Input":
            data = modbus.read_discrete_inputs(address, 1)
        elif data_type == "Input Register":
            data = modbus.read_input_registers(address, 1)
        else:
            data = modbus.read_registers(address, 1)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        if self.raw_data_callback:
            self.raw_data_callback(
                f"Script READ {data_type} {address}", data, elapsed_ms,
                function_code_for(data_type, is_write=False),
            )
        if data is None:
            return None
        value = data[0] if isinstance(data, list) else data
        return int(value)


class ScriptWidget(QWidget):
    """A small, purpose-built test-sequence language: WRITE/READ/WAIT/LOG/LET/REPEAT/REPEAT UNTIL/IF."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.runner = None
        self.running = False

        self.step_timer = QTimer(self)
        self.step_timer.setSingleShot(True)
        self.step_timer.timeout.connect(self._resume)

        self._setup_ui()

        self._psutil_available = psutil is not None
        if self._psutil_available:
            psutil.cpu_percent(interval=None)  # first call just primes the baseline
            self.cpu_timer = QTimer(self)
            self.cpu_timer.timeout.connect(self._update_cpu_usage)
            self.cpu_timer.start(1000)

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

        self.add_tag_btn = QPushButton("Add Tag")
        self.add_tag_btn.setStyleSheet(self._button_style())
        self.add_tag_btn.clicked.connect(self._open_tag_picker)
        toolbar.addWidget(self.add_tag_btn)

        toolbar.addStretch()

        self.cpu_label = QLabel("CPU: --")
        self.cpu_label.setToolTip("System-wide CPU usage, useful for spotting a script loop that's running hot")
        toolbar.addWidget(self.cpu_label)

        layout.addLayout(toolbar)

        main_splitter = QSplitter(Qt.Horizontal)

        editor_splitter = QSplitter(Qt.Vertical)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setPlaceholderText(DEFAULT_SCRIPT_HELP)
        self.editor.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self._show_editor_context_menu)
        editor_splitter.addWidget(self.editor)

        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.document().setMaximumBlockCount(5000)
        editor_splitter.addWidget(self.console)

        editor_splitter.setSizes([420, 150])
        main_splitter.addWidget(editor_splitter)

        main_splitter.addWidget(self._build_variables_panel())
        main_splitter.setSizes([700, 220])
        layout.addWidget(main_splitter, 1)

    def _build_variables_panel(self):
        """A live watch panel: every LET-defined variable in the compiled script, with its
        current value while running -- so a script author can see state without sprinkling
        LOG lines everywhere just to check what a variable holds mid-run."""
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(4)
        panel_layout.addWidget(QLabel("Variables"))

        self.variables_table = QTableWidget(0, 2)
        self.variables_table.setHorizontalHeaderLabels(["Name", "Value"])
        self.variables_table.verticalHeader().setVisible(False)
        self.variables_table.horizontalHeader().setStretchLastSection(True)
        self.variables_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.variables_table.setSelectionMode(QTableWidget.NoSelection)
        self.variables_table.setStyleSheet(self._table_style())
        panel_layout.addWidget(self.variables_table)
        return panel

    def _table_style(self):
        if self.parent_window is not None and hasattr(self.parent_window, "_get_table_style"):
            return self.parent_window._get_table_style()
        return ""

    def _reset_variables_panel(self, names):
        """(Re)populate the watch panel with `names`, each shown blank until LET assigns it."""
        table = self.variables_table
        table.setRowCount(len(names))
        for row, name in enumerate(names):
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, name_item)
            value_item = QTableWidgetItem("")
            value_item.setFlags(value_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 1, value_item)

    def _refresh_variables_panel(self):
        if self.runner is None:
            return
        values = self.runner.variables
        table = self.variables_table
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            if name_item is None:
                continue
            value_item = table.item(row, 1)
            value_item.setText(str(values.get(name_item.text(), "")))

    def _log_console(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        scrollbar = self.console.verticalScrollBar()
        # Only follow new lines if already scrolled to the bottom -- otherwise scrolling up
        # to read past output gets yanked back down as soon as the script logs again.
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        mode = getattr(self.parent_window, "_theme_mode", "light")
        self.console.append(format_log_html(timestamp, message, mode))
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        # Also forward to the main window's System Logs, not just this tab's own console.
        if hasattr(self.parent_window, '_log'):
            self.parent_window._log(f"[Script] {message}")

    def _update_cpu_usage(self):
        if not self._psutil_available:
            return
        try:
            percent = psutil.cpu_percent(interval=None)
        except psutil.Error:
            self.cpu_label.setText("CPU: --")
            return
        self.cpu_label.setText(f"CPU: {percent:.1f}%")

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
        self.editor.insertPlainText(tag["name"])

    def _open_tag_picker(self):
        tags = []
        if self.parent_window is not None and hasattr(self.parent_window, "_get_monitoring_tags"):
            tags = self.parent_window._get_monitoring_tags()

        dialog = TagPickerDialog(
            tags,
            self,
            hint_text="Select a tag to insert",
            empty_hint_text="No tags configured yet",
        )
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.wants_add_tag():
            self._add_tag_and_switch()
            return
        tag = dialog.chosen_tag()
        if tag is not None:
            self._insert_tag_reference(tag)

    def _add_tag_and_switch(self):
        if self.parent_window is None or not hasattr(self.parent_window, "_add_monitoring_tag"):
            return
        self.parent_window._add_monitoring_tag()
        tab_widget = getattr(self.parent_window, "tab_widget", None)
        if tab_widget is None:
            return
        for i in range(tab_widget.count()):
            if tab_widget.tabText(i) == "Tags":
                tab_widget.setCurrentIndex(i)
                break

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

        self._reset_variables_panel(collect_variable_names(instructions))
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
            getattr(self.parent_window, "_display_raw_data", None),
            getattr(self.parent_window, "_get_monitoring_tags", None),
            getattr(self.parent_window, "_reserve_range", None),
            getattr(self.parent_window, "_release_range", None),
        )
        self.runner.load(instructions)
        self._reset_variables_panel(collect_variable_names(instructions))
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

        self._refresh_variables_panel()

        if self.runner.finished():
            self._log_console("Script finished")
            self._stop()
            return

        self.step_timer.start(max(MIN_STEP_INTERVAL_MS, wait_ms or 0))

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
