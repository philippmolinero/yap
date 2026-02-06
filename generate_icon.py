"""
Yap App Icon Generator — Quiet Resonance

Final icon: Instrument Serif Italic lowercase 'y' on deep muted navy.

The italic serif 'y' is perfect for Yap:
- The forward lean suggests speech flowing, words in motion
- The serif gives it character without being fussy
- The calligraphic descender curves with the elegance of a breath
- It's distinctive at every size, from 1024px to 16px menubar

Color: Dusty lavender on deep navy — intimate, calm, quiet confidence.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math
import os

SIZE = 1024
CENTER = SIZE // 2

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        ".claude/skills/canvas-design/canvas-fonts")

# === COLOR PALETTE ===
# Slightly warmer navy — less blue-black, more ink
BG_DEEP = (26, 28, 44)
# Warmer dusty lavender — a touch of rose warmth mixed in
MARK_COLOR = (182, 176, 212)


def superellipse_mask(size, n=5.0):
    """macOS-style superellipse (squircle) mask."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    padding = int(size * 0.045)
    radius = (size - 2 * padding) / 2
    cx, cy = size / 2, size / 2
    points = []
    for i in range(1200):
        t = 2 * math.pi * i / 1200
        cos_t = math.cos(t)
        sin_t = math.sin(t)
        x = cx + radius * abs(cos_t) ** (2/n) * (1 if cos_t >= 0 else -1)
        y = cy + radius * abs(sin_t) ** (2/n) * (1 if sin_t >= 0 else -1)
        points.append((x, y))
    draw.polygon(points, fill=255)
    return img


def create_background(size):
    """Deep navy with subtle radial warmth at center."""
    img = Image.new("RGBA", (size, size), BG_DEEP + (255,))
    gradient = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    c = size // 2
    max_r = int(size * 0.44)
    for r in range(max_r, 0, -2):
        # Slightly stronger gradient for more depth
        alpha = int(16 * (1 - r / max_r) ** 1.8)
        grad_draw.ellipse([c - r, c - r, c + r, c + r], fill=(255, 255, 255, alpha))
    return Image.alpha_composite(img, gradient)


def render_centered_glyph(char, font_path, font_size, color, canvas_size,
                           x_nudge=0, y_nudge=0):
    """Render a glyph optically centered on a transparent canvas."""
    # Render at 2x for better antialiasing, then downscale
    render_size = canvas_size * 2
    layer = Image.new("RGBA", (render_size, render_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    font = ImageFont.truetype(font_path, font_size * 2)
    bbox = font.getbbox(char)
    char_w = bbox[2] - bbox[0]
    char_h = bbox[3] - bbox[1]

    # Center on canvas
    x = (render_size - char_w) / 2 - bbox[0] + x_nudge * 2
    y = (render_size - char_h) / 2 - bbox[1] + y_nudge * 2

    draw.text((x, y), char, font=font, fill=color)

    # Downscale with high-quality resampling
    layer = layer.resize((canvas_size, canvas_size), Image.LANCZOS)
    return layer


def create_icon():
    """Create the 1024x1024 macOS app icon."""
    img = create_background(SIZE)

    font_path = os.path.join(FONT_DIR, "InstrumentSerif-Italic.ttf")

    # Size the glyph: the y should occupy roughly 52% of the icon height
    # with generous breathing room on all sides
    font_size = int(SIZE * 0.62)

    # Optical adjustments:
    # - Nudge right to compensate for italic lean (the descender pulls left)
    # - Nudge up because descenders make it feel optically low
    glyph = render_centered_glyph("y", font_path, font_size,
                                    MARK_COLOR + (255,), SIZE,
                                    x_nudge=int(SIZE * 0.020),
                                    y_nudge=int(SIZE * -0.022))

    img = Image.alpha_composite(img, glyph)

    # Apply superellipse mask
    mask = superellipse_mask(SIZE, n=5.0)
    final = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    final.paste(img, (0, 0), mask)
    return final


def create_icon_512():
    """Create a 512x512 variant."""
    icon = create_icon()
    return icon.resize((512, 512), Image.LANCZOS)


def create_menubar_icon():
    """Create 22pt menubar template icon at 2x resolution (44px).

    Rendered at 4x (176px) with stroke thickening, then downscaled
    to 44px for crisp retina rendering with proper weight.
    """
    target = 44
    render = target * 4  # 176px for clean rendering

    font_path = os.path.join(FONT_DIR, "InstrumentSerif-Italic.ttf")

    # Render large — fill ~90% of the canvas height
    glyph = render_centered_glyph("y", font_path, int(render * 0.88),
                                   (0, 0, 0, 255), render,
                                   x_nudge=int(render * 0.02),
                                   y_nudge=int(render * -0.02))

    # Thicken strokes: use MaxFilter to dilate, then composite
    # This adds ~1-2px of weight at render size (~0.5px at final)
    from PIL import ImageFilter
    alpha = glyph.split()[3]
    thick_alpha = alpha.filter(ImageFilter.MaxFilter(5))
    # Blend: 70% thickened + 30% original for natural weight gain
    import numpy as np
    orig_arr = np.array(alpha, dtype=np.float32)
    thick_arr = np.array(thick_alpha, dtype=np.float32)
    blended = np.clip(orig_arr * 0.3 + thick_arr * 0.7, 0, 255).astype(np.uint8)
    blended_alpha = Image.fromarray(blended, mode="L")

    result = Image.new("RGBA", (render, render), (0, 0, 0, 0))
    black = Image.new("RGBA", (render, render), (0, 0, 0, 255))
    result.paste(black, (0, 0), blended_alpha)

    # Downscale to target with LANCZOS
    result = result.resize((target, target), Image.LANCZOS)
    return result


if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(root, "assets")
    os.makedirs(assets, exist_ok=True)

    # Main app icon at 1024 (used by PyInstaller for .icns)
    icon = create_icon()
    icon.save(os.path.join(assets, "icon_app.png"), "PNG")
    print("Saved: assets/icon_app.png")

    # Menubar template icon (44px @2x, black on transparent)
    mb = create_menubar_icon()
    mb.save(os.path.join(assets, "icon_menubar.png"), "PNG")
    print("Saved: assets/icon_menubar.png")

    # Also save full-res copies in project root for reference
    icon.save(os.path.join(root, "yap-icon-1024.png"), "PNG")
    create_icon_512().save(os.path.join(root, "yap-icon-512.png"), "PNG")
    print("Saved reference copies: yap-icon-1024.png, yap-icon-512.png")
