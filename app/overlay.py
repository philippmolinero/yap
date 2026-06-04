"""Floating recording indicator — charcoal capsule at bottom of screen.

Recording: status dot, label, and audio-reactive waveform
Processing: compact flowing circular spinner animation
"""

import logging
import math
import time

import AppKit
import objc

logger = logging.getLogger(__name__)


class OverlayState:
    HIDDEN = "hidden"
    RECORDING = "recording"
    PROCESSING = "processing"


# Capsule dimensions
_WIDTH = 286
_HEIGHT = 46
_CORNER_RADIUS = 23
_BOTTOM_MARGIN = 80
_GLOW_PADDING = 12
_WINDOW_WIDTH = _WIDTH + _GLOW_PADDING * 2
_WINDOW_HEIGHT = _HEIGHT + _GLOW_PADDING * 2
_MIN_REVEAL_WIDTH = 46
_COMPACT_WIDTH = 166
_COMPACT_PROGRESS = (_COMPACT_WIDTH - _MIN_REVEAL_WIDTH) / (_WIDTH - _MIN_REVEAL_WIDTH)
_PROCESSING_WIDTH = 118
_PROCESSING_PROGRESS = (_PROCESSING_WIDTH - _MIN_REVEAL_WIDTH) / (_WIDTH - _MIN_REVEAL_WIDTH)
_LONG_RECORDING_EXPAND_DELAY = 0.85

# Waveform config
_NUM_BARS = 11
_BAR_WIDTH = 3.5
_BAR_GAP = 5.0
_BAR_MAX_HEIGHT = 24.0
_BAR_MIN_HEIGHT = 3.0

# Layout
_DOT_X = 21
_DOT_SIZE = 12
_SEPARATOR_X = 48
_LABEL_X = 64
_LABEL_WIDTH = 82
_WAVEFORM_X = 150
_WAVEFORM_WIDTH = 112

# Compact recording layout
_COMPACT_DOT_X = 82
_COMPACT_SEPARATOR_X = 108
_COMPACT_WAVEFORM_X = 116
_COMPACT_WAVEFORM_WIDTH = 90
_COMPACT_SPINNER_X = 122
_COMPACT_SPINNER_WIDTH = 42
_PROCESSING_SPINNER_X = 122
_PROCESSING_SPINNER_WIDTH = 42

# Spinner config
_SPINNER_RADIUS = 8.0
_SPINNER_DOT_COUNT = 8
_SPINNER_DOT_SIZE = 2.7


def _rgba(hex_value: str, alpha: float = 1.0):
    hex_value = hex_value.lstrip("#")
    red = int(hex_value[0:2], 16) / 255.0
    green = int(hex_value[2:4], 16) / 255.0
    blue = int(hex_value[4:6], 16) / 255.0
    return AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
        red,
        green,
        blue,
        alpha,
    )


_SURFACE = _rgba("#171512", 0.94)
_SURFACE_STROKE = _rgba("#F5F0E8", 0.14)
_SAGE_GLOW = _rgba("#BFE7A5")
_SAGE_LIGHT = _rgba("#BFE7A5")
_PARCHMENT = _rgba("#F5F0E8")
_HAIRLINE = _rgba("#F5F0E8", 0.16)


class CapsuleBackgroundView(AppKit.NSView):
    """Deterministic charcoal capsule so QA screenshots match the live surface."""

    def initWithFrame_(self, frame):
        self = objc.super(CapsuleBackgroundView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._reveal_progress = 1.0
        return self

    def setRevealProgress_(self, progress):
        self._reveal_progress = max(0.0, min(progress, 1.0))
        self.setNeedsDisplay_(True)

    def revealProgress(self):
        return self._reveal_progress

    def drawRect_(self, rect):
        progress = self._reveal_progress
        width = _MIN_REVEAL_WIDTH + (_WIDTH - _MIN_REVEAL_WIDTH) * progress
        x = _GLOW_PADDING + (_WIDTH - width) / 2
        y = _GLOW_PADDING
        radius = min(_CORNER_RADIUS, width / 2)

        for i, alpha in enumerate((0.030, 0.018, 0.010)):
            inset = -2.0 - i * 3.0
            glow_rect = AppKit.NSMakeRect(
                x + inset,
                y + inset,
                width - inset * 2,
                _HEIGHT - inset * 2,
            )
            glow = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                glow_rect,
                radius - inset,
                radius - inset,
            )
            _SAGE_GLOW.colorWithAlphaComponent_(alpha * progress).setStroke()
            glow.setLineWidth_(2.0 + i * 1.5)
            glow.stroke()

        base_rect = AppKit.NSMakeRect(x + 0.5, y + 0.5, width - 1, _HEIGHT - 1)
        base_path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            base_rect,
            radius,
            radius,
        )

        _SURFACE.setFill()
        base_path.fill()

        _SURFACE_STROKE.setStroke()
        base_path.setLineWidth_(1.0)
        base_path.stroke()


