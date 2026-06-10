#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="Yap.app"
APP_DEST="/Applications/$APP_NAME"
APP_SOURCE="dist/$APP_NAME"
PLIST_PATH="$HOME/Library/LaunchAgents/com.yap-dictation.plist"
LOCK_PATH="$HOME/.config/yap/.yap.lock"

FULL_CLEAN=0
SKIP_BUILD=0
NO_LAUNCH=0

usage() {
    cat <<EOF
Usage: ./update.sh [options]

Options:
  --full-clean   Remove app, config, old backups, and reset TCC permissions
  --skip-build   Reinstall from existing dist/Yap.app without rebuilding
  --no-launch    Do not open Yap after install
  -h, --help     Show this help

Examples:
  ./update.sh
  ./update.sh --full-clean
  ./update.sh --skip-build --no-launch
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --full-clean)
            FULL_CLEAN=1
            shift
            ;;
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --no-launch)
            NO_LAUNCH=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

echo "=== Yap — Update ==="
echo ""

echo "Stopping running Yap instances..."
pkill -f "/Applications/Yap.app/Contents/MacOS/Yap" 2>/dev/null || true
pkill -f "python3 -m app.main" 2>/dev/null || true
pkill -f "Python -m app.main" 2>/dev/null || true
rm -f "$LOCK_PATH" 2>/dev/null || true

echo "Removing old launch agent (if present)..."
launchctl unload "$PLIST_PATH" 2>/dev/null || true
rm -f "$PLIST_PATH" 2>/dev/null || true

echo "Removing installed app..."
rm -rf "$APP_DEST"

if [[ "$FULL_CLEAN" -eq 1 ]]; then
    echo "Running full clean..."
    rm -rf "$HOME/.config/yap"
    rm -rf "$HOME/.config"/yap.backup.* 2>/dev/null || true
    tccutil reset All com.yap.dictation 2>/dev/null || true
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
    echo ""
    echo "Building fresh app bundle..."
    ./build.sh
fi

if [[ ! -d "$APP_SOURCE" ]]; then
    echo "Error: $APP_SOURCE not found."
    echo "Run ./build.sh first or remove --skip-build."
    exit 1
fi

echo ""
echo "Installing app to /Applications..."
cp -R "$APP_SOURCE" "$APP_DEST"
xattr -cr "$APP_DEST"

if [[ "$NO_LAUNCH" -eq 0 ]]; then
    echo "Launching Yap..."
    open "$APP_DEST"
fi

echo ""
echo "=== Update complete ==="
if [[ "$FULL_CLEAN" -eq 1 ]]; then
    echo "Full clean was applied. You may need to re-grant permissions and re-enter API keys."
fi
