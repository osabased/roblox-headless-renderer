#!/usr/bin/env python3
"""ZIndexBehavior Global and Sibling stacking, against Studio's measurements.

Studio measured each case in both behaviors: the hit order at a point from
GetGuiObjectsAtPosition (topmost first), and the pixels of screen captures. Hit order
matched draw order everywhere but in a CanvasGroup's overflow under Global. The models
are built here as Studio's probes were and travel the real path, lune IR -> layout ->
renderer and hit map.

Draw order is read from pixels by peeling. Copy k of a case hides the backgrounds of the
k objects Studio has on top at the case's first point, so that point must show the next
object's colour, and the backdrop once every object is hidden. Each object has a colour
of its own within its case.

Under Global a CanvasGroup is not drawn as a group: Studio fades and tints only its own
background and does not clip its children's drawing, though it still clips their hit
regions to its rect. The CanvasGroup scenes rebuild Studio's captures of that.

Run: python tests/test_zindex_behavior.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import colour3, item, offset, rgb, token, udim, write_model  # noqa: E402
from rhr.hitmap import at_point, build_hitmap  # noqa: E402
from rhr.ir import load_ir, resolve_path  # noqa: E402
from rhr.pipeline import render_ir  # noqa: E402
from rhr.ui_layout import lay_out_pane  # noqa: E402
from test_fixtures import emit_ir  # noqa: E402

OUT = REPO / "out" / "zindex_behavior"
ZINDEX_BEHAVIOR = {"Global": 0, "Sibling": 1}
LAYOUT_ORDER = token(2)
GAP = 40
TOL = 10
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (150, 150, 150)
FADED_GRAY = (202, 202, 202)
RED = (230, 30, 30)
GREEN = (30, 180, 60)
BLUE = (40, 70, 230)
YELLOW = (250, 220, 0)
PALETTE = (RED, GREEN, BLUE, YELLOW, GRAY, (255, 140, 0), (150, 50, 200), (0, 210, 220), (20, 20, 20),
           (120, 70, 20), (255, 120, 200))


def frame(name: str, z: int, xy, wh, colour, children=(), cls: str = "Frame", **props) -> dict:
    return item(cls, name, {"Position": offset(*xy), "Size": offset(*wh), "ZIndex": z, "BackgroundColor3": rgb(colour),
                            "BorderSizePixel": 0, "Active": True, **props}, children)


def node(name: str, z: int, xy, wh, children=(), cls: str = "Frame", **props) -> dict:
    """An object of an order case, coloured, named and placed for each copy by `copy`."""
    return {"cls": cls, "name": name, "z": z, "xy": xy, "wh": wh, "props": props, "children": list(children)}


def scroller(name: str, z: int, xy, wh, canvas, thickness: int, children) -> dict:
    return node(name, z, xy, wh, children, "ScrollingFrame", CanvasSize=offset(*canvas), ScrollBarThickness=thickness)


def stacked(name: str, wh, layout: dict, cells) -> dict:
    """A holder whose layout overlaps its children, which are (name, ZIndex, LayoutOrder)."""
    return node("Holder", 2, (240, 100), wh, [layout] + [node(n, z, (0, 0), (120, 60), LayoutOrder=order)
                                                       for n, z, order in cells])


# Each case: the box its objects cover, the objects, and Studio's order at each point
# (topmost first) under Global and under Sibling. Copies are peeled at the first point.
CASES = {
    "Nested": ((240, 140, 120, 120), [
        node("A", 2, (240, 140), (120, 120), [
            node("A1", 1, (10, 10), (100, 100)),
            node("A2", 4, (10, 10), (100, 100), [node("A2a", 1, (10, 10), (80, 80))]),
        ]),
        node("B", 1, (240, 140), (120, 120), [node("B1", 3, (10, 10), (100, 100)), node("B2", 2, (10, 10), (100, 100))]),
        node("C", 2, (240, 140), (120, 120), [node("C1", 2, (10, 10), (100, 100))]),
    ], {(300, 200): ("A2 B1 C1 C B2 A B A2a A1", "C1 C A2a A2 A1 A B1 B2 B")}),
    "Clip": ((150, 100, 300, 200), [
        node("K", 3, (240, 140), (120, 120), [
            node("K1", 1, (-60, -60), (240, 240)),
            node("K2", 6, (60, 60), (240, 240)),
        ], ClipsDescendants=True),
        node("L", 2, (150, 100), (300, 200)),
        node("M", 4, (280, 180), (40, 40)),
    ], {(310, 210): ("K2 M K L K1", "M K2 K1 K L"), (400, 250): ("L", "L")}),
    "Scroll": ((200, 100, 300, 220), [
        scroller("S", 3, (240, 140), (160, 120), (400, 400), 12, [
            node("S1", 1, (0, 0), (150, 110)),
            node("S2", 5, (20, 20), (150, 110)),
        ]),
        node("O1", 2, (200, 100), (300, 220)),
        node("O2", 4, (300, 180), (40, 40)),
    ], {(310, 200): ("S2 O2 S O1 S1", "O2 S2 S1 S O1"), (394, 200): ("S O1", "S O1")}),
    "NestedScroll": ((200, 100, 300, 250), [
        node("Y", 1, (200, 100), (300, 250)),
        scroller("Outer", 2, (240, 120), (200, 160), (600, 600), 10, [
            scroller("Inner", 1, (10, 10), (150, 120), (400, 400), 10, [
                node("In1", 5, (0, 0), (140, 110)),
                node("In2", 1, (10, 10), (140, 110)),
            ]),
            node("OuterChild", 3, (20, 20), (150, 110)),
        ]),
        node("X", 4, (300, 180), (30, 30)),
    ], {(310, 190): ("In1 X OuterChild Outer In2 Inner Y", "X OuterChild In1 In2 Inner Outer Y")}),
    "CanvasGroup": ((200, 100, 300, 220), [
        node("G", 3, (240, 140), (160, 120), [
            node("G1", 1, (0, 0), (150, 110)),
            node("G2", 6, (20, 20), (150, 110)),
        ], "CanvasGroup"),
        node("H", 2, (200, 100), (300, 220)),
        node("J", 4, (300, 180), (40, 40)),
    ], {(310, 200): ("G2 J G H G1", "J G2 G1 G H")}),
    "List": ((240, 100, 200, 200), [
        stacked("Holder", (200, 200), item("UIListLayout", "Layout", {"Padding": udim(0, -50), "SortOrder": LAYOUT_ORDER}),
                [("i1", 1, 3), ("i2", 3, 1), ("i3", 1, 4), ("i4", 1, 2)]),
    ], {(300, 145): ("i2 Holder i4 i3 i1", "i2 i4 i3 i1 Holder")}),
    "GridRows": ((240, 100, 200, 200), [
        stacked("Holder", (200, 200), item("UIGridLayout", "Layout", {
            "CellSize": offset(120, 60), "CellPadding": offset(0, -50), "SortOrder": LAYOUT_ORDER,
        }), [("g1", 1, 3), ("g2", 3, 1), ("g3", 1, 4), ("g4", 1, 2)]),
    ], {(300, 145): ("g2 Holder g4 g3 g1", "g2 g4 g3 g1 Holder")}),
    "GridColumns": ((240, 100, 300, 100), [
        stacked("Holder", (300, 100), item("UIGridLayout", "Layout", {
            "CellSize": offset(60, 60), "CellPadding": offset(-40, 0), "FillDirectionMaxCells": 4,
            "SortOrder": LAYOUT_ORDER,
        }), [("g1", 2, 3), ("g2", 1, 1), ("g3", 1, 4), ("g4", 1, 2)]),
    ], {(295, 130): ("g1 Holder g4 g2", "g1 g4 g2 Holder")}),
}

# Studio's capture of one Global gui: CanvasGroups among other objects, a white frame at
# ZIndex -10 behind them all. Points are on screen.
MIXED = {(320, 60): (95, 110, 192), (350, 100): (90, 165, 106), (440, 80): YELLOW, (310, 150): FADED_GRAY,
         (720, 80): FADED_GRAY, (620, 70): YELLOW, (600, 110): BLUE}

X0 = {"Global": 40, "Sibling": 400}


def mixed() -> list[dict]:
    return [item("ScreenGui", "Mixed", {"ScreenInsets": token(0), "ZIndexBehavior": token(0)}, [
        frame("White", -10, (0, 0), (2000, 2000), WHITE),
        frame("CG", 3, (300, 20), (200, 150), GRAY, [
            frame("CG_high", 6, (100, 20), (90, 110), YELLOW),
            frame("CG_low", 1, (10, 10), (60, 60), BLUE),
        ], "CanvasGroup", GroupTransparency=0.5),
        frame("J", 4, (420, 60), (40, 40), RED),
        frame("K", 2, (330, 0), (40, 120), GREEN),
        frame("PF", 5, (560, 20), (150, 150), BLUE, [
            frame("CGc", 1, (20, 20), (150, 80), GRAY, [frame("CGc_high", 9, (10, 10), (60, 40), YELLOW)],
                  "CanvasGroup", GroupTransparency=0.5),
        ]),
    ])]


def faded(x0: int) -> list[dict]:
    return [
        frame("CG", 3, (x0, 20), (200, 100), GRAY, [
            frame("Above", 5, (10, 20), (80, 60), RED),
            frame("Below", 1, (110, 20), (80, 60), BLUE),
        ], "CanvasGroup", GroupTransparency=0.5, BackgroundTransparency=1.0),
        frame("CG2", 3, (x0, 150), (200, 100), GRAY, [frame("Above2", 5, (10, 20), (80, 60), RED)],
              "CanvasGroup", GroupTransparency=0.5),
    ]


def tinted(x0: int) -> list[dict]:
    return [frame("CG", 3, (x0, 20), (200, 100), WHITE, [frame("Child", 5, (110, 20), (80, 60), WHITE)],
                  "CanvasGroup", GroupColor3=colour3(0, 0, 1))]


def clipped(x0: int) -> list[dict]:
    return [
        frame("Clip", 3, (x0, 20), (200, 100), GRAY, [
            frame("Out", 5, (120, 40), (120, 80), RED),
            frame("Left", 1, (-40, 30), (60, 40), BLUE),
        ], "CanvasGroup"),
        frame("Corner", 3, (x0, 150), (120, 100), GRAY, [
            item("UICorner", "Round", {"CornerRadius": udim(0, 40)}),
            frame("Fill", 5, (0, 0), (120, 100), GREEN),
        ], "CanvasGroup"),
        frame("Stroke", 3, (x0 + 170, 150), (100, 100), GRAY, [
            item("UIStroke", "Line", {"Thickness": 10.0, "Color": colour3(0, 0, 0)}),
        ], "CanvasGroup", GroupTransparency=0.5),
    ]


# Studio's captures with a Global gui at x0 = 40 and a Sibling gui at x0 = 400 over a
# backdrop gui: each point (an offset from x0) with the colour drawn under Global and
# under Sibling, and the clipping scene's hit orders. Studio's hit at (x0+4,154), on the
# rounded-off corner, leaves out the CanvasGroup itself; rhr's hit regions are rects.
# None marks a colour rhr doesn't draw yet: under Sibling its CanvasGroup layer clips
# and fades the group's own Outer UIStroke, which Studio draws whole and opaque.
SCENES = {
    "fade": (WHITE, faded, {
        (50, 70): (RED, (242, 142, 142)), (150, 70): (BLUE, (147, 162, 243)),
        (150, 200): (FADED_GRAY, FADED_GRAY), (50, 200): (RED, (242, 142, 142)),
    }, {}),
    "tint": ((40, 40, 40), tinted, {(50, 70): ((0, 0, 254), (0, 0, 254)), (150, 70): (WHITE, (0, 0, 254))}, {}),
    "clip": (WHITE, clipped, {
        (220, 90): (RED, WHITE), (150, 70): (RED, RED), (-10, 70): (BLUE, WHITE), (10, 70): (GRAY, BLUE),
        (4, 154): (GREEN, WHITE), (60, 200): (GREEN, GREEN), (165, 200): (BLACK, None),
        (220, 200): (FADED_GRAY, FADED_GRAY),
    }, {
        (220, 90): ("", ""), (150, 70): ("Out Clip", "Out Clip"), (-10, 70): ("", ""),
        (10, 70): ("Clip Left", "Left Clip"), (60, 200): ("Fill Corner", "Fill Corner"),
    }),
}


def scene(build, backdrop) -> list[dict]:
    back = item("ScreenGui", "Backdrop", {"ScreenInsets": token(0), "DisplayOrder": 998},
                [frame("Fill", 1, (0, 0), (2000, 2000), backdrop, Active=False)])
    return [back] + [item("ScreenGui", behavior, {"ScreenInsets": token(0), "ZIndexBehavior": token(value),
                                                 "DisplayOrder": 999 + value}, build(X0[behavior]))
                     for behavior, value in ZINDEX_BEHAVIOR.items()]


def names(specs) -> list[str]:
    return [name for spec in specs if "cls" in spec for name in (spec["name"], *names(spec["children"]))]


def copy(spec: dict, colours: dict, hidden: set, tag: str, shift=(0, 0)) -> dict:
    if "cls" not in spec:
        return spec
    props = dict(spec["props"])
    if spec["name"] in hidden:
        props["BackgroundTransparency"] = 1.0
    x, y = spec["xy"]
    return frame(f"{spec['name']}_{tag}", spec["z"], (x + shift[0], y + shift[1]), spec["wh"], colours[spec["name"]],
                 [copy(child, colours, hidden, tag) for child in spec["children"]], spec["cls"], **props)


def peeled(behavior: str):
    """Every case's peeled copies, a row per case, in one ScreenGui of `behavior`: the
    model, each case's copy offsets from where the case was measured, and the screen."""
    roots, shifts = [], {}
    width, y = 0, GAP
    for case, (box, specs, points) in CASES.items():
        bx, by, bw, bh = box
        colours = dict(zip(names(specs), PALETTE))
        peel = next(iter(points.values()))[ZINDEX_BEHAVIOR[behavior]].split()
        shifts[case] = [(GAP + k * (bw + GAP) - bx, y - by) for k in range(len(peel) + 1)]
        for k, shift in enumerate(shifts[case]):
            roots += [copy(spec, colours, set(peel[:k]), f"{case}{k}", shift) for spec in specs]
        width = max(width, GAP + len(shifts[case]) * (bw + GAP))
        y += bh + GAP
    gui = item("ScreenGui", f"Order{behavior}", {"ScreenInsets": token(0),
                                                "ZIndexBehavior": token(ZINDEX_BEHAVIOR[behavior])}, roots)
    return [gui], shifts, (width, y)


