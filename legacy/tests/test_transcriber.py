"""Tests for transcription language guardrails and retry behavior."""

import httpx
import pytest

import app.transcriber as transcriber_module
from app.transcriber import (
    GroqTranscriber,
    TranscriptionResult,
    UnconfiguredTranscriber,
    _gemini_transcript_text,
    _post_with_retry,
    contains_cjk,
    create_transcriber,
    gemini_language_codes,
    normalize_language,
    skips_llm_cleanup,
)


def test_normalize_language_accepts_names_and_locale_codes():
    assert normalize_language("German") == "de"
    assert normalize_language("English") == "en"
    assert normalize_language("de-DE") == "de"
    assert normalize_language("ja_JP") == "ja"


def test_contains_cjk_detects_japanese_and_chinese_text():
    assert contains_cjk("これはテストです") is True
    assert contains_cjk("これは Test") is True
    assert contains_cjk("Das ist ein Test.") is False


def test_groq_language_guard_allows_configured_languages():
    transcriber = GroqTranscriber(
        api_key="gsk-test",
        allowed_languages=["en", "de"],
        fallback_languages=["de", "en"],
    )

    assert transcriber._is_allowed_result(
        TranscriptionResult(text="Kleiner Test.", language="German", latency=0.1)
    ) is True
    assert transcriber._is_allowed_result(
        TranscriptionResult(text="Small test.", language="English", latency=0.1)
    ) is True


def test_groq_language_guard_rejects_cjk_even_when_language_is_missing():
    transcriber = GroqTranscriber(
        api_key="gsk-test",
        allowed_languages=["en", "de"],
        fallback_languages=["de", "en"],
    )

    assert transcriber._is_allowed_result(
        TranscriptionResult(text="これはテストです", language="", latency=0.1)
    ) is False


def test_create_transcriber_stays_strict_by_default_without_key():
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        create_transcriber(provider="groq")


def test_create_transcriber_can_return_unconfigured_placeholder_without_key():
    transcriber = create_transcriber(provider="groq", allow_unconfigured=True)

    assert isinstance(transcriber, UnconfiguredTranscriber)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        transcriber.transcribe(b"wav")


def test_skips_llm_cleanup_only_for_gemini_smart():
    assert skips_llm_cleanup("gemini", "smart") is True
    assert skips_llm_cleanup("gemini", "") is True
    assert skips_llm_cleanup("gemini", "verbatim") is False
    assert skips_llm_cleanup("groq", "smart") is False


def test_gemini_language_codes_prefer_explicit_hint():
    assert gemini_language_codes("de", ["en", "de"]) == ["de-DE"]
    assert gemini_language_codes("", ["en", "de"]) == ["en", "de-DE"]
    assert gemini_language_codes("", []) == ["auto"]


def test_gemini_transcript_text_reads_interactions_steps():
    text, language = _gemini_transcript_text(
        {
            "output_text": "",
            "steps": [{"content": [{"type": "text", "text": "  Meet Wednesday.  "}]}],
        }
    )
    assert text == "Meet Wednesday."
    assert language == ""


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "https://api.test/v1"),
                response=self,
            )

    def json(self):
        return {"text": "ok", "language": "en"}


class _FakeClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def post(self, url, *, files, headers):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    monkeypatch.setattr(transcriber_module.time, "sleep", lambda *_: None)


def test_post_with_retry_recovers_from_transport_error():
    client = _FakeClient([httpx.ConnectError("refused"), 200])

    resp = _post_with_retry(client, "https://api.test/v1", files=[], headers={})

    assert resp.status_code == 200
    assert client.calls == 2


def test_post_with_retry_recovers_from_server_error():
    client = _FakeClient([503, 200])

    resp = _post_with_retry(client, "https://api.test/v1", files=[], headers={})

    assert resp.status_code == 200
    assert client.calls == 2


def test_post_with_retry_does_not_retry_client_errors():
    client = _FakeClient([401, 200])

    with pytest.raises(httpx.HTTPStatusError):
        _post_with_retry(client, "https://api.test/v1", files=[], headers={})

    assert client.calls == 1


