"""Reusable UI widgets: cards, waveform, audio input, gauge."""

from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..audio import (
    AUDIO_FILTER,
    AudioClip,
    AudioError,
    AudioPlayer,
    Recorder,
    decode_audio,
    format_duration,
    waveform_peaks,
)
from .theme import ACCENT, DANGER, MUTED, SUCCESS, WARNING

MAX_RECORD_SECONDS = 60.0


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(12)
        if title:
            head = QVBoxLayout()
            head.setSpacing(2)
            title_label = QLabel(title)
            title_label.setObjectName("cardTitle")
            head.addWidget(title_label)
            if subtitle:
                sub = QLabel(subtitle)
                sub.setObjectName("cardSubtitle")
                sub.setWordWrap(True)
                head.addWidget(sub)
            outer.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        outer.addLayout(self.body)


class Badge(QLabel):
    _NAMES = {
        "success": "badgeSuccess",
        "danger": "badgeDanger",
        "neutral": "badgeNeutral",
    }

    def __init__(self, text: str = "", kind: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_kind(kind, text)

    def set_kind(self, kind: str, text: str | None = None) -> None:
        self.setObjectName(self._NAMES.get(kind, "badgeNeutral"))
        if text is not None:
            self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


class StatTile(QFrame):
    def __init__(self, caption: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setObjectName("innerPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("bigStat")
        caption_label = QLabel(caption)
        caption_label.setObjectName("statCaption")
        layout.addWidget(self.value_label)
        layout.addWidget(caption_label)

    def set_value(self, value: str | int) -> None:
        self.value_label.setText(str(value))


class WaveformWidget(QWidget):
    """Waveform renderer with click-to-seek and playback cursor."""

    seekRequested = Signal(float)  # fraction in [0, 1]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(116)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clip: AudioClip | None = None
        self._progress = 0.0
        self._mins = None
        self._maxs = None
        self._peaks_key = None

    def sizeHint(self) -> QSize:
        return QSize(520, 120)

    def set_clip(self, clip: AudioClip | None) -> None:
        self._clip = clip
        self._progress = 0.0
        self._peaks_key = None
        self.update()

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def _ensure_peaks(self, width: int) -> None:
        if self._clip is None:
            return
        points = max(8, int(width / 2))
        key = (id(self._clip), points)
        if self._peaks_key == key:
            return
        self._mins, self._maxs = waveform_peaks(self._clip.samples, points)
        self._peaks_key = key

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        painter.fillPath(path, QColor("#0B1220"))
        painter.setPen(QPen(QColor("#1E293B"), 1))
        painter.drawPath(path)

        if self._clip is None or self._clip.samples.size == 0:
            painter.setPen(QColor("#64748B"))
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "拖入音频文件，或点击下方按钮选择 / 录制")
            return

        left = 12.0
        right = rect.width() - 12.0
        top = 12.0
        bottom = rect.height() - 22.0
        plot_w = max(1.0, right - left)
        plot_h = max(1.0, bottom - top)
        center_y = (top + bottom) / 2.0

        # Grid + time labels.
        grid_pen = QPen(QColor("#1E293B"), 1)
        painter.setPen(grid_pen)
        for i in range(5):
            x = left + plot_w * i / 4.0
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
        painter.setPen(QPen(QColor("#1E293B"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(left, center_y), QPointF(right, center_y))

        label_font = painter.font()
        label_font.setPointSize(8)
        painter.setFont(label_font)
        painter.setPen(QColor("#64748B"))
        duration = self._clip.duration
        for i, frac in enumerate((0.0, 0.25, 0.5, 0.75, 1.0)):
            text = format_duration(duration * frac)
            align = Qt.AlignmentFlag.AlignLeft
            if i == 0:
                align = Qt.AlignmentFlag.AlignLeft
            elif i == 4:
                align = Qt.AlignmentFlag.AlignRight
            else:
                align = Qt.AlignmentFlag.AlignHCenter
            x = left + plot_w * frac
            label_rect = QRectF(x - 26, bottom + 2, 52, 16)
            painter.drawText(label_rect, align, text)

        self._ensure_peaks(int(plot_w))
        mins, maxs = self._mins, self._maxs
        if mins is None or maxs is None:
            return
        n = len(maxs)
        step = plot_w / max(1, n)
        top_path = QPainterPath()
        bottom_path = QPainterPath()
        for i in range(n):
            x = left + (i + 0.5) * step
            y_top = center_y - float(maxs[i]) * (plot_h / 2.0) * 0.92
            y_bottom = center_y - float(mins[i]) * (plot_h / 2.0) * 0.92
            if i == 0:
                top_path.moveTo(x, y_top)
                bottom_path.moveTo(x, y_bottom)
            else:
                top_path.lineTo(x, y_top)
                bottom_path.lineTo(x, y_bottom)

        envelope = QPainterPath(top_path)
        for i in range(n - 1, -1, -1):
            x = left + (i + 0.5) * step
            y_bottom = center_y - float(mins[i]) * (plot_h / 2.0) * 0.92
            envelope.lineTo(x, y_bottom)
        envelope.closeSubpath()

        gradient = QLinearGradient(0, top, 0, bottom)
        gradient.setColorAt(0.0, QColor("#818CF8"))
        gradient.setColorAt(0.5, QColor("#6366F1"))
        gradient.setColorAt(1.0, QColor("#22D3EE"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(envelope)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#A5B4FC"), 0.8))
        painter.drawPath(top_path)
        painter.drawPath(bottom_path)

        if self._progress > 0.001:
            x = left + plot_w * self._progress
            painter.setPen(QPen(QColor("#F8FAFC"), 1.6))
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.setBrush(QColor("#F8FAFC"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, top), 3.2, 3.2)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._clip is None or event.button() != Qt.MouseButton.LeftButton:
            return
        width = max(1.0, self.width() - 24.0)
        frac = (event.position().x() - 12.0) / width
        self.seekRequested.emit(max(0.0, min(1.0, frac)))


class SimilarityGauge(QWidget):
    """Semicircular gauge that visualises a cosine similarity score."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 170)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._score: float | None = None
        self._threshold = 0.365

    def sizeHint(self) -> QSize:
        return QSize(240, 180)

    def set_result(self, score: float | None, threshold: float) -> None:
        self._score = score
        self._threshold = threshold
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        side = min(rect.width(), rect.height() * 1.15) - 16
        gauge_rect = QRectF(
            rect.center().x() - side / 2,
            rect.center().y() - side / 2 + 8,
            side,
            side,
        )
        start_angle = 225.0
        span = 270.0

        bg_pen = QPen(QColor("#E2E8F0"), 13)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(gauge_rect, int((90 - start_angle) * 16), int(-span * 16))

        if self._score is None:
            painter.setPen(QColor("#94A3B8"))
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "等待比对")
            return

        score = max(0.0, min(1.0, float(self._score)))
        color = QColor(SUCCESS if score >= self._threshold else WARNING)
        value_pen = QPen(color, 13)
        value_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(value_pen)
        painter.drawArc(gauge_rect, int((90 - start_angle) * 16), int(-span * score * 16))

        # Threshold marker.
        angle = math.radians(start_angle + span * max(0.0, min(1.0, self._threshold)))
        cx = gauge_rect.center().x()
        cy = gauge_rect.center().y()
        r = side / 2
        p1 = QPointF(cx + math.cos(angle) * (r - 14), cy - math.sin(angle) * (r - 14))
        p2 = QPointF(cx + math.cos(angle) * (r + 6), cy - math.sin(angle) * (r + 6))
        painter.setPen(QPen(QColor("#94A3B8"), 2))
        painter.drawLine(p1, p2)

        painter.setPen(QColor("#0F172A"))
        big = painter.font()
        big.setPointSize(22)
        big.setBold(True)
        painter.setFont(big)
        score_rect = QRectF(rect.center().x() - side / 2, rect.center().y() - 12, side, 46)
        painter.drawText(score_rect, Qt.AlignmentFlag.AlignCenter, f"{self._score:.3f}")

        small = painter.font()
        small.setPointSize(9)
        small.setBold(False)
        painter.setFont(small)
        painter.setPen(QColor("#64748B"))
        caption_rect = QRectF(rect.center().x() - side / 2, rect.center().y() + 30, side, 20)
        painter.drawText(caption_rect, Qt.AlignmentFlag.AlignCenter,
                         f"余弦相似度 · 阈值 {self._threshold:.3f}")


class AudioInputCard(Card):
    """Audio selection / recording card with waveform and playback."""

    audioChanged = Signal()

    def __init__(self, title: str = "音频", subtitle: str | None = None, parent=None):
        super().__init__(title, subtitle, parent)
        self.clip: AudioClip | None = None
        self._player = AudioPlayer()
        self._recorder = Recorder()
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(90)
        self._play_timer.timeout.connect(self._on_play_tick)
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(90)
        self._rec_timer.timeout.connect(self._on_record_tick)
        self._play_origin = 0.0
        self._play_started = 0.0
        self._seek_fraction = 0.0
        self._record_started = 0.0

        self.waveform = WaveformWidget()
        self.waveform.seekRequested.connect(self._on_seek)
        self.body.addWidget(self.waveform)

        self.file_btn = QPushButton("选择文件")
        self.file_btn.setObjectName("secondary")
        self.file_btn.clicked.connect(self.browse_file)
        self.record_btn = QPushButton("● 录制")
        self.record_btn.setObjectName("secondary")
        self.record_btn.clicked.connect(self.toggle_record)
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setObjectName("secondary")
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setEnabled(False)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.file_btn)
        row.addWidget(self.record_btn)
        row.addWidget(self.play_btn)
        row.addStretch(1)
        self.status_label = QLabel("未选择音频")
        self.status_label.setObjectName("muted")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.status_label)
        self.body.addLayout(row)

        self.setAcceptDrops(True)

    # ---------------------------------------------------------------- state
    def set_audio(self, clip: AudioClip, source_label: str | None = None) -> None:
        self.stop_playback(reset=True)
        if self._recorder.is_recording:
            self._stop_recording()
        self.clip = clip
        self._seek_fraction = 0.0
        self.waveform.set_clip(clip)
        label = source_label or (Path(clip.path).name if clip.path else "录音")
        self.status_label.setText(f"{label} · {format_duration(clip.duration)}")
        self.status_label.setToolTip(clip.path or "麦克风录音")
        self.play_btn.setEnabled(True)
        self.audioChanged.emit()

    def clear(self) -> None:
        self.stop_playback(reset=True)
        self.clip = None
        self._seek_fraction = 0.0
        self.waveform.set_clip(None)
        self.status_label.setText("未选择音频")
        self.status_label.setToolTip("")
        self.play_btn.setEnabled(False)
        self.audioChanged.emit()

    # ---------------------------------------------------------------- file
    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择音频文件", str(Path.home()), AUDIO_FILTER)
        if path:
            self.load_file(path)

    def load_file(self, path: str) -> None:
        try:
            clip = decode_audio(path)
        except AudioError as exc:
            QMessageBox.warning(self, "无法读取音频", str(exc))
            return
        self.set_audio(clip, Path(path).name)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_file(url.toLocalFile())
                event.acceptProposedAction()
                return

    # ---------------------------------------------------------------- record
    def toggle_record(self) -> None:
        if self._recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self.stop_playback(reset=True)
        try:
            self._recorder.start()
        except AudioError as exc:
            QMessageBox.warning(self, "无法录音", str(exc))
            return
        self._record_started = time.monotonic()
        self.record_btn.setText("■ 停止录制")
        self.file_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.status_label.setText("录音中 · 0.0s")
        self.waveform.set_clip(None)
        self._rec_timer.start()

    def _stop_recording(self) -> None:
        self._rec_timer.stop()
        self.record_btn.setText("● 录制")
        self.file_btn.setEnabled(True)
        try:
            clip = self._recorder.stop()
        except AudioError as exc:
            self.waveform.set_clip(None)
            self.status_label.setText("未选择音频")
            QMessageBox.warning(self, "录音失败", str(exc))
            self.audioChanged.emit()
            return
        self.set_audio(clip, "麦克风录音")

    def _on_record_tick(self) -> None:
        elapsed = time.monotonic() - self._record_started
        samples, sr = self._recorder.snapshot(seconds=3.0)
        if samples.size:
            self.waveform.set_clip(AudioClip(samples=samples, sample_rate=sr))
        self.status_label.setText(f"录音中 · {elapsed:.1f}s")
        if elapsed >= MAX_RECORD_SECONDS:
            self._stop_recording()

    # -------------------------------------------------------------- playback
    def toggle_play(self) -> None:
        if self._play_timer.isActive():
            self.stop_playback(reset=False)
            return
        if self.clip is None:
            return
        if self._seek_fraction >= 0.999:
            self._seek_fraction = 0.0
        self._start_play(self._seek_fraction)

    def _on_seek(self, fraction: float) -> None:
        self._seek_fraction = fraction
        if self._play_timer.isActive():
            self.stop_playback(reset=False)
            self._start_play(fraction)
        else:
            self.waveform.set_progress(fraction)

    def _start_play(self, fraction: float) -> None:
        if self.clip is None:
            return
        duration = self.clip.duration
        fraction = max(0.0, min(0.999, fraction))
        offset_seconds = duration * fraction
        start_index = int(offset_seconds * self.clip.sample_rate)
        playable = AudioClip(self.clip.samples[start_index:], self.clip.sample_rate, self.clip.path)
        if playable.samples.size == 0:
            return
        try:
            self._player.play(playable)
        except Exception as exc:  # pragma: no cover - audio device dependent
            QMessageBox.warning(self, "无法播放", f"音频设备不可用：\n{exc}")
            return
        self._play_origin = offset_seconds
        self._play_started = time.monotonic()
        self.play_btn.setText("■ 停止")
        self.waveform.set_progress(fraction)
        self._play_timer.start()

    def _on_play_tick(self) -> None:
        if self.clip is None:
            self.stop_playback(reset=True)
            return
        elapsed = self._play_origin + (time.monotonic() - self._play_started)
        if elapsed >= self.clip.duration:
            self.stop_playback(reset=True)
            return
        self.waveform.set_progress(elapsed / max(1e-6, self.clip.duration))
        if not self._player.is_active():
            self.stop_playback(reset=True)

    def stop_playback(self, reset: bool = True) -> None:
        self._play_timer.stop()
        try:
            self._player.stop()
        except Exception:
            pass
        self.play_btn.setText("▶ 播放")
        if reset:
            self.waveform.set_progress(0.0)
            self._seek_fraction = 0.0

    def shutdown(self) -> None:
        if self._recorder.is_recording:
            try:
                self._recorder.stop()
            except Exception:
                pass
        self.stop_playback(reset=True)


def page_header(title: str, subtitle: str) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    subtitle_label = QLabel(subtitle)
    subtitle_label.setObjectName("pageSubtitle")
    subtitle_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(subtitle_label)
    return widget


def make_table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().setVisible(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    header.setHighlightSections(False)
    table.setMinimumHeight(180)
    return table


def set_col_widths(table: QTableWidget, widths: list[int]) -> None:
    header = table.horizontalHeader()
    for i, width in enumerate(widths):
        header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(i, width)
    header.setStretchLastSection(True)