"""Sound feedback for recording start/stop/error."""

import logging

import AppKit

from app.resources import get_resource_path

logger = logging.getLogger(__name__)

_START_PATH = str(get_resource_path("assets", "record_start.wav"))
_STOP_PATH = str(get_resource_path("assets", "record_stop.wav"))
_CLICK_PATH = str(get_resource_path("assets", "ui_click.wav"))


def _load_sound(path: str):
    sound = AppKit.NSSound.alloc().initWithContentsOfFile_byReference_(path, False)
    if sound is None:
        logger.error("Failed to load sound from %s", path)
    return sound


class SoundFeedback:
    """Plays subtle audio cues for recording events."""

    def __init__(self):
        fallback = _load_sound(_CLICK_PATH)
        self._start = _load_sound(_START_PATH) or fallback
        self._stop = _load_sound(_STOP_PATH) or fallback
        error_sound = AppKit.NSSound.soundNamed_("Basso")
        if error_sound is None:
            logger.error("Failed to load system error sound")
        self._error = error_sound

    def play_start(self):
        """Play rising chime when recording starts."""
        if self._start:
            self._start.stop()
            self._start.play()

    def play_stop(self):
        """Play falling chime when recording stops."""
        if self._stop:
            self._stop.stop()
            self._stop.play()

    def play_error(self):
        """Play system error sound when a dictation fails."""
        if self._error:
            self._error.stop()
            self._error.play()
