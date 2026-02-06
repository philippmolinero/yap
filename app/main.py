"""Yap — macOS menubar dictation app."""

import collections
import logging
import os
import subprocess
import threading

import AppKit
import rumps

from app.cleanup import create_cleanup
from app.config import CONFIG_FILE, VOCAB_FILE, load_config
from app.hotkeys import HotkeyManager
from app.overlay import OverlayState, RecordingOverlay
from app.paster import paste
from app.pipeline import Pipeline, PipelineState
from app.recorder import Recorder
from app.sounds import SoundFeedback
from app.transcriber import Transcriber

logger = logging.getLogger(__name__)

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_ICON_PATH = os.path.join(_ASSETS_DIR, "icon_menubar.png")


class YapApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Yap",
            icon=_ICON_PATH,
            template=True,
            quit_button=None,
        )

        # Load config
        self.cfg = load_config()

        # Validate API keys
        if not self.cfg.mistral_api_key:
            rumps.notification(
                "Yap",
                "Missing API Key",
                "MISTRAL_API_KEY not set. Check your .env file.",
            )

        # Sound feedback
        self.sounds = SoundFeedback()

        # Dictation history (most recent first)
        self._history: collections.deque[str] = collections.deque(maxlen=15)

        # Build pipeline components
        self.recorder = Recorder(
            sample_rate=self.cfg.transcription.sample_rate,
            silence_timeout=self.cfg.silence.timeout,
            silence_threshold=self.cfg.silence.threshold,
        )
        self.recorder._on_silence = self._on_silence
        recorder = self.recorder
        transcriber = Transcriber(
            api_key=self.cfg.mistral_api_key,
            model=self.cfg.transcription.model,
            vocabulary=self.cfg.vocabulary,
        )
        cleanup = create_cleanup(
            provider=self.cfg.cleanup.provider,
            api_key=self.cfg.groq_api_key,
            model=self.cfg.cleanup.model,
            enabled=self.cfg.cleanup.enabled,
        )

        self.pipeline = Pipeline(
            recorder=recorder,
            transcriber=transcriber,
            cleanup=cleanup,
            paste_delay_ms=self.cfg.paste.delay_ms,
            on_state_change=self._on_state_change,
            on_complete=self._on_dictation_complete,
        )

        # Overlay — waveform pulls audio level directly from recorder
        self.overlay = RecordingOverlay()
        self.overlay.set_level_provider(lambda: self.recorder.audio_level)

        # Hotkey manager
        self.hotkey_mgr = HotkeyManager(
            on_start=self._on_hotkey_start,
            on_stop=self._on_hotkey_stop,
            keycode=self.cfg.hotkey.keycode,
            double_tap_ms=self.cfg.hotkey.double_tap_ms,
        )

        # Build menu
        self.status_item = rumps.MenuItem("Status: Idle", callback=None)
        self.status_item.set_callback(None)
        self.stop_item = rumps.MenuItem("Stop Recording", callback=self._on_stop_clicked)
        self.stop_item.set_callback(None)  # hidden until recording
        self.recent_menu = rumps.MenuItem("Recent")
        self.menu = [
            self.status_item,
            self.stop_item,
            None,
            self.recent_menu,
            None,
            rumps.MenuItem("Open Config", callback=self._open_config),
            rumps.MenuItem("Open Vocabulary", callback=self._open_vocabulary),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _on_hotkey_start(self):
        self.pipeline.start_recording()

    def _on_hotkey_stop(self):
        threading.Thread(
            target=self.pipeline.stop_recording_and_process,
            daemon=True,
        ).start()

    def _on_state_change(self, state: PipelineState):
        if state == PipelineState.RECORDING:
            self.sounds.play_start()
        elif state == PipelineState.PROCESSING:
            self.sounds.play_stop()

        status_text = f"Status: {state.value.capitalize()}"

        def update():
            self.status_item.title = status_text
            if state == PipelineState.RECORDING:
                self.stop_item.set_callback(self._on_stop_clicked)
                self.overlay.show(OverlayState.RECORDING)
            elif state == PipelineState.PROCESSING:
                self.stop_item.set_callback(None)
                self.overlay.show(OverlayState.PROCESSING)
            else:
                self.stop_item.set_callback(None)
                self.overlay.hide()

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(update)

    def _on_stop_clicked(self, _):
        """Menu bar stop button — emergency escape hatch."""
        logger.info("Manual stop from menu bar")
        self.hotkey_mgr.reset()
        threading.Thread(
            target=self.pipeline.stop_recording_and_process,
            daemon=True,
        ).start()

    def _on_silence(self):
        """Called from recorder when silence exceeds timeout — auto-stop."""
        logger.info("Silence detected — auto-stopping")
        self.hotkey_mgr.reset()
        threading.Thread(
            target=self.pipeline.stop_recording_and_process,
            daemon=True,
        ).start()

    def _on_dictation_complete(self, text: str):
        """Called after a successful dictation paste — update history."""
        self._history.appendleft(text)
        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
            self._rebuild_recent_menu
        )

    def _rebuild_recent_menu(self):
        """Rebuild the Recent submenu from history."""
        for key in list(self.recent_menu.keys()):
            del self.recent_menu[key]
        for i, text in enumerate(self._history):
            label = text[:50] + "..." if len(text) > 50 else text
            key = f"recent_{i}"
            item = rumps.MenuItem(label, callback=self._on_recent_click)
            item._full_text = text
            self.recent_menu[key] = item

    def _on_recent_click(self, sender):
        """Re-paste a previous dictation."""
        text = getattr(sender, "_full_text", sender.title)
        threading.Thread(
            target=paste,
            args=(text, self.cfg.paste.delay_ms),
            daemon=True,
        ).start()

    def _open_config(self, _):
        subprocess.Popen(["open", str(CONFIG_FILE)])

    def _open_vocabulary(self, _):
        subprocess.Popen(["open", str(VOCAB_FILE)])

    def _quit(self, _):
        self.hotkey_mgr.stop()
        rumps.quit_application()

    @rumps.timer(0.1)
    def _start_hotkey_once(self, timer):
        timer.stop()
        self.hotkey_mgr.start()
        logger.info("Hotkey manager started")



def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    app = YapApp()
    app.run()


if __name__ == "__main__":
    main()
