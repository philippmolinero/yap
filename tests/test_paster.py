"""Tests for app.paster."""

from types import SimpleNamespace
from unittest import mock

import app.paster as paster


class _FakePasteboard:
    def __init__(self):
        self.contents = None

    def clearContents(self):
        self.contents = None

    def setString_forType_(self, text, paste_type):
        self.contents = (text, paste_type)


def test_paste_shows_alert_when_accessibility_is_missing(monkeypatch):
    pasteboard = _FakePasteboard()
    monkeypatch.setattr(
        paster,
        "AppKit",
        SimpleNamespace(
            NSPasteboard=SimpleNamespace(generalPasteboard=lambda: pasteboard),
            NSPasteboardTypeString="public.utf8-plain-text",
        ),
    )
    monkeypatch.setattr(paster, "_has_accessibility_permission", lambda: False)
    monkeypatch.setattr(paster, "_show_accessibility_alert_once", mock.Mock())
    monkeypatch.setattr(paster.time, "sleep", lambda *_: None)
    run = mock.Mock()
    monkeypatch.setattr(paster.subprocess, "run", run)

    paster.paste("hello", delay_ms=0)

    assert pasteboard.contents[0] == "hello"
    run.assert_not_called()
    paster._show_accessibility_alert_once.assert_called_once()


def test_paste_shows_alert_when_osascript_fails(monkeypatch):
    pasteboard = _FakePasteboard()
    monkeypatch.setattr(
        paster,
        "AppKit",
        SimpleNamespace(
            NSPasteboard=SimpleNamespace(generalPasteboard=lambda: pasteboard),
            NSPasteboardTypeString="public.utf8-plain-text",
        ),
    )
    monkeypatch.setattr(paster, "_has_accessibility_permission", lambda: True)
    monkeypatch.setattr(paster, "_show_accessibility_alert_once", mock.Mock())
    monkeypatch.setattr(paster.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        paster.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stderr="not allowed to send keystrokes",
        ),
    )

    paster.paste("hello", delay_ms=0)

    paster._show_accessibility_alert_once.assert_called_once()


def test_paste_succeeds_without_alert(monkeypatch):
    pasteboard = _FakePasteboard()
    monkeypatch.setattr(
        paster,
        "AppKit",
        SimpleNamespace(
            NSPasteboard=SimpleNamespace(generalPasteboard=lambda: pasteboard),
            NSPasteboardTypeString="public.utf8-plain-text",
        ),
    )
    monkeypatch.setattr(paster, "_has_accessibility_permission", lambda: True)
    monkeypatch.setattr(paster, "_show_accessibility_alert_once", mock.Mock())
    monkeypatch.setattr(paster.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        paster.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    paster.paste("hello", delay_ms=0)

    paster._show_accessibility_alert_once.assert_not_called()
