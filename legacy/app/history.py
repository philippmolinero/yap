"""Persistent dictation history: JSON file in the config dir."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_history(path: Path, limit: int = 15) -> list[str]:
    """Load history entries (most recent first). Returns [] on any problem."""
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load history from %s", path)
        return []
    if not isinstance(data, list):
        logger.warning("History file %s has unexpected format, ignoring", path)
        return []
    return [item for item in data if isinstance(item, str) and item][:limit]


def save_history(path: Path, items: list[str]):
    """Atomically write history entries (most recent first). Best-effort."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(list(items), ensure_ascii=False))
        tmp.chmod(0o600)  # dictations are private
        tmp.replace(path)
    except OSError:
        logger.exception("Failed to save history to %s", path)
