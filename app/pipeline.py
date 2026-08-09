"""Pipeline: orchestrates record -> transcribe -> clean -> paste."""

import logging
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable

from app.cleanup import CleanupProvider
from app.metrics import MetricsWriter, PipelineMeasurement, wav_duration_seconds
from app.paster import paste
from app.recorder import Recorder
from app.transcriber import TranscriptionProvider, create_transcriber

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
        transcriber: TranscriptionProvider,
        cleanup: CleanupProvider,
        paste_delay_ms: int = 50,
        on_state_change: Callable[[PipelineState], None] | None = None,
        on_complete: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        failed_recording_path: Path | None = None,
        metrics_path: Path | None = None,
        on_measurement: Callable[[PipelineMeasurement], None] | None = None,
    ):
        self.recorder = recorder
        self.transcriber = transcriber
        self.cleanup = cleanup
        self.paste_delay_ms = paste_delay_ms
        self._on_state_change = on_state_change
        self._on_complete = on_complete
        self._on_error = on_error
        self._failed_recording_path = failed_recording_path
        self._metrics_writer = MetricsWriter(metrics_path) if metrics_path is not None else None
        self._on_measurement = on_measurement
        self._failed_wav: bytes | None = None
        self._state = PipelineState.IDLE
        self._state_lock = threading.RLock()
        self._recording_id_seq = 0
        self._active_recording_id: int | None = None

    @staticmethod
    def _provider_details(provider: object) -> tuple[str, str]:
        name = str(getattr(provider, "provider", "") or provider.__class__.__name__.lower())
        model = str(getattr(provider, "model", "") or "")
        return name, model

    @staticmethod
    def _exception_code(prefix: str, error: Exception) -> str:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status is not None:
            return f"{prefix}_http_{status}"
        return f"{prefix}_{error.__class__.__name__.lower()}"

    def _emit_measurement(
        self,
        *,
        recording_id: int | None,
        source: str,
        wav_bytes: bytes | None,
        recorder_stop_s: float,
        transcription_s: float | None,
        cleanup_s: float | None,
        total_s: float,
        language: str = "",
        text_chars: int = 0,
        success: bool,
        error: str = "",
        fallback_reason: str = "",
    ) -> None:
        transcription_provider, transcription_model = self._provider_details(self.transcriber)
        cleanup_provider, cleanup_model = self._provider_details(self.cleanup)
        measurement = PipelineMeasurement(
            recording_id=recording_id,
            source=source,
            audio_duration_s=wav_duration_seconds(wav_bytes) if wav_bytes else None,
            recorder_stop_s=recorder_stop_s,
            transcription_s=transcription_s,
            cleanup_s=cleanup_s,
            total_s=total_s,
            transcription_provider=transcription_provider,
            transcription_model=transcription_model,
            cleanup_provider=cleanup_provider,
            cleanup_model=cleanup_model,
            language=language,
            text_chars=text_chars,
            success=success,
            error=error,
            fallback_reason=fallback_reason,
        )
        if self._metrics_writer is not None:
            self._metrics_writer.append(measurement)
        if self._on_measurement is not None:
            try:
                self._on_measurement(measurement)
            except Exception:
                logger.exception("Pipeline measurement callback error")

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
                total = time.perf_counter() - t_total
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
                self._emit_measurement(
                    recording_id=recording_id,
                    source=source,
                    wav_bytes=None,
                    recorder_stop_s=time.perf_counter() - t_stop,
                    transcription_s=None,
                    cleanup_s=None,
                    total_s=total,
                    success=False,
                    error="recorder_stop_failed",
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
                total = time.perf_counter() - t_total
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
                self._emit_measurement(
                    recording_id=recording_id,
                    source=source,
                    wav_bytes=None,
                    recorder_stop_s=stop_elapsed,
                    transcription_s=None,
                    cleanup_s=None,
                    total_s=total,
                    success=False,
                    error="empty_audio",
                )
                return False

            self._set_state(
                PipelineState.PROCESSING,
                source=source,
                recording_id=recording_id,
            )

        return self._process_audio(
            wav_bytes,
            source,
            recording_id,
            t_total,
            recorder_stop_s=stop_elapsed,
        )

    def _process_audio(
        self,
        wav_bytes: bytes,
        source: str,
        recording_id: int | None,
        t_total: float,
        *,
        recorder_stop_s: float = 0.0,
        from_retry: bool = False,
    ) -> bool:
        """Transcribe, clean, and paste audio. Caller must have set PROCESSING state."""
        # Transcribe
        t_transcribe = time.perf_counter()
        try:
            result = self.transcriber.transcribe(wav_bytes)
        except Exception:
            transcribe_elapsed = time.perf_counter() - t_transcribe
            logger.exception(
                "Transcription failed [provider=%s model=%s source=%s recording=%s]",
                self._provider_details(self.transcriber)[0],
                self._provider_details(self.transcriber)[1],
                source,
                recording_id if recording_id is not None else "-",
            )
            self._stash_failed_recording(wav_bytes)
            self._set_state(
                PipelineState.IDLE,
                source=f"{source}:transcription_error",
                recording_id=recording_id,
            )
            self._emit_measurement(
                recording_id=recording_id,
                source=source,
                wav_bytes=wav_bytes,
                recorder_stop_s=recorder_stop_s,
                transcription_s=transcribe_elapsed,
                cleanup_s=None,
                total_s=time.perf_counter() - t_total,
                success=False,
                error="transcription_failed",
                fallback_reason="transcription_exception",
            )
            self._notify_error("transcription_failed")
            return False

        if from_retry:
            # The stashed audio reached the API — the copy is no longer needed.
            self._clear_failed_recording()

        if not result.text.strip():
            transcribe_elapsed = time.perf_counter() - t_transcribe
            logger.info(
                "Empty transcription [provider=%s model=%s source=%s recording=%s]",
                self._provider_details(self.transcriber)[0],
                self._provider_details(self.transcriber)[1],
                source,
                recording_id if recording_id is not None else "-",
            )
            self._set_state(
                PipelineState.IDLE,
                source=f"{source}:empty_transcript",
                recording_id=recording_id,
            )
            self._emit_measurement(
                recording_id=recording_id,
                source=source,
                wav_bytes=wav_bytes,
                recorder_stop_s=recorder_stop_s,
                transcription_s=transcribe_elapsed,
                cleanup_s=None,
                total_s=time.perf_counter() - t_total,
                language=getattr(result, "language", ""),
                success=False,
                error="empty_transcript",
            )
            return False

        transcribe_elapsed = time.perf_counter() - t_transcribe
        logger.info(
            "Transcribed [%s] (%.2fs provider=%.2fs avg_logprob=%s no_speech_prob=%s) "
            "[provider=%s model=%s recording=%s text_chars=%d]",
            result.language,
            result.latency,
            transcribe_elapsed,
            getattr(result, "avg_logprob", None),
            getattr(result, "no_speech_prob", None),
            self._provider_details(self.transcriber)[0],
            self._provider_details(self.transcriber)[1],
            recording_id if recording_id is not None else "-",
            len(result.text),
        )

        # Cleanup
        text = result.text
        cleanup_elapsed = None
        cleanup_fallback_reason = ""
        cleanup_error = ""
        t_cleanup = time.perf_counter()
        try:
            cleanup_result = self.cleanup.clean(text, result.language)
            text = cleanup_result.text
            cleanup_elapsed = time.perf_counter() - t_cleanup
            cleanup_fallback_reason = getattr(cleanup_result, "fallback_reason", "")
            logger.info(
                "Cleaned (%.2fs provider=%.2fs fallback=%s) [provider=%s model=%s recording=%s text_chars=%d]",
                cleanup_result.latency,
                cleanup_elapsed,
                cleanup_fallback_reason or "none",
                getattr(cleanup_result, "provider", "") or self._provider_details(self.cleanup)[0],
                getattr(cleanup_result, "model", "") or self._provider_details(self.cleanup)[1],
                recording_id if recording_id is not None else "-",
                len(text),
            )
        except Exception as exc:
            cleanup_elapsed = time.perf_counter() - t_cleanup
            cleanup_fallback_reason = "cleanup_exception"
            cleanup_error = self._exception_code("cleanup", exc)
            logger.exception(
                "Cleanup failed, using raw transcript [provider=%s model=%s recording=%s]",
                self._provider_details(self.cleanup)[0],
                self._provider_details(self.cleanup)[1],
                recording_id if recording_id is not None else "-",
            )

        # Paste
        paste_failed = False
        try:
            paste(text, delay_ms=self.paste_delay_ms)
        except Exception:
            paste_failed = True
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
            "Total pipeline: %.2fs [source=%s recording=%s transcription=%.2fs cleanup=%.2fs]",
            total,
            source,
            recording_id if recording_id is not None else "-",
            transcribe_elapsed,
            cleanup_elapsed or 0.0,
        )

        self._emit_measurement(
            recording_id=recording_id,
            source=source,
            wav_bytes=wav_bytes,
            recorder_stop_s=recorder_stop_s,
            transcription_s=transcribe_elapsed,
            cleanup_s=cleanup_elapsed,
            total_s=total,
            language=result.language,
            text_chars=len(text),
            success=not paste_failed,
            error=cleanup_error or ("paste_failed" if paste_failed else ""),
            fallback_reason=cleanup_fallback_reason,
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

    @property
    def has_failed_recording(self) -> bool:
        """True if a transcription-failed recording is available for retry."""
        if self._failed_wav:
            return True
        path = self._failed_recording_path
        try:
            return path is not None and path.exists() and path.stat().st_size > 0
        except OSError:
            return False

    def retry_last_recording(self, source: str = "retry") -> bool:
        """Re-run transcription for the last recording that failed to transcribe."""
        with self._state_lock:
            if self._state != PipelineState.IDLE:
                logger.warning(
                    "retry_last_recording ignored in state %s [source=%s]",
                    self._state.value,
                    source,
                )
                return False

            wav_bytes = self._load_failed_recording()
            if not wav_bytes:
                logger.info("retry_last_recording: no failed recording available")
                return False

            self._recording_id_seq += 1
            recording_id = self._recording_id_seq
            self._active_recording_id = recording_id
            self._set_state(
                PipelineState.PROCESSING,
                source=source,
                recording_id=recording_id,
            )

        return self._process_audio(
            wav_bytes,
            source,
            recording_id,
            time.perf_counter(),
            recorder_stop_s=0.0,
            from_retry=True,
        )

    def _stash_failed_recording(self, wav_bytes: bytes):
        """Keep the audio of a failed transcription so the user can retry it."""
        self._failed_wav = wav_bytes
        path = self._failed_recording_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(wav_bytes)
            path.chmod(0o600)
            logger.info("Saved failed recording to %s (%d bytes)", path, len(wav_bytes))
        except OSError:
            logger.exception("Failed to save recording to %s", path)

    def _load_failed_recording(self) -> bytes:
        if self._failed_wav:
            return self._failed_wav
        path = self._failed_recording_path
        if path is None:
            return b""
        try:
            if path.exists():
                return path.read_bytes()
        except OSError:
            logger.exception("Failed to read saved recording from %s", path)
        return b""

    def _clear_failed_recording(self):
        self._failed_wav = None
        path = self._failed_recording_path
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove saved recording %s", path)

    def _notify_error(self, reason: str):
        if self._on_error is None:
            return
        try:
            self._on_error(reason)
        except Exception:
            logger.exception("on_error callback error")


if __name__ == "__main__":
    import os
    import sys
    from dotenv import load_dotenv
    from app.config import load_config
    from app.cleanup import create_cleanup

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_dotenv()

    cfg = load_config()
    if cfg.transcription.provider == "groq" and not cfg.groq_api_key:
        print("Error: GROQ_API_KEY not set")
        sys.exit(1)
    if cfg.transcription.provider != "groq" and not cfg.mistral_api_key:
        print("Error: MISTRAL_API_KEY not set")
        sys.exit(1)

    recorder = Recorder(sample_rate=cfg.transcription.sample_rate)
    transcriber = create_transcriber(
        provider=cfg.transcription.provider,
        mistral_api_key=cfg.mistral_api_key,
        groq_api_key=cfg.groq_api_key,
        model=cfg.transcription.model,
        language=cfg.transcription.language,
        vocabulary=cfg.vocabulary,
        allowed_languages=cfg.transcription.allowed_languages,
        fallback_languages=cfg.transcription.fallback_languages,
    )
    cleanup = create_cleanup(
        provider=cfg.cleanup.provider,
        api_key={
            "groq": cfg.groq_api_key,
            "mistral": cfg.mistral_api_key,
            "cerebras": cfg.cerebras_api_key,
        }.get(cfg.cleanup.provider, ""),
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
