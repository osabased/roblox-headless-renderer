#!/usr/bin/env python3
"""What a story reads of the values Roblox works out as it lays GUI out.

RHR lays the UI out after the story ran, so while it runs these read as Studio reads
them on a new element, where Lune would raise for want of a default: zero sizes,
positions and rotation, GuiState Idle, an empty OpenTypeFeaturesError, a TextBox's
CursorPosition 1 and SelectionStart -1, a VideoFrame not loaded. TextFits and an
image's IsLoaded read true instead, so code that waits for them, or shrinks text until
it fits, goes on; a grid's AbsoluteCellSize reads zero, where Studio reads the CellSize
it starts with, which a story usually changes. The story's target and ScreenGui have
the area's size, and AbsolutePosition 0,0: Roblox measures it from the area's corner.
`tests/fixtures/rojo_stories/src/ComputedReads.story.luau` reads each into a label, for
elements the story makes, a TextLabel from the project's files and a clone of it.

    python tests/test_computed_reads.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "tests" / "fixtures" / "rojo_stories" / "src" / "ComputedReads.story.luau"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


ZERO = "0,0"
TEXT = {"TextBounds": ZERO, "TextFits": "true", "OpenTypeFeaturesError": '""'}
EXPECTED = {
    "Frame": {"AbsoluteSize": ZERO, "AbsolutePosition": ZERO, "AbsoluteRotation": "0", "GuiState": "Idle"},
    "TextLabel": TEXT,
    "TextButton": {**TEXT, "GuiState": "Idle"},
    "TextBox": {**TEXT, "CursorPosition": "1", "SelectionStart": "-1"},
    "ImageLabel": {"IsLoaded": "true"},
    "ImageButton": {"IsLoaded": "true", "GuiState": "Idle"},
    "VideoFrame": {"IsLoaded": "false", "Resolution": ZERO, "TimeLength": "0"},
    "ScrollingFrame": {"AbsoluteCanvasSize": ZERO, "AbsoluteWindowSize": ZERO, "AbsoluteSize": ZERO},
    "CanvasGroup": {"AbsoluteSize": ZERO, "GuiState": "Idle"},
    "ViewportFrame": {"AbsolutePosition": ZERO},
    "ScreenGui": {"AbsoluteSize": ZERO, "AbsolutePosition": ZERO, "AbsoluteRotation": "0"},
    "BillboardGui": {"CurrentDistance": "0", "DistanceStep": "0", "AbsoluteSize": ZERO},
    "SurfaceGui": {"AbsoluteSize": ZERO},
    "UIListLayout": {"AbsoluteContentSize": ZERO},
    "UIGridLayout": {"AbsoluteContentSize": ZERO, "AbsoluteCellCount": ZERO, "AbsoluteCellSize": ZERO},
    "UIPageLayout": {"AbsoluteContentSize": ZERO},
    "UITableLayout": {"AbsoluteContentSize": ZERO},
    "Target": {"AbsoluteSize": "800,542", "AbsolutePosition": ZERO, "AbsoluteRotation": "0", "GuiState": "Idle"},
    "Screen": {"AbsoluteSize": "800,542", "AbsolutePosition": ZERO},
    "Template": {"AbsoluteSize": ZERO, "GuiState": "Idle", "TextBounds": ZERO, "TextFits": "true"},
    "Clone": {"TextBounds": ZERO, "TextFits": "true"},
}


def main() -> int:
    print("computed reads: on an 800x600 screen, whose area is 800x542 below the top bar")
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORY), "--rich", "--viewport", "800x600"],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    check(proc.returncode == 0, f"layout exits 0 {proc.stderr[-400:] if proc.returncode else ''}")
    if proc.returncode == 0:
        prefix = "ComputedReads/Target/"
        got = {node["path"][len(prefix):]: node.get("text", {}).get("content")
               for node in json.loads(proc.stdout)["nodes"] if node["path"].startswith(prefix)}
        expected = {f"{subject}.{name}": value for subject, reads in EXPECTED.items() for name, value in reads.items()}
        for read, value in expected.items():
            check(got.get(read) == value, f"{read} = {got.get(read)!r}, expected {value!r}")
        unexpected = sorted(set(got) - set(expected))
        check(not unexpected, f"the story reads nothing else: {unexpected}")

    print(f"computed reads: {len(failures)} failed" if failures else "computed reads: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
