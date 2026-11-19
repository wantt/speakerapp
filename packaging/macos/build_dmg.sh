#!/usr/bin/env bash
# Build "Voiceprint Studio.app" and a distributable DMG on macOS.
#
# Usage:
#   packaging/macos/build_dmg.sh [--no-build]
#
# Environment:
#   PYTHON           python interpreter with project deps (default: .venv/bin/python)
#   CODESIGN_ID      codesign identity, "-" (ad-hoc) by default
#   APPLE_ID / APPLE_TEAM_ID / APPLE_APP_PASSWORD
#                    when all three are set, the DMG is notarized with notarytool
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

APP_NAME="Voiceprint Studio"
VERSION="1.0.0"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || command -v python)"
  fi
fi
DIST="$ROOT/dist"
APP="$DIST/$APP_NAME.app"
MACHINE="$(uname -m)"
DMG="$DIST/VoiceprintStudio-$VERSION-$MACHINE.dmg"
if [[ -z "${CODESIGN_ID:-}" ]]; then
  CODESIGN_ID="$(security find-identity -v -p codesigning 2>/dev/null \
    | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)"
  [[ -z "$CODESIGN_ID" ]] && CODESIGN_ID="-"
fi

BUILD=1
for arg in "$@"; do
  case "$arg" in
    --no-build) BUILD=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "error: this script must run on macOS (hdiutil not found)" >&2
  exit 1
fi

if [[ ! -f "src/voiceprint_studio/resources/icon.icns" ]]; then
  echo "==> generating icons"
  "$PYTHON" scripts/make_icons.py
fi

if [[ "$BUILD" == "1" ]]; then
  echo "==> building $APP_NAME.app"
  "$PYTHON" -m PyInstaller --noconfirm --clean packaging/voiceprint_studio.spec
fi

if [[ ! -d "$APP" ]]; then
  echo "error: $APP not found; run without --no-build" >&2
  exit 1
fi

echo "==> verifying frozen self-test"
"$APP/Contents/MacOS/VoiceprintStudio" --self-test

echo "==> code signing (identity: $CODESIGN_ID)"
if [[ "$CODESIGN_ID" == "-" ]]; then
  codesign --force --deep --sign - "$APP"
else
  codesign --force --deep --sign "$CODESIGN_ID" \
    --timestamp \
    --options runtime \
    --entitlements packaging/macos/entitlements.plist \
    "$APP"
fi
codesign --verify --deep --strict --verbose=2 "$APP"

echo "==> creating DMG"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/voiceprint-dmg.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -ov \
  -format UDZO \
  "$DMG"
hdiutil verify "$DMG"

if [[ "$CODESIGN_ID" != "-" ]]; then
  echo "==> signing DMG"
  codesign --force --sign "$CODESIGN_ID" --timestamp "$DMG"
  codesign --verify --verbose=2 "$DMG"
fi

NOTARY_PASSWORD="${APPLE_APP_PASSWORD:-${APPLE_APP_SPECIFIC_PASSWORD:-}}"
if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "$NOTARY_PASSWORD" ]]; then
  echo "==> notarizing (this can take a few minutes)"
  xcrun notarytool submit "$DMG" \
    --apple-id "$APPLE_ID" \
    --team-id "$APPLE_TEAM_ID" \
    --password "$NOTARY_PASSWORD" \
    --wait
  xcrun stapler staple "$DMG"
fi

echo
echo "Done: $DMG"
echo "      $APP"