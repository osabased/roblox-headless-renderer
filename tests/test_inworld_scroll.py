#!/usr/bin/env python3
"""ScrollingFrames in a SurfaceGui and a BillboardGui, against Studio's measurements.

Studio measured the ten cases below in a 730x390 SurfaceGui and in a BillboardGui of
that size, and both gave a ScreenGui's numbers: each frame's window, canvas, clamped
CanvasPosition and Child rect as in STUDIO, bars drawn over a strip of the frame's own
background, each thumb where rhr.scrolling puts it. The models are built here as
Studio's probe built them, drawn as `rhr scene` draws in-world UI (render_gui_node)
and checked as tests/test_scroll_bars.py checks a ScreenGui. Each green Child must
also show where Studio shows it, and `rhr hitmap` must find it where it is drawn.

Run: python tests/test_inworld_scroll.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import item, offset, rgb, scale, token, udim2, vec2, write_model  # noqa: E402
from rhr import pipeline  # noqa: E402
from rhr.hitmap import build_hitmap  # noqa: E402
from rhr.ir import load_ir, resolve_path  # noqa: E402
from rhr.ui_engine.layout import Rect  # noqa: E402
from rhr.ui_layout import lay_out_pane  # noqa: E402
from test_fixtures import emit_ir  # noqa: E402
from test_scroll_bars import BACKDROP, GREEN, Cells, check_case, child, dist, fmt, near, summary  # noqa: E402

OUT = REPO / "out" / "inworld_scroll"
CANVAS = (730, 390)
GUIS = {"surface": "SurfacePart/Surface", "billboard": "BillboardPart/Billboard"}
# Studio's numbers per case, the same in both GUIs: window, canvas, CanvasPosition and
# the Child's rect from the frame's top left.
STUDIO = {
    "Vert": ((110, 170), (130, 300), (0, 0), {"Child": (0, 0, 130, 40)}),
    "Inset": ((110, 170), (110, 300), (0, 0), {"Child": (0, 0, 110, 40)}),
    "Left": ((110, 170), (110, 300), (0, 0), {"Child": (20, 0, 110, 40)}),
    "Both": ((110, 150), (300, 300), (0, 0), {"Child": (0, 0, 300, 300)}),
    "Fits": ((130, 170), (130, 170), (0, 0), {"Child": (0, 0, 130, 40)}),
    "AlwaysFits": ((130, 170), (110, 170), (0, 0), {"Child": (0, 0, 110, 40)}),
    "Mid": ((110, 170), (130, 600), (0, 300), {"Child": (0, 0, 130, 20)}),
    "OnePx": ((110, 170), (130, 600), (0, 1), {"Child": (0, -1, 130, 20)}),
    "Clamp": ((110, 150), (300, 300), (190, 150), {"Child": (60, 100, 50, 50)}),
    "AutoGrow": ((110, 170), (130, 350), (0, 0), {"Child": (0, 50, 100, 300)}),
}


def at(index: int) -> tuple[int, int]:
    """Where Studio's probe put cell `index` (from 0), five to a row."""
    return 10 + index % 5 * 143, 10 + index // 5 * 195


def active_child(size, position=None) -> dict:
    """The green Child, Active so that `rhr hitmap` lists it."""
    node = child(size, position)
    node["props"]["Active"] = True
    return node


def frames(cells: Cells) -> list[dict]:
    def cell(index: int, name: str, kid: dict, **kw) -> dict:
        return cells.frame(name, f"Backdrop/{name}", name, at(index), [kid], **kw)

    row = udim2(1, 0, 0, 40)
    return [
        cell(0, "Vert", active_child(row), CanvasSize=offset(0, 300)),
        cell(1, "Inset", active_child(row), vinset="ScrollBar", CanvasSize=offset(0, 300)),
        cell(2, "Left", active_child(row), left=True, vinset="ScrollBar", CanvasSize=offset(0, 300)),
        cell(3, "Both", active_child(scale(1, 1)), CanvasSize=offset(300, 300)),
        cell(4, "Fits", active_child(row), CanvasSize=offset(0, 100)),
        cell(5, "AlwaysFits", active_child(row), vinset="Always", CanvasSize=offset(0, 100)),
        cell(6, "Mid", active_child(udim2(1, 0, 0, 20), offset(0, 300)), CanvasSize=offset(0, 600),
             CanvasPosition=vec2(0, 300)),
        cell(7, "OnePx", active_child(udim2(1, 0, 0, 20)), CanvasSize=offset(0, 600), CanvasPosition=vec2(0, 1)),
        cell(8, "Clamp", active_child(offset(50, 50), offset(250, 250)), CanvasSize=offset(300, 300),
             CanvasPosition=vec2(1000, 1000)),
        cell(9, "AutoGrow", active_child(offset(100, 300), offset(0, 50)), probe=False, CanvasSize=offset(0, 100),
             AutomaticCanvasSize=token(2)),
    ]


