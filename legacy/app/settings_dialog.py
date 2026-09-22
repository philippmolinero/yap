"""Settings dialog for the Gemini API key (PyObjC NSWindow)."""

import logging
from typing import Callable

import AppKit
import objc

from app.config import SECRETS_FILE, _load_secrets, save_secrets

logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 420
_WINDOW_HEIGHT = 210
_FIELD_HEIGHT = 24
_LABEL_WIDTH = 120
_PADDING = 20
_PASTE_BUTTON_WIDTH = 56
_BUTTON_WIDTH = 80
_BUTTON_HEIGHT = 32
_NOTE = "Dictation uses Gemini Live. The transcript is already cleaned."


def _read_clipboard_text() -> str:
    """Return UTF-8 clipboard text or empty string."""
    try:
        pasteboard = AppKit.NSPasteboard.generalPasteboard()
        text = pasteboard.stringForType_(AppKit.NSPasteboardTypeString)
        if text:
            return str(text)
    except Exception:
        logger.exception("Failed to read clipboard text")
    return ""


class _SettingsWindow(AppKit.NSWindow):
    """Window subclass to make Cmd+V paste work reliably in text fields."""

    def performKeyEquivalent_(self, event):
        try:
            chars = str(event.charactersIgnoringModifiers() or "")
            flags = int(event.modifierFlags())
            command = bool(flags & AppKit.NSEventModifierFlagCommand)
            if command and chars.lower() == "v":
                responder = self.firstResponder()
                if responder is not None and responder.respondsToSelector_("paste:"):
                    AppKit.NSApp.sendAction_to_from_("paste:", responder, self)
                    return True
        except Exception:
            logger.exception("Error handling Cmd+V in settings window")
        return objc.super(_SettingsWindow, self).performKeyEquivalent_(event)


class _SettingsController(AppKit.NSObject):
    """NSObject subclass that receives button actions."""

    def initWithDialog_(self, dialog):
        self = objc.super(_SettingsController, self).init()
        if self is None:
            return None
        self._dialog = dialog
        return self

    @objc.IBAction
    def saveClicked_(self, sender):
        try:
            self._dialog._do_save()
        except Exception:
            logger.exception("Error in saveClicked_")

    @objc.IBAction
    def cancelClicked_(self, sender):
        try:
            self._dialog._do_cancel()
        except Exception:
            logger.exception("Error in cancelClicked_")

    @objc.IBAction
    def pasteGeminiClicked_(self, sender):
        try:
            self._dialog._paste_into_field(self._dialog._gemini_field)
        except Exception:
            logger.exception("Error in pasteGeminiClicked_")


class SettingsDialog:
    """Modal-ish settings window for the Gemini API key."""

    def __init__(self, on_save: Callable | None = None):
        self._on_save = on_save
        self._window = None
        self._gemini_field = None
        self._controller = None

    def show(self):
        """Show the settings window. Must be called on the main thread."""
        def _show():
            try:
                self._build_and_show()
            except Exception:
                logger.exception("Failed to show settings dialog")

        if AppKit.NSThread.isMainThread():
            _show()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_show)

    def _build_and_show(self):
        self._controller = _SettingsController.alloc().initWithDialog_(self)

        screen = AppKit.NSScreen.mainScreen().frame()
        x = (screen.size.width - _WINDOW_WIDTH) / 2
        y = (screen.size.height - _WINDOW_HEIGHT) / 2
        rect = AppKit.NSMakeRect(x, y, _WINDOW_WIDTH, _WINDOW_HEIGHT)

        self._window = _SettingsWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskTitled | AppKit.NSWindowStyleMaskClosable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("Yap Settings")
        self._window.setLevel_(AppKit.NSFloatingWindowLevel)

        content = self._window.contentView()
        content_height = _WINDOW_HEIGHT

        note = AppKit.NSTextField.wrappingLabelWithString_(_NOTE)
        note.setFrame_(AppKit.NSMakeRect(_PADDING, content_height - 58, _WINDOW_WIDTH - _PADDING * 2, 36))
        content.addSubview_(note)

        y_pos = content_height - 58 - _FIELD_HEIGHT - 12
        gemini_label = AppKit.NSTextField.labelWithString_("Gemini API Key:")
        gemini_label.setFrame_(AppKit.NSMakeRect(_PADDING, y_pos, _LABEL_WIDTH, _FIELD_HEIGHT))
        gemini_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(gemini_label)

        field_x = _PADDING + _LABEL_WIDTH + 8
        field_width = _WINDOW_WIDTH - _PADDING * 2 - _LABEL_WIDTH - 8 - _PASTE_BUTTON_WIDTH - 8
        paste_x = field_x + field_width + 8

        self._gemini_field = AppKit.NSSecureTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(field_x, y_pos, field_width, _FIELD_HEIGHT)
        )
        self._gemini_field.setPlaceholderString_("AIza...")
        content.addSubview_(self._gemini_field)

        paste_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(paste_x, y_pos, _PASTE_BUTTON_WIDTH, _FIELD_HEIGHT)
        )
        paste_btn.setTitle_("Paste")
        paste_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        paste_btn.setTarget_(self._controller)
        paste_btn.setAction_("pasteGeminiClicked:")
        content.addSubview_(paste_btn)

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _WINDOW_WIDTH - _PADDING - _BUTTON_WIDTH * 2 - 12,
                _PADDING,
                _BUTTON_WIDTH,
                _BUTTON_HEIGHT,
            )
        )
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        cancel_btn.setTarget_(self._controller)
        cancel_btn.setAction_("cancelClicked:")
        content.addSubview_(cancel_btn)

        save_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _WINDOW_WIDTH - _PADDING - _BUTTON_WIDTH,
                _PADDING,
                _BUTTON_WIDTH,
                _BUTTON_HEIGHT,
            )
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")
        save_btn.setTarget_(self._controller)
        save_btn.setAction_("saveClicked:")
        content.addSubview_(save_btn)

        keys, _preferences = _load_secrets()
        if keys.get("google"):
            self._gemini_field.setStringValue_(keys["google"])

        self._window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self._window.makeFirstResponder_(self._gemini_field)

    def _paste_into_field(self, field) -> bool:
        """Paste clipboard text into a given API key field."""
        text = _read_clipboard_text()
        if not text:
            logger.info("Paste requested but clipboard has no text")
            return False
        field.setStringValue_(text)
        self._window.makeFirstResponder_(field)
        return True

    def _do_cancel(self):
        try:
            self._window.close()
        except Exception:
            logger.exception("Error closing settings window")

    def _do_save(self):
        try:
            keys, preferences = _load_secrets()
            gemini_key = str(self._gemini_field.stringValue())
            save_secrets(
                mistral_api_key=keys.get("mistral", ""),
                groq_api_key=keys.get("groq", ""),
                cerebras_api_key=keys.get("cerebras", ""),
                gemini_api_key=gemini_key,
                cleanup_provider=preferences.get("cleanup_provider", ""),
                cleanup_model=preferences.get("cleanup_model", ""),
                transcription_provider="gemini",
            )
            logger.info("API keys saved to %s", SECRETS_FILE)

            self._window.setTitle_("Saved!")
            on_save = self._on_save
            window = self._window

            def _close_after_delay(_timer):
                try:
                    window.close()
                    if on_save:
                        on_save()
                except Exception:
                    logger.exception("Error in post-save callback")

            AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.6, False, _close_after_delay
            )
        except Exception:
            logger.exception("Error saving settings")
            self._window.setTitle_("Error saving!")
