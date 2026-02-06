#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Yap — Build ==="
echo ""

# Clean previous builds
rm -rf build/ dist/

echo "Building Yap.app with PyInstaller..."
pyinstaller yap.spec --noconfirm

echo ""
echo "=== Build complete ==="
echo "App bundle: dist/Yap.app"
echo ""
echo "To test: open dist/Yap.app"
echo "To create DMG: ./create_dmg.sh"
