import csv
import os
import time

from PySide6.QtCore import Qt, QTimer, QDateTime
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QDialog, QTableWidget,
    QHeaderView, QColorDialog, QFileDialog, QMessageBox, QGroupBox,
    QAbstractItemView, QSizePolicy, QDateTimeEdit
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

TAG_TYPES = ["Coil", "Discrete Input", "Holding Register", "Input Register"]
VALUE_FORMATS = ["Bool", "U16", "S16", "U32", "S32", "F32", "U32_SWAP", "S32_SWAP", "F32_SWAP", "Hex"]


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


class AddPenDialog(QDialog):
    """SCADA-style pen configuration grid: fixed 20 rows, each a tag/address plus a color."""

    def __init__(self, pens, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trend Pens")
        self.resize(780, 560)
        self._rows = []

        layout = QVBoxLayout(self)

        table = QTableWidget(MAX_PENS, 7)
        table.setHorizontalHeaderLabels(["On", "Name", "Type", "Address", "Count", "Format", "Color"])
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

            name_edit = QLineEdit(pen.name)
            table.setCellWidget(row, 1, name_edit)

            type_combo = QComboBox()
            type_combo.addItems(TAG_TYPES)
            type_combo.setCurrentText(pen.type)
            table.setCellWidget(row, 2, type_combo)

            address_spin = QSpinBox()
            address_spin.setRange(0, 65535)
            address_spin.setValue(pen.address)
            table.setCellWidget(row, 3, address_spin)

            count_spin = QSpinBox()
            count_spin.setRange(1, 125)
            count_spin.setValue(pen.count)
            table.setCellWidget(row, 4, count_spin)

            format_combo = QComboBox()
            format_combo.addItems(VALUE_FORMATS)
            format_combo.setCurrentText(pen.format)
            format_combo.currentTextChanged.connect(
                lambda text, c=count_spin: self._coerce_count_for_format(text, c)
            )
            table.setCellWidget(row, 5, format_combo)

            color_btn = ColorButton(pen.color)
            table.setCellWidget(row, 6, color_btn)

            self._rows.append({
                "enabled": enabled_box,
                "name": name_edit,
                "type": type_combo,
                "address": address_spin,
                "count": count_spin,
                "format": format_combo,
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

    @staticmethod
    def _coerce_count_for_format(format_text, count_spin):
        """Keep the register count valid for 32-bit formats (must be even), matching the Tags table."""
        base = format_text.replace("_SWAP", "")
        if base in ("U32", "S32", "F32") and count_spin.value() % 2 != 0:
            count_spin.setValue(2)

    def apply_to(self, pens):
        """Copy the dialog's field values back onto the pen objects."""
        for row, widgets in enumerate(self._rows):
            pen = pens[row]
            pen.enabled = widgets["enabled"].isChecked()
            pen.name = widgets["name"].text().strip()
            pen.type = widgets["type"].currentText()
            pen.address = widgets["address"].value()
            pen.count = widgets["count"].value()
            pen.format = widgets["format"].currentText()
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


class TrendWidget(QWidget):
    """SCADA-style trend tab: up to 20 live-polled pens plotted over time, live or historical."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.pens = [TrendPen(i, DEFAULT_PEN_COLORS[i % len(DEFAULT_PEN_COLORS)]) for i in range(MAX_PENS)]
        self.mode = "live"
        self.window_seconds = TIME_WINDOWS[0][1]
        self.running = False
        self.graph_settings = {
            "background_color": QColor("#FFFFFF"),
            "axis_color": QColor("#333333"),
            "grid_visible": True,
            "grid_color": QColor("#DDDDDD"),
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
        toolbar.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Live", "Hist"])
        self.mode_combo.setStyleSheet(self._input_style())
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_combo)

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

    # --- Pen configuration ---

    def _open_add_pen_dialog(self):
        dialog = AddPenDialog(self.pens, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.apply_to(self.pens)
            self._sync_series()

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
        self.chart.setBackgroundBrush(s["background_color"])
        axis_pen = QPen(s["axis_color"])
        self.axis_x.setLinePen(axis_pen)
        self.axis_y.setLinePen(axis_pen)
        self.axis_x.setLabelsColor(s["axis_color"])
        self.axis_y.setLabelsColor(s["axis_color"])
        self.axis_x.setGridLineVisible(s["grid_visible"])
        self.axis_y.setGridLineVisible(s["grid_visible"])
        grid_pen = QPen(s["grid_color"])
        self.axis_x.setGridLinePen(grid_pen)
        self.axis_y.setGridLinePen(grid_pen)
        self.axis_x.setTitleText(s["x_title"])
        self.axis_y.setTitleText(s["y_title"])
        if not s["y_auto"]:
            self.axis_y.setRange(s["y_min"], s["y_max"])

    # --- Mode / time window / zoom ---

    def _on_mode_changed(self, text):
        self.mode = "live" if text == "Live" else "hist"
        if self.mode == "live":
            self._apply_time_window(anchor_now=True)

    def _on_window_changed(self, _index):
        self.window_seconds = self.window_combo.currentData()
        self._apply_time_window(anchor_now=(self.mode == "live"))

    def _apply_time_window(self, anchor_now):
        if anchor_now:
            now = QDateTime.currentDateTime()
            self.axis_x.setRange(now.addSecs(-self.window_seconds), now)
            return

        current_min = self.axis_x.min()
        current_max = self.axis_x.max()
        center = current_min.addMSecs(current_min.msecsTo(current_max) // 2)
        half = self.window_seconds * 1000 // 2
        self.axis_x.setRange(center.addMSecs(-half), center.addMSecs(half))

    def _zoom(self, factor):
        new_span = max(MIN_WINDOW_SECONDS, min(MAX_WINDOW_SECONDS, self.window_seconds * factor))
        self.window_seconds = int(new_span)
        self._apply_time_window(anchor_now=(self.mode == "live"))

    def _go_to_range(self):
        """Jump the view directly to a typed From/To range (switches to Hist mode)."""
        from_dt = self.from_datetime_edit.dateTime()
        to_dt = self.to_datetime_edit.dateTime()
        if from_dt >= to_dt:
            QMessageBox.warning(self, "Invalid Range", "'From' must be earlier than 'To'.")
            return

        self.mode_combo.setCurrentText("Hist")
        self.window_seconds = max(MIN_WINDOW_SECONDS, from_dt.secsTo(to_dt))
        self.axis_x.setRange(from_dt, to_dt)

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
        if self.mode == "live":
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
            if self.mode == "live":
                self.axis_x.setRange(now.addSecs(-self.window_seconds), now)

    def _read_pen_value(self, modbus, pen):
        try:
            if pen.type == "Coil":
                data = modbus.read_coils(pen.address, pen.count)
            elif pen.type == "Discrete Input":
                data = modbus.read_discrete_inputs(pen.address, pen.count)
            elif pen.type == "Input Register":
                data = modbus.read_input_registers(pen.address, pen.count)
            else:
                data = modbus.read_registers(pen.address, pen.count)

            if data is None:
                return None

            if pen.type in ("Coil", "Discrete Input"):
                first = data[0] if isinstance(data, list) else data
                return 1.0 if bool(first) else 0.0

            registers = data if isinstance(data, list) else [data]
            decoder = getattr(self.parent_window, "_decode_register_values", None)
            decoded = decoder(registers, pen.format) if decoder else registers
            value = decoded[0] if isinstance(decoded, list) else decoded
            return float(value)
        except Exception:
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
