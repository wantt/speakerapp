"""Voiceprint library management page."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...audio import AudioError, AudioPlayer, decode_audio, format_duration
from ...context import AppContext
from ...store import Sample
from ..widgets import Card, make_table, page_header
from ..worker import run_async


class LibraryPage(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setObjectName("pageBody")
        self.ctx = ctx
        self._current_speaker_id: int | None = None
        self._samples: list[Sample] = []
        self._player = AudioPlayer()
        self._worker = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        header_row = QHBoxLayout()
        header_row.addWidget(page_header(
            "声纹库",
            "查看、试听和管理已注册的说话人及其声纹样本。所有数据仅保存在本机。",
        ), 1)
        header_right = QVBoxLayout()
        header_right.setSpacing(6)
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("muted")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondary")
        refresh_btn.clicked.connect(self.refresh)
        header_right.addWidget(self.stats_label)
        header_right.addWidget(refresh_btn, 0, Qt.AlignmentFlag.AlignRight)
        header_row.addLayout(header_right)
        root.addLayout(header_row)

        speaker_card = Card("声纹档案")
        self.speaker_table = make_table(["姓名", "样本数", "备注", "创建时间"])
        self.speaker_table.setMinimumHeight(240)
        self.speaker_table.itemSelectionChanged.connect(self._on_speaker_selection)
        speaker_card.body.addWidget(self.speaker_table)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.rename_btn = QPushButton("重命名")
        self.rename_btn.setObjectName("secondary")
        self.rename_btn.clicked.connect(self.rename_speaker)
        self.delete_btn = QPushButton("删除档案")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self.delete_speaker)
        open_dir_btn = QPushButton("打开数据目录")
        open_dir_btn.setObjectName("ghost")
        open_dir_btn.clicked.connect(self.open_data_dir)
        self.speaker_status = QLabel("")
        self.speaker_status.setObjectName("hint")
        actions.addWidget(self.rename_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        actions.addWidget(self.speaker_status)
        actions.addWidget(open_dir_btn)
        speaker_card.body.addLayout(actions)
        root.addWidget(speaker_card)

        sample_card = Card("样本明细")
        self.sample_title = QLabel("未选择说话人")
        self.sample_title.setObjectName("hint")
        self.sample_table = make_table(["时长", "采集时间", "音频文件"])
        self.sample_table.setMinimumHeight(180)
        self.sample_table.doubleClicked.connect(lambda _index: self.play_sample())
        self.sample_table.itemSelectionChanged.connect(self._on_sample_selection)
        sample_card.body.addWidget(self.sample_title)
        sample_card.body.addWidget(self.sample_table)
        sample_actions = QHBoxLayout()
        sample_actions.setSpacing(8)
        self.play_btn = QPushButton("试听样本")
        self.play_btn.setObjectName("secondary")
        self.play_btn.clicked.connect(self.play_sample)
        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.setObjectName("secondary")
        self.stop_btn.clicked.connect(self._stop_playback)
        self.delete_sample_btn = QPushButton("删除样本")
        self.delete_sample_btn.setObjectName("danger")
        self.delete_sample_btn.clicked.connect(self.delete_sample)
        self.sample_status = QLabel("")
        self.sample_status.setObjectName("hint")
        sample_actions.addWidget(self.play_btn)
        sample_actions.addWidget(self.stop_btn)
        sample_actions.addWidget(self.delete_sample_btn)
        sample_actions.addStretch(1)
        sample_actions.addWidget(self.sample_status)
        sample_card.body.addLayout(sample_actions)
        root.addWidget(sample_card)
        root.addStretch(1)

        self.ctx.libraryChanged.connect(self.refresh)
        self.refresh()

    # -------------------------------------------------------------- refresh
    def refresh(self) -> None:
        speakers = self.ctx.store.list_speakers()
        selected_id = self._current_speaker_id
        self.speaker_table.blockSignals(True)
        self.speaker_table.setRowCount(0)
        target_row = -1
        for row, speaker in enumerate(speakers):
            self.speaker_table.insertRow(row)
            name_item = QTableWidgetItem(speaker.name)
            name_item.setData(Qt.ItemDataRole.UserRole, speaker.id)
            count_item = QTableWidgetItem(str(speaker.sample_count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            note_item = QTableWidgetItem(speaker.note or "—")
            created_item = QTableWidgetItem(speaker.created_at.replace("T", " ")[:16])
            self.speaker_table.setItem(row, 0, name_item)
            self.speaker_table.setItem(row, 1, count_item)
            self.speaker_table.setItem(row, 2, note_item)
            self.speaker_table.setItem(row, 3, created_item)
            if selected_id is not None and speaker.id == selected_id:
                target_row = row
        self.speaker_table.blockSignals(False)

        all_speakers, all_samples = self.ctx.store.stats()
        self.stats_label.setText(f"共 {all_speakers} 位说话人 · {all_samples} 条声纹样本")

        if not speakers:
            self._current_speaker_id = None
            self.sample_title.setText("声纹库为空，请先到「声纹注册」页面添加声纹。")
            self.sample_table.setRowCount(0)
            self._samples = []
            self._set_actions_enabled(False)
            return

        if target_row < 0:
            target_row = 0
        self.speaker_table.blockSignals(True)
        self.speaker_table.selectRow(target_row)
        self.speaker_table.blockSignals(False)
        item = self.speaker_table.item(target_row, 0)
        self._current_speaker_id = int(item.data(Qt.ItemDataRole.UserRole))
        self._load_samples(self._current_speaker_id)
        self._set_actions_enabled(True)

    def _on_speaker_selection(self) -> None:
        rows = self.speaker_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.speaker_table.item(rows[0].row(), 0)
        if item is None:
            return
        speaker_id = int(item.data(Qt.ItemDataRole.UserRole))
        if speaker_id == self._current_speaker_id:
            return
        self._current_speaker_id = speaker_id
        self._load_samples(speaker_id)

    def _load_samples(self, speaker_id: int) -> None:
        speaker = self.ctx.store.get_speaker(speaker_id)
        self._samples = self.ctx.store.list_samples(speaker_id)
        self.sample_title.setText(
            f"「{speaker.name}」· {len(self._samples)} 条样本" if speaker else "样本明细"
        )
        self.sample_table.setRowCount(0)
        for row, sample in enumerate(self._samples):
            self.sample_table.insertRow(row)
            duration_item = QTableWidgetItem(f"{sample.duration:.1f}s")
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            created_item = QTableWidgetItem(sample.created_at.replace("T", " ")[:19])
            source_item = QTableWidgetItem(sample.source_name or "—")
            source_item.setData(Qt.ItemDataRole.UserRole, sample.id)
            self.sample_table.setItem(row, 0, duration_item)
            self.sample_table.setItem(row, 1, created_item)
            self.sample_table.setItem(row, 2, source_item)
        self.sample_status.setText("")
        self._set_actions_enabled(True)

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.rename_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        has_sample = enabled and bool(self.sample_table.selectionModel().selectedRows())
        self.play_btn.setEnabled(has_sample)
        self.delete_sample_btn.setEnabled(has_sample)

    def _selected_sample(self) -> Sample | None:
        rows = self.sample_table.selectionModel().selectedRows()
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._samples):
            return self._samples[idx]
        return None

    def _on_sample_selection(self) -> None:
        has_sample = bool(self.sample_table.selectionModel().selectedRows())
        self.play_btn.setEnabled(has_sample)
        self.delete_sample_btn.setEnabled(has_sample)

    # -------------------------------------------------------------- actions
    def rename_speaker(self) -> None:
        if self._current_speaker_id is None:
            return
        speaker = self.ctx.store.get_speaker(self._current_speaker_id)
        if speaker is None:
            return
        new_name, ok = QInputDialog.getText(self, "重命名声纹档案", "新的姓名：", text=speaker.name)
        if not ok:
            return
        try:
            self.ctx.store.rename_speaker(speaker.id, new_name)
        except ValueError as exc:
            QMessageBox.warning(self, "重命名失败", str(exc))
            return
        self.speaker_status.setText(f"已重命名为「{new_name.strip()}」")
        self.ctx.libraryChanged.emit()

    def delete_speaker(self) -> None:
        if self._current_speaker_id is None:
            return
        speaker = self.ctx.store.get_speaker(self._current_speaker_id)
        if speaker is None:
            return
        answer = QMessageBox.question(
            self,
            "删除声纹档案",
            f"确定删除「{speaker.name}」及其 {speaker.sample_count} 条声纹样本吗？\n该操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.store.delete_speaker(speaker.id)
        self._current_speaker_id = None
        self.ctx.libraryChanged.emit()

    def delete_sample(self) -> None:
        sample = self._selected_sample()
        if sample is None:
            QMessageBox.information(self, "未选择样本", "请先在样本列表中选择一条样本。")
            return
        answer = QMessageBox.question(
            self,
            "删除声纹样本",
            f"确定删除这条 {sample.duration:.1f} 秒的样本吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.ctx.store.delete_sample(sample.id)
        self.ctx.libraryChanged.emit()

    def play_sample(self) -> None:
        sample = self._selected_sample()
        if sample is None:
            QMessageBox.information(self, "未选择样本", "请先在样本列表中选择一条样本。")
            return
        self.sample_status.setText("正在加载音频…")
        self._worker = run_async(
            lambda: decode_audio(sample.audio_path),
            self._on_clip_ready,
            self._on_audio_error,
        )

    def _on_clip_ready(self, clip) -> None:
        try:
            self._player.play(clip)
            self.sample_status.setText(f"正在播放 · {format_duration(clip.duration)}")
        except Exception as exc:  # pragma: no cover - device dependent
            QMessageBox.warning(self, "无法播放", f"音频设备不可用：\n{exc}")
            self.sample_status.setText("")

    def _on_audio_error(self, message: str) -> None:
        self.sample_status.setText("")
        QMessageBox.warning(self, "无法播放样本", message)

    def _stop_playback(self) -> None:
        try:
            self._player.stop()
        except Exception:
            pass
        self.sample_status.setText("已停止播放")

    def open_data_dir(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.store.home)))

    def shutdown(self) -> None:
        self._stop_playback()