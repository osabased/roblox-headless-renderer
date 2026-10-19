#!/usr/bin/env python3
"""ScrollingFrame windows, canvases and bars, against Studio's measurements.

Studio measured each scroll case below on an 874x401 screen: the frame's window
(AbsoluteWindowSize), its canvas (AbsoluteCanvasSize), its clamped CanvasPosition and
its children's rects. The models are built here with the setups Studio's probes used
and travel the real path, lune IR -> layout -> renderer. Each case is checked three
ways: rhr.scrolling's numbers, the drawn rects and the pixels. A blue Probe child the
size of the canvas makes every window pixel content, so the window must show no
background, the bar strips nothing but background and bar, and the thumb must run
where Studio's does.

The bar-image cases draw test images of four flat quadrants from a temporary image
cache, so a sample in each quadrant shows which way up each part is drawn.

Run: python tests/test_scroll_bars.py
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
    QUADRANTS, colour3, content, item, offset, quadrant_cache, rgb, scale, token, udim, udim2, vec2, write_model,
)
from rhr import scrolling  # noqa: E402
from rhr.ir import load_ir, resolve_path  # noqa: E402
from rhr.missing_images import explain  # noqa: E402
from rhr.pipeline import render_ir  # noqa: E402
from rhr.ui_engine.assets import record_undrawn  # noqa: E402
from rhr.ui_layout import lay_out_pane  # noqa: E402
from test_fixtures import FIXTURES, emit_ir  # noqa: E402

OUT = REPO / "out" / "scroll_bars"
SCREEN = (874, 401)
GUI = "RhrScrollProbe"
PANEL = (52, 56, 70)
GREEN = (40, 160, 60)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
BACKDROP = (16, 16, 16)
# Roblox's own bar: ScrollBarImageColor3 at 128/255 opacity.
BAR_ALPHA = 128 / 255
INSET = {"None": 0, "ScrollBar": 1, "Always": 2}
PARTS = ("TopImage", "MidImage", "BottomImage")
DEFAULTS = ("rbxasset://textures/ui/Scroll/scroll-top.png", "rbxasset://textures/ui/Scroll/scroll-middle.png",
            "rbxasset://textures/ui/Scroll/scroll-bottom.png")
OTHER_FILE = "rbxasset://textures/DevConsole/Arrow.png"
THUMBNAIL = "rbxthumb://type=Asset&id=1&w=150&h=150"

# Studio's numbers per case: window, canvas, CanvasPosition, and each child's rect
# from the frame's top left.
STUDIO = {
    "Scale": ((110, 170), (130, 1203), (0, 0), {"Child": (0, 120.3, 130, 601.5)}),
    "AlwaysFits": ((130, 170), (110, 170), (0, 0), {"Child": (0, 0, 110, 40)}),
    "Both": ((110, 150), (300, 300), (0, 0), {"Child": (0, 0, 300, 300)}),
    "BothInset": ((110, 150), (300, 300), (0, 0), {"Child": (0, 0, 300, 300)}),
    "Left": ((110, 170), (110, 300), (0, 0), {"Child": (20, 0, 110, 40)}),
    "MinThumb": ((110, 170), (130, 20000), (0, 0), {}),
    "Disabled": ((110, 170), (130, 300), (0, 0), {"Child": (0, 0, 130, 40)}),
    "DirY": ((110, 170), (1748, 802), (0, 0), {"Child": (0, 0, 1748, 40)}),
    "Padded": ((110, 170), (110, 300), (0, 0), {"Child": (12, 12, 86, 138)}),
    "CrossV": ((110, 150), (874, 300), (0, 0), {"Child": (0, 0, 874, 40)}),
    "CrossH": ((110, 150), (300, 401), (0, 0), {"Child": (0, 0, 40, 401)}),
    "PadParent": ((50, 70), (90, 260), (0, 0), {}),
    "Nested": ((120, 170), (130, 500), (0, 0), {"Inner": (0, 0, 100, 100)}),
    "NestedInner": ((90, 100), (100, 500), (0, 0), {}),
    "Min6": ((124, 170), (130, 20000), (0, 0), {}),
    "Min30": ((100, 170), (130, 20000), (0, 0), {}),
    "MinMid": ((110, 170), (130, 20000), (0, 9915), {}),
    "HalfAfter": ((110, 170), (130, 600), (0, 300), {}),
    "AutoMax": ((110, 170), (130, 250), (0, 0), {"Child": (0, 0, 130, 100)}),
    "AutoScale": ((110, 170), (130, 200.5), (0, 0), {"Child": (0, 0, 130, 100)}),
    "LeftBoth": ((110, 150), (300, 300), (0, 0), {"Child": (20, 0, 300, 300)}),
    "HLong": ((130, 150), (600, 170), (0, 0), {"Child": (0, 0, 40, 170)}),
    "HLongInset": ((130, 150), (600, 150), (0, 0), {"Child": (0, 0, 40, 150)}),
    "Thin": ((126, 170), (130, 300), (0, 0), {}),
    "BoundaryInset": ((110, 150), (600, 160), (0, 0), {}),
    "BoundaryNone": ((110, 150), (600, 170), (0, 0), {}),
    "ClampNone": ((110, 150), (300, 300), (190, 150), {}),
    "ClampInset": ((110, 150), (300, 300), (190, 150), {}),
    "AlwaysOverflow": ((110, 170), (110, 300), (0, 0), {}),
    "BoundaryV": ((110, 150), (120, 600), (0, 0), {}),
    "LeftNone": ((110, 170), (130, 300), (0, 0), {"Child": (0, 0, 130, 40)}),
    "LeftAlwaysFits": ((130, 170), (110, 170), (0, 0), {"Child": (20, 0, 110, 40)}),
    "LeftFits": ((130, 170), (130, 170), (0, 0), {"Child": (0, 0, 130, 40)}),
}

TOP, MID, BOTTOM = list(QUADRANTS)
UNCACHED = "rbxassetid://990000099"
BAR_BG = (40, 40, 40)
BAR_T = 48
TINTS = {"Col": ((1.0, 0.5, 0.0), 0.5)}
BAR_CELLS = [
    ("Vtop", 10, 10, 80, 380, True, 760, (TOP, "", "")),
    ("Vmid", 100, 10, 80, 380, True, 760, ("", MID, "")),
    ("Vbot", 190, 10, 80, 380, True, 760, ("", "", BOTTOM)),
    ("Vall", 280, 10, 80, 380, True, 760, (TOP, MID, BOTTOM)),
    ("Vmin", 370, 10, 80, 380, True, 38000, (TOP, MID, BOTTOM)),
    ("Htop", 460, 10, 404, 70, False, 808, (TOP, "", "")),
    ("Hmid", 460, 90, 404, 70, False, 808, ("", MID, "")),
    ("Hbot", 460, 170, 404, 70, False, 808, ("", "", BOTTOM)),
    ("Hall", 460, 250, 404, 70, False, 808, (TOP, MID, BOTTOM)),
    ("Col", 460, 330, 190, 60, False, 380, (MID, MID, MID)),
    ("Hmin", 660, 330, 204, 60, False, 20400, (TOP, MID, BOTTOM)),
]
EXTRA_CELLS = [
    ("Mixed", 10, 10, 80, 380, True, 760, (DEFAULTS[0], MID, DEFAULTS[2])),
    ("MissingId", 100, 10, 80, 380, True, 760, (UNCACHED, "", "")),
    ("MissingFile", 190, 10, 80, 380, True, 760, (OTHER_FILE, "", "")),
    ("MissingThumb", 280, 10, 80, 380, True, 760, (THUMBNAIL, "", "")),
]


def render(name: str, roots: list[dict], icons: Path | None = None):
    """A model drawn on Studio's screen: its IR, the drawn rects and the RGB pixels."""
    ir = emit_ir(write_model(OUT / f"{name}.rbxmx", roots), OUT / f"{name}.json")
    rects: dict = {}
    png = render_ir(ir, OUT / f"{name}.png", *SCREEN, bg_color=(0, 0, 0, 255), rect_map=rects, icons_dir=icons)
    return ir, rects, np.asarray(Image.open(png).convert("RGB")).astype(float)