class ListeningDotView(AppKit.NSView):
    """Soft breathing indicator for the active recording state."""

    def initWithFrame_(self, frame):
        self = objc.super(ListeningDotView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._animating = False
        self._timer = None
        self._phase = 0.0
        self._active = True
        return self

    def setActive_(self, active):
        self._active = active
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        frame = self.frame()
        inset = 1.0

        if not self._active:
            dot_color = _PARCHMENT.colorWithAlphaComponent_(0.30)
            dot_color.setFill()
            dot = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
                AppKit.NSMakeRect(
                    inset + 3.5,
                    inset + 3.5,
                    frame.size.width - (inset + 3.5) * 2,
                    frame.size.height - (inset + 3.5) * 2,
                )
            )
            dot.fill()
            return

        pulse = 0.5 + 0.5 * math.sin(self._phase)
        glow_inset = max(0.0, 0.5 - pulse * 2.0)

        glow_color = _SAGE_LIGHT.colorWithAlphaComponent_(0.12 + pulse * 0.22)
        glow_color.setFill()
        glow = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
            AppKit.NSMakeRect(
                glow_inset,
                glow_inset,
                frame.size.width - glow_inset * 2,
                frame.size.height - glow_inset * 2,
            )
        )
        glow.fill()

        dot_color = _SAGE_LIGHT.colorWithAlphaComponent_(0.96)
        dot_color.setFill()
        dot = AppKit.NSBezierPath.bezierPathWithOvalInRect_(
            AppKit.NSMakeRect(
                inset + 2.5,
                inset + 2.5,
                frame.size.width - (inset + 2.5) * 2,
                frame.size.height - (inset + 2.5) * 2,
            )
        )
        dot.fill()

    def startAnimating(self):
        self._animating = True
        if self._timer is None:
            self._timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / 30.0, self, "tick:", None, True
            )

    def stopAnimating(self):
        self._animating = False
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self._phase = 0.0
        self.setNeedsDisplay_(True)

    def tick_(self, timer):
        if not self._animating:
            return
        self._phase += 0.08
        self.setNeedsDisplay_(True)


