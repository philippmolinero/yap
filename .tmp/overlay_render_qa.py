import math
import sys
from pathlib import Path

import AppKit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.overlay import OverlayState, RecordingOverlay


OUTPUT_DIR = PROJECT_ROOT / ".tmp" / "overlay-qa"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def write_view_png(view, path: Path):
    bounds = view.bounds()
    rep = view.bitmapImageRepForCachingDisplayInRect_(bounds)
    view.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    data = rep.representationUsingType_properties_(AppKit.NSPNGFileType, {})
    data.writeToFile_atomically_(str(path), True)
    print(path, flush=True)


def pump(duration=0.02):
    run_loop = AppKit.NSRunLoop.currentRunLoop()
    until = AppKit.NSDate.dateWithTimeIntervalSinceNow_(duration)
    run_loop.runUntilDate_(until)


def render_state(overlay, state: str, path: Path, duration=0.26):
    overlay.show(state)
    pump(duration)
    if state == OverlayState.RECORDING:
        overlay._dot._phase = 1.2
        for i in range(18):
            overlay._waveform._level_provider = lambda i=i: 0.38 + 0.25 * math.sin(i * 0.55)
            overlay._waveform.tick_(None)
    elif state == OverlayState.PROCESSING:
        for _ in range(18):
            overlay._spinner.tick_(None)
    overlay._window.contentView().displayIfNeeded()
    write_view_png(overlay._window.contentView(), path)


def render_reveal_mid(overlay, path: Path):
    overlay.show(OverlayState.RECORDING)
    pump(0.03)
    overlay._container.setRevealProgress_(0.42)
    overlay._set_content_alpha(0.0)
    overlay._window.contentView().displayIfNeeded()
    write_view_png(overlay._window.contentView(), path)


def render_processing_transition_mid(overlay, path: Path):
    overlay.show(OverlayState.RECORDING)
    pump(1.18)
    overlay.show(OverlayState.PROCESSING)
    pump(0.08)
    for _ in range(8):
        overlay._spinner.tick_(None)
    overlay._window.contentView().displayIfNeeded()
    write_view_png(overlay._window.contentView(), path)


def make_dark_preview(source_path: Path, output_path: Path):
    from PIL import Image

    source = Image.open(source_path).convert("RGBA")
    canvas = Image.new("RGBA", source.size, (28, 28, 32, 255))
    canvas.alpha_composite(source, (0, 0))
    canvas.convert("RGB").save(output_path)
    print(output_path, flush=True)


def make_comparison(source_path: Path, implementation_path: Path, output_path: Path):
    from PIL import Image, ImageDraw

    source = Image.open(source_path).convert("RGBA")
    implementation = Image.open(implementation_path).convert("RGBA")

    source.thumbnail((720, 320), Image.Resampling.LANCZOS)
    implementation = implementation.resize(
        (implementation.width * 2, implementation.height * 2),
        Image.Resampling.LANCZOS,
    )

    padding = 32
    label_height = 36
    width = max(source.width, implementation.width) + padding * 2
    height = source.height + implementation.height + padding * 3 + label_height * 2

    canvas = Image.new("RGBA", (width, height), (28, 28, 32, 255))
    draw = ImageDraw.Draw(canvas)
    draw.text((padding, padding), "Source concept", fill=(245, 240, 232, 255))
    canvas.alpha_composite(source, ((width - source.width) // 2, padding + label_height))

    y = padding + label_height + source.height + padding
    draw.text((padding, y), "Native AppKit render", fill=(245, 240, 232, 255))
    canvas.alpha_composite(
        implementation,
        ((width - implementation.width) // 2, y + label_height),
    )

    canvas.convert("RGB").save(output_path)
    print(output_path, flush=True)


def main():
    AppKit.NSApplication.sharedApplication()

    def build_overlay():
        overlay = RecordingOverlay()
        overlay.set_level_provider(lambda: 0.65)
        return overlay

    compact_path = OUTPUT_DIR / "recording-compact-render.png"
    recording_path = OUTPUT_DIR / "recording-expanded-render.png"
    processing_path = OUTPUT_DIR / "processing-render.png"
    processing_transition_path = OUTPUT_DIR / "processing-transition-render.png"
    reveal_mid_path = OUTPUT_DIR / "reveal-mid-render.png"
    compact_dark_path = OUTPUT_DIR / "recording-compact-dark-preview.png"
    recording_dark_path = OUTPUT_DIR / "recording-dark-preview.png"
    processing_dark_path = OUTPUT_DIR / "processing-dark-preview.png"
    processing_transition_dark_path = OUTPUT_DIR / "processing-transition-dark-preview.png"
    comparison_path = OUTPUT_DIR / "recording-comparison.png"
    source_path = (
        Path.home()
        / ".codex/generated_images/019e91ee-3134-72d3-a0bd-78752fca2b67/"
        / "ig_0f12b31ad2bb7225016a2144836e3c81918273149bedd5d767.png"
    )

    reveal_overlay = build_overlay()
    render_reveal_mid(reveal_overlay, reveal_mid_path)
    reveal_overlay.hide()

    compact_overlay = build_overlay()
    render_state(compact_overlay, OverlayState.RECORDING, compact_path, duration=0.26)
    compact_overlay.hide()

    expanded_overlay = build_overlay()
    render_state(expanded_overlay, OverlayState.RECORDING, recording_path, duration=1.18)
    expanded_overlay.hide()

    processing_overlay = build_overlay()
    render_state(processing_overlay, OverlayState.PROCESSING, processing_path, duration=1.18)
    processing_overlay.hide()

    processing_transition_overlay = build_overlay()
    render_processing_transition_mid(processing_transition_overlay, processing_transition_path)
    processing_transition_overlay.hide()

    make_dark_preview(compact_path, compact_dark_path)
    make_dark_preview(recording_path, recording_dark_path)
    make_dark_preview(processing_path, processing_dark_path)
    make_dark_preview(processing_transition_path, processing_transition_dark_path)
    make_comparison(source_path, recording_path, comparison_path)


if __name__ == "__main__":
    main()
