"""Tests for app.settings_dialog — settings UI construction."""

from pathlib import Path
from unittest import mock

import pytest


class TestSettingsDialogInit:
    """Test SettingsDialog construction (no GUI display)."""

    def test_creates_with_no_callback(self):
        from app.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        assert dialog._on_save is None
        assert dialog._window is None

    def test_creates_with_callback(self):
        from app.settings_dialog import SettingsDialog

        cb = mock.Mock()
        dialog = SettingsDialog(on_save=cb)
        assert dialog._on_save is cb

    def test_do_save_writes_secrets_and_shows_confirmation(self, tmp_path):
        """Simulate the save action without the full GUI."""
        secrets_file = tmp_path / "secrets.toml"
        config_dir = tmp_path / "yap"
        config_dir.mkdir()

        cb = mock.Mock()

        with mock.patch("app.settings_dialog.save_secrets") as mock_save, \
             mock.patch("app.settings_dialog.SECRETS_FILE", secrets_file), \
             mock.patch("app.settings_dialog.AppKit") as mock_appkit:
            from app.settings_dialog import SettingsDialog

            dialog = SettingsDialog(on_save=cb)

            # Simulate GUI fields and window
            mock_field_mistral = mock.Mock()
            mock_field_mistral.stringValue.return_value = "sk-test-123"
            mock_field_groq = mock.Mock()
            mock_field_groq.stringValue.return_value = "gsk-test-456"
            mock_cleanup_popup = mock.Mock()
            mock_cleanup_popup.titleOfSelectedItem.return_value = "Groq (Fast)"
            mock_window = mock.Mock()

            dialog._mistral_field = mock_field_mistral
            dialog._groq_field = mock_field_groq
            dialog._cleanup_popup = mock_cleanup_popup
            dialog._window = mock_window

            dialog._do_save()

        mock_save.assert_called_once_with(
            mistral_api_key="sk-test-123",
            groq_api_key="gsk-test-456",
            cleanup_provider="groq",
        )
        # Window title changes to "Saved!" as confirmation
        mock_window.setTitle_.assert_called_with("Saved!")

    def test_do_cancel_closes_window(self):
        from app.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        mock_window = mock.Mock()
        dialog._window = mock_window

        dialog._do_cancel()

        mock_window.close.assert_called_once()


class TestSettingsController:
    """Test _SettingsController delegates to dialog."""

    def test_controller_delegates_save(self):
        from app.settings_dialog import _SettingsController

        mock_dialog = mock.Mock()
        controller = _SettingsController.alloc().initWithDialog_(mock_dialog)

        controller.saveClicked_(None)
        mock_dialog._do_save.assert_called_once()

    def test_controller_delegates_cancel(self):
        from app.settings_dialog import _SettingsController

        mock_dialog = mock.Mock()
        controller = _SettingsController.alloc().initWithDialog_(mock_dialog)

        controller.cancelClicked_(None)
        mock_dialog._do_cancel.assert_called_once()