def model(kind: str, cells: Cells) -> list[dict]:
    """Studio's probe: the cells on a backdrop, in a SurfaceGui or a BillboardGui on a part."""
    backdrop = item("Frame", "Backdrop", {"Size": scale(1, 1), "BackgroundColor3": rgb(BACKDROP),
                                          "BorderSizePixel": 0}, frames(cells))
    sibling = {"ZIndexBehavior": token(1)}
    if kind == "surface":
        gui = item("SurfaceGui", "Surface", {**sibling, "CanvasSize": vec2(*CANVAS)}, [backdrop])
    else:
        gui = item("BillboardGui", "Billboard", {**sibling, "Size": offset(*CANVAS), "ClipsDescendants": False},
                   [backdrop])
    part, _ = GUIS[kind].split("/")
    return [item("Part", part, {}, [gui])]


def draw(kind: str, cells: Cells):
    """The GUI drawn as `rhr scene` draws it: the IR, the drawn rects and the RGB pixels of
    the GUI's own area, then the whole picture's size and the GUI's offset in it.

    render_gui_node keeps its rects to itself, so they are recorded from its final draw.
    """
    ir = emit_ir(write_model(OUT / f"{kind}.rbxmx", model(kind, cells)), OUT / f"{kind}.json")
    drawn: dict = {}
    render_object = pipeline.render_object

    def recording(*args, **kwargs):
        if kwargs.get("draw", True):
            kwargs["rect_map"] = drawn
        return render_object(*args, **kwargs)

    pipeline.render_object = recording
    try:
        png, (left, top) = pipeline.render_gui_node(load_ir(ir), GUIS[kind], *CANVAS, OUT / f"{kind}.png")
    finally:
        pipeline.render_object = render_object
    picture = Image.open(png).convert("RGB")
    img = np.asarray(picture).astype(float)[top:top + CANVAS[1], left:left + CANVAS[0]]
    rects = {path: Rect(r.x - left, r.y - top, r.w, r.h) for path, r in drawn.items()}
    return ir, rects, img, picture.size, (left, top)


def shown_child(img, case: dict):
    """Where the green Child shows inside its frame, as (x, y, w, h), or None."""
    (fx, fy), w, h = case["screen"], case["w"], case["h"]
    ys, xs = np.nonzero(dist(img[fy:fy + h, fx:fx + w], GREEN) <= 8)
    if not len(xs):
        return None
    return fx + int(xs.min()), fy + int(ys.min()), int(xs.max() - xs.min()) + 1, int(ys.max() - ys.min()) + 1


def studio_child(case: dict, studio) -> tuple:
    """The part of the Child Studio shows: its rect cut to the frame's window."""
    (ww, wh), _, _, children = studio
    (fx, fy), t = case["screen"], case["t"]
    wx = fx + (t if case["left"] and case["w"] - ww == t else 0)
    x, y, w, h = children["Child"]
    x0, y0 = max(fx + x, wx), max(fy + y, fy)
    x1, y1 = min(fx + x + w, wx + ww), min(fy + y + h, fy + wh)
    return x0, y0, x1 - x0, y1 - y0


def check_hitmap(check, kind: str, ir, cells: Cells, img) -> None:
    found = {node["path"]: node["rect"] for node in build_hitmap(ir, *CANVAS)["nodes"]}
    for name, case in cells.cases.items():
        rect = found.get(f"{GUIS[kind]}/{case['path']}/Child")
        listed = (rect["x"], rect["y"], rect["w"], rect["h"]) if rect else None
        shown = shown_child(img, case)
        check(listed is not None and shown is not None and near(listed, shown, 1),
              f"{kind} hitmap {name}: Child listed at {fmt(listed) if listed else 'nowhere'}, "
              f"drawn at {fmt(shown) if shown else 'nowhere'}")


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    for kind, gui in GUIS.items():
        cells = Cells()
        ir, rects, img, size, origin = draw(kind, cells)
        scrolls: dict = {}
        lay_out_pane(resolve_path(load_ir(ir)["roots"], gui), (0, 0, *CANVAS), scrolls)
        for name, case in cells.cases.items():
            problems = check_case(img, rects, scrolls.get(f"{gui}/{case['path']}"), case, STUDIO[name], gui)
            want, shown = studio_child(case, STUDIO[name]), shown_child(img, case)
            if shown is None or not near(shown, want, 1):
                problems.append(f"Child shows at {fmt(shown) if shown else 'nowhere'}, Studio {fmt(want)}")
            check(not problems, f"{kind} {name}: {summary(problems)}")
        check(set(cells.cases) == set(STUDIO), f"{kind}: every Studio case is built")
        check_hitmap(check, kind, ir, cells, img)
        check(size == CANVAS and origin == (0, 0),
              f"{kind}: content outside the scroll windows doesn't grow the {CANVAS[0]}x{CANVAS[1]} picture "
              f"(drawn {size[0]}x{size[1]}, GUI at {origin})")
    print(f"\n{len(failures)} in-world scroll checks failed" if failures else "\nin-world scroll: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
