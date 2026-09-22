"""GitHub Releases based self-updater for Yap."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time

import httpx

from app.config import CONFIG_DIR
from app.version import (
    APP_NAME,
    APP_VERSION,
    GITHUB_REPO,
    bundled_app_path,
    is_newer_version,
    normalize_version,
    release_asset_name_for_version,
)

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_S = 24 * 60 * 60
_LATEST_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


class UpdateError(RuntimeError):
    """Raised when update check/install fails."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_url: str
    asset_name: str
    asset_url: str
    notes: str


@dataclass(frozen=True)
class UpdateInstallPlan:
    version: str
    work_dir: Path
    archive_path: Path
    staged_app_path: Path
    target_app_path: Path
    script_path: Path


class UpdateManager:
    """Check for and install app updates from GitHub Releases."""

    def __init__(
        self,
        *,
        current_version: str = APP_VERSION,
        state_file: Path | None = None,
        current_app_path: Path | None = None,
    ):
        self.current_version = normalize_version(current_version)
        self.state_file = state_file or (CONFIG_DIR / "updater_state.json")
        self.current_app_path = current_app_path or bundled_app_path()

    def is_self_update_supported(self) -> bool:
        return self.current_app_path is not None and self.current_app_path.suffix == ".app"

    def should_check_for_updates(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        state = self._load_state()
        last_checked_at = float(state.get("last_checked_at", 0.0) or 0.0)
        if last_checked_at <= 0:
            return True
        return (now - last_checked_at) >= _CHECK_INTERVAL_S

    def mark_checked(self, checked_at: float | None = None):
        checked_at = checked_at if checked_at is not None else time.time()
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"last_checked_at": checked_at}))

    def fetch_available_update(self) -> UpdateInfo | None:
        try:
            response = httpx.get(
                _LATEST_RELEASE_URL,
                headers=self._headers(),
                follow_redirects=True,
                timeout=10.0,
            )
            if response.status_code == 404:
                self.mark_checked()
                return None
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise UpdateError("Could not reach GitHub Releases.") from exc

        self.mark_checked()

        latest_version = normalize_version(payload.get("tag_name", ""))
        if not latest_version:
            raise UpdateError("Latest release is missing a version tag.")

        if not is_newer_version(latest_version, self.current_version):
            return None

        asset = self._select_asset(payload.get("assets", []), latest_version)
        if asset is None:
            raise UpdateError(
                f"Release {latest_version} does not contain a usable zip asset."
            )

        return UpdateInfo(
            version=latest_version,
            release_url=payload.get("html_url", ""),
            asset_name=asset["name"],
            asset_url=asset["browser_download_url"],
            notes=payload.get("body", ""),
        )

    def prepare_update(self, update: UpdateInfo) -> UpdateInstallPlan:
        if not self.is_self_update_supported():
            raise UpdateError("Self-update is only available from the installed app bundle.")

        work_dir = Path(tempfile.mkdtemp(prefix="yap-update-"))
        archive_path = work_dir / update.asset_name
        extract_dir = work_dir / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            self._download_asset(update.asset_url, archive_path)
            try:
                subprocess.run(
                    ["ditto", "-x", "-k", str(archive_path), str(extract_dir)],
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                raise UpdateError("Downloaded update archive could not be unpacked.") from exc

            staged_app_path = extract_dir / f"{APP_NAME}.app"
            if not staged_app_path.exists():
                raise UpdateError("Downloaded update archive did not contain Yap.app.")

            target_app_path = self.current_app_path
            assert target_app_path is not None
            script_path = work_dir / "install-update.sh"
            self._write_installer_script(script_path)

            return UpdateInstallPlan(
                version=update.version,
                work_dir=work_dir,
                archive_path=archive_path,
                staged_app_path=staged_app_path,
                target_app_path=target_app_path,
                script_path=script_path,
            )
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise

    def launch_installer(self, plan: UpdateInstallPlan, *, current_pid: int | None = None):
        current_pid = current_pid if current_pid is not None else os.getpid()
        try:
            subprocess.Popen(
                [
                    "/bin/bash",
                    str(plan.script_path),
                    str(current_pid),
                    str(plan.staged_app_path),
                    str(plan.target_app_path),
                    str(plan.work_dir),
                ],
                start_new_session=True,
            )
        except OSError as exc:
            raise UpdateError("Could not launch the update installer helper.") from exc

    def _load_state(self) -> dict[str, float]:
        if not self.state_file.exists():
            return {}
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            logger.warning("Failed to parse updater state, resetting it")
            return {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{self.current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _select_asset(self, assets: list[dict], version: str) -> dict | None:
        expected_name = release_asset_name_for_version(version)
        for asset in assets:
            if asset.get("name") == expected_name:
                return asset

        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".zip") and APP_NAME.lower() in name:
                return asset

        return None

    def _download_asset(self, asset_url: str, archive_path: Path):
        try:
            with httpx.stream(
                "GET",
                asset_url,
                headers=self._headers(),
                follow_redirects=True,
                timeout=60.0,
            ) as response:
                response.raise_for_status()
                with archive_path.open("wb") as fh:
                    for chunk in response.iter_bytes():
                        if chunk:
                            fh.write(chunk)
        except httpx.HTTPError as exc:
            raise UpdateError("Could not download the update archive.") from exc

    def _write_installer_script(self, script_path: Path):
        script_path.write_text(
            """#!/bin/bash
set -euo pipefail

PID="$1"
STAGED_APP="$2"
TARGET_APP="$3"
WORK_DIR="$4"

fail() {
    /usr/bin/osascript -e 'display alert "Yap Update Failed" message "'"$1"'" as critical'
    exit 1
}

while /bin/kill -0 "$PID" 2>/dev/null; do
    /bin/sleep 0.25
done

/bin/sleep 0.5
/usr/bin/rm -rf "$TARGET_APP" || fail "Could not remove the previous app bundle."
/bin/cp -R "$STAGED_APP" "$TARGET_APP" || fail "Could not copy the updated app bundle. Check folder permissions."
/usr/bin/xattr -cr "$TARGET_APP" 2>/dev/null || true
/usr/bin/open "$TARGET_APP" || fail "The update installed, but Yap could not be relaunched."
/usr/bin/rm -rf "$WORK_DIR" 2>/dev/null || true
"""
        )
        script_path.chmod(
            script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
