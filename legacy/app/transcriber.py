"""Voxtral transcription module.

Uses httpx directly for the API call because the mistralai SDK (v1.9)
doesn't expose the `context_bias` parameter yet.
"""

import base64
import logging
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

MISTRAL_TRANSCRIPTION_URL = "https://api.mistral.ai/v1/audio/transcriptions"
GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GEMINI_TRANSCRIPTION_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_DEFAULT_MODEL = "gemini-3.5-transcribe"
GEMINI_LIVE_MODEL = "gemini-3.5-transcribe-live"
_GEMINI_VOCAB_LIMIT = 100
_BCP47_LANGUAGE = {
    "en": "en",
    "de": "de-DE",
    "th": "th-TH",
}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_S = (0.5, 1.0)
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_CJK_RANGES = (
    ("\u3040", "\u30ff"),  # Hiragana + Katakana
    ("\u3400", "\u9fff"),  # CJK unified ideographs
    ("\uf900", "\ufaff"),  # CJK compatibility ideographs
    ("\uac00", "\ud7af"),  # Hangul
)
_LANGUAGE_ALIASES = {
    "english": "en",
    "german": "de",
    "deutsch": "de",
    "thai": "th",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
}


@dataclass
class TranscriptionResult:
    text: str
    language: str
    latency: float
    duration: float | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        ...


class UnconfiguredTranscriber(TranscriptionProvider):
    """Placeholder used by the menubar app before API keys are configured."""

    def __init__(self, reason: str):
        self.reason = reason

    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        raise RuntimeError(self.reason)


def _post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    files: list[tuple],
    headers: dict[str, str],
) -> httpx.Response:
    """POST with retries on transient failures (network errors, 429, 5xx).

    Non-retryable HTTP errors (e.g. 401, 413) raise immediately.
    """
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        if attempt > 0:
            backoff = _RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)]
            time.sleep(backoff)
        try:
            resp = client.post(url, files=files, headers=headers)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise
            last_exc = exc
            logger.warning(
                "Transcription request got HTTP %d (attempt %d/%d)",
                exc.response.status_code,
                attempt + 1,
                _RETRY_ATTEMPTS,
            )
        except httpx.TransportError as exc:
            last_exc = exc
            logger.warning(
                "Transcription request failed: %s (attempt %d/%d)",
                exc,
                attempt + 1,
                _RETRY_ATTEMPTS,
            )
    assert last_exc is not None
    raise last_exc


def _post_json_with_retry(
    client: httpx.Client,
    url: str,
    *,
    json: dict,
    headers: dict[str, str],
) -> httpx.Response:
    """JSON POST with the same transient-error retry policy as multipart uploads."""
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        if attempt > 0:
            backoff = _RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)]
            time.sleep(backoff)
        try:
            resp = client.post(url, json=json, headers=headers)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise
            last_exc = exc
            logger.warning(
                "Transcription request got HTTP %d (attempt %d/%d)",
                exc.response.status_code,
                attempt + 1,
                _RETRY_ATTEMPTS,
            )
        except httpx.TransportError as exc:
            last_exc = exc
            logger.warning(
                "Transcription request failed: %s (attempt %d/%d)",
                exc,
                attempt + 1,
                _RETRY_ATTEMPTS,
            )
    assert last_exc is not None
    raise last_exc


def normalize_language(language: str) -> str:
    normalized = language.strip().lower().replace("_", "-")
    if not normalized:
        return ""
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    return normalized.split("-", 1)[0]


def contains_cjk(text: str) -> bool:
    for char in text:
        if any(start <= char <= end for start, end in _CJK_RANGES):
            return True
    return False


def skips_llm_cleanup(provider: str, mode: str = "") -> bool:
    """True when the ASR step already returns formatted dictation text."""
    if provider != "gemini":
        return False
    return (mode or "smart").strip().lower() == "smart"


def gemini_language_codes(language: str, allowed_languages: list[str] | None = None) -> list[str]:
    """Map Yap language settings to Gemini BCP-47 hints."""
    if language.strip():
        normalized = normalize_language(language)
        return [_BCP47_LANGUAGE.get(normalized, normalized)] if normalized else ["auto"]
    codes = []
    for item in allowed_languages or []:
        normalized = normalize_language(item)
        if normalized:
            codes.append(_BCP47_LANGUAGE.get(normalized, normalized))
    return codes or ["auto"]


def _gemini_transcript_text(body: dict) -> tuple[str, str]:
    """Extract transcript text and optional language from an Interactions response."""
    text = str(body.get("output_text") or "").strip()
    if not text:
        for step in body.get("steps") or []:
            if not isinstance(step, dict):
                continue
            for item in step.get("content") or []:
                if isinstance(item, dict) and str(item.get("text") or "").strip():
                    text = str(item["text"]).strip()
                    break
            if text:
                break
    if not text:
        for candidate in body.get("candidates") or []:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            for part in (content or {}).get("parts") or []:
                if isinstance(part, dict) and str(part.get("text") or "").strip():
                    text = str(part["text"]).strip()
                    break
            if text:
                break
    language = str(body.get("language") or "").strip()
    return text, language


