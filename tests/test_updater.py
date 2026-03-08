"""Tests for app.updater."""

import json
from pathlib import Path
import subprocess

import pytest

import app.updater as updater_module
import app.version as version_module
from app.version import bundled_app_path, release_asset_name_for_version


class _FakeResponse:
    def __init__(self, *, payload=None, chunks=None, status_code=200):
        self._payload = payload or {}
        self._chunks = chunks or []
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_bundled_app_path_only_returns_yap_bundle(monkeypatch):
    monkeypatch.setattr(version_module.sys, "executable", "/Applications/Python.app/Contents/MacOS/Python")
    assert bundled_app_path() is None

    monkeypatch.setattr(version_module.sys, "executable", "/Applications/Yap.app/Contents/MacOS/Yap")
    assert bundled_app_path() == Path("/Applications/Yap.app")


def test_fetch_available_update_returns_newer_release(monkeypatch, tmp_path):
    payload = {
        "tag_name": "v0.2.1",
        "html_url": "https://github.com/philippmoeller-fr/yap/releases/tag/v0.2.1",
        "body": "Bug fixes",
        "assets": [
            {
                "name": release_asset_name_for_version("0.2.1"),
                "browser_download_url": "https://example.com/Yap-0.2.1.zip",
            }
        ],
    }
    monkeypatch.setattr(updater_module.httpx, "get", lambda *args, **kwargs: _FakeResponse(payload=payload))

    state_file = tmp_path / "updater_state.json"
    manager = updater_module.UpdateManager(
        current_version="0.2.0",
        state_file=state_file,
        current_app_path=tmp_path / "Yap.app",
    )

    update = manager.fetch_available_update()

    assert update is not None
    assert update.version == "0.2.1"
    assert update.asset_url == "https://example.com/Yap-0.2.1.zip"
    assert state_file.exists()
    assert manager.should_check_for_updates(
        now=json.loads(state_file.read_text())["last_checked_at"] + 1
    ) is False


def test_fetch_available_update_returns_none_when_already_current(monkeypatch, tmp_path):
    payload = {"tag_name": "0.2.1", "assets": []}
    monkeypatch.setattr(updater_module.httpx, "get", lambda *args, **kwargs: _FakeResponse(payload=payload))

    manager = updater_module.UpdateManager(
        current_version="0.2.1",
        state_file=tmp_path / "state.json",
        current_app_path=tmp_path / "Yap.app",
    )

    assert manager.fetch_available_update() is None


def test_fetch_available_update_treats_missing_release_as_no_update(monkeypatch, tmp_path):
    monkeypatch.setattr(
        updater_module.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse(status_code=404),
    )

    manager = updater_module.UpdateManager(
        current_version="0.2.1",
        state_file=tmp_path / "state.json",
        current_app_path=tmp_path / "Yap.app",
    )

    assert manager.fetch_available_update() is None


def test_prepare_update_downloads_and_stages_app(monkeypatch, tmp_path):
    app_path = tmp_path / "Yap.app"
    app_path.mkdir()
    manager = updater_module.UpdateManager(
        current_version="0.2.0",
        state_file=tmp_path / "state.json",
        current_app_path=app_path,
    )
    update = updater_module.UpdateInfo(
        version="0.2.1",
        release_url="https://example.com/release",
        asset_name="Yap-0.2.1.zip",
        asset_url="https://example.com/Yap-0.2.1.zip",
        notes="Notes",
    )

    monkeypatch.setattr(
        updater_module.httpx,
        "stream",
        lambda *args, **kwargs: _FakeResponse(chunks=[b"zip-bytes"]),
    )

    def fake_run(cmd, check):
        extract_dir = Path(cmd[4])
        (extract_dir / "Yap.app").mkdir()
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(updater_module.subprocess, "run", fake_run)

    plan = manager.prepare_update(update)

    assert plan.archive_path.read_bytes() == b"zip-bytes"
    assert plan.staged_app_path == plan.work_dir / "extract" / "Yap.app"
    assert plan.script_path.exists()


def test_launch_installer_spawns_helper(monkeypatch, tmp_path):
    manager = updater_module.UpdateManager(
        current_version="0.2.0",
        state_file=tmp_path / "state.json",
        current_app_path=tmp_path / "Yap.app",
    )
    plan = updater_module.UpdateInstallPlan(
        version="0.2.1",
        work_dir=tmp_path / "work",
        archive_path=tmp_path / "work" / "Yap-0.2.1.zip",
        staged_app_path=tmp_path / "work" / "extract" / "Yap.app",
        target_app_path=tmp_path / "Yap.app",
        script_path=tmp_path / "work" / "install-update.sh",
    )

    popen_calls = []
    monkeypatch.setattr(
        updater_module.subprocess,
        "Popen",
        lambda args, start_new_session: popen_calls.append((args, start_new_session)),
    )

    manager.launch_installer(plan, current_pid=1234)

    assert popen_calls == [
        (
            [
                "/bin/bash",
                str(plan.script_path),
                "1234",
                str(plan.staged_app_path),
                str(plan.target_app_path),
                str(plan.work_dir),
            ],
            True,
        )
    ]


def test_prepare_update_rejects_non_bundle_install(tmp_path):
    manager = updater_module.UpdateManager(
        current_version="0.2.0",
        state_file=tmp_path / "state.json",
        current_app_path=None,
    )
    update = updater_module.UpdateInfo(
        version="0.2.1",
        release_url="https://example.com/release",
        asset_name="Yap-0.2.1.zip",
        asset_url="https://example.com/Yap-0.2.1.zip",
        notes="Notes",
    )

    with pytest.raises(updater_module.UpdateError, match="installed app bundle"):
        manager.prepare_update(update)
