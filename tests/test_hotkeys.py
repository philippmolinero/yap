"""Tests for app.hotkeys stuck-hold recovery paths."""

from unittest import mock

import app.hotkeys as hotkeys


class _InlineThread:
    """Test helper: run thread targets synchronously."""

    def __init__(self, target, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._daemon = daemon

    def start(self):
        self._target(*self._args, **self._kwargs)


class _FakeWaitEvent:
    def __init__(self, results):
        self._results = list(results)

    def wait(self, timeout):
        if self._results:
            return self._results.pop(0)
        return False

    def set(self):
        return None

    def clear(self):
        return None


class TestHotkeyRecovery:
    def test_watchdog_forces_release_when_key_state_is_up(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=on_stop)
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: False)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceFlagsState", lambda *_: 0)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        assert mgr._release_watchdog_tick() is False
        assert mgr._option_held is True
        assert mgr.forced_release_count == 0

        assert mgr._release_watchdog_tick() is True
        assert mgr._option_held is False
        assert mgr._active is False
        assert mgr.forced_release_count == 1
        on_stop.assert_called_once()

    def test_watchdog_keeps_hold_when_key_is_still_down(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: True)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceFlagsState", lambda *_: 0)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        assert mgr._release_watchdog_tick() is False

        assert mgr._option_held is True
        assert mgr._active is True
        assert mgr.forced_release_count == 0

    def test_timeout_event_forces_release_before_reenable(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=on_stop)
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: False)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceFlagsState", lambda *_: 0)
        tap_enable = mock.Mock()
        monkeypatch.setattr(hotkeys.Quartz, "CGEventTapEnable", tap_enable)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True
        mgr._tap = object()
        event = object()

        returned = mgr._callback(
            proxy=None,
            event_type=hotkeys.Quartz.kCGEventTapDisabledByTimeout,
            event=event,
            refcon=None,
        )

        assert returned is event
        assert mgr._option_held is False
        assert mgr._active is False
        assert mgr.forced_release_count == 1
        on_stop.assert_called_once()
        tap_enable.assert_called_once_with(mgr._tap, True)

    def test_key_up_event_releases_even_without_flags_changed(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(
            on_start=mock.Mock(),
            on_stop=on_stop,
            keycode=hotkeys.RIGHT_OPTION_KEYCODE,
        )
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetIntegerValueField",
            lambda *_: hotkeys.RIGHT_OPTION_KEYCODE,
        )

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        mgr._callback(
            proxy=None,
            event_type=hotkeys._KEY_UP,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is False
        assert mgr._active is False
        on_stop.assert_called_once()

    def test_watchdog_keeps_hold_when_flags_report_down(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: False)
        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventSourceFlagsState",
            lambda *_: hotkeys._RIGHT_OPTION_FLAG,
        )

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        assert mgr._release_watchdog_tick() is False

        assert mgr._option_held is True
        assert mgr._active is True
        assert mgr.forced_release_count == 0

    def test_right_control_flags_changed_starts_and_stops(self, monkeypatch):
        on_start = mock.Mock()
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(
            on_start=on_start,
            on_stop=on_stop,
            keycode=hotkeys.RIGHT_CONTROL_KEYCODE,
        )
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(mgr, "_schedule_release_watchdog", mock.Mock())
        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetIntegerValueField",
            lambda *_: hotkeys.RIGHT_CONTROL_KEYCODE,
        )

        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetFlags",
            lambda *_: hotkeys.Quartz.kCGEventFlagMaskControl,
        )
        mgr._callback(
            proxy=None,
            event_type=hotkeys._FLAGS_CHANGED,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is True
        assert mgr._active is True
        on_start.assert_called_once()

        monkeypatch.setattr(hotkeys.Quartz, "CGEventGetFlags", lambda *_: 0)
        mgr._callback(
            proxy=None,
            event_type=hotkeys._FLAGS_CHANGED,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is False
        assert mgr._active is False
        on_stop.assert_called_once()

    def test_multiple_modifier_keycodes_can_trigger(self, monkeypatch):
        on_start = mock.Mock()
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(
            on_start=on_start,
            on_stop=on_stop,
            keycode=hotkeys.RIGHT_CONTROL_KEYCODE,
            keycodes=[hotkeys.RIGHT_OPTION_KEYCODE, hotkeys.RIGHT_CONTROL_KEYCODE],
        )
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(mgr, "_schedule_release_watchdog", mock.Mock())
        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetIntegerValueField",
            lambda *_: hotkeys.RIGHT_OPTION_KEYCODE,
        )

        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetFlags",
            lambda *_: hotkeys.Quartz.kCGEventFlagMaskAlternate,
        )
        mgr._callback(
            proxy=None,
            event_type=hotkeys._FLAGS_CHANGED,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is True
        assert mgr._held_keycode == hotkeys.RIGHT_OPTION_KEYCODE
        assert mgr._active is True
        on_start.assert_called_once()

        monkeypatch.setattr(hotkeys.Quartz, "CGEventGetFlags", lambda *_: 0)
        mgr._callback(
            proxy=None,
            event_type=hotkeys._FLAGS_CHANGED,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is False
        assert mgr._held_keycode is None
        assert mgr._active is False
        on_stop.assert_called_once()

    def test_other_configured_modifier_does_not_release_active_key(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(
            on_start=mock.Mock(),
            on_stop=on_stop,
            keycode=hotkeys.RIGHT_CONTROL_KEYCODE,
            keycodes=[hotkeys.RIGHT_OPTION_KEYCODE, hotkeys.RIGHT_CONTROL_KEYCODE],
        )
        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGEventGetIntegerValueField",
            lambda *_: hotkeys.RIGHT_OPTION_KEYCODE,
        )
        monkeypatch.setattr(hotkeys.Quartz, "CGEventGetFlags", lambda *_: 0)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True
        mgr._held_keycode = hotkeys.RIGHT_CONTROL_KEYCODE

        mgr._callback(
            proxy=None,
            event_type=hotkeys._FLAGS_CHANGED,
            event=object(),
            refcon=None,
        )

        assert mgr._option_held is True
        assert mgr._held_keycode == hotkeys.RIGHT_CONTROL_KEYCODE
        assert mgr._active is True
        on_stop.assert_not_called()

    def test_normal_release_path_does_not_increment_forced_counter(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=on_stop)
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        mgr._release_if_needed()

        assert mgr._option_held is False
        assert mgr._active is False
        assert mgr.forced_release_count == 0
        on_stop.assert_called_once()

    def test_wait_for_input_monitoring_keeps_polling_until_granted(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())
        preflight_results = iter([False, False, True])

        monkeypatch.setattr(
            hotkeys.Quartz,
            "CGPreflightListenEventAccess",
            lambda: next(preflight_results),
        )
        request = mock.Mock()
        monkeypatch.setattr(hotkeys.Quartz, "CGRequestListenEventAccess", request)
        monkeypatch.setattr(mgr, "_show_permission_alert_once", mock.Mock())
        mgr._stop_event = _FakeWaitEvent([False, False])

        assert mgr._wait_for_input_monitoring() is True
        request.assert_called_once()
        mgr._show_permission_alert_once.assert_called_once()

    def test_wait_for_input_monitoring_exits_when_stopped(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())

        monkeypatch.setattr(hotkeys.Quartz, "CGPreflightListenEventAccess", lambda: False)
        request = mock.Mock()
        monkeypatch.setattr(hotkeys.Quartz, "CGRequestListenEventAccess", request)
        monkeypatch.setattr(mgr, "_show_permission_alert_once", mock.Mock())
        mgr._stop_event = _FakeWaitEvent([True])

        assert mgr._wait_for_input_monitoring() is False
        request.assert_called_once()
        mgr._show_permission_alert_once.assert_called_once()

    def test_start_ignores_duplicate_running_thread(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())
        mgr._thread = mock.Mock(is_alive=mock.Mock(return_value=True))
        thread_ctor = mock.Mock()
        monkeypatch.setattr(hotkeys.threading, "Thread", thread_ctor)

        assert mgr.start() is False
        thread_ctor.assert_not_called()
