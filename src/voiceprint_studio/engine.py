"""Neural speaker embedding engine built on the ERes2NetV2 checkpoint.

The model definition is vendored in :mod:`voiceprint_studio.models.eres2netv2`.
Feature extraction mirrors ModelScope's pipeline: 80-bin Kaldi fbank,
per-utterance mean normalisation, 16 kHz sampling rate.
"""

from __future__ import annotations

import threading
from pathlib import Path

import numpy as np
import torch
import torchaudio
import torchaudio.compliance.kaldi as kaldi

from .models.eres2netv2 import ERes2NetV2

SAMPLE_RATE = 16000
EMBED_DIM = 192
DEFAULT_THRESHOLD = 0.365
MAX_EMBED_SECONDS = 30.0


def resource_dir() -> Path:
    """Return the directory that holds bundled model resources."""
    import sys

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "voiceprint_studio" / "resources"
    return Path(__file__).resolve().parent / "resources"


def resample(audio: np.ndarray, orig_sr: int, target_sr: int = SAMPLE_RATE) -> np.ndarray:
    """Resample mono float32 audio."""
    if orig_sr == target_sr:
        return audio.astype(np.float32, copy=False)
    tensor = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)).unsqueeze(0)
    out = torchaudio.functional.resample(tensor, orig_sr, target_sr)
    return out.squeeze(0).numpy().astype(np.float32, copy=False)


def cosine_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
    a = np.asarray(emb_a, dtype=np.float64).ravel()
    b = np.asarray(emb_b, dtype=np.float64).ravel()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


def normalize_embedding(emb: np.ndarray) -> np.ndarray:
    emb = np.asarray(emb, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(emb))
    return emb / norm if norm > 1e-12 else emb


class SpeakerEngine:
    """Loads the checkpoint once and extracts speaker embeddings."""

    def __init__(self, model_path: Path | None = None, allow_download: bool = False):
        self.model_path = Path(model_path) if model_path else resource_dir() / "pretrained_eres2netv2.ckpt"
        self.allow_download = allow_download
        self.device = torch.device("cpu")
        self.model: ERes2NetV2 | None = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        model_path = self.model_path
        if not model_path.exists():
            if self.allow_download:
                model_path = self._download_model()
                self.model_path = model_path
            else:
                raise FileNotFoundError(
                    f"未找到模型权重文件：{model_path}\n"
                    "请先运行 scripts/download_model.py 下载模型，或安装完整安装包。"
                )

        model = ERes2NetV2(
            embed_dim=EMBED_DIM,
            baseWidth=26,
            scale=2,
            expansion=2,
        )
        state = torch.load(str(model_path), map_location="cpu", weights_only=True)
        model.load_state_dict(state, strict=True)
        model.eval()
        model.to(self.device)
        self.model = model

    def _download_model(self) -> Path:
        """Fetch the checkpoint from ModelScope (development convenience)."""
        try:
            from modelscope.hub.snapshot_download import snapshot_download
        except ImportError as exc:  # pragma: no cover - optional path
            raise RuntimeError("未安装 modelscope，无法自动下载模型。") from exc
        local_dir = snapshot_download("zuosi041116/ERes2NetV2")
        src = Path(local_dir) / "pretrained_eres2netv2.ckpt"
        dest = resource_dir() / "pretrained_eres2netv2.ckpt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(src, dest)
        return dest

    def embed(self, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
        """Extract a 192-D embedding from mono audio."""
        if self.model is None:
            raise RuntimeError("声纹模型尚未加载。")

        audio = np.asarray(audio, dtype=np.float32).ravel()
        if audio.size == 0:
            raise ValueError("音频为空。")
        if sample_rate != SAMPLE_RATE:
            audio = resample(audio, sample_rate, SAMPLE_RATE)

        max_samples = int(MAX_EMBED_SECONDS * SAMPLE_RATE)
        if audio.size > max_samples:
            start = (audio.size - max_samples) // 2
            audio = audio[start:start + max_samples]

        waveform = torch.from_numpy(np.ascontiguousarray(audio)).unsqueeze(0)

        with self._lock, torch.inference_mode():
            feature = kaldi.fbank(
                waveform,
                num_mel_bins=80,
                sample_frequency=SAMPLE_RATE,
                dither=0.0,
            )
            feature = feature - feature.mean(dim=0, keepdim=True)
            feature = feature.unsqueeze(0)
            embedding = self.model(feature.to(self.device))

        return embedding.detach().cpu().numpy().astype(np.float32).ravel()