class SeparatorView(AppKit.NSView):
    """Single native hairline separating status from content."""

    def drawRect_(self, rect):
        _HAIRLINE.setFill()
        path = AppKit.NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            AppKit.NSMakeRect(0, 0, 1.0, self.frame().size.height),
            0.5,
            0.5,
        )
        path.fill()


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

            intensity = (h - _BAR_MIN_HEIGHT) / max(_BAR_MAX_HEIGHT - _BAR_MIN_HEIGHT, 1)
            alpha = 0.74 + 0.22 * intensity
            color = _PARCHMENT.blendedColorWithFraction_ofColor_(
                0.44 * intensity,
                _SAGE_LIGHT,
            ).colorWithAlphaComponent_(alpha)
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
        self._phase += 0.16
        raw_level = self._level_provider() if self._level_provider else 0.0
        level = max(0.0, min(raw_level, 1.0))

        for i in range(_NUM_BARS):
            distance = abs(i - (_NUM_BARS - 1) / 2)
            center_weight = 1.0 - (distance / max((_NUM_BARS - 1) / 2, 1)) * 0.42
            variation = 0.58 + 0.42 * math.sin(self._phase + i * 0.92)
            idle_breath = 0.5 + 0.5 * math.sin(self._phase * 0.7 + i * 0.45)
            target_level = max(level, 0.05 * idle_breath)
            target = _BAR_MIN_HEIGHT + (_BAR_MAX_HEIGHT - _BAR_MIN_HEIGHT) * target_level * variation * center_weight

            current = self._bar_heights[i]
            if target > current:
                self._bar_heights[i] = current + (target - current) * 0.48
            else:
                self._bar_heights[i] = current + (target - current) * 0.24

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
            alpha = 0.14 + 0.68 * (i / _SPINNER_DOT_COUNT)
            color = _PARCHMENT.colorWithAlphaComponent_(alpha)
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
    """Compact native capsule at the bottom of the screen."""

    def __init__(self):
        self._window = None
        self._container = None
        self._dot = None
        self._separator = None
        self._label = None
        self._waveform = None
        self._spinner = None
        self._state = OverlayState.HIDDEN
        self._level_provider = None
        self._manual_audio_level = 0.0
        self._motion_timer = None
        self._expand_timer = None
        self._content_alpha = 1.0
        self._recording_expansion_progress = 1.0
        self._setup()

    def set_level_provider(self, provider):
        """Set a callable that returns current audio level (0.0-1.0).
        The waveform will pull from this on each animation tick."""
        self._level_provider = provider
        self._waveform.setLevelProvider_(provider)

    def update_audio_level(self, level: float):
        """Set a manual audio level for the standalone overlay demo."""
        self._manual_audio_level = max(0.0, min(level, 1.0))
        if self._level_provider is None:
            self._waveform.setLevelProvider_(lambda: self._manual_audio_level)

    def _setup(self):
        screen = AppKit.NSScreen.mainScreen()
        screen_frame = screen.frame()
        x = (screen_frame.size.width - _WINDOW_WIDTH) / 2
        y = _BOTTOM_MARGIN - _GLOW_PADDING

        rect = AppKit.NSMakeRect(x, y, _WINDOW_WIDTH, _WINDOW_HEIGHT)

        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskBorderless,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self._window.setLevel_(AppKit.NSFloatingWindowLevel)
        self._window.setHasShadow_(False)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(AppKit.NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)
        self._window.setAlphaValue_(0.0)
        self._window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
        )

        self._container = CapsuleBackgroundView.alloc().initWithFrame_(
            AppKit.NSMakeRect(0, 0, _WINDOW_WIDTH, _WINDOW_HEIGHT)
        )
        self._window.setContentView_(self._container)

        self._dot = ListeningDotView.alloc().initWithFrame_(
            AppKit.NSMakeRect(
                _GLOW_PADDING + _DOT_X,
                _GLOW_PADDING + (_HEIGHT - _DOT_SIZE) / 2,
                _DOT_SIZE,
                _DOT_SIZE,
            )
        )
        self._container.addSubview_(self._dot)

        self._separator = SeparatorView.alloc().initWithFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + _SEPARATOR_X, _GLOW_PADDING + 13, 1, 20)
        )
        self._container.addSubview_(self._separator)

        self._label = AppKit.NSTextField.labelWithString_("Listening")
        self._label.setFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + _LABEL_X, _GLOW_PADDING + 11, _LABEL_WIDTH, 24)
        )
        self._label.setTextColor_(_PARCHMENT.colorWithAlphaComponent_(0.96))
        self._label.setFont_(
            AppKit.NSFont.systemFontOfSize_weight_(15, AppKit.NSFontWeightMedium)
        )
        self._label.setAlignment_(AppKit.NSTextAlignmentLeft)
        self._container.addSubview_(self._label)

        # Waveform (recording)
        self._waveform = WaveformView.alloc().initWithFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + _WAVEFORM_X, _GLOW_PADDING + 8, _WAVEFORM_WIDTH, 30)
        )
        self._container.addSubview_(self._waveform)

        # Spinner (processing)
        self._spinner = SpinnerView.alloc().initWithFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + _WAVEFORM_X, _GLOW_PADDING + 8, _WAVEFORM_WIDTH, 30)
        )
        self._spinner.setHidden_(True)
        self._container.addSubview_(self._spinner)
        self._set_recording_expansion(1.0)

    def _set_content_alpha(self, alpha: float):
        self._content_alpha = max(0.0, min(alpha, 1.0))
        self._apply_content_alpha()

    def _apply_content_alpha(self):
        expansion = self._recording_expansion_progress
        if self._dot is not None:
            dot_alpha = self._content_alpha if self._state == OverlayState.RECORDING else 0.0
            self._dot.setAlphaValue_(dot_alpha)
        if self._separator is not None:
            separator_alpha = self._content_alpha * expansion if self._state == OverlayState.RECORDING else 0.0
            self._separator.setAlphaValue_(separator_alpha)
        if self._waveform is not None:
            waveform_alpha = self._content_alpha if self._state == OverlayState.RECORDING else 0.0
            self._waveform.setAlphaValue_(waveform_alpha)
        if self._spinner is not None:
            spinner_alpha = self._content_alpha if self._state == OverlayState.PROCESSING else 0.0
            self._spinner.setAlphaValue_(spinner_alpha)
        if self._label is not None:
            label_alpha = 0.0
            if self._state == OverlayState.RECORDING:
                label_alpha = self._content_alpha * max(
                    0.0, min((expansion - 0.62) / 0.38, 1.0)
                )
            self._label.setAlphaValue_(label_alpha)

    def _lerp(self, start: float, end: float, progress: float) -> float:
        return start + (end - start) * progress

    def _set_recording_expansion(self, progress: float):
        self._recording_expansion_progress = max(0.0, min(progress, 1.0))
        p = self._recording_expansion_progress

        dot_x = self._lerp(_COMPACT_DOT_X, _DOT_X, p)
        separator_x = self._lerp(_COMPACT_SEPARATOR_X, _SEPARATOR_X, p)
        waveform_x = self._lerp(_COMPACT_WAVEFORM_X, _WAVEFORM_X, p)
        waveform_width = self._lerp(_COMPACT_WAVEFORM_WIDTH, _WAVEFORM_WIDTH, p)
        spinner_compact_x = (
            _PROCESSING_SPINNER_X
            if self._state == OverlayState.PROCESSING
            else _COMPACT_SPINNER_X
        )
        spinner_compact_width = (
            _PROCESSING_SPINNER_WIDTH
            if self._state == OverlayState.PROCESSING
            else _COMPACT_SPINNER_WIDTH
        )
        spinner_x = self._lerp(spinner_compact_x, _WAVEFORM_X, p)
        spinner_width = self._lerp(spinner_compact_width, _WAVEFORM_WIDTH, p)

        self._dot.setFrame_(
            AppKit.NSMakeRect(
                _GLOW_PADDING + dot_x,
                _GLOW_PADDING + (_HEIGHT - _DOT_SIZE) / 2,
                _DOT_SIZE,
                _DOT_SIZE,
            )
        )
        self._separator.setFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + separator_x, _GLOW_PADDING + 13, 1, 20)
        )
        self._label.setFrame_(
            AppKit.NSMakeRect(_GLOW_PADDING + _LABEL_X, _GLOW_PADDING + 11, _LABEL_WIDTH, 24)
        )
        self._waveform.setFrame_(
            AppKit.NSMakeRect(
                _GLOW_PADDING + waveform_x,
                _GLOW_PADDING + 8,
                waveform_width,
                30,
            )
        )
        self._spinner.setFrame_(
            AppKit.NSMakeRect(
                _GLOW_PADDING + spinner_x,
                _GLOW_PADDING + 8,
                spinner_width,
                30,
            )
        )
        self._apply_content_alpha()

    def _cancel_motion(self):
        if self._motion_timer is not None:
            self._motion_timer.invalidate()
            self._motion_timer = None

    def _cancel_expand_timer(self):
        if self._expand_timer is not None:
            self._expand_timer.invalidate()
            self._expand_timer = None

    def _animate_reveal(self, target_progress: float, duration: float, on_complete=None):
        self._cancel_motion()
        start_progress = self._container.revealProgress()
        target_progress = max(0.0, min(target_progress, 1.0))
        start = time.monotonic()

        def ease_out_cubic(t):
            return 1 - pow(1 - t, 3)

        def ease_in_cubic(t):
            return t * t * t

        opening = target_progress > start_progress

        def tick(timer):
            elapsed = time.monotonic() - start
            t = max(0.0, min(elapsed / duration, 1.0))
            eased_t = ease_out_cubic(t) if opening else ease_in_cubic(t)
            progress = start_progress + (target_progress - start_progress) * eased_t
            self._container.setRevealProgress_(progress)
            if opening:
                self._set_content_alpha_(min(1.0, max(0.0, (t - 0.42) / 0.32)))
            else:
                self._set_content_alpha_(max(0.0, 1.0 - t * 3.5))

            if t >= 1.0:
                timer.invalidate()
                self._motion_timer = None
                self._container.setRevealProgress_(target_progress)
                self._set_content_alpha_(1.0 if target_progress > 0 else 0.0)
                if on_complete:
                    on_complete()

        self._motion_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0 / 60.0,
            True,
            tick,
        )

    def _set_content_alpha_(self, alpha):
        self._set_content_alpha(alpha)

    def _animate_full_expansion(self):
        self._cancel_motion()
        start_width = self._container.revealProgress()
        start_expansion = self._recording_expansion_progress
        start = time.monotonic()
        duration = 0.22

        def ease_out_cubic(t):
            return 1 - pow(1 - t, 3)

        def tick(timer):
            elapsed = time.monotonic() - start
            t = max(0.0, min(elapsed / duration, 1.0))
            eased = ease_out_cubic(t)
            self._container.setRevealProgress_(
                start_width + (1.0 - start_width) * eased
            )
            self._set_recording_expansion(
                start_expansion + (1.0 - start_expansion) * eased
            )
            self._set_content_alpha_(1.0)

            if t >= 1.0:
                timer.invalidate()
                self._motion_timer = None
                self._container.setRevealProgress_(1.0)
                self._set_recording_expansion(1.0)
                self._set_content_alpha_(1.0)

        self._motion_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0 / 60.0,
            True,
            tick,
        )

    def _animate_layout(self, target_width: float, target_expansion: float, duration: float):
        self._cancel_motion()
        start_width = self._container.revealProgress()
        start_expansion = self._recording_expansion_progress
        target_width = max(0.0, min(target_width, 1.0))
        target_expansion = max(0.0, min(target_expansion, 1.0))
        start = time.monotonic()

        def ease_out_cubic(t):
            return 1 - pow(1 - t, 3)

        def tick(timer):
            elapsed = time.monotonic() - start
            t = max(0.0, min(elapsed / duration, 1.0))
            eased = ease_out_cubic(t)
            self._container.setRevealProgress_(
                start_width + (target_width - start_width) * eased
            )
            self._set_recording_expansion(
                start_expansion + (target_expansion - start_expansion) * eased
            )
            self._set_content_alpha_(1.0)

            if t >= 1.0:
                timer.invalidate()
                self._motion_timer = None
                self._container.setRevealProgress_(target_width)
                self._set_recording_expansion(target_expansion)
                self._set_content_alpha_(1.0)

        self._motion_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0 / 60.0,
            True,
            tick,
        )

    def _schedule_delayed_expansion(self, delay: float):
        self._cancel_expand_timer()

        def expand(timer):
            self._expand_timer = None
            if self._state == OverlayState.RECORDING:
                self._animate_full_expansion()

        self._expand_timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            delay,
            False,
            expand,
        )

    def show(self, state: str):
        """Show overlay with given state."""
        previous_state = self._state
        was_hidden = previous_state == OverlayState.HIDDEN
        self._state = state

        def _update():
            self._cancel_motion()
            if state == OverlayState.RECORDING:
                self._cancel_expand_timer()
                self._label.setStringValue_("Listening")
                self._dot.setActive_(True)
                self._dot.setHidden_(False)
                self._dot.startAnimating()
                self._waveform.setHidden_(False)
                self._waveform.startAnimating()
                self._spinner.stopAnimating()
                self._spinner.setHidden_(True)
            elif state == OverlayState.PROCESSING:
                self._cancel_expand_timer()
                self._dot.stopAnimating()
                self._dot.setActive_(False)
                self._dot.setHidden_(True)
                self._waveform.stopAnimating()
                self._waveform.setHidden_(True)
                self._spinner.setHidden_(False)
                self._spinner.startAnimating()

            self._window.orderFrontRegardless()
            self._window.setAlphaValue_(1.0)
            if was_hidden:
                self._container.setRevealProgress_(0.0)
                self._set_content_alpha(0.0)
                if state == OverlayState.RECORDING:
                    self._set_recording_expansion(0.0)
                    self._animate_reveal(_COMPACT_PROGRESS, 0.16)
                    self._schedule_delayed_expansion(_LONG_RECORDING_EXPAND_DELAY)
                elif state == OverlayState.PROCESSING:
                    self._set_recording_expansion(0.0)
                    self._animate_reveal(_PROCESSING_PROGRESS, 0.14)
                else:
                    self._animate_reveal(1.0, 0.18)
            else:
                if state == OverlayState.PROCESSING:
                    self._animate_layout(_PROCESSING_PROGRESS, 0.0, 0.16)
                elif state == OverlayState.RECORDING and previous_state != OverlayState.RECORDING:
                    self._animate_layout(_COMPACT_PROGRESS, 0.0, 0.16)
                    self._schedule_delayed_expansion(_LONG_RECORDING_EXPAND_DELAY)
                self._set_content_alpha(1.0)

        if AppKit.NSThread.isMainThread():
            _update()
        else:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(_update)

    def hide(self):
        """Hide the overlay with fade out."""
        self._state = OverlayState.HIDDEN

        def _update():
            self._cancel_expand_timer()
            self._dot.stopAnimating()
            self._waveform.stopAnimating()
            self._spinner.stopAnimating()

            def _finish():
                self._window.setAlphaValue_(0.0)
                self._window.orderOut_(None)

            self._animate_reveal(0.0, 0.16, on_complete=_finish)

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
