import math
import subprocess
import sys
import time
from pathlib import Path

import AppKit
from PyObjCTools import AppHelper

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.overlay import OverlayState, RecordingOverlay


OUTPUT_DIR = Path(".tmp/overlay-qa").resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

level = {"value": 0.0}
started_at = time.monotonic()


def audio_level():
    elapsed = time.monotonic() - started_at
    return 0.32 + 0.34 * (0.5 + 0.5 * math.sin(elapsed * 5.4))


def capture(name):
    path = OUTPUT_DIR / name
    subprocess.run(["screencapture", "-x", str(path)], check=True)
    print(path, flush=True)


def main():
    AppKit.NSApplication.sharedApplication()
    overlay = RecordingOverlay()
    overlay.set_level_provider(audio_level)

    overlay.show(OverlayState.RECORDING)
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        1.2,
        False,
        lambda _: capture("recording-full.png"),
    )
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        2.0,
        False,
        lambda _: overlay.show(OverlayState.PROCESSING),
    )
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        2.7,
        False,
        lambda _: capture("processing-full.png"),
    )
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        3.1,
        False,
        lambda _: overlay.hide(),
    )
    AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
        3.5,
        False,
        lambda _: AppHelper.stopEventLoop(),
    )

    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