def test_post_with_retry_gives_up_after_max_attempts():
    client = _FakeClient([httpx.ConnectError("refused")] * 5)

    with pytest.raises(httpx.ConnectError):
        _post_with_retry(client, "https://api.test/v1", files=[], headers={})

    assert client.calls == 3


def test_groq_transcriber_retries_disallowed_language(monkeypatch):
    transcriber = GroqTranscriber(
        api_key="gsk-test",
        allowed_languages=["en", "de"],
        fallback_languages=["de", "en"],
    )
    results = iter(
        [
            TranscriptionResult(text="これはテストです", language="Japanese", latency=0.1),
            TranscriptionResult(text="Kleiner Test.", language="German", latency=0.2),
        ]
    )
    monkeypatch.setattr(transcriber, "_transcribe_once", lambda *_args, **_kwargs: next(results))

    result = transcriber.transcribe(b"wav")

    assert result.text == "Kleiner Test."
    assert result.language == "German"


def test_groq_transcriber_sends_language_prompt_and_quality_settings(monkeypatch):
    transcriber = GroqTranscriber(
        api_key="gsk-test",
        vocabulary=["Cerebras", "Voxtral Realtime"],
        language="en",
    )

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "text": "Use Cerebras with Voxtral Realtime.",
                "language": "en",
                "duration": 1.2,
                "segments": [
                    {
                        "avg_logprob": -0.11,
                        "no_speech_prob": 0.02,
                        "compression_ratio": 1.4,
                    }
                ],
            }

    captured = {}

    def fake_post(client, url, *, files, headers):
        captured["files"] = files
        captured["headers"] = headers
        return _Response()

    monkeypatch.setattr(transcriber_module, "_post_with_retry", fake_post)

    result = transcriber.transcribe(b"wav")

    assert result.text == "Use Cerebras with Voxtral Realtime."
    assert result.avg_logprob == -0.11
    assert result.no_speech_prob == 0.02
    assert result.compression_ratio == 1.4
    fields = {name: value for name, value in captured["files"] if name != "file"}
    assert fields["model"] == (None, "whisper-large-v3-turbo")
    assert fields["response_format"] == (None, "verbose_json")
    assert fields["language"] == (None, "en")
    assert fields["temperature"] == (None, "0")
    assert "Cerebras" in fields["prompt"][1]
    assert "Voxtral Realtime" in fields["prompt"][1]


def test_create_transcriber_builds_gemini_smart_provider():
    transcriber = create_transcriber(
        provider="gemini",
        gemini_api_key="AIza-test",
        allowed_languages=["en", "de"],
        vocabulary=["Yap"],
    )

    from app.transcriber import GeminiTranscriber

    assert isinstance(transcriber, GeminiTranscriber)
    assert transcriber.mode == "smart"
    assert transcriber.model == "gemini-3.5-transcribe"


def test_gemini_transcriber_sends_smart_mode_and_vocabulary(monkeypatch):
    from app.transcriber import GeminiTranscriber

    transcriber = GeminiTranscriber(
        api_key="AIza-test",
        vocabulary=["Cerebras", "Yap"],
        allowed_languages=["en", "de"],
    )

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output_text": "Use Cerebras with Yap.",
                "language": "en",
            }

    captured = {}

    def fake_post(client, url, *, json, headers):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _Response()

    monkeypatch.setattr(transcriber_module, "_post_json_with_retry", fake_post)

    result = transcriber.transcribe(b"wav-bytes")

    assert result.text == "Use Cerebras with Yap."
    config = captured["json"]["generation_config"]["transcription_config"]
    assert captured["json"]["model"] == "gemini-3.5-transcribe"
    assert config["mode"] == {"type": "smart"}
    assert config["language_codes"] == ["en", "de-DE"]
    assert config["custom_vocabulary"] == ["Cerebras", "Yap"]
    assert captured["json"]["input"][0]["mime_type"] == "audio/wav"
    assert captured["headers"]["x-goog-api-key"] == "AIza-test"


def test_create_transcriber_gemini_without_key_can_be_unconfigured():
    transcriber = create_transcriber(provider="gemini", allow_unconfigured=True)
    assert isinstance(transcriber, UnconfiguredTranscriber)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        transcriber.transcribe(b"wav")
