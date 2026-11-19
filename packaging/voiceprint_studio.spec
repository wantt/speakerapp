# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Voiceprint Studio.

Build from the repository root (not from this directory):

    pyinstaller --noconfirm --clean packaging/voiceprint_studio.spec

Artifacts land in ``dist/``:
    macOS   -> dist/Voiceprint Studio.app
    Windows -> dist/VoiceprintStudio/VoiceprintStudio.exe
    Linux   -> dist/VoiceprintStudio/VoiceprintStudio
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

APP_VERSION = "1.0.0"

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
SRC = ROOT / "src"
RESOURCES = SRC / "voiceprint_studio" / "resources"
ENTRY = ROOT / "main.py"

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

# Model checkpoint + configuration + runtime icons.
datas = [
    (str(RESOURCES / "pretrained_eres2netv2.ckpt"), "voiceprint_studio/resources"),
    (str(RESOURCES / "configuration.json"), "voiceprint_studio/resources"),
    (str(RESOURCES / "icon.png"), "voiceprint_studio/resources"),
]

binaries = []
hiddenimports = [
    "sounddevice",
    "soundfile",
    "imageio_ffmpeg",
    "cffi",
    "torchaudio.compliance.kaldi",
    "torchaudio.functional",
    "torchaudio.transforms",
]

# Native audio libraries shipped as package data: PortAudio (sounddevice),
# libsndfile (soundfile) and a static ffmpeg build (imageio-ffmpeg).
def _foreign_native(src: str) -> bool:
    """True for a shared library belonging to a different platform."""
    name = Path(src).name.lower()
    if IS_MAC:
        return name.endswith((".dll", ".so"))
    if IS_WIN:
        return name.endswith((".dylib", ".so"))
    return name.endswith((".dll", ".dylib"))


for pkg in ("_sounddevice_data", "_soundfile_data", "imageio_ffmpeg"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    pkg_datas = [item for item in pkg_datas if not _foreign_native(item[0])]
    pkg_binaries = [item for item in pkg_binaries if not _foreign_native(item[0])]
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

datas += collect_data_files("sounddevice")
datas += collect_data_files("soundfile")

icon_file = RESOURCES / ("icon.icns" if IS_MAC else "icon.ico")
icon_arg = str(icon_file) if (IS_MAC or IS_WIN) and icon_file.exists() else None

excludes = [
    "tkinter",
    "matplotlib",
    "pandas",
    "pyarrow",
    "scipy",
    "IPython",
    "notebook",
    "jupyter",
    "modelscope",
    "transformers",
    "datasets",
    "accelerate",
    "PIL",
    # Qt modules that a desktop widget app never touches.
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtMultimedia",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtTest",
]

a = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceprintStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VoiceprintStudio",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="Voiceprint Studio.app",
        icon=icon_arg,
        bundle_identifier="com.voiceprintstudio.app",
        version=APP_VERSION,
        short_version=APP_VERSION,
        info_plist={
            "CFBundleDisplayName": "声纹工坊",
            "CFBundleName": "Voiceprint Studio",
            "CFBundleExecutable": "VoiceprintStudio",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "LSApplicationCategoryType": "public.app-category.utilities",
            "NSMicrophoneUsageDescription": "声纹工坊需要访问麦克风以录制声纹样本。",
            "NSHumanReadableCopyright": "Apache-2.0 · ERes2NetV2 by zuosi041116",
        },
    )