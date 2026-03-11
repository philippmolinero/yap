"""Tests for app.pipeline request ordering and cancellation."""

import threading
import time
from types import SimpleNamespace

import app.pipeline as pipeline_module
from app.cleanup import NoopCleanup


class _FakeRecorder:
    def __init__(self, wav_bytes: bytes = b"wav-bytes"):
        self.wav_bytes = wav_bytes
        self.start_calls = 0
        self.stop_calls = 0
        self.stop_abort_args: list[bool] = []
        self.force_stop_calls = 0
        self._is_recording = False
        self.start_entered: threading.Event | None = None
        self.allow_start: threading.Event | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def start(self):
        self.start_calls += 1
        if self.start_entered is not None:
            self.start_entered.set()
        if self.allow_start is not None:
            assert self.allow_start.wait(timeout=1.0)
        self._is_recording = True

    def stop(self, *, abort: bool = False) -> bytes:
        self.stop_calls += 1
        self.stop_abort_args.append(abort)
        self._is_recording = False
        return self.wav_bytes

    def force_stop(self) -> bool:
        self.force_stop_calls += 1
        self._is_recording = False
        return True


class _FakeTranscriber:
    def __init__(
        self,
        text: str = "hello world",
        entered: threading.Event | None = None,
        allow_finish: threading.Event | None = None,
    ):
        self.text = text
        self.entered = entered
        self.allow_finish = allow_finish

    def transcribe(self, wav_bytes: bytes):
        if self.entered is not None:
            self.entered.set()
        if self.allow_finish is not None:
            assert self.allow_finish.wait(timeout=1.0)
        return SimpleNamespace(text=self.text, language="en", latency=0.01)


def _build_pipeline(recorder, transcriber, states, monkeypatch):
    pasted: list[str] = []
    monkeypatch.setattr(pipeline_module, "paste", lambda text, delay_ms=0: pasted.append(text))
    pipeline = pipeline_module.Pipeline(
        recorder=recorder,
        transcriber=transcriber,
        cleanup=NoopCleanup(),
        paste_delay_ms=0,
        on_state_change=states.append,
    )
    return pipeline, pasted


def test_pipeline_serializes_overlapping_start_and_stop(monkeypatch):
    start_entered = threading.Event()
    allow_start = threading.Event()
    recorder = _FakeRecorder()
    recorder.start_entered = start_entered
    recorder.allow_start = allow_start
    states: list[pipeline_module.PipelineState] = []
    pipeline, pasted = _build_pipeline(recorder, _FakeTranscriber(), states, monkeypatch)

    start_thread = threading.Thread(
        target=pipeline.start_recording,
        kwargs={"source": "hotkey_down"},
    )
    stop_thread = threading.Thread(
        target=pipeline.stop_recording_and_process,
        kwargs={"source": "hotkey_up"},
    )

    start_thread.start()
    assert start_entered.wait(timeout=1.0)
    stop_thread.start()

    time.sleep(0.05)
    assert recorder.stop_calls == 0

    allow_start.set()
    start_thread.join(timeout=1.0)
    stop_thread.join(timeout=1.0)

    assert pipeline.state == pipeline_module.PipelineState.IDLE
    assert recorder.start_calls == 1
    assert recorder.stop_calls == 1
    assert recorder.stop_abort_args == [False]
    assert states == [
        pipeline_module.PipelineState.RECORDING,
        pipeline_module.PipelineState.PROCESSING,
        pipeline_module.PipelineState.IDLE,
    ]
    assert pasted == ["hello world"]


def test_pipeline_ignores_new_start_while_processing(monkeypatch):
    transcribe_entered = threading.Event()
    allow_finish = threading.Event()
    recorder = _FakeRecorder()
    states: list[pipeline_module.PipelineState] = []
    pipeline, _ = _build_pipeline(
        recorder,
        _FakeTranscriber(entered=transcribe_entered, allow_finish=allow_finish),
        states,
        monkeypatch,
    )

    assert pipeline.start_recording(source="hotkey_down") is True

    worker = threading.Thread(
        target=pipeline.stop_recording_and_process,
        kwargs={"source": "hotkey_up"},
    )
    worker.start()

    assert transcribe_entered.wait(timeout=1.0)
    assert pipeline.state == pipeline_module.PipelineState.PROCESSING
    assert pipeline.start_recording(source="hotkey_down") is False
    assert recorder.start_calls == 1

    allow_finish.set()
    worker.join(timeout=1.0)

    assert pipeline.state == pipeline_module.PipelineState.IDLE
    assert states == [
        pipeline_module.PipelineState.RECORDING,
        pipeline_module.PipelineState.PROCESSING,
        pipeline_module.PipelineState.IDLE,
    ]


def test_cancel_recording_aborts_active_recorder(monkeypatch):
    recorder = _FakeRecorder()
    states: list[pipeline_module.PipelineState] = []
    pipeline, _ = _build_pipeline(recorder, _FakeTranscriber(), states, monkeypatch)

    assert pipeline.start_recording(source="hotkey_down") is True
    assert pipeline.cancel_recording(source="menu_stop") is True

    assert recorder.force_stop_calls == 1
    assert pipeline.state == pipeline_module.PipelineState.IDLE
    assert states == [
        pipeline_module.PipelineState.RECORDING,
        pipeline_module.PipelineState.IDLE,
    ]


def test_start_failure_leaves_pipeline_idle(monkeypatch):
    class _FailingRecorder(_FakeRecorder):
        def start(self):
            self.start_calls += 1
            raise RuntimeError("boom")

    recorder = _FailingRecorder()
    pipeline, _ = _build_pipeline(recorder, _FakeTranscriber(), [], monkeypatch)

    assert pipeline.start_recording(source="hotkey_down") is False
    assert pipeline.state == pipeline_module.PipelineState.IDLE
    assert recorder.start_calls == 1


def test_silence_auto_stop_uses_abortive_recorder_stop(monkeypatch):
    recorder = _FakeRecorder()
    states: list[pipeline_module.PipelineState] = []
    pipeline, pasted = _build_pipeline(recorder, _FakeTranscriber(), states, monkeypatch)

    assert pipeline.start_recording(source="hotkey_down") is True
    assert (
        pipeline.stop_recording_and_process(
            source="silence",
            abort_recording_stop=True,
        )
        is True
    )

    assert recorder.stop_calls == 1
    assert recorder.stop_abort_args == [True]
    assert pipeline.state == pipeline_module.PipelineState.IDLE
    assert states == [
        pipeline_module.PipelineState.RECORDING,
        pipeline_module.PipelineState.PROCESSING,
        pipeline_module.PipelineState.IDLE,
    ]
    assert pasted == ["hello world"]
