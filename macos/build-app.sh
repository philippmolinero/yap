#!/bin/bash
# Build Yap.app. Usage: ./build-app.sh [--install] [--run]
set -euo pipefail
cd "$(dirname "$0")"

swift build -c release
BIN_DIR="$(swift build -c release --show-bin-path)"

APP="dist/Yap.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$BIN_DIR/Yap" "$APP/Contents/MacOS/Yap"
cp Info.plist "$APP/Contents/Info.plist"

# SPM resource bundle: sounds, menubar icon, and seeded defaults. Flatten the
# resource files into Contents/Resources so Bundle.main finds them directly.
for bundle in "$BIN_DIR"/*.bundle; do
    [ -e "$bundle" ] || continue
    if [ -d "$bundle/Contents/Resources" ]; then
        find "$bundle/Contents/Resources" -maxdepth 1 -type f -exec cp {} "$APP/Contents/Resources/" \;
    fi
    find "$bundle" -maxdepth 1 -type f -exec cp {} "$APP/Contents/Resources/" \;
done

IDENTITY="${YAP_CODESIGN_IDENTITY:-}"
if [[ -z "$IDENTITY" ]]; then
    IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F '"' '/Yap Local Codesign|Developer ID Application|Apple Development/ { print $2; exit }')"
fi
if [[ -n "$IDENTITY" ]]; then
    /usr/bin/codesign --force --timestamp=none --sign "$IDENTITY" "$APP"
else
    /usr/bin/codesign --force --sign - "$APP"
fi

echo "Built $APP"

if [[ "${1:-}" == "--install" || "${2:-}" == "--install" ]]; then
    rm -rf /Applications/Yap.app
    cp -R "$APP" /Applications/
    echo "Installed /Applications/Yap.app"
fi

if [[ "${1:-}" == "--run" || "${2:-}" == "--run" ]]; then
    open "$APP"
fi
