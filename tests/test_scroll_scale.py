#!/usr/bin/env python3
"""ScrollingFrame scale resolution: a child's Scale resolves against the CANVAS.

Studio lays a ScrollingFrame's children out on its canvas: CanvasSize, its Scale of
the box the frame's own Size resolved against. Measured in Studio: a 130x170 frame
with CanvasSize (0,0,3,0) and a 20 px bar, on a 401 px tall screen, has a 130x1203
canvas, and its child sized (1,0,0.5,0) at (0,0,0.1,0) is 130x601.5 at canvas y
120.3. Patch 0015 resolved Scale against the window, which those numbers rule out;
tests/test_scroll_bars.py holds the other measured cases.

Fixture: a ScrollingFrame (100x100 at 50,50 in the content area, CanvasSize yScale 3,
the default 12 px bar) with one blue child Panel at yScale 0.06, height yScale 10.067.
The content area is 242 px tall at the 400x300 viewport, so the canvas is 726 tall:
the panel starts 0.06 * 726 = 43.56 px down the frame, and the vertical bar shows,
taking a 12 px strip off the window's right.

Run: python tests/test_scroll_scale.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))

from test_fixtures import _bbox, _render, content_origin, rel  # noqa: E402

BLUE = (0, 0, 255)
RED = (255, 0, 0)
# Roblox's own bar: white at 128/255 opacity, over the frame's red.
THUMB = (255, 128, 128)


def _at(img, x: int, y: int) -> tuple[int, ...]:
    """The colour at a point of the fixture's content area."""
    ox, oy = content_origin("scroll_scale")
    return tuple(int(v) for v in img[y + oy, x + ox, :3])


def _near(colour, want, tol: int = 8) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(colour, want))


def check_panel_on_canvas() -> str:
    """The panel's yScale 0.06 resolves against the 726 px canvas, not the 100 px window."""
    img = _render("scroll_scale")
    box = rel(_bbox(img, BLUE), "scroll_scale")
    # Top: content y 50 + 43.56, its first whole row 94. Right: the window ends where
    # the bar's strip starts, x 138. Bottom: the panel is some 7300 px tall, clipped
    # at the frame's bottom (content y 150).
    expected = (50, 94, 137, 149)
    assert box == expected, f"panel bbox {box}, expected {expected}"
    return f"panel bbox {box}"


def check_bar_strip() -> str:
    """The bar's strip holds no content, and its bare track shows the frame's background."""
    img = _render("scroll_scale")
    ox, oy = content_origin("scroll_scale")
    strip = img[50 + oy:150 + oy, 138 + ox:150 + ox, :3]
    blue = int((abs(strip - BLUE).max(axis=-1) <= 8).sum())
    assert blue == 0, f"{blue} blue px in the bar's strip (content x 138..149)"
    track = _at(img, 143, 100)
    assert _near(track, RED), f"track below the thumb at (143,100): {track}, expected the frame's red"
    return f"strip clear, track {track}"


def check_default_thumb() -> str:
    """The thumb: the window's share of the track, at least two thicknesses (24 px) long,
    drawn from the middle of its top part to the middle of its bottom one."""
    img = _render("scroll_scale")
    colour = _at(img, 144, 62)
    assert _near(colour, THUMB), f"thumb at (144,62): {colour}, expected {THUMB}"
    box = rel(_bbox(img, THUMB), "scroll_scale")
    # The thumb spans content y 50..74; its bar is 6 px short at each end.
    expected = (138, 56, 149, 67)
    assert box == expected, f"thumb bbox {box}, expected {expected}"
    return f"thumb {colour}, bbox {box}"


CHECKS = [
    ("scroll_scale: panel top at canvas yScale", check_panel_on_canvas),
    ("scroll_scale: the bar's strip is left to the bar", check_bar_strip),
    ("scroll_scale: Roblox's default thumb", check_default_thumb),
]


def main() -> int:
    failures = 0
    for name, fn in CHECKS:
        try:
            detail = fn()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {name}: {exc}")
        else:
            print(f"ok    {name}: {detail}")
    print(f"\n{len(CHECKS) - failures}/{len(CHECKS)} scroll-scale checks pass")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
