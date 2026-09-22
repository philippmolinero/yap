"""Tests for the Thai practice capture seam."""

from dataclasses import dataclass

from app.thai_practice import (
    ThaiPracticeCapture,
    ThaiPracticePrompt,
    ThaiPracticeState,
)


@dataclass
class _FakeRecorder:
    wav_bytes: bytes = b"thai-wav"

    def __post_init__(self):
        self.start_calls = 0
        self.stop_calls = 0
        self.force_stop_calls = 0
        self._is_recording = False

    @property
    def is_recording(self):
        return self._is_recording

    def start(self):
        self.start_calls += 1
        self._is_recording = True

    def stop(self, *, abort=False):
        self.stop_calls += 1
        self._is_recording = False
        return self.wav_bytes

    def force_stop(self):
        self.force_stop_calls += 1
        self._is_recording = False
        return True


def _prompt():
    return ThaiPracticePrompt(
        prompt_id="sentence-01",
        text="ตอนนั้นฉันอายุเจ็ดขวบ",
        source="learning-thai",
    )


def test_capture_records_prompt_tagged_audio_in_memory():
    recorder = _FakeRecorder()
    states = []
    captures = []
    practice = ThaiPracticeCapture(
        recorder=recorder,
        prompt=_prompt(),
        on_state_change=states.append,
        on_captured=captures.append,
    )

    assert practice.start_recording(source="thai_hotkey_down") is True
    assert practice.state == ThaiPracticeState.RECORDING

    assert practice.stop_recording(source="thai_hotkey_up") is True

    assert practice.state == ThaiPracticeState.CAPTURED
    assert states == [ThaiPracticeState.RECORDING, ThaiPracticeState.CAPTURED]
    assert len(captures) == 1
    assert captures[0].prompt == _prompt()
    assert captures[0].wav_bytes == b"thai-wav"
    assert practice.last_capture == captures[0]
    assert recorder.start_calls == 1
    assert recorder.stop_calls == 1


def test_capture_does_not_start_while_shared_recorder_is_active():
    recorder = _FakeRecorder()
    recorder._is_recording = True
    practice = ThaiPracticeCapture(recorder=recorder, prompt=_prompt())

    assert practice.start_recording(source="thai_hotkey_down") is False
    assert practice.state == ThaiPracticeState.IDLE
    assert recorder.start_calls == 0


def test_empty_capture_returns_to_idle_and_reports_error():
    recorder = _FakeRecorder(wav_bytes=b"")
    errors = []
    practice = ThaiPracticeCapture(
        recorder=recorder,
        prompt=_prompt(),
        on_error=errors.append,
    )

    assert practice.start_recording() is True
    assert practice.stop_recording() is False

    assert practice.state == ThaiPracticeState.IDLE
    assert errors == ["empty_audio"]
    assert practice.last_capture is None


def test_cancel_discards_audio_and_returns_to_idle():
    recorder = _FakeRecorder()
    practice = ThaiPracticeCapture(recorder=recorder, prompt=_prompt())

    assert practice.start_recording() is True
    assert practice.cancel_recording(source="menu_stop") is True

    assert practice.state == ThaiPracticeState.IDLE
    assert practice.last_capture is None
    assert recorder.force_stop_calls == 1


def test_start_failure_reports_error_and_stays_idle():
    class _FailingRecorder(_FakeRecorder):
        def start(self):
            self.start_calls += 1
            raise RuntimeError("microphone unavailable")

    errors = []
    practice = ThaiPracticeCapture(
        recorder=_FailingRecorder(),
        prompt=_prompt(),
        on_error=errors.append,
    )

    assert practice.start_recording() is False
    assert practice.state == ThaiPracticeState.IDLE
    assert errors == ["start_failed"]
