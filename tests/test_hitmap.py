#!/usr/bin/env python3
"""Hit-region dump: interactive metadata, hidden capture, and stacking.

Task 2.3 is tested through the real IR -> adapter -> hit-test
path. The fixture has two equal overlapping buttons, with the invisible Active
button on top, plus a TextBox to pin its input flags. The rendered PNG proves
the hidden button is not painted while the hitmap still names it as the target.
When stdout is cut, the stderr count line gives every node and probe, and a note
names each list cut, probe points too.

Run: python tests/test_hitmap.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests"))
FIXTURE = REPO / "tests" / "fixtures" / "hitmap_overlap.rbxmx"
RHR = [sys.executable, "-m", "rhr"]
OUT = REPO / "out" / "hitmap"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def main() -> int:
    from rhr.hitmap import build_hitmap, dump_json, narrowed
    from test_fixtures import emit_ir

    OUT.mkdir(parents=True, exist_ok=True)
    ir = emit_ir(FIXTURE)
    hitmap = build_hitmap(ir, 400, 300)
    by_path = {entry["path"]: entry for entry in hitmap["nodes"]}

    expected_paths = {
        "HitMap/Root/VisibleBottom",
        "HitMap/Root/InvisibleTop",
        "HitMap/Root/Input",
    }
    check(set(by_path) == expected_paths, f"all interactive nodes are listed ({sorted(by_path)})")

    hidden = by_path["HitMap/Root/InvisibleTop"]
    check(hidden["visible"] is False, "the top button is reported invisible")
    # Studio (2026-09-28): a hidden element never takes a click, Active or not.
    check(hidden["active"] is True and hidden["capturesClicks"] is False,
          "an invisible Active button captures no clicks")
    check(hidden["activatedTargetCandidate"] is False and by_path["HitMap/Root/VisibleBottom"]["activatedTargetCandidate"],
          "only the visible button can fire Activated")

    bottom = by_path["HitMap/Root/VisibleBottom"]
    bottom_rect = bottom.get("rect")
    hidden_rect = hidden.get("rect")
    check(
        bottom["visible"] is True and bottom_rect is not None and bottom_rect == hidden_rect,
        f"the overlapping buttons have the same resolved rect ({bottom_rect})",
    )

    textbox = by_path["HitMap/Root/Input"]
    check(textbox["textEditable"] is True and textbox["clearTextOnFocus"] is False,
          "TextBox editing flags are reported")

    overlap = next(
        probe for probe in hitmap["hitTests"]
        if probe["point"] == {"x": 100.0, "y": 60.0}
    )
    check(
        overlap["stack"][:2] == [
            "HitMap/Root/InvisibleTop",
            "HitMap/Root/VisibleBottom",
        ],
        f"the overlap stack is topmost first ({overlap['stack']})",
    )
    check(
        overlap["target"] == "HitMap/Root/VisibleBottom"
        and overlap["targetVisible"] is True and overlap["targetIsButton"] is True,
        f"the click goes to the visible button under the hidden one ({overlap})",
    )

    # The renderer still paints only the visible lower button. This guards
    # against implementing the input overlay by mutating render visibility.
    from rhr.pipeline import render_ir
    from PIL import Image

    png = OUT / "hitmap_overlap.png"
    render_ir(ir, png, 400, 300, bg_color=(0, 0, 0, 0))
    with Image.open(png) as image:
        pixel = image.convert("RGBA").getpixel((25, 25))
    check(pixel[:3] == (255, 0, 0) and pixel[3] > 0,
          f"the hidden top button is not painted over the visible red button ({pixel})")

    # CLI contract: JSON is stable and diagnostics stay on stderr.
    cli_out = OUT / "hitmap_cli.json"
    proc = subprocess.run(
        [*RHR, "hitmap", str(FIXTURE), "--all", "--viewport", "400x300", "--out", str(cli_out)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=300,
    )
    check(proc.returncode == 0, f"rhr hitmap exits 0 ({proc.stderr.strip()[-120:]})")
    cli_data = json.loads(cli_out.read_text()) if cli_out.exists() else {}
    check(cli_data == json.loads(dump_json(narrowed(hitmap, everything=True, whole=True))),
          "CLI output matches the library dump")
    check("hitmap 3 interactive nodes, 2 probe points" in proc.stderr,
          "CLI reports node and probe counts on stderr")

    # The canonical serialisation must not change between two builds.
    check(dump_json(hitmap) == dump_json(build_hitmap(ir, 400, 300)),
          "two hitmap builds are byte-identical")

    # Renderer/hitmap parity on a centered grid: the grid block is centered as a
    # whole and the short second row starts at the block's left edge, as in Studio.
    # Duplicate names are intentional, so compare the geometric multiset.
    grid_ir = emit_ir(REPO / "tests" / "fixtures" / "centered_grid_buttons.rbxmx")
    from rhr.hitmap import _paint_entries
    from rhr.ir import load_ir
    from rhr.pipeline import load_screens
    screens = load_screens(grid_ir, 400, 300)
    entries = _paint_entries(load_ir(grid_ir)["roots"][0], screens[0][1])
    grid_x = sorted(
        round(float(getattr(rect, "x")), 3)
        for node, rect in entries
        # Same-named cells are indexed (`Rare[1]`, `Rare[2]`); match any index.
        if re.fullmatch(r"Shop/Parts/(Mythic|Legendary|Epic|Common|Rare)(\[\d+\])?",
                        node.get("_path") or "")
        if node.get("type") == "TextButton"
    )
    check(
        grid_x == [85.0, 85.0, 145.0, 145.0, 205.0, 265.0],
        f"centered grid traversal matches the layout pass ({grid_x})",
    )

    # Who gets a click, case by case as Studio did on 2026-09-28 (rhr.hitmap).
    proc = subprocess.run([*RHR, "hitmap", str(REPO / "tests" / "fixtures" / "hitmap_studio.rbxmx"),
                           "--viewport", "1000x300"], capture_output=True, text=True, cwd=str(REPO), timeout=300)
    targets = {}
    for test in json.loads(proc.stdout)["hitTests"] if proc.returncode == 0 else []:
        targets[int(test["point"]["x"])] = test["target"]
    expected = {
        50: "Main/Alone",
        150: "Main/UnderActiveFrame",       # an Active Frame over it in the same ScreenGui: no effect
        250: None,                          # Interactable = false: dead
        350: None,                          # a parent with Interactable = false: dead
        450: "Main/UnderDeadButton",        # a non-Interactable button on top: clicks pass through
        550: "Above/Cover[1]",              # a transparent Active Frame in a ScreenGui above swallows it
        650: "Main/UnderOtherGuiPassive",   # ... but not when it is not Active
        750: "Main/UnderOtherGuiHidden",    # ... or hidden
        850: "Main/OverLowerGui",           # an Active Frame in a lower ScreenGui: no effect
    }
    for x, target in expected.items():
        check(targets.get(x, "missing") == target, f"Studio case at x={x}: {target} gets the click ({targets.get(x)})")

    cut_notes()
    print("hitmap: ok" if not failures else f"hitmap: {len(failures)} failed")
    return 1 if failures else 0


def nested_buttons(columns: int) -> dict:
    """A hit map of `columns` columns of 4 buttons nested in each other under a long
    path, so a probe's stack holds 4 long paths: probes outgrow their share of stdout
    before the nodes do."""
    from rhr.hitmap import _centre

    base = "Gui/" + "/".join(f"Frame{i:02d}" for i in range(25))
    nodes = []
    for column in range(columns):
        path = f"{base}/Col{column}"
        for depth in range(4):
            path, side = f"{path}/Btn{depth}", 200 - depth * 40
            nodes.append({"path": path, "class": "TextButton", "rect": {"x": column * 200, "y": 0, "w": side, "h": side},
                          "visible": True, "active": True, "selectable": True, "interactable": True,
                          "capturesClicks": True, "activatedTargetCandidate": True, "zOrder": depth, "pane": 0})
    tests = []
    for x, y in sorted({_centre(n["rect"]) for n in nodes}):
        stack = sorted((n for n in nodes if n["rect"]["x"] <= x < n["rect"]["x"] + n["rect"]["w"]
                        and n["rect"]["y"] <= y < n["rect"]["y"] + n["rect"]["h"]), key=lambda n: -n["zOrder"])
        tests.append({"point": {"x": x, "y": y}, "stack": [n["path"] for n in stack], "target": stack[0]["path"],
                      "targetIsButton": True, "targetVisible": True})
    return {"nodes": nodes, "hitTests": tests, "panes": []}


def cut_notes() -> None:
    """The stderr lines after a cut: the counts are of every node and probe, and each
    list that was cut says so, probes too when every node fits."""
    import contextlib
    import io

    from rhr.cli import _hitmap_counts
    from rhr.hitmap import narrowed

    for columns in (3, 40):
        whole = nested_buttons(columns)
        shown = narrowed(whole)
        check(len(shown["hitTests"]) + shown["moreHitTests"] == len(whole["hitTests"]),
              f"{columns} columns: moreHitTests counts every probe left out "
              f"({len(shown['hitTests'])} + {shown['moreHitTests']} of {len(whole['hitTests'])})")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            _hitmap_counts(shown, 0)
        lines = err.getvalue().splitlines()
        check(bool(lines) and lines[0].startswith(
                  f"hitmap {len(whole['nodes'])} interactive nodes, {len(whole['hitTests'])} probe points"),
              f"{columns} columns: the count line gives the totals ({lines[:1]})")
        if shown["moreNodes"]:
            check(any(f"of {len(whole['nodes'])} interactive nodes on stdout, cut to fit" in line for line in lines),
                  f"{columns} columns: a line says nodes were cut ({lines})")
        check(shown["moreHitTests"] > 0 and any(
                  f"{len(shown['hitTests'])} of {len(whole['hitTests'])} probe points on stdout, cut to fit" in line
                  for line in lines),
              f"{columns} columns: a line says probe points were cut "
              f"(moreNodes {shown['moreNodes']}, moreHitTests {shown['moreHitTests']}: {lines})")
    check(narrowed(nested_buttons(3))["moreNodes"] == 0, "3 columns: every node fits, and only probes are cut")


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
