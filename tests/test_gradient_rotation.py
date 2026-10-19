"""UIGradient ramps run along Studio's lines: off the axes across the chord through the
box's centre, and on text at the gradient's own Rotation.

Fitted from Studio's fidelity capture of 2026-10-18 (1536x790, Edit mode). A 172x100
Frame at Rotation 45 ramps at 45.1 degrees over 140.5 px (the chord is 141.4),
centred, with its corners clamped to the end colours; at Rotation 0 and 90 it ramps
over the width and the height. A 172x100 TextLabel's glyphs at Rotation 0 ramp at 0.5
degrees over the label's 172 px width. test_gradient_studio.py has the other sizes,
angles, Offsets and strokes.
"""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from rhr.pipeline import render_object  # noqa: E402

OUT = REPO / "out" / "gradient-rotation"
W, H, MARGIN = 172, 100, 10
FRAME_STOPS = [(0.0, (230, 40, 40)), (0.5, (40, 200, 80)), (1.0, (40, 80, 230))]
TEXT_STOPS = [(0.0, (255, 170, 40)), (1.0, (220, 40, 200))]

FAILURES = []


def check(ok, message):
    print(f"{'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        FAILURES.append(message)


def gradient(stops, rotation):
    return {
        "colors": [(t, "#%02x%02x%02x" % rgb) for t, rgb in stops],
        "transparency": [(0, 0), (1, 0)],
        "rotation": rotation,
    }


def render(node, name):
    node = {**node, "size": [0, W, 0, H], "position": [0, MARGIN, 0, MARGIN]}
    png = render_object(node, OUT / f"{name}.png", W + 2 * MARGIN, H + 2 * MARGIN)
    return np.asarray(Image.open(png).convert("RGBA")).astype(float)


def ramp_positions(rgb, stops):
    """Each colour's place on the ramp, from the nearest stop-to-stop segment."""
    best_t = np.zeros(len(rgb))
    best_d = np.full(len(rgb), np.inf)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        c0 = np.array(c0, dtype=float)
        seg = np.array(c1, dtype=float) - c0
        s = np.clip(((rgb - c0) @ seg) / (seg @ seg), 0, 1)
        d = np.linalg.norm(rgb - (c0 + s[:, None] * seg), axis=1)
        closer = d < best_d
        best_t[closer] = (t0 + s * (t1 - t0))[closer]
        best_d[closer] = d[closer]
    return best_t, best_d


def fit_ramp(image, mask, stops):
    """Fit t = a + b x + c y, in box pixels, to the unclamped masked pixels.

    Returns the ramp's angle in degrees, its length in pixels and t at the box centre."""
    ys, xs = np.nonzero(mask)
    t, d = ramp_positions(image[ys, xs, :3], stops)
    keep = (d < 4) & (t > 0.04) & (t < 0.96)
    x = xs[keep] + 0.5 - MARGIN
    y = ys[keep] + 0.5 - MARGIN
    A = np.column_stack([np.ones(len(x)), x, y])
    (a, b, c), *_ = np.linalg.lstsq(A, t[keep], rcond=None)
    return math.degrees(math.atan2(c, b)), 1 / math.hypot(b, c), a + b * W / 2 + c * H / 2


def box_mask(image):
    mask = np.zeros(image.shape[:2], dtype=bool)
    mask[MARGIN + 2 : MARGIN + H - 2, MARGIN + 2 : MARGIN + W - 2] = True
    return mask


def near(image, x, y, rgb, label):
    actual = image[MARGIN + y, MARGIN + x, :3]
    check(np.max(np.abs(actual - rgb)) <= 2, f"{label}: {actual.astype(int).tolist()}")


def main():
    for rotation, angle, length in ((0, 0.0, W), (90, 90.0, H), (45, 45.0, 140.5)):
        frame = {"type": "Frame", "name": f"Gradient{rotation}", "bg": [255, 255, 255],
                 "gradient": gradient(FRAME_STOPS, rotation)}
        image = render(frame, f"frame-{rotation}")
        got_angle, got_length, centre = fit_ramp(image, box_mask(image), FRAME_STOPS)
        check(abs(got_angle - angle) <= 0.5, f"Rotation {rotation}: the ramp runs at {got_angle:.1f} degrees")
        check(abs(got_length - length) <= 1.5,
              f"Rotation {rotation}: the ramp is {got_length:.1f} px long (Studio {length:.1f})")
        check(abs(centre - 0.5) <= 0.01, f"Rotation {rotation}: the ramp is centred (t {centre:.3f})")
        if rotation == 45:
            near(image, 4, 4, FRAME_STOPS[0][1], "Rotation 45: the top-left corner takes the first colour")
            near(image, W - 5, H - 5, FRAME_STOPS[-1][1], "Rotation 45: the bottom-right corner takes the last colour")

    label = {"type": "TextLabel", "name": "TextGradient", "bgTransparency": 1, "text": "Gradient",
             "font": "FredokaOne", "textSize": 36, "textColor": [255, 255, 255],
             "textStrokeTransparency": 1, "gradient": gradient(TEXT_STOPS, 0)}
    image = render(label, "text-0")
    glyphs = image[:, :, 3] == 255
    check(glyphs.sum() > 500, f"the label draws its text ({int(glyphs.sum())} opaque px)")
    got_angle, got_length, centre = fit_ramp(image, glyphs, TEXT_STOPS)
    check(abs(got_angle) <= 1.0, f"text at Rotation 0: the ramp runs at {got_angle:.1f} degrees (Studio 0.5)")
    check(abs(got_length - W) <= 2, f"text at Rotation 0: the ramp spans {got_length:.1f} px, the label's width")
    check(abs(centre - 0.5) <= 0.02, f"text at Rotation 0: the ramp is centred on the label (t {centre:.3f})")
    return int(bool(FAILURES))


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
