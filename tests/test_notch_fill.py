#!/usr/bin/env python3
"""The notch fill: what a ScreenGui paints outside the device safe area of a notched screen.

Studio measured each case below in Play on its iPhone 16 emulator, in landscape: an
874x401 screen with a 62 px notch at each side, under the 58 px top bar. The models are
built here with the setups Studio's probes used: each case is a ScreenGui at
DisplayOrder 110 over a blue ScreenInsets None gui at 100, so blue shows wherever the
case paints nothing. What they show (docs/known-approximations.md): an object whose
total rect, its outline and Border stroke included, covers the device safe area on both
axes paints out to the screen edges, and keeps its own rect for layout;
ClipToDeviceSafeArea clips everything else to the safe area.

ListFull and ListWide take the rule through UIListLayout placement, which the renderer
draws by a path of its own; they follow from the rule rather than from a measurement.

Run: python tests/test_notch_fill.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import (  # noqa: E402
    QUADRANTS, content, item, offset, quadrant_cache, rgb, scale, token, udim, udim2, vec2, write_model,
)
from rhr import devices, insets  # noqa: E402
from rhr.pipeline import render_ir  # noqa: E402
from test_fixtures import emit_ir  # noqa: E402

OUT = REPO / "out" / "notch_fill"
SCREEN = (874, 401)
FULL = (0, 0, *SCREEN)
STUDIO_PHONE = devices.Device("studio", "iphone_16", SCREEN, safe=(62.0, 0.0, 62.0, 0.0))
TOPBAR = 58
NONE, DEVICE, CORE = 0, 1, 2
RED = (255, 0, 0)
GREEN = (0, 255, 0)
DARK_GREEN = (0, 200, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
IMAGE = "rbxassetid://990000001"

# Stretching changes only where an object paints: Studio's AbsolutePosition and
# AbsoluteSize, and its children's layout, stay as they were. In screen pixels here.
RECTS = {
    "B": {"Case/Fill": (62, 0, 750, 401)},
    "Img": {"Case/Fill": (62, 0, 750, 401)},
    "Holder": {"Case/Holder": (62, 0, 750, 401), "Case/Holder/Child": (62, 0, 750, 401)},
    "Oversized": {"Case/Fill": (-38, -100, 950, 601)},
    "ListFull": {"Case/Holder/Child": (62, 0, 750, 401)},
}


def notch_gui(mode: int, *children, **props) -> dict:
    return item("ScreenGui", "Case", {"ScreenInsets": token(mode), "DisplayOrder": 110, "ZIndexBehavior": token(1),
                                      **props}, children)


def fill(name: str, colour, position=None, size=None, children=(), **props) -> dict:
    p = {"Size": size or scale(1, 1), "BackgroundColor3": rgb(colour), "BorderSizePixel": 0}
    if position:
        p["Position"] = position
    return item("Frame", name, {**p, **props}, children)


def corner(radius: int) -> dict:
    return item("UICorner", "Corner", {"CornerRadius": udim(0, radius)})


def listed(*children) -> dict:
    """A see-through holder over the safe area that lists its children down from its top."""
    return fill("Holder", RED, children=[item("UIListLayout", "List"), *children], BackgroundTransparency=1.0)


def fmt(values) -> str:
    return "(" + ",".join(f"{value:g}" for value in values) + ")"


def summary(problems: list[str]) -> str:
    if not problems:
        return "as Studio"
    return "; ".join(problems[:4]) + (f"; +{len(problems) - 4} more" if len(problems) > 4 else "")


def near(a, b, tol: float = 0.5) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def dist(img, colour):
    return np.abs(img - np.asarray(colour, float)).max(axis=-1)


def beside_change(want) -> np.ndarray:
    """Pixels within a pixel of a colour change in `want`, where an edge may blend."""
    h, w = want.shape[:2]
    padded = np.pad(want, ((1, 1), (1, 1), (0, 0)), mode="edge")
    out = np.zeros((h, w), bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= (padded[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] != want).any(axis=-1)
    return out


def differ(img, want, skip) -> list[str]:
    wrong = (dist(img, want) > 10) & ~skip
    if not wrong.any():
        return []
    ys, xs = np.nonzero(wrong)
    x, y = xs[0], ys[0]
    return [f"{int(wrong.sum())} px differ in ({xs.min()},{ys.min()})-({xs.max() + 1},{ys.max() + 1}), "
            f"({x},{y}) is {fmt(img[y, x])}, Studio {fmt(want[y, x])}"]


def painted(*layers, corners: bool = False):
    """Blue with each (colour, (x0, y0, x1, y1)) layer painted over it.

    Pixels beside a colour change are skipped, and with `corners` the 2x2 screen
    corners, where Studio's stretched stroke corners weren't measured.
    """
    w, h = SCREEN
    want = np.empty((h, w, 3))
    want[...] = BLUE
    for colour, (x0, y0, x1, y1) in layers:
        want[y0:y1, x0:x1] = colour
    skip = beside_change(want)
    if corners:
        for x, y in ((0, 0), (w - 2, 0), (0, h - 2), (w - 2, h - 2)):
            skip[y:y + 2, x:x + 2] = True
    return lambda img: differ(img, want, skip)


def rounded(radius: int):
    """A screen-sized red rect with corners of `radius`, over blue.

    The pixels a corner's arc passes through are skipped: anti-aliasing part-covers
    them, and where an arc meets the screen edge at a shallow angle that runs several
    pixels along the edge.
    """
    w, h = SCREEN
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    cx = np.where(xs < radius, radius, w - radius)
    cy = np.where(ys < radius, radius, h - radius)
    in_corner = ((xs < radius) | (xs >= w - radius)) & ((ys < radius) | (ys >= h - radius))
    farthest = np.hypot(np.maximum(abs(xs - cx), abs(xs + 1 - cx)), np.maximum(abs(ys - cy), abs(ys + 1 - cy)))
    nearest = np.hypot(np.clip(cx, xs, xs + 1) - cx, np.clip(cy, ys, ys + 1) - cy)
    want = np.empty((h, w, 3))
    want[...] = BLUE
    want[~in_corner | (farthest <= radius)] = RED
    return lambda img: differ(img, want, in_corner & (nearest < radius) & (farthest > radius))


def sampled(*points):
    """Each ((x, y), colour) pixel."""
    def check(img) -> list[str]:
        return [f"{fmt(point)} is {fmt(img[point[1], point[0]])}, Studio {fmt(want)}"
                for point, want in points if dist(img[point[1], point[0]], want) > 10]

    return check


def cases() -> dict:
    framed = {"position": offset(2, 2), "size": udim2(1, -4, 1, -4)}
    stroke = item("UIStroke", "Stroke", {"Thickness": 2.0, "Color": rgb(YELLOW), "ApplyStrokeMode": token(1)})
    into_notches = [fill("IntoNotch", RED, udim2(0, -40, 0, 100), offset(100, 50)),
                    fill("IntoNotchRight", DARK_GREEN, udim2(1, -60, 0, 200), offset(100, 50))]
    image = item("ImageLabel", "Fill", {"Size": scale(1, 1), "BackgroundTransparency": 1.0, "BorderSizePixel": 0,
                                        "Image": content(IMAGE)})
    tl, tr, bl, br = QUADRANTS[IMAGE]
    clips = {"BackgroundTransparency": 1.0, "ClipsDescendants": True}
    return {
        "ProbeDevice": (notch_gui(DEVICE, fill("Fill", GREEN)), painted((GREEN, FULL))),
        "ProbeCore": (notch_gui(CORE, fill("Fill", RED)), painted((RED, (62, 58, 812, 401)))),
        "B": (notch_gui(CORE, fill("Fill", RED, udim2(0, 0, 0, -58), udim2(1, 0, 1, 58))), painted((RED, FULL))),
        "Short": (notch_gui(CORE, fill("Fill", RED, udim2(0, 0, 0, -58), udim2(1, -1, 1, 58))),
                  painted((RED, (62, 0, 811, 401)))),
        "Bordered": (notch_gui(DEVICE, fill("Fill", RED, **framed, BorderSizePixel=2, BorderColor3=rgb(YELLOW))),
                     painted((YELLOW, FULL), (RED, (2, 2, 872, 399)))),
        "Stroked": (notch_gui(DEVICE, fill("Fill", RED, **framed, children=[stroke])),
                    painted((YELLOW, FULL), (RED, (2, 2, 872, 399)), corners=True)),
        "Inset2": (notch_gui(DEVICE, fill("Fill", RED, **framed)), painted((RED, (64, 2, 810, 399)))),
        "Img": (notch_gui(DEVICE, image),
                sampled(((10, 10), tl), ((864, 10), tr), ((10, 391), bl), ((864, 391), br),
                        ((218, 100), tl), ((655, 100), tr), ((218, 300), bl), ((655, 300), br))),
        "Cornered": (notch_gui(DEVICE, fill("Fill", RED, children=[corner(40)])), rounded(40)),
        "NoneExact": (notch_gui(NONE, fill("Fill", RED, offset(62, 0), udim2(0, 750, 1, 0))),
                      painted((RED, (62, 0, 812, 401)))),
        "Holder": (notch_gui(DEVICE, fill("Holder", RED, children=[fill("Child", RED)], **clips)),
                   painted((RED, FULL))),
        "ShortClip": (notch_gui(DEVICE, fill("ShortClip", RED, size=udim2(1, -1, 1, 0),
                                             children=[fill("Child", RED, size=udim2(1, 2, 1, 0))], **clips)),
                      painted((RED, (62, 0, 811, 401)))),
        "ClipDefault": (notch_gui(DEVICE, *into_notches),
                        painted((RED, (62, 100, 122, 150)), (DARK_GREEN, (752, 200, 812, 250)))),
        "ClipOff": (notch_gui(DEVICE, *into_notches, ClipToDeviceSafeArea=False),
                    painted((RED, (22, 100, 122, 150)), (DARK_GREEN, (752, 200, 852, 250)))),
        "Oversized": (notch_gui(DEVICE, fill("Fill", RED, scale(0.5, 0.5), udim2(1, 200, 1, 200), [corner(60)],
                                             AnchorPoint=vec2(0.5, 0.5))), painted((RED, FULL))),
        "ListFull": (notch_gui(DEVICE, listed(fill("Child", RED))), painted((RED, FULL))),
        "ListWide": (notch_gui(DEVICE, listed(fill("Child", DARK_GREEN, size=udim2(1, 100, 0, 100)))),
                     painted((DARK_GREEN, (62, 0, 812, 100)))),
    }


def render(name: str, roots: list[dict], icons: Path):
    """A model drawn on Studio's phone screen: the drawn rects and the RGB pixels."""
    ir = emit_ir(write_model(OUT / f"{name}.rbxmx", roots), OUT / f"{name}.json")
    rects: dict = {}
    devices.CURRENT = STUDIO_PHONE
    try:
        png = render_ir(ir, OUT / f"{name}.png", *SCREEN, bg_color=(0, 0, 0, 255), rect_map=rects,
                        icons_dir=icons, topbar_height=TOPBAR)
    finally:
        devices.CURRENT = None
    return rects, np.asarray(Image.open(png).convert("RGB")).astype(float)


