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


class TestHotkeyRecovery:
    def test_watchdog_forces_release_when_key_state_is_up(self, monkeypatch):
        on_stop = mock.Mock()
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=on_stop)
        monkeypatch.setattr(hotkeys.threading, "Thread", _InlineThread)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: False)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceFlagsState", lambda *_: 0)
        monkeypatch.setattr(mgr, "_schedule_release_watchdog", mock.Mock())

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        mgr._release_watchdog_tick()
        assert mgr._option_held is True
        assert mgr.forced_release_count == 0

        mgr._release_watchdog_tick()
        assert mgr._option_held is False
        assert mgr._active is False
        assert mgr.forced_release_count == 1
        on_stop.assert_called_once()

    def test_watchdog_keeps_hold_when_key_is_still_down(self, monkeypatch):
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=mock.Mock())
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceKeyState", lambda *_: True)
        monkeypatch.setattr(hotkeys.Quartz, "CGEventSourceFlagsState", lambda *_: 0)
        reschedule = mock.Mock()
        monkeypatch.setattr(mgr, "_schedule_release_watchdog", reschedule)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        mgr._release_watchdog_tick()

        assert mgr._option_held is True
        assert mgr._active is True
        assert mgr.forced_release_count == 0
        reschedule.assert_called_once()

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
        mgr = hotkeys.HotkeyManager(on_start=mock.Mock(), on_stop=on_stop)
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
        reschedule = mock.Mock()
        monkeypatch.setattr(mgr, "_schedule_release_watchdog", reschedule)

        mgr._active = True
        mgr._toggle_mode = False
        mgr._option_held = True

        mgr._release_watchdog_tick()

        assert mgr._option_held is True
        assert mgr._active is True
        assert mgr.forced_release_count == 0
        reschedule.assert_called_once()

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
