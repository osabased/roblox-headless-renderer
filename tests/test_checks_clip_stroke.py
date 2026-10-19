#!/usr/bin/env python3
"""Two checks that must see what a player sees, run on hand-made layout dumps.

`under-notch` and `under-touch-controls` measure the part of a button that clipping
ancestors leave visible (a ScrollingFrame or ClipsDescendants frame hides the rest, and
the button is scrolled into the frame to be used), while `small-target` keeps the whole
rect. `invisible-content` counts a UIStroke that draws: thickness above 0, transparency
below 1, and for a text object only in Border mode (a Contextual stroke outlines the
text, so it paints only where the text does).

Run: python tests/test_checks_clip_stroke.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from rhr import devices  # noqa: E402
from rhr.checks import run_checks  # noqa: E402

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def node(path: str, cls: str, x: float, y: float, w: float, h: float, **extra) -> dict:
    return {"path": path, "class": cls, "visible": True, "zIndex": 1, "rect": {"x": x, "y": y, "w": w, "h": h}, **extra}


def findings(nodes: list[dict], viewport=(852, 393), device: str | None = None) -> list[dict]:
    previous = devices.CURRENT
    devices.CURRENT = devices.DEVICES[device] if device else None
    try:
        return run_checks({"viewport": list(viewport), "nodes": nodes})
    finally:
        devices.CURRENT = previous


def hits(found: list[dict], name: str) -> set[str]:
    return {p for f in found if f["check"] == name for p in f["paths"]}


def device_cases() -> None:
    print("device checks measure the visible part of a button")
    # Phone: home bar from y 372, notches x < 59 and x >= 793, jump button (697,280 70x70).
    def shelf(frame_h: float, cls="ScrollingFrame", **frame) -> list[dict]:
        return [node("G/Shelf", cls, 300, 100, 300, frame_h, **frame),
                node("G/Shelf/Button", "TextButton", 400, 350, 56, 44)]

    found = findings(shelf(260), device="phone")
    check("G/Shelf/Button" not in hits(found, "under-notch"),
          "a button whose visible part ends above the home bar is not under-notch")
    found = findings(shelf(280), device="phone")
    check("G/Shelf/Button" in hits(found, "under-notch"),
          "a ScrollingFrame that reaches the home bar still reports its button")
    found = findings(shelf(260, "Frame", clipsDescendants=True), device="phone")
    check("G/Shelf/Button" not in hits(found, "under-notch"), "ClipsDescendants clips like a ScrollingFrame")
    found = findings(shelf(260, "Frame"), device="phone")
    check("G/Shelf/Button" in hits(found, "under-notch"), "a Frame that does not clip clips nothing")

    nested = [node("G/Panel", "Frame", 200, 50, 500, 280, clipsDescendants=True),
              node("G/Panel/Shelf", "ScrollingFrame", 300, 100, 300, 280),
              node("G/Panel/Shelf/Button", "TextButton", 400, 340, 56, 44)]
    check("G/Panel/Shelf/Button" not in hits(findings(nested, device="phone"), "under-notch"),
          "every clipping ancestor counts, not only the nearest")

    side = [node("G/Side", "ScrollingFrame", 0, 100, 200, 150),
            node("G/Side/Button", "TextButton", 20, 120, 56, 44)]
    check("G/Side/Button" in hits(findings(side, device="phone"), "under-notch"),
          "a button in a ScrollingFrame that reaches into the notch is reported")

    gone = [node("G/Pane", "ScrollingFrame", 100, 100, 200, 150),
            node("G/Pane/Button", "TextButton", 10, 120, 40, 44)]
    check("G/Pane/Button" not in hits(findings(gone, device="phone"), "under-notch"),
          "a button with nothing left after clipping is skipped")

    jump = [node("G/Box", "Frame", 600, 100, 200, 170, clipsDescendants=True),
            node("G/Box/Button", "TextButton", 700, 260, 56, 80)]
    check("G/Box/Button" not in hits(findings(jump, device="phone"), "under-touch-controls"),
          "the clipped-away part of a button is not under the jump button")
    jump[0]["rect"]["h"] = 300
    check("G/Box/Button" in hits(findings(jump, device="phone"), "under-touch-controls"),
          "the visible part of a button is still checked against the jump button")

    sliver = [node("G/Box", "Frame", 600, 100, 200, 190, clipsDescendants=True),
              node("G/Box/Button", "TextButton", 700, 260, 56, 80)]
    check("G/Box/Button" not in hits(findings(sliver, device="phone"), "under-touch-controls"),
          "a sliver under a corner of the jump button is judged against the whole button")

    small = [node("G/Box", "ScrollingFrame", 300, 100, 300, 105),
             node("G/Box/Button", "TextButton", 400, 190, 56, 30)]
    check("G/Box/Button" in hits(findings(small, device="phone"), "small-target"),
          "small-target uses the whole rect of a button half scrolled out of view")


def stroke_cases() -> None:
    print("invisible-content counts the strokes that draw")
    clear = {"color": [255, 0, 0], "transparency": 1}

    def frame(name: str, *strokes: dict) -> dict:
        return node(f"G/{name}", "Frame", 10, 10, 50, 50, background=clear, strokes=list(strokes))

    def label(name: str, *strokes: dict) -> dict:
        return node(f"G/{name}", "TextLabel", 10, 10, 50, 50, background=clear, strokes=list(strokes),
                    text={"content": "Hi", "transparency": 1, "color": [0, 0, 0]})

    ring = {"color": [0, 0, 0], "thickness": 2, "transparency": 0}
    nodes = [
        frame("Plain"),
        frame("Ring", ring),
        frame("Faint", {**ring, "transparency": 0.9}),
        frame("Gone", {**ring, "transparency": 1}),
        frame("Flat", {**ring, "thickness": 0}),
        frame("Border", {**ring, "applyMode": "Border"}),
        label("TextOutline", ring),
        label("TextBorder", {**ring, "applyMode": "Border"}),
    ]
    invisible = hits(findings(nodes), "invisible-content")
    check("G/Plain" in invisible, "a frame with no stroke and no fill is reported")
    check("G/Ring" not in invisible, "a transparent frame with a visible stroke is not reported")
    check("G/Faint" not in invisible, "a stroke at 90% transparency still draws")
    check("G/Gone" in invisible, "a stroke at 100% transparency draws nothing")
    check("G/Flat" in invisible, "a stroke of thickness 0 draws nothing")
    check("G/Border" not in invisible, "a Border stroke on a frame draws")
    check("G/TextOutline" in invisible, "a Contextual stroke on invisible text outlines nothing")
    check("G/TextBorder" not in invisible, "a Border stroke on a text object draws its box")


def main() -> int:
    device_cases()
    stroke_cases()
    print("checks clip/stroke: ok" if not failures else f"checks clip/stroke: {len(failures)} failed")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
