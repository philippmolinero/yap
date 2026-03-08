"""Yap — macOS menubar dictation app."""

import collections
import fcntl
import logging
import subprocess
import sys
import threading

import AppKit
import objc
import rumps

from app.cleanup import create_cleanup
from app.config import CONFIG_DIR, CONFIG_FILE, VOCAB_FILE, load_config
from app.hotkeys import HotkeyManager
from app.overlay import OverlayState, RecordingOverlay
from app.paster import paste
from app.pipeline import Pipeline, PipelineState
from app.recorder import Recorder
from app.resources import get_resource_path
from app.settings_dialog import SettingsDialog
from app.sounds import SoundFeedback
from app.transcriber import Transcriber
from app.updater import UpdateInfo, UpdateManager
from app.version import APP_NAME, APP_VERSION, bundled_app_path

logger = logging.getLogger(__name__)

_ICON_PATH = str(get_resource_path("assets", "icon_menubar.png"))


class _SleepWakeObserver(AppKit.NSObject):
    """NSObject subclass that receives NSWorkspace sleep/wake notifications."""

    def initWithApp_(self, app):
        self = objc.super(_SleepWakeObserver, self).init()
        if self is None:
            return None
        self._app = app
        return self

    def register(self):
        """Subscribe to sleep/wake notifications from NSWorkspace."""
        nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        nc.addObserver_selector_name_object_(
            self,
            objc.selector(self.handleWillSleep_, signature=b"v@:@"),
            AppKit.NSWorkspaceWillSleepNotification,
            None,
        )
        nc.addObserver_selector_name_object_(
            self,
            objc.selector(self.handleDidWake_, signature=b"v@:@"),
            AppKit.NSWorkspaceDidWakeNotification,
            None,
        )
        logger.info("Sleep/wake observer registered")

    def unregister(self):
        """Remove notification observers."""
        nc = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        nc.removeObserver_(self)
        logger.info("Sleep/wake observer unregistered")

    def handleWillSleep_(self, notification):
        try:
            logger.info("System going to sleep — stopping recording and event tap")
            app = self._app
            if app.pipeline.state == PipelineState.RECORDING or app.recorder.is_recording:
                logger.info("Active recording detected, cancelling before sleep")
                app.hotkey_mgr.reset()
                app.pipeline.cancel_recording(source="sleep")
            elif app.pipeline.state == PipelineState.PROCESSING:
                logger.info("Pipeline already processing during sleep")
            # Tear down the event tap
            app.hotkey_mgr.stop()
        except Exception:
            logger.exception("Error in sleep handler")

    def handleDidWake_(self, notification):
        try:
            logger.info("System woke from sleep — restarting event tap after delay")

            def _restart():
                try:
                    import time
                    time.sleep(1.0)
                    app = self._app
                    app.hotkey_mgr.start()
                    logger.info("Event tap restarted after wake")
                except Exception:
                    logger.exception("Error restarting event tap after wake")

            threading.Thread(target=_restart, daemon=True).start()
        except Exception:
            logger.exception("Error in wake handler")


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

        # Sound feedback
        self.sounds = SoundFeedback()

        # Dictation history (most recent first)
        self._history: collections.deque[str] = collections.deque(maxlen=15)

        # Settings dialog instance
        self._settings_dialog = None

        # Updater state
        self.updater = UpdateManager(current_app_path=bundled_app_path())
        self._available_update: UpdateInfo | None = None
        self._update_busy_title: str | None = None
        self._update_lock = threading.Lock()

        # Build pipeline components
        self._build_pipeline()

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

        # Sleep/wake observer — must be retained to prevent GC
        self._sleep_wake_observer = _SleepWakeObserver.alloc().initWithApp_(self)
        self._sleep_wake_observer.register()

        # Build menu
        self.status_item = rumps.MenuItem("Status: Idle", callback=None)
        self.status_item.set_callback(None)
        self.stop_item = rumps.MenuItem("Stop Recording", callback=self._on_stop_clicked)
        self.stop_item.set_callback(None)  # hidden until recording
        self.recent_menu = rumps.MenuItem("Recent")
        self.update_item = rumps.MenuItem("Check for Updates...", callback=self._on_update_item_clicked)
        self.menu = [
            self.status_item,
            self.stop_item,
            None,
            self.recent_menu,
            None,
            self.update_item,
            rumps.MenuItem("Settings...", callback=self._open_settings),
            rumps.MenuItem("Open Config", callback=self._open_config),
            rumps.MenuItem("Open Vocabulary", callback=self._open_vocabulary),
            None,
            rumps.MenuItem("Quit", callback=self._quit),
        ]
        self._refresh_update_item()

    def _build_pipeline(self):
        """Create recorder, transcriber, cleanup, and pipeline from current config."""
        if hasattr(self, "recorder") and self.recorder is not None:
            self.recorder.force_stop()
        self.recorder = Recorder(
            sample_rate=self.cfg.transcription.sample_rate,
            silence_timeout=self.cfg.silence.timeout,
            silence_threshold=self.cfg.silence.threshold,
        )
        self.recorder._on_silence = self._on_silence
        transcriber = Transcriber(
            api_key=self.cfg.mistral_api_key,
            model=self.cfg.transcription.model,
            vocabulary=self.cfg.vocabulary,
        )
        cleanup_key = {"groq": self.cfg.groq_api_key, "mistral": self.cfg.mistral_api_key}.get(
            self.cfg.cleanup.provider, ""
        )
        cleanup = create_cleanup(
            provider=self.cfg.cleanup.provider,
            api_key=cleanup_key,
            model=self.cfg.cleanup.model,
            enabled=self.cfg.cleanup.enabled,
        )

        self.pipeline = Pipeline(
            recorder=self.recorder,
            transcriber=transcriber,
            cleanup=cleanup,
            paste_delay_ms=self.cfg.paste.delay_ms,
            on_state_change=self._on_state_change,
            on_complete=self._on_dictation_complete,
        )

    def _on_hotkey_start(self):
        # Already running in a daemon thread (dispatched from HotkeyManager._handle_down)
        self.pipeline.start_recording(source="hotkey_down")

    def _on_hotkey_stop(self):
        # Already running in a daemon thread (dispatched from HotkeyManager._handle_up)
        self.pipeline.stop_recording_and_process(source="hotkey_up")

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

        # Safety net: if we reached IDLE but PortAudio is still active,
        # force-close the stream so the mic doesn't stay latched on.
        if state == PipelineState.IDLE and self.recorder.is_recording:
            logger.warning("Pipeline IDLE but recorder still active — force-stopping recorder")
            threading.Thread(
                target=self.pipeline.cancel_recording,
                kwargs={"source": "idle_safety_net"},
                daemon=True,
            ).start()

    def _on_stop_clicked(self, _):
        """Menu bar stop button — emergency escape hatch."""
        logger.info(
            "Emergency stop from menu bar (pipeline=%s, recorder_active=%s)",
            self.pipeline.state.value,
            self.recorder.is_recording,
        )
        # Immediately disable the button and reset hotkey state so
        # hold-to-talk doesn't re-trigger, before any blocking calls.
        self.stop_item.set_callback(None)
        self.hotkey_mgr.reset()

        threading.Thread(
            target=self.pipeline.cancel_recording,
            kwargs={"source": "menu_stop"},
            daemon=True,
        ).start()

    def _on_silence(self):
        """Called from recorder when silence exceeds timeout — auto-stop."""
        logger.info("Silence detected — auto-stopping")
        if self.pipeline.state != PipelineState.RECORDING:
            if self.recorder.is_recording:
                logger.warning("Silence callback while IDLE but recorder active — cancelling recorder")
                threading.Thread(
                    target=self.pipeline.cancel_recording,
                    kwargs={"source": "silence_desync"},
                    daemon=True,
                ).start()
            return
        self.hotkey_mgr.reset()
        threading.Thread(
            target=self.pipeline.stop_recording_and_process,
            kwargs={"source": "silence"},
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

    def _refresh_update_item(self):
        def update():
            if self._update_busy_title:
                self.update_item.title = self._update_busy_title
                self.update_item.set_callback(None)
            elif self._available_update is not None:
                self.update_item.title = f"Install Update {self._available_update.version}..."
                self.update_item.set_callback(self._on_update_item_clicked)
            else:
                self.update_item.title = "Check for Updates..."
                self.update_item.set_callback(self._on_update_item_clicked)

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(update)

    def _show_alert(
        self,
        title: str,
        message: str,
        *,
        style=AppKit.NSAlertStyleInformational,
    ):
        def show():
            try:
                alert = AppKit.NSAlert.alloc().init()
                alert.setMessageText_(title)
                alert.setInformativeText_(message)
                alert.setAlertStyle_(style)
                alert.addButtonWithTitle_("OK")
                alert.runModal()
            except Exception:
                logger.exception("Failed to show alert: %s", title)

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(show)

    def _show_confirm_alert(
        self,
        title: str,
        message: str,
        *,
        confirm_label: str,
        cancel_label: str,
        on_confirm,
    ):
        def show():
            try:
                alert = AppKit.NSAlert.alloc().init()
                alert.setMessageText_(title)
                alert.setInformativeText_(message)
                alert.setAlertStyle_(AppKit.NSAlertStyleInformational)
                alert.addButtonWithTitle_(confirm_label)
                alert.addButtonWithTitle_(cancel_label)
                response = alert.runModal()
                if response == AppKit.NSAlertFirstButtonReturn:
                    on_confirm()
            except Exception:
                logger.exception("Failed to show confirmation alert: %s", title)

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(show)

    def _on_update_item_clicked(self, _):
        if not self.updater.is_self_update_supported():
            self._show_alert(
                f"{APP_NAME} Update Unavailable",
                "Self-update only works from the installed Yap.app bundle.",
                style=AppKit.NSAlertStyleWarning,
            )
            return

        if self._available_update is not None:
            self._prompt_install_update(self._available_update)
            return

        threading.Thread(
            target=self._check_for_updates,
            kwargs={"interactive": True},
            daemon=True,
        ).start()

    def _check_for_updates(self, *, interactive: bool):
        if not self._update_lock.acquire(blocking=False):
            if interactive:
                self._show_alert(
                    "Update Check Already Running",
                    "Yap is already checking for updates.",
                )
            return

        self._update_busy_title = "Checking for Updates..."
        self._refresh_update_item()
        try:
            update = self.updater.fetch_available_update()
        except Exception as exc:
            logger.exception("Update check failed")
            if interactive:
                self._show_alert(
                    "Update Check Failed",
                    str(exc),
                    style=AppKit.NSAlertStyleWarning,
                )
            return
        finally:
            self._update_busy_title = None
            self._refresh_update_item()
            self._update_lock.release()

        self._available_update = update
        self._refresh_update_item()

        if update is None:
            if interactive:
                self._show_alert(
                    f"{APP_NAME} Is Up To Date",
                    f"You're already running version {APP_VERSION}.",
                )
            return

        logger.info("Update available: %s", update.version)
        if interactive:
            self._prompt_install_update(update)

    def _prompt_install_update(self, update: UpdateInfo):
        if self.pipeline.state != PipelineState.IDLE:
            self._show_alert(
                "Finish Dictation First",
                "Stop recording or wait for processing to finish before installing an update.",
                style=AppKit.NSAlertStyleWarning,
            )
            return

        self._show_confirm_alert(
            f"Install {APP_NAME} {update.version}?",
            (
                f"Version {update.version} is available.\n\n"
                f"{APP_NAME} will quit, install the update, and relaunch automatically."
            ),
            confirm_label="Install",
            cancel_label="Later",
            on_confirm=lambda: threading.Thread(
                target=self._install_update,
                args=(update,),
                daemon=True,
            ).start(),
        )

    def _install_update(self, update: UpdateInfo):
        if not self._update_lock.acquire(blocking=False):
            return

        self._update_busy_title = f"Installing Update {update.version}..."
        self._refresh_update_item()
        try:
            plan = self.updater.prepare_update(update)
            self.updater.launch_installer(plan)
        except Exception as exc:
            logger.exception("Update install failed")
            self._update_busy_title = None
            self._refresh_update_item()
            self._show_alert(
                "Update Failed",
                str(exc),
                style=AppKit.NSAlertStyleWarning,
            )
            return
        finally:
            self._update_lock.release()

        logger.info("Update staged successfully: %s", update.version)
        self._quit(None)

    def _open_settings(self, _):
        """Open the settings dialog."""
        self._settings_dialog = SettingsDialog(on_save=self._on_settings_saved)
        self._settings_dialog.show()

    def _on_settings_saved(self):
        """Callback after settings are saved — reload config and rebuild pipeline."""
        if self.pipeline.state != PipelineState.IDLE:
            logger.warning("Cannot reload config while recording is active")
            return
        logger.info("Settings saved, reloading config")
        self.cfg = load_config()
        self._build_pipeline()
        self.overlay.set_level_provider(lambda: self.recorder.audio_level)

    def _open_config(self, _):
        subprocess.Popen(["open", str(CONFIG_FILE)])

    def _open_vocabulary(self, _):
        subprocess.Popen(["open", str(VOCAB_FILE)])

    def _quit(self, _):
        self._sleep_wake_observer.unregister()
        self.hotkey_mgr.stop()
        rumps.quit_application()

    @rumps.timer(0.1)
    def _start_hotkey_once(self, timer):
        timer.stop()
        self.hotkey_mgr.start()
        logger.info("Hotkey manager startup requested")

        if self.updater.is_self_update_supported() and self.updater.should_check_for_updates():
            threading.Thread(
                target=self._check_for_updates,
                kwargs={"interactive": False},
                daemon=True,
            ).start()

        # Check for missing API keys after startup — auto-open settings
        if not self.cfg.mistral_api_key:
            logger.warning("Mistral API key not set — opening Settings")
            self._open_settings(None)



_lock_file = None


def _acquire_single_instance_lock():
    """Ensure only one instance of Yap is running. Exits if another is found."""
    global _lock_file
    lock_path = CONFIG_DIR / ".yap.lock"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _lock_file = open(lock_path, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("Yap is already running.", file=sys.stderr)
        sys.exit(0)


def main():
    # Log to file when running as a bundle (no terminal to see stdout)
    log_file = CONFIG_DIR / "yap.log" if getattr(sys, "_MEIPASS", None) else None
    handlers = []
    if log_file:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="w"))
    handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    _acquire_single_instance_lock()
    app = YapApp()
    app.run()


if __name__ == "__main__":
    main()
