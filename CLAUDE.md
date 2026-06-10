# Yap — macOS Menubar Dictation App

## About
Yap is a lightweight macOS menubar app for voice dictation. Hold Right Option to record, release to transcribe and paste text into the active app. Designed for fast, low-friction dictation — no windows, no UI chrome, just a subtle overlay and audio feedback. Uses Voxtral (Mistral) for transcription and Groq LLM for transcript cleanup (filler removal, punctuation). Supports hold-to-talk and double-tap toggle modes, silence auto-stop, and a history of recent dictations.

## Naming
- Project directory: `yap/`
- Config directory: `~/.config/yap/` (migrated from `~/.config/voxtral-dictation/`)

## Quick Reference
- Run: `python3 -m app.main` from project root (dev), or `open dist/Yap.app` (bundled)
- Build: `./build.sh` (creates dist/Yap.app), `./create_dmg.sh` (creates DMG)
- Release: `./release.sh` (build + DMG + GitHub release with zip + DMG assets)
- Update/Reinstall: `./update.sh` (stop old app, rebuild, reinstall, relaunch)
- Full reset update: `./update.sh --full-clean` (also wipes config/backups + resets TCC)
- Fast reinstall without build: `./update.sh --skip-build`
- Finder launcher: double-click `update.command`
- Config: `~/.config/yap/config.toml` (user), `config/default.toml` (bundled defaults)
- Secrets: `~/.config/yap/secrets.toml` (API keys, managed via Settings dialog)
- Logs: `~/.config/yap/yap.log` (bundled app only, overwritten each launch)
- History: `~/.config/yap/history.json` (persisted recent dictations)
- Failed recording rescue: `~/.config/yap/last_failed_recording.wav` (kept for "Retry Failed Dictation" menu item after a transcription failure)
- Env vars: `MISTRAL_API_KEY`, `GROQ_API_KEY` in `.env` (dev fallback)

## Update Workflow
- Day-to-day updates: run `./update.sh`
- Publish a release: run `./release.sh`
- Deep cleanup when permissions/state feel broken: run `./update.sh --full-clean`
- If paste stops working after update, re-enable Accessibility for `Yap`
- If hotkey stops working after update, re-enable Input Monitoring for `Yap`
- After `--full-clean`, you must re-enter API keys in Settings

## Architecture
- Pipeline: hotkey → recorder → transcriber (Voxtral/Groq, with retry on transient errors) → cleanup (Groq) → paster (NSPasteboard + native CGEvent Cmd+V, osascript fallback)
- Transcription failures stash the WAV to `last_failed_recording.wav` and fire the pipeline `on_error` callback (error sound + "Retry Failed Dictation" menu item)
- UI: rumps menubar app + frosted glass overlay (AppKit/NSVisualEffectView) + settings dialog (NSWindow)
- Hotkeys: Quartz CGEventTap on Right Option (hold-to-talk + double-tap toggle)
- Resources: `app/resources.py` resolves paths for both dev mode and PyInstaller bundles (`sys._MEIPASS`)
- Packaging: PyInstaller via `yap.spec`, entry point `run.py`, build scripts in project root
- Single instance: `fcntl.flock` on `~/.config/yap/.yap.lock`

## macOS Permissions (CRITICAL)
Three separate permissions are required. Getting these wrong causes silent failures.

| Permission | System Settings Panel | What it's for | API to check |
|---|---|---|---|
| Input Monitoring | Privacy & Security > Input Monitoring | CGEventTap hotkey listening | `CGPreflightListenEventAccess()` |
| Microphone | Privacy & Security > Microphone | Audio recording | macOS prompts automatically |
| Accessibility | Privacy & Security > Accessibility | Paste via Cmd+V (osascript) | `AXIsProcessTrusted()` |

- **Input Monitoring ≠ Accessibility**: `kCGEventTapOptionListenOnly` requires Input Monitoring, NOT Accessibility. `AXIsProcessTrustedWithOptions` checks Accessibility only — do NOT use it for event taps.
- **Use `CGPreflightListenEventAccess()` / `CGRequestListenEventAccess()`** (in `Quartz`) to check/request Input Monitoring.
- **`CGEventTapCreate` returns non-None even without permission** — events just silently never arrive. Always check `CGPreflightListenEventAccess()` first.
- **`ApplicationServices` module not bundled by PyInstaller** — access functions through `Quartz` or `ctypes` instead.
- **Terminal inherits permissions**: Running from Terminal works because Terminal has its own Input Monitoring grant. Finder-launched apps need their own.
- **TCC entries go stale on rebuild** only for ad-hoc signatures. Builds are signed with the self-signed "Yap Local Codesign" keychain identity (build.sh auto-detects it; cert PEM kept at `~/.config/yap/yap-codesign-cert.pem`), so permissions persist across rebuilds. If the identity is missing on a new machine, recreate it (self-signed cert with codeSigning EKU, trust via `security add-trusted-cert -p codeSign`) or grants reset every build; stale entries can be cleared with `tccutil reset ListenEvent com.yap.dictation`.
- **`com.apple.provenance` is immutable on macOS 26**: `xattr -cr` cannot remove it. Don't waste time trying.
- **Event tap timeout**: macOS disables slow taps. Handle `kCGEventTapDisabledByTimeout` in callback and re-enable.
- The app polls `CGPreflightListenEventAccess()` every 2s so it auto-activates after the user grants Input Monitoring — no relaunch needed.

## Critical Gotchas
- **PyObjC + exceptions**: Python exceptions inside `addOperationWithBlock_` crash the app (SIGABRT). Never let exceptions escape blocks dispatched to `NSOperationQueue.mainQueue()`.
- **NSObject for button targets**: Plain Python classes can't be `setTarget_()` targets. Use an NSObject subclass with `@objc.IBAction` methods.
- **rumps MenuItem**: Inherits from `OrderedDict` — use `menu[key] = MenuItem(...)` to add sub-items, NOT `.add()`. `menu.clear()` crashes if submenu NSMenu hasn't been created yet; delete by key instead.
- **rumps callback visibility**: `set_callback(None)` greys out a menu item, `set_callback(fn)` re-enables it.
- **rumps.notification unreliable**: macOS notification permissions for bundled Python apps are often suppressed. Use in-window feedback instead.
- **Thread safety**: `_on_silence` fires from sounddevice audio callback thread. Always dispatch UI work to main queue. `NSSound.play()/stop()` are thread-safe.

## Code Style
- Dataclass configs in `app/config.py`, loaded from TOML sections
- Callbacks wired via constructor params (`on_state_change`, `on_complete`, `_on_silence`)
- Background work via `threading.Thread(target=..., daemon=True).start()`
- Main thread dispatch: `AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(fn)`

## Development
- Working directory may be `~/Lab/personal/` (parent), not the project root — use full paths or `git -C` for git commands
- Tests: `pytest tests/` — 33 tests covering config, resources, settings dialog, integration
- Debug bundled app: check `~/.config/yap/yap.log`
- After rebuilding, reset stale TCC: `tccutil reset ListenEvent com.yap.dictation`

## Git
- Personal repo: `philippmolinero/yap` (canonical for code, releases, and in-app updater). The old `philippmoeller-fr/yap` repo is stale — do not push or release there.
