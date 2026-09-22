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
            cerebras = "csk-test-cerebras"
        """))

        with mock.patch("app.config.SECRETS_FILE", secrets_file):
            from app.config import _load_secrets

            keys, prefs = _load_secrets()

        assert keys["mistral"] == "sk-test-mistral"
        assert keys["groq"] == "gsk-test-groq"
        assert keys["cerebras"] == "csk-test-cerebras"

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

            save_secrets(
                mistral_api_key="sk-abc",
                groq_api_key="gsk-xyz",
                cerebras_api_key="csk-123",
            )

        content = secrets_file.read_text()
        assert 'mistral = "sk-abc"' in content
        assert 'groq = "gsk-xyz"' in content
        assert 'cerebras = "csk-123"' in content

    def test_save_secrets_file_permissions(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets

            save_secrets(
                mistral_api_key="sk-abc",
                groq_api_key="gsk-xyz",
                cerebras_api_key="csk-123",
            )

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

            save_secrets(
                mistral_api_key='key-with"quote',
                groq_api_key="key-with\\slash",
                cerebras_api_key="key-with-cerebras",
            )
            keys, prefs = _load_secrets()

        assert keys["mistral"] == 'key-with"quote'
        assert keys["groq"] == "key-with\\slash"
        assert keys["cerebras"] == "key-with-cerebras"

    def test_save_then_load_roundtrip(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets, _load_secrets

            save_secrets(
                mistral_api_key="sk-roundtrip",
                groq_api_key="gsk-roundtrip",
                cerebras_api_key="csk-roundtrip",
            )
            keys, prefs = _load_secrets()

        assert keys["mistral"] == "sk-roundtrip"
        assert keys["groq"] == "gsk-roundtrip"
        assert keys["cerebras"] == "csk-roundtrip"

    def test_save_secrets_roundtrips_cleanup_model_preference(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets, _load_secrets

            save_secrets(
                cerebras_api_key="csk-roundtrip",
                cleanup_provider="cerebras",
                cleanup_model="gemma-4-31b",
            )
            keys, prefs = _load_secrets()

        assert keys["cerebras"] == "csk-roundtrip"
        assert prefs == {"cleanup_provider": "cerebras", "cleanup_model": "gemma-4-31b"}

    def test_save_secrets_roundtrips_gemini_transcription_preference(self, tmp_path):
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        with mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.CONFIG_DIR", config_dir):
            from app.config import save_secrets, _load_secrets

            save_secrets(
                gemini_api_key="AIza-roundtrip",
                cerebras_api_key="csk-roundtrip",
                cleanup_provider="cerebras",
                cleanup_model="gpt-oss-120b",
                transcription_provider="gemini",
            )
            keys, prefs = _load_secrets()

        assert keys["google"] == "AIza-roundtrip"
        assert keys["cerebras"] == "csk-roundtrip"
        assert prefs["cleanup_provider"] == "cerebras"
        assert prefs["transcription_provider"] == "gemini"


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
            cerebras = "csk-from-secrets"
        """))

        env = {
            "MISTRAL_API_KEY": "sk-from-env",
            "GROQ_API_KEY": "gsk-from-env",
            "CEREBRAS_API_KEY": "csk-from-env",
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
        assert cfg.cerebras_api_key == "csk-from-secrets"

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
            "CEREBRAS_API_KEY": "csk-from-env",
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
        assert cfg.cerebras_api_key == "csk-from-env"

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
            cerebras = ""
        """))

        env = {
            "MISTRAL_API_KEY": "sk-from-env",
            "GROQ_API_KEY": "gsk-from-env",
            "CEREBRAS_API_KEY": "csk-from-env",
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
        assert cfg.cerebras_api_key == "csk-from-env"

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
        assert cfg.transcription.provider == "gemini"
        assert cfg.transcription.model == "gemini-3.5-transcribe"
        assert cfg.transcription.mode == "smart"
        assert cfg.transcription.language == ""
        assert cfg.transcription.sample_rate == 16000
        assert cfg.transcription.allowed_languages == ["en", "de"]
        assert cfg.transcription.fallback_languages == ["de", "en"]
        assert cfg.cleanup.enabled is True
        assert cfg.cleanup.provider == "groq"
        assert cfg.cleanup.model == "openai/gpt-oss-120b"
        assert cfg.cerebras_api_key == ""
        assert cfg.paste.delay_ms == 50
        assert cfg.silence.timeout == 5.0
        assert cfg.silence.threshold == 0.008
        assert cfg.thai_practice.enabled is True
        assert cfg.thai_practice.modifier_keycode == 60
        assert cfg.thai_practice.prompt_id == "sentence-01"
        assert cfg.thai_practice.prompt_text == "ตอนนั้นฉันอายุเจ็ดขวบ"
        assert cfg.thai_practice.prompt_source == "learning-thai"

    def test_cerebras_preference_selects_production_cleanup_model(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"

        shutil.copy(Path(__file__).parent.parent / "config" / "default.toml", config_file)
        secrets_file.write_text(
            textwrap.dedent(
                """\
                [api_keys]
                mistral = ""
                groq = ""
                cerebras = "csk-from-secrets"

                [preferences]
                cleanup_provider = "cerebras"
                """
            )
        )

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=True):
            from app.config import load_config

            cfg = load_config()

        assert cfg.cerebras_api_key == "csk-from-secrets"
        assert cfg.cleanup.provider == "cerebras"
        assert cfg.cleanup.model == "gpt-oss-120b"

    def test_cerebras_preference_preserves_explicit_model(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"
        config_file.write_text(
            "[cleanup]\nprovider = \"groq\"\nmodel = \"gemma-4-31b\"\n"
        )
        secrets_file.write_text(
            "[api_keys]\ncerebras = \"csk-from-secrets\"\n\n[preferences]\ncleanup_provider = \"cerebras\"\n"
        )

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=True):
            from app.config import load_config

            cfg = load_config()

        assert cfg.cleanup.provider == "cerebras"
        assert cfg.cleanup.model == "gemma-4-31b"

    def test_cerebras_key_does_not_change_default_provider(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"
        shutil.copy(Path(__file__).parent.parent / "config" / "default.toml", config_file)
        secrets_file.write_text("[api_keys]\ncerebras = \"csk-from-secrets\"\n")

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=True):
            from app.config import load_config

            cfg = load_config()

        assert cfg.cleanup.provider == "groq"

    def test_retired_groq_cleanup_model_is_migrated(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text(
            '[cleanup]\nprovider = "groq"\nmodel = "meta-llama/llama-4-scout-17b-16e-instruct"\n'
        )

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", config_dir / "secrets.toml"), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=True):
            from app.config import load_config

            cfg = load_config()

        assert cfg.cleanup.provider == "groq"
        assert cfg.cleanup.model == "openai/gpt-oss-120b"

    def test_gemini_transcription_preference_selects_smart_without_disabling_cleanup(self, tmp_path):
        config_dir = tmp_path / "yap"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        secrets_file = config_dir / "secrets.toml"
        shutil.copy(Path(__file__).parent.parent / "config" / "default.toml", config_file)
        secrets_file.write_text(
            textwrap.dedent(
                """\
                [api_keys]
                google = "AIza-from-secrets"
                cerebras = "csk-from-secrets"

                [preferences]
                cleanup_provider = "cerebras"
                transcription_provider = "gemini"
                """
            )
        )

        with mock.patch("app.config.CONFIG_DIR", config_dir), \
             mock.patch("app.config.CONFIG_FILE", config_file), \
             mock.patch("app.config.SECRETS_FILE", secrets_file), \
             mock.patch("app.config.VOCAB_FILE", config_dir / "vocabulary.txt"), \
             mock.patch.dict(os.environ, {}, clear=True):
            from app.config import load_config

            cfg = load_config()

        assert cfg.gemini_api_key == "AIza-from-secrets"
        assert cfg.transcription.provider == "gemini"
        assert cfg.transcription.model == "gemini-3.5-transcribe"
        assert cfg.transcription.mode == "smart"
        assert cfg.cleanup.provider == "cerebras"
        assert cfg.cleanup.enabled is True

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
