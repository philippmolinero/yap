#!/bin/bash

PLIST_NAME="com.yap-dictation"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

echo "=== Yap — Uninstall ==="

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null
    rm "$PLIST_PATH"
    echo "Removed launchd plist."
else
    echo "No launchd plist found."
fi

echo ""
echo "Done. The app will no longer auto-start."
echo "Your config remains at ~/.config/voxtral-dictation/"
echo "To fully remove, delete the voxtral-dictation directory."
