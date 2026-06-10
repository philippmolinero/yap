"""Tests for app.config — config loading, migration, secrets."""

import os
import shutil
import textwrap
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory structure."""
    d = tmp_path / "yap"
    d.mkdir()
    return d


class TestSecrets:
    """Secrets loading and saving."""

    def test_load_secrets_empty_when_no_file(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"

        with mock.patch("app.config.SECRETS_FILE", secrets_file):
            from app.config import _load_secrets

            keys, prefs = _load_secrets()

        assert keys == {}
        assert prefs == {}

    def test_load_secrets_from_file(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        secrets_file.write_text(textwrap.dedent("""\
            [api_keys]
            mistral = "sk-test-mistral"
            groq = "gsk-test-groq"
        """))

        with mock.patch("app.config.SECRETS_FILE", secrets_file):
            from app.config import _load_secrets

            keys, prefs = _load_secrets()

        assert keys["mistral"] == "sk-test-mistral"
        assert keys["groq"] == "gsk-test-groq"

    def test_load_secrets_handles_invalid_toml(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        secrets_file.write_text("this is not valid toml {{{")

        with mock.patch("app.config.SECRETS_FILE", secrets_file):
            from app.config import _load_secrets

            keys, prefs = _load_secrets()

        assert keys == {}
        assert prefs == {}

    def test_save_secrets(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets

            save_secrets(mistral_api_key="sk-abc", groq_api_key="gsk-xyz")

        content = secrets_file.read_text()
        assert 'mistral = "sk-abc"' in content
        assert 'groq = "gsk-xyz"' in content

    def test_save_secrets_file_permissions(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets

            save_secrets(mistral_api_key="sk-abc", groq_api_key="gsk-xyz")

        import stat
        mode = secrets_file.stat().st_mode
        assert mode & stat.S_IROTH == 0, "secrets.toml should not be world-readable"
        assert mode & stat.S_IWOTH == 0, "secrets.toml should not be world-writable"

    def test_save_secrets_escapes_special_chars(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets, _load_secrets

            save_secrets(mistral_api_key='key-with"quote', groq_api_key="key-with\\slash")
            keys, prefs = _load_secrets()

        assert keys["mistral"] == 'key-with"quote'
        assert keys["groq"] == "key-with\\slash"

    def test_save_then_load_roundtrip(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets, _load_secrets

            save_secrets(mistral_api_key="sk-roundtrip", groq_api_key="gsk-roundtrip")
            keys, prefs = _load_secrets()

        assert keys["mistral"] == "sk-roundtrip"
        assert keys["groq"] == "gsk-roundtrip"


class TestLoadConfig:
    """Full config loading with secrets + env var precedence."""

    def test_secrets_take_precedence_over_env(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"

        # Copy bundled config
        shutil.copy(
            Path(__file__).parent.parent / "config" / "default.toml",
            config_file,
        )

        secrets_file.write_text(textwrap.dedent("""\
            [api_keys]
            mistral = "sk-from-secrets"
            groq = "gsk-from-secrets"
        """))

        env = {
            "MISTRAL_API_KEY": "sk-from-env",
            "GROQ_API_KEY": "gsk-from-env",
        }

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, env):
            from app.config import load_config

            cfg = load_config()

        assert cfg.mistral_api_key == "sk-from-secrets"
        assert cfg.groq_api_key == "gsk-from-secrets"

    def test_env_fallback_when_no_secrets(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"

        shutil.copy(
            Path(__file__).parent.parent / "config" / "default.toml",
            config_file,
        )

        env = {
            "MISTRAL_API_KEY": "sk-from-env",
            "GROQ_API_KEY": "gsk-from-env",
        }

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, env):
            from app.config import load_config

            cfg = load_config()

        assert cfg.mistral_api_key == "sk-from-env"
        assert cfg.groq_api_key == "gsk-from-env"

    def test_empty_secrets_falls_back_to_env(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"

        shutil.copy(
            Path(__file__).parent.parent / "config" / "default.toml",
            config_file,
        )

        # Secrets file exists but keys are empty
        secrets_file.write_text(textwrap.dedent("""\
            [api_keys]
            mistral = ""
            groq = ""
        """))

        env = {
            "MISTRAL_API_KEY": "sk-from-env",
            "GROQ_API_KEY": "gsk-from-env",
        }

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, env):
            from app.config import load_config

            cfg = load_config()

        assert cfg.mistral_api_key == "sk-from-env"
        assert cfg.groq_api_key == "gsk-from-env"

    def test_config_defaults(self, tmp_path):
        """Config uses correct defaults when TOML is empty."""
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("")  # empty TOML

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", config_dir / "secrets.toml"), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=False):
            from app.config import load_config

            cfg = load_config()

        assert cfg.hotkey.keycode == 62
        assert cfg.hotkey.keycodes == [61, 62]
        assert cfg.hotkey.double_tap_ms == 300
        assert cfg.transcription.provider == "groq"
        assert cfg.transcription.model == "whisper-large-v3-turbo"
        assert cfg.transcription.sample_rate == 16000
        assert cfg.transcription.allowed_languages == ["en", "de"]
        assert cfg.transcription.fallback_languages == ["de", "en"]
        assert cfg.cleanup.enabled is True
        assert cfg.cleanup.provider == "groq"
        assert cfg.cleanup.model == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert cfg.paste.delay_ms == 50
        assert cfg.silence.timeout == 5.0
        assert cfg.silence.threshold == 0.008

class TestEnsureConfigDir:
    """Config dir creation and bundled file copying."""

    def test_creates_dir_and_copies_defaults(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_file = config_dir / "config.toml"
        vocab_file = config_dir / "vocabulary.txt"

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.VOCAB_FILE", vocab_file):
            from app.config import _ensure_config_dir

            _ensure_config_dir()

        assert config_dir.exists()
        assert config_file.exists()
        assert vocab_file.exists()

    def test_does_not_overwrite_existing_config(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("custom content")

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"):
            from app.config import _ensure_config_dir

            _ensure_config_dir()

        assert config_file.read_text() == "custom content"
