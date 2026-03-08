"""Microphone recording module: capture audio as WAV bytes."""

import io
import logging
import threading
import time as _time

import numpy as np
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)


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

    def _reset_levels(self):
        self._level = 0.0
        self._silence_start = None
        self._silence_fired = False

    def _clear_frames(self):
        with self._lock:
            self._frames.clear()

    def _close_stream(self, stream: sd.InputStream, *, abort: bool):
        stop_method = stream.abort if abort else stream.stop
        action = "abort" if abort else "stop"

        try:
            stop_method(ignore_errors=True)
        except Exception:
            logger.exception("Recorder stream %s failed", action)

        try:
            stream.close(ignore_errors=True)
        except Exception:
            logger.exception("Recorder stream close failed")

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
                stream.start()
            except Exception:
                self._stream = None
                self._clear_frames()
                self._reset_levels()
                if stream is not None:
                    self._close_stream(stream, abort=True)
                raise

    def stop(self) -> bytes:
        """Stop recording and return WAV bytes (PCM16).

        Thread-safe: if two threads call stop() concurrently, only the first
        one actually stops the PortAudio stream. The second gets empty bytes.
        """
        with self._stop_lock:
            stream, self._stream = self._stream, None

        if stream is not None:
            self._close_stream(stream, abort=False)
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
