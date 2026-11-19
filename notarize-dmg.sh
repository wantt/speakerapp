#!/bin/bash
#
# Voiceprint Studio macOS DMG Batch Notarization Script
#
# Usage: ./notarize-dmg.sh <release-folder>
#
# Notarizes and staples all .dmg files in the given folder.
# Credentials are read from .env (APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD,
# APPLE_TEAM_ID) or from the environment.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
RELEASE_DIR="$1"

if [ -z "$RELEASE_DIR" ]; then
    echo -e "${RED}✗ Usage: $0 <release-folder>${NC}"
    exit 1
fi

if [ ! -d "$RELEASE_DIR" ]; then
    echo -e "${RED}✗ Directory not found: $RELEASE_DIR${NC}"
    exit 1
fi

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Voiceprint Studio DMG Batch Notarization${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Load .env file (repo root first, then parent, then cwd)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
for ENV_FILE in "$SCRIPT_DIR/.env" "$SCRIPT_DIR/../.env" ".env"; do
    if [ -f "$ENV_FILE" ]; then
        echo -e "${GREEN}✓${NC} Loading $ENV_FILE..."
        set -a
        source "$ENV_FILE"
        set +a
        break
    fi
done

# Validate environment variables
MISSING=""
[ -z "$APPLE_ID" ]                    && MISSING="$MISSING APPLE_ID"
[ -z "$APPLE_APP_SPECIFIC_PASSWORD" ] && MISSING="$MISSING APPLE_APP_SPECIFIC_PASSWORD"
[ -z "$APPLE_TEAM_ID" ]               && MISSING="$MISSING APPLE_TEAM_ID"

if [ -n "$MISSING" ]; then
    echo -e "${RED}✗ Missing environment variables:$MISSING${NC}"
    echo ""
    echo "Create a .env file with:"
    echo "  APPLE_ID=your@email.com"
    echo "  APPLE_APP_SPECIFIC_PASSWORD=xxxx-xxxx-xxxx-xxxx"
    echo "  APPLE_TEAM_ID=XXXXXXXXXX"
    exit 1
fi

echo -e "${GREEN}✓${NC} Environment variables set"
echo -e "  APPLE_ID:      $APPLE_ID"
echo -e "  APPLE_TEAM_ID: $APPLE_TEAM_ID"

# Check Developer ID certificate
CERT=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1)
if [ -z "$CERT" ]; then
    echo -e "${RED}✗ No Developer ID Application certificate found${NC}"
    exit 1
fi
CODESIGN_ID="${CODESIGN_ID:-$(echo "$CERT" | sed 's/.*"\(.*\)".*/\1/')}"
echo -e "${GREEN}✓${NC} Certificate: $CODESIGN_ID"

# Collect DMG files (bash 3.2 compatible - macOS ships bash 3.2)
DMG_FILES=()
while IFS= read -r dmg; do
    DMG_FILES+=("$dmg")
done < <(find "$RELEASE_DIR" -maxdepth 2 -name "*.dmg" | sort)

if [ ${#DMG_FILES[@]} -eq 0 ]; then
    echo -e "${RED}✗ No .dmg files found in: $RELEASE_DIR${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}Found ${#DMG_FILES[@]} DMG file(s):${NC}"
for f in "${DMG_FILES[@]}"; do
    echo -e "  ${YELLOW}•${NC} $f"
done

# --- Helper: notarize + staple one DMG ---
notarize_dmg() {
    local DMG="$1"
    local NAME
    NAME="$(basename "$DMG")"

    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Notarizing: $NAME${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Sign the DMG itself (best practice before notarization)
    echo -e "${BLUE}➤${NC} Signing DMG..."
    if ! codesign --force --sign "$CODESIGN_ID" --timestamp "$DMG"; then
        echo -e "${RED}✗ DMG signing failed for: $NAME${NC}"
        return 1
    fi

    # Submit for notarization and wait
    echo -e "${BLUE}➤${NC} Submitting to Apple Notary Service..."
    if ! xcrun notarytool submit "$DMG" \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_APP_SPECIFIC_PASSWORD" \
        --team-id "$APPLE_TEAM_ID" \
        --wait \
        --timeout 30m; then
        echo -e "${RED}✗ Notarization failed for: $NAME${NC}"
        return 1
    fi

    # Staple the ticket
    echo -e "${BLUE}➤${NC} Stapling notarization ticket..."
    if ! xcrun stapler staple "$DMG"; then
        echo -e "${RED}✗ Stapling failed for: $NAME${NC}"
        return 1
    fi

    # Verify
    echo -e "${BLUE}➤${NC} Verifying..."
    if xcrun stapler validate "$DMG" &>/dev/null; then
        echo -e "${GREEN}✓ $NAME — notarized and stapled${NC}"
        return 0
    else
        echo -e "${RED}✗ Validation failed for: $NAME${NC}"
        return 1
    fi
}

# --- Process all DMGs ---
PASS=0
FAIL=0
FAILED_FILES=()
START=$(date +%s)

for DMG in "${DMG_FILES[@]}"; do
    if notarize_dmg "$DMG"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED_FILES+=("$DMG")
    fi
done

END=$(date +%s)

# --- Summary ---
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Summary  (elapsed: $((END - START))s)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Passed: $PASS${NC}"
[ $FAIL -gt 0 ] && echo -e "${RED}  Failed: $FAIL${NC}"

if [ ${#FAILED_FILES[@]} -gt 0 ]; then
    echo -e "${RED}  Failed files:${NC}"
    for f in "${FAILED_FILES[@]}"; do
        echo -e "${RED}    • $f${NC}"
    done
fi

echo ""
echo -e "${BLUE}DMG files in $RELEASE_DIR:${NC}"
ls -lh "$RELEASE_DIR"/*.dmg 2>/dev/null || true
echo ""

[ $FAIL -eq 0 ]
