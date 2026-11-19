"""Headless self-test used to verify a frozen build.

Run with::

    VoiceprintStudio --self-test

It loads the bundled checkpoint, extracts an embedding from synthetic audio,
and exercises the audio decoders (soundfile + bundled ffmpeg).  It never
creates a Qt window, so it works on headless CI machines.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int = 16000) -> None:
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(pcm16.tobytes())


def run_self_test() -> int:
    from . import APP_NAME, __version__
    from .engine import EMBED_DIM, SpeakerEngine, resource_dir

    print(f"{APP_NAME} {__version__} self-test")
    print(f"python      : {sys.version.split()[0]}")
    print(f"executable  : {sys.executable}")
    print(f"frozen      : {bool(getattr(sys, 'frozen', False))}")
    res = resource_dir()
    print(f"resources   : {res}")
    ckpt = res / "pretrained_eres2netv2.ckpt"
    print(f"checkpoint  : {ckpt} ({ckpt.stat().st_size if ckpt.exists() else 'MISSING'})")
    if not ckpt.exists():
        print("FAIL: checkpoint missing")
        return 1

    sample_rate = 16000
    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    audio = (0.4 * np.sin(2 * np.pi * 180 * t) + 0.15 * np.sin(2 * np.pi * 420 * t)).astype(
        np.float32
    )

    try:
        engine = SpeakerEngine()
        engine.load()
        emb = engine.embed(audio, sample_rate)
    except Exception as exc:  # pragma: no cover - diagnostic path
        import traceback

        traceback.print_exc()
        print(f"FAIL: embedding extraction: {exc}")
        return 1
    print(f"embedding   : shape={emb.shape} norm={float(np.linalg.norm(emb)):.4f}")
    if emb.shape != (EMBED_DIM,) or not np.isfinite(emb).all():
        print("FAIL: unexpected embedding")
        return 1

    from .audio import decode_audio

    with tempfile.TemporaryDirectory(prefix="voiceprint-selftest-") as tmp:
        wav_path = Path(tmp) / "probe.wav"
        _write_wav(wav_path, audio)

        try:
            clip = decode_audio(wav_path)
        except Exception as exc:  # pragma: no cover - diagnostic path
            import traceback

            traceback.print_exc()
            print(f"FAIL: soundfile decoding: {exc}")
            return 1
        print(f"wav decode  : {clip.samples.shape[0]} samples @ {clip.sample_rate} Hz")
        if clip.samples.shape[0] < sample_rate:
            print("FAIL: decoded wav too short")
            return 1

        from .audio import prepare_playback

        playback = prepare_playback(clip.samples, clip.sample_rate, 48000)
        expected = round(clip.samples.shape[0] * 48000 / clip.sample_rate)
        print(f"playback mix: {playback.shape[0]} samples @ 48 kHz (expected {expected})")
        if abs(int(playback.shape[0]) - expected) > 48 or playback[0] != 0.0:
            print("FAIL: playback preprocessing")
            return 1

        from .audio import _ffmpeg_executable

        ffmpeg = _ffmpeg_executable()
        if ffmpeg:
            mp3_path = Path(tmp) / "probe.mp3"
            proc = subprocess.run(
                [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path),
                 "-codec:a", "libmp3lame", "-q:a", "4", str(mp3_path)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print(f"WARN: ffmpeg encode failed: {proc.stderr.strip()}")
            else:
                mp3_clip = decode_audio(mp3_path)
                print(
                    f"mp3 decode  : {mp3_clip.samples.shape[0]} samples @ "
                    f"{mp3_clip.sample_rate} Hz (ffmpeg={ffmpeg})"
                )
                if mp3_clip.samples.shape[0] == 0:
                    print("FAIL: decoded mp3 empty")
                    return 1
        else:
            print("WARN: ffmpeg not found; mp3 decoding unavailable")

    print("SELFTEST OK")
    return 0