"""Global hotkey monitoring via Quartz CGEventTap.

Monitors Right Option (keycode 61) for:
- Hold-to-talk: key_down -> on_start(), key_up -> on_stop()
- Double-tap toggle: two key_downs within 300ms -> enters toggle mode, next tap -> on_stop()

Requires Input Monitoring permission in System Settings > Privacy & Security.
"""

import logging
import threading
import time
from typing import Callable

import AppKit
import Quartz

logger = logging.getLogger(__name__)

# Right Option keycode
RIGHT_OPTION_KEYCODE = 61

# CGEvent types
_KEY_DOWN = Quartz.kCGEventKeyDown
_KEY_UP = Quartz.kCGEventKeyUp
_FLAGS_CHANGED = Quartz.kCGEventFlagsChanged

# Right Option flag mask
_RIGHT_OPTION_FLAG = Quartz.kCGEventFlagMaskAlternate


class HotkeyManager:
    """Monitors global key events for push-to-talk and double-tap toggle."""

    def __init__(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        keycode: int = RIGHT_OPTION_KEYCODE,
        double_tap_ms: int = 300,
    ):
        self.on_start = on_start
        self.on_stop = on_stop
        self.keycode = keycode
        self.double_tap_ms = double_tap_ms

        self._active = False  # Currently recording
        self._toggle_mode = False  # In toggle (hands-free) mode
        self._last_down_time = 0.0
        self._option_held = False
        self._thread: threading.Thread | None = None
        self._tap = None

    def _callback(self, proxy, event_type, event, refcon):
        """CGEventTap callback — runs on the CFRunLoop thread."""
        # macOS disables event taps that are slow to respond — re-enable
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            logger.warning("Event tap disabled by timeout — re-enabling")
            Quartz.CGEventTapEnable(self._tap, True)
            return event

        # We monitor flagsChanged for modifier keys like Option
        if event_type == _FLAGS_CHANGED:
            flags = Quartz.CGEventGetFlags(event)
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            )

            if keycode != self.keycode:
                return event

            option_down = bool(flags & _RIGHT_OPTION_FLAG)

            if option_down and not self._option_held:
                # Key pressed down
                self._option_held = True
                self._handle_down()
            elif not option_down and self._option_held:
                # Key released
                self._option_held = False
                self._handle_up()

        return event

    def _handle_down(self):
        now = time.time()
        elapsed_ms = (now - self._last_down_time) * 1000

        if self._active and self._toggle_mode:
            # In toggle mode — a new tap stops recording
            self._toggle_mode = False
            self._active = False
            logger.info("Toggle mode off — stopping")
            self.on_stop()
        elif not self._active and elapsed_ms < self.double_tap_ms:
            # Double-tap detected — enter toggle mode
            self._toggle_mode = True
            self._active = True
            logger.info("Double-tap — toggle mode on")
            self.on_start()
        elif not self._active:
            # Single press — hold-to-talk
            self._active = True
            self._toggle_mode = False
            logger.info("Hold-to-talk — recording")
            self.on_start()

        self._last_down_time = now

    def _handle_up(self):
        if self._active and not self._toggle_mode:
            # Release in hold-to-talk mode — stop
            self._active = False
            logger.info("Released — stopping")
            self.on_stop()
        # In toggle mode, release is ignored

    def _wait_for_input_monitoring(self) -> bool:
        """Request Input Monitoring permission and poll until granted."""
        if Quartz.CGPreflightListenEventAccess():
            return True

        logger.info("Requesting Input Monitoring permission...")
        Quartz.CGRequestListenEventAccess()
        self._show_permission_alert()

        # Poll every 2 seconds for up to 2 minutes
        for _ in range(60):
            time.sleep(2)
            if Quartz.CGPreflightListenEventAccess():
                logger.info("Input Monitoring permission granted")
                return True

        logger.error("Timed out waiting for Input Monitoring permission")
        return False

    def _run_loop(self):
        """Create event tap and run the CFRunLoop (blocking)."""
        if not self._wait_for_input_monitoring():
            return

        mask = Quartz.CGEventMaskBit(_FLAGS_CHANGED)

        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )

        if self._tap is None:
            logger.error("Failed to create event tap")
            self._show_permission_alert()
            return

        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(),
            run_loop_source,
            Quartz.kCFRunLoopDefaultMode,
        )
        Quartz.CGEventTapEnable(self._tap, True)

        logger.info("Hotkey manager started (keycode %d)", self.keycode)
        Quartz.CFRunLoopRun()

    def start(self):
        """Start monitoring in a daemon thread."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def reset(self):
        """Reset internal state (e.g. after an external stop like silence detection)."""
        self._active = False
        self._toggle_mode = False
        self._option_held = False

    def _show_permission_alert(self):
        """Show a user-visible alert when Input Monitoring permission is missing."""
        def show():
            try:
                alert = AppKit.NSAlert.alloc().init()
                alert.setMessageText_("Yap needs Input Monitoring permission")
                alert.setInformativeText_(
                    "Hotkey detection requires Input Monitoring access.\n\n"
                    "To fix:\n"
                    "1. Open System Settings > Privacy & Security > Input Monitoring\n"
                    "2. Find 'Yap' and toggle it ON\n"
                    "3. If already ON, toggle it OFF then ON again\n\n"
                    "Yap will activate automatically once permission is granted."
                )
                alert.setAlertStyle_(AppKit.NSAlertStyleWarning)
                alert.addButtonWithTitle_("Open System Settings")
                alert.addButtonWithTitle_("OK")
                response = alert.runModal()
                if response == AppKit.NSAlertFirstButtonReturn:
                    AppKit.NSWorkspace.sharedWorkspace().openURL_(
                        AppKit.NSURL.URLWithString_(
                            "x-apple.systempreferences:com.apple.preference.security"
                            "?Privacy_ListenEvent"
                        )
                    )
            except Exception:
                logger.exception("Failed to show permission alert")
        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(show)

    def stop(self):
        """Stop the event tap and run loop."""
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Hotkey test — press Right Option to start/stop.")
    print("Hold = push-to-talk, double-tap = toggle mode.")
    print("Ctrl+C to quit.\n")

    mgr = HotkeyManager(
        on_start=lambda: print(">>> START"),
        on_stop=lambda: print("<<< STOP"),
    )
    mgr.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mgr.stop()
        print("\nDone.")
