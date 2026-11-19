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


PLAYBACK_FADE_SECONDS = 0.008
PLAYBACK_BLOCKSIZE = 1024

_sd_module = None


def _sounddevice():
    """Import sounddevice lazily and cache it (PortAudio may be absent)."""
    global _sd_module
    if _sd_module is None:
        import sounddevice as sd

        _sd_module = sd
    return _sd_module


def prepare_playback(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample to the output device rate and fade the edges.

    Resampling to the device's native rate avoids low-quality sample-rate
    conversion inside the OS audio engine, and the short fades remove the
    clicks caused by starting/ending a waveform at a non-zero amplitude.
    """
    data = np.asarray(samples, dtype=np.float32).ravel()
    if data.size == 0:
        return data
    if dst_rate and src_rate != dst_rate:
        from .engine import resample

        data = resample(data, src_rate, dst_rate)
    data = np.ascontiguousarray(data, dtype=np.float32)
    fade = min(int((dst_rate or SAMPLE_RATE) * PLAYBACK_FADE_SECONDS), data.size // 2)
    if fade > 0:
        data = data.copy()
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        data[:fade] *= ramp
        data[-fade:] *= ramp[::-1]
    return data


class AudioPlayer:
    """Click-free, non-blocking playback through PortAudio.

    A dedicated output stream is fed from a pre-faded buffer, so playback can
    be stopped smoothly (the callback ramps the gain down before finishing)
    instead of cutting the signal, which produced audible pops.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream = None
        self._sd = None
        self._data = np.zeros(0, np.float32)
        self._pos = 0
        self._killing = False
        self._finished = threading.Event()
        self._sample_rate = SAMPLE_RATE

    @staticmethod
    def _output_sample_rate() -> int:
        try:
            info = _sounddevice().query_devices(kind="output")
            rate = int(round(float(info.get("default_samplerate") or SAMPLE_RATE)))
            return max(8000, rate)
        except Exception:
            return SAMPLE_RATE

    def play(self, clip: AudioClip) -> None:
        sd = _sounddevice()
        self.stop()
        rate = self._output_sample_rate()
        data = prepare_playback(clip.samples, clip.sample_rate, rate)
        if data.size == 0:
            return
        with self._lock:
            self._data = data
            self._pos = 0
            self._killing = False
            self._sample_rate = rate
            self._sd = sd
            self._finished.clear()

        stream = sd.OutputStream(
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=PLAYBACK_BLOCKSIZE,
            latency="high",
            callback=self._callback,
            finished_callback=self._on_finished,
        )
        self._stream = stream
        try:
            stream.start()
        except Exception:
            self._stream = None
            try:
                stream.close()
            except Exception:
                pass
            raise

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ANN001
        with self._lock:
            data = self._data
            pos = self._pos
            killing = self._killing
        outdata.fill(0)
        if pos >= data.size:
            raise self._sd.CallbackStop
        n = min(frames, data.size - pos)
        if killing:
            # Smooth fade-out instead of an abrupt cut.
            ramp = np.linspace(1.0, 0.0, n, endpoint=False, dtype=np.float32)
            outdata[:n, 0] = data[pos : pos + n] * ramp
        else:
            outdata[:n, 0] = data[pos : pos + n]
        with self._lock:
            self._pos = pos + n
        if killing or pos + n >= data.size:
            raise self._sd.CallbackStop

    def _on_finished(self) -> None:
        self._finished.set()

    def stop(self) -> None:
        stream = self._stream
        if stream is None:
            return
        with self._lock:
            self._killing = True
        try:
            if stream.active:
                # Give the callback time to play its fade-out block.
                self._finished.wait(0.08)
            stream.stop()
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass
            self._stream = None

    def is_active(self) -> bool:
        stream = self._stream
        if stream is None:
            return False
        try:
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