import html

# Classification is keyword-based rather than a structured log level, since call sites across
# the app just pass free-form message strings (e.g. self._log(f"Wrote {value} to {address}")) --
# adding an explicit level to every one of those call sites would be a much bigger, riskier
# change for what's meant to be a readability nicety, not a logging framework.
ERROR_COLOR = "#C62828"
WRITE_COLOR = "#1565C0"
CONNECT_COLOR = "#2E7D32"

ERROR_KEYWORDS = (
    "error", "failed", "fail", "invalid", "rejected", "exception", "timeout", "lost",
    "duplicate", "overlap", "not connected", "no free address",
)
WRITE_KEYWORDS = ("write", "wrote")
CONNECT_KEYWORDS = ("connected", "reconnected")


def log_line_color(message):
    """Pick a highlight color for a log message based on its content. Returns None for a
    plain informational line (no special color)."""
    lower = message.lower()
    if any(keyword in lower for keyword in ERROR_KEYWORDS):
        return ERROR_COLOR
    if "disconnected" in lower:
        return None  # neither a failure nor a normal write/connect event
    if any(keyword in lower for keyword in WRITE_KEYWORDS):
        return WRITE_COLOR
    if any(keyword in lower for keyword in CONNECT_KEYWORDS):
        return CONNECT_COLOR
    return None


def format_log_html(timestamp, message):
    """Render one log line as an HTML fragment suitable for QTextEdit.append()."""
    color = log_line_color(message)
    escaped = html.escape(message)
    if color:
        return f'<span style="color:{color};">{html.escape(timestamp)} {escaped}</span>'
    return f"{html.escape(timestamp)} {escaped}"