def fmt(values) -> str:
    return "(" + ",".join(f"{value:g}" for value in values) + ")"


def summary(problems: list[str]) -> str:
    if not problems:
        return "as Studio"
    return "; ".join(problems[:4]) + (f"; +{len(problems) - 4} more" if len(problems) > 4 else "")


def near(a, b, tol: float = 1.5) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def mask(shape, rect, grow: int):
    """Pixels of an (x, y, w, h) rect: grown by `grow` px, or shrunk when it is negative."""
    x, y, w, h = rect
    lo, hi = (np.floor, np.ceil) if grow >= 0 else (np.ceil, np.floor)
    x0, y0 = int(lo(x)) - grow, int(lo(y)) - grow
    x1, y1 = int(hi(x + w)) + grow, int(hi(y + h)) + grow
    out = np.zeros(shape, bool)
    out[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = True
    return out


def dist(img, colour):
    return np.abs(img - np.asarray(colour, float)).max(axis=-1)


def segment(img, a, b):
    """How far each pixel is along the blend from colour a to b (0..1), and off it."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    s = np.clip(((img - a) @ d) / (d @ d), 0.0, 1.0)
    return s, np.linalg.norm(img - (a + s[..., None] * d), axis=-1)


def runs(on) -> list[tuple[int, int]]:
    edges = np.flatnonzero(np.diff(np.concatenate(([0], on.astype(int), [0]))))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2])]


def thumb_span(window: float, canvas: float, position: float, t: float) -> tuple[float, float]:
    """Studio's thumb on a track as long as the window: its start and length."""
    length = max(2 * t, window * window / canvas)
    start = 0.0 if canvas <= window else (window - length) * position / (canvas - window)
    return start, length


def pixel(img, point):
    return img[int(point[1]), int(point[0])]


def at(index: int) -> tuple[int, int]:
    return 10 + (index - 1) % 6 * 143, 10 + (index - 1) // 6 * 195


def child(size, position=None):
    props = {"Size": size, "BackgroundColor3": rgb(GREEN), "BorderSizePixel": 0}
    if position:
        props["Position"] = position
    return item("Frame", "Child", props)


def padding(px: int):
    return item("UIPadding", "Pad", {f"Padding{side}": udim(0, px) for side in ("Left", "Right", "Top", "Bottom")})


def canvas_probe():
    return item("Frame", "Probe", {"Size": scale(1, 1), "BackgroundColor3": rgb(BLUE), "BorderSizePixel": 0,
                                   "ZIndex": 0})


def gui(frames: list[dict]) -> list[dict]:
    backdrop = item("Frame", "Backdrop", {"Size": scale(1, 1), "BackgroundColor3": rgb(BACKDROP),
                                          "BorderSizePixel": 0}, frames)
    return [item("ScreenGui", GUI, {"ScreenInsets": token(0), "ZIndexBehavior": token(1)}, [backdrop])]


class Cells:
    """The ScrollingFrame cases of one screen, as each was built and where it sits."""

    def __init__(self) -> None:
        self.cases: dict[str, dict] = {}

    def frame(self, case: str, path: str, name: str, xy, children=(), *, screen=None, w=130, h=170, t=20,
              left=False, vinset="None", hinset="None", pad=0, bg=PANEL, bar=RED, probe=True, **props) -> dict:
        """A ScrollingFrame at `xy` in its parent; `screen` is its top left on screen when
        that is not `xy`. With `bg` None the case has no pixel checks."""
        p = {"Position": offset(*xy), "Size": offset(w, h), "BorderSizePixel": 0, "ScrollBarThickness": t}
        if bg:
            p["BackgroundColor3"] = rgb(bg)
        if bar:
            p["ScrollBarImageColor3"] = rgb(bar)
        if left:
            p["VerticalScrollBarPosition"] = token(1)
        if vinset != "None":
            p["VerticalScrollBarInset"] = token(INSET[vinset])
        if hinset != "None":
            p["HorizontalScrollBarInset"] = token(INSET[hinset])
        p.update(props)
        kids = ([padding(pad)] if pad else []) + list(children) + ([canvas_probe()] if probe else [])
        self.cases[case] = {"path": path, "screen": screen or xy, "w": w, "h": h, "t": t, "left": left,
                            "vinset": vinset, "pad": pad, "bg": bg, "bar": bar, "probe": probe}
        return item("ScrollingFrame", name, p, kids)

    def cell(self, index: int, name: str, children=(), **kw) -> dict:
        return self.frame(name, f"Backdrop/{name}", name, at(index), children, **kw)


def insets_screen(cells: Cells) -> list[dict]:
    return gui([
        cells.cell(1, "Scale", [child(scale(1, 0.5), udim2(0, 0, 0.1, 0))], CanvasSize=udim2(0, 0, 3, 0)),
        cells.cell(2, "AlwaysFits", [child(udim2(1, 0, 0, 40))], vinset="Always", CanvasSize=offset(0, 100)),
        cells.cell(3, "Both", [child(scale(1, 1))], CanvasSize=offset(300, 300)),
        cells.cell(4, "BothInset", [child(scale(1, 1))], vinset="ScrollBar", hinset="ScrollBar",
                   CanvasSize=offset(300, 300)),
        cells.cell(5, "Left", [child(udim2(1, 0, 0, 40))], left=True, vinset="ScrollBar",
                   CanvasSize=offset(0, 300)),
        cells.cell(6, "MinThumb", CanvasSize=offset(0, 20000)),
        cells.cell(7, "Disabled", [child(udim2(1, 0, 0, 40))], CanvasSize=offset(0, 300), ScrollingEnabled=False),
        cells.cell(8, "DirY", [child(udim2(1, 0, 0, 40))], CanvasSize=scale(2, 2), ScrollingDirection=token(2)),
        cells.cell(9, "Padded", [child(scale(1, 0.5))], pad=12, vinset="ScrollBar", CanvasSize=offset(0, 300)),
        cells.cell(10, "CrossV", [child(udim2(1, 0, 0, 40))], vinset="ScrollBar",
                   CanvasSize=udim2(1, 0, 0, 300)),
        cells.cell(11, "CrossH", [child(udim2(0, 40, 1, 0))], hinset="ScrollBar",
                   CanvasSize=udim2(0, 300, 1, 0)),
    ])


def thumbs_screen(cells: Cells) -> list[dict]:
    x, y = at(1)
    inner = cells.frame("PadParent", "Backdrop/PadParent/Inner", "Inner", (0, 0), screen=(x + 20, y + 20), w=60,
                        h=80, t=10, CanvasSize=udim2(1, 0, 2, 0))
    pad_parent = item("Frame", "PadParent", {"Position": offset(x, y), "Size": offset(130, 170),
                                              "BackgroundColor3": rgb((30, 30, 40)), "BorderSizePixel": 0},
                      [padding(20), inner])
    nested_inner = cells.frame("NestedInner", "Backdrop/Nested/Inner", "Inner", (0, 0), screen=at(2), w=100,
                               h=100, t=10, bg=(80, 80, 110), CanvasSize=udim2(0, 0, 1, 0))
    return gui([
        pad_parent,
        cells.cell(2, "Nested", [nested_inner], t=10, CanvasSize=offset(0, 500)),
        cells.cell(3, "Min6", t=6, CanvasSize=offset(0, 20000)),
        cells.cell(4, "Min30", t=30, CanvasSize=offset(0, 20000)),
        cells.cell(5, "MinMid", CanvasSize=offset(0, 20000), CanvasPosition=vec2(0, 9915)),
        cells.cell(6, "HalfAfter", CanvasSize=offset(0, 600), CanvasPosition=vec2(0, 300)),
        cells.cell(7, "AutoMax", [child(udim2(1, 0, 0, 100))], probe=False, CanvasSize=offset(0, 250),
                   AutomaticCanvasSize=token(2)),
        cells.cell(8, "AutoScale", [child(udim2(1, 0, 0, 100))], probe=False, CanvasSize=udim2(0, 0, 0.5, 0),
                   AutomaticCanvasSize=token(2)),
        cells.cell(9, "LeftBoth", [child(scale(1, 1))], left=True, vinset="ScrollBar", hinset="ScrollBar",
                   CanvasSize=offset(300, 300)),
        cells.cell(10, "HLong", [child(udim2(0, 40, 1, 0))], CanvasSize=offset(600, 0)),
        cells.cell(11, "HLongInset", [child(udim2(0, 40, 1, 0))], hinset="ScrollBar", CanvasSize=offset(600, 0)),
        cells.cell(12, "Thin", t=4, CanvasSize=offset(0, 300)),
    ])


def edges_screen(cells: Cells) -> list[dict]:
    def left(index: int, name: str, **kw) -> dict:
        plain = item("Frame", "Child", {"Size": udim2(1, 0, 0, 40)})
        return cells.cell(index, name, [plain], left=True, bg=None, bar=None, probe=False, **kw)

    return gui([
        cells.cell(1, "BoundaryInset", hinset="ScrollBar", CanvasSize=offset(600, 160)),
        cells.cell(2, "BoundaryNone", CanvasSize=offset(600, 160)),
        cells.cell(3, "ClampNone", CanvasSize=offset(300, 300), CanvasPosition=vec2(1000, 1000)),
        cells.cell(4, "ClampInset", vinset="ScrollBar", hinset="ScrollBar", CanvasSize=offset(300, 300),
                   CanvasPosition=vec2(1000, 1000)),
        cells.cell(5, "AlwaysOverflow", vinset="Always", CanvasSize=offset(0, 300)),
        cells.cell(6, "BoundaryV", vinset="ScrollBar", CanvasSize=offset(120, 600)),
        left(7, "LeftNone", CanvasSize=offset(0, 300)),
        left(8, "LeftAlwaysFits", vinset="Always", CanvasSize=offset(0, 100)),
        left(9, "LeftFits", vinset="ScrollBar", CanvasSize=offset(0, 100)),
    ])


def check_case(img, rects, scroll, case: dict, studio, gui: str = GUI) -> list[str]:
    (ww, wh), (cw, ch), (cpx, cpy), children = studio
    (fx, fy), w, h, t, pad, left = case["screen"], case["w"], case["h"], case["t"], case["pad"], case["left"]
    v_shown, h_shown = w - ww == t, h - wh == t
    v_inset = case["vinset"] == "Always" or (case["vinset"] == "ScrollBar" and v_shown)
    window = (fx + (t if left and v_shown else 0), fy, ww, wh)
    ox, oy = fx - cpx + (t if left and v_inset else 0), fy - cpy
    problems = []
    if scroll is None:
        problems.append("no scrolling solved")
    else:
        for label, got, want in (("window", scroll.window, window), ("canvas", scroll.canvas, (cw, ch)),
                                 ("CanvasPosition", scroll.position, (cpx, cpy))):
            if not near(got, want):
                problems.append(f"{label} {fmt(got)}, Studio {fmt(want)}")

    path = f"{gui}/{case['path']}"
    content_rects = {f"{path}/{name}": (fx + x, fy + y, width, height)
                     for name, (x, y, width, height) in children.items()}
    if case["probe"]:
        content_rects[f"{path}/Probe"] = (ox + pad, oy + pad, cw - 2 * pad, ch - 2 * pad)
    for key, rect in {path: (fx, fy, w, h), **content_rects}.items():
        got = rects.get(key)
        label = key.removeprefix(path).lstrip("/") or "frame"
        if got is None:
            problems.append(f"{label} not drawn")
        elif not near((got.x, got.y, got.w, got.h), rect):
            problems.append(f"{label} at {fmt((got.x, got.y, got.w, got.h))}, Studio {fmt(rect)}")
    if case["bg"] is None:
        return problems

    shape = img.shape[:2]
    bg = np.asarray(case["bg"], float)
    bar = bg + (np.asarray(case["bar"], float) - bg) * BAR_ALPHA
    inside = np.zeros(shape, bool)
    reach = np.zeros(shape, bool)
    for rect in content_rects.values():
        inside |= mask(shape, rect, -1)
        reach |= mask(shape, rect, 1)
    window_px = mask(shape, window, -1)
    is_bg = dist(img, bg) <= 8
    if (hidden := window_px & inside & is_bg).any():
        problems.append(f"{int(hidden.sum())} window px show the background over content")
    if (stray := window_px & ~reach & ~is_bg).any():
        problems.append(f"{int(stray.sum())} window px painted outside the content")
    along, off = segment(img, bg, bar)
    strip = mask(shape, (fx, fy, w, h), -1) & ~mask(shape, window, 1)
    if (leaked := strip & (off > 8)).any():
        problems.append(f"{int(leaked.sum())} strip px are neither background nor bar")

    def thumb(label: str, line, first: int, origin: float, window_len: float, canvas_len: float,
              position: float) -> None:
        start, length = thumb_span(window_len, canvas_len, position, t)
        want = (origin + start + t / 2, origin + start + length - t / 2)
        found = [(first + a, first + b) for a, b in runs(line >= 0.5)]
        if len(found) != 1 or not near(found[0], want):
            problems.append(f"{label} thumb at {found or 'nowhere'}, Studio {fmt(want)}")

    if v_shown:
        column = int(np.floor(fx + t / 2 if left else fx + w - t / 2))
        top = round(fy)
        thumb("vertical", along[top:round(fy + wh), column], top, fy, wh, ch, cpy)
    if h_shown:
        row = int(np.floor(fy + h - t / 2))
        start = round(fx)
        thumb("horizontal", along[row, start:round(fx + ww)], start, fx, ww, cw, cpx)
    return problems


def check_scroll(check) -> None:
    built: set[str] = set()
    for name, build in (("scroll_insets", insets_screen), ("scroll_thumbs", thumbs_screen),
                        ("scroll_edges", edges_screen)):
        cells = Cells()
        ir, rects, img = render(name, build(cells))
        scrolls: dict = {}
        lay_out_pane(resolve_path(load_ir(ir)["roots"], GUI), (0, 0, *SCREEN), scrolls)
        for case_name, case in cells.cases.items():
            scroll = scrolls.get(f"{GUI}/{case['path']}")
            check(not (problems := check_case(img, rects, scroll, case, STUDIO[case_name])),
                  f"scroll {case_name}: {summary(problems)}")
        built |= set(cells.cases)
    check(built == set(STUDIO), f"every Studio case is built (left out: {sorted(set(STUDIO) - built)})")


def bar_gui(name: str, cells) -> list[dict]:
    frames = []
    for cell, x, y, w, h, vertical, canvas, parts in cells:
        tint, transparency = TINTS.get(cell, ((1.0, 1.0, 1.0), 0.0))
        frames.append(item("ScrollingFrame", cell, {
            "Position": offset(x, y), "Size": offset(w, h), "BackgroundColor3": rgb(BAR_BG), "BorderSizePixel": 0,
            "ScrollBarThickness": BAR_T, "ScrollingDirection": token(2 if vertical else 1),
            "CanvasSize": offset(0, canvas) if vertical else offset(canvas, 0),
            **{part: content(uri) for part, uri in zip(PARTS, parts)},
            "ScrollBarImageColor3": colour3(*tint), "ScrollBarImageTransparency": transparency,
        }))
    back = item("Frame", "Back", {"Size": scale(1, 1), "BackgroundColor3": rgb((0, 0, 0)), "BorderSizePixel": 0})
    return [item("ScreenGui", name, {"ScreenInsets": token(0), "ZIndexBehavior": token(1)}, [back, *frames])]


def bar_boxes(w, h, vertical, canvas) -> list[tuple[float, float]]:
    """Where TopImage, MidImage and BottomImage go along the track, at CanvasPosition 0."""
    track = h if vertical else w
    start, length = thumb_span(track, canvas, 0, BAR_T)
    return [(start, start + BAR_T), (start + BAR_T, start + length - BAR_T), (start + length - BAR_T, start + length)]


def part_samples(x, y, w, h, vertical, box):
    """Quadrant centres of a part's box, each with the image quadrant Studio shows there."""
    a, b = box
    if vertical:
        x0 = x + w - BAR_T
        xs, ys = (x0 + BAR_T / 4, x0 + 3 * BAR_T / 4), (y + a + (b - a) / 4, y + a + 3 * (b - a) / 4)
        return [((xs[0], ys[0]), 0), ((xs[1], ys[0]), 1), ((xs[0], ys[1]), 2), ((xs[1], ys[1]), 3)]
    y0 = y + h - BAR_T
    xs, ys = (x + a + (b - a) / 4, x + a + 3 * (b - a) / 4), (y0 + BAR_T / 4, y0 + 3 * BAR_T / 4)
    # A horizontal bar shows each image turned a quarter turn counter-clockwise.
    return [((xs[0], ys[0]), 1), ((xs[1], ys[0]), 3), ((xs[0], ys[1]), 0), ((xs[1], ys[1]), 2)]


def check_bars(check) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        icons = quadrant_cache(Path(tmp))
        _, _, img = render("bars", bar_gui("BarProbe", BAR_CELLS), icons)
        for name, x, y, w, h, vertical, canvas, parts in BAR_CELLS:
            tint, transparency = TINTS.get(name, ((1.0, 1.0, 1.0), 0.0))
            alpha = 1 - transparency
            problems = []
            boxes = bar_boxes(w, h, vertical, canvas)
            for part, uri, box in zip(PARTS, parts, boxes):
                if box[1] - box[0] <= 0:
                    continue
                for point, quadrant in part_samples(x, y, w, h, vertical, box):
                    want = np.asarray(BAR_BG, float)
                    if uri:
                        want = want * (1 - alpha) + np.asarray(QUADRANTS[uri][quadrant], float) * tint * alpha
                    if dist(pixel(img, point), want) > 10:
                        problems.append(f"{part} at {fmt(point)}: {fmt(pixel(img, point))}, Studio {fmt(want)}")
            beyond = boxes[2][1] + 20
            if beyond < (h if vertical else w):
                point = (x + w - BAR_T / 2, y + beyond) if vertical else (x + beyond, y + h - BAR_T / 2)
                if dist(pixel(img, point), BAR_BG) > 10:
                    problems.append(f"track past the thumb at {fmt(point)}: {fmt(pixel(img, point))}")
            check(not problems, f"bar {name}: {summary(problems)}")

        with record_undrawn() as undrawn:
            _, _, img = render("bars_extra", bar_gui("BarExtra", EXTRA_CELLS), icons)
        cap = np.asarray(BAR_BG, float) + (255 - np.asarray(BAR_BG, float)) * BAR_ALPHA
        _, x, y, w, h, _, canvas, _ = EXTRA_CELLS[0]
        boxes = bar_boxes(w, h, True, canvas)
        problems = []
        for label, along, want in (("top box, upper half", boxes[0][0] + BAR_T / 4, BAR_BG),
                                   ("top box, lower half", boxes[0][0] + 3 * BAR_T / 4, cap),
                                   ("bottom box, upper half", boxes[2][0] + BAR_T / 4, cap),
                                   ("bottom box, lower half", boxes[2][0] + 3 * BAR_T / 4, BAR_BG)):
            point = (x + w - BAR_T / 2, y + along)
            if dist(pixel(img, point), want) > 10:
                problems.append(f"default {label}: {fmt(pixel(img, point))}, Studio {fmt(want)}")
        for point, quadrant in part_samples(x, y, w, h, True, boxes[1]):
            want = QUADRANTS[MID][quadrant]
            if dist(pixel(img, point), want) > 10:
                problems.append(f"custom MidImage at {fmt(point)}: {fmt(pixel(img, point))}, Studio {fmt(want)}")
        check(not problems, f"bar Mixed, Roblox's own caps around a custom middle: {summary(problems)}")

        missing = explain(undrawn, offline=True, icons_dir=icons)
        for name, x, y, w, h, _, _, (uri, _, _) in EXTRA_CELLS[1:]:
            problems = []
            drawn = int((dist(img[y:y + h, x + w - BAR_T:x + w], BAR_BG) > 10).sum())
            if drawn:
                problems.append(f"{drawn} px drawn")
            listed = [entry for entry in missing if entry["path"] == f"BarExtra/{name}" and entry["uri"] == uri
                      and entry["class"] == "ScrollingFrame" and entry["reason"]]
            if not listed:
                problems.append(f"not listed as missing (listed: {[entry['path'] for entry in missing]})")
            elif uri == UNCACHED and listed[0]["reason"] != "offline":
                problems.append(f"listed as {listed[0]['reason']!r}, not offline")
            check(not problems, f"bar {name}: {uri} draws nothing and is listed missing: {summary(problems)}")
        listed = sorted({entry["uri"] for entry in missing} & set(DEFAULTS))
        check(not listed, f"Roblox's own bar images aren't listed missing (listed: {listed})")


def check_rules(check) -> None:
    for part, value, kind in (
        ("TopImage", DEFAULTS[0], "default"),
        ("BottomImage", DEFAULTS[2], "default"),
        ("MidImage", DEFAULTS[0], "missing"),
        ("TopImage", OTHER_FILE, "missing"),
        ("TopImage", THUMBNAIL, "missing"),
        ("TopImage", "rbxassetid://123", "asset"),
        ("TopImage", "", "none"),
        ("TopImage", "rbxassetid://0", "none"),
        ("TopImage", "garbage", "missing"),
    ):
        got = scrolling.classify(part, value)
        check(got[0] == kind, f"{part} {value!r} draws as {kind} ({got})")
    check(scrolling.classify("MidImage", "rbxassetid://123") == ("asset", "123"), "an asset id draws from its id")


def check_ir(check) -> None:
    roots = load_ir(emit_ir(FIXTURES / "scroll_bar_images.rbxmx", OUT / "scroll_bar_images.json"))["roots"]
    for name, want in (("Unset", DEFAULTS), ("Empty", ("", "", "")), ("Custom", (OTHER_FILE, MID, THUMBNAIL))):
        props = resolve_path(roots, f"ScrollBarImages/{name}").get("props") or {}
        got = tuple(props.get(part) for part in PARTS)
        check(got == want, f"IR: {name}'s bar images read {got}")


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    check_scroll(check)
    check_bars(check)
    check_rules(check)
    check_ir(check)
    print(f"\n{len(failures)} scroll-bar checks failed" if failures else "\nscroll bars: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