def render(name: str, roots: list[dict], size):
    """A model drawn on a white screen: its IR, the drawn rects and the RGB pixels."""
    ir = emit_ir(write_model(OUT / f"{name}.rbxmx", roots), OUT / f"{name}.json")
    rects: dict = {}
    png = render_ir(ir, OUT / f"{name}.png", *size, bg_color=(*WHITE, 255), rect_map=rects)
    return ir, rects, np.asarray(Image.open(png).convert("RGB")).astype(float)


def fmt(values) -> str:
    return "(" + ",".join(f"{value:g}" for value in values) + ")"


def summary(problems: list[str]) -> str:
    if not problems:
        return "as Studio"
    return "; ".join(problems[:4]) + (f"; +{len(problems) - 4} more" if len(problems) > 4 else "")


def versus(got: list[str], want: list[str], sep: str) -> str:
    return "as Studio" if got == want else f"{sep.join(got) or 'none'}, Studio {sep.join(want) or 'none'}"


def near(a, b, tol: float = 0.5) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def dist(a, b) -> float:
    return float(np.abs(np.asarray(a, float) - np.asarray(b, float)).max())


def pixel(img, point):
    return img[int(point[1]), int(point[0])]


def named(colour, colours: dict) -> str:
    """The case object, or the backdrop, whose colour a pixel shows."""
    name, want = min({**colours, "backdrop": WHITE}.items(), key=lambda entry: dist(colour, entry[1]))
    return name if dist(colour, want) <= TOL else fmt(colour)


