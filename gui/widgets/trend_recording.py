"""Trend Record/Replay: capture a running Trend to a file and play it back later.

Deliberately isolated from TrendWidget's own pens/chart/QLineSeries -- see
TrendRecordingWindow's docstring. Recording taps TrendWidget.sample_tick (emitted once
per poll tick from _poll_pens); replay renders entirely inside this window's own chart,
so a loaded recording can never appear in -- or be mistaken for -- the live Trend view.
"""
import json
import os
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QDateTime
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QScrollBar, QFileDialog, QMessageBox, QSizePolicy
)
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis

from theme import apply_dropdown_delegate

FILE_VERSION = 1
FILE_FILTER = "ModbusLens Trend Recording (*.mltrend)"
REPLAY_SPEEDS = [("1x", 1.0), ("2x", 2.0), ("4x", 4.0), ("8x", 8.0)]
REPLAY_TICK_MS = 100  # how often the replay driver advances its virtual clock


class TrendRecording:
    """A captured (or loaded) Trend run: frozen pen metadata + an ordered list of ticks.
    No Qt object references -- this is exactly what a .mltrend file holds.

    ticks: [{"t": ms_since_recording_start, "v": {"<pen_slot>": value, ...}}, ...]
    """

    def __init__(self, pens, interval_ms, recorded_at=None, ticks=None):
        self.pens = pens
        self.interval_ms = interval_ms
        self.recorded_at = recorded_at or datetime.now().isoformat(timespec="seconds")
        self.ticks = ticks if ticks is not None else []

    def duration_ms(self):
        return self.ticks[-1]["t"] if self.ticks else 0

    def save(self, path):
        data = {
            "version": FILE_VERSION,
            "recorded_at": self.recorded_at,
            "interval_ms": self.interval_ms,
            "pens": self.pens,
            "ticks": self.ticks,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    @staticmethod
    def load(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TrendRecording(
            pens=data.get("pens", []),
            interval_ms=data.get("interval_ms", 1000),
            recorded_at=data.get("recorded_at"),
            ticks=data.get("ticks", []),
        )


class TrendRecordingWindow(QDialog):
    """Standalone Record/Replay window opened from the Trend tab's "Record / Replay"
    button. Non-modal and reused across opens (TrendWidget keeps one instance alive and
    just show()/raise()s it), the same lazy-singleton pattern NetworkDiagnosticsDialog
    uses. Never reads or writes TrendWidget.pens/chart -- recording snapshots pen
    metadata once at start and only listens to TrendWidget.sample_tick; replay renders
    into this window's own QChart from a loaded file. That separation is deliberate:
    replayed data must never be able to show up in the live Trend view."""

    def __init__(self, trend_widget, parent=None):
        super().__init__(parent or trend_widget)
        self.trend_widget = trend_widget
        self.setWindowTitle("Trend Recording / Replay - ModbusLens")
        self.resize(900, 650)

        self._mode = "idle"  # "idle" | "recording" | "replay"
        self._recording = None  # TrendRecording currently being captured or loaded
        self._pen_series = {}  # pen slot (int) -> QLineSeries, this window's own chart
        self._record_start_epoch_ms = None
        self._replay_base_epoch_ms = None
        self._replay_elapsed_ms = 0
        self._replay_playing = False
        self._updating_scrub = False

        self._replay_timer = QTimer(self)
        self._replay_timer.timeout.connect(self._advance_replay)

        self._setup_ui()
        self._apply_mode()

    # --- Shared styling (reuse TrendWidget's, which itself reuses ModbusGUI's) ---

    def _button_style(self):
        return self.trend_widget._button_style()

    def _input_style(self):
        return self.trend_widget._input_style()

    def _colors(self):
        parent_window = getattr(self.trend_widget, "parent_window", None)
        if parent_window is not None and hasattr(parent_window, "_colors"):
            return parent_window._colors()
        return {}

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.heading_label = QLabel("RECORD / REPLAY")
        heading_font = QFont()
        heading_font.setPointSize(20)
        heading_font.setBold(True)
        self.heading_label.setFont(heading_font)
        self.heading_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.heading_label)

        self.status_label = QLabel("Start a recording or load a previous one below.")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        control_row = QHBoxLayout()
        self.record_btn = QPushButton("Start Recording")
        self.record_btn.setStyleSheet(self._button_style())
        self.record_btn.clicked.connect(self._on_record_button)
        control_row.addWidget(self.record_btn)

        self.load_btn = QPushButton("Load Replay")
        self.load_btn.setStyleSheet(self._button_style())
        self.load_btn.clicked.connect(self._load_replay)
        control_row.addWidget(self.load_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.setStyleSheet(self._button_style())
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_recording)
        control_row.addWidget(self.export_btn)
        control_row.addStretch()
        layout.addLayout(control_row)

        self.chart = QChart()
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm:ss")
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.axis_y = QValueAxis()
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        now = QDateTime.currentDateTime()
        self.axis_x.setRange(now.addSecs(-60), now)
        self.axis_y.setRange(0, 100)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.chart_view, 1)

        self.scrub_bar = QScrollBar(Qt.Horizontal)
        self.scrub_bar.setEnabled(False)
        self.scrub_bar.valueChanged.connect(self._on_scrub_moved)
        layout.addWidget(self.scrub_bar)

        transport_row = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.setStyleSheet(self._button_style())
        self.play_btn.clicked.connect(self._toggle_play)
        transport_row.addWidget(self.play_btn)

        transport_row.addWidget(QLabel("Speed:"))
        self.speed_combo = QComboBox()
        for label, _factor in REPLAY_SPEEDS:
            self.speed_combo.addItem(label)
        self.speed_combo.setStyleSheet(self._input_style())
        apply_dropdown_delegate(
            self.speed_combo,
            getattr(getattr(self.trend_widget, "parent_window", None), "_theme_mode", "light"),
        )
        transport_row.addWidget(self.speed_combo)
        transport_row.addStretch()
        layout.addLayout(transport_row)

    # --- Mode / heading ---

    def _apply_mode(self):
        c = self._colors()
        if self._mode == "recording":
            text, color = "● RECORDING", c.get("error", "#D32F2F")
        elif self._mode == "replay":
            text, color = "▶ REPLAY", c.get("accent", "#1565C0")
        else:
            text, color = "RECORD / REPLAY", c.get("text", "#000000")
        self.heading_label.setText(text)
        self.heading_label.setStyleSheet(f"color: {color};")

        self.record_btn.setText("Stop Recording" if self._mode == "recording" else "Start Recording")
        self.load_btn.setEnabled(self._mode != "recording")
        self.export_btn.setEnabled(self._recording is not None and bool(self._recording.ticks))
        transport_enabled = self._mode == "replay"
        self.play_btn.setEnabled(transport_enabled)
        self.speed_combo.setEnabled(transport_enabled)
        self.scrub_bar.setEnabled(transport_enabled)

    # --- Shared chart helpers ---

    def _reset_chart(self):
        self._replay_timer.stop()
        self._replay_playing = False
        self.play_btn.setText("Play")
        for series in self._pen_series.values():
            self.chart.removeSeries(series)
        self._pen_series = {}
        self.scrub_bar.setEnabled(False)

    def _build_series_for_pens(self, pens):
        for pen_data in pens:
            series = QLineSeries()
            series.setName(pen_data.get("label") or pen_data["name"])
            series.setPen(QPen(QColor(pen_data["color"]), 2))
            self.chart.addSeries(series)
            series.attachAxis(self.axis_x)
            series.attachAxis(self.axis_y)
            self._pen_series[pen_data["slot"]] = series

    def _update_y_range(self):
        values = [p.y() for series in self._pen_series.values() for p in series.points()]
        if not values:
            return
        lo, hi = min(values), max(values)
        if lo == hi:
            lo -= 1
            hi += 1
        margin = (hi - lo) * 0.1
        self.axis_y.setRange(lo - margin, hi + margin)

    # --- Recording ---

    def _on_record_button(self):
        if self._mode == "recording":
            self._stop_recording()
        else:
            self._start_recording()

    def _snapshot_active_pens(self):
        return [
            {
                "slot": pen.slot, "name": pen.name, "label": pen.label, "type": pen.type,
                "address": pen.address, "count": pen.count, "format": pen.format,
                "index": pen.index, "scale_mode": pen.scale_mode, "color": pen.color.name(),
            }
            for pen in self.trend_widget.pens if pen.is_active()
        ]

    def _start_recording(self):
        pens = self._snapshot_active_pens()
        if not pens:
            QMessageBox.warning(self, "No Pens", "Add at least one active pen in Trend before recording.")
            return

        if self._mode == "recording":
            self._stop_recording()
        self._reset_chart()

        interval_ms = self.trend_widget.interval_input.value()
        self._recording = TrendRecording(pens=pens, interval_ms=interval_ms)
        self._build_series_for_pens(pens)
        self._record_start_epoch_ms = None
        self.trend_widget.sample_tick.connect(self._on_recorded_tick)

        self._mode = "recording"
        self._apply_mode()
        self.status_label.setText("Recording... 0 samples")

    def _on_recorded_tick(self, epoch_ms, values):
        if self._mode != "recording" or self._recording is None:
            return
        if self._record_start_epoch_ms is None:
            self._record_start_epoch_ms = epoch_ms

        t = epoch_ms - self._record_start_epoch_ms
        recorded_values = {}
        for slot, value in values.items():
            series = self._pen_series.get(slot)
            if series is None:
                continue
            series.append(epoch_ms, value)
            recorded_values[str(slot)] = value
        if not recorded_values:
            return
        self._recording.ticks.append({"t": t, "v": recorded_values})

        self._update_y_range()
        now = QDateTime.fromMSecsSinceEpoch(epoch_ms)
        self.axis_x.setRange(now.addSecs(-60), now)

        elapsed_s = t / 1000
        self.status_label.setText(f"Recording... {elapsed_s:.0f}s elapsed, {len(self._recording.ticks)} samples")

    def _stop_recording(self):
        try:
            self.trend_widget.sample_tick.disconnect(self._on_recorded_tick)
        except (RuntimeError, TypeError):
            pass
        self._mode = "idle"
        self._apply_mode()
        count = len(self._recording.ticks) if self._recording else 0
        self.status_label.setText(f"Recording stopped -- {count} samples captured. Use Export to save.")

    # --- Replay ---

    def _load_replay(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Trend Recording", "", FILE_FILTER)
        if not path:
            return
        try:
            recording = TrendRecording.load(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.critical(self, "Load Failed", f"Could not load recording: {e}")
            return
        if not recording.pens or not recording.ticks:
            QMessageBox.warning(self, "Empty Recording", "That file has no pens or no samples to replay.")
            return

        if self._mode == "recording":
            self._stop_recording()
        self._reset_chart()
        self._recording = recording
        self._build_series_for_pens(recording.pens)

        # Anchor the replay's x-axis to when it was actually recorded (not "now") --
        # showing the original wall-clock time keeps a loaded replay visibly historical,
        # never confusable with the live Trend view's current timestamps.
        self._replay_base_epoch_ms = self._parse_recorded_at_epoch_ms(recording.recorded_at)
        self._replay_elapsed_ms = 0

        duration = recording.duration_ms()
        self.scrub_bar.setRange(0, max(0, duration))
        self.scrub_bar.setValue(0)

        self._mode = "replay"
        self._apply_mode()
        self._render_replay_up_to(0)
        self.status_label.setText(
            f"Loaded {os.path.basename(path)} -- {len(recording.ticks)} samples, {duration / 1000:.0f}s"
        )

    @staticmethod
    def _parse_recorded_at_epoch_ms(recorded_at):
        dt = QDateTime.fromString(recorded_at or "", Qt.ISODate)
        if not dt.isValid():
            dt = QDateTime.currentDateTime()
        return dt.toMSecsSinceEpoch()

    def _toggle_play(self):
        if self._mode != "replay" or self._recording is None:
            return
        self._replay_playing = not self._replay_playing
        self.play_btn.setText("Pause" if self._replay_playing else "Play")
        if self._replay_playing:
            if self._replay_elapsed_ms >= self._recording.duration_ms():
                self._replay_elapsed_ms = 0
            self._replay_timer.start(REPLAY_TICK_MS)
        else:
            self._replay_timer.stop()

    def _current_speed(self):
        return REPLAY_SPEEDS[self.speed_combo.currentIndex()][1]

    def _advance_replay(self):
        if self._recording is None:
            return
        self._replay_elapsed_ms += REPLAY_TICK_MS * self._current_speed()
        duration = self._recording.duration_ms()
        if self._replay_elapsed_ms >= duration:
            self._replay_elapsed_ms = duration
            self._render_replay_up_to(self._replay_elapsed_ms)
            self._replay_playing = False
            self.play_btn.setText("Play")
            self._replay_timer.stop()
            return
        self._render_replay_up_to(self._replay_elapsed_ms)

    def _render_replay_up_to(self, elapsed_ms):
        """Rebuild every pen's preview series from scratch up to elapsed_ms. Recordings
        are bounded by however long the user chose to record, so re-walking the tick
        list on every step/scrub is simpler and safer than incremental append/remove
        bookkeeping, at the cost of being O(n) per step instead of O(1)."""
        if self._recording is None:
            return
        for series in self._pen_series.values():
            series.clear()

        last_t = 0
        for tick in self._recording.ticks:
            if tick["t"] > elapsed_ms:
                break
            last_t = tick["t"]
            x_ms = self._replay_base_epoch_ms + tick["t"]
            for slot_str, value in tick["v"].items():
                series = self._pen_series.get(int(slot_str))
                if series is not None:
                    series.append(x_ms, value)

        self._update_y_range()
        window_start = QDateTime.fromMSecsSinceEpoch(self._replay_base_epoch_ms)
        window_end = QDateTime.fromMSecsSinceEpoch(self._replay_base_epoch_ms + max(last_t, 1000))
        self.axis_x.setRange(window_start, window_end)

        self._updating_scrub = True
        try:
            self.scrub_bar.setValue(int(elapsed_ms))
        finally:
            self._updating_scrub = False

        duration = self._recording.duration_ms()
        self.status_label.setText(f"Replaying... {elapsed_ms / 1000:.0f}s / {duration / 1000:.0f}s")

    def _on_scrub_moved(self, value):
        if self._updating_scrub or self._mode != "replay":
            return
        self._replay_elapsed_ms = value
        self._render_replay_up_to(value)

    # --- Export ---

    def _export_recording(self):
        if self._recording is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Trend Recording",
            f"trend_recording_{time.strftime('%Y%m%d_%H%M%S')}.mltrend", FILE_FILTER
        )
        if not path:
            return
        try:
            self._recording.save(path)
        except OSError as e:
            QMessageBox.critical(self, "Export Failed", f"Could not save recording: {e}")
            return
        QMessageBox.information(self, "Export Complete", f"Recording saved to {path}")
