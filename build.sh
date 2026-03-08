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
