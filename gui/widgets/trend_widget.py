import csv
import os
import time

from PySide6.QtCore import Qt, QTimer, QDateTime, QEvent, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QColorDialog, QFileDialog, QMessageBox, QGroupBox,
    QAbstractItemView, QSizePolicy, QDateTimeEdit, QListWidget, QListWidgetItem,
    QScrollBar, QGraphicsLineItem
)
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
from PySide6.QtPrintSupport import QPrinter

MAX_PENS = 20
MAX_POINTS_PER_PEN = 20000  # rolling cap so a long-running trend doesn't grow memory forever

TIME_WINDOWS = [
    ("1 min", 60), ("5 min", 300), ("15 min", 900), ("30 min", 1800),
    ("1 hour", 3600), ("4 hours", 14400), ("8 hours", 28800), ("24 hours", 86400),
]
MIN_WINDOW_SECONDS = 5
MAX_WINDOW_SECONDS = 7 * 24 * 3600

DEFAULT_PEN_COLORS = [
    "#E6194B", "#3CB44B", "#DAA520", "#4363D8", "#F58231", "#911EB4",
    "#42D4D4", "#F032E6", "#9AA300", "#E67AA3", "#008080", "#9A6EBF",
    "#9A6324", "#B8860B", "#800000", "#3D9970", "#808000", "#D2691E",
    "#000075", "#696969",
]

# Trend pens plot a value over time, so only analog (register) data sources make
# sense here -- Coil/Discrete Input and the Bool format are digital/on-off and are
# intentionally left out (unlike the Tags tab, which supports both).
TAG_TYPES = ["Holding Register", "Input Register"]
VALUE_FORMATS = ["U16", "S16", "U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP", "Hex"]


class TrendPen:
    """Configuration plus live chart series for one trend pen."""

    def __init__(self, slot, color):
        self.slot = slot
        self.enabled = False
        self.name = ""
        self.type = "Holding Register"
        self.address = 0
        self.count = 1
        self.format = "U16"
        self.color = QColor(color)
        self.series = None  # QLineSeries, created once the pen is enabled with a name

    def is_active(self):
        return self.enabled and bool(self.name)


class ColorButton(QPushButton):
    """Small swatch button that opens a color picker on click, like a SCADA pen color cell."""

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.setFixedWidth(48)
        self.color = QColor(color)
        self.clicked.connect(self._pick_color)
        self._update_swatch()

    def _update_swatch(self):
        self.setStyleSheet(f"background-color: {self.color.name()}; border: 1px solid #888888;")

    def _pick_color(self):
        # Parented to self.window() rather than self: QColorDialog inherits its parent's
        # stylesheet, and this button's own background-color swatch style would otherwise
        # bleed into the whole dialog (and flatten its buttons along with it).
        chosen = QColorDialog.getColor(self.color, self.window(), "Select Color")
        if chosen.isValid():
            self.color = chosen
            self._update_swatch()


def _switch_to_tags_tab(main_window):
    tab_widget = getattr(main_window, "tab_widget", None) if main_window is not None else None
    if tab_widget is None:
        return
    for i in range(tab_widget.count()):
        if tab_widget.tabText(i) == "Tags":
            tab_widget.setCurrentIndex(i)
            return


class TagPickerDialog(QDialog):
    def __init__(self, tags, parent=None, hint_text=None, empty_hint_text=None):
        super().__init__(parent)
        self.setWindowTitle("Select Tag")
        self.resize(260, 360)
        self._chosen = None
        self._want_add_tag = False

        layout = QVBoxLayout(self)

        if hint_text is None:
            hint_text = "Only analog tags allowed"
        if empty_hint_text is None:
            empty_hint_text = "No analog tags yet"
        hint = QLabel(hint_text if tags else empty_hint_text)
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        for tag in tags:
            item = QListWidgetItem(tag["name"])
            item.setData(Qt.UserRole, tag)
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self.list_widget, 1)

        button_row = QHBoxLayout()
        add_tag_btn = QPushButton("Add Tag...")
        add_tag_btn.clicked.connect(self._choose_add_tag)
        button_row.addWidget(add_tag_btn)
        button_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self._accept_selected)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def _accept_item(self, item):
        self._chosen = item.data(Qt.UserRole)
        self.accept()

    def _accept_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self._chosen = item.data(Qt.UserRole)
        self.accept()

    def _choose_add_tag(self):
        self._want_add_tag = True
        self.accept()

    def chosen_tag(self):
        return self._chosen

    def wants_add_tag(self):
        return self._want_add_tag


