"""Pipeline: orchestrates record -> transcribe -> clean -> paste."""

import logging
import threading
import time
from enum import Enum
from typing import Callable

from app.cleanup import CleanupProvider
from app.paster import paste
from app.recorder import Recorder
from app.transcriber import Transcriber

logger = logging.getLogger(__name__)

_SLOW_START_WARNING_S = 0.2
_SLOW_STOP_WARNING_S = 0.5


class PipelineState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


class Pipeline:
    """Wires together recorder, transcriber, cleanup, and paster."""

    def __init__(
        self,
        recorder: Recorder,
        transcriber: Transcriber,
        cleanup: CleanupProvider,
        paste_delay_ms: int = 50,
        on_state_change: Callable[[PipelineState], None] | None = None,
        on_complete: Callable[[str], None] | None = None,
    ):
        self.recorder = recorder
        self.transcriber = transcriber
        self.cleanup = cleanup
        self.paste_delay_ms = paste_delay_ms
        self._on_state_change = on_state_change
        self._on_complete = on_complete
        self._state = PipelineState.IDLE
        self._state_lock = threading.RLock()
        self._recording_id_seq = 0
        self._active_recording_id: int | None = None

    @property
    def state(self) -> PipelineState:
        with self._state_lock:
            return self._state

    def _set_state(
        self,
        state: PipelineState,
        *,
        source: str = "internal",
        recording_id: int | None = None,
    ):
        callback = self._on_state_change
        with self._state_lock:
            previous = self._state
            if recording_id is None:
                recording_id = self._active_recording_id
            self._state = state
            if state == PipelineState.IDLE:
                self._active_recording_id = None

        logger.info(
            "Pipeline transition %s -> %s [source=%s recording=%s thread=%s]",
            previous.value,
            state.value,
            source,
            recording_id if recording_id is not None else "-",
            threading.current_thread().name,
        )

        if callback:
            try:
                callback(state)
            except Exception:
                logger.exception("State callback error")

    def start_recording(self, source: str = "external") -> bool:
        """Begin capturing audio."""
        with self._state_lock:
            if self._state != PipelineState.IDLE:
                logger.warning(
                    "start_recording ignored in state %s [source=%s recording=%s]",
                    self._state.value,
                    source,
                    self._active_recording_id if self._active_recording_id is not None else "-",
                )
                return False

            self._recording_id_seq += 1
            recording_id = self._recording_id_seq
            self._active_recording_id = recording_id

            t_start = time.perf_counter()
            try:
                self.recorder.start()
            except Exception:
                self._active_recording_id = None
                logger.exception(
                    "Recorder start failed [source=%s recording=%d]",
                    source,
                    recording_id,
                )
                return False

            elapsed = time.perf_counter() - t_start
            if elapsed > _SLOW_START_WARNING_S:
                logger.warning(
                    "Recorder start was slow (%.3fs) [source=%s recording=%d]",
                    elapsed,
                    source,
                    recording_id,
                )

            self._set_state(
                PipelineState.RECORDING,
                source=source,
                recording_id=recording_id,
            )
            return True

    def stop_recording_and_process(
        self,
        source: str = "external",
        *,
        abort_recording_stop: bool = False,
    ) -> bool:
        """Stop recording, transcribe, clean, and paste."""
        with self._state_lock:
            if self._state != PipelineState.RECORDING:
                logger.warning(
                    "stop_recording_and_process ignored in state %s [source=%s recording=%s]",
                    self._state.value,
                    source,
                    self._active_recording_id if self._active_recording_id is not None else "-",
                )
                return False

            recording_id = self._active_recording_id
            t_total = time.perf_counter()
            t_stop = time.perf_counter()
            try:
                wav_bytes = self.recorder.stop(abort=abort_recording_stop)
            except Exception:
                logger.exception(
                    "Recorder stop failed [source=%s recording=%s]",
                    source,
                    recording_id if recording_id is not None else "-",
                )
                self._set_state(
                    PipelineState.IDLE,
                    source=f"{source}:stop_error",
                    recording_id=recording_id,
                )
                return False

            stop_elapsed = time.perf_counter() - t_stop
            if stop_elapsed > _SLOW_STOP_WARNING_S:
                logger.warning(
                    "Recorder stop was slow (%.3fs) [source=%s recording=%s]",
                    stop_elapsed,
                    source,
                    recording_id if recording_id is not None else "-",
                )

            if not wav_bytes:
                logger.warning(
                    "No audio captured [source=%s recording=%s]",
                    source,
                    recording_id if recording_id is not None else "-",
                )
                self._set_state(
                    PipelineState.IDLE,
                    source=f"{source}:empty_audio",
                    recording_id=recording_id,
                )
                return False

            self._set_state(
                PipelineState.PROCESSING,
                source=source,
                recording_id=recording_id,
            )

        # Transcribe
        try:
            result = self.transcriber.transcribe(wav_bytes)
        except Exception:
            logger.exception(
                "Transcription failed [source=%s recording=%s]",
                source,
                recording_id if recording_id is not None else "-",
            )
            self._set_state(
                PipelineState.IDLE,
                source=f"{source}:transcription_error",
                recording_id=recording_id,
            )
            return False

        if not result.text.strip():
            logger.info(
                "Empty transcription [source=%s recording=%s]",
                source,
                recording_id if recording_id is not None else "-",
            )
            self._set_state(
                PipelineState.IDLE,
                source=f"{source}:empty_transcript",
                recording_id=recording_id,
            )
            return False

        logger.info(
            "Transcribed [%s] (%.2fs) [recording=%s]: %s",
            result.language,
            result.latency,
            recording_id if recording_id is not None else "-",
            result.text,
        )

        # Cleanup
        text = result.text
        try:
            cleanup_result = self.cleanup.clean(text, result.language)
            text = cleanup_result.text
            logger.info(
                "Cleaned (%.2fs) [recording=%s]: %s",
                cleanup_result.latency,
                recording_id if recording_id is not None else "-",
                text,
            )
        except Exception:
            logger.exception(
                "Cleanup failed, using raw transcript [recording=%s]",
                recording_id if recording_id is not None else "-",
            )

        # Paste
        try:
            paste(text, delay_ms=self.paste_delay_ms)
        except Exception:
            logger.exception(
                "Paste failed [recording=%s]",
                recording_id if recording_id is not None else "-",
            )

        # Notify completion
        if self._on_complete:
            try:
                self._on_complete(text)
            except Exception:
                logger.exception("on_complete callback error")

        total = time.perf_counter() - t_total
        logger.info(
            "Total pipeline: %.2fs [source=%s recording=%s]",
            total,
            source,
            recording_id if recording_id is not None else "-",
        )

        self._set_state(
            PipelineState.IDLE,
            source=f"{source}:complete",
            recording_id=recording_id,
        )
        return True

    def cancel_recording(self, source: str = "external") -> bool:
        """Abort an active recording without transcribing partial audio."""
        with self._state_lock:
            recorder_active = self.recorder.is_recording
            if self._state != PipelineState.RECORDING and not recorder_active:
                logger.info(
                    "cancel_recording ignored in state %s [source=%s recording=%s]",
                    self._state.value,
                    source,
                    self._active_recording_id if self._active_recording_id is not None else "-",
                )
                return False

            recording_id = self._active_recording_id
            if recorder_active:
                self.recorder.force_stop()

            self._set_state(
                PipelineState.IDLE,
                source=f"{source}:cancel",
                recording_id=recording_id,
            )
            return True


