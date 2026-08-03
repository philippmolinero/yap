"""Local capture seam for Thai speech practice."""

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from app.recorder import Recorder

logger = logging.getLogger(__name__)


class ThaiPracticeState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    CAPTURED = "captured"


@dataclass(frozen=True)
class ThaiPracticePrompt:
    """The source-backed prompt associated with one practice recording."""

    prompt_id: str
    text: str
    source: str


@dataclass(frozen=True)
class ThaiPracticeCaptureResult:
    """An in-memory recording ready for a later local analyzer."""

    prompt: ThaiPracticePrompt
    wav_bytes: bytes


class ThaiPracticeCapture:
    """Capture Thai audio without transcription, upload, or persistence."""

    def __init__(
        self,
        recorder: Recorder,
        prompt: ThaiPracticePrompt,
        on_state_change: Callable[[ThaiPracticeState], None] | None = None,
        on_captured: Callable[[ThaiPracticeCaptureResult], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self.recorder = recorder
        self.prompt = prompt
        self._on_state_change = on_state_change
        self._on_captured = on_captured
        self._on_error = on_error
        self._state = ThaiPracticeState.IDLE
        self._state_lock = threading.RLock()
        self._last_capture: ThaiPracticeCaptureResult | None = None

    @property
    def state(self) -> ThaiPracticeState:
        with self._state_lock:
            return self._state

    @property
    def last_capture(self) -> ThaiPracticeCaptureResult | None:
        with self._state_lock:
            return self._last_capture

    def _notify_state(self, state: ThaiPracticeState):
        callback = self._on_state_change
        if callback is None:
            return
        try:
            callback(state)
        except Exception:
            logger.exception("Thai practice state callback failed")

    def _set_state(self, state: ThaiPracticeState):
        with self._state_lock:
            self._state = state
        self._notify_state(state)

    def _notify_error(self, reason: str):
        callback = self._on_error
        if callback is None:
            return
        try:
            callback(reason)
        except Exception:
            logger.exception("Thai practice error callback failed")

    def start_recording(self, source: str = "external") -> bool:
        """Start a local Thai capture if the shared recorder is available."""
        start_failed = False
        with self._state_lock:
            if self._state == ThaiPracticeState.RECORDING:
                logger.warning("Thai practice start ignored while already recording")
                return False
            if self.recorder.is_recording:
                logger.warning(
                    "Thai practice start ignored because the shared recorder is active [source=%s]",
                    source,
                )
                return False

            try:
                self.recorder.start()
            except Exception:
                logger.exception("Thai practice recorder start failed [source=%s]", source)
                start_failed = True
            else:
                self._last_capture = None
                self._state = ThaiPracticeState.RECORDING

        if start_failed:
            self._notify_error("start_failed")
            return False

        logger.info("Thai practice recording started [source=%s]", source)
        self._notify_state(ThaiPracticeState.RECORDING)
        return True

    def stop_recording(
        self,
        source: str = "external",
        *,
        abort_recording_stop: bool = False,
    ) -> bool:
        """Stop a Thai capture and retain its WAV bytes only in memory."""
        with self._state_lock:
            if self._state != ThaiPracticeState.RECORDING:
                logger.warning(
                    "Thai practice stop ignored in state %s [source=%s]",
                    self._state.value,
                    source,
                )
                return False

            try:
                wav_bytes = self.recorder.stop(abort=abort_recording_stop)
            except Exception:
                logger.exception("Thai practice recorder stop failed [source=%s]", source)
                self._state = ThaiPracticeState.IDLE
                notify_state = True
                notify_error = "stop_failed"
            else:
                notify_state = True
                notify_error = None
                if not wav_bytes:
                    logger.warning("Thai practice capture contained no audio [source=%s]", source)
                    self._last_capture = None
                    self._state = ThaiPracticeState.IDLE
                    notify_error = "empty_audio"
                else:
                    self._last_capture = ThaiPracticeCaptureResult(
                        prompt=self.prompt,
                        wav_bytes=wav_bytes,
                    )
                    self._state = ThaiPracticeState.CAPTURED

        if notify_state:
            self._notify_state(self.state)
        if notify_error:
            self._notify_error(notify_error)
            return False

        capture = self.last_capture
        if capture is not None and self._on_captured is not None:
            try:
                self._on_captured(capture)
            except Exception:
                logger.exception("Thai practice capture callback failed")

        logger.info("Thai practice recording captured locally [source=%s]", source)
        return True

    def cancel_recording(self, source: str = "external") -> bool:
        """Abort and discard an active Thai recording."""
        with self._state_lock:
            if self._state != ThaiPracticeState.RECORDING:
                logger.info(
                    "Thai practice cancel ignored in state %s [source=%s]",
                    self._state.value,
                    source,
                )
                return False

            self.recorder.force_stop()
            self._last_capture = None
            self._state = ThaiPracticeState.IDLE

        self._notify_state(ThaiPracticeState.IDLE)
        logger.info("Thai practice recording cancelled [source=%s]", source)
        return True
