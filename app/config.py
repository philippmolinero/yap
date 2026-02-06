"""Configuration loading: TOML config + vocabulary + secrets + environment variables."""

import logging
import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from app.resources import get_resource_path

logger = logging.getLogger(__name__)

_OLD_CONFIG_DIR = Path.home() / ".config" / "voxtral-dictation"
CONFIG_DIR = Path.home() / ".config" / "yap"
CONFIG_FILE = CONFIG_DIR / "config.toml"
VOCAB_FILE = CONFIG_DIR / "vocabulary.txt"
SECRETS_FILE = CONFIG_DIR / "secrets.toml"

# Bundled defaults (shipped with the app)
_BUNDLED_CONFIG = get_resource_path("config", "default.toml")
_BUNDLED_VOCAB = get_resource_path("config", "vocabulary.txt")


@dataclass
class HotkeyConfig:
    keycode: int = 61
    double_tap_ms: int = 300


@dataclass
class TranscriptionConfig:
    model: str = "voxtral-mini-latest"
    sample_rate: int = 16000


@dataclass
class CleanupConfig:
    enabled: bool = True
    provider: str = "groq"
    model: str = "llama-3.3-70b-versatile"


@dataclass
class PasteConfig:
    delay_ms: int = 50


@dataclass
class SilenceConfig:
    timeout: float = 5.0
    threshold: float = 0.008


@dataclass
class AppConfig:
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)
    silence: SilenceConfig = field(default_factory=SilenceConfig)
    vocabulary: list[str] = field(default_factory=list)
    mistral_api_key: str = ""
    groq_api_key: str = ""


def _migrate_config_dir():
    """Migrate from old ~/.config/voxtral-dictation/ to ~/.config/yap/."""
    if _OLD_CONFIG_DIR.exists() and not CONFIG_DIR.exists():
        logger.info("Migrating config dir: %s -> %s", _OLD_CONFIG_DIR, CONFIG_DIR)
        shutil.move(str(_OLD_CONFIG_DIR), str(CONFIG_DIR))


def _ensure_config_dir():
    """Create config dir and copy defaults on first run."""
    _migrate_config_dir()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists() and _BUNDLED_CONFIG.exists():
        shutil.copy(_BUNDLED_CONFIG, CONFIG_FILE)

    if not VOCAB_FILE.exists() and _BUNDLED_VOCAB.exists():
        shutil.copy(_BUNDLED_VOCAB, VOCAB_FILE)


def _load_vocabulary() -> list[str]:
    """Load vocabulary terms from file, one per line."""
    if not VOCAB_FILE.exists():
        return []
    lines = VOCAB_FILE.read_text().strip().splitlines()
    return [line.strip() for line in lines if line.strip()]


def _load_secrets() -> dict[str, str]:
    """Load API keys from secrets.toml."""
    if not SECRETS_FILE.exists():
        return {}
    try:
        raw = tomllib.loads(SECRETS_FILE.read_text())
        return raw.get("api_keys", {})
    except Exception:
        logger.warning("Failed to parse secrets.toml, ignoring")
        return {}


def _escape_toml_string(s: str) -> str:
    """Escape a string for safe inclusion in a TOML double-quoted value."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def save_secrets(*, mistral_api_key: str = "", groq_api_key: str = ""):
    """Save API keys to secrets.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = "[api_keys]\n"
    content += f'mistral = "{_escape_toml_string(mistral_api_key)}"\n'
    content += f'groq = "{_escape_toml_string(groq_api_key)}"\n'
    SECRETS_FILE.write_text(content)
    SECRETS_FILE.chmod(0o600)


def load_config() -> AppConfig:
    """Load full app configuration from TOML + vocabulary + secrets + env."""
    load_dotenv()
    _ensure_config_dir()

    # Parse TOML
    raw = {}
    if CONFIG_FILE.exists():
        raw = tomllib.loads(CONFIG_FILE.read_text())

    hotkey_raw = raw.get("hotkey", {})
    trans_raw = raw.get("transcription", {})
    cleanup_raw = raw.get("cleanup", {})
    paste_raw = raw.get("paste", {})
    silence_raw = raw.get("silence", {})

    # API keys: secrets.toml > env vars
    secrets = _load_secrets()
    mistral_key = secrets.get("mistral", "") or os.environ.get("MISTRAL_API_KEY", "")
    groq_key = secrets.get("groq", "") or os.environ.get("GROQ_API_KEY", "")

    return AppConfig(
        hotkey=HotkeyConfig(**hotkey_raw),
        transcription=TranscriptionConfig(**trans_raw),
        cleanup=CleanupConfig(**cleanup_raw),
        paste=PasteConfig(**paste_raw),
        silence=SilenceConfig(**silence_raw),
        vocabulary=_load_vocabulary(),
        mistral_api_key=mistral_key,
        groq_api_key=groq_key,
    )


if __name__ == "__main__":
    cfg = load_config()
    print(f"Config dir: {CONFIG_DIR}")
    print(f"Hotkey keycode: {cfg.hotkey.keycode}")
    print(f"Transcription model: {cfg.transcription.model}")
    print(f"Cleanup enabled: {cfg.cleanup.enabled}, provider: {cfg.cleanup.provider}")
    print(f"Vocabulary: {cfg.vocabulary}")
    print(f"Mistral key: {'set' if cfg.mistral_api_key else 'missing'}")
    print(f"Groq key: {'set' if cfg.groq_api_key else 'missing'}")
