"""Microphone recording module: capture audio as WAV bytes."""

import io
import threading
import time as _time

import numpy as np
import sounddevice as sd
import soundfile as sf


class Recorder:
    """Push-to-talk recorder. Call start() to begin, stop() to get WAV bytes."""

    def __init__(self, sample_rate: int = 16000, silence_timeout: float = 0, silence_threshold: float = 0.008):
        self.sample_rate = sample_rate
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._level: float = 0.0  # current RMS audio level (0.0 - 1.0)
        # Silence detection
        self._silence_timeout = silence_timeout  # 0 = disabled
        self._silence_threshold = silence_threshold
        self._silence_start: float | None = None
        self._silence_fired = False
        self._on_silence = None  # callable, fired once when silence exceeds timeout

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
        with self._lock:
            self._frames.clear()
        self._silence_start = None
        self._silence_fired = False

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Stop recording and return WAV bytes (PCM16)."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            if not self._frames:
                return b""
            audio = np.concatenate(self._frames, axis=0)
            self._frames.clear()

        buf = io.BytesIO()
        sf.write(buf, audio, self.sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active


if __name__ == "__main__":
    import time

    rec = Recorder()
    print("Recording for 3 seconds...")
    rec.start()
    time.sleep(3)
    wav = rec.stop()
    duration = len(wav) / (16000 * 2)  # 16-bit = 2 bytes/sample
    print(f"Captured {len(wav)} bytes ({duration:.1f}s)")
