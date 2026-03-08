"""Tests for app.recorder stream lifecycle hardening."""

import threading
import time

import pytest

import app.recorder as recorder_module


class _FakeStream:
    def __init__(
        self,
        start_entered: threading.Event | None = None,
        allow_start: threading.Event | None = None,
        stop_called: threading.Event | None = None,
        *,
        fail_start: bool = False,
    ):
        self.active = False
        self.start_entered = start_entered
        self.allow_start = allow_start
        self.stop_called = stop_called
        self.fail_start = fail_start
        self.stop_calls = 0
        self.abort_calls = 0
        self.close_calls = 0

    def start(self):
        if self.start_entered is not None:
            self.start_entered.set()
        if self.allow_start is not None:
            assert self.allow_start.wait(timeout=1.0)
        if self.fail_start:
            raise RuntimeError("failed to start")
        self.active = True

    def stop(self, ignore_errors=True):
        self.stop_calls += 1
        self.active = False
        if self.stop_called is not None:
            self.stop_called.set()

    def abort(self, ignore_errors=True):
        self.abort_calls += 1
        self.active = False

    def close(self, ignore_errors=True):
        self.close_calls += 1


def test_start_and_stop_are_serialized(monkeypatch):
    start_entered = threading.Event()
    allow_start = threading.Event()
    stop_called = threading.Event()
    streams: list[_FakeStream] = []

    def make_stream(**kwargs):
        stream = _FakeStream(
            start_entered=start_entered,
            allow_start=allow_start,
            stop_called=stop_called,
        )
        streams.append(stream)
        return stream

    monkeypatch.setattr(recorder_module.sd, "InputStream", make_stream)
    recorder = recorder_module.Recorder()
    errors: list[Exception] = []

    def run_start():
        try:
            recorder.start()
        except Exception as exc:  # pragma: no cover - should remain empty
            errors.append(exc)

    start_thread = threading.Thread(target=run_start)
    start_thread.start()
    assert start_entered.wait(timeout=1.0)

    stop_result: dict[str, bytes] = {}
    stop_thread = threading.Thread(
        target=lambda: stop_result.setdefault("value", recorder.stop())
    )
    stop_thread.start()

    time.sleep(0.05)
    assert not stop_called.is_set()

    allow_start.set()
    start_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)

    assert errors == []
    assert stop_called.is_set()
    assert stop_result["value"] == b""
    assert streams[0].stop_calls == 1
    assert streams[0].close_calls == 1


def test_force_stop_aborts_active_stream(monkeypatch):
    stream = _FakeStream()
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    recorder = recorder_module.Recorder()

    recorder.start()
    assert recorder.is_recording is True
    assert recorder.force_stop() is True

    assert stream.abort_calls == 1
    assert stream.stop_calls == 0
    assert stream.close_calls == 1
    assert recorder.is_recording is False


def test_start_failure_cleans_up_stream(monkeypatch):
    stream = _FakeStream(fail_start=True)
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    recorder = recorder_module.Recorder()

    with pytest.raises(RuntimeError, match="failed to start"):
        recorder.start()

    assert stream.abort_calls == 1
    assert stream.close_calls == 1
    assert recorder.is_recording is False
