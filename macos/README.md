# Yap

Native macOS menubar dictation. Hold the trigger, speak, release — the text
appears in whatever app you were using.

## How it works

Press and hold **Right Option** or **Right Control** to dictate (push-to-talk),
or **double-tap** the trigger for hands-free mode (tap again to stop). While you
hold, audio streams to Gemini Live; on release the finalized text is pasted into
the app that was focused at key-down. Your clipboard is restored afterwards, and
after a few seconds of silence the recording stops on its own.

## Layout

| Target        | Contents |
|---------------|----------|
| `YapCore`     | UI-free engine: config + TOML, Keychain secrets, Gemini live/unary clients, pipeline state machine, WAV codec, history, metrics |
| `Yap`         | App shell: SwiftUI menu bar + Settings, overlay capsule, AVAudioEngine capture, CGEventTap hotkey, paste |
| `YapCoreTests`| Test runner and suite (see below) |

## Build and run

```sh
./build-app.sh              # builds dist/Yap.app (signed "Yap Local Codesign" when available)
./build-app.sh --install    # additionally copies to /Applications/Yap.app
./build-app.sh --run        # additionally launches it
swift run Yap               # run without bundling (uses the same ~/.config/yap)
```

## Tests

```sh
swift run YapCoreTests      # exit code 0 = all green
```

The Command Line Tools toolchain ships neither swift-testing nor XCTest, so the
suite runs through a small self-contained runner in `Sources/YapCoreTests`.
Tests use temporary directories and `YAP_CONFIG_DIR`, never the real config.

Covered: TOML editing, config round-trips, Keychain migration and blocked-read
fallback, WAV codec, history, metrics schema (privacy), language mapping, Gemini
payload shaping, and the full pipeline state machine with fakes (live turn,
fallback to unary, empty audio/transcript, failure stash + retry, cancel,
silence auto-stop, clipboard-only paste).

## CLI

```sh
Yap.app/Contents/MacOS/Yap --doctor              # config, key source, permissions
Yap.app/Contents/MacOS/Yap --transcribe file.wav # stream a file through the live pipeline
```

`--transcribe` is the end-to-end check for the transcription chain.

## Configuration

Lives in `~/.config/yap/` and is shared with older Yap versions:

- `config.toml` — trigger keys, mode (`smart`/`verbatim`), language hint,
  silence auto-stop, paste delay. Settings rewrites only the keys Yap manages.
- `vocabulary.txt` — preferred spellings sent as Gemini custom vocabulary.
- `history.json`, `pipeline_metrics.jsonl` (timings only, never text), `yap.log`

The Gemini API key is stored in the **Keychain** (`com.yap.dictation.gemini-key`).
A key found in the legacy `secrets.toml` is migrated automatically; environment
variables `GEMINI_API_KEY`/`GOOGLE_API_KEY` work as a development fallback.

> Note: builds signed with the self-signed "Yap Local Codesign" certificate may
> show a Keychain authorization dialog the first time a *new* binary reads the
> key ("Always Allow" settles it). Yap never blocks on that dialog — it falls
> back to `secrets.toml`/environment for the run. Developer ID-signed releases
> do not prompt.

## Permissions

| Permission        | For |
|-------------------|-----|
| Input Monitoring  | hearing the trigger key system-wide |
| Microphone        | dictation |
| Accessibility     | posting Cmd+V into the focused app |

The Settings pane shows all three with request/open buttons; the menu status
line reports what is missing.
