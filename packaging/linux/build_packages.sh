#!/usr/bin/env bash
# Build Linux packages for Voiceprint Studio: .deb (always) and AppImage
# (when appimagetool can be obtained).
#
# Usage:
#   packaging/linux/build_packages.sh [--no-build] [--no-appimage]
#
# Environment:
#   PYTHON   python interpreter with project deps (default: .venv/bin/python)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERSION="1.0.0"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || command -v python)"
  fi
fi
DIST="$ROOT/dist"
ONEDIR="$DIST/VoiceprintStudio"
ICON="$ROOT/src/voiceprint_studio/resources/icon.png"

BUILD=1
APPIMAGE=1
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    --no-appimage) APPIMAGE=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) DEB_ARCH="amd64"; APPIMAGE_ARCH="x86_64" ;;
  aarch64|arm64) DEB_ARCH="arm64"; APPIMAGE_ARCH="aarch64" ;;
  *) DEB_ARCH="$ARCH"; APPIMAGE_ARCH="$ARCH" ;;
esac

if [[ ! -f "$ICON" ]]; then
  echo "==> generating icons"
  "$PYTHON" scripts/make_icons.py
fi
if [[ ! -f "$ROOT/src/voiceprint_studio/resources/pretrained_eres2netv2.ckpt" ]]; then
  echo "==> downloading model checkpoint"
  "$PYTHON" scripts/download_model.py
fi

if [[ "$BUILD" == "1" ]]; then
  echo "==> building PyInstaller bundle"
  "$PYTHON" -m PyInstaller --noconfirm --clean packaging/voiceprint_studio.spec
fi

if [[ ! -x "$ONEDIR/VoiceprintStudio" ]]; then
  echo "error: $ONEDIR/VoiceprintStudio not found; run without --no-build" >&2
  exit 1
fi

echo "==> verifying frozen self-test"
"$ONEDIR/VoiceprintStudio" --self-test

# ---------------------------------------------------------------- .deb ------
if command -v dpkg-deb >/dev/null 2>&1; then
  echo "==> building .deb ($DEB_ARCH)"
  STAGE="$(mktemp -d)"
  trap 'rm -rf "$STAGE"' EXIT
  PKGROOT="$STAGE/voiceprint-studio"
  mkdir -p \
    "$PKGROOT/DEBIAN" \
    "$PKGROOT/opt/VoiceprintStudio" \
    "$PKGROOT/usr/bin" \
    "$PKGROOT/usr/share/applications" \
    "$PKGROOT/usr/share/icons/hicolor/256x256/apps" \
    "$PKGROOT/usr/share/icons/hicolor/512x512/apps" \
    "$PKGROOT/usr/share/doc/voiceprint-studio"

  cp -R "$ONEDIR"/. "$PKGROOT/opt/VoiceprintStudio/"
  ln -s /opt/VoiceprintStudio/VoiceprintStudio "$PKGROOT/usr/bin/voiceprint-studio"
  cp packaging/linux/voiceprint-studio.desktop "$PKGROOT/usr/share/applications/"
  cp "$ICON" "$PKGROOT/usr/share/icons/hicolor/256x256/apps/voiceprint-studio.png"
  cp "$ICON" "$PKGROOT/usr/share/icons/hicolor/512x512/apps/voiceprint-studio.png"
  cp LICENSE.txt "$PKGROOT/usr/share/doc/voiceprint-studio/copyright"

  INSTALLED_KB="$(du -sk "$PKGROOT" | cut -f1)"
  cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: voiceprint-studio
Version: $VERSION
Section: sound
Priority: optional
Architecture: $DEB_ARCH
Installed-Size: $INSTALLED_KB
Maintainer: Voiceprint Studio <noreply@example.com>
Homepage: https://www.modelscope.cn/models/zuosi041116/ERes2NetV2
Depends: libportaudio2, libgl1, libegl1, libglib2.0-0, libfontconfig1, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0, libxcb-xkb1
Description: Voiceprint Studio - speaker enrollment, comparison and 1:N search
 声纹工坊：基于 ERes2NetV2 的跨平台声纹工作台，支持声纹注册、
 两段音频比对、声纹库 1:N 检索和音频波形展示。
EOF

  cat > "$PKGROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
  chmod +x "$PKGROOT/DEBIAN/postinst"

  cat > "$PKGROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
exit 0
EOF
  chmod +x "$PKGROOT/DEBIAN/postrm"

  DEB="$DIST/VoiceprintStudio-${VERSION}-${DEB_ARCH}.deb"
  dpkg-deb --root-owner-group -Zxz --build "$PKGROOT" "$DEB" >/dev/null
  echo "    $DEB"

  rm -rf "$PKGROOT"
  trap - EXIT
  rm -rf "$STAGE"
else
  echo "warning: dpkg-deb not found; skipping .deb" >&2
fi

# ------------------------------------------------------------ AppImage ------
if [[ "$APPIMAGE" == "1" ]]; then
  echo "==> building AppImage ($APPIMAGE_ARCH)"
  STAGE="$(mktemp -d)"
  APPDIR="$STAGE/VoiceprintStudio.AppDir"
  mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/voiceprint-studio" \
           "$APPDIR/usr/share/applications" \
           "$APPDIR/usr/share/icons/hicolor/256x256/apps"
  cp -R "$ONEDIR"/. "$APPDIR/usr/lib/voiceprint-studio/"
  ln -s ../lib/voiceprint-studio/VoiceprintStudio "$APPDIR/usr/bin/voiceprint-studio"
  cp packaging/linux/voiceprint-studio.desktop "$APPDIR/"
  cp packaging/linux/voiceprint-studio.desktop "$APPDIR/usr/share/applications/"
  cp "$ICON" "$APPDIR/voiceprint-studio.png"
  cp "$ICON" "$APPDIR/usr/share/icons/hicolor/256x256/apps/voiceprint-studio.png"
  cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/voiceprint-studio/VoiceprintStudio" "$@"
EOF
  chmod +x "$APPDIR/AppRun"

  TOOL="$STAGE/appimagetool"
  if [[ ! -x "$(command -v appimagetool || true)" ]]; then
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage"
    echo "    downloading $URL"
    if curl -fsSL --retry 3 -o "$TOOL" "$URL"; then
      chmod +x "$TOOL"
    else
      TOOL=""
    fi
  else
    TOOL="$(command -v appimagetool)"
  fi

  if [[ -n "$TOOL" ]]; then
    OUT="$DIST/VoiceprintStudio-${VERSION}-${APPIMAGE_ARCH}.AppImage"
    rm -f "$OUT"
    APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$APPIMAGE_ARCH" \
      "$TOOL" --no-appstream "$APPDIR" "$OUT"
    echo "    $OUT"
  else
    echo "warning: appimagetool unavailable; skipping AppImage" >&2
  fi
  rm -rf "$STAGE"
fi

echo
echo "Done. Artifacts in $DIST"