def stack(hitmap: dict, x: float, y: float) -> list[str]:
    """Who is under a point in the hit map, topmost first, by name without the copy tag."""
    return [path.rsplit("/", 1)[-1].rsplit("_", 1)[0] for path in at_point(hitmap, x, y)["hitTests"][0]["stack"]]


def check_orders(check) -> None:
    for behavior, index in ZINDEX_BEHAVIOR.items():
        roots, shifts, size = peeled(behavior)
        ir, _, img = render(f"order_{behavior.lower()}", roots, size)
        hits = build_hitmap(ir, *size)
        for case, (_, specs, points) in CASES.items():
            colours = dict(zip(names(specs), PALETTE))
            peel = next(iter(points.values()))[index].split()
            for (x, y), orders in points.items():
                order = orders[index].split()
                want = [next((name for name in order if name not in peel[:k]), "backdrop")
                        for k in range(len(shifts[case]))]
                drawn = [named(pixel(img, (x + dx, y + dy)), colours) for dx, dy in shifts[case]]
                check(drawn == want, f"{behavior} {case} copies at ({x},{y}) show {versus(drawn, want, ' ')}")
                dx, dy = shifts[case][0]
                hit = stack(hits, x + dx, y + dy)
                check(hit == order, f"{behavior} {case} hits at ({x},{y}): {versus(hit, order, ' > ')}")


