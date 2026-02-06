"""Sound feedback for recording start/stop."""

import io
import logging

import numpy as np
import soundfile as sf

import AppKit

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 44100


def _generate_blip(freq: float, duration_ms: float = 40, volume: float = 0.2) -> bytes:
    """Generate a short blip sound as WAV bytes."""
    samples = int(_SAMPLE_RATE * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, samples, dtype=np.float32)
    # Smooth bell-curve envelope for a clean attack/decay
    envelope = np.sin(np.pi * np.linspace(0, 1, samples))
    wave = volume * envelope * np.sin(2 * np.pi * freq * t)
    buf = io.BytesIO()
    sf.write(buf, wave, _SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class SoundFeedback:
    """Plays subtle audio cues for recording events."""

    def __init__(self):
        self._start_sound = self._load(_generate_blip(1200, 35, 0.20))
        self._stop_sound = self._load(_generate_blip(800, 45, 0.15))

    @staticmethod
    def _load(wav_bytes: bytes) -> AppKit.NSSound:
        data = AppKit.NSData.dataWithBytes_length_(wav_bytes, len(wav_bytes))
        sound = AppKit.NSSound.alloc().initWithData_(data)
        return sound

    def play_start(self):
        """Play a subtle high blip when recording starts."""
        self._start_sound.stop()
        self._start_sound.play()

    def play_stop(self):
        """Play a subtle low blip when recording stops."""
        self._stop_sound.stop()
        self._stop_sound.play()
