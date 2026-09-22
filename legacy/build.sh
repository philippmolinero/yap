#!/bin/bash
set -e

cd "$(dirname "$0")"

VERSION="$(python3 - <<'PY'
from app.version import APP_VERSION
print(APP_VERSION)
PY
)"

echo "=== Yap — Build ==="
echo ""

# Clean previous builds
rm -rf build/ dist/

echo "Building Yap.app with PyInstaller..."
pyinstaller yap.spec --noconfirm

if [[ -z "${YAP_CODESIGN_IDENTITY:-}" ]]; then
    YAP_CODESIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F '"' '/Developer ID Application|Apple Development|Yap Local Codesign/ { print $2; exit }')"
fi

if [[ -n "${YAP_CODESIGN_IDENTITY:-}" ]]; then
    echo "Signing Yap.app with: $YAP_CODESIGN_IDENTITY"
    /usr/bin/codesign --force --deep --timestamp=none --sign "$YAP_CODESIGN_IDENTITY" "dist/Yap.app"
else
    echo "Warning: no code signing identity found; Yap.app will keep PyInstaller's ad-hoc signature."
    echo "macOS may ask for Input Monitoring and Accessibility permissions again after each rebuild."
fi

ZIP_PATH="dist/Yap-${VERSION}.zip"
echo "Creating release zip..."
ditto -c -k --sequesterRsrc --keepParent "dist/Yap.app" "$ZIP_PATH"

echo ""
echo "=== Build complete ==="
echo "App bundle: dist/Yap.app"
echo "Zip asset:  $ZIP_PATH"
echo ""
echo "To test: open dist/Yap.app"
echo "To create DMG: ./create_dmg.sh"
