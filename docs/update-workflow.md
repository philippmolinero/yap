# Yap Update Workflow

Use this to update/reinstall Yap without manual cleanup steps.

## Standard Update

```bash
./update.sh
```

What it does:
- Stops running Yap instances
- Removes old `/Applications/Yap.app`
- Builds a fresh `dist/Yap.app`
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
