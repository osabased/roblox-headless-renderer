#!/usr/bin/env python3
"""UI that code builds: a story file is run in its Rojo project and drawn.

`tests/fixtures/rojo_stories/` is a place project with a tiny UI helper standing in
for a UI library (Packages/Mini.luau), a package linked by string require the way
pesde links them (Packages/Tag.luau), and one story per form: a function(target)
that reads sizes and tweens (Badge), a UI Labs table with controls (Panel), one that
sizes itself from the screen (Viewport), one that uses the package (Tagged), one
that calls Roblox's profiler every frame (Profiled), one that sets a legacy Font and
a FontFace (Fonts), one with a child under its parent's ZIndex (Stacked), one that
fails (Broken), one whose require leads nowhere (Missing) and one that reaches for
Lune's own globals (Escape).
`tests/fixtures/rojo_wrapped/` is a place whose default.project.json only wraps
common.project.json.

    python tests/test_story.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]
STORIES = ROOT / "tests" / "fixtures" / "rojo_stories" / "src"
WRAPPED = ROOT / "tests" / "fixtures" / "rojo_wrapped" / "src"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([*RHR, *args], cwd=ROOT, capture_output=True, text=True, timeout=300)


def layout(story: str, *extra: str) -> dict | None:
    proc = run(["layout", str(STORIES / story), "--viewport", "800x600", *extra])
    check(proc.returncode == 0, f"layout {story} exits 0 {proc.stderr[-400:] if proc.returncode else ''}")
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def main() -> int:
    print("story: the function form (mounts into target, returns a cleanup)")
    doc = layout("Badge.story.luau")
    if doc:
        rects = doc["rects"]
        check(rects.get("Badge/Target/Badge") == {"x": 300.0, "y": 98.0, "w": 200.0, "h": 80.0},
              f"a module's component, drawn where its tween ends: {rects.get('Badge/Target/Badge')}")
        check("Badge/Target/Claim" in rects, "an instance the story made itself")
        check(doc["viewport"] == [800, 600], "drawn at --viewport")

    print("story: the UI Labs table form, controls at their defaults")
    doc = layout("Panel.story.luau", "--rich")
    if doc:
        nodes = {node["path"]: node for node in doc["nodes"]}
        panel = nodes.get("Panel/Target/Panel", {}).get("rect")
        check(panel is not None and panel["h"] == 180.0, f"a slider control's value (3 rows): {panel}")
        check(all(f"Panel/Target/Panel/Row{row}" in nodes for row in (1, 2, 3)), "one button per row")
        title = nodes.get("Panel/Target/Panel/Title", {}).get("text", {}).get("content")
        check(title == "Settings", f"a plain control's default: {title!r}")
        check(doc["model"] == "Panel.story.json", f"documents name the story: {doc['model']!r}")

    print("story: it mounts where a game's own UI does, below the top bar and inside the device's insets")
    for screen, flags, area, camera, inset in (
            ("800x600", ["--viewport", "800x600"], (0, 58, 800, 542), "800x600", "0,58"),
            ("a 36 px top bar", ["--viewport", "800x600", "--topbar-height", "36"], (0, 36, 800, 564), "800x600",
             "0,36"),
            ("the phone", ["--device", "phone"], (59, 58, 734, 314), "852x393", "0,58")):
        proc = run(["layout", str(STORIES / "Viewport.story.luau"), "--rich", *flags])
        check(proc.returncode == 0, f"layout on {screen} exits 0 {proc.stderr[-400:] if proc.returncode else ''}")
        if proc.returncode:
            continue
        nodes = {node["path"]: node for node in json.loads(proc.stdout)["nodes"]}

        def rect(path: str) -> tuple | None:
            box = nodes.get(f"Viewport/{path}", {}).get("rect")
            return box and (box["x"], box["y"], box["w"], box["h"])

        def text(path: str) -> str | None:
            return nodes.get(f"Viewport/{path}", {}).get("text", {}).get("content")

        x, y, w, h = area
        check(rect("Target") == area, f"{screen}: the target fills that area: {rect('Target')}")
        check(rect("Target/Bar") == (x, y, w // 2, h // 2),
              f"{screen}: target.AbsoluteSize is its size: {rect('Target/Bar')}")
        check(text("Target/Inset") == inset, f"{screen}: GetGuiInset: {text('Target/Inset')!r}")
        check(text("Target/Size") == camera, f"{screen}: CurrentCamera.ViewportSize: {text('Target/Size')!r}")

    print("story: string requires, as pesde links packages")
    doc = layout("Tagged.story.luau")
    if doc:
        tag = doc["rects"].get("Tagged/Target/Tag")
        check(tag == {"x": 10.0, "y": 78.0, "w": 120.0, "h": 28.0}, f"./, ../ and @self/ lead to the package: {tag}")
    proc = run(["layout", str(STORIES / "Missing.story.luau")])
    check(proc.returncode == 2 and 'require("./NotThere")' in proc.stderr
          and re.search(r"at src[\\/]Missing\.story\.luau:2", proc.stderr) is not None,
          f"a path that leads nowhere is an error at its line: {proc.stderr.strip()[-300:]}")

    print("story: Roblox's profiler calls, made every frame")
    proc = run(["layout", str(STORIES / "Profiled.story.luau"), "--viewport", "800x600"])
    bar = json.loads(proc.stdout)["rects"].get("Profiled/Target/Bar") if proc.returncode == 0 else None
    check(bar is not None and bar["w"] == 100.0 and "attempt to call" not in proc.stderr,
          f"debug.profilebegin and the memory categories do nothing: {bar} {proc.stderr.strip()[-300:]}")

    print("story: a FontFace set after a legacy Font, the order UI libraries with defaults set them")
    from rhr.cli import ir_for
    from rhr.ir import load_ir, resolve_path

    roots = load_ir(ir_for(STORIES / "Fonts.story.luau", viewport=(800, 600)))["roots"]
    face = resolve_path(roots, "Fonts/Target/Face")["props"].get("FontFace", {})
    check((face.get("family"), face.get("weight")) == ("rbxasset://fonts/families/BuilderSans.json",
                                                       "Enum.FontWeight.Bold"),
          f"the FontFace is kept: {face}")
    legacy = resolve_path(roots, "Fonts/Target/Legacy")["props"].get("FontFace", {})
    check((legacy.get("family"), legacy.get("weight")) == ("rbxasset://fonts/families/GothamSSm.json",
                                                           "Enum.FontWeight.Bold"),
          f"a legacy Font alone is drawn as its FontFace: {legacy}")

    print("story: it mounts in a Sibling ScreenGui, as UI Labs mounts stories")
    from PIL import Image

    stacked = STORIES / "Stacked.story.luau"
    screen = resolve_path(load_ir(ir_for(stacked, viewport=(800, 600)))["roots"], "Stacked")
    behavior = screen["props"].get("ZIndexBehavior", {}).get("name")
    check(behavior == "Sibling", f"the story's ScreenGui: {behavior!r}")
    with tempfile.TemporaryDirectory(prefix="rhr-story-") as directory:
        out = Path(directory) / "stacked.png"
        proc = run(["ui", str(stacked), "--viewport", "800x600", "--out", str(out)])
        pixel = None
        if proc.returncode == 0:
            with Image.open(out) as image:
                pixel = image.convert("RGB").getpixel((200, 208))
    check(pixel == (255, 0, 0), f"a child under its parent's ZIndex is drawn above it: {pixel} "
                                f"{proc.stderr[-300:] if proc.returncode else ''}")

    print("story: check, and a picture")
    proc = run(["check", str(STORIES / "Panel.story.luau")])
    check(proc.returncode in (0, 1) and json.loads(proc.stdout or "{}").get("model") == "Panel.story.json",
          f"check names the story {proc.stderr[-300:] if proc.returncode > 1 else ''}")
    proc = run(["check", str(STORIES / "Viewport.story.luau"), "--devices", "phone,desktop"])
    runs = re.findall(r"^story  Viewport\.story\.luau: ", proc.stderr, re.M)
    check(proc.returncode in (0, 1) and len(runs) == 2,
          f"check --devices runs the story on each screen: {len(runs)} runs {'' if runs else proc.stderr[-300:]}")
    with tempfile.TemporaryDirectory(prefix="rhr-story-") as directory:
        out = Path(directory) / "badge.png"
        proc = run(["ui", str(STORIES / "Badge.story.luau"), "--viewport", "800x600", "--out", str(out)])
        check(proc.returncode == 0 and out.is_file() and out.stat().st_size > 1000,
              f"ui draws the story {proc.stderr[-300:] if proc.returncode else ''}")

    print("story: run again only when something it runs on changed")
    first = run(["layout", str(STORIES / "Badge.story.luau"), "--viewport", "800x600"])
    again = run(["layout", str(STORIES / "Badge.story.luau"), "--viewport", "800x600"])
    check(again.returncode == 0 and "unchanged since its last run" in again.stderr and again.stdout == first.stdout,
          f"unchanged: the UI it built is reused {again.stderr[-300:]}")
    other = run(["layout", str(STORIES / "Badge.story.luau"), "--viewport", "640x480"])
    check("ran it in its Rojo project" in other.stderr, "another viewport runs it again")
    helper = next(path for path in sorted(STORIES.rglob("*.luau")) if not path.name.endswith(".story.luau"))
    os.utime(helper)
    edited = run(["layout", str(STORIES / "Badge.story.luau"), "--viewport", "800x600"])
    check("ran it in its Rojo project" in edited.stderr and edited.stdout == first.stdout,
          f"a project file changed ({helper.name}): run again")

    print("story: errors point at the project's files")
    proc = run(["layout", str(STORIES / "Broken.story.luau")])
    check(proc.returncode == 2, f"a failing story exits 2 (got {proc.returncode})")
    check("NotAProperty is not a valid member of Frame" in proc.stderr, f"the error: {proc.stderr.strip()[-300:]}")
    check(re.search(r"at src[\\/]Broken\.story\.luau:5", proc.stderr) is not None, "the line, in the story's file")
    check("story-runtime" not in proc.stderr, "not RHR's own runtime frames")

    print("story: no way to Lune's own globals through getfenv")
    proc = run(["layout", str(STORIES / "Escape.story.luau")])
    check(proc.returncode == 2 and "getfenv is not available" in proc.stderr,
          f"refused: {proc.stderr.strip()[-200:]}")

    print("story: in a project whose default.project.json wraps another")
    proc = run(["layout", str(WRAPPED / "Card.story.luau"), "--viewport", "800x600"])
    card = json.loads(proc.stdout)["rects"].get("Card/Target/Card") if proc.returncode == 0 else None
    check(card == {"x": 40.0, "y": 98.0, "w": 160.0, "h": 90.0},
          f"runs in the place it wraps: {card} {proc.stderr.strip()[-300:] if proc.returncode else ''}")

    print("story: outside a Rojo project")
    with tempfile.TemporaryDirectory(prefix="rhr-story-loose-") as directory:
        loose = Path(directory) / "Loose.story.luau"
        shutil.copy(STORIES / "Viewport.story.luau", loose)
        proc = run(["layout", str(loose)])
    check(proc.returncode == 2 and "Rojo project" in proc.stderr, f"says why: {proc.stderr.strip()[-200:]}")

    print(f"story: {len(failures)} failed" if failures else "story: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