def _vocabulary_prompt(terms: list[str]) -> str:
    """Build Groq's short spelling/context prompt within its 224-token limit."""
    normalized = [" ".join(term.split()) for term in terms if term.strip()]
    if not normalized:
        return ""
    prompt = "Preferred spellings and technical terms: " + ", ".join(normalized)
    # Keep room below the documented 224-token limit without requiring a
    # tokenizer dependency. Truncate at a term boundary where possible.
    if len(prompt) <= 700:
        return prompt
    return prompt[:700].rsplit(", ", 1)[0]


def _segment_quality(body: dict) -> tuple[float | None, float | None, float | None]:
    segments = body.get("segments") or []
    values = {"avg_logprob": [], "no_speech_prob": [], "compression_ratio": []}
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        for key in values:
            value = segment.get(key)
            if isinstance(value, (int, float)):
                values[key].append(float(value))
    return tuple(
        statistics.fmean(values[key]) if values[key] else None
        for key in ("avg_logprob", "no_speech_prob", "compression_ratio")
    )


def _score_allowed_transcript(result: TranscriptionResult, allowed_languages: set[str]) -> int:
    text = result.text.strip()
    if not text:
        return -100
    score = len(text)
    language = normalize_language(result.language)
    if language in allowed_languages:
        score += 1000
    if contains_cjk(text):
        score -= 5000
    return score


class Transcriber(TranscriptionProvider):
    """Wraps the Voxtral transcription API."""

    def __init__(self, api_key: str, model: str = "voxtral-mini-2602", vocabulary: list[str] | None = None):
        self.api_key = api_key
        self.model = model
        self.provider = "mistral"
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
        resp = _post_with_retry(
            self._client,
            MISTRAL_TRANSCRIPTION_URL,
            files=fields,
            headers=headers,
        )
        latency = time.perf_counter() - t0

        body = resp.json()
        return TranscriptionResult(
            text=body.get("text", ""),
            language=body.get("language", ""),
            latency=latency,
        )

    def open_live_session(self):
        """Start a Mistral Realtime socket. The caller does not wait for a transcript."""
        from app.mistral_live import MistralRealtimeSession

        session = MistralRealtimeSession(api_key=self.api_key)
        session.start()
        return session


class GroqTranscriber(TranscriptionProvider):
    """Wraps Groq's OpenAI-compatible Whisper transcription API."""

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-large-v3-turbo",
        language: str = "",
        allowed_languages: list[str] | None = None,
        fallback_languages: list[str] | None = None,
        vocabulary: list[str] | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.provider = "groq"
        self.language = language
        self.vocabulary = vocabulary or []
        self.allowed_languages = {
            normalize_language(language)
            for language in (allowed_languages or [])
            if normalize_language(language)
        }
        self.fallback_languages = [
            normalize_language(language)
            for language in (fallback_languages or [])
            if normalize_language(language)
        ]
        self._client = httpx.Client(timeout=30.0)

    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        result = self._transcribe_once(wav_bytes, language=self.language)
        if self._is_allowed_result(result):
            return result

        if not self.allowed_languages or self.language:
            return result

        candidates = [result]
        for language in self.fallback_languages:
            if language not in self.allowed_languages:
                continue
            retry = self._transcribe_once(wav_bytes, language=language)
            if retry.text.strip() and self._is_allowed_result(retry):
                return retry
            candidates.append(retry)

        return max(
            candidates,
            key=lambda candidate: _score_allowed_transcript(candidate, self.allowed_languages),
        )

    def _transcribe_once(self, wav_bytes: bytes, language: str = "") -> TranscriptionResult:
        fields: list[tuple] = [
            ("model", (None, self.model)),
            ("file", ("recording.wav", wav_bytes, "audio/wav")),
            ("response_format", (None, "verbose_json")),
            ("temperature", (None, "0")),
        ]
        if language:
            fields.append(("language", (None, language)))
        prompt = _vocabulary_prompt(self.vocabulary)
        if prompt:
            fields.append(("prompt", (None, prompt)))

        headers = {"Authorization": f"Bearer {self.api_key}"}

        t0 = time.perf_counter()
        resp = _post_with_retry(
            self._client,
            GROQ_TRANSCRIPTION_URL,
            files=fields,
            headers=headers,
        )
        latency = time.perf_counter() - t0

        body = resp.json()
        avg_logprob, no_speech_prob, compression_ratio = _segment_quality(body)
        return TranscriptionResult(
            text=body.get("text", ""),
            language=body.get("language", ""),
            latency=latency,
            duration=body.get("duration"),
            avg_logprob=avg_logprob,
            no_speech_prob=no_speech_prob,
            compression_ratio=compression_ratio,
        )

    def _is_allowed_result(self, result: TranscriptionResult) -> bool:
        text = result.text.strip()
        if not text:
            return True
        if contains_cjk(text):
            return False
        if not self.allowed_languages:
            return True
        language = normalize_language(result.language)
        return not language or language in self.allowed_languages


