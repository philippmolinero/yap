"""Tests for app.resources — resource path resolution."""

import sys
from pathlib import Path
from unittest import mock

import pytest


# The project root (yap/)
PROJECT_ROOT = Path(__file__).parent.parent


class TestDevMode:
    """In dev mode, sys._MEIPASS is not set — paths resolve relative to project root."""

    def test_get_resource_path_returns_path_object(self):
        from app.resources import get_resource_path

        result = get_resource_path("config", "default.toml")
        assert isinstance(result, Path)

    def test_get_resource_path_config(self):
        from app.resources import get_resource_path

        result = get_resource_path("config", "default.toml")
        assert result == PROJECT_ROOT / "config" / "default.toml"

    def test_get_resource_path_assets(self):
        from app.resources import get_resource_path

        result = get_resource_path("assets", "icon_menubar.png")
        assert result == PROJECT_ROOT / "assets" / "icon_menubar.png"

    def test_bundled_files_exist_in_dev(self):
        """Bundled config and assets exist at dev paths."""
        from app.resources import get_resource_path

        assert get_resource_path("config", "default.toml").exists()
        assert get_resource_path("config", "vocabulary.txt").exists()
        assert get_resource_path("assets", "icon_menubar.png").exists()

    def test_single_part(self):
        from app.resources import get_resource_path

        result = get_resource_path("README.md")
        assert result == PROJECT_ROOT / "README.md"


class TestBundleMode:
    """When sys._MEIPASS is set (PyInstaller), paths resolve relative to it."""

    def test_meipass_override(self, tmp_path):
        """Simulate PyInstaller bundle by setting sys._MEIPASS."""
        fake_meipass = tmp_path / "Yap_extracted"
        fake_meipass.mkdir(parents=True)

        import importlib
        import app.resources

        original = getattr(sys, "_MEIPASS", None)
        try:
            sys._MEIPASS = str(fake_meipass)
            importlib.reload(app.resources)

            result = app.resources.get_resource_path("config", "default.toml")
            assert result == fake_meipass / "config" / "default.toml"
        finally:
            if original is None:
                if hasattr(sys, "_MEIPASS"):
                    del sys._MEIPASS
            else:
                sys._MEIPASS = original
            importlib.reload(app.resources)
