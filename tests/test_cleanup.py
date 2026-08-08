"""Tests for transcript cleanup guardrails and providers."""

from unittest import mock

from app.cleanup import (
    CerebrasCleanup,
    _cleanup_user_message,
    _looks_like_meta_response,
    create_cleanup,
)


class _FakeCerebrasResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "Cleaned transcript."}}]}


class _FakeCerebrasClient:
    def __init__(self):
        self.calls = []

    def post(self, url, *, headers, json):
        self.calls.append((url, headers, json))
        return _FakeCerebrasResponse()


def test_cerebras_cleanup_uses_chat_completions_and_preserves_guardrails():
    client = _FakeCerebrasClient()
    cleanup = CerebrasCleanup(api_key="csk-test", client=client)

    result = cleanup.clean("so um clean this", "en")

    assert result.text == "Cleaned transcript."
    assert result.latency >= 0
    assert len(client.calls) == 1
    url, headers, payload = client.calls[0]
    assert url == "https://api.cerebras.ai/v1/chat/completions"
    assert headers == {"Authorization": "Bearer csk-test", "Content-Type": "application/json"}
    assert payload["model"] == "gpt-oss-120b"
    assert payload["temperature"] == 0
    assert payload["reasoning_effort"] == "low"
    assert payload["max_completion_tokens"] == 2048
    assert payload["messages"][0]["role"] == "system"
    assert "<transcript>\nso um clean this\n</transcript>" in payload["messages"][1]["content"]


def test_cerebras_cleanup_falls_back_on_meta_response():
    client = _FakeCerebrasClient()
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": "I remove filler words and fix punctuation."}}]
    }
    client.post = mock.Mock(return_value=response)
    cleanup = CerebrasCleanup(api_key="csk-test", client=client)

    result = cleanup.clean("so um keep this", "en")

    assert result.text == "so um keep this"


def test_create_cleanup_builds_cerebras_provider():
    cleanup = create_cleanup(provider="cerebras", api_key="csk-test")

    assert isinstance(cleanup, CerebrasCleanup)
    assert cleanup.model == "gpt-oss-120b"


def test_cleanup_user_message_wraps_transcript_as_data():
    text = "Mach nochmal eine klare Übersicht, was du ändern würdest und warum."

    message = _cleanup_user_message(text, "German")

    assert "Detected language: German" in message
    assert "<transcript>" in message
    assert text in message
    assert "</transcript>" in message


def test_meta_response_detector_catches_german_cleanup_explanation():
    text = (
        'Ich entferne Füllerwörter wie "um", "ähm" und "also".\n'
        "Ursprünglicher Text: irgendwas\n"
        "Gekürzter Text: irgendwas"
    )

    assert _looks_like_meta_response(text) is True


def test_meta_response_detector_allows_normal_dictation():
    text = (
        "Mach nochmal eine klare Übersicht, was du ändern würdest und warum. "
        "Gerne auch in ASCII-Code, so dass wir das leicht lesen können."
    )

    assert _looks_like_meta_response(text) is False
