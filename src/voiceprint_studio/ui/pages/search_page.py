"""1:N voiceprint retrieval page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...context import AppContext
from ...engine import DEFAULT_THRESHOLD, cosine_similarity
from ..widgets import AudioInputCard, Badge, Card, make_table, page_header
from ..worker import run_async


class SearchPage(QWidget):
    navigateRequested = Signal(str)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setObjectName("pageBody")
        self.ctx = ctx
        self._worker = None
        self._raw_results: list[tuple[int, str, float, int, int]] | None = None
        self._scan_info: tuple[int, int] = (0, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(page_header(
            "声纹检索",
            "用一段语音在本地声纹库中进行 1:N 检索，找出最相似的已注册说话人。",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(16)

        self.audio_card = AudioInputCard("检索音频", "待识别的语音，建议 3~30 秒。")
        self.audio_card.audioChanged.connect(self._reset_results)
        left.addWidget(self.audio_card)

        options = Card("检索设置")
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
        self.library_label = QLabel("")
        self.library_label.setObjectName("hint")
        self.search_btn = QPushButton("开始检索")
        self.search_btn.setObjectName("primary")
        self.search_btn.clicked.connect(self.search)
        row.addWidget(threshold_label)
        row.addWidget(self.threshold_spin)
        row.addWidget(self.library_label, 1)
        row.addWidget(self.search_btn)
        options.body.addLayout(row)
        self.status_label = QLabel("检索会返回声纹库中相似度最高的说话人。")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        options.body.addWidget(self.status_label)
        left.addWidget(options)
        left.addStretch(1)

        results_card = Card("检索结果")
        head = QHBoxLayout()
        head.setSpacing(10)
        self.summary_badge = Badge("尚无结果", "neutral")
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("hint")
        self.summary_label.setWordWrap(True)
        head.addWidget(self.summary_badge)
        head.addWidget(self.summary_label, 1)
        results_card.body.addLayout(head)

        self.empty_label = QLabel("选择一段语音并点击「开始检索」。")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(160)
        results_card.body.addWidget(self.empty_label)

        self.table = make_table(["排名", "姓名", "最高相似度", "命中样本", "判定"])
        self.table.setVisible(False)
        self.table.setMinimumHeight(300)
        header = self.table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 56)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 92)
        self.table.setColumnWidth(4, 92)
        results_card.body.addWidget(self.table)

        self.register_hint = QPushButton("前往声纹注册 →")
        self.register_hint.setObjectName("ghost")
        self.register_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        self.register_hint.clicked.connect(lambda: self.navigateRequested.emit("register"))
        self.register_hint.setVisible(False)
        results_card.body.addWidget(self.register_hint, 0, Qt.AlignmentFlag.AlignRight)

        columns.addLayout(left, 1)
        columns.addWidget(results_card, 1)
        root.addLayout(columns, 1)

        self.ctx.libraryChanged.connect(self._refresh_library_label)
        self._refresh_library_label()

    # -------------------------------------------------------------- helpers
    def _threshold(self) -> float:
        return float(self.threshold_spin.value())

    def _refresh_library_label(self) -> None:
        speakers, samples = self.ctx.store.stats()
        self.library_label.setText(f"声纹库：{speakers} 人 · {samples} 条样本")

    def _reset_results(self) -> None:
        self._raw_results = None
        self._scan_info = (0, 0)
        self.table.setVisible(False)
        self.empty_label.setVisible(True)
        self.empty_label.setText("选择一段语音并点击「开始检索」。")
        self.register_hint.setVisible(False)
        self.summary_badge.set_kind("neutral", "尚无结果")
        self.summary_label.setText("")
        self.status_label.setObjectName("hint")
        self.status_label.setText("检索会返回声纹库中相似度最高的说话人。")

    def _on_threshold_changed(self) -> None:
        if self._raw_results is not None:
            self._render_results()

    def _render_results(self) -> None:
        if not self._raw_results:
            return
        threshold = self._threshold()
        self.table.setRowCount(0)
        matches = 0
        for idx, (speaker_id, name, best, hits, total) in enumerate(self._raw_results[:10]):
            row = self.table.rowCount()
            self.table.insertRow(row)
            rank = QTableWidgetItem(str(idx + 1))
            rank.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name_item = QTableWidgetItem(name)
            score_item = QTableWidgetItem(f"{best:.3f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            hits_item = QTableWidgetItem(f"{hits} / {total}")
            hits_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if best >= threshold:
                verdict, color = "匹配", QColor("#059669")
                matches += 1
            elif best >= threshold - 0.06:
                verdict, color = "接近阈值", QColor("#B45309")
            else:
                verdict, color = "不匹配", QColor("#94A3B8")
            verdict_item = QTableWidgetItem(verdict)
            verdict_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            score_item.setForeground(color)
            verdict_item.setForeground(color)
            rank_item_color = QColor("#64748B")
            rank.setForeground(rank_item_color)
            self.table.setItem(row, 0, rank)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, score_item)
            self.table.setItem(row, 3, hits_item)
            self.table.setItem(row, 4, verdict_item)
        self.table.setVisible(True)
        self.empty_label.setVisible(False)
        self.register_hint.setVisible(False)

        scanned_samples, scanned_speakers = self._scan_info
        if matches:
            self.summary_badge.set_kind("success", f"找到 {matches} 位匹配声纹")
            self.summary_label.setText(
                f"共扫描 {scanned_samples} 条样本 / {scanned_speakers} 位说话人，"
                f"阈值 {threshold:.3f}。"
            )
        else:
            self.summary_badge.set_kind("danger", "未找到匹配")
            self.summary_label.setText(
                f"已扫描 {scanned_samples} 条样本 / {scanned_speakers} 位说话人，"
                f"没有声音超过阈值 {threshold:.3f}。下方为最接近的候选。"
            )

    # --------------------------------------------------------------- action
    def search(self) -> None:
        clip = self.audio_card.clip
        if clip is None:
            QMessageBox.information(self, "缺少音频", "请先选择或录制一段检索语音。")
            return
        speakers, samples = self.ctx.store.stats()
        if speakers == 0 or samples == 0:
            self.empty_label.setText("声纹库为空。请先注册至少一位说话人的声纹。")
            self.register_hint.setVisible(True)
            self.summary_badge.set_kind("neutral", "声纹库为空")
            return
        if not self.ctx.engine_loaded:
            QMessageBox.information(self, "模型加载中", "声纹模型正在加载，请稍候几秒再试。")
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("正在检索…")
        self.status_label.setObjectName("hint")
        self.status_label.setText("正在提取声纹并扫描本地声纹库…")

        engine = self.ctx.engine
        store = self.ctx.store
        threshold = self._threshold()

        def job():
            probe = engine.embed(clip.samples, clip.sample_rate)
            stored = store.list_samples()
            groups: dict[int, dict] = {}
            for sample in stored:
                score = cosine_similarity(probe, sample.embedding)
                group = groups.setdefault(
                    sample.speaker_id, {"name": sample.speaker_name, "scores": []}
                )
                group["scores"].append(score)
            results = []
            for speaker_id, group in groups.items():
                scores = group["scores"]
                best = max(scores)
                hits = sum(1 for s in scores if s >= threshold)
                results.append((speaker_id, group["name"], best, hits, len(scores)))
            results.sort(key=lambda item: item[2], reverse=True)
            return results, len(stored), len(groups)

        self._worker = run_async(job, self._on_done, self._on_error)

    def _on_done(self, payload) -> None:
        results, scanned_samples, scanned_speakers = payload
        self._raw_results = results
        self._scan_info = (scanned_samples, scanned_speakers)
        self.search_btn.setEnabled(True)
        self.search_btn.setText("开始检索")
        self.status_label.setObjectName("hint")
        self.status_label.setText("检索完成。调整阈值可实时更新判定。")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self._render_results()

    def _on_error(self, message: str) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("开始检索")
        self.status_label.setObjectName("errorText")
        self.status_label.setText(message)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        QMessageBox.warning(self, "检索失败", message)

    def shutdown(self) -> None:
        self.audio_card.shutdown()