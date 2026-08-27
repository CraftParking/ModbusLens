"""Central color tokens and Qt theme application for Light/Dark/Follow System.

Every widget file pulls its colors from get_colors(mode) rather than hardcoding hex
values, so the whole app can be re-themed by changing MODE and restarting -- no
per-widget re-styling at runtime (see README's Upcoming Features / this feature's
own scope: restart-to-apply, not live switching).
"""
import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate

APP_ORG = "ModbusLens"
APP_NAME = "ModbusLens"
THEME_MODE_KEY = "app/theme_mode"
VALID_MODES = ("light", "dark", "system")

LIGHT = {
    "window_bg": "#F0F0F0",
    "surface": "#FFFFFF",
    "surface_alt": "#F5F5F5",
    "surface_alt2": "#F8F8F8",
    "border": "#CCCCCC",
    "border_light": "#E0E0E0",
    "text": "#000000",
    "text_secondary": "#333333",
    "text_dim": "#444444",
    "text_disabled": "#999999",
    "heading": "#222222",
    "header_bg": "#E9E9E9",
    "hover": "#E0E0E0",
    "hover_strong": "#E8E8E8",
    "pressed": "#D0D0D0",
    "accent": "#007ACC",
    "selection_bg": "#007ACC",
    "selection_text": "#FFFFFF",
    "selection_inactive_bg": "#B3D7FF",
    "selection_inactive_text": "#000000",
    "danger": "#B00020",
    "success_flash": "#E8F5E8",
    "tooltip_bg": "#FFFFDC",
    "tooltip_text": "#000000",
    "disabled_text": "#808080",
    "disabled_selection": "#C8C8C8",
    "button_hover_border": "#BBBBBB",
    "button_pressed_bg": "#DDDDDD",
    "button_pressed_border": "#AAAAAA",
    "button_disabled_border": "#EEEEEE",
    "log_error": "#C62828",
    "log_write": "#1565C0",
    "log_connect": "#2E7D32",
    "log_warning": "#EF6C00",
}

DARK = {
    "window_bg": "#1E1E1E",
    "surface": "#252526",
    "surface_alt": "#2D2D30",
    "surface_alt2": "#252526",
    "border": "#3F3F46",
    "border_light": "#3F3F46",
    "text": "#E8E8E8",
    "text_secondary": "#CCCCCC",
    "text_dim": "#B0B0B0",
    "text_disabled": "#6E6E6E",
    "heading": "#E0E0E0",
    "header_bg": "#333337",
    "hover": "#3E3E42",
    "hover_strong": "#3E3E42",
    "pressed": "#094771",
    "accent": "#3A9CDC",
    "selection_bg": "#094771",
    "selection_text": "#FFFFFF",
    "selection_inactive_bg": "#264F78",
    "selection_inactive_text": "#E8E8E8",
    "danger": "#F44336",
    "success_flash": "#1B5E20",
    "tooltip_bg": "#3B3B3B",
    "tooltip_text": "#F0F0F0",
    "disabled_text": "#6E6E6E",
    "disabled_selection": "#454545",
    "button_hover_border": "#555555",
    "button_pressed_bg": "#0E639C",
    "button_pressed_border": "#1177BB",
    "button_disabled_border": "#2D2D30",
    "log_error": "#EF5350",
    "log_write": "#64B5F6",
    "log_connect": "#81C784",
    "log_warning": "#FFB74D",
}


def get_colors(mode):
    return DARK if mode == "dark" else LIGHT


_ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_generated_icons")


def _draw_arrow_icon(path, direction, color_hex):
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtGui import QPixmap, QPainter, QPolygon

    size = 10
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color_hex))
    if direction == "up":
        triangle = QPolygon([QPoint(1, 7), QPoint(9, 7), QPoint(5, 2)])
    else:
        triangle = QPolygon([QPoint(1, 2), QPoint(9, 2), QPoint(5, 7)])
    painter.drawPolygon(triangle)
    painter.end()
    pixmap.save(path, "PNG")