class TagPickerCell(QWidget):
    def __init__(self, tags, initial_tag_name=None, main_window=None, parent=None):
        super().__init__(parent)
        self._tags = tags
        self._main_window = main_window
        self._tag = next((t for t in tags if t["name"] == initial_tag_name), None)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self.label = QLabel()
        layout.addWidget(self.label, 1)

        self.picker_btn = QPushButton("⋮")
        self.picker_btn.setFixedWidth(28)
        self.picker_btn.clicked.connect(self._open_picker)
        layout.addWidget(self.picker_btn)

        self._refresh_label()

    def _refresh_label(self):
        if self._tag:
            self.label.setText(self._tag["name"])
            self.label.setStyleSheet("")
        else:
            self.label.setText("Add Tag")
            self.label.setStyleSheet("color: #888888;")

    def _open_picker(self):
        dialog = TagPickerDialog(self._tags, self.window())
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.wants_add_tag():
            _switch_to_tags_tab(self._main_window)
            enclosing = self.window()
            if isinstance(enclosing, QDialog):
                enclosing.reject()
            return
        self._tag = dialog.chosen_tag()
        self._refresh_label()

    def current_tag(self):
        return self._tag


class AddPenDialog(QDialog):
    """SCADA-style pen configuration grid: fixed 20 rows, each an on/off toggle, a tag
    picker, and a color."""

    def __init__(self, pens, tags, main_window=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trend Pens")
        self.resize(560, 560)
        self._rows = []

        layout = QVBoxLayout(self)

        table = QTableWidget(MAX_PENS, 3)
        table.setHorizontalHeaderLabels(["On", "Name", "Color"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)

        for row in range(MAX_PENS):
            pen = pens[row]

            enabled_box = QCheckBox()
            enabled_box.setChecked(pen.enabled)
            enabled_cell = QWidget()
            enabled_cell_layout = QHBoxLayout(enabled_cell)
            enabled_cell_layout.addWidget(enabled_box)
            enabled_cell_layout.setAlignment(Qt.AlignCenter)
            enabled_cell_layout.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 0, enabled_cell)

            name_cell = TagPickerCell(tags, pen.name or None, main_window)
            table.setCellWidget(row, 1, name_cell)

            color_btn = ColorButton(pen.color)
            table.setCellWidget(row, 2, color_btn)

            self._rows.append({
                "enabled": enabled_box,
                "name": name_cell,
                "color": color_btn,
            })

        layout.addWidget(table)

        button_row = QHBoxLayout()
        button_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def apply_to(self, pens):
        for row, widgets in enumerate(self._rows):
            pen = pens[row]
            pen.enabled = widgets["enabled"].isChecked()
            tag = widgets["name"].current_tag()
            if tag:
                pen.name = tag["name"]
                pen.type = tag["type"]
                pen.address = tag["address"]
                pen.count = tag["count"]
                pen.format = tag["format"]
            else:
                pen.name = ""
            pen.color = widgets["color"].color


class GraphPropertiesDialog(QDialog):
    """Axis, color, and grid configuration for the trend chart."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Graph Properties")
        s = settings

        layout = QVBoxLayout(self)

        colors_group = QGroupBox("Colors")
        colors_layout = QVBoxLayout(colors_group)

        bg_row = QHBoxLayout()
        bg_row.addWidget(QLabel("Background Color:"))
        self.bg_btn = ColorButton(s["background_color"])
        bg_row.addWidget(self.bg_btn)
        bg_row.addStretch()
        colors_layout.addLayout(bg_row)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Axis Line Color:"))
        self.axis_btn = ColorButton(s["axis_color"])
        axis_row.addWidget(self.axis_btn)
        axis_row.addStretch()
        colors_layout.addLayout(axis_row)

        grid_row = QHBoxLayout()
        self.grid_checkbox = QCheckBox("Show Grid Lines")
        self.grid_checkbox.setChecked(s["grid_visible"])
        grid_row.addWidget(self.grid_checkbox)
        grid_row.addWidget(QLabel("Grid Color:"))
        self.grid_btn = ColorButton(s["grid_color"])
        grid_row.addWidget(self.grid_btn)
        grid_row.addStretch()
        colors_layout.addLayout(grid_row)

        layout.addWidget(colors_group)

        x_axis_group = QGroupBox("X Axis")
        x_axis_layout = QHBoxLayout(x_axis_group)
        x_axis_layout.addWidget(QLabel("Title:"))
        self.x_title_edit = QLineEdit(s["x_title"])
        x_axis_layout.addWidget(self.x_title_edit)
        layout.addWidget(x_axis_group)

        axis_group = QGroupBox("Y Axis")
        axis_layout = QVBoxLayout(axis_group)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title:"))
        self.title_edit = QLineEdit(s["y_title"])
        title_row.addWidget(self.title_edit)
        axis_layout.addLayout(title_row)

        self.auto_checkbox = QCheckBox("Auto Range")
        self.auto_checkbox.setChecked(s["y_auto"])
        self.auto_checkbox.toggled.connect(self._on_auto_toggled)
        axis_layout.addWidget(self.auto_checkbox)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("Min:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-1e9, 1e9)
        self.min_spin.setValue(s["y_min"])
        range_row.addWidget(self.min_spin)
        range_row.addWidget(QLabel("Max:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-1e9, 1e9)
        self.max_spin.setValue(s["y_max"])
        range_row.addWidget(self.max_spin)
        axis_layout.addLayout(range_row)

        layout.addWidget(axis_group)

        self._on_auto_toggled(self.auto_checkbox.isChecked())

        button_row = QHBoxLayout()
        button_row.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(ok_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

    def _on_auto_toggled(self, checked):
        self.min_spin.setEnabled(not checked)
        self.max_spin.setEnabled(not checked)

    def values(self):
        return {
            "background_color": self.bg_btn.color,
            "axis_color": self.axis_btn.color,
            "grid_visible": self.grid_checkbox.isChecked(),
            "grid_color": self.grid_btn.color,
            "x_title": self.x_title_edit.text().strip() or "Time",
            "y_auto": self.auto_checkbox.isChecked(),
            "y_min": self.min_spin.value(),
            "y_max": self.max_spin.value(),
            "y_title": self.title_edit.text().strip() or "Value",
        }


class DetachedPlaceholder(QWidget):
    """Sits in the Trend tab's place while the real widget is floating in its own window --
    a plain red X, so it's obvious at a glance the tab isn't just empty/broken."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#CC3333"), 3))
        w, h = self.width(), self.height()
        painter.drawLine(0, 0, w, h)
        painter.drawLine(w, 0, 0, h)
        painter.end()