class GeminiTranscriber(TranscriptionProvider):
    """Gemini transcription. `transcribe` posts one WAV. `open_live_session` streams PCM."""

    def __init__(
        self,
        api_key: str,
        model: str = GEMINI_DEFAULT_MODEL,
        mode: str = "smart",
        language: str = "",
        allowed_languages: list[str] | None = None,
        vocabulary: list[str] | None = None,
    ):
        self.api_key = api_key
        self.model = model or GEMINI_DEFAULT_MODEL
        self.provider = "gemini"
        self.mode = (mode or "smart").strip().lower() or "smart"
        self.language = language
        self.allowed_languages = [
            normalize_language(item)
            for item in (allowed_languages or [])
            if normalize_language(item)
        ]
        self.vocabulary = vocabulary or []
        self._client = httpx.Client(timeout=45.0)

    def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        vocab = [term.strip() for term in self.vocabulary if term.strip()][:_GEMINI_VOCAB_LIMIT]
        transcription_config: dict = {
            "language_codes": gemini_language_codes(self.language, self.allowed_languages),
            "mode": {"type": self.mode},
        }
        if vocab:
            transcription_config["custom_vocabulary"] = vocab
        payload = {
            "model": self.model,
            "input": [
                {
                    "type": "audio",
                    "data": base64.b64encode(wav_bytes).decode("ascii"),
                    "mime_type": "audio/wav",
                }
            ],
            "generation_config": {"transcription_config": transcription_config},
        }
        t0 = time.perf_counter()
        resp = _post_json_with_retry(
            self._client,
            GEMINI_TRANSCRIPTION_URL,
            json=payload,
            headers={"x-goog-api-key": self.api_key},
        )
        latency = time.perf_counter() - t0
        text, language = _gemini_transcript_text(resp.json())
        return TranscriptionResult(text=text, language=language, latency=latency)

    def _live_setup(self) -> dict:
        vocab = [term.strip() for term in self.vocabulary if term.strip()][:_GEMINI_VOCAB_LIMIT]
        transcription: dict = {
            "languageCodes": gemini_language_codes(self.language, self.allowed_languages),
            "mode": "SMART" if self.mode == "smart" else "VERBATIM",
        }
        if vocab:
            transcription["customVocabulary"] = vocab
        return {
            "setup": {
                "model": f"models/{GEMINI_LIVE_MODEL}",
                "generationConfig": {"responseModalities": ["TEXT"]},
                "inputAudioTranscription": transcription,
                "realtimeInputConfig": {
                    "automaticActivityDetection": {"disabled": True},
                },
            }
        }

    def open_live_session(self):
        """Start a push-to-talk socket. The caller does not wait for a transcript."""
        from app.gemini_live import GeminiLiveSession

        session = GeminiLiveSession(api_key=self.api_key, setup=self._live_setup())
        session.start()
        return session


def create_transcriber(
    *,
    provider: str,
    mistral_api_key: str = "",
    groq_api_key: str = "",
    gemini_api_key: str = "",
    model: str = "",
    vocabulary: list[str] | None = None,
    allowed_languages: list[str] | None = None,
    fallback_languages: list[str] | None = None,
    language: str = "",
    mode: str = "",
    allow_unconfigured: bool = False,
) -> TranscriptionProvider:
    """Factory: create the configured transcription provider."""
    if provider == "groq":
        if not groq_api_key:
            if allow_unconfigured:
                return UnconfiguredTranscriber("GROQ_API_KEY is required for Groq transcription")
            raise ValueError("GROQ_API_KEY is required for Groq transcription")
        return GroqTranscriber(
            api_key=groq_api_key,
            model=model or "whisper-large-v3-turbo",
            language=language,
            allowed_languages=allowed_languages,
            fallback_languages=fallback_languages,
            vocabulary=vocabulary,
        )

    if provider == "gemini":
        if not gemini_api_key:
            if allow_unconfigured:
                return UnconfiguredTranscriber("GEMINI_API_KEY is required for Gemini transcription")
            raise ValueError("GEMINI_API_KEY is required for Gemini transcription")
        return GeminiTranscriber(
            api_key=gemini_api_key,
            model=model or GEMINI_DEFAULT_MODEL,
            mode=mode or "smart",
            language=language,
            allowed_languages=allowed_languages,
            vocabulary=vocabulary,
        )

    if not mistral_api_key:
        if allow_unconfigured:
            return UnconfiguredTranscriber("MISTRAL_API_KEY is required for Mistral transcription")
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
