"""Privacy-preserving pipeline measurements.

Measurements deliberately contain timings, model identities, and outcome
reasons only. Transcript content and API credentials never belong in this
artifact.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineMeasurement:
    recording_id: int | None
    source: str
    audio_duration_s: float | None
    recorder_stop_s: float
    transcription_s: float | None
    cleanup_s: float | None
    total_s: float
    transcription_provider: str
    transcription_model: str
    cleanup_provider: str
    cleanup_model: str
    language: str
    text_chars: int
    success: bool
    error: str = ""
    fallback_reason: str = ""
    cleanup_finish_reason: str = ""
    cleanup_attempts: int = 0
    cleanup_request_attempts: int = 0
    cleanup_status_code: int | None = None
    cleanup_retry_statuses: tuple[int, ...] = ()
    timestamp: str = ""

    def as_dict(self) -> dict:
        values = asdict(self)
        if not values["timestamp"]:
            values["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return values


class MetricsWriter:
    """Append measurements to a local, mode-0600 JSONL file."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def append(self, measurement: PipelineMeasurement) -> None:
        record = measurement.as_dict()
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                self.path.chmod(0o600)
        except OSError:
            # Metrics must never break dictation or paste.
            logger.exception("Failed to write pipeline measurement to %s", self.path)


def wav_duration_seconds(wav_bytes: bytes) -> float | None:
    """Return WAV duration without retaining or writing audio content."""
    import io
    import wave

    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            rate = wav.getframerate()
            if rate <= 0:
                return None
            return wav.getnframes() / rate
    except (OSError, EOFError, wave.Error):
        return None