def get_arrow_icon_paths(mode):
    """Path to a small up/down triangle PNG matching this theme's text color.

    QSpinBox's native increment/decrement arrows only render as long as
    ::up-button/::down-button are left completely unstyled; once _get_input_style()
    gives them a background/border (needed so the button itself is visible), Qt's
    style sheet engine stops drawing the built-in arrow glyph and requires an
    explicit ::up-arrow/::down-arrow image instead. Generated once per mode and
    cached on disk rather than shipped as a static asset, so both themes stay
    colored from the same token table as everything else.
    """
    c = get_colors(mode)
    os.makedirs(_ICON_DIR, exist_ok=True)
    up_path = os.path.join(_ICON_DIR, f"spin_up_{mode}.png").replace("\\", "/")
    down_path = os.path.join(_ICON_DIR, f"spin_down_{mode}.png").replace("\\", "/")
    if not os.path.exists(up_path):
        _draw_arrow_icon(up_path, "up", c["text_secondary"])
    if not os.path.exists(down_path):
        _draw_arrow_icon(down_path, "down", c["text_secondary"])
    return up_path, down_path


def load_saved_mode():
    """The user's saved preference: 'light', 'dark', or 'system'. Defaults to 'system'."""
    settings = QSettings(APP_ORG, APP_NAME)
    mode = settings.value(THEME_MODE_KEY, "system", type=str)
    return mode if mode in VALID_MODES else "system"


def save_mode(mode):
    settings = QSettings(APP_ORG, APP_NAME)
    settings.setValue(THEME_MODE_KEY, mode)


def resolve_mode(saved_mode, app):
    """Turn 'system' into a concrete 'light'/'dark' by asking Qt what the OS is set to.
    Falls back to light if Qt can't tell (older Qt, or the platform doesn't report it)."""
    if saved_mode in ("light", "dark"):
        return saved_mode
    try:
        from PySide6.QtCore import Qt
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
    except Exception:
        pass
    return "light"


