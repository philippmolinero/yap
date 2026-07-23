# Yap install monitor findings - 2026-06-22

## Outcome

- Rebuilt `dist/Yap.app` from the local Python 3.12 `.venv`.
- Installed the bundle to `/Applications/Yap.app`.
- Normal LaunchServices launch now stays alive after writing API keys from the repo `.env` into `~/.config/yap/secrets.toml`.
- Follow-up build installed after making missing API keys a recoverable startup state.
- Current startup log:
  - Sleep/wake observer registered.
  - Hotkey manager startup requested.
  - Input Monitoring permission missing and waiting for grant after ad-hoc rebuild.

## Findings

- `./update.sh` and `./build.sh` failed because shell scripts and `.command` launchers did not have executable bits set.
- The local system `python3` is Python 3.9.6, but the repo requires Python 3.11+ features (`tomllib`, PEP 604 union types). Tests should be run through the Python 3.12 `.venv`.
- `pytest` was not declared in `requirements.txt`, so the documented test command could not run from a fresh environment.
- PyObjC 12 is a bad dependency choice for this setup; pip warned about incorrect Python 3.9 support metadata and native build failed under the system Python. Pinning PyObjC below 12 avoids that path.
- PyInstaller needs Pillow to convert `assets/icon_app.png` into a macOS bundle icon.
- A bundled app launched from `/Applications` does not see the repo `.env`. Without `~/.config/yap/secrets.toml`, startup crashes before opening Settings:
  - `ValueError: GROQ_API_KEY is required for Groq transcription`
- Build completed with ad-hoc signing because no code-signing identity was available. macOS may require fresh Input Monitoring and Accessibility grants after each rebuild.
- `spctl --assess` reported an internal code-signing subsystem error on the ad-hoc bundle. Direct execution and LaunchServices launch work after secrets are present, but release builds should use a stable signing identity.
- Creating a self-signed local code-signing identity requires trusting a certificate in the user's login keychain. That is a persistent security change and should only be done after explicit user approval.
- Two untrusted `Yap Local Codesign` certificate entries were left in the login keychain from setup attempts before the trust step was blocked. They are not valid signing identities and should be removed in Keychain Access before retrying local signing setup.
- A valid `Yap Local Codesign` identity was later created and `build.sh` used it to sign `dist/Yap.app`. The installed app runs, but `codesign --verify --deep --strict` still reports `CSSMERR_TP_NOT_TRUSTED`; resolving that likely requires trusting the self-signed certificate in the System keychain, which is a broader machine-wide trust change.

## Locked In

- Added missing test/build dependencies to `requirements.txt`:
  - `pytest`
  - `Pillow`
  - `pyobjc-core<12`
  - `pyobjc-framework-Quartz<12`
  - `pyobjc-framework-Cocoa<12`
- Created a local Python 3.12 `.venv` and verified:
  - `.venv/bin/python -m pytest -q`
  - `93 passed`
- Set executable bits on:
  - `build.sh`
  - `create_dmg.sh`
  - `install.sh`
  - `release.sh`
  - `uninstall.sh`
  - `update.sh`
  - `install.command`
  - `update.command`
- Added `scripts/create_local_codesign_identity.sh` to create a self-signed `Yap Local Codesign` identity for users who approve local Keychain trust. The script now requires `--trust` before modifying trust settings.
- Changed app startup so missing transcription API keys no longer crash the menubar app. Yap starts, marks dictation unavailable, opens Settings, and blocks hotkey recording until keys are configured.
- Created the local `Yap Local Codesign` identity and rebuilt/reinstalled the app signed with that identity.

## Improvement Candidates

- For local signing, remove stale untrusted `Yap Local Codesign` certs in Keychain Access, then run `scripts/create_local_codesign_identity.sh --trust` only after accepting the trust tradeoff for a self-signed code-signing root in the login keychain.
- If strict `codesign`/Gatekeeper verification is required, explicitly approve adding the local self-signed certificate to `/Library/Keychains/System.keychain`; otherwise, keep the narrower login-keychain setup and accept that the app is signed but not fully trusted by system assessment.
- Add a bootstrap check in `update.sh` that verifies it is executable and that `build.sh` is executable, or invoke sibling scripts through `bash`.
- Add a documented Python version requirement, ideally with `.python-version` or a `pyproject.toml` `requires-python`.
- Consider committing a native `.icns` app icon so PyInstaller does not depend on Pillow for bundle creation.
- Add a release/build preflight that warns when no stable code-signing identity is found.
- Add a post-install smoke check that verifies the app process remains alive and prints the last lines of `~/.config/yap/yap.log` on failure.
