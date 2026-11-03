#!/usr/bin/env python3
"""Every command on every kind of input either shows something or exits 2 and says why.

The inputs hold one kind of content, or none: a UI-only model, a UI whose label text
is longer than stdout's whole allowance, a 3D-only model, an empty Model, a file of
scripts, a Rojo project that maps only code, a Rojo project whose `$path` is missing,
a story that builds a label and one that builds nothing, and asset and place ids
served from a seeded model cache (an empty Model, the shop, a place of the tower and
the shop, an empty place, and an id not cached at all). Each command either exits 0
(or 1 for `check`) with a document that holds what that command is for
(`shows_something` says what, per command), or a PNG that is not one flat colour, or
exits 2 with a reason on stderr: never 0 with nothing, never a traceback or a page
error. UI commands exit 2 on input with no UI and 3D commands (scene-dump among them)
on input with no world, `inspect` on a story (Luau source, not a model), and a
`--path` that names nothing, or only hidden elements for `hitmap` and `check`, exits 2
too; `scene-dump` is judged by its full dump (`holds_world`). A label
too long for stdout is kept, shortened. The cache is the test's own, with the pinned
tools copied in, so no download happens.

    python tests/test_nothing_to_show.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

# Hermetic even when run by hand: no downloads, no Studio textures, software WebGL.
import _harness  # noqa: F401
from _models import script

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]
SHOP = ROOT / "examples" / "shop.rbxmx"
TOWER = ROOT / "examples" / "tower.rbxmx"

UI_COMMANDS = ("ui", "layout", "check", "hitmap")
WORLD_COMMANDS = ("scene", "preview", "scene-dump")
DATA_COMMANDS = ("inspect",)
PICTURES = ("ui", "scene", "preview")
# `scene-dump --parts` runs before the summary: its full dump is what the summary's
# check reads (`holds_world`).
RUNS = (("ui",), ("layout",), ("layout", "--rich"), ("check",), ("hitmap",), ("inspect",), ("scene",),
        ("preview",), ("scene-dump", "--parts"), ("scene-dump",))
# Each list cut to fit stdout, beside the count of the rows it left out (rhr.budget).
CUT_LISTS = (("rects", "moreRects"), ("nodes", "moreNodes"), ("hitTests", "moreHitTests"),
             ("findings", "moreFindings"), ("scripts", "moreScripts"), ("missingAssets", "moreMissingAssets"))

EMPTY_MODEL = ('<roblox version="4"><Item class="Model" referent="M"><Properties>'
               '<string name="Name">Empty</string></Properties></Item></roblox>')
SCRIPT_ONLY = '<roblox version="4">' + script("ModuleScript", "Module", "return 1") + "</roblox>"
LABEL_STORY = ('return function(target)\n\tlocal label = Instance.new("TextLabel")\n'
               '\tlabel.Size = UDim2.fromOffset(200, 50)\n\tlabel.Text = "Hello"\n'
               '\tlabel.Parent = target\n\treturn function() label:Destroy() end\nend\n')
EMPTY_STORY = "return function(target)\n\treturn function() end\nend\n"
# Text longer than the whole allowance a list gets on stdout (rhr.budget.ALLOWANCE), on
# the first row (paths sort Gui/Rules first): a cut that stopped at the first row too big
# left `nodes` empty.
LONG_TEXT = "lorem ipsum " * 2500
OVERSIZED_LABEL = ('<roblox version="4"><Item class="ScreenGui" referent="G"><Properties><string name="Name">Gui'
                   '</string></Properties><Item class="TextLabel" referent="L"><Properties><string name="Name">'
                   f'Rules</string><string name="Text">{LONG_TEXT}</string><UDim2 name="Size"><XS>0</XS>'
                   '<XO>400</XO><YS>0</YS><YO>300</YO></UDim2></Properties></Item>'
                   '<Item class="TextButton" referent="P"><Properties><string name="Name">Start</string>'
                   '<string name="Text">Start</string><UDim2 name="Size"><XS>0</XS><XO>100</XO><YS>0</YS><YO>40</YO>'
                   '</UDim2></Properties><Item class="Frame" referent="C"><Properties><string name="Name">Child'
                   '</string><UDim2 name="Size"><XS>0</XS><XO>20</XO><YS>0</YS><YO>20</YO></UDim2></Properties>'
                   '</Item></Item></Item></roblox>')
EMPTY_PLACE = ('<roblox version="4"><Item class="Workspace" referent="W"><Properties><string name="Name">Workspace'
               '</string></Properties></Item><Item class="StarterGui" referent="G"><Properties><string name="Name">'
               'StarterGui</string></Properties></Item></roblox>')
# A frame whose one button is hidden, beside a shown button.
HIDDEN_ONLY = ('<roblox version="4"><Item class="ScreenGui" referent="G"><Properties><string name="Name">Gui'
               '</string></Properties><Item class="Frame" referent="F"><Properties><string name="Name">Frame'
               '</string></Properties><Item class="TextButton" referent="H"><Properties><string name="Name">Hidden'
               '</string><bool name="Visible">false</bool></Properties></Item></Item><Item class="TextButton" '
               'referent="S"><Properties><string name="Name">Shown</string><UDim2 name="Size"><XS>0</XS><XO>100'
               '</XO><YS>0</YS><YO>40</YO></UDim2></Properties></Item></Item></roblox>')
EMPTY_ASSET, SHOP_ASSET, UNCACHED_ASSET = "1000000001", "1000000002", "1000000003"
PLACE_ASSET, EMPTY_PLACE_ASSET = "1000000004", "1000000005"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def tower_and_shop_place() -> str:
    """An XML place: the tower in Workspace, the shop in StarterGui (its referents
    renamed so they cannot collide with the tower's)."""
    tower = TOWER.read_text(encoding="utf-8").rstrip()
    shop = SHOP.read_text(encoding="utf-8").replace('referent="RBX', 'referent="SHOP')
    shop = shop[shop.index(">") + 1:shop.rindex("</roblox>")]
    return (tower.removesuffix("</roblox>") + '<Item class="StarterGui" referent="SG"><Properties>'
            '<string name="Name">StarterGui</string></Properties>' + shop + "</Item></roblox>")


def inputs(tmp: Path, cache: Path) -> dict[str, tuple[str, set[str]]]:
    """name -> (what to pass, what it holds): "ui", "world", "source" for Luau that
    `inspect` refuses, or "unreadable" for one every command refuses."""
    (tmp / "empty_model.rbxmx").write_text(EMPTY_MODEL, encoding="utf-8")
    (tmp / "oversized_label.rbxmx").write_text(OVERSIZED_LABEL, encoding="utf-8")
    (tmp / "script_only.rbxmx").write_text(SCRIPT_ONLY, encoding="utf-8")
    code = tmp / "code_only"
    (code / "src").mkdir(parents=True)
    (code / "src" / "init.luau").write_text("return {}\n", encoding="utf-8")
    (code / "default.project.json").write_text(json.dumps({"name": "code_only", "tree": {
        "$className": "DataModel", "ReplicatedStorage": {"Shared": {"$path": "src"}}}}), encoding="utf-8")
    missing = tmp / "missing_path"
    missing.mkdir()
    (missing / "default.project.json").write_text(json.dumps({"name": "missing_path", "tree": {"$path": "nowhere"}}),
                                                  encoding="utf-8")
    stories = tmp / "stories"
    (stories / "src").mkdir(parents=True)
    (stories / "src" / "Label.story.luau").write_text(LABEL_STORY, encoding="utf-8")
    (stories / "src" / "Empty.story.luau").write_text(EMPTY_STORY, encoding="utf-8")
    (stories / "default.project.json").write_text(json.dumps({"name": "stories", "tree": {
        "$className": "DataModel", "ReplicatedStorage": {"UI": {"$path": "src"}}}}), encoding="utf-8")
    # rhr.remote's cache: <id><suffix> with <id>.json naming the suffix (.rbxlx for an
    # XML place, as rhr.remote._suffix names one); `checked` 0 is stale, which offline
    # still uses.
    models = cache / "cache" / "models"
    models.mkdir(parents=True)
    for asset, suffix, body in ((EMPTY_ASSET, ".rbxmx", EMPTY_MODEL),
                                (SHOP_ASSET, ".rbxmx", SHOP.read_text(encoding="utf-8")),
                                (PLACE_ASSET, ".rbxlx", tower_and_shop_place()),
                                (EMPTY_PLACE_ASSET, ".rbxlx", EMPTY_PLACE)):
        (models / f"{asset}{suffix}").write_text(body, encoding="utf-8")
        (models / f"{asset}.json").write_text(json.dumps({"suffix": suffix, "checked": 0}), encoding="utf-8")
    return {
        "ui-only model": (str(SHOP), {"ui"}),
        "UI with a label too long for stdout": (str(tmp / "oversized_label.rbxmx"), {"ui"}),
        "3D-only model": (str(TOWER), {"world"}),
        "empty Model": (str(tmp / "empty_model.rbxmx"), set()),
        "scripts only": (str(tmp / "script_only.rbxmx"), set()),
        "code-only Rojo project": (str(code), set()),
        "Rojo project, $path missing": (str(missing), {"unreadable"}),
        "story that builds a label": (str(stories / "src" / "Label.story.luau"), {"ui", "source"}),
        "story that builds nothing": (str(stories / "src" / "Empty.story.luau"), {"source"}),
        "asset id, empty Model": (EMPTY_ASSET, set()),
        "asset id, the shop": (f"rbxassetid://{SHOP_ASSET}", {"ui"}),
        "place link, the tower and the shop": (f"https://www.roblox.com/games/{PLACE_ASSET}/Tower", {"ui", "world"}),
        "place id, an empty place": (EMPTY_PLACE_ASSET, set()),
        "asset id, not cached": (UNCACHED_ASSET, {"unreadable"}),
    }


def holds_world(dump: dict) -> bool:
    """Whether a full scene dump (`scene-dump --parts`) holds a 3D world, as rhr's
    scene-dump decides it (src/rhr/cli.py `_scene_dump`): a part, a Terrain whose voxels
    were read and are not the empty grid (`empty` False; None is a grid that could not
    be read), a sky, an atmosphere, a light, a beam or a trail. Lighting alone is not."""
    return bool(dump["parts"] or any(terrain.get("empty") is False for terrain in dump["terrain"])
                or dump["sky"] is not None or dump["atmosphere"] is not None
                or dump["lights"] or dump["beams"] or dump["trails"])


def shows_something(args: tuple[str, ...], stdout: str, world: dict | None = None) -> str | None:
    """Why `stdout` of a successful `rhr <args>` shows nothing, or None when it shows
    something: what that is depends on the command. *world* is the input's full scene
    dump, for the scene-dump summary, which does not say all that `holds_world` reads."""
    command = args[0]
    if not stdout.strip():
        return "nothing on stdout"
    if command in PICTURES:
        png = Path(stdout.strip().splitlines()[-1])
        if not png.is_file():
            return f"no PNG at {png}"
        with Image.open(png) as image:
            if all(low == high for low, high in image.convert("RGB").getextrema()):
                return "the PNG is one flat colour"
        return None
    try:
        document = json.loads(stdout)
    except ValueError:
        return "stdout is not JSON"
    if not str(document.get("schema", "")).startswith("rhr."):
        return "no rhr schema"
    # A list cut to fit stdout keeps a row: an empty one beside a count of left-out
    # rows is a cut that dropped everything.
    for rows, more in CUT_LISTS:
        if document.get(more) and not document.get(rows):
            return f"`{rows}` cut to nothing ({more} {document[more]})"
    if command == "layout":
        # Input with UI has a screen with elements, each a rect (a node with --rich).
        rows = "nodes" if "--rich" in args else "rects"
        return None if document[rows] else f"no {rows}"
    if command == "hitmap":
        # A UI where nothing takes a click is an answer, as a clean UI is for check:
        # `panes` names each screen laid out, so a hitmap shows nodes or at least panes.
        return None if document["nodes"] or document["panes"] else "no nodes and no panes"
    if command == "check":
        # No findings is a clean UI, an answer; what must hold is that every finding is
        # counted, shown or not.
        counted = sum(document["findingCounts"].values())
        shown = len(document["findings"]) + document["moreFindings"]
        return None if shown == counted else f"{shown} findings shown or left out, {counted} counted"
    if command == "scene-dump":
        dump = document if "--parts" in args else world
        if dump is None:
            return "scene-dump --parts on the same input showed no dump to judge the summary by"
        return None if holds_world(dump) else "no parts, read terrain, sky, atmosphere, lights, beams or trails"
    if command == "inspect":
        # Every model or place holds an instance, and classCounts names its class.
        return None if document["instances"] and document["classCounts"] else "no instances"
    return f"no rule for {command}"


def rhr(tmp: Path, env: dict, *args: str) -> tuple[subprocess.CompletedProcess, str]:
    """rhr run in *tmp*, and the last line of its stderr."""
    proc = subprocess.run([*RHR, *args], cwd=tmp, env=env, capture_output=True, text=True, timeout=600)
    return proc, (proc.stderr.strip().splitlines() or [""])[-1]


def run_all(tmp: Path, cache: Path, env: dict) -> None:
    for i, (name, (target, holds)) in enumerate(inputs(tmp, cache).items()):
        world = None
        for args in RUNS:
            command = args[0]
            out = ["--out", str(tmp / f"{i}-{command}.png")] if command in PICTURES else []
            proc, last = rhr(tmp, env, *args, target, *out)
            label = f"{' '.join(args)} on {name}"
            if "Traceback" in proc.stderr or "page error" in proc.stderr:
                check(False, f"{label}: crashed (exit {proc.returncode}): {last[:200]}")
                continue
            if ("unreadable" in holds or (command in UI_COMMANDS and "ui" not in holds)
                    or (command in WORLD_COMMANDS and "world" not in holds)
                    or (command in DATA_COMMANDS and "source" in holds)):
                check(proc.returncode == 2 and not proc.stdout.strip() and bool(last.strip()),
                      f"{label}: exits 2 with a reason (exit {proc.returncode}: {last[:120]})")
                continue
            ok_codes = (0, 1) if command == "check" else (0,)
            why = shows_something(args, proc.stdout, world) if proc.returncode in ok_codes else None
            if args == ("scene-dump", "--parts") and why is None and proc.returncode == 0:
                world = json.loads(proc.stdout)
            check(proc.returncode in ok_codes and why is None,
                  f"{label}: shows something (exit {proc.returncode}{': ' + why if why else ''}"
                  f"{': ' + last[:120] if proc.returncode not in ok_codes else ''})")
    for command, target in (*((command, SHOP) for command in ("layout", "check", "hitmap")), ("scene-dump", TOWER)):
        proc, last = rhr(tmp, env, command, str(target), "--path", "Nowhere")
        check(proc.returncode == 2 and not proc.stdout.strip() and "Nowhere" in last,
              f"{command} --path Nowhere: exits 2 with a reason (exit {proc.returncode}: {last[:120]})")
    # Hidden elements take no clicks and are listed only with --all, so a --path that
    # holds nothing else would print no nodes.
    hidden = tmp / "hidden_only.rbxmx"
    hidden.write_text(HIDDEN_ONLY, encoding="utf-8")
    proc, last = rhr(tmp, env, "hitmap", str(hidden), "--path", "Gui/Frame")
    check(proc.returncode == 2 and not proc.stdout.strip() and "--all" in last,
          f"hitmap --path to only hidden elements: exits 2 and names --all (exit {proc.returncode}: {last[:120]})")
    proc, _ = rhr(tmp, env, "hitmap", str(hidden), "--path", "Gui/Frame", "--all")
    nodes = [node["path"] for node in json.loads(proc.stdout)["nodes"]] if proc.returncode == 0 else []
    check(nodes == ["Gui/Frame/Hidden"], f"hitmap --path to only hidden elements --all lists them ({nodes})")
    # check skips hidden UI: told apart from a --path that names nothing.
    proc, last = rhr(tmp, env, "check", str(hidden), "--path", "Gui/Frame/Hidden")
    check(proc.returncode == 2 and not proc.stdout.strip() and "only hidden UI" in last and "--show" in last,
          f"check --path to only hidden UI: exits 2 and names --show (exit {proc.returncode}: {last[:120]})")
    oversized(tmp, env)


def oversized(tmp: Path, env: dict) -> None:
    """A row longer than stdout's whole allowance is kept shortened and the rows after it
    are still kept; `--path` to it prints it, not an empty document."""
    label = tmp / "oversized_label.rbxmx"
    for extra in ((), ("--path", "Gui/Rules")):
        proc, _ = rhr(tmp, env, "layout", str(label), "--rich", *extra)
        document = json.loads(proc.stdout) if proc.returncode == 0 else {"nodes": []}
        paths = sorted(node["path"] for node in document["nodes"])
        want = ["Gui/Rules"] if extra else ["Gui/Rules", "Gui/Start", "Gui/Start/Child"]
        rules = next((node for node in document["nodes"] if node["path"] == "Gui/Rules"), {})
        check(paths == want and document.get("moreNodes") == 0
              and rules.get("shortened") == {"text.content": len(LONG_TEXT)} and "shortened" in proc.stderr,
              f"layout --rich {' '.join(extra)} on a label too long for stdout: keeps {want}, the label "
              f"shortened (exit {proc.returncode}: {paths}, moreNodes {document.get('moreNodes')}, "
              f"shortened {rules.get('shortened')})")


def main() -> int:
    print("nothing to show: every command shows something or exits 2 with a reason")
    from rhr.paths import CACHE

    with tempfile.TemporaryDirectory(prefix="rhr-nothing-") as directory:
        tmp = Path(directory)
        cache = tmp / "cache"
        if (CACHE / "bin").is_dir():
            shutil.copytree(CACHE / "bin", cache / "bin")
        env = {**os.environ, "RHR_CACHE_DIR": str(cache), "RHR_OFFLINE": "1", "RHR_SERVER": "0"}
        try:
            run_all(tmp, cache, env)
        finally:
            # The warm browser worker keeps its session in this cache, open until it stops.
            subprocess.run([*RHR, "browser", "stop"], env=env, capture_output=True, timeout=60)
    print("nothing to show: ok" if not failures else f"nothing to show: {len(failures)} failed")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    sys.exit(main())
