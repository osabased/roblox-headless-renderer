"""UIGradient ramps match Studio's on fills off the axes, with an Offset, on text and on
UIStrokes.

Measured in Studio on 2026-10-19 (750x401 viewport, Edit mode) from luma pairs: each case
drawn black-to-white and white-to-black, t = Y_a / (Y_a + Y_b), lengths scaled by a
140 px control fill in the same capture. The rules they fit:

- A ramp runs at Rotation over the chord through the centre of the box it shades,
  min(w / |cos R|, h / |sin R|), so its ends reach the box's edges on the ramp's own
  line.
- Offset moves the ramp's centre by (Offset.X * w, Offset.Y * h) on screen.
- A TextLabel's gradient, and a text UIStroke's, spans the label's box, not the text's
  bounds or the stroke's.
- A UIStroke's gradient spans the stroke's outer edge: the box grown by Thickness for
  Outer, half of it for Center, nothing for Inner. A UICorner doesn't change it.

The Inner strokes, the text strokes, Rotation 180 and the Offset centres at Rotation 0
and 90 already matched before the chord rule; they guard against regressions. The text
strokes hold within 1.5 to 3 px: Studio's read 0.7 to 2.4 px shorter than the label,
which no rule here explains.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from rhr.pipeline import render_object  # noqa: E402
from test_gradient_rotation import ramp_positions  # noqa: E402

OUT = REPO / "out" / "gradient-studio"
MARGIN = 20
STOPS = [(0.0, (230, 40, 40)), (1.0, (40, 80, 230))]

FILLS = [
    # w, h, rotation, offset, Studio's length, Studio's t at the box centre
    (172, 100, 30, (0, 0), 198.4, 0.501),
    (172, 100, 60, (0, 0), 115.2, 0.498),
    (172, 100, 135, (0, 0), 140.7, 0.499),
    (172, 100, 315, (0, 0), 141.1, 0.499),
    (100, 172, 30, (0, 0), 115.4, 0.503),
    (100, 172, 60, (0, 0), 198.0, 0.500),
    (120, 120, 30, (0, 0), 138.4, 0.498),
    (120, 120, 135, (0, 0), 169.4, 0.499),
    (300, 60, 30, (0, 0), 120.1, 0.500),
    (300, 60, 60, (0, 0), 69.2, 0.500),
    (300, 60, 135, (0, 0), 84.4, 0.500),
    (172, 100, 180, (0, 0), 171.5, 0.498),
    (172, 100, 45, (0.25, 0), 141.3, 0.285),
    (172, 100, 45, (0, 0.25), 141.2, 0.376),
    (172, 100, 30, (0.25, 0.25), 198.7, 0.248),
    (172, 100, 0, (0.25, 0), 172.1, 0.252),
    (172, 100, 90, (0, 0.25), 99.8, 0.250),
]
STROKES = [
    # w, h, thickness, BorderStrokePosition, rotation, corner, Studio's length
    (140, 80, 1, "Outer", 0, 0, 142.3),
    (140, 80, 2, "Outer", 0, 0, 144.4),
    (140, 80, 4, "Outer", 0, 0, 148.0),
    (140, 80, 8, "Outer", 0, 0, 155.9),
    (140, 80, 12, "Outer", 0, 0, 164.0),
    (220, 80, 4, "Outer", 0, 0, 228.4),
    (220, 80, 12, "Outer", 0, 0, 244.1),
    (140, 80, 4, "Center", 0, 0, 143.8),
    (140, 80, 8, "Center", 0, 0, 148.0),
    (220, 80, 8, "Center", 0, 0, 228.6),
    (140, 80, 4, "Inner", 0, 0, 139.9),
    (140, 80, 8, "Inner", 0, 0, 140.3),
    (140, 80, 4, "Outer", 90, 0, 87.9),
    (140, 80, 12, "Outer", 90, 0, 103.7),
    (140, 80, 4, "Outer", 45, 0, 124.4),
    (140, 80, 4, "Outer", 0, 16, 147.5),
    (140, 80, 4, "Outer", 45, 16, 124.2),
]
TEXTS = [
    # text, TextScaled, TextSize, rotation, on the stroke, Studio's length, tolerance
    ("Gradient", True, 14, 90, False, 119.6, 1.0),
    ("Gradient", True, 14, 45, False, 170.5, 1.0),
    ("Gradient", True, 14, 0, True, 297.5, 3.0),
    ("Gradient", True, 14, 90, True, 118.4, 2.0),
    ("Hi", False, 48, 90, True, 119.1, 1.5),
]

FAILURES = []


def check(ok, message):
    print(f"{'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        FAILURES.append(message)


def gradient(rotation, offset=(0, 0)):
    return {
        "colors": [(t, "#%02x%02x%02x" % rgb) for t, rgb in STOPS],
        "transparency": [(0, 0), (1, 0)],
        "rotation": rotation,
        "offset": list(offset),
    }


def render(node, w, h, name):
    node = {**node, "size": [0, w, 0, h], "position": [0, MARGIN, 0, MARGIN]}
    png = render_object(node, OUT / f"{name}.png", w + 2 * MARGIN, h + 2 * MARGIN)
    return np.asarray(Image.open(png).convert("RGBA")).astype(float)


def fit_ramp(image, mask, w, h):
    """Fit t = a + b x + c y to the unclamped masked pixels.

    Returns the ramp's angle in degrees (0..360), its length in pixels and t at the box centre."""
    ys, xs = np.nonzero(mask)
    t, d = ramp_positions(image[ys, xs, :3], STOPS)
    keep = (d < 4) & (t > 0.04) & (t < 0.96)
    x = xs[keep] + 0.5 - MARGIN
    y = ys[keep] + 0.5 - MARGIN
    A = np.column_stack([np.ones(len(x)), x, y])
    (a, b, c), *_ = np.linalg.lstsq(A, t[keep], rcond=None)
    return math.degrees(math.atan2(c, b)) % 360, 1 / math.hypot(b, c), a + b * w / 2 + c * h / 2


