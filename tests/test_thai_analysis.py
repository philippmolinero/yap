"""Tests for the local Thai pitch-contour analyzer."""

import io

import numpy as np
import pytest
import soundfile as sf

from app.thai_analysis import ThaiPitchAnalyzer, ThaiPitchStatus


def _wav_bytes(samples: np.ndarray, sample_rate: int = 16_000) -> bytes:
    output = io.BytesIO()
    sf.write(output, samples.astype(np.float64), sample_rate, format="WAV", subtype="PCM_16")
    return output.getvalue()


def test_analyzer_returns_local_pitch_contour_for_voiced_wav():
    sample_rate = 16_000
    time = np.arange(sample_rate) / sample_rate
    samples = 0.2 * np.sin(2 * np.pi * 180 * time)

    result = ThaiPitchAnalyzer().analyze(_wav_bytes(samples, sample_rate))

    assert result.status == ThaiPitchStatus.ANALYZED
    assert result.duration_s == 1.0
    assert result.voiced_coverage > 0.9
    assert result.median_f0_hz == pytest.approx(180.0, abs=1.0)
    assert len(result.times_s) == len(result.frequencies_hz)
    assert len(result.semitone_contour) == len(result.frequencies_hz)
    assert all(value is not None for value in result.frequencies_hz)
    assert all(value is not None for value in result.semitone_contour)
    assert max(abs(value) for value in result.semitone_contour if value is not None) < 0.1


def test_analyzer_marks_valid_silence_as_no_voice():
    sample_rate = 16_000
    samples = np.zeros(sample_rate)

    result = ThaiPitchAnalyzer().analyze(_wav_bytes(samples, sample_rate))

    assert result.status == ThaiPitchStatus.NO_VOICE
    assert result.voiced_coverage == 0.0
    assert result.median_f0_hz is None
    assert result.semitone_contour == ()


def test_analyzer_marks_too_short_voice_as_uncertain():
    sample_rate = 16_000
    time = np.arange(int(sample_rate * 0.10)) / sample_rate
    samples = 0.2 * np.sin(2 * np.pi * 180 * time)

    result = ThaiPitchAnalyzer().analyze(_wav_bytes(samples, sample_rate))

    assert result.status == ThaiPitchStatus.UNCERTAIN
    assert result.reason == "limited_voiced_evidence"
    assert result.median_f0_hz == pytest.approx(180.0, abs=2.0)


def test_analyzer_marks_unreadable_audio_as_invalid_without_raising():
    result = ThaiPitchAnalyzer().analyze(b"not a wav")

    assert result.status == ThaiPitchStatus.INVALID_AUDIO
    assert result.voiced_coverage == 0.0
    assert result.reason == "decode_failed"
