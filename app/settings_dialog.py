"""Settings dialog for API key configuration (PyObjC NSWindow)."""

import logging
from typing import Callable

import AppKit
import objc

from app.config import SECRETS_FILE, load_config, save_secrets

logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 420
_WINDOW_HEIGHT = 240
_FIELD_HEIGHT = 24
_LABEL_WIDTH = 120
_PADDING = 20
_PASTE_BUTTON_WIDTH = 56
_BUTTON_WIDTH = 80
_BUTTON_HEIGHT = 32


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
    def pasteMistralClicked_(self, sender):
        try:
            self._dialog._paste_into_field(self._dialog._mistral_field)
        except Exception:
            logger.exception("Error in pasteMistralClicked_")

    @objc.IBAction
    def pasteGroqClicked_(self, sender):
        try:
            self._dialog._paste_into_field(self._dialog._groq_field)
        except Exception:
            logger.exception("Error in pasteGroqClicked_")


class SettingsDialog:
    """Modal-ish settings window for API keys."""

    def __init__(self, on_save: Callable | None = None):
        self._on_save = on_save
        self._window = None
        self._mistral_field = None
        self._groq_field = None
        self._cleanup_popup = None
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
        # Controller for button actions (must be NSObject)
        self._controller = _SettingsController.alloc().initWithDialog_(self)

        # Center on screen
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

        # --- Mistral API Key ---
        y_pos = content_height - _PADDING - _FIELD_HEIGHT - 10

        mistral_label = AppKit.NSTextField.labelWithString_("Mistral API Key:")
        mistral_label.setFrame_(AppKit.NSMakeRect(_PADDING, y_pos, _LABEL_WIDTH, _FIELD_HEIGHT))
        mistral_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(mistral_label)

        field_x = _PADDING + _LABEL_WIDTH + 8
        field_width = (
            _WINDOW_WIDTH - _PADDING * 2 - _LABEL_WIDTH - 8 - _PASTE_BUTTON_WIDTH - 8
        )
        paste_x = field_x + field_width + 8

        self._mistral_field = AppKit.NSSecureTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                field_x,
                y_pos,
                field_width,
                _FIELD_HEIGHT,
            )
        )
        self._mistral_field.setPlaceholderString_("sk-...")
        content.addSubview_(self._mistral_field)

        mistral_paste_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                paste_x,
                y_pos,
                _PASTE_BUTTON_WIDTH,
                _FIELD_HEIGHT,
            )
        )
        mistral_paste_btn.setTitle_("Paste")
        mistral_paste_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        mistral_paste_btn.setTarget_(self._controller)
        mistral_paste_btn.setAction_("pasteMistralClicked:")
        content.addSubview_(mistral_paste_btn)

        # --- Groq API Key ---
        y_pos -= _FIELD_HEIGHT + 16

        groq_label = AppKit.NSTextField.labelWithString_("Groq API Key:")
        groq_label.setFrame_(AppKit.NSMakeRect(_PADDING, y_pos, _LABEL_WIDTH, _FIELD_HEIGHT))
        groq_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(groq_label)

        self._groq_field = AppKit.NSSecureTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                field_x,
                y_pos,
                field_width,
                _FIELD_HEIGHT,
            )
        )
        self._groq_field.setPlaceholderString_("gsk_...")
        content.addSubview_(self._groq_field)

        groq_paste_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                paste_x,
                y_pos,
                _PASTE_BUTTON_WIDTH,
                _FIELD_HEIGHT,
            )
        )
        groq_paste_btn.setTitle_("Paste")
        groq_paste_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        groq_paste_btn.setTarget_(self._controller)
        groq_paste_btn.setAction_("pasteGroqClicked:")
        content.addSubview_(groq_paste_btn)

        # --- Cleanup Provider ---
        y_pos -= _FIELD_HEIGHT + 16

        cleanup_label = AppKit.NSTextField.labelWithString_("Cleanup:")
        cleanup_label.setFrame_(AppKit.NSMakeRect(_PADDING, y_pos, _LABEL_WIDTH, _FIELD_HEIGHT))
        cleanup_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(cleanup_label)

        self._cleanup_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            AppKit.NSMakeRect(
                _PADDING + _LABEL_WIDTH + 8,
                y_pos,
                180,
                _FIELD_HEIGHT,
            ),
            False,
        )
        self._cleanup_popup.addItemsWithTitles_(["Groq (Fast)", "Mistral", "Disabled"])
        content.addSubview_(self._cleanup_popup)

        # --- Buttons ---
        y_pos -= _BUTTON_HEIGHT + 24

        cancel_btn = AppKit.NSButton.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _WINDOW_WIDTH - _PADDING - _BUTTON_WIDTH * 2 - 12,
                y_pos,
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
                y_pos,
                _BUTTON_WIDTH,
                _BUTTON_HEIGHT,
            )
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
        save_btn.setKeyEquivalent_("\r")  # Enter key
        save_btn.setTarget_(self._controller)
        save_btn.setAction_("saveClicked:")
        content.addSubview_(save_btn)

        # Load existing config (secrets.toml > env vars)
        cfg = load_config()
        if cfg.mistral_api_key:
            self._mistral_field.setStringValue_(cfg.mistral_api_key)
        if cfg.groq_api_key:
            self._groq_field.setStringValue_(cfg.groq_api_key)

        # Pre-select cleanup dropdown
        if not cfg.cleanup.enabled:
            self._cleanup_popup.selectItemWithTitle_("Disabled")
        elif cfg.cleanup.provider == "mistral":
            self._cleanup_popup.selectItemWithTitle_("Mistral")
        else:
            self._cleanup_popup.selectItemWithTitle_("Groq (Fast)")

        self._window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self._window.makeFirstResponder_(self._mistral_field)

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
            mistral_key = str(self._mistral_field.stringValue())
            groq_key = str(self._groq_field.stringValue())

            # Map dropdown selection to provider string
            selection = str(self._cleanup_popup.titleOfSelectedItem())
            provider_map = {"Groq (Fast)": "groq", "Mistral": "mistral", "Disabled": "disabled"}
            cleanup_provider = provider_map.get(selection, "groq")

            save_secrets(mistral_api_key=mistral_key, groq_api_key=groq_key, cleanup_provider=cleanup_provider)
            logger.info("API keys saved to %s", SECRETS_FILE)

            # Brief visual confirmation before closing
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
