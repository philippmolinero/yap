"""Floating recording indicator — slim frosted bar at bottom of screen.

Recording: audio-reactive waveform bars (silent = flat, speaking = moving)
Processing: flowing circular spinner animation
"""

import logging
import math

import AppKit
import Quartz
import objc

logger = logging.getLogger(__name__)


class OverlayState:
    HIDDEN = "hidden"
    RECORDING = "recording"
    PROCESSING = "processing"


# Bar dimensions
_WIDTH = 80
_HEIGHT = 36
_CORNER_RADIUS = 18
_BOTTOM_MARGIN = 80

# Waveform config
_NUM_BARS = 5
_BAR_WIDTH = 4.0
_BAR_GAP = 5.0
_BAR_MAX_HEIGHT = 26.0
_BAR_MIN_HEIGHT = 3.0

# Spinner config
_SPINNER_RADIUS = 8.0
_SPINNER_DOT_COUNT = 8
_SPINNER_DOT_SIZE = 2.5


class WaveformView(AppKit.NSView):
    """Audio-reactive waveform bars. Pulls level from a provider callable."""

    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._animating = False
        self._timer = None
        self._level_provider = None  # callable returning 0.0-1.0
        self._bar_heights = [_BAR_MIN_HEIGHT] * _NUM_BARS
        self._phase = 0.0
        return self

    def setLevelProvider_(self, provider):
        """Set a callable that returns current audio level (0.0-1.0)."""
        self._level_provider = provider

    def drawRect_(self, rect):
        if not self._animating:
            return

        frame = self.frame()
        total_width = _NUM_BARS * _BAR_WIDTH + (_NUM_BARS - 1) * _BAR_GAP
        start_x = (frame.size.width - total_width) / 2

        for i in range(_NUM_BARS):
            h = self._bar_heights[i]
            x = start_x + i * (_BAR_WIDTH + _BAR_GAP)
            y = (frame.size.height - h) / 2

            alpha = 0.6 + 0.4 * (h - _BAR_MIN_HEIGHT) / max(_BAR_MAX_HEIGHT - _BAR_MIN_HEIGHT, 1)
            color = AppKit.NSColor.whiteColor().colorWithAlphaComponent_(alpha)
            color.setFill()

            path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                AppKit.NSMakeRect(x, y, _BAR_WIDTH, h),
                _BAR_WIDTH / 2,
                _BAR_WIDTH / 2,
            )
            path.fill()

    def startAnimating(self):
        self._animating = True
        self._phase = 0.0
        self._bar_heights = [_BAR_MIN_HEIGHT] * _NUM_BARS
        if self._timer is None:
            self._timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / 20.0, self, "tick:", None, True
            )

    def stopAnimating(self):
        self._animating = False
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self.setNeedsDisplay_(True)

    def tick_(self, timer):
        self._phase += 0.2
        level = self._level_provider() if self._level_provider else 0.0

        for i in range(_NUM_BARS):
            # Each bar gets a different target based on level + phase offset
            offset = i * 0.9
            variation = 0.3 + 0.7 * math.sin(self._phase + offset)
            target = _BAR_MIN_HEIGHT + (_BAR_MAX_HEIGHT - _BAR_MIN_HEIGHT) * level * variation

            # Snappy interpolation
            current = self._bar_heights[i]
            if target > current:
                self._bar_heights[i] = current + (target - current) * 0.6
            else:
                self._bar_heights[i] = current + (target - current) * 0.3

        self.setNeedsDisplay_(True)


class SpinnerView(AppKit.NSView):
    """Smooth flowing circular spinner for processing state."""

    def initWithFrame_(self, frame):
        self = objc.super(SpinnerView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._animating = False
        self._timer = None
        self._angle = 0.0
        return self

    def drawRect_(self, rect):
        if not self._animating:
            return

        frame = self.frame()
        cx = frame.size.width / 2
        cy = frame.size.height / 2

        for i in range(_SPINNER_DOT_COUNT):
            dot_angle = self._angle + (2 * math.pi * i / _SPINNER_DOT_COUNT)
            x = cx + _SPINNER_RADIUS * math.cos(dot_angle) - _SPINNER_DOT_SIZE / 2
            y = cy + _SPINNER_RADIUS * math.sin(dot_angle) - _SPINNER_DOT_SIZE / 2

            # Trail effect: dots closer to the "head" are more opaque
            alpha = 0.15 + 0.75 * (i / _SPINNER_DOT_COUNT)
            color = AppKit.NSColor.whiteColor().colorWithAlphaComponent_(alpha)
            color.setFill()

            path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
                AppKit.NSMakeRect(x, y, _SPINNER_DOT_SIZE, _SPINNER_DOT_SIZE)
            )
            path.fill()

    def startAnimating(self):
        self._animating = True
        self._angle = 0.0
        if self._timer is None:
            self._timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / 20.0, self, "tick:", None, True
            )

    def stopAnimating(self):
        self._animating = False
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self.setNeedsDisplay_(True)

    def tick_(self, timer):
        self._angle -= 0.1  # clockwise rotation
        self.setNeedsDisplay_(True)


