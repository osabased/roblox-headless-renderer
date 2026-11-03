#!/usr/bin/env python3
"""Default outputs stay small enough for an agent to read, whatever the file's size.

An agent's shell tool cuts output (Claude Code at 30,000 characters) and every
kilobyte is paid in context. The full scene dump of a 116k-part place was 52 MB and
`inspect` of a real game 424 KB; the defaults are summaries, and the flags give the
detail. Generated here: a place of 100,000 parts in 1,000 models whose StarterGui
holds 30 copies of examples/shop.rbxmx, 1,000 labels whose text spills out of its box
and 2,000 image buttons on ids that are not cached; a world of 2,000 decals on such
ids; and a model with 600 scripts, 300 of them calling getfenv, and 600 images. Every
default JSON output on them stays under the budget (the test names each one that does
not), each cut list counts exactly what it left out, `cut` names only paths those rows
are under and counts them all (`cut_problems`), `--all` or `--out` gives every row,
`check --baseline` refuses stdout that was cut, and `scene-dump --parts` without
`--path` or `--limit` is not cut (it is the full dump, by design).

    python -m pytest tests/test_output_budget.py

(pytest gives it an empty cache of its own, tests/conftest.py; run by hand, images
the machine has cached draw, and the missing-asset counts come out short.)
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# Offline even when run by hand: online, a run downloads those of the generated image
# ids that exist on Roblox, which took over ten minutes a command.
import _harness  # noqa: F401
from _models import ir_offset, script
from rhr.budget import CUT_LIMIT

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]
BUDGET = 30_000  # UTF-16 units of JSON on stdout: Claude Code cuts a tool's output there
SHOP = ROOT / "examples" / "shop.rbxmx"


def part(name: str, x: float, y: float) -> dict:
    return {"className": "Part", "name": name, "props": {
        "CFrame": {"_t": "CFrame", "X": x, "Y": y, "Z": 0, "R00": 1, "R01": 0, "R02": 0,
                   "R10": 0, "R11": 1, "R12": 0, "R20": 0, "R21": 0, "R22": 1},
        "Size": {"_t": "Vector3", "X": 2, "Y": 1, "Z": 2},
        "Color": {"_t": "Color3", "R": 0.5, "G": 0.5, "B": 0.5}, "Transparency": 0,
        "Material": {"_t": "EnumItem", "name": "Plastic", "value": 256},
        "Shape": {"_t": "EnumItem", "name": "Block", "value": 1}}, "children": []}


def strip(node: dict) -> None:
    """Drop the converter's path and id, which would make every copy the first one."""
    node.pop("path", None)
    node.pop("id", None)
    for child in node["children"]:
        strip(child)


def find(node: dict, name: str) -> dict | None:
    if node["name"] == name:
        return node
    for child in node["children"]:
        if (found := find(child, name)) is not None:
            return found
    return None


