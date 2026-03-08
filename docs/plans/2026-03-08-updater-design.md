# Yap Updater Design

Yap currently ships as an unsigned PyInstaller menubar app. The existing update path is `./update.sh`, which rebuilds and replaces `/Applications/Yap.app` from the terminal. That works for local development, but it is not a product update mechanism because the installed app cannot discover or install a new release by itself.

There are two viable directions:

1. Sparkle: native macOS updater, but it assumes a signed/notarized app, signed archives, and an appcast feed.
2. GitHub Releases self-updater: the app checks the latest GitHub release, downloads a prepared archive, stages it locally, quits, and lets a helper replace the bundle and relaunch it.

The recommended path for the current project is the GitHub Releases updater. It matches the existing release model, avoids introducing incomplete Sparkle integration before signing exists, and can be implemented cleanly inside the current PyInstaller bundle.

Architecture:

- `app/version.py` is the single source of truth for the app version and release asset naming.
- `app/updater.py` checks GitHub Releases, compares versions, downloads `Yap-<version>.zip`, expands it, and writes a small installer helper script.
- `app/main.py` exposes the updater through a menu item, performs background checks once per day, and only allows install while the dictation pipeline is idle.
- `build.sh` always emits the zip asset the updater expects.

Failure handling:

- Network and archive failures become user-friendly alerts.
- The installer runs in a helper after the app quits, so the running bundle never tries to overwrite itself in place.
- If the app is not running from `Yap.app`, self-update is disabled.
