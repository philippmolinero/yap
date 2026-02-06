"""Configuration loading: TOML config + vocabulary + environment variables."""

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "voxtral-dictation"
CONFIG_FILE = CONFIG_DIR / "config.toml"
VOCAB_FILE = CONFIG_DIR / "vocabulary.txt"

# Bundled defaults (shipped with the app)
_BUNDLED_DIR = Path(__file__).parent.parent / "config"
_BUNDLED_CONFIG = _BUNDLED_DIR / "default.toml"
_BUNDLED_VOCAB = _BUNDLED_DIR / "vocabulary.txt"


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


def _ensure_config_dir():
    """Create config dir and copy defaults on first run."""
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


def load_config() -> AppConfig:
    """Load full app configuration from TOML + vocabulary + env."""
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

    return AppConfig(
        hotkey=HotkeyConfig(
            keycode=hotkey_raw.get("keycode", 61),
            double_tap_ms=hotkey_raw.get("double_tap_ms", 300),
        ),
        transcription=TranscriptionConfig(
            model=trans_raw.get("model", "voxtral-mini-latest"),
            sample_rate=trans_raw.get("sample_rate", 16000),
        ),
        cleanup=CleanupConfig(
            enabled=cleanup_raw.get("enabled", True),
            provider=cleanup_raw.get("provider", "groq"),
            model=cleanup_raw.get("model", "llama-3.3-70b-versatile"),
        ),
        paste=PasteConfig(
            delay_ms=paste_raw.get("delay_ms", 50),
        ),
        silence=SilenceConfig(
            timeout=silence_raw.get("timeout", 5.0),
            threshold=silence_raw.get("threshold", 0.008),
        ),
        vocabulary=_load_vocabulary(),
        mistral_api_key=os.environ.get("MISTRAL_API_KEY", ""),
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
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
