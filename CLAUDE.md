# Yap — macOS Menubar Dictation App

## About
Yap is a lightweight macOS menubar app for voice dictation. Hold Right Option to record, release to transcribe and paste text into the active app. Designed for fast, low-friction dictation — no windows, no UI chrome, just a subtle overlay and audio feedback. Uses Voxtral (Mistral) for transcription and Groq LLM for transcript cleanup (filler removal, punctuation). Supports hold-to-talk and double-tap toggle modes, silence auto-stop, and a history of recent dictations.

## Naming
- Project directory: `yap/`
- Config directory: `~/.config/yap/` (migrated from `~/.config/voxtral-dictation/`)

## Quick Reference
- Run: `python3 -m app.main` from project root (dev), or `open dist/Yap.app` (bundled)
- Build: `./build.sh` (creates dist/Yap.app), `./create_dmg.sh` (creates DMG)
- Config: `~/.config/yap/config.toml` (user), `config/default.toml` (bundled defaults)
- Secrets: `~/.config/yap/secrets.toml` (API keys, managed via Settings dialog)
- Env vars: `MISTRAL_API_KEY`, `GROQ_API_KEY` in `.env` (dev fallback)

## Architecture
- Pipeline: hotkey → recorder → transcriber (Voxtral) → cleanup (Groq) → paster (pbcopy + Cmd+V)
- UI: rumps menubar app + frosted glass overlay (AppKit/NSVisualEffectView) + settings dialog (NSWindow)
- Hotkeys: Quartz CGEventTap on Right Option (hold-to-talk + double-tap toggle)
- Resources: `app/resources.py` resolves paths for both dev mode and py2app bundles
- Packaging: py2app via `setup.py`, entry point `run.py`, build scripts in project root

## Critical Gotchas
- **PyObjC + exceptions**: Python exceptions inside `addOperationWithBlock_` crash the app (SIGABRT). Never let exceptions escape blocks dispatched to `NSOperationQueue.mainQueue()`.
- **rumps MenuItem**: Inherits from `OrderedDict` — use `menu[key] = MenuItem(...)` to add sub-items, NOT `.add()`. `menu.clear()` crashes if submenu NSMenu hasn't been created yet (no items added); delete by key instead.
- **rumps callback visibility**: `set_callback(None)` greys out a menu item, `set_callback(fn)` re-enables it.
- **Thread safety**: `_on_silence` fires from sounddevice audio callback thread. Always dispatch UI work to main queue. `NSSound.play()/stop()` are thread-safe.

## Code Style
- Dataclass configs in `app/config.py`, loaded from TOML sections
- Callbacks wired via constructor params (`on_state_change`, `on_complete`, `_on_silence`)
- Background work via `threading.Thread(target=..., daemon=True).start()`
- Main thread dispatch: `AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(fn)`

## Development
- Working directory may be `~/Lab/personal/` (parent), not the project root — use full paths or `git -C` for git commands
- No test suite yet — verify manually with `python3 -m app.main`

## Git
- Personal repo under `philippmolinero` GitHub account
