"""Clipboard + paste module: copy text and simulate Cmd+V in the active window."""

import subprocess
import time


def paste(text: str, delay_ms: int = 50):
    """Set clipboard via pbcopy and trigger Cmd+V via AppleScript.

    Raises subprocess.CalledProcessError if pbcopy fails.
    The Cmd+V keystroke may fail without Accessibility permission — in that
    case a warning is logged but we don't raise (the text is still on the clipboard).
    """
    import logging

    # Set clipboard
    subprocess.run(
        ["pbcopy"],
        input=text.encode("utf-8"),
        check=True,
    )

    # Brief delay to ensure clipboard is ready
    time.sleep(delay_ms / 1000.0)

    # Simulate Cmd+V
    result = subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "v" using command down',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logging.getLogger(__name__).warning(
            "Cmd+V keystroke failed (Accessibility permission needed?): %s",
            result.stderr.strip(),
        )


if __name__ == "__main__":
    print("Pasting test text in 2 seconds... switch to a text editor!")
    time.sleep(2)
    paste("Hello from Voxtral Dictation!")
    print("Done.")
