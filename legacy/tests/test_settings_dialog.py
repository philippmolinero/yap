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

    def test_do_save_writes_gemini_and_keeps_other_keys(self, tmp_path):
        """Simulate the save action without the full GUI."""
        secrets_file = tmp_path / "secrets.toml"
        cb = mock.Mock()
        stored = (
            {
                "mistral": "sk-test-123",
                "groq": "gsk-test-456",
                "cerebras": "csk-test-789",
                "google": "AIza-old",
            },
            {"cleanup_provider": "cerebras", "cleanup_model": "gpt-oss-120b"},
        )

        with mock.patch("app.settings_dialog.save_secrets") as mock_save, \
             mock.patch("app.settings_dialog._load_secrets", return_value=stored), \
             mock.patch("app.settings_dialog.SECRETS_FILE", secrets_file), \
             mock.patch("app.settings_dialog.AppKit"):
            from app.settings_dialog import SettingsDialog

            dialog = SettingsDialog(on_save=cb)
            dialog._gemini_field = mock.Mock()
            dialog._gemini_field.stringValue.return_value = "AIza-test"
            dialog._window = mock.Mock()

            dialog._do_save()

        mock_save.assert_called_once_with(
            mistral_api_key="sk-test-123",
            groq_api_key="gsk-test-456",
            cerebras_api_key="csk-test-789",
            gemini_api_key="AIza-test",
            cleanup_provider="cerebras",
            cleanup_model="gpt-oss-120b",
            transcription_provider="gemini",
        )
        dialog._window.setTitle_.assert_called_with("Saved!")

    def test_do_cancel_closes_window(self):
        from app.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        mock_window = mock.Mock()
        dialog._window = mock_window

        dialog._do_cancel()

        mock_window.close.assert_called_once()

    def test_paste_into_field_sets_value_and_focus(self):
        from app.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        field = mock.Mock()
        window = mock.Mock()
        dialog._window = window

        with mock.patch("app.settings_dialog._read_clipboard_text", return_value="sk-pasted"):
            ok = dialog._paste_into_field(field)

        assert ok is True
        field.setStringValue_.assert_called_once_with("sk-pasted")
        window.makeFirstResponder_.assert_called_once_with(field)

    def test_paste_into_field_returns_false_on_empty_clipboard(self):
        from app.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        field = mock.Mock()
        window = mock.Mock()
        dialog._window = window

        with mock.patch("app.settings_dialog._read_clipboard_text", return_value=""):
            ok = dialog._paste_into_field(field)

        assert ok is False
        field.setStringValue_.assert_not_called()
        window.makeFirstResponder_.assert_not_called()


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

    def test_controller_delegates_gemini_paste(self):
        from app.settings_dialog import _SettingsController

        mock_dialog = mock.Mock()
        mock_dialog._gemini_field = mock.Mock()
        controller = _SettingsController.alloc().initWithDialog_(mock_dialog)

        controller.pasteGeminiClicked_(None)
        mock_dialog._paste_into_field.assert_called_once_with(mock_dialog._gemini_field)
