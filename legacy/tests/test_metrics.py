"""Tests for privacy-preserving pipeline measurements."""

import json

from app.metrics import MetricsWriter, PipelineMeasurement


def test_metrics_writer_appends_redacted_jsonl(tmp_path):
    path = tmp_path / "metrics.jsonl"
    writer = MetricsWriter(path)
    measurement = PipelineMeasurement(
        recording_id=7,
        source="hotkey_up",
        audio_duration_s=3.2,
        recorder_stop_s=0.01,
        transcription_s=0.62,
        cleanup_s=0.48,
        total_s=1.21,
        transcription_provider="groq",
        transcription_model="whisper-large-v3-turbo",
        cleanup_provider="cerebras",
        cleanup_model="gpt-oss-120b",
        language="en",
        text_chars=128,
        success=True,
        cleanup_finish_reason="stop",
        cleanup_attempts=2,
        cleanup_request_attempts=3,
        cleanup_status_code=200,
        cleanup_retry_statuses=(429,),
    )

    writer.append(measurement)

    record = json.loads(path.read_text())
    assert record["recording_id"] == 7
    assert record["cleanup_provider"] == "cerebras"
    assert record["total_s"] == 1.21
    assert record["cleanup_finish_reason"] == "stop"
    assert record["cleanup_request_attempts"] == 3
    assert record["cleanup_status_code"] == 200
    assert record["cleanup_retry_statuses"] == [429]
    assert "text" not in record
    assert "transcript" not in record
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_measurement_has_stable_timestamp_and_failure_fields():
    record = PipelineMeasurement(
        recording_id=None,
        source="hotkey_up",
        audio_duration_s=None,
        recorder_stop_s=0.0,
        transcription_s=None,
        cleanup_s=None,
        total_s=0.0,
        transcription_provider="groq",
        transcription_model="whisper-large-v3-turbo",
        cleanup_provider="cerebras",
        cleanup_model="gpt-oss-120b",
        language="",
        text_chars=0,
        success=False,
        error="transcription_failed",
        fallback_reason="network",
    ).as_dict()

    assert record["timestamp"].endswith("+00:00")
    assert record["success"] is False
    assert record["error"] == "transcription_failed"
    assert record["fallback_reason"] == "network"
