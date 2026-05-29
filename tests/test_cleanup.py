"""Tests for transcript cleanup guardrails."""

from app.cleanup import _cleanup_user_message, _looks_like_meta_response


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
