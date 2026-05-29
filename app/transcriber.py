"""Voxtral transcription module.

Uses httpx directly for the API call because the mistralai SDK (v1.9)
doesn't expose the `context_bias` parameter yet.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

MISTRAL_TRANSCRIPTION_URL = "https://api.mistral.ai/v1/audio/transcriptions"
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


@dataclass
class TranscriptionResult:
    text: str
    language: str
    latency: float


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        ...


class Transcriber(TranscriptionProvider):
    """Wraps the Voxtral transcription API."""

    def __init__(self, api_key: str, model: str = "voxtral-mini-2602", vocabulary: list[str] | None = None):
        self.api_key = api_key
        self.model = model
        self.vocabulary = vocabulary or []
        self._client = httpx.Client(timeout=30.0)

    @staticmethod
    def _normalize_vocab(terms: list[str]) -> list[str]:
        """Normalize vocabulary for the API: each term must match ^[^,\\s]+$."""
        result = []
        for term in terms:
            # Split multi-word terms into individual words, also add underscored version
            words = term.split()
            if len(words) > 1:
                result.append("_".join(words))
                result.extend(words)
            else:
                result.append(term)
        return list(dict.fromkeys(result))  # dedupe preserving order

    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        """Transcribe WAV audio bytes. Returns text, detected language, and latency."""
        # Build multipart fields — context_bias must be repeated fields
        fields: list[tuple] = [
            ("model", (None, self.model)),
            ("file", ("recording.wav", wav_bytes, "audio/wav")),
        ]
        for term in self._normalize_vocab(self.vocabulary):
            fields.append(("context_bias", (None, term)))

        headers = {"Authorization": f"Bearer {self.api_key}"}

        t0 = time.perf_counter()
        resp = self._client.post(
            MISTRAL_TRANSCRIPTION_URL,
            files=fields,
            headers=headers,
        )
        resp.raise_for_status()
        latency = time.perf_counter() - t0

        body = resp.json()
        return TranscriptionResult(
            text=body.get("text", ""),
            language=body.get("language", ""),
            latency=latency,
        )


class GroqTranscriber(TranscriptionProvider):
    """Wraps Groq's OpenAI-compatible Whisper transcription API."""

    def __init__(self, api_key: str, model: str = "whisper-large-v3-turbo", language: str = ""):
        self.api_key = api_key
        self.model = model
        self.language = language
        self._client = httpx.Client(timeout=30.0)

    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        fields: list[tuple] = [
            ("model", (None, self.model)),
            ("file", ("recording.wav", wav_bytes, "audio/wav")),
            ("response_format", (None, "verbose_json")),
        ]
        if self.language:
            fields.append(("language", (None, self.language)))

        headers = {"Authorization": f"Bearer {self.api_key}"}

        t0 = time.perf_counter()
        resp = self._client.post(
            GROQ_TRANSCRIPTION_URL,
            files=fields,
            headers=headers,
        )
        resp.raise_for_status()
        latency = time.perf_counter() - t0

        body = resp.json()
        return TranscriptionResult(
            text=body.get("text", ""),
            language=body.get("language", ""),
            latency=latency,
        )


def create_transcriber(
    *,
    provider: str,
    mistral_api_key: str = "",
    groq_api_key: str = "",
    model: str = "",
    vocabulary: list[str] | None = None,
) -> TranscriptionProvider:
    """Factory: create the configured transcription provider."""
    if provider == "groq":
        if not groq_api_key:
            raise ValueError("GROQ_API_KEY is required for Groq transcription")
        return GroqTranscriber(api_key=groq_api_key, model=model or "whisper-large-v3-turbo")

    if not mistral_api_key:
        raise ValueError("MISTRAL_API_KEY is required for Mistral transcription")
    return Transcriber(
        api_key=mistral_api_key,
        model=model or "voxtral-mini-2602",
        vocabulary=vocabulary,
    )


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    from app.recorder import Recorder

    load_dotenv()

    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        print("Error: MISTRAL_API_KEY not set")
        exit(1)

    t = Transcriber(api_key=key, vocabulary=["Claude Code", "CLAUDE.md", "Anthropic", "Voxtral"])
    rec = Recorder()

    print("Recording 5 seconds — speak now!")
    rec.start()
    import time as _time
    _time.sleep(5)
    wav = rec.stop()

    if wav:
        result = t.transcribe(wav)
        print(f"Language: {result.language}")
        print(f"Text: {result.text}")
        print(f"Latency: {result.latency:.2f}s")
    else:
        print("No audio captured")
