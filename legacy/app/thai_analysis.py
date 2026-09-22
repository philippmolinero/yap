"""Local acoustic evidence for Thai speech practice.

This module extracts an F0 contour from the recorder's WAV bytes. It does not
recognize words, align syllables, classify lexical tones, or decide whether a
learner's pronunciation is correct.
"""

import io
import logging
import math
from dataclasses import dataclass
from enum import Enum

import numpy as np
import parselmouth
import soundfile as sf

logger = logging.getLogger(__name__)


class ThaiPitchStatus(Enum):
    """What the local pitch extractor can safely say about a recording."""

    ANALYZED = "analyzed"
    UNCERTAIN = "uncertain"
    NO_VOICE = "no_voice"
    INVALID_AUDIO = "invalid_audio"


@dataclass(frozen=True)
class ThaiPitchAnalysisResult:
    """Speaker-normalized pitch evidence, never a lexical-tone score."""

    status: ThaiPitchStatus
    duration_s: float
    voiced_coverage: float
    times_s: tuple[float, ...] = ()
    frequencies_hz: tuple[float | None, ...] = ()
    semitone_contour: tuple[float | None, ...] = ()
    median_f0_hz: float | None = None
    sample_rate_hz: int | None = None
    reason: str | None = None


class ThaiPitchAnalyzer:
    """Extract a local F0 contour from WAV bytes using Praat via Parselmouth."""

    def __init__(
        self,
        *,
        time_step: float = 0.01,
        pitch_floor_hz: float = 75.0,
        pitch_ceiling_hz: float = 500.0,
        min_voiced_coverage: float = 0.20,
        min_duration_s: float = 0.20,
    ):
        if time_step <= 0:
            raise ValueError("time_step must be positive")
        if pitch_floor_hz <= 0 or pitch_ceiling_hz <= pitch_floor_hz:
            raise ValueError("pitch bounds are invalid")
        if not 0 <= min_voiced_coverage <= 1:
            raise ValueError("min_voiced_coverage must be between 0 and 1")
        if min_duration_s < 0:
            raise ValueError("min_duration_s must not be negative")

        self.time_step = time_step
        self.pitch_floor_hz = pitch_floor_hz
        self.pitch_ceiling_hz = pitch_ceiling_hz
        self.min_voiced_coverage = min_voiced_coverage
        self.min_duration_s = min_duration_s

    def analyze(self, wav_bytes: bytes) -> ThaiPitchAnalysisResult:
        """Return local F0 evidence for one recorder-produced WAV recording."""
        decoded = self._decode_wav(wav_bytes)
        if decoded is None:
            return ThaiPitchAnalysisResult(
                status=ThaiPitchStatus.INVALID_AUDIO,
                duration_s=0.0,
                voiced_coverage=0.0,
                reason="decode_failed",
            )

        samples, sample_rate = decoded
        duration_s = len(samples) / sample_rate
        try:
            sound = parselmouth.Sound(samples, sampling_frequency=float(sample_rate))
            pitch = sound.to_pitch(
                time_step=self.time_step,
                pitch_floor=self.pitch_floor_hz,
                pitch_ceiling=self.pitch_ceiling_hz,
            )
        except Exception:
            logger.exception("Thai pitch extraction failed")
            return ThaiPitchAnalysisResult(
                status=ThaiPitchStatus.INVALID_AUDIO,
                duration_s=duration_s,
                voiced_coverage=0.0,
                sample_rate_hz=sample_rate,
                reason="pitch_extraction_failed",
            )

        frequencies = pitch.selected_array["frequency"]
        times = pitch.xs()
        frequency_values: list[float | None] = []
        voiced_values: list[float] = []
        for raw_frequency in frequencies:
            frequency = float(raw_frequency)
            if math.isfinite(frequency) and frequency > 0:
                frequency_values.append(frequency)
                voiced_values.append(frequency)
            else:
                frequency_values.append(None)

        frame_count = len(frequency_values)
        voiced_coverage = len(voiced_values) / frame_count if frame_count else 0.0
        time_values = tuple(float(value) for value in times)

        if not voiced_values:
            return ThaiPitchAnalysisResult(
                status=ThaiPitchStatus.NO_VOICE,
                duration_s=duration_s,
                voiced_coverage=0.0,
                times_s=time_values,
                frequencies_hz=tuple(frequency_values),
                sample_rate_hz=sample_rate,
                reason="no_voiced_frames",
            )

        median_f0_hz = float(np.median(np.asarray(voiced_values, dtype=np.float64)))
        semitone_contour = tuple(
            None
            if frequency is None
            else float(12.0 * math.log2(frequency / median_f0_hz))
            for frequency in frequency_values
        )
        status = (
            ThaiPitchStatus.ANALYZED
            if voiced_coverage >= self.min_voiced_coverage
            and duration_s >= self.min_duration_s
            else ThaiPitchStatus.UNCERTAIN
        )
        reason = None if status == ThaiPitchStatus.ANALYZED else "limited_voiced_evidence"

        return ThaiPitchAnalysisResult(
            status=status,
            duration_s=duration_s,
            voiced_coverage=voiced_coverage,
            times_s=time_values,
            frequencies_hz=tuple(frequency_values),
            semitone_contour=semitone_contour,
            median_f0_hz=median_f0_hz,
            sample_rate_hz=sample_rate,
            reason=reason,
        )

    @staticmethod
    def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int] | None:
        try:
            samples, sample_rate = sf.read(
                io.BytesIO(wav_bytes),
                dtype="float64",
                always_2d=True,
            )
        except Exception:
            logger.exception("Thai WAV decoding failed")
            return None

        if samples.size == 0 or sample_rate <= 0:
            return None

        # Recorder captures one channel, but averaging keeps the analyzer
        # predictable if a stereo fixture or future input reaches this seam.
        mono = np.mean(samples, axis=1)
        if mono.size == 0 or not np.all(np.isfinite(mono)):
            return None
        return mono, int(sample_rate)