if __name__ == "__main__":
    import os
    import sys
    from dotenv import load_dotenv
    from app.config import load_config
    from app.cleanup import create_cleanup

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    cfg = load_config()
    if not cfg.mistral_api_key:
        print("Error: MISTRAL_API_KEY not set")
        sys.exit(1)

    recorder = Recorder(sample_rate=cfg.transcription.sample_rate)
    transcriber = Transcriber(
        api_key=cfg.mistral_api_key,
        model=cfg.transcription.model,
        vocabulary=cfg.vocabulary,
    )
    cleanup = create_cleanup(
        provider=cfg.cleanup.provider,
        api_key=cfg.groq_api_key,
        model=cfg.cleanup.model,
        enabled=cfg.cleanup.enabled,
    )

    pipeline = Pipeline(
        recorder=recorder,
        transcriber=transcriber,
        cleanup=cleanup,
        paste_delay_ms=cfg.paste.delay_ms,
        on_state_change=lambda s: print(f"[State: {s.value}]"),
    )

    print("Pipeline CLI test. Press Enter to start recording, Enter again to stop and process.")
    print("Ctrl+C to quit.\n")

    try:
        while True:
            input("Press Enter to start recording...")
            pipeline.start_recording()
            input("Recording... press Enter to stop.")
            pipeline.stop_recording_and_process()
            print()
    except KeyboardInterrupt:
        print("\nDone.")