def check_groups(check) -> None:
    _, _, img = render("group_mixed", mixed(), (800, 300))
    problems = [f"{point} {fmt(got)}, Studio {fmt(want)}" for point, want in MIXED.items()
                if dist(got := pixel(img, point), want) > TOL]
    check(not problems, f"Global CanvasGroups among other objects: {summary(problems)}")
    for name, (backdrop, build, draws, hit_orders) in SCENES.items():
        ir, _, img = render(f"group_{name}", scene(build, backdrop), (800, 300))
        hits = build_hitmap(ir, 800, 300) if hit_orders else None
        for behavior, index in ZINDEX_BEHAVIOR.items():
            x0 = X0[behavior]
            problems = [f"(x0{dx:+},{y}) {fmt(got)}, Studio {fmt(want[index])}" for (dx, y), want in draws.items()
                        if want[index] is not None and dist(got := pixel(img, (x0 + dx, y)), want[index]) > TOL]
            check(not problems, f"{behavior} CanvasGroup {name}: {summary(problems)}")
            for (dx, y), orders in hit_orders.items():
                order = orders[index].split()
                hit = stack(hits, x0 + dx, y)
                check(hit == order, f"{behavior} CanvasGroup {name} hits at (x0{dx:+},{y}): {versus(hit, order, ' > ')}")


