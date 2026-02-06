"""Pipeline: orchestrates record -> transcribe -> clean -> paste."""

import logging
import time
from enum import Enum
from typing import Callable

from app.cleanup import CleanupProvider, NoopCleanup
from app.paster import paste
from app.recorder import Recorder
from app.transcriber import Transcriber

logger = logging.getLogger(__name__)


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

    @property
    def state(self) -> PipelineState:
        return self._state

    def _set_state(self, state: PipelineState):
        self._state = state
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception:
                logger.exception("State callback error")

    def start_recording(self):
        """Begin capturing audio."""
        self._set_state(PipelineState.RECORDING)
        self.recorder.start()

    def stop_recording_and_process(self):
        """Stop recording, transcribe, clean, and paste."""
        t_total = time.perf_counter()

        # Stop recording
        wav_bytes = self.recorder.stop()
        if not wav_bytes:
            logger.warning("No audio captured")
            self._set_state(PipelineState.IDLE)
            return

        self._set_state(PipelineState.PROCESSING)

        # Transcribe
        try:
            result = self.transcriber.transcribe(wav_bytes)
        except Exception:
            logger.exception("Transcription failed")
            self._set_state(PipelineState.IDLE)
            return

        if not result.text.strip():
            logger.info("Empty transcription")
            self._set_state(PipelineState.IDLE)
            return

        logger.info(
            "Transcribed [%s] (%.2fs): %s",
            result.language, result.latency, result.text,
        )

        # Cleanup
        text = result.text
        try:
            cleanup_result = self.cleanup.clean(text, result.language)
            text = cleanup_result.text
            logger.info("Cleaned (%.2fs): %s", cleanup_result.latency, text)
        except Exception:
            logger.exception("Cleanup failed, using raw transcript")

        # Paste
        try:
            paste(text, delay_ms=self.paste_delay_ms)
        except Exception:
            logger.exception("Paste failed")

        # Notify completion
        if self._on_complete:
            try:
                self._on_complete(text)
            except Exception:
                logger.exception("on_complete callback error")

        total = time.perf_counter() - t_total
        logger.info("Total pipeline: %.2fs", total)

        self._set_state(PipelineState.IDLE)


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
