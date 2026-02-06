#!/bin/bash
# Yap Installer — copies app to /Applications and strips macOS provenance flag

set -e

APP_NAME="Yap.app"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$SCRIPT_DIR/$APP_NAME"
DEST="/Applications/$APP_NAME"

if [ ! -d "$SOURCE" ]; then
    echo "Error: $APP_NAME not found next to this installer."
    exit 1
fi

echo "Installing Yap..."

# Remove old version if present
rm -rf "$DEST"

# Copy app to /Applications
cp -R "$SOURCE" "$DEST"

# Strip provenance/quarantine flags that block event tap access
xattr -cr "$DEST"

echo ""
echo "Yap installed to /Applications."
echo "You can now launch it from Applications or Spotlight."
echo ""
echo "First launch: grant Accessibility and Microphone permissions when prompted."
open "$DEST"
