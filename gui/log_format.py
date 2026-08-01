import html

from theme import get_colors

# Classification is keyword-based rather than a structured log level, since call sites across
# the app just pass free-form message strings (e.g. self._log(f"Wrote {value} to {address}")) --
# adding an explicit level to every one of those call sites would be a much bigger, riskier
# change for what's meant to be a readability nicety, not a logging framework.
# Colors themselves come from theme.py (log_error/log_write/log_connect) so a log line stays
# readable against the log widget's background in either Light or Dark mode.

ERROR_KEYWORDS = (
    "error", "failed", "fail", "invalid", "rejected", "exception", "timeout", "lost",
    "duplicate", "overlap", "not connected", "no free address",
)
WRITE_KEYWORDS = ("write", "wrote")
CONNECT_KEYWORDS = ("connected", "reconnected")


def log_line_color(message, mode="light"):
    """Pick a highlight color for a log message based on its content. Returns None for a
    plain informational line (no special color)."""
    c = get_colors(mode)
    lower = message.lower()
    if any(keyword in lower for keyword in ERROR_KEYWORDS):
        return c["log_error"]
    if "disconnected" in lower:
        return None  # neither a failure nor a normal write/connect event
    if any(keyword in lower for keyword in WRITE_KEYWORDS):
        return c["log_write"]
    if any(keyword in lower for keyword in CONNECT_KEYWORDS):
        return c["log_connect"]
    return None


def format_log_html(timestamp, message, mode="light"):
    """Render one log line as an HTML fragment suitable for QTextEdit.append()."""
    color = log_line_color(message, mode)
    escaped = html.escape(message)
    if color:
        return f'<span style="color:{color};">{html.escape(timestamp)} {escaped}</span>'
    return f"{html.escape(timestamp)} {escaped}"
