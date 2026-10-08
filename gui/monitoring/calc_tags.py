"""Calculated tags: a Tags-table row in Mode "Calc" whose value is an expression over other
tags' current values (e.g. P1 + P2 + P3, or V1 * I1 * PF / 1000), evaluated after every Tags
poll cycle -- never read from the wire, so a calc tag adds no bus traffic.

The expression language is the Script tab's (same parser): numbers, + - * /, parentheses and
tag names. A plain name means a tag on the calc tag's own device; [DEVICE NAME].TAG names a tag
on another device (e.g. [METER 2].P1). Calc tags can use other calc tags; a circular reference
or a missing/failed input makes the result an error instead of a stale or wrong number."""

from widgets.script_widget import ScriptError, ScriptRunner, parse_expression


class CalcError(Exception):
    pass


def split_ref(name, own_device):
    """'[METER 2].P1' -> ('METER 2', 'P1'); 'P1' -> (own_device, 'P1')."""
    if name.startswith("[") and "]." in name:
        device, tag = name[1:].split("].", 1)
        return device.strip(), tag
    return own_device, name


def compile_expression(text):
    """Parse an expression, rejecting direct register reads (HR 0 ...): a calc tag works on
    other tags' values only, so it never touches the wire."""
    text = (text or "").strip()
    if not text:
        raise CalcError("no expression")
    try:
        node = parse_expression(text)
    except ScriptError as e:
        raise CalcError(str(e))
    if _contains(node, "read"):
        raise CalcError("use tag names, not register reads (HR 0 ...)")
    return node


def referenced_names(node):
    names = set()
    _walk(node, lambda n: names.add(n[1]) if n[0] == "var" else None)
    return names


def _contains(node, kind):
    found = []
    _walk(node, lambda n: found.append(n) if n[0] == kind else None)
    return bool(found)


def _walk(node, visit):
    if not isinstance(node, tuple):
        return
    visit(node)
    for child in node[1:]:
        if isinstance(child, tuple):
            _walk(child, visit)


def evaluate(node, resolve):
    """Evaluate a compiled expression; resolve(name) -> number (raises CalcError)."""
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "str":
        raise CalcError("text isn't allowed in a calculated tag")
    if kind == "var":
        return resolve(node[1])
    if kind == "neg":
        return -evaluate(node[1], resolve)
    if kind == "binop":
        _, op, left, right = node
        try:
            return ScriptRunner._apply_binop(op, evaluate(left, resolve), evaluate(right, resolve))
        except ScriptError as e:
            raise CalcError(str(e))
    raise CalcError(f"unsupported expression ({kind})")


def evaluate_all(calc_tags, inputs, device_names):
    """Evaluate every calc tag. calc_tags: dicts with name/device/expression; inputs:
    {(device, name): number} of the polled tags' latest values. Returns
    {(device, name): number or CalcError} -- calc tags may reference each other."""
    by_key = {(t.get("device", ""), t["name"]): t for t in calc_tags}
    lowered = {d.lower(): d for d in device_names}
    results = {}
    visiting = set()

    def value_of(key):
        if key in results:
            if isinstance(results[key], CalcError):
                raise results[key]
            return results[key]
        if key in by_key:
            return compute(key)
        if key not in inputs:
            raise CalcError(f"no value for {key[1]}" + (f" on {key[0]}" if key[0] else ""))
        return inputs[key]

    def compute(key):
        if key in visiting:
            raise CalcError("circular reference")
        visiting.add(key)
        tag = by_key[key]
        try:
            node = compile_expression(tag.get("expression"))

            def resolve(name):
                device, tag_name = split_ref(name, key[0])
                device = lowered.get(device.lower(), device)
                return value_of((device, tag_name))

            value = evaluate(node, resolve)
            if not isinstance(value, (int, float)):
                raise CalcError("result isn't a number")
            results[key] = value
            return value
        except CalcError as e:
            results[key] = e
            raise
        finally:
            visiting.discard(key)

    for key in by_key:
        if key not in results:
            try:
                compute(key)
            except CalcError:
                pass
    return results


def format_value(value):
    """Up to 4 decimals, trailing zeros dropped (224.1234, 15, 0.5)."""
    if isinstance(value, int) or float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}".rstrip("0").rstrip(".")
