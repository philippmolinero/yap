"""Settings dialog for API key configuration (PyObjC NSWindow)."""

import logging
from typing import Callable

import AppKit
import objc

from app.config import SECRETS_FILE, load_config, save_secrets

logger = logging.getLogger(__name__)

_WINDOW_WIDTH = 420
_WINDOW_HEIGHT = 200
_FIELD_HEIGHT = 24
_LABEL_WIDTH = 120
_PADDING = 20
_BUTTON_WIDTH = 80
_BUTTON_HEIGHT = 32


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


class SettingsDialog:
    """Modal-ish settings window for API keys."""

    def __init__(self, on_save: Callable | None = None):
        self._on_save = on_save
        self._window = None
        self._mistral_field = None
        self._groq_field = None
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

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
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

        self._mistral_field = AppKit.NSSecureTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _PADDING + _LABEL_WIDTH + 8,
                y_pos,
                _WINDOW_WIDTH - _PADDING * 2 - _LABEL_WIDTH - 8,
                _FIELD_HEIGHT,
            )
        )
        self._mistral_field.setPlaceholderString_("sk-...")
        content.addSubview_(self._mistral_field)

        # --- Groq API Key ---
        y_pos -= _FIELD_HEIGHT + 16

        groq_label = AppKit.NSTextField.labelWithString_("Groq API Key:")
        groq_label.setFrame_(AppKit.NSMakeRect(_PADDING, y_pos, _LABEL_WIDTH, _FIELD_HEIGHT))
        groq_label.setAlignment_(AppKit.NSTextAlignmentRight)
        content.addSubview_(groq_label)

        self._groq_field = AppKit.NSSecureTextField.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _PADDING + _LABEL_WIDTH + 8,
                y_pos,
                _WINDOW_WIDTH - _PADDING * 2 - _LABEL_WIDTH - 8,
                _FIELD_HEIGHT,
            )
        )
        self._groq_field.setPlaceholderString_("gsk_...")
        content.addSubview_(self._groq_field)

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

        # Load existing keys (secrets.toml > env vars)
        cfg = load_config()
        if cfg.mistral_api_key:
            self._mistral_field.setStringValue_(cfg.mistral_api_key)
        if cfg.groq_api_key:
            self._groq_field.setStringValue_(cfg.groq_api_key)

        self._window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)

    def _do_cancel(self):
        try:
            self._window.close()
        except Exception:
            logger.exception("Error closing settings window")

    def _do_save(self):
        try:
            mistral_key = str(self._mistral_field.stringValue())
            groq_key = str(self._groq_field.stringValue())
            save_secrets(mistral_api_key=mistral_key, groq_api_key=groq_key)
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
