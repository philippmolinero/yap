# Yap Update Workflow

Use this to update/reinstall Yap without manual cleanup steps.

## In-App Updates

Bundled `Yap.app` now supports checking GitHub Releases directly from the menu bar app:

- `Check for Updates...` checks the latest GitHub release
- If a newer release exists, the menu item changes to `Install Update <version>...`
- Installing an update downloads the release zip, quits Yap, replaces the current `Yap.app`, and relaunches it

Release requirement:

- GitHub Releases must include a zip asset named `Yap-<version>.zip`

`./build.sh` now produces that zip automatically in `dist/`.

## Publish a Release

```bash
./release.sh
```

What it does:
- Verifies `gh` auth is available
- Refuses to release from a dirty git worktree by default
- Builds `dist/Yap.app`, `dist/Yap-<version>.zip`, and `dist/Yap-<version>.dmg`
- Creates or updates GitHub release `v<version>`
- Uploads the zip and DMG assets the app/updater expects

Useful flags:
- `--skip-build`: reuse existing `dist/` artifacts
- `--draft`: create or keep the release as a draft
- `--prerelease`: mark the release as a prerelease
- `--notes-file PATH`: provide explicit release notes
- `--allow-dirty`: override the clean-worktree guard

## Standard Update

```bash
./update.sh
```

What it does:
- Stops running Yap instances
- Removes old `/Applications/Yap.app`
- Builds a fresh `dist/Yap.app`
- Builds `dist/Yap-<version>.zip` for GitHub Releases / in-app updates
- Reinstalls to `/Applications/Yap.app`
- Launches Yap

## Full Reset Update

```bash
./update.sh --full-clean
```

Also does:
- Removes `~/.config/yap` and legacy `~/.config/voxtral-dictation`
- Removes `~/.config/yap.backup.*`
- Resets TCC for `com.yap.dictation` (best effort)

Use this when permissions/state are broken and standard update is not enough.

## Fast Reinstall (No Build)

```bash
./update.sh --skip-build
```

Useful when `dist/Yap.app` is already built.

## Finder Shortcut

Double-click:

```text
update.command
```

## Permission Checklist

After reinstall, verify:
- Input Monitoring: needed for hotkey listening
- Accessibility: needed for Cmd+V paste
- Microphone: needed for recording

If hotkey fails, check `Input Monitoring`.
If transcript appears in logs but nothing is inserted, check `Accessibility`.
