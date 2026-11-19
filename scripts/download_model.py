#!/usr/bin/env python3
"""Download the ERes2NetV2 checkpoint used by Voiceprint Studio.

Usage:
    python scripts/download_model.py [--force]

The file is fetched from ModelScope and written to
``src/voiceprint_studio/resources/pretrained_eres2netv2.ckpt``.  Installers
bundle this file, so it only needs to be present before packaging.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST_DIR = ROOT / "src" / "voiceprint_studio" / "resources"
CKPT = DEST_DIR / "pretrained_eres2netv2.ckpt"
CONFIG = DEST_DIR / "configuration.json"

MODEL_ID = "zuosi041116/ERes2NetV2"
BASE_URL = f"https://www.modelscope.cn/api/v1/models/{MODEL_ID}/repo"
MIN_CKPT_BYTES = 50 * 1024 * 1024


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "voiceprint-studio/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 / total
                sys.stdout.write(f"\r  {dest.name}: {done / 1048576:6.1f} / {total / 1048576:6.1f} MB ({pct:5.1f}%)")
            else:
                sys.stdout.write(f"\r  {dest.name}: {done / 1048576:6.1f} MB")
            sys.stdout.flush()
    sys.stdout.write("\n")
    os.replace(tmp, dest)


def _from_modelscope() -> bool:
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        return False
    print(f"  using modelscope SDK for {MODEL_ID}")
    local_dir = Path(snapshot_download(MODEL_ID))
    src = local_dir / "pretrained_eres2netv2.ckpt"
    if not src.exists():
        return False
    shutil.copy2(src, CKPT)
    cfg = local_dir / "configuration.json"
    if cfg.exists():
        shutil.copy2(cfg, CONFIG)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    if CKPT.exists() and CKPT.stat().st_size >= MIN_CKPT_BYTES and not args.force:
        print(f"checkpoint already present: {CKPT} ({CKPT.stat().st_size} bytes)")
        return 0

    print(f"fetching {MODEL_ID}")
    try:
        ok = _from_modelscope()
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"  modelscope SDK failed: {exc}")
        ok = False

    if not ok:
        url = f"{BASE_URL}?Revision=master&FilePath=pretrained_eres2netv2.ckpt"
        print(f"  {url}")
        _download(url, CKPT)

    if CKPT.stat().st_size < MIN_CKPT_BYTES:
        print(f"error: {CKPT} looks truncated ({CKPT.stat().st_size} bytes)", file=sys.stderr)
        return 1
    print(f"checkpoint ready: {CKPT} ({CKPT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())