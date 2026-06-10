"""Clipboard + paste module: copy text and simulate Cmd+V in the active window."""

import ctypes
import logging
import subprocess
import threading
import time

import AppKit
import Quartz

logger = logging.getLogger(__name__)
_ACCESSIBILITY_ALERT_LOCK = threading.Lock()
_ACCESSIBILITY_ALERT_SHOWN = False
_V_KEYCODE = 9  # ANSI 'v'


def _show_accessibility_alert_once():
    global _ACCESSIBILITY_ALERT_SHOWN
    with _ACCESSIBILITY_ALERT_LOCK:
        if _ACCESSIBILITY_ALERT_SHOWN:
            return
        _ACCESSIBILITY_ALERT_SHOWN = True

    def show():
        try:
            alert = AppKit.NSAlert.alloc().init()
            alert.setMessageText_("Yap needs Accessibility permission to paste")
            alert.setInformativeText_(
                "Dictation was recorded and copied to the clipboard, but macOS blocked the Cmd+V keystroke.\n\n"
                "To fix:\n"
                "1. Open System Settings > Privacy & Security > Accessibility\n"
                "2. Find 'Yap' and turn it ON\n"
                "3. If it is already ON, turn it OFF and ON again"
            )
            alert.setAlertStyle_(AppKit.NSAlertStyleWarning)
            alert.addButtonWithTitle_("Open System Settings")
            alert.addButtonWithTitle_("OK")
            response = alert.runModal()
            if response == AppKit.NSAlertFirstButtonReturn:
                AppKit.NSWorkspace.sharedWorkspace().openURL_(
                    AppKit.NSURL.URLWithString_(
                        "x-apple.systempreferences:com.apple.preference.security"
                        "?Privacy_Accessibility"
                    )
                )
        except Exception:
            logger.exception("Failed to show Accessibility alert")

    AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(show)


_AX_TRUSTED_FN = None


def _load_ax_is_process_trusted():
    """Load AXIsProcessTrusted via ctypes.

    PyInstaller does not bundle the ApplicationServices PyObjC module, and
    Quartz's lazy import of AXIsProcessTrusted fails inside the app bundle —
    loading the system framework directly works in both dev and bundled mode.
    """
    lib = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    fn = lib.AXIsProcessTrusted
    fn.restype = ctypes.c_bool
    fn.argtypes = []
    return fn


def _has_accessibility_permission() -> bool | None:
    global _AX_TRUSTED_FN
    try:
        if _AX_TRUSTED_FN is None:
            _AX_TRUSTED_FN = _load_ax_is_process_trusted()
        return bool(_AX_TRUSTED_FN())
    except Exception:
        logger.exception("Accessibility trust check failed")
        return None


def _paste_via_cgevent() -> bool:
    """Post a synthetic Cmd+V via Quartz. Much faster than an osascript subprocess."""
    try:
        source = Quartz.CGEventSourceCreate(
            Quartz.kCGEventSourceStateCombinedSessionState
        )
        key_down = Quartz.CGEventCreateKeyboardEvent(source, _V_KEYCODE, True)
        key_up = Quartz.CGEventCreateKeyboardEvent(source, _V_KEYCODE, False)
        if key_down is None or key_up is None:
            return False
        Quartz.CGEventSetFlags(key_down, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventSetFlags(key_up, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, key_up)
        return True
    except Exception:
        logger.exception("CGEvent paste failed, falling back to osascript")
        return False


def paste(text: str, delay_ms: int = 50):
    """Set clipboard via NSPasteboard and trigger Cmd+V (CGEvent, osascript fallback).

    The Cmd+V keystroke may fail without Accessibility permission — in that
    case a warning is logged but we don't raise (the text is still on the clipboard).
    """
    # Set clipboard via NSPasteboard (avoids encoding issues with pbcopy)
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)

    # Brief delay to ensure clipboard is ready
    time.sleep(delay_ms / 1000.0)

    trusted = _has_accessibility_permission()
    if trusted is False:
        logger.warning("Accessibility permission missing — copied text but skipped Cmd+V")
        _show_accessibility_alert_once()
        return

    # Simulate Cmd+V natively — but only when Accessibility is confirmed:
    # without it macOS drops CGEvents silently, while osascript reports an
    # error we can surface. Unknown trust state therefore goes to osascript.
    if trusted is True and _paste_via_cgevent():
        return

    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "Cmd+V keystroke failed (Accessibility permission needed?): %s",
            result.stderr.strip(),
        )
        _show_accessibility_alert_once()


if __name__ == "__main__":
    print("Pasting test text in 2 seconds... switch to a text editor!")
    time.sleep(2)
    paste("Hello from Voxtral Dictation!")
    print("Done.")