class TrendWidget(QWidget):
    """SCADA-style trend tab: up to 20 live-polled pens plotted over time, live or historical."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pens = [TrendPen(i, DEFAULT_PEN_COLORS[i % len(DEFAULT_PEN_COLORS)]) for i in range(MAX_PENS)]
        self.window_seconds = TIME_WINDOWS[0][1]
        self.running = False
        c = parent._colors() if parent is not None and hasattr(parent, "_colors") else {}
        is_dark = bool(parent) and getattr(parent, "_theme_mode", "light") == "dark"
        self.graph_settings = {
            "background_color": QColor(c.get("surface", "#FFFFFF")),
            "axis_color": QColor(c.get("text_secondary", "#333333")),
            "grid_visible": True,
            # High-contrast against the plot background specifically -- the generic border
            # token is too subtle here (thin grid lines need more contrast than a panel border).
            "grid_color": QColor("#FFFFFF" if is_dark else "#000000"),
            "x_title": "Time",
            "y_auto": True,
            "y_min": 0.0,
            "y_max": 100.0,
            "y_title": "Value",
        }

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_pens)

        self._log_file = None
        self._log_writer = None

        self._detach_window = None
        self._detach_placeholder = None
        self._detach_tab_index = None

        self._setup_ui()
        self._apply_graph_settings()

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

        self.add_pen_btn = QPushButton("Add Pen")
        self.add_pen_btn.setStyleSheet(self._button_style())
        self.add_pen_btn.clicked.connect(self._open_add_pen_dialog)
        toolbar.addWidget(self.add_pen_btn)

        self.properties_btn = QPushButton("Graph Properties")
        self.properties_btn.setStyleSheet(self._button_style())
        self.properties_btn.clicked.connect(self._open_properties_dialog)
        toolbar.addWidget(self.properties_btn)

        toolbar.addSpacing(15)
        toolbar.addWidget(QLabel("Interval (ms):"))
        self.interval_input = QSpinBox()
        self.interval_input.setRange(200, 60000)
        self.interval_input.setValue(1000)
        self.interval_input.setStyleSheet(self._input_style())
        self.interval_input.valueChanged.connect(self._on_interval_changed)
        toolbar.addWidget(self.interval_input)

        self.start_btn = QPushButton("Start Trend")
        self.start_btn.setStyleSheet(self._button_style())
        self.start_btn.clicked.connect(self._start_trend)
        toolbar.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Trend")
        self.stop_btn.setStyleSheet(self._button_style())
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_trend)
        toolbar.addWidget(self.stop_btn)

        self.detach_btn = QPushButton("Detach")
        self.detach_btn.setStyleSheet(self._button_style())
        self.detach_btn.clicked.connect(self._detach)
        toolbar.addWidget(self.detach_btn)

        toolbar.addStretch()

        self.log_btn = QPushButton("Log to CSV")
        self.log_btn.setStyleSheet(self._button_style())
        self.log_btn.clicked.connect(self._toggle_logging)
        toolbar.addWidget(self.log_btn)

        self.print_btn = QPushButton("Print")
        self.print_btn.setStyleSheet(self._button_style())
        self.print_btn.clicked.connect(self._print_graph)
        toolbar.addWidget(self.print_btn)

        layout.addLayout(toolbar)

        self.chart = QChart()
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)

        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm:ss")
        self.axis_x.setTitleText(self.graph_settings["x_title"])
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)

        self.axis_y = QValueAxis()
        self.axis_y.setTitleText(self.graph_settings["y_title"])
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)

        now = QDateTime.currentDateTime()
        self.axis_x.setRange(now.addSecs(-self.window_seconds), now)
        self.axis_y.setRange(self.graph_settings["y_min"], self.graph_settings["y_max"])

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.chart_view, 1)

        self._cursor_line = QGraphicsLineItem()
        self._cursor_line.setPen(QPen(QColor("#888888"), 1, Qt.DashLine))
        self._cursor_line.setZValue(100)
        self.chart.scene().addItem(self._cursor_line)
        self._cursor_line.setVisible(False)
        self._hover_x_ms = None
        self.chart_view.setMouseTracking(True)
        self.chart_view.viewport().installEventFilter(self)

        self.history_scrollbar = QScrollBar(Qt.Horizontal)
        self.history_scrollbar.setEnabled(False)
        self._updating_scrollbar = False
        self.history_scrollbar.valueChanged.connect(self._on_scrollbar_moved)
        layout.addWidget(self.history_scrollbar)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Time Window:"))
        self.window_combo = QComboBox()
        for label, seconds in TIME_WINDOWS:
            self.window_combo.addItem(label, seconds)
        self.window_combo.setCurrentIndex(0)
        self.window_combo.setStyleSheet(self._input_style())
        self.window_combo.currentIndexChanged.connect(self._on_window_changed)
        bottom.addWidget(self.window_combo)

        bottom.addStretch()

        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.setStyleSheet(self._button_style())
        self.zoom_in_btn.clicked.connect(lambda: self._zoom(0.5))
        bottom.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.setStyleSheet(self._button_style())
        self.zoom_out_btn.clicked.connect(lambda: self._zoom(2.0))
        bottom.addWidget(self.zoom_out_btn)

        layout.addLayout(bottom)

        history_row = QHBoxLayout()
        history_row.addWidget(QLabel("From:"))
        self.from_datetime_edit = QDateTimeEdit(now.addSecs(-self.window_seconds))
        self.from_datetime_edit.setCalendarPopup(True)
        self.from_datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.from_datetime_edit.setStyleSheet(self._input_style())
        history_row.addWidget(self.from_datetime_edit)

        history_row.addWidget(QLabel("To:"))
        self.to_datetime_edit = QDateTimeEdit(now)
        self.to_datetime_edit.setCalendarPopup(True)
        self.to_datetime_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.to_datetime_edit.setStyleSheet(self._input_style())
        history_row.addWidget(self.to_datetime_edit)

        self.go_to_range_btn = QPushButton("Go")
        self.go_to_range_btn.setStyleSheet(self._button_style())
        self.go_to_range_btn.clicked.connect(self._go_to_range)
        history_row.addWidget(self.go_to_range_btn)
        history_row.addStretch()

        layout.addLayout(history_row)

        stats_header_row = QHBoxLayout()
        stats_header_row.addStretch()
        # Only useful (and only shown) in the detached floating window, where hiding this
        # table gives the graph itself more room -- the docked tab is never short on space.
        self.stats_toggle_btn = QPushButton("▼ Hide Stats")
        self.stats_toggle_btn.setStyleSheet(self._button_style())
        self.stats_toggle_btn.clicked.connect(self._toggle_stats_table)
        self.stats_toggle_btn.setVisible(False)
        stats_header_row.addWidget(self.stats_toggle_btn)
        layout.addLayout(stats_header_row)

        self.stats_table = QTableWidget(0, 5)
        self.stats_table.setHorizontalHeaderLabels(["Pen", "Value", "Minimum", "Maximum", "Average"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.stats_table.setMaximumHeight(160)
        self.stats_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.stats_table)

    def _toggle_stats_table(self):
        visible = not self.stats_table.isVisible()
        self.stats_table.setVisible(visible)
        self.stats_toggle_btn.setText("▼ Hide Stats" if visible else "▶ Show Stats")

    # --- Detach / re-dock ---

    def _detach(self):
        if self._detach_window is not None:
            return
        tab_widget = getattr(self.parent_window, "tab_widget", None)
        if tab_widget is None:
            return
        index = tab_widget.indexOf(self)
        if index < 0:
            return
        self._detach_tab_index = index

        self._detach_placeholder = DetachedPlaceholder()
        tab_widget.removeTab(index)
        tab_widget.insertTab(index, self._detach_placeholder, "Trend")

        window = QWidget()
        window.setWindowTitle("Trend - ModbusLens")
        window.setWindowFlag(Qt.Window, True)
        window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        window.resize(1000, 700)
        window.closeEvent = self._on_detach_window_close

        window_layout = QVBoxLayout(window)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.addWidget(self)

        fixed_row = QHBoxLayout()
        fixed_row.addStretch()
        fixed_btn = QPushButton("Fixed")
        fixed_btn.setStyleSheet(self._button_style())
        fixed_btn.clicked.connect(self._redock)
        fixed_row.addWidget(fixed_btn)
        window_layout.addLayout(fixed_row)

        self._detach_window = window
        self.detach_btn.setEnabled(False)
        self.stats_toggle_btn.setVisible(True)
        # QTabWidget.removeTab() hides whatever widget was in that tab -- reparenting it
        # into the new window doesn't undo that, so without this it floats invisibly.
        self.show()
        window.show()

    def _on_detach_window_close(self, event):
        self._redock(from_close_event=True)
        event.accept()

    def _redock(self, from_close_event=False):
        window = self._detach_window
        if window is None:
            return
        self._detach_window = None  # guard against the closeEvent this triggers below

        window.layout().removeWidget(self)

        tab_widget = getattr(self.parent_window, "tab_widget", None)
        if tab_widget is not None and self._detach_tab_index is not None:
            tab_widget.removeTab(self._detach_tab_index)
            tab_widget.insertTab(self._detach_tab_index, self, "Trend")
            tab_widget.setCurrentIndex(self._detach_tab_index)
            self.show()

        self._detach_placeholder = None
        self.detach_btn.setEnabled(True)
        self.stats_toggle_btn.setVisible(False)
        if not self.stats_table.isVisible():
            self._toggle_stats_table()  # always land back on the docked tab fully expanded

        if not from_close_event:
            window.close()
        window.deleteLater()

    # --- Pen configuration ---

    def _open_add_pen_dialog(self):
        dialog = AddPenDialog(self.pens, self._get_eligible_tags(), self.parent_window, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to(self.pens)
            self._sync_series()

    def _get_eligible_tags(self):
        getter = getattr(self.parent_window, "_get_monitoring_tags", None)
        if getter is None:
            return []
        return [tag for tag in getter() if tag["type"] in TAG_TYPES and tag["format"] in VALUE_FORMATS]

    def _sync_series(self):
        """Add/remove/restyle chart series so they match the current pen configuration."""
        for pen in self.pens:
            if pen.is_active():
                if pen.series is None:
                    series = QLineSeries()
                    series.setName(pen.name)
                    series.setPen(QPen(pen.color, 2))
                    self.chart.addSeries(series)
                    series.attachAxis(self.axis_x)
                    series.attachAxis(self.axis_y)
                    pen.series = series
                else:
                    pen.series.setName(pen.name)
                    pen.series.setPen(QPen(pen.color, 2))
            elif pen.series is not None:
                self.chart.removeSeries(pen.series)
                pen.series = None
        self._update_stats_table()

    def _has_active_pens(self):
        return any(pen.is_active() for pen in self.pens)

    # --- Graph properties ---

    def _open_properties_dialog(self):
        dialog = GraphPropertiesDialog(self.graph_settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.graph_settings.update(dialog.values())
            self._apply_graph_settings()

    def _apply_graph_settings(self):
        s = self.graph_settings
        # QChart.setBackgroundBrush() alone only paints the chart's outer margin -- the plot
        # area itself (where the grid and series actually sit) is a separate layer that stays
        # on the QChartView's own white palette background unless explicitly given a brush too.
        self.chart.setBackgroundBrush(s["background_color"])
        self.chart.setPlotAreaBackgroundBrush(s["background_color"])
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart_view.setBackgroundBrush(s["background_color"])
        axis_pen = QPen(s["axis_color"])
        self.axis_x.setLinePen(axis_pen)
        self.axis_y.setLinePen(axis_pen)
        self.axis_x.setLabelsColor(s["grid_color"])
        self.axis_y.setLabelsColor(s["grid_color"])
        self.axis_x.setGridLineVisible(s["grid_visible"])
        self.axis_y.setGridLineVisible(s["grid_visible"])
        grid_pen = QPen(s["grid_color"])
        self.axis_x.setGridLinePen(grid_pen)
        self.axis_y.setGridLinePen(grid_pen)
        self.axis_x.setTitleText(s["x_title"])
        self.axis_y.setTitleText(s["y_title"])
        self.axis_x.setTitleBrush(s["grid_color"])
        self.axis_y.setTitleBrush(s["grid_color"])
        if not s["y_auto"]:
            self.axis_y.setRange(s["y_min"], s["y_max"])

    # --- Time window / zoom ---

    def _on_window_changed(self, _index):
        self.window_seconds = self.window_combo.currentData()
        self._apply_time_window(anchor_now=False)

    def _apply_time_window(self, anchor_now):
        if anchor_now:
            now = QDateTime.currentDateTime()
            self.axis_x.setRange(now.addSecs(-self.window_seconds), now)
        else:
            current_min = self.axis_x.min()
            current_max = self.axis_x.max()
            center = current_min.addMSecs(current_min.msecsTo(current_max) // 2)
            half = self.window_seconds * 1000 // 2
            self.axis_x.setRange(center.addMSecs(-half), center.addMSecs(half))
        self._update_scrollbar()
        self._update_stats_table()

    def _zoom(self, factor):
        new_span = max(MIN_WINDOW_SECONDS, min(MAX_WINDOW_SECONDS, self.window_seconds * factor))
        self.window_seconds = int(new_span)
        self._apply_time_window(anchor_now=False)

    def _go_to_range(self):
        """Jump the view directly to a typed From/To range."""
        from_dt = self.from_datetime_edit.dateTime()
        to_dt = self.to_datetime_edit.dateTime()
        if from_dt >= to_dt:
            QMessageBox.warning(self, "Invalid Range", "'From' must be earlier than 'To'.")
            return

        self.window_seconds = max(MIN_WINDOW_SECONDS, from_dt.secsTo(to_dt))
        self.axis_x.setRange(from_dt, to_dt)
        self._update_scrollbar()
        self._update_stats_table()

    # --- Start / stop ---

    def _start_trend(self):
        if not self._has_active_pens():
            QMessageBox.warning(self, "No Pens Configured", "Add at least one pen before starting the trend.")
            return
        if not self._check_connection():
            return

        self.running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.add_pen_btn.setEnabled(False)
        self._apply_time_window(anchor_now=True)
        self.poll_timer.start(self.interval_input.value())

    def _stop_trend(self):
        self.running = False
        self.poll_timer.stop()
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.add_pen_btn.setEnabled(True)

    def _check_connection(self):
        modbus = getattr(self.parent_window, "modbus", None)
        if modbus and modbus.is_connected():
            return True
        QMessageBox.warning(self, "Not Connected", "Connect to a Modbus server before starting the trend.")
        return False

    def _on_interval_changed(self, value):
        if self.running:
            self.poll_timer.start(value)

    # --- Polling ---

    def _poll_pens(self):
        modbus = getattr(self.parent_window, "modbus", None)
        if not modbus or not modbus.is_connected():
            self._stop_trend()
            QMessageBox.warning(self, "Trend Stopped", "Trend was stopped because the Modbus connection is not active.")
            return

        now = QDateTime.currentDateTime()
        now_ms = now.toMSecsSinceEpoch()
        got_point = False
        log_timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

        # If the view is already sitting at the live edge, keep it there as new points
        # arrive; if the user scrolled back into history, leave the view exactly where
        # they put it. The tolerance covers normal gaps between one poll and the next.
        tolerance_ms = max(self.interval_input.value(), 1000) * 1.5
        was_at_live_edge = (now_ms - self.axis_x.max().toMSecsSinceEpoch()) <= tolerance_ms

        for pen in self.pens:
            if not (pen.is_active() and pen.series is not None):
                continue
            value = self._read_pen_value(modbus, pen)
            if value is None:
                continue
            pen.series.append(now_ms, value)
            self._trim_series(pen.series)
            got_point = True
            self._log_pen_value(pen, log_timestamp, value)

        if got_point:
            self._update_y_range()
            if was_at_live_edge:
                self.axis_x.setRange(now.addSecs(-self.window_seconds), now)
            self._update_scrollbar()
            self._update_stats_table()

    def _read_pen_value(self, modbus, pen):
        try:
            # pen.address is the same user-facing address a Tag shows (e.g. "1" with
            # 1-based addressing) -- it needs the same conversion Tags/Address Table
            # already apply before it's a real protocol offset, or this reads the wrong
            # register (off by one whenever 1-based addressing is on, which is the default).
            offset_converter = getattr(self.parent_window, "_tag_user_address_to_offset", None)
            address = offset_converter({"address": pen.address}) if offset_converter else pen.address

            if pen.type == "Coil":
                data = modbus.read_coils(address, pen.count)
            elif pen.type == "Discrete Input":
                data = modbus.read_discrete_inputs(address, pen.count)
            elif pen.type == "Input Register":
                data = modbus.read_input_registers(address, pen.count)
            else:
                data = modbus.read_registers(address, pen.count)

            if data is None:
                return None

            if pen.type in ("Coil", "Discrete Input"):
                first = data[0] if isinstance(data, list) else data
                return 1.0 if bool(first) else 0.0

            # If the tag this pen is bound to has engineering-unit scaling enabled on
            # the Tags tab, plot that scaled value instead of the raw one -- Trend always
            # follows whatever the Tags tab is currently configured to show for it.
            scaled = self._scaled_pen_value(pen, data)
            if scaled is not None:
                return scaled

            registers = data if isinstance(data, list) else [data]
            decoder = getattr(self.parent_window, "_decode_register_values", None)
            decoded = decoder(registers, pen.format) if decoder else registers
            value = decoded[0] if isinstance(decoded, list) else decoded
            return float(value)
        except Exception:
            return None

    def _scaled_pen_value(self, pen, data):
        getter = getattr(self.parent_window, "_get_monitoring_tags", None)
        manager = getattr(self.parent_window, "monitoring_manager", None)
        if getter is None or manager is None:
            return None
        tag = next((t for t in getter() if t["name"] == pen.name), None)
        if tag is None:
            return None
        config = manager.tag_scaling.get(tag["row"])
        if not config or not config.get("enabled"):
            return None
        result = manager.compute_engineering_value(tag, data)
        if not result:
            return None
        try:
            return float(result)
        except ValueError:
            return None

    @staticmethod
    def _trim_series(series):
        overflow = series.count() - MAX_POINTS_PER_PEN
        if overflow > 0:
            series.removePoints(0, overflow)

    def _update_y_range(self):
        if not self.graph_settings["y_auto"]:
            return

        values = [point.y() for pen in self.pens if pen.series is not None for point in pen.series.points()]
        if not values:
            return

        lo, hi = min(values), max(values)
        if lo == hi:
            lo -= 1
            hi += 1
        margin = (hi - lo) * 0.1
        self.axis_y.setRange(lo - margin, hi + margin)

    # --- History scrollbar ---

    def _data_time_bounds(self):
        starts, ends = [], []
        for pen in self.pens:
            if pen.series is None or pen.series.count() == 0:
                continue
            starts.append(pen.series.at(0).x())
            ends.append(pen.series.at(pen.series.count() - 1).x())
        if not starts:
            return None
        return min(starts), max(ends)

    def _update_scrollbar(self):
        bounds = self._data_time_bounds()
        if bounds is None:
            self.history_scrollbar.setEnabled(False)
            return

        data_start, data_end = bounds
        window_ms = self.window_seconds * 1000
        total_span = max(int(data_end - data_start), window_ms)

        self._updating_scrollbar = True
        try:
            self.history_scrollbar.setEnabled(True)
            self.history_scrollbar.setRange(0, max(0, total_span - window_ms))
            self.history_scrollbar.setPageStep(window_ms)
            current_min_ms = self.axis_x.min().toMSecsSinceEpoch()
            self.history_scrollbar.setValue(int(current_min_ms - data_start))
        finally:
            self._updating_scrollbar = False

    def _on_scrollbar_moved(self, value):
        if self._updating_scrollbar:
            return
        bounds = self._data_time_bounds()
        if bounds is None:
            return
        data_start, _ = bounds
        new_min = QDateTime.fromMSecsSinceEpoch(int(data_start) + value)
        new_max = new_min.addMSecs(self.window_seconds * 1000)
        self.axis_x.setRange(new_min, new_max)
        self._update_stats_table()

    # --- Live stats table + hover crosshair ---

    def eventFilter(self, obj, event):
        if obj is self.chart_view.viewport():
            if event.type() == QEvent.MouseMove:
                self._on_chart_hover(event.position())
            elif event.type() == QEvent.Leave:
                self._clear_hover()
        return super().eventFilter(obj, event)

    def _on_chart_hover(self, widget_pos):
        scene_pos = self.chart_view.mapToScene(widget_pos.toPoint())
        chart_pos = self.chart.mapFromScene(scene_pos)
        if not self.chart.plotArea().contains(chart_pos):
            self._clear_hover()
            return

        x_ms = self.chart.mapToValue(scene_pos).x()
        top = self.chart.mapToPosition(QPointF(x_ms, self.axis_y.max()))
        bottom = self.chart.mapToPosition(QPointF(x_ms, self.axis_y.min()))
        self._cursor_line.setLine(top.x(), top.y(), bottom.x(), bottom.y())
        self._cursor_line.setVisible(True)

        self._hover_x_ms = x_ms
        self._update_stats_table()
        self._update_legend_labels()

    def _clear_hover(self):
        self._cursor_line.setVisible(False)
        self._hover_x_ms = None
        self._update_stats_table()
        self._update_legend_labels()

    def _update_legend_labels(self):
        for pen in self.pens:
            if not pen.is_active() or pen.series is None:
                continue
            markers = self.chart.legend().markers(pen.series)
            if not markers:
                continue
            if self._hover_x_ms is not None and pen.series.count() > 0:
                value = self._nearest_value(pen.series, self._hover_x_ms)
                label = f"{pen.name}: {value:g}" if value is not None else pen.name
            else:
                label = pen.name
            markers[0].setLabel(label)

    @staticmethod
    def _nearest_value(series, x_ms):
        best_value, best_dist = None, None
        for point in series.points():
            dist = abs(point.x() - x_ms)
            if best_dist is None or dist < best_dist:
                best_dist, best_value = dist, point.y()
        return best_value

    def _update_stats_table(self):
        xmin = self.axis_x.min().toMSecsSinceEpoch()
        xmax = self.axis_x.max().toMSecsSinceEpoch()
        active_pens = [pen for pen in self.pens if pen.is_active() and pen.series is not None]

        self.stats_table.setRowCount(len(active_pens))
        for row, pen in enumerate(active_pens):
            in_view = [pt.y() for pt in pen.series.points() if xmin <= pt.x() <= xmax]

            if self._hover_x_ms is not None and pen.series.count() > 0:
                value = self._nearest_value(pen.series, self._hover_x_ms)
            elif in_view:
                value = in_view[-1]
            else:
                value = None

            name_item = QTableWidgetItem(pen.name)
            name_item.setBackground(pen.color)
            luminance = 0.299 * pen.color.red() + 0.587 * pen.color.green() + 0.114 * pen.color.blue()
            name_item.setForeground(QColor("#000000" if luminance > 140 else "#FFFFFF"))
            self.stats_table.setItem(row, 0, name_item)
            self.stats_table.setItem(row, 1, QTableWidgetItem("" if value is None else f"{value:g}"))
            self.stats_table.setItem(row, 2, QTableWidgetItem(f"{min(in_view):g}" if in_view else ""))
            self.stats_table.setItem(row, 3, QTableWidgetItem(f"{max(in_view):g}" if in_view else ""))
            self.stats_table.setItem(row, 4, QTableWidgetItem(f"{sum(in_view) / len(in_view):g}" if in_view else ""))

    # --- Logging ---

    def _toggle_logging(self):
        if self._log_writer is not None:
            self._log_file.close()
            self._log_file = None
            self._log_writer = None
            self.log_btn.setText("Log to CSV")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Log Trend to CSV", "trend_log.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            is_new_or_empty = True
            try:
                is_new_or_empty = os.path.getsize(file_path) == 0
            except OSError:
                pass
            self._log_file = open(file_path, "a", newline="", encoding="utf-8")
            self._log_writer = csv.writer(self._log_file)
            if is_new_or_empty:
                self._log_writer.writerow(["Timestamp", "Pen Name", "Type", "Address", "Value"])
                self._log_file.flush()
        except OSError as e:
            QMessageBox.warning(self, "Logging Failed", f"Could not open file for logging: {e}")
            return
        self.log_btn.setText("Stop Logging")

    def _log_pen_value(self, pen, timestamp, value):
        if not self._log_writer:
            return
        self._log_writer.writerow([timestamp, pen.name, pen.type, pen.address, value])
        self._log_file.flush()

    # --- Print ---

    def _print_graph(self):
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "Print Graph", "trend.png", "PNG Image (*.png);;PDF Document (*.pdf)"
        )
        if not file_path:
            return

        want_pdf = file_path.lower().endswith(".pdf") or "PDF" in selected_filter
        try:
            if want_pdf:
                if not file_path.lower().endswith(".pdf"):
                    file_path += ".pdf"
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(file_path)
                painter = QPainter(printer)
                self.chart_view.render(painter)
                painter.end()
            else:
                if not file_path.lower().endswith(".png"):
                    file_path += ".png"
                self.chart_view.grab().save(file_path, "PNG")
        except Exception as e:
            QMessageBox.warning(self, "Print Failed", f"Could not save graph: {e}")
