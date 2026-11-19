"""Voiceprint enrolment page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...context import AppContext
from ..widgets import AudioInputCard, Card, StatTile, page_header
from ..worker import run_async


class RegisterPage(QWidget):
    navigateRequested = Signal(str)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setObjectName("pageBody")
        self.ctx = ctx
        self._worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(page_header(
            "声纹注册",
            "录入一段清晰的语音，让 ERes2NetV2 为说话人提取 192 维声纹特征并保存到本地声纹库。",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setSpacing(16)

        self.audio_card = AudioInputCard(
            "1 · 添加语音样本",
            "拖入音频文件，或使用麦克风录制。建议 3~30 秒、环境安静、同一人连续说话。",
        )
        self.audio_card.audioChanged.connect(self._reset_status)
        left.addWidget(self.audio_card)

        form_card = Card("2 · 填写档案信息")
        name_label = QLabel("姓名")
        name_label.setObjectName("fieldLabel")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：张三（同名会追加为新的声纹样本）")
        self.name_edit.setMaxLength(60)
        note_label = QLabel("备注（可选）")
        note_label.setObjectName("fieldLabel")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("例如：产品部 / 客户 A / 家庭成员")

        form_card.body.addWidget(name_label)
        form_card.body.addWidget(self.name_edit)
        form_card.body.addWidget(note_label)
        form_card.body.addWidget(self.note_edit)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self.register_btn = QPushButton("注册声纹")
        self.register_btn.setObjectName("primary")
        self.register_btn.setMinimumWidth(150)
        self.register_btn.clicked.connect(self.register)
        self.status_label = QLabel("注册后将提取声纹特征并保存到本地。")
        self.status_label.setObjectName("hint")
        self.status_label.setWordWrap(True)
        action_row.addWidget(self.register_btn)
        action_row.addWidget(self.status_label, 1)
        form_card.body.addLayout(action_row)
        left.addWidget(form_card)
        left.addStretch(1)

        overview_card = Card("声纹库概览")
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.speaker_stat = StatTile("注册人数")
        self.sample_stat = StatTile("声纹样本")
        stats_row.addWidget(self.speaker_stat)
        stats_row.addWidget(self.sample_stat)
        overview_card.body.addLayout(stats_row)
        recent_label = QLabel("最近注册")
        recent_label.setObjectName("fieldLabel")
        overview_card.body.addWidget(recent_label)
        self.recent_layout = QVBoxLayout()
        self.recent_layout.setSpacing(6)
        overview_card.body.addLayout(self.recent_layout)
        manage_btn = QPushButton("管理声纹库 →")
        manage_btn.setObjectName("ghost")
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.clicked.connect(lambda: self.navigateRequested.emit("library"))
        overview_card.body.addWidget(manage_btn, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(overview_card)

        tips_card = Card("采集小贴士")
        for text in (
            "• 一次只让一个人说话，避免多人对话。",
            "• 避免背景音乐、风噪和强混响。",
            "• 普通话或方言均可，模型为中文声纹模型。",
            "• 同一个人可注册多条样本，提升检索稳定性。",
        ):
            tip = QLabel(text)
            tip.setObjectName("hint")
            tip.setWordWrap(True)
            tips_card.body.addWidget(tip)
        right.addWidget(tips_card)
        right.addStretch(1)

        columns.addLayout(left, 3)
        columns.addLayout(right, 2)
        root.addLayout(columns, 1)

        self.ctx.libraryChanged.connect(self.refresh_library)
        self.refresh_library()

    # ------------------------------------------------------------------ ui
    def _reset_status(self) -> None:
        self.status_label.setObjectName("hint")
        self.status_label.setText("注册后将提取声纹特征并保存到本地。")
        self._repolish(self.status_label)

    @staticmethod
    def _repolish(widget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_status(self, text: str, error: bool = False, success: bool = False) -> None:
        self.status_label.setObjectName("errorText" if error else "successText" if success else "hint")
        self.status_label.setText(text)
        self._repolish(self.status_label)

    def refresh_library(self) -> None:
        speakers, samples = self.ctx.store.stats()
        self.speaker_stat.set_value(speakers)
        self.sample_stat.set_value(samples)
        self._clear_layout(self.recent_layout)
        recent = self.ctx.store.list_speakers()[:5]
        if not recent:
            empty = QLabel("暂无注册声纹")
            empty.setObjectName("muted")
            self.recent_layout.addWidget(empty)
            return
        for speaker in recent:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(speaker.name)
            name.setStyleSheet("font-weight: 600;")
            count = QLabel(f"{speaker.sample_count} 个样本")
            count.setObjectName("muted")
            row.addWidget(name)
            row.addStretch(1)
            row.addWidget(count)
            self.recent_layout.addLayout(row)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child is not None:
                RegisterPage._clear_layout(child)

    # -------------------------------------------------------------- action
    def register(self) -> None:
        clip = self.audio_card.clip
        name = self.name_edit.text().strip()
        note = self.note_edit.text().strip()
        if clip is None:
            QMessageBox.information(self, "缺少音频", "请先选择或录制一段语音。")
            return
        if not name:
            QMessageBox.information(self, "缺少姓名", "请填写说话人姓名。")
            self.name_edit.setFocus()
            return
        if not self.ctx.engine_loaded:
            QMessageBox.information(self, "模型加载中", "声纹模型正在加载，请稍候几秒再试。")
            return

        self.register_btn.setEnabled(False)
        self.register_btn.setText("正在注册…")
        self._set_status("正在提取声纹特征…")

        def job():
            embedding = self.ctx.engine.embed(clip.samples, clip.sample_rate)
            speaker_id = self.ctx.store.add_sample(name, clip, embedding, note)
            speaker = self.ctx.store.get_speaker(speaker_id)
            return speaker.name if speaker else name

        self._worker = run_async(job, self._on_registered, self._on_error)

    def _on_registered(self, name: str) -> None:
        self.register_btn.setEnabled(True)
        self.register_btn.setText("注册声纹")
        self._set_status(f"已成功注册「{name}」的声纹样本。", success=True)
        self.name_edit.clear()
        self.note_edit.clear()
        self.audio_card.clear()
        self.ctx.libraryChanged.emit()

    def _on_error(self, message: str) -> None:
        self.register_btn.setEnabled(True)
        self.register_btn.setText("注册声纹")
        self._set_status(message, error=True)
        QMessageBox.warning(self, "注册失败", message)