def apply_theme(app, mode):
    """Apply the resolved ('light' or 'dark') theme: Fusion style, a full QPalette, the
    OS-level color-scheme hint, and a global stylesheet for the chrome (menus, tabs,
    status bar, group boxes) that the palette alone doesn't reach."""
    from PySide6.QtCore import Qt

    c = get_colors(mode)
    up_arrow, down_arrow = get_arrow_icon_paths(mode)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["window_bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["surface_alt"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.BrightText, QColor(c["selection_text"]))
    palette.setColor(QPalette.Button, QColor(c["window_bg"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.Highlight, QColor(c["selection_bg"]))
    palette.setColor(QPalette.HighlightedText, QColor(c["selection_text"]))
    palette.setColor(QPalette.ToolTipBase, QColor(c["tooltip_bg"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["tooltip_text"]))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(c["disabled_text"]))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(c["disabled_text"]))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["disabled_text"]))
    palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(c["disabled_selection"]))
    palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(c["disabled_text"]))
    app.setPalette(palette)

    # On Windows, Qt tracks the OS light/dark setting independently of the palette
    # (QStyleHints.colorScheme()) and native/Fusion-derived colors (disabled states,
    # tooltips, some sub-controls) follow that signal even after setPalette() above.
    # Without this override, a system in the other mode still bleeds through into
    # parts of the UI the palette doesn't fully cover.
    style_hints = app.styleHints()
    if hasattr(style_hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        style_hints.setColorScheme(Qt.ColorScheme.Dark if mode == "dark" else Qt.ColorScheme.Light)

    app.setStyleSheet(f"""
        QMainWindow {{
            background-color: {c["window_bg"]};
        }}

        QMenuBar {{
            background-color: {c["window_bg"]};
            color: {c["text"]};
            border-bottom: 1px solid {c["border"]};
        }}

        QMenuBar::item:selected {{
            background-color: {c["hover"]};
        }}

        QMenu {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
        }}

        QMenu::item:selected {{
            background-color: {c["selection_bg"]};
            color: {c["selection_text"]};
        }}

        QStatusBar {{
            background-color: {c["window_bg"]};
            color: {c["text"]};
            border-top: 1px solid {c["border"]};
        }}

        QTabWidget::pane {{
            border: 1px solid {c["border"]};
            background-color: {c["surface"]};
        }}

        QTabBar::tab {{
            background-color: {c["surface_alt"]};
            color: {c["text_secondary"]};
            padding: 8px 16px;
            border: 1px solid {c["border"]};
            margin-right: 2px;
        }}

        QTabBar::tab:selected {{
            background-color: {c["surface"]};
            color: {c["text_secondary"]};
            border-bottom: 1px solid {c["surface"]};
        }}

        QTabBar::tab:hover {{
            background-color: {c["hover_strong"]};
        }}

        QGroupBox {{
            font-weight: bold;
            color: {c["heading"]};
            border: 1px solid {c["border"]};
            margin-top: 1ex;
            background-color: {c["surface_alt2"]};
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 10px 0 10px;
        }}

        QTableWidget {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            gridline-color: {c["border_light"]};
        }}

        QHeaderView::section {{
            background-color: {c["header_bg"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            padding: 5px;
        }}

        QTableWidget::item:selected {{
            background-color: {c["selection_bg"]};
            color: {c["selection_text"]};
        }}

        QTableWidget::item:selected:!active {{
            background-color: {c["selection_inactive_bg"]};
            color: {c["selection_inactive_text"]};
        }}

        QToolTip {{
            background-color: {c["tooltip_bg"]};
            color: {c["tooltip_text"]};
            border: 1px solid {c["border"]};
        }}

        QComboBox {{
            background-color: {c["surface"]};
            color: {c["text"]};
            border: 1px solid {c["border"]};
            padding: 4px 8px;
        }}

        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}

        QComboBox::down-arrow {{
            image: url({down_arrow});
            width: 7px;
            height: 7px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {c["surface"]};
            border: 1px solid {c["border"]};
        }}
    """)


class DropdownItemDelegate(QStyledItemDelegate):
    """Explicitly paints QComboBox popup list items from the theme color dict.

    Qt Fusion's QSS/palette signal propagation on QComboBox popup views is
    fragile: a palette mutation on the combo body (e.g. from tagRowSelected
    highlighting) leaks into the popup and makes unselected items white-on-white
    in light mode. Painting each item directly from the color tokens is immune
    to that, since it never consults the widget palette."""

    def __init__(self, colors):
        super().__init__()
        self._c = colors

    def paint(self, painter, option, index):
        c = self._c
        rect = option.rect

        if option.state & QStyle.State_Selected:
            bg, fg = QColor(c["selection_bg"]), QColor(c["selection_text"])
        elif option.state & QStyle.State_MouseOver:
            bg, fg = QColor(c["hover"]), QColor(c["text"])
        else:
            bg, fg = QColor(c["surface"]), QColor(c["text"])

        painter.save()
        painter.fillRect(rect, bg)
        painter.setPen(QPen(fg))
        text = index.data(Qt.DisplayRole)
        if text is None:
            text = ""
        painter.drawText(rect.adjusted(6, 0, -4, 0),
                         Qt.AlignLeft | Qt.AlignVCenter, str(text))
        painter.restore()


def apply_dropdown_delegate(combo, mode):
    """Attach a DropdownItemDelegate to a QComboBox's popup view.

    mode is the already-resolved ('light'/'dark') or raw ('system') preference;
    if 'system' it is resolved against the current QApplication."""
    if mode == "system":
        app = QApplication.instance()
        mode = resolve_mode(mode, app) if app else "light"
    colors = get_colors(mode)
    combo.view().setItemDelegate(DropdownItemDelegate(colors))
