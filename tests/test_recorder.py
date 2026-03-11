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


def test_stop_can_use_abortive_path(monkeypatch):
    stream = _FakeStream()
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    recorder = recorder_module.Recorder()

    recorder.start()
    recorder.stop(abort=True)

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


def test_start_times_out_and_cleans_up_stream(monkeypatch):
    start_release = threading.Event()

    class _HungStartStream(_FakeStream):
        def start(self):
            start_release.wait(timeout=1.0)
            self.active = True

        def abort(self, ignore_errors=True):
            self.abort_calls += 1
            self.active = False
            start_release.set()

    stream = _HungStartStream()
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    monkeypatch.setattr(recorder_module, "_START_TIMEOUT_S", 0.01)
    monkeypatch.setattr(recorder_module, "_STOP_ABORT_DRAIN_TIMEOUT_S", 0.05)
    monkeypatch.setattr(recorder_module, "_CLOSE_TIMEOUT_S", 0.05)

    recorder = recorder_module.Recorder()

    with pytest.raises(RuntimeError, match="start timed out"):
        recorder.start()

    assert stream.abort_calls == 1
    assert stream.close_calls == 1
    assert recorder.is_recording is False


def test_stop_falls_back_to_abort_when_stream_stop_hangs(monkeypatch):
    stop_release = threading.Event()

    class _HungStopStream(_FakeStream):
        def stop(self, ignore_errors=True):
            self.stop_calls += 1
            stop_release.wait(timeout=1.0)
            self.active = False

        def abort(self, ignore_errors=True):
            self.abort_calls += 1
            self.active = False
            stop_release.set()

    stream = _HungStopStream()
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    monkeypatch.setattr(recorder_module, "_STOP_TIMEOUT_S", 0.01)
    monkeypatch.setattr(recorder_module, "_STOP_ABORT_DRAIN_TIMEOUT_S", 0.05)

    recorder = recorder_module.Recorder()
    recorder.start()

    assert recorder.stop() == b""
    assert stream.stop_calls == 1
    assert stream.abort_calls == 1
    assert stream.close_calls == 1


def test_stop_returns_when_stream_close_hangs(monkeypatch):
    close_release = threading.Event()

    class _HungCloseStream(_FakeStream):
        def close(self, ignore_errors=True):
            self.close_calls += 1
            close_release.wait(timeout=1.0)

    stream = _HungCloseStream()
    monkeypatch.setattr(recorder_module.sd, "InputStream", lambda **kwargs: stream)
    monkeypatch.setattr(recorder_module, "_CLOSE_TIMEOUT_S", 0.01)

    recorder = recorder_module.Recorder()
    unhealthy_reasons: list[str] = []
    recorder._on_backend_unhealthy = unhealthy_reasons.append
    recorder.start()

    stop_result: dict[str, bytes] = {}
    worker = threading.Thread(
        target=lambda: stop_result.setdefault("value", recorder.stop())
    )
    worker.start()
    worker.join(timeout=0.5)

    assert worker.is_alive() is False
    assert stop_result["value"] == b""
    assert stream.stop_calls == 1
    assert stream.close_calls == 1
    assert unhealthy_reasons == ["stream_teardown_timeout"]
