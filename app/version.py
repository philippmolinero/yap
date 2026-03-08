"""Version and release metadata for Yap."""

from pathlib import Path
import sys

APP_NAME = "Yap"
APP_VERSION = "0.2.1"
GITHUB_REPO = "philippmolinero/yap"


def normalize_version(version: str) -> str:
    """Normalize a version string such as 'v0.2.1' -> '0.2.1'."""
    return version.strip().removeprefix("v")


def parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted numeric version into a tuple for comparison."""
    normalized = normalize_version(version)
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"Unsupported version format: {version}")
    return tuple(int(part) for part in parts)


def is_newer_version(candidate: str, current: str) -> bool:
    """Return True when candidate is newer than current."""
    return parse_version(candidate) > parse_version(current)


def release_asset_name_for_version(version: str) -> str:
    """Return the expected zip asset name for a release."""
    return f"{APP_NAME}-{normalize_version(version)}.zip"


def bundled_app_path() -> Path | None:
    """Return the current .app bundle path when running from a bundle."""
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app" and parent.name == f"{APP_NAME}.app":
            return parent
    return None
