#!/usr/bin/env python3
"""A story that builds no UI that draws exits 2 and says what its target holds.

UI is a GuiObject shown on the story's screen (rhr.story.BuiltNothing). A story that
parents only a UIListLayout and a Folder, one whose only Frame is Visible = false, and
one whose only visible Frame sits in a hidden one each exit 2 on `layout`, and the
message names what the target holds; a visible Frame beside a UIListLayout draws. A
story that mounts from task.delay(2, ...) captured at --story-time 1 says a timer was
still waiting and names --story-time, at once and when reused from the story cache, and
draws at --story-time 2.1.

    python tests/test_story_empty.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]

FRAME = 'local frame = Instance.new("Frame")\n\tframe.Size = UDim2.fromOffset(100, 100)\n'
STORIES = {
    "Layout": ('return function(target)\n\tInstance.new("UIListLayout").Parent = target\n'
               '\tInstance.new("Folder").Parent = target\n\treturn function() end\nend\n'),
    "Hidden": (f'return function(target)\n\t{FRAME}\tframe.Name = "Panel"\n\tframe.Visible = false\n'
               '\tframe.Parent = target\n\treturn function() end\nend\n'),
    "Inside": (f'return function(target)\n\t{FRAME}\tframe.Name = "Panel"\n\tframe.Visible = false\n'
               '\tframe.Parent = target\n\tlocal inner = Instance.new("Frame")\n\tinner.Parent = frame\n'
               '\treturn function() end\nend\n'),
    "Shown": (f'return function(target)\n\tInstance.new("UIListLayout").Parent = target\n\t{FRAME}'
              '\tframe.Parent = target\n\treturn function() end\nend\n'),
    "Delayed": (f'return function(target)\n\ttask.delay(2, function()\n\t\t{FRAME}\t\tframe.Parent = target\n'
                '\tend)\n\treturn function() end\nend\n'),
}

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def layout(story: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([*RHR, "layout", str(story), "--viewport", "800x600", *extra], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)


def main() -> int:
    from rhr.story import BuiltNothing, _draws_something

    print("story: what BuiltNothing carries for the hint rhr.cli adds")
    got = None
    try:
        _draws_something({"shown": 0, "classes": ["Folder"], "hidden": [], "time": 1.0,
                          "timers": [{"due": 2.0, "at": None}, {"due": 3.0, "at": None}]})
    except BuiltNothing as exc:
        got = (exc.holds, exc.timers, exc.time, exc.due)
    check(got == (["Folder"], 2, 1.0, 2.0), f"holds, timers, time, due: {got}")
    try:
        _draws_something({"shown": 1, "classes": ["Frame"], "hidden": [], "time": 0.5, "timers": []})
        check(True, "a shown GuiObject raises nothing")
    except BuiltNothing as exc:
        check(False, f"a shown GuiObject raises nothing: {exc}")

    with tempfile.TemporaryDirectory(prefix="rhr-story-empty-") as directory:
        project = Path(directory)
        (project / "src").mkdir()
        for name, source in STORIES.items():
            (project / "src" / f"{name}.story.luau").write_text(source, encoding="utf-8")
        (project / "default.project.json").write_text(json.dumps({"name": "empty_stories", "tree": {
            "$className": "DataModel", "ReplicatedStorage": {"UI": {"$path": "src"}}}}), encoding="utf-8")

        def story(name: str) -> Path:
            return project / "src" / f"{name}.story.luau"

        print("story: a target that holds only a layout and a Folder draws nothing")
        proc = layout(story("Layout"))
        check(proc.returncode == 2 and "no UI to draw" in proc.stderr
              and "only Folder, UIListLayout" in proc.stderr,
              f"exit 2, naming what it holds (exit {proc.returncode}): {proc.stderr.strip()[-300:]}")

        print("story: a target whose UI is all hidden draws nothing")
        for name in ("Hidden", "Inside"):
            proc = layout(story(name))
            check(proc.returncode == 2 and "hidden" in proc.stderr and "Target/Panel" in proc.stderr,
                  f"{name}: exit 2, naming the hidden element (exit {proc.returncode}): "
                  f"{proc.stderr.strip()[-300:]}")

        print("story: a visible Frame beside a layout draws")
        proc = layout(story("Shown"))
        check(proc.returncode == 0 and "Shown/Target/Frame" in json.loads(proc.stdout or "{}").get("rects", {}),
              f"exit 0 with the Frame (exit {proc.returncode}): {proc.stderr.strip()[-300:]}")

        print("story: captured at --story-time before its timer mounts the UI")
        for run in ("ran", "reused"):
            proc = layout(story("Delayed"), "--story-time", "1")
            check(proc.returncode == 2 and "1 timer(s) still waiting" in proc.stderr
                  and "--story-time" in proc.stderr and ("unchanged since its last run" in proc.stderr) == (
                      run == "reused"),
                  f"{run}: exit 2, the timer and --story-time named (exit {proc.returncode}): "
                  f"{proc.stderr.strip()[-400:]}")
        proc = layout(story("Delayed"), "--story-time", "2.1")
        check(proc.returncode == 0 and "Delayed/Target/Frame" in json.loads(proc.stdout or "{}").get("rects", {}),
              f"--story-time 2.1 draws it (exit {proc.returncode}): {proc.stderr.strip()[-300:]}")

    print(f"story empty: {len(failures)} failed" if failures else "story empty: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