def laid_out(behavior: str) -> tuple[list[dict], dict]:
    """A flexed list and a grid filled from its top right, and their items' colours."""
    items = {"a": (RED, 2), "b": (GREEN, 1), "c": (BLUE, 3)}
    cells = {f"g{i}": (colour, i) for i, colour in enumerate(PALETTE[:5], 1)}
    holder = PALETTE[9]
    gui = item("ScreenGui", f"Layout{behavior}", {"ScreenInsets": token(0),
                                                 "ZIndexBehavior": token(ZINDEX_BEHAVIOR[behavior])}, [
        frame("Flex", 1, (20, 20), (400, 80), holder, [
            item("UIListLayout", "Layout", {"FillDirection": token(0), "HorizontalFlex": token(1),
                                            "Padding": udim(0, 10), "SortOrder": LAYOUT_ORDER}),
            *(frame(name, 1, (0, 0), (60, 60), colour, LayoutOrder=order) for name, (colour, order) in items.items()),
        ]),
        frame("Grid", 1, (20, 120), (300, 200), holder, [
            item("UIGridLayout", "Layout", {"CellSize": offset(60, 40), "CellPadding": offset(10, 10),
                                            "FillDirectionMaxCells": 2, "StartCorner": token(1),
                                            "SortOrder": LAYOUT_ORDER}),
            *(frame(name, 1, (0, 0), (10, 10), colour, LayoutOrder=order) for name, (colour, order) in cells.items()),
        ]),
    ])
    return [gui], {name: colour for name, (colour, _) in {**items, **cells}.items()}


def check_layout(check) -> None:
    for behavior in ZINDEX_BEHAVIOR:
        roots, colours = laid_out(behavior)
        ir, rects, img = render(f"layout_{behavior.lower()}", roots, (480, 360))
        gui = f"Layout{behavior}"
        boxes = lay_out_pane(resolve_path(load_ir(ir)["roots"], gui), (0, 0, 480, 360))
        problems = []
        for path, box in boxes.items():
            want = (box.x, box.y, box.w, box.h)
            got = rects.get(path)
            label = path.removeprefix(f"{gui}/")
            if got is None:
                problems.append(f"{label} not drawn")
            elif not near((got.x, got.y, got.w, got.h), want):
                problems.append(f"{label} drawn at {fmt((got.x, got.y, got.w, got.h))}, laid out at {fmt(want)}")
            colour = colours.get(label.rsplit("/", 1)[-1])
            if colour and dist(shown := pixel(img, (box.x + box.w / 2, box.y + box.h / 2)), colour) > TOL:
                problems.append(f"{label}'s middle shows {fmt(shown)}")
        check(not problems, f"{behavior} flexed list and grid draw at the layout's rects: {summary(problems)}")


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    check_orders(check)
    check_groups(check)
    check_layout(check)
    print(f"\n{len(failures)} ZIndexBehavior checks failed" if failures else "\nZIndexBehavior: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
