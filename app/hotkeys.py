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
_RELEASE_WATCHDOG_INTERVAL_S = 0.2
_RELEASE_MISS_TICKS_REQUIRED = 2
_INPUT_MONITORING_POLL_INTERVAL_S = 1.0

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
        self._thread_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._tap = None
        self._cf_run_loop = None  # CFRunLoop reference for clean shutdown
        self._release_watchdog_thread: threading.Thread | None = None
        self._release_watchdog_token = 0
        self._forced_release_count = 0
        self._release_miss_ticks = 0
        self._permission_alert_lock = threading.Lock()
        self._permission_alert_shown = False

    @property
    def forced_release_count(self) -> int:
        return self._forced_release_count

    def _cancel_release_watchdog(self):
        self._release_watchdog_token += 1
        self._release_watchdog_thread = None

    def _schedule_release_watchdog(self):
        self._release_watchdog_token += 1
        token = self._release_watchdog_token

        def _run():
            try:
                while True:
                    time.sleep(_RELEASE_WATCHDOG_INTERVAL_S)
                    if token != self._release_watchdog_token:
                        return
                    if self._release_watchdog_tick():
                        return
            except Exception:
                logger.exception("Release watchdog loop failed")

        thread = threading.Thread(target=_run, daemon=True)
        self._release_watchdog_thread = thread
        thread.start()

    def _release_watchdog_tick(self) -> bool:
        if not self._option_held:
            return True

        if self._is_key_physically_down():
            self._release_miss_ticks = 0
            return False

        self._release_miss_ticks += 1
        if self._release_miss_ticks < _RELEASE_MISS_TICKS_REQUIRED:
            return False

        if not self._is_key_physically_down():
            self._record_forced_release("watchdog")
            self._release_if_needed()
            return True

        self._release_miss_ticks = 0
        return False

    def _is_key_physically_down(self) -> bool:
        key_down = False
        flags_down = False
        key_check_ok = False
        flags_check_ok = False

        try:
            key_down = bool(
                Quartz.CGEventSourceKeyState(
                    Quartz.kCGEventSourceStateCombinedSessionState,
                    self.keycode,
                )
            )
            key_check_ok = True
        except Exception:
            logger.exception("Release watchdog key state check failed")

        try:
            flags = Quartz.CGEventSourceFlagsState(
                Quartz.kCGEventSourceStateCombinedSessionState
            )
            flags_down = bool(flags & _RIGHT_OPTION_FLAG)
            flags_check_ok = True
        except Exception:
            logger.exception("Release watchdog flags check failed")

        # Modifier key reporting can differ by macOS version/hardware. Treat
        # either signal as "still down" to avoid false forced releases.
        if key_down or flags_down:
            return True
        # If both checks failed due exceptions, fail open (assume down).
        if not key_check_ok and not flags_check_ok:
            return True
        return False

    def _release_if_needed(self):
        if not self._option_held:
            return
        self._option_held = False
        self._release_miss_ticks = 0
        self._cancel_release_watchdog()
        self._handle_up()

    def _record_forced_release(self, reason: str):
        self._forced_release_count += 1
        logger.warning(
            "Forced hotkey release (%s) [count=%d]",
            reason,
            self._forced_release_count,
        )

    def _callback(self, proxy, event_type, event, refcon):
        """CGEventTap callback — runs on the CFRunLoop thread."""
        # macOS disables event taps that are slow to respond — re-enable
        if event_type == Quartz.kCGEventTapDisabledByTimeout:
            logger.warning("Event tap disabled by timeout — re-enabling")
            if self._option_held and not self._is_key_physically_down():
                self._record_forced_release("event_tap_timeout")
                self._release_if_needed()
            if self._tap is not None:
                Quartz.CGEventTapEnable(self._tap, True)
            return event

        if event_type in (_KEY_DOWN, _KEY_UP):
            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode
            )
            if keycode != self.keycode:
                return event
            if event_type == _KEY_DOWN and not self._option_held:
                self._option_held = True
                self._handle_down()
            elif event_type == _KEY_UP and self._option_held:
                self._release_if_needed()
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
                self._release_if_needed()

        return event

    def _handle_down(self):
        now = time.time()
        elapsed_ms = (now - self._last_down_time) * 1000
        self._release_miss_ticks = 0

        if self._active and self._toggle_mode:
            # In toggle mode — a new tap stops recording
            self._toggle_mode = False
            self._active = False
            logger.info("Toggle mode off — stopping")
            threading.Thread(target=self.on_stop, daemon=True).start()
        elif not self._active and elapsed_ms < self.double_tap_ms:
            # Double-tap detected — enter toggle mode
            self._toggle_mode = True
            self._active = True
            logger.info("Double-tap — toggle mode on")
            threading.Thread(target=self.on_start, daemon=True).start()
        elif not self._active:
            # Single press — hold-to-talk
            self._active = True
            self._toggle_mode = False
            logger.info("Hold-to-talk — recording")
            threading.Thread(target=self.on_start, daemon=True).start()

        self._schedule_release_watchdog()
        self._last_down_time = now

    def _handle_up(self):
        self._cancel_release_watchdog()
        if self._active and not self._toggle_mode:
            # Release in hold-to-talk mode — stop
            self._active = False
            logger.info("Released — stopping")
            threading.Thread(target=self.on_stop, daemon=True).start()
        # In toggle mode, release is ignored

    def _wait_for_input_monitoring(self) -> bool:
        """Request Input Monitoring permission and poll until granted or stopped."""
        if Quartz.CGPreflightListenEventAccess():
            return True

        logger.warning("Input Monitoring permission missing — waiting for grant")
        Quartz.CGRequestListenEventAccess()
        self._show_permission_alert_once()

        while not self._stop_event.wait(_INPUT_MONITORING_POLL_INTERVAL_S):
            if Quartz.CGPreflightListenEventAccess():
                logger.info("Input Monitoring permission granted")
                return True

        logger.info("Stopped while waiting for Input Monitoring permission")
        return False

    def _run_loop(self):
        """Create event tap and run the CFRunLoop (blocking)."""
        if not self._wait_for_input_monitoring():
            return

        mask = (
            Quartz.CGEventMaskBit(_FLAGS_CHANGED)
            | Quartz.CGEventMaskBit(_KEY_DOWN)
            | Quartz.CGEventMaskBit(_KEY_UP)
        )

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
        self._cf_run_loop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(
            self._cf_run_loop,
            run_loop_source,
            Quartz.kCFRunLoopDefaultMode,
        )
        Quartz.CGEventTapEnable(self._tap, True)

        logger.info("Hotkey manager started (keycode %d)", self.keycode)
        Quartz.CFRunLoopRun()
        logger.info("Hotkey manager CFRunLoop exited")

    def start(self):
        """Start monitoring in a daemon thread."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                logger.info("Hotkey manager start ignored — already running")
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            return True

    def reset(self):
        """Reset internal state (e.g. after an external stop like silence detection)."""
        self._cancel_release_watchdog()
        self._release_miss_ticks = 0
        self._active = False
        self._toggle_mode = False
        self._option_held = False

    def _show_permission_alert_once(self):
        """Show a user-visible alert when Input Monitoring permission is missing."""
        with self._permission_alert_lock:
            if self._permission_alert_shown:
                return
            self._permission_alert_shown = True

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
                    "Yap will activate automatically after permission is granted. No restart is required."
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
        """Stop the event tap, CFRunLoop, and thread cleanly."""
        logger.info("Hotkey manager stopping")
        self._stop_event.set()
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None
        if self._cf_run_loop is not None:
            Quartz.CFRunLoopStop(self._cf_run_loop)
            self._cf_run_loop = None
        with self._thread_lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
            if thread.is_alive():
                logger.warning("Hotkey thread did not exit within timeout")
            with self._thread_lock:
                if self._thread is thread:
                    self._thread = None
        self.reset()
        logger.info("Hotkey manager stopped")

    def restart(self):
        """Stop and restart the event tap (e.g. after sleep/wake)."""
        logger.info("Hotkey manager restarting")
        self.stop()
        self.start()


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
