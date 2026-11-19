"""SQLite-backed voiceprint library."""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from .audio import AudioClip, save_wav

APP_DIR_NAME = "VoiceprintStudio"


def app_data_dir() -> Path:
    override = os.environ.get("VOICEPRINT_STUDIO_HOME")
    if override:
        base = Path(override).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home()) / APP_DIR_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        base = Path(xdg) / "voiceprint-studio"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Speaker:
    id: int
    name: str
    note: str
    created_at: str
    sample_count: int = 0


@dataclass
class Sample:
    id: int
    speaker_id: int
    speaker_name: str
    audio_path: str
    source_name: str
    duration: float
    embedding: np.ndarray
    created_at: str


class VoiceprintStore:
    def __init__(self, home: Path | None = None):
        self.home = Path(home) if home else app_data_dir()
        self.audio_dir = self.home / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "voiceprints.db"
        self._lock = threading.RLock()
        self._init_db()

    # ------------------------------------------------------------------ db
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS speakers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    speaker_id INTEGER NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
                    audio_path TEXT NOT NULL,
                    source_name TEXT NOT NULL DEFAULT '',
                    duration REAL NOT NULL DEFAULT 0,
                    embedding BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_samples_speaker ON samples(speaker_id);
                """
            )
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(samples)").fetchall()
            }
            if "source_name" not in columns:
                conn.execute(
                    "ALTER TABLE samples ADD COLUMN source_name TEXT NOT NULL DEFAULT ''"
                )

    # ------------------------------------------------------------- queries
    def list_speakers(self) -> list[Speaker]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.id, s.name, s.note, s.created_at, COUNT(x.id) AS sample_count
                FROM speakers s LEFT JOIN samples x ON x.speaker_id = s.id
                GROUP BY s.id ORDER BY s.id DESC
                """
            ).fetchall()
        return [Speaker(r["id"], r["name"], r["note"], r["created_at"], r["sample_count"]) for r in rows]

    def get_speaker(self, speaker_id: int) -> Speaker | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM speakers WHERE id = ?", (speaker_id,)
            ).fetchone()
            if not row:
                return None
            count = conn.execute(
                "SELECT COUNT(*) FROM samples WHERE speaker_id = ?", (speaker_id,)
            ).fetchone()[0]
        return Speaker(row["id"], row["name"], row["note"], row["created_at"], count)

    def find_speaker_by_name(self, name: str) -> Speaker | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM speakers WHERE name = ? ORDER BY id LIMIT 1", (name.strip(),)
            ).fetchone()
        if not row:
            return None
        return self.get_speaker(row["id"])

    def list_samples(self, speaker_id: int | None = None) -> list[Sample]:
        query = """
            SELECT x.id, x.speaker_id, s.name AS speaker_name, x.audio_path,
                   x.source_name, x.duration, x.embedding, x.created_at
            FROM samples x JOIN speakers s ON s.id = x.speaker_id
        """
        args: tuple = ()
        if speaker_id is not None:
            query += " WHERE x.speaker_id = ?"
            args = (speaker_id,)
        query += " ORDER BY x.id DESC"
        with self._lock, self._connect() as conn:
            rows = conn.execute(query, args).fetchall()
        return [
            Sample(
                r["id"], r["speaker_id"], r["speaker_name"], r["audio_path"],
                r["source_name"], float(r["duration"]),
                np.frombuffer(r["embedding"], dtype=np.float32).copy(),
                r["created_at"],
            )
            for r in rows
        ]

    def stats(self) -> tuple[int, int]:
        with self._lock, self._connect() as conn:
            speakers = conn.execute("SELECT COUNT(*) FROM speakers").fetchone()[0]
            samples = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        return int(speakers), int(samples)

    # -------------------------------------------------------------- writes
    def add_sample(
        self,
        name: str,
        clip: AudioClip,
        embedding: np.ndarray,
        note: str = "",
        speaker_id: int | None = None,
    ) -> int:
        """Enrol one utterance. Returns the speaker id (existing or new)."""
        name = (name or "").strip()
        if not name:
            raise ValueError("请输入姓名。")
        if clip.duration < 0.4:
            raise ValueError("音频过短，请录制或选择至少 0.5 秒的语音。")

        with self._lock:
            if speaker_id is None:
                existing = self.find_speaker_by_name(name)
                if existing is not None:
                    speaker_id = existing.id
                else:
                    speaker_id = self.create_speaker(name, note)
            else:
                speaker = self.get_speaker(speaker_id)
                if speaker is None:
                    raise ValueError("声纹档案不存在。")

            audio_path = self._persist_audio(clip)
            source_name = Path(clip.path).name if clip.path else "麦克风录音"
            now = datetime.now().isoformat(timespec="seconds")
            blob = np.asarray(embedding, dtype=np.float32).tobytes()
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO samples(speaker_id, audio_path, source_name, duration, embedding, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (speaker_id, str(audio_path), source_name, clip.duration, blob, now),
                )
        return int(speaker_id)

    def create_speaker(self, name: str, note: str = "") -> int:
        name = (name or "").strip()
        if not name:
            raise ValueError("请输入姓名。")
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO speakers(name, note, created_at) VALUES (?, ?, ?)",
                (name, note.strip(), now),
            )
            return int(cur.lastrowid)

    def rename_speaker(self, speaker_id: int, new_name: str) -> None:
        new_name = (new_name or "").strip()
        if not new_name:
            raise ValueError("姓名不能为空。")
        with self._lock, self._connect() as conn:
            clash = conn.execute(
                "SELECT id FROM speakers WHERE name = ? AND id != ?", (new_name, speaker_id)
            ).fetchone()
            if clash:
                raise ValueError("已存在同名声纹档案。")
            conn.execute("UPDATE speakers SET name = ? WHERE id = ?", (new_name, speaker_id))

    def delete_speaker(self, speaker_id: int) -> None:
        with self._lock, self._connect() as conn:
            paths = [
                r["audio_path"]
                for r in conn.execute(
                    "SELECT audio_path FROM samples WHERE speaker_id = ?", (speaker_id,)
                ).fetchall()
            ]
            conn.execute("DELETE FROM speakers WHERE id = ?", (speaker_id,))
        for p in paths:
            _unlink_quietly(Path(p))

    def delete_sample(self, sample_id: int) -> None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT audio_path, speaker_id FROM samples WHERE id = ?", (sample_id,)
            ).fetchone()
            if not row:
                return
            conn.execute("DELETE FROM samples WHERE id = ?", (sample_id,))
            remaining = conn.execute(
                "SELECT COUNT(*) FROM samples WHERE speaker_id = ?", (row["speaker_id"],)
            ).fetchone()[0]
            if remaining == 0:
                conn.execute("DELETE FROM speakers WHERE id = ?", (row["speaker_id"],))
        _unlink_quietly(Path(row["audio_path"]))

    # ------------------------------------------------------------- private
    def _persist_audio(self, clip: AudioClip) -> Path:
        if clip.path:
            src = Path(clip.path)
            # Already inside our library: keep the existing file.
            try:
                src.resolve().relative_to(self.audio_dir.resolve())
                return src
            except Exception:
                pass
            if src.exists() and src.is_file():
                suffix = src.suffix.lower() or ".wav"
                dest = self.audio_dir / f"{uuid.uuid4().hex}{suffix}"
                try:
                    import shutil

                    shutil.copy2(src, dest)
                    return dest
                except OSError:
                    pass
        dest = self.audio_dir / f"{uuid.uuid4().hex}.wav"
        save_wav(dest, clip)
        return dest


def _unlink_quietly(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass