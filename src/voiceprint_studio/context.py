"""Shared application context (model engine + voiceprint library)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .engine import SpeakerEngine
from .store import VoiceprintStore


class AppContext(QObject):
    libraryChanged = Signal()
    engineReady = Signal()
    engineFailed = Signal(str)

    def __init__(self, store: VoiceprintStore | None = None, engine: SpeakerEngine | None = None):
        super().__init__()
        self.store = store or VoiceprintStore()
        self.engine = engine or SpeakerEngine()

    @property
    def engine_loaded(self) -> bool:
        return self.engine.is_loaded