def check_cases(check) -> None:
    underlay = item("ScreenGui", "ProbeNone", {"ScreenInsets": token(NONE), "DisplayOrder": 100},
                    [fill("Fill", BLUE)])
    with tempfile.TemporaryDirectory() as tmp:
        icons = quadrant_cache(Path(tmp))
        for name, (gui, expect) in cases().items():
            rects, img = render(name, [underlay, gui], icons)
            problems = expect(img)
            for path, want in RECTS.get(name, {}).items():
                got = rects.get(path)
                if got is None:
                    problems.append(f"{path} not drawn")
                elif not near((got.x, got.y, got.w, got.h), want):
                    problems.append(f"{path} at {fmt((got.x, got.y, got.w, got.h))}, Studio {fmt(want)}")
            check(not problems, f"notch {name}: {summary(problems)}")


def check_rules(check) -> None:
    check(insets.safe_area({}, *SCREEN) is None, "nothing to paint without device insets")
    devices.CURRENT = STUDIO_PHONE
    try:
        area = insets.safe_area({}, *SCREEN)
        check(area == insets.SafeArea(FULL, (62, 0, 750, 401), extend=True, clip=True),
              f"a default ScreenGui stretches and clips to the safe area ({area})")
        check(insets.safe_area({"ScreenInsets": "Enum.ScreenInsets.None"}, *SCREEN) is None,
              "ScreenInsets None paints nothing outside its area")
        # SafeAreaCompatibility None wasn't measured: it does what Roblox documents.
        for raw in ("Enum.SafeAreaCompatibility.None", 0,
                    {"_t": "EnumItem", "enum": "Enum.SafeAreaCompatibility", "name": "None", "value": 0}):
            area = insets.safe_area({"SafeAreaCompatibility": raw}, *SCREEN)
            check(area is not None and not area.extend and area.clip,
                  f"SafeAreaCompatibility {raw!r} stretches nothing and still clips ({area})")
        for raw in (False, "false"):
            area = insets.safe_area({"ClipToDeviceSafeArea": raw}, *SCREEN)
            check(area is not None and area.extend and not area.clip,
                  f"ClipToDeviceSafeArea {raw!r} stretches and doesn't clip ({area})")
        both_off = {"SafeAreaCompatibility": "Enum.SafeAreaCompatibility.None", "ClipToDeviceSafeArea": False}
        check(insets.safe_area(both_off, *SCREEN) is None, "both off paints nothing outside the area")
    finally:
        devices.CURRENT = None


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    check_cases(check)
    check_rules(check)
    print(f"\n{len(failures)} notch-fill checks failed" if failures else "\nnotch fill: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
