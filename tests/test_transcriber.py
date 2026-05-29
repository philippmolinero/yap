"""Tests for transcription language guardrails."""

from app.transcriber import (
    GroqTranscriber,
    TranscriptionResult,
    contains_cjk,
    normalize_language,
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