def big_place(path: Path, shop: dict) -> None:
    strip(shop)
    title = find(shop, "Title")
    guis = []
    for g in range(30):
        gui = copy.deepcopy(shop)
        gui["name"] = gui["props"]["Name"] = f"Shop{g}"
        guis.append(gui)
    labels = []
    for i in range(1000):
        label = copy.deepcopy(title)
        label["name"] = label["props"]["Name"] = f"Label{i}"
        label["props"].update(Text=f"a caption far too long for its box {i}", TextSize=14,
                              Size=ir_offset(40, 16), Position=ir_offset((i % 40) * 48, 40 + (i // 40) * 20))
        labels.append(label)
    images = [{"className": "ImageButton", "name": f"Icon{i}", "props": {
        "Size": ir_offset(20, 20), "Position": ir_offset((i % 90) * 21, 600 + (i // 90) * 21),
        "Image": f"rbxassetid://{9000000 + i}", "BackgroundTransparency": 1, "Visible": True}, "children": []}
        for i in range(2000)]
    guis.append({"className": "ScreenGui", "name": "Labels", "props": {"Enabled": True}, "children": labels})
    guis.append({"className": "ScreenGui", "name": "Icons", "props": {"Enabled": True}, "children": images})
    models = [{"className": "Model", "name": f"House{m}", "props": {},
               "children": [part(f"Brick{p}", m * 30 + (p % 10) * 2, (p // 10) * 1.0) for p in range(100)]}
              for m in range(1000)]
    path.write_text(json.dumps({"sourcePath": "budget", "roots": [
        {"className": "Workspace", "name": "Workspace", "props": {}, "children": models},
        {"className": "StarterGui", "name": "StarterGui", "props": {}, "children": guis}]}), encoding="utf-8")


def decal_world(path: Path) -> None:
    faces = ("Front", "Back", "Left", "Right", "Top", "Bottom", "Front", "Back", "Left", "Right")
    parts = []
    for p in range(200):
        block = part(f"Wall{p}", (p % 20) * 3, (p // 20) * 2)
        block["children"] = [{"className": "Decal", "name": f"Decal{d}", "props": {
            "Texture": f"rbxassetid://{8000000 + p * 10 + d}",
            "Face": {"_t": "EnumItem", "name": faces[d], "value": d}}, "children": []} for d in range(10)]
        parts.append(block)
    path.write_text(json.dumps({"sourcePath": "decals", "roots": [
        {"className": "Workspace", "name": "Workspace", "props": {}, "children": parts}]}), encoding="utf-8")


def many_scripts(path: Path) -> None:
    items = []
    for i in range(600):
        source = f"local env = getfenv(1)\nreturn {{ value = {i} }}" if i % 2 else f"return {{ value = {i} }}"
        items.append(script("ModuleScript", f"Module{i}", source + "\n") +
                     f'<Item class="Decal" referent="D{i}"><Properties><string name="Name">'
                     f'Decal{i}</string><Content name="Texture"><url>rbxassetid://{1000000 + i}</url></Content>'
                     f'</Properties></Item>')
    path.write_text('<roblox version="4"><Item class="Model" referent="M"><Properties><string name="Name">Big'
                    '</string></Properties>' + "".join(items) + '</Item></roblox>', encoding="utf-8")


def ancestry(path: str) -> set[str]:
    """*path* and each of its ancestor paths."""
    paths = {path}
    while "/" in path:
        path = path.rsplit("/", 1)[0]
        paths.add(path)
    return paths


def cut_problems(cut: list[dict], shown: list[str], every: list[str]) -> list[str]:
    """What is wrong with `cut` when the rows at the *shown* paths are on stdout, of the
    rows at the *every* paths (each path once per row). Not rhr.budget.cut_tree's rule
    over again, but what any answer by it holds: each entry's path is reached by the
    kept rows (a kept row's path or an ancestor of one), or is the first segment of a
    left-out row they reach none of; it counts no more rows than are left out at or
    under it; the counts sum to the rows left out, or to no more than that when
    CUT_LIMIT entries may have left some out; the biggest come first."""
    reached = set().union(*map(ancestry, shown))
    left = [ancestry(path) for path in (Counter(every) - Counter(shown)).elements()]
    tops = {min(lines, key=len) for lines in left if reached.isdisjoint(lines)}
    problems = []
    for entry in cut:
        if entry["path"] not in reached and entry["path"] not in tops:
            problems.append(f"{entry['path']}: no kept row reaches it, and it tops no left-out row")
        under = sum(1 for lines in left if entry["path"] in lines)
        if not 0 < entry["more"] <= under:
            problems.append(f"{entry['path']}: more {entry['more']}, {under} rows left out at or under it")
    total = sum(entry["more"] for entry in cut)
    if len(cut) > CUT_LIMIT or total > len(left) or (len(cut) < CUT_LIMIT and total != len(left)):
        problems.append(f"{len(cut)} entries count {total}, {len(left)} rows were left out")
    counts = [entry["more"] for entry in cut]
    if counts != sorted(counts, reverse=True):
        problems.append(f"not the biggest first: {counts}")
    return problems


def run(*args: str, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    proc = subprocess.run([*RHR, *args], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert proc.returncode in ok, (args[:2], proc.returncode, proc.stderr[-500:])
    return proc


def main() -> None:
    over = []

    def within_budget(label: str, stdout: str) -> dict:
        units = len(stdout.encode("utf-16-le")) // 2
        print(f"  {units:>9,} characters  {label}")
        if units >= BUDGET:
            over.append(f"{label}: {units:,} characters")
        return json.loads(stdout)

    def written(*args: str, ok: tuple[int, ...] = (0,)) -> dict:
        out = tmp / f"{args[0]}-out.json"
        run(*args, "--out", str(out), ok=ok)
        return json.loads(out.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="rhr-budget-") as directory:
        tmp = Path(directory)
        run("ir", str(SHOP), "--out", str(tmp / "shop.json"))
        place = tmp / "place.json"
        big_place(place, json.loads((tmp / "shop.json").read_text(encoding="utf-8"))["roots"][0])

        doc = within_budget("scene-dump", run("scene-dump", str(place)).stdout)
        assert doc["schema"] == "rhr.scene-summary/1" and doc["parts"] == 100_000, doc["parts"]
        assert doc["models"][0]["parts"] == 100 and doc["moreModels"] > 0, doc["models"][:2]
        one = json.loads(run("scene-dump", str(place), "--path", "Workspace/House7").stdout)
        assert one["parts"] == 100 and one["models"][0]["path"].startswith("Workspace/House7/"), one["models"][:1]
        limited = json.loads(run("scene-dump", str(place), "--parts", "--limit", "5").stdout)
        assert limited["schema"] == "rhr.scene-dump/1" and len(limited["parts"]) == 5
        assert limited["partsTotal"] == 100_000, limited["partsTotal"]
        house = json.loads(run("scene-dump", str(place), "--parts", "--path", "Workspace/House7").stdout)
        assert len(house["parts"]) == 100, "--parts gives every part under --path"
        # A known residual: the full dump is what bare --parts asks for, so it is not cut.
        full = run("scene-dump", str(place), "--parts").stdout
        assert len(full) > BUDGET and len(json.loads(full)["parts"]) == 100_000, "bare --parts gives every part"

        layout = within_budget("layout", run("layout", str(place)).stdout)
        whole = json.loads(run("layout", str(place), "--all").stdout)
        assert whole["moreRects"] == 0 and whole["cut"] == [], "--all prints every rect"
        assert layout["moreRects"] > 0 and len(layout["rects"]) + layout["moreRects"] == len(whole["rects"])
        assert all(path.rsplit("/", 1)[0] in layout["rects"] for path in layout["rects"]
                   if path.rsplit("/", 1)[0] in whole["rects"]), "breadth-first: a kept rect's parent is kept"
        problems = cut_problems(layout["cut"], list(layout["rects"]), list(whole["rects"]))
        assert not problems, problems[:3]
        top = layout["cut"][0]
        there = json.loads(run("layout", str(place), "--path", top["path"], "--all").stdout)["rects"]
        assert len(there) >= top["more"] and there == {
            path: rect for path, rect in whole["rects"].items() if top["path"] in ancestry(path)}, \
            f"--path {top['path']} --all prints the {top['more']} rects `cut` counts there ({len(there)})"
        rich = within_budget("layout --rich", run("layout", str(place), "--rich").stdout)
        rich_paths = [node["path"] for node in written("layout", str(place), "--rich")["nodes"]]
        assert rich["moreNodes"] > 0 and len(rich["nodes"]) + rich["moreNodes"] == len(rich_paths), rich["moreNodes"]
        problems = cut_problems(rich["cut"], [node["path"] for node in rich["nodes"]], rich_paths)
        assert not problems, problems[:3]
        top = rich["cut"][0]
        there = json.loads(run("layout", str(place), "--rich", "--path", top["path"], "--all").stdout)["nodes"]
        assert len(there) >= top["more"], f"--rich --path {top['path']} --all: {len(there)} nodes, cut {top['more']}"

        check = within_budget("check", run("check", str(place), ok=(0, 1)).stdout)
        every = written("check", str(place), ok=(0, 1))
        assert check["findingCounts"]["text-wider-than-box"] >= 1000, check["findingCounts"]
        assert sum(check["findingCounts"].values()) == len(every["findings"]) == (
            len(check["findings"]) + check["moreFindings"]) and every["moreFindings"] == 0
        assert max(sum(f["check"] == c for f in check["findings"]) for c in check["findingCounts"]) <= 10
        cut_stdout = tmp / "cut-check.json"
        cut_stdout.write_text(json.dumps(check), encoding="utf-8")
        refused = subprocess.run([*RHR, "check", str(place), "--baseline", str(cut_stdout)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=600)
        assert refused.returncode == 2 and "--out" in refused.stderr, refused.stderr[-300:]
        (tmp / "baseline.json").write_text(json.dumps(every), encoding="utf-8")
        again = json.loads(run("check", str(place), "--baseline", str(tmp / "baseline.json")).stdout)
        assert again["findings"] == [] and again["moreFindings"] == 0, "a baseline from --out holds every finding"

        assert json.loads(run("check", str(place), "--all", ok=(0, 1)).stdout)["findings"] == every["findings"], \
            "--all prints every finding"

        hitmap = within_budget("hitmap", run("hitmap", str(place)).stdout)
        clicks = written("hitmap", str(place))
        assert hitmap["moreNodes"] > 0 and len(hitmap["nodes"]) + hitmap["moreNodes"] == len(clicks["nodes"])
        assert len(hitmap["hitTests"]) + hitmap["moreHitTests"] == len(clicks["hitTests"]), hitmap["moreHitTests"]
        problems = cut_problems(hitmap["cut"], [node["path"] for node in hitmap["nodes"]],
                                [node["path"] for node in clicks["nodes"]])
        assert not problems, problems[:3]
        assert clicks["moreNodes"] == clicks["moreHitTests"] == 0 and clicks["cut"] == []
        top = hitmap["cut"][0]
        listed = json.loads(run("hitmap", str(place), "--path", top["path"], "--all").stdout)
        there = {node["path"] for node in listed["nodes"]}
        assert listed["moreNodes"] == listed["moreHitTests"] == 0 and len(listed["nodes"]) >= top["more"] and {
            node["path"] for node in clicks["nodes"] if top["path"] in ancestry(node["path"])} <= there, \
            f"--path {top['path']} --all prints every node there, hidden ones too"
        dumped = tmp / "ui-layout.json"
        ui = within_budget("ui --json", run("ui", str(place), "--json", "--out", str(tmp / "ui.png"),
                                            "--dump-layout", str(dumped)).stdout)
        assert len(ui["missingAssets"]) <= 40 and ui["moreMissingAssets"] > 0, ui["moreMissingAssets"]
        dumped = json.loads(dumped.read_text(encoding="utf-8"))
        assert dumped["rects"] == whole["rects"] and dumped["moreRects"] == 0 and dumped["cut"] == [], \
            "ui --dump-layout writes every rect, as layout --all prints them"
        assert len(json.loads(run("ui", str(place), "--json", "--all", "--out", str(tmp / "ui.png")).stdout)
                   ["missingAssets"]) == len(ui["missingAssets"]) + ui["moreMissingAssets"]

        world = tmp / "decals.json"
        decal_world(world)
        for command in ("scene", "preview"):
            report = within_budget(f"{command} --json (2,000 decals)",
                                   run(command, str(world), "--json", "--out", str(tmp / f"{command}.png")).stdout)
            assert len(report["missingAssets"]) + report["moreMissingAssets"] == 2000, report["moreMissingAssets"]

        model = tmp / "scripts.rbxmx"
        many_scripts(model)
        doc = within_budget("inspect", run("inspect", str(model)).stdout)
        assert doc["scriptsTotal"]["count"] == 600 and doc["assetCounts"]["images"] == 600, doc.get("scriptsTotal")
        assert doc["findingCounts"] == {"fenv": 300} and len(doc["findings"]) <= 10, doc["findingCounts"]
        assert len(doc["findings"]) + doc["moreFindings"] == 300, doc["moreFindings"]
        assert doc["moreScripts"] > 0 and len(doc["scripts"]) + doc["moreScripts"] == 300, doc["moreScripts"]
        flagged = written("inspect", str(model))
        assert len(flagged["findings"]) == len(flagged["scripts"]) == 300, "--out writes every flagged script"
        assert flagged["moreFindings"] == flagged["moreScripts"] == 0
        everything = json.loads(run("inspect", str(model), "--all").stdout)
        assert len(everything["scripts"]) == 600 and len(everything["assets"]["images"]) == 600
        assert len(everything["findings"]) == 300, "--all prints every finding"
    assert not over, f"over the {BUDGET:,}-character budget: " + "; ".join(over)
    print("output budget: every default JSON output stays under 30,000 characters; --all and --out give every row")


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    main()
