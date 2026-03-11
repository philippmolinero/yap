"""Microphone recording module: capture audio as WAV bytes."""

import io
import logging
import threading
import time as _time

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

_START_TIMEOUT_S = 3.0
_STOP_TIMEOUT_S = 1.0
_STOP_ABORT_DRAIN_TIMEOUT_S = 0.25
_CLOSE_TIMEOUT_S = 0.25


class Recorder:
    """Push-to-talk recorder. Call start() to begin, stop() to get WAV bytes."""

    def __init__(self, sample_rate: int = 16000, silence_timeout: float = 0, silence_threshold: float = 0.008):
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._stop_lock = threading.Lock()  # prevents concurrent stop() calls
        self._level: float = 0.0  # current RMS audio level (0.0 - 1.0)
        # Silence detection
        self._silence_timeout = silence_timeout  # 0 = disabled
        self._silence_threshold = silence_threshold
        self._silence_start: float | None = None
        self._silence_fired = False
        self._on_silence = None  # callable, fired once when silence exceeds timeout
        self._on_backend_unhealthy = None  # callable(reason: str)
        self._backend_unhealthy_notified = False

    def _reset_levels(self):
        self._level = 0.0
        self._silence_start = None
        self._silence_fired = False

    def _clear_frames(self):
        with self._lock:
            self._frames.clear()

    def _mark_backend_unhealthy(self, reason: str):
        if self._backend_unhealthy_notified:
            return
        self._backend_unhealthy_notified = True
        logger.error("Recorder backend unhealthy: %s", reason)
        callback = self._on_backend_unhealthy
        if callback is None:
            return
        try:
            callback(reason)
        except Exception:
            logger.exception("Recorder backend unhealthy callback failed")

    def _run_stream_action(
        self,
        stream: sd.InputStream,
        action_name: str,
        *,
        timeout_s: float,
        raise_errors: bool = False,
    ) -> bool:
        finished = threading.Event()
        error: list[Exception] = []

        def _run():
            try:
                method = getattr(stream, action_name)
                if action_name == "start":
                    method()
                else:
                    method(ignore_errors=True)
            except Exception as exc:
                if raise_errors:
                    error.append(exc)
                else:
                    logger.exception("Recorder stream %s failed", action_name)
            finally:
                finished.set()

        threading.Thread(target=_run, daemon=True).start()
        completed = finished.wait(timeout_s)
        if completed and error:
            raise error[0]
        return completed

    def _close_stream(self, stream: sd.InputStream, *, abort: bool):
        backend_unhealthy = False
        if abort:
            if not self._run_stream_action(
                stream,
                "abort",
                timeout_s=_STOP_ABORT_DRAIN_TIMEOUT_S,
            ):
                logger.warning(
                    "Recorder stream abort timed out after %.2fs; leaving stream detached",
                    _STOP_ABORT_DRAIN_TIMEOUT_S,
                )
                backend_unhealthy = True
        else:
            if not self._run_stream_action(stream, "stop", timeout_s=_STOP_TIMEOUT_S):
                logger.warning(
                    "Recorder stream stop timed out after %.2fs; aborting stream",
                    _STOP_TIMEOUT_S,
                )
                if not self._run_stream_action(
                    stream,
                    "abort",
                    timeout_s=_STOP_ABORT_DRAIN_TIMEOUT_S,
                ):
                    logger.warning(
                        "Recorder stream abort timed out after stop timeout; leaving stream detached",
                    )
                    backend_unhealthy = True

        if not self._run_stream_action(stream, "close", timeout_s=_CLOSE_TIMEOUT_S):
            logger.warning(
                "Recorder stream close timed out after %.2fs; leaving stream detached",
                _CLOSE_TIMEOUT_S,
            )
            backend_unhealthy = True

        if backend_unhealthy:
            self._mark_backend_unhealthy("stream_teardown_timeout")

    def _callback(self, indata, frame_count, time_info, status):
        if status:
            import sys
            print(f"Recording warning: {status}", file=sys.stderr)
        with self._lock:
            self._frames.append(indata.copy())
        # Compute RMS level for this chunk, clamp to 0-1
        rms = float(np.sqrt(np.mean(indata ** 2)))
        self._level = min(rms * 20.0, 1.0)  # amplify aggressively for visible bars

        # Silence detection
        if self._silence_timeout > 0 and not self._silence_fired:
            if rms < self._silence_threshold:
                now = _time.time()
                if self._silence_start is None:
                    self._silence_start = now
                elif now - self._silence_start >= self._silence_timeout:
                    self._silence_fired = True
                    if self._on_silence:
                        self._on_silence()
            else:
                self._silence_start = None

    @property
    def audio_level(self) -> float:
        """Current audio level 0.0 (silence) to 1.0 (loud)."""
        return self._level

    def start(self):
        """Start recording from the default microphone."""
        with self._stop_lock:
            old_stream, self._stream = self._stream, None
            if old_stream is not None:
                logger.warning("Discarding stale recorder stream before start")
                self._close_stream(old_stream, abort=True)

            self._clear_frames()
            self._reset_levels()

            stream = None
            try:
                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=self._callback,
                )
                self._stream = stream
                if not self._run_stream_action(
                    stream,
                    "start",
                    timeout_s=_START_TIMEOUT_S,
                    raise_errors=True,
                ):
                    logger.warning(
                        "Recorder stream start timed out after %.2fs; aborting stream",
                        _START_TIMEOUT_S,
                    )
                    self._stream = None
                    self._clear_frames()
                    self._reset_levels()
                    self._close_stream(stream, abort=True)
                    stream = None
                    self._mark_backend_unhealthy("stream_start_timeout")
                    raise RuntimeError("Recorder stream start timed out")
            except Exception:
                self._stream = None
                self._clear_frames()
                self._reset_levels()
                if stream is not None:
                    self._close_stream(stream, abort=True)
                raise

    def stop(self, *, abort: bool = False) -> bytes:
        """Stop recording and return WAV bytes (PCM16).

        Thread-safe: if two threads call stop() concurrently, only the first
        one actually stops the PortAudio stream. The second gets empty bytes.
        """
        with self._stop_lock:
            stream, self._stream = self._stream, None

        if stream is not None:
            self._close_stream(stream, abort=abort)
        self._reset_levels()

        with self._lock:
            if not self._frames:
                return b""
            audio = np.concatenate(self._frames, axis=0)
            self._frames.clear()

        buf = io.BytesIO()
        sf.write(buf, audio, self.sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def force_stop(self) -> bool:
        """Abort and discard the current stream without processing audio."""
        with self._stop_lock:
            stream, self._stream = self._stream, None

        self._clear_frames()
        self._reset_levels()

        if stream is None:
            return False

        self._close_stream(stream, abort=True)
        return True

    @property
    def is_recording(self) -> bool:
        with self._stop_lock:
            stream = self._stream
        return stream is not None and stream.active


if __name__ == "__main__":
    import time

    rec = Recorder()
    print("Recording for 3 seconds...")
    rec.start()
    time.sleep(3)
    wav = rec.stop()
    duration = len(wav) / (16000 * 2)  # 16-bit = 2 bytes/sample
    print(f"Captured {len(wav)} bytes ({duration:.1f}s)")
