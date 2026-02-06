#!/bin/bash
set -e

cd "$(dirname "$0")"

APP_PATH="dist/Yap.app"
DMG_NAME="Yap-1.0.0.dmg"
DMG_PATH="dist/$DMG_NAME"
VOLUME_NAME="Yap"
TMP_DMG="dist/tmp_yap.dmg"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH not found. Run ./build.sh first."
    exit 1
fi

echo "=== Creating DMG ==="

# Clean previous DMG
rm -f "$DMG_PATH" "$TMP_DMG"

# Create temporary DMG
hdiutil create -srcfolder "$APP_PATH" -volname "$VOLUME_NAME" -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" -format UDRW "$TMP_DMG"

# Convert to compressed read-only DMG
hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH"
rm -f "$TMP_DMG"

echo ""
echo "=== DMG created ==="
echo "Output: $DMG_PATH"