class RecordingOverlay:
    """Slim frosted glass bar at the bottom of the screen."""

    def __init__(self):
        self._window = None
        self._waveform = None
        self._spinner = None
        self._state = OverlayState.HIDDEN
        self._level_provider = None
        self._setup()

    def set_level_provider(self, provider):
        """Set a callable that returns current audio level (0.0-1.0).
        The waveform will pull from this on each animation tick."""
        self._level_provider = provider
        self._waveform.setLevelProvider_(provider)

    def _setup(self):
        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()
        x = (screen_frame.size.width - _WIDTH) / 2
        y = _BOTTOM_MARGIN

        rect = AppKit.NSMakeRect(x, y, _WIDTH, _HEIGHT)

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(AppKit.NSFloatingWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)
        self._window.setAlphaValue_(0.0)
        self._window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )

        # Frosted glass background
        vibrancy = AppKit.NSVisualEffectView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, _WIDTH, _HEIGHT)
        )
        vibrancy.setMaterial_(AppKit.NSVisualEffectMaterialHUDWindow)
        vibrancy.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
        vibrancy.setState_(AppKit.NSVisualEffectStateActive)
        vibrancy.setWantsLayer_(True)
        vibrancy.layer().setCornerRadius_(_CORNER_RADIUS)
        vibrancy.layer().setMasksToBounds_(True)
        vibrancy.layer().setBorderColor_(
            AppKit.NSColor.colorWithWhite_alpha_(0.5, 0.4).CGColor()
        )
        vibrancy.layer().setBorderWidth_(1.0)
        vibrancy.setAlphaValue_(0.8)
        self._window.setContentView_(vibrancy)

        # Waveform (recording)
        self._waveform = WaveformView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, _WIDTH, _HEIGHT)
        )
        vibrancy.addSubview_(self._waveform)

        # Spinner (processing)
        self._spinner = SpinnerView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, _WIDTH, _HEIGHT)
        )
        vibrancy.addSubview_(self._spinner)

    def show(self, state: str):
        """Show overlay with given state."""
        self._state = state

        def _update():
            if state == OverlayState.RECORDING:
                self._waveform.setHidden_(False)
                self._waveform.startAnimating()
                self._spinner.stopAnimating()
                self._spinner.setHidden_(True)
            elif state == OverlayState.PROCESSING:
                self._waveform.stopAnimating()
                self._waveform.setHidden_(True)
                self._spinner.setHidden_(False)
                self._spinner.startAnimating()

            self._window.orderFrontRegardless()
            ctx = AppKit.NSAnimationContext.currentContext()
            ctx.setDuration_(0.15)
            self._window.animator().setAlphaValue_(1.0)

        if AppKit.NSThread.isMainThread():
            _update()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_update)

    def hide(self):
        """Hide the overlay with fade out."""
        self._state = OverlayState.HIDDEN

        def _update():
            self._waveform.stopAnimating()
            self._spinner.stopAnimating()
            ctx = AppKit.NSAnimationContext.currentContext()
            ctx.setDuration_(0.2)
            self._window.animator().setAlphaValue_(0.0)
            AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                0.25, False, lambda _: self._window.orderOut_(None)
            )

        if AppKit.NSThread.isMainThread():
            _update()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_update)



if __name__ == "__main__":
    import time
    import threading

    app = AppKit.NSApplication.sharedApplication()
    overlay = RecordingOverlay()

    def demo():
        time.sleep(0.5)
        print("Recording (simulated levels)...", flush=True)
        overlay.show(OverlayState.RECORDING)

        # Simulate audio levels
        for i in range(120):  # 4 seconds at 30fps
            level = 0.5 + 0.5 * math.sin(i * 0.1) if (i % 60) < 40 else 0.0
            overlay.update_audio_level(level)
            time.sleep(1.0 / 30)

        print("Processing...", flush=True)
        overlay.show(OverlayState.PROCESSING)
        time.sleep(3)
        print("Done.", flush=True)
        overlay.hide()
        time.sleep(1)
        from PyObjCTools import AppHelper
        AppHelper.stopEventLoop()

    threading.Thread(target=demo, daemon=True).start()

    from PyObjCTools import AppHelper
    AppHelper.runEventLoop()
