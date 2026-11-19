#!/usr/bin/env python3
"""Generate application icons (PNG / ICNS / ICO) from a single drawing.

Usage:
    python scripts/make_icons.py

Writes into src/voiceprint_studio/resources/:
    icon.png   - 1024x1024 master image (also used at runtime by the GUI)
    icon.icns  - macOS bundle icon (built on macOS with ``iconutil``)
    icon.ico   - Windows installer/executable icon
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "src" / "voiceprint_studio" / "resources"

SIZE = 1024
SS = 4  # supersampling factor for smooth edges

# Palette matching ui/theme.py
INDIGO = (79, 70, 229)
CYAN = (34, 211, 238)
WHITE = (255, 255, 255)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _gradient(size: int) -> Image.Image:
    """Diagonal indigo -> cyan gradient."""
    small = Image.new("RGB", (size, size))
    px = small.load()
    for y in range(size):
        for x in range(size):
            t = min(1.0, (x + y) / (2 * size - 2))
            px[x, y] = _lerp(INDIGO, CYAN, t * 0.85)
    return small


def draw_icon() -> Image.Image:
    big = SIZE * SS
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    bg = _gradient(big)
    bg.putalpha(_rounded_mask(big, radius=int(big * 0.225)))
    canvas.alpha_composite(bg)

    draw = ImageDraw.Draw(canvas)

    # White waveform bars centred on the icon.
    heights = [0.20, 0.34, 0.52, 0.74, 0.44, 0.66, 0.30, 0.46, 0.22]
    bar_w = big * 0.045
    gap = big * 0.038
    total = len(heights) * bar_w + (len(heights) - 1) * gap
    x = (big - total) / 2
    cy = big / 2
    for h in heights:
        half = big * h / 2
        draw.rounded_rectangle(
            (x, cy - half, x + bar_w, cy + half),
            radius=bar_w / 2,
            fill=WHITE,
        )
        x += bar_w + gap

    # Subtle inner highlight along the top edge.
    draw.rounded_rectangle(
        (big * 0.06, big * 0.055, big * 0.94, big * 0.42),
        radius=int(big * 0.16),
        outline=(255, 255, 255, 40),
        width=int(big * 0.012),
    )

    return canvas.resize((SIZE, SIZE), Image.LANCZOS)


def write_png(img: Image.Image, path: Path) -> None:
    img.save(path, "PNG")
    print(f"wrote {path.relative_to(ROOT)}")


def write_ico(img: Image.Image, path: Path) -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(path, "ICO", sizes=sizes)
    print(f"wrote {path.relative_to(ROOT)}")


def write_icns(img: Image.Image, path: Path) -> None:
    if sys.platform != "darwin" or shutil.which("iconutil") is None:
        print("skipping icon.icns (iconutil only available on macOS)")
        return
    iconset = RES / "icon.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    specs = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in specs:
        img.resize((size, size), Image.LANCZOS).save(iconset / name)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(path)],
        check=True,
    )
    shutil.rmtree(iconset)
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> int:
    RES.mkdir(parents=True, exist_ok=True)
    img = draw_icon()
    write_png(img, RES / "icon.png")
    write_ico(img, RES / "icon.ico")
    write_icns(img, RES / "icon.icns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())