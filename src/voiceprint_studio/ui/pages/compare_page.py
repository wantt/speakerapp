"""Pairwise speaker comparison page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...context import AppContext
from ...engine import DEFAULT_THRESHOLD, cosine_similarity
from ..widgets import AudioInputCard, Badge, Card, SimilarityGauge, page_header
from ..worker import run_async


class ComparePage(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setObjectName("pageBody")
        self.ctx = ctx
        self._worker = None
        self._score: float | None = None
        self._durations: tuple[float, float] = (0.0, 0.0)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(page_header(
            "声纹比对",
            "输入两段音频，计算余弦相似度并按照阈值判断是否为同一说话人。",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(16)

        self.audio_a = AudioInputCard("音频 A", "第一个说话人的语音")
        self.audio_b = AudioInputCard("音频 B", "第二个说话人的语音")
        self.audio_a.audioChanged.connect(self._reset_result)
        self.audio_b.audioChanged.connect(self._reset_result)
        left.addWidget(self.audio_a)
        left.addWidget(self.audio_b)

        action_card = Card("比对设置")
        row = QHBoxLayout()
        row.setSpacing(10)
        threshold_label = QLabel("判定阈值")
        threshold_label.setObjectName("fieldLabel")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 1.0)
        self.threshold_spin.setDecimals(3)
        self.threshold_spin.setSingleStep(0.005)
        self.threshold_spin.setValue(DEFAULT_THRESHOLD)
        self.threshold_spin.setFixedWidth(96)
        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)
        hint = QLabel("得分 ≥ 阈值判定为同一人；默认 0.365 来自模型卡片。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.compare_btn = QPushButton("开始比对")
        self.compare_btn.setObjectName("primary")
        self.compare_btn.clicked.connect(self.compare)
        row.addWidget(threshold_label)
        row.addWidget(self.threshold_spin)
        row.addWidget(hint, 1)
        row.addWidget(self.compare_btn)
        action_card.body.addLayout(row)
        self.status_label = QLabel("选择两段音频后开始比对。")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        action_card.body.addWidget(self.status_label)
        left.addWidget(action_card)
        left.addStretch(1)

        result_card = Card("比对结果")
        result_card.setFixedWidth(360)
        self.gauge = SimilarityGauge()
        result_card.body.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignHCenter)
        self.badge = Badge("等待比对", "neutral")
        result_card.body.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        self.result_desc = QLabel("")
        self.result_desc.setObjectName("hint")
        self.result_desc.setWordWrap(True)
        self.result_desc.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        result_card.body.addWidget(self.result_desc)
        result_card.body.addSpacing(4)
        self.detail_label = QLabel("模型：ERes2NetV2 · 192 维声纹 embedding")
        self.detail_label.setObjectName("muted")
        self.detail_label.setWordWrap(True)
        result_card.body.addWidget(self.detail_label)
        result_card.body.addStretch(1)
        columns.addLayout(left, 1)
        columns.addWidget(result_card)
        root.addLayout(columns, 1)

    # -------------------------------------------------------------- helpers
    def _threshold(self) -> float:
        return float(self.threshold_spin.value())

    def _reset_result(self) -> None:
        self._score = None
        self.gauge.set_result(None, self._threshold())
        self.badge.set_kind("neutral", "等待比对")
        self.result_desc.setText("")
        self.detail_label.setText("模型：ERes2NetV2 · 192 维声纹 embedding")

    def _on_threshold_changed(self) -> None:
        if self._score is None:
            self.gauge.set_result(None, self._threshold())
            return
        self._show_result(self._score, self._durations)

    def _show_result(self, score: float, durations: tuple[float, float]) -> None:
        threshold = self._threshold()
        same = score >= threshold
        self.gauge.set_result(score, threshold)
        self.badge.set_kind("success" if same else "danger", "同一人" if same else "不同人")
        if same:
            self.result_desc.setText(f"相似度 {score:.3f} 高于阈值 {threshold:.3f}，判定为同一说话人。")
        else:
            self.result_desc.setText(f"相似度 {score:.3f} 低于阈值 {threshold:.3f}，判定为不同说话人。")
        self.detail_label.setText(
            f"音频 A：{durations[0]:.1f} 秒　·　音频 B：{durations[1]:.1f} 秒\n"
            "模型：ERes2NetV2 · 192 维声纹 embedding"
        )

    # --------------------------------------------------------------- action
    def compare(self) -> None:
        clip_a = self.audio_a.clip
        clip_b = self.audio_b.clip
        if clip_a is None or clip_b is None:
            QMessageBox.information(self, "缺少音频", "请为 A、B 两段都选择或录制语音。")
            return
        if not self.ctx.engine_loaded:
            QMessageBox.information(self, "模型加载中", "声纹模型正在加载，请稍候几秒再试。")
            return

        self.compare_btn.setEnabled(False)
        self.compare_btn.setText("正在比对…")
        self.status_label.setText("正在提取两段音频的声纹特征…")

        engine = self.ctx.engine

        def job():
            emb_a = engine.embed(clip_a.samples, clip_a.sample_rate)
            emb_b = engine.embed(clip_b.samples, clip_b.sample_rate)
            return cosine_similarity(emb_a, emb_b), clip_a.duration, clip_b.duration

        self._worker = run_async(job, self._on_done, self._on_error)

    def _on_done(self, result) -> None:
        score, dur_a, dur_b = result
        self._score = float(score)
        self._durations = (float(dur_a), float(dur_b))
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("开始比对")
        self.status_label.setObjectName("hint")
        self.status_label.setText("比对完成。调整阈值可实时更新判定结果。")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._show_result(self._score, self._durations)

    def _on_error(self, message: str) -> None:
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("开始比对")
        self.status_label.setText(message)
        QMessageBox.warning(self, "比对失败", message)

    def shutdown(self) -> None:
        self.audio_a.shutdown()
        self.audio_b.shutdown()