def angle_off(got, want):
    return abs((got - want + 180) % 360 - 180)


def check_ramp(label, fitted, rotation, length, tol, centre=None):
    got_angle, got_length, got_centre = fitted
    check(angle_off(got_angle, rotation) <= 0.5, f"{label}: the ramp runs at {got_angle:.1f} degrees")
    check(abs(got_length - length) <= tol, f"{label}: the ramp is {got_length:.1f} px long (Studio {length:.1f})")
    if centre is not None:
        check(abs(got_centre - centre) <= 0.01, f"{label}: t at the centre is {got_centre:.3f} (Studio {centre:.3f})")


def main():
    for w, h, rotation, offset, length, centre in FILLS:
        name = f"fill-{w}x{h}-r{rotation}-o{offset[0]}_{offset[1]}"
        frame = {"type": "Frame", "name": name, "bg": [255, 255, 255], "gradient": gradient(rotation, offset)}
        image = render(frame, w, h, name)
        mask = np.zeros(image.shape[:2], dtype=bool)
        mask[MARGIN + 2 : MARGIN + h - 2, MARGIN + 2 : MARGIN + w - 2] = True
        check_ramp(f"{w}x{h} fill at Rotation {rotation}, Offset {offset}", fit_ramp(image, mask, w, h),
                   rotation, length, 1.0, centre)

    for w, h, thickness, position, rotation, corner, length in STROKES:
        name = f"stroke-{w}x{h}-{position}{thickness}-r{rotation}-k{corner}"
        stroke = {"thickness": thickness, "color": [255, 255, 255], "transparency": 0, "lineJoin": "Round",
                  "applyMode": "Border", "gradient": gradient(rotation)}
        if position != "Outer":
            stroke["borderPosition"] = position
        frame = {"type": "Frame", "name": name, "bg": [0, 0, 0], "bgTransparency": 1, "strokes": [stroke]}
        if corner:
            frame["corner"] = {"scale": 0, "offset": corner}
        image = render(frame, w, h, name)
        check_ramp(f"{w}x{h} {position} {thickness} px stroke at Rotation {rotation}"
                   + (f", UICorner {corner}" if corner else ""),
                   fit_ramp(image, image[:, :, 3] >= 200, w, h), rotation, length, 1.0, 0.5)

    for text, scaled, size, rotation, on_stroke, length, tol in TEXTS:
        name = f"text-{text}-r{rotation}-{'stroke' if on_stroke else 'label'}"
        label = {"type": "TextLabel", "name": name, "bgTransparency": 1, "text": text, "font": "FredokaOne",
                 "textSize": size, "textScaled": scaled, "textStrokeTransparency": 1}
        if on_stroke:
            label["textColor"] = [0, 0, 0]
            label["strokes"] = [{"thickness": 6, "color": [255, 255, 255], "transparency": 0,
                                 "lineJoin": "Round", "gradient": gradient(rotation)}]
        else:
            label["textColor"] = [255, 255, 255]
            label["gradient"] = gradient(rotation)
        image = render(label, 300, 120, name)
        check_ramp(f"300x120 {text!r} {'text stroke' if on_stroke else 'text'} at Rotation {rotation}",
                   fit_ramp(image, image[:, :, 3] == 255, 300, 120), rotation, length, tol, 0.5)
    return int(bool(FAILURES))


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
