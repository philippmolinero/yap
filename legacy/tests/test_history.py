"""Tests for app.history persistence."""

from app.history import load_history, save_history


def test_history_roundtrip(tmp_path):
    path = tmp_path / "history.json"
    items = ["latest dictation", "older dictation", "umlauts äöü"]

    save_history(path, items)

    assert load_history(path) == items
    assert (path.stat().st_mode & 0o777) == 0o600


def test_load_history_missing_file_returns_empty(tmp_path):
    assert load_history(tmp_path / "missing.json") == []


def test_load_history_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not json")

    assert load_history(path) == []


def test_load_history_ignores_non_string_entries(tmp_path):
    path = tmp_path / "history.json"
    path.write_text('["valid", 42, null, "", "also valid"]')

    assert load_history(path) == ["valid", "also valid"]


def test_load_history_respects_limit(tmp_path):
    path = tmp_path / "history.json"
    save_history(path, [f"entry {i}" for i in range(30)])

    assert load_history(path, limit=15) == [f"entry {i}" for i in range(15)]


def test_save_history_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "history.json"

    save_history(path, ["entry"])

    assert load_history(path) == ["entry"]
