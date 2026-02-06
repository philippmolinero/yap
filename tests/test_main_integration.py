"""Tests for app.main — integration of settings, resources, and menu structure."""

from pathlib import Path
from unittest import mock

import pytest


class TestIconPath:
    """Icon path uses get_resource_path."""

    def test_icon_path_resolves_to_existing_file(self):
        from app.main import _ICON_PATH

        assert Path(_ICON_PATH).exists()
        assert _ICON_PATH.endswith("icon_menubar.png")

    def test_icon_path_is_string(self):
        from app.main import _ICON_PATH

        assert isinstance(_ICON_PATH, str)


class TestConfigDirPaths:
    """Verify the config directory references are updated."""

    def test_config_dir_is_yap(self):
        from app.config import CONFIG_DIR

        assert CONFIG_DIR.name == "yap"
        assert str(CONFIG_DIR).endswith(".config/yap")

    def test_old_config_dir_is_voxtral(self):
        from app.config import _OLD_CONFIG_DIR

        assert _OLD_CONFIG_DIR.name == "voxtral-dictation"

    def test_secrets_file_in_config_dir(self):
        from app.config import CONFIG_DIR, SECRETS_FILE

        assert SECRETS_FILE.parent == CONFIG_DIR
        assert SECRETS_FILE.name == "secrets.toml"
