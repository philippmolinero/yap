"""Sound feedback for recording start/stop."""

import logging

import AppKit

from app.resources import get_resource_path

logger = logging.getLogger(__name__)

_CLICK_PATH = str(get_resource_path("assets", "ui_click.wav"))


class SoundFeedback:
    """Plays subtle audio cues for recording events."""

    def __init__(self):
        sound = AppKit.NSSound.alloc().initWithContentsOfFile_byReference_(
            _CLICK_PATH, False
        )
        if sound is None:
            logger.error("Failed to load click sound from %s", _CLICK_PATH)
        self._click = sound

    def play_start(self):
        """Play click when recording starts."""
        if self._click:
            self._click.stop()
            self._click.play()

    def play_stop(self):
        """Play click when recording stops."""
        if self._click:
            self._click.stop()
            self._click.play()
