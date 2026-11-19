"""Audio decoding, playback, recording and waveform helpers."""

from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .engine import SAMPLE_RATE

# Extensions we advertise in the file dialog. Anything else is still attempted
# through FFmpeg when available.
AUDIO_FILTER = (
    "音频文件 (*.wav *.flac *.ogg *.mp3 *.m4a *.aac *.opus *.wma *.aiff *.aif *.webm);;"
    "所有文件 (*)"
)


class AudioError(RuntimeError):
    pass


@dataclass
class AudioClip:
    samples: np.ndarray  # mono float32
    sample_rate: int
    path: str | None = None

    @property
    def duration(self) -> float:
        return float(self.samples.size) / float(self.sample_rate) if self.sample_rate else 0.0

    @property
    def channels(self) -> int:
        return 1


def _ffmpeg_executable() -> str | None:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _read_with_ffmpeg(path: Path) -> AudioClip:
    exe = _ffmpeg_executable()
    if not exe:
        raise AudioError(
            "无法解码该音频文件。请使用 WAV/FLAC/OGG 格式，或安装 FFmpeg。"
        )
    proc = subprocess.run(
        [
            exe, "-v", "error", "-i", str(path), "-vn",
            "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1",
            "-ar", str(SAMPLE_RATE), "pipe:1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode("utf-8", errors="ignore").strip().splitlines()
        message = detail[-1] if detail else "未知错误"
        raise AudioError(f"无法解码音频：{message}")
    samples = np.frombuffer(proc.stdout, dtype="<f4").astype(np.float32, copy=True)
    return AudioClip(samples=samples, sample_rate=SAMPLE_RATE, path=str(path))


def decode_audio(path: str | Path) -> AudioClip:
    """Decode an audio file to mono float32 samples.

    Tries libsndfile first (fast, bundled), then FFmpeg for formats such as
    MP3/M4A/WMA that libsndfile may not support on every platform.
    """
    p = Path(path)
    if not p.exists():
        raise AudioError(f"文件不存在：{p}")
    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=True)
        if data.size == 0:
            raise AudioError("音频文件为空。")
        data = data.mean(axis=1, dtype=np.float32)
        return AudioClip(samples=data.astype(np.float32, copy=False), sample_rate=int(sr), path=str(p))
    except AudioError:
        raise
    except Exception:
        return _read_with_ffmpeg(p)


def save_wav(path: str | Path, clip: AudioClip) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), clip.samples, clip.sample_rate, subtype="PCM_16")


def waveform_peaks(samples: np.ndarray, points: int = 1000) -> tuple[np.ndarray, np.ndarray]:
    """Downsample a waveform to (min, max) pairs per horizontal point."""
    samples = np.asarray(samples, dtype=np.float32).ravel()
    points = max(1, int(points))
    if samples.size == 0:
        return np.zeros(points, np.float32), np.zeros(points, np.float32)
    if samples.size <= points:
        pad = points - samples.size
        data = np.pad(samples, (0, pad))
        return data.copy(), data.copy()
    usable = (samples.size // points) * points
    reshaped = samples[:usable].reshape(points, -1)
    return reshaped.min(axis=1), reshaped.max(axis=1)


def format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    if minutes:
        return f"{minutes}:{rest:04.1f}"
    return f"{rest:.1f}s"


class AudioPlayer:
    """Non-blocking playback through PortAudio (sounddevice)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def play(self, clip: AudioClip) -> None:
        import sounddevice as sd

        with self._lock:
            sd.stop()
            sd.play(np.ascontiguousarray(clip.samples, dtype=np.float32), clip.sample_rate)

    def stop(self) -> None:
        import sounddevice as sd

        sd.stop()

    @staticmethod
    def is_active() -> bool:
        try:
            import sounddevice as sd

            stream = sd.get_stream()
            return bool(stream.active)
        except Exception:
            return False


class Recorder:
    """Microphone recorder that captures at the device rate and resamples to 16 kHz."""

    def __init__(self) -> None:
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.sample_rate: int | None = None
        self.level: float = 0.0
        self._error: str | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        with self._lock:
            self._chunks = []
        self.level = 0.0
        self._error = None
        try:
            device = sd.query_devices(kind="input")
            rate = int(device.get("default_samplerate") or SAMPLE_RATE)
            stream = sd.InputStream(
                samplerate=rate,
                channels=1,
                dtype="float32",
                callback=self._callback,
            )
            stream.start()
            self._stream = stream
            self.sample_rate = rate
        except Exception as exc:  # pragma: no cover - hardware dependent
            self._stream = None
            raise AudioError(
                "无法打开麦克风。请检查系统麦克风权限和设备。\n" + str(exc)
            ) from exc

    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        chunk = np.asarray(indata[:, 0], dtype=np.float32).copy()
        with self._lock:
            self._chunks.append(chunk)
            rms = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
        self.level = max(float(self.level) * 0.85, rms)

    def snapshot(self, seconds: float = 3.0) -> tuple[np.ndarray, int]:
        """Return the most recent samples for live plotting."""
        with self._lock:
            data = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
        rate = self.sample_rate or SAMPLE_RATE
        tail = int(rate * seconds)
        return data[-tail:], rate

    def stop(self) -> AudioClip:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            samples = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self._chunks = []
        rate = self.sample_rate or SAMPLE_RATE
        if samples.size == 0:
            raise AudioError("没有录到声音。")
        from .engine import resample

        samples = resample(samples, rate, SAMPLE_RATE)
        return AudioClip(samples=samples, sample_rate=SAMPLE_RATE)


def total_duration_label(clip: AudioClip | None) -> str:
    if clip is None:
        return "未选择"
    return format_duration(clip.duration)