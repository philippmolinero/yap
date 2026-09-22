#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

VERSION="$(python3 - <<'PY'
from app.version import APP_VERSION
print(APP_VERSION)
PY
)"
TAG="v${VERSION}"
TITLE="Yap ${VERSION}"
ZIP_PATH="dist/Yap-${VERSION}.zip"
DMG_PATH="dist/Yap-${VERSION}.dmg"

SKIP_BUILD=0
DRAFT=0
PRERELEASE=0
ALLOW_DIRTY=0
GENERATE_NOTES=1
NOTES_FILE=""
NOTES_TEXT=""

usage() {
    cat <<EOF
Usage: ./release.sh [options]

Options:
  --skip-build         Reuse existing dist artifacts
  --draft              Create or keep the release as a draft
  --prerelease         Mark the release as a prerelease
  --allow-dirty        Allow releasing from a dirty worktree
  --notes-file PATH    Use explicit release notes from a file
  --notes TEXT         Use explicit release notes text
  --no-generate-notes  Disable GitHub auto-generated release notes
  -h, --help           Show this help

Examples:
  ./release.sh
  ./release.sh --draft
  ./release.sh --notes-file docs/release-notes/0.2.1.md
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build)
            SKIP_BUILD=1
            shift
            ;;
        --draft)
            DRAFT=1
            shift
            ;;
        --prerelease)
            PRERELEASE=1
            shift
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            shift
            ;;
        --notes-file)
            NOTES_FILE="${2:-}"
            shift 2
            ;;
        --notes)
            NOTES_TEXT="${2:-}"
            shift 2
            ;;
        --no-generate-notes)
            GENERATE_NOTES=0
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

if [[ -n "$NOTES_FILE" && -n "$NOTES_TEXT" ]]; then
    echo "Error: use either --notes-file or --notes, not both." >&2
    exit 1
fi

if [[ -n "$NOTES_FILE" && ! -f "$NOTES_FILE" ]]; then
    echo "Error: notes file not found: $NOTES_FILE" >&2
    exit 1
fi

if [[ "$ALLOW_DIRTY" -eq 0 ]] && [[ -n "$(git status --short)" ]]; then
    echo "Error: git worktree is dirty. Commit or stash changes, or rerun with --allow-dirty." >&2
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "Error: GitHub CLI 'gh' is not installed." >&2
    exit 1
fi

gh auth status >/dev/null

echo "=== Yap — Release ${VERSION} ==="
echo ""

if [[ "$SKIP_BUILD" -eq 0 ]]; then
    ./build.sh
    ./create_dmg.sh
fi

if [[ ! -f "$ZIP_PATH" ]]; then
    echo "Error: missing zip asset: $ZIP_PATH" >&2
    exit 1
fi

if [[ ! -f "$DMG_PATH" ]]; then
    echo "Error: missing DMG asset: $DMG_PATH" >&2
    exit 1
fi

CREATE_ARGS=(
    "$TAG"
    "$ZIP_PATH"
    "$DMG_PATH"
    --title "$TITLE"
    --target "$(git rev-parse HEAD)"
)

EDIT_ARGS=(
    "$TAG"
    --title "$TITLE"
)

if [[ "$DRAFT" -eq 1 ]]; then
    CREATE_ARGS+=(--draft)
    EDIT_ARGS+=(--draft)
fi

if [[ "$PRERELEASE" -eq 1 ]]; then
    CREATE_ARGS+=(--prerelease)
    EDIT_ARGS+=(--prerelease)
fi

if [[ -n "$NOTES_FILE" ]]; then
    CREATE_ARGS+=(--notes-file "$NOTES_FILE")
    EDIT_ARGS+=(--notes-file "$NOTES_FILE")
elif [[ -n "$NOTES_TEXT" ]]; then
    CREATE_ARGS+=(--notes "$NOTES_TEXT")
    EDIT_ARGS+=(--notes "$NOTES_TEXT")
elif [[ "$GENERATE_NOTES" -eq 1 ]]; then
    CREATE_ARGS+=(--generate-notes)
fi

if gh release view "$TAG" >/dev/null 2>&1; then
    echo "Release $TAG already exists — updating assets..."
    gh release upload "$TAG" "$ZIP_PATH" "$DMG_PATH" --clobber

    if [[ -n "$NOTES_FILE" || -n "$NOTES_TEXT" || "$DRAFT" -eq 1 || "$PRERELEASE" -eq 1 ]]; then
        gh release edit "${EDIT_ARGS[@]}"
    fi
else
    echo "Creating release $TAG..."
    gh release create "${CREATE_ARGS[@]}"
fi

echo ""
echo "=== Release complete ==="
echo "Tag:    $TAG"
echo "Assets: $ZIP_PATH, $DMG_PATH"
echo "Open:   https://github.com/philippmolinero/yap/releases/tag/$TAG"
