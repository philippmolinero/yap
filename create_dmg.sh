#!/bin/bash
set -e

cd "$(dirname "$0")"

APP_PATH="dist/Yap.app"
DMG_NAME="Yap-0.2.0.dmg"
DMG_PATH="dist/$DMG_NAME"
VOLUME_NAME="Yap"
TMP_DIR="dist/dmg_staging"
TMP_DMG="dist/tmp_yap.dmg"

if [ ! -d "$APP_PATH" ]; then
    echo "Error: $APP_PATH not found. Run ./build.sh first."
    exit 1
fi

echo "=== Creating DMG ==="

# Clean previous
rm -rf "$TMP_DIR" "$TMP_DMG" "$DMG_PATH"

# Create staging directory with app + Applications symlink
mkdir -p "$TMP_DIR"
cp -R "$APP_PATH" "$TMP_DIR/"
ln -s /Applications "$TMP_DIR/Applications"

# Create temporary DMG from staging directory
hdiutil create -srcfolder "$TMP_DIR" -volname "$VOLUME_NAME" -fs HFS+ \
    -fsargs "-c c=64,a=16,e=16" -format UDRW "$TMP_DMG"

# Convert to compressed read-only DMG
hdiutil convert "$TMP_DMG" -format UDZO -o "$DMG_PATH"

# Cleanup
rm -rf "$TMP_DIR" "$TMP_DMG"

echo ""
echo "=== DMG created ==="
echo "Output: $DMG_PATH"
echo ""
echo "Drag Yap.app to Applications. The app self-strips quarantine on first launch."
