#!/usr/bin/env python3
"""Machine-readable 3D scene dump contract."""

from __future__ import annotations

import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]
FIXTURE = ROOT / "tests/fixtures/scene_geometry.rbxmx"


def main() -> None:
    proc = subprocess.run(
        [*RHR, "scene-dump", "--parts", str(FIXTURE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert len(data["parts"]) == 1
    part = data["parts"][0]
    assert part["path"] == "Scene/Props/RedBlock"
    assert part["position"] == [2.0, 3.0, -4.0]
    assert part["size"] == [4.0, 2.0, 6.0]
    assert part["bounds"]["min"] == [-1.0, 2.0, -6.0], part["bounds"]
    assert part["bounds"]["max"] == [5.0, 4.0, -2.0], part["bounds"]
    assert data["bounds"]["center"] == [2.0, 3.0, -4.0]
    assert data["fallbacks"] == {}
    assert data["materialFallbacks"] == {}
    assert data["unsupportedVisualClasses"] == {}
    assert data["preferredCamera"] == "Scene/SceneCamera"
    assert "scene-dump 1 parts" in proc.stderr
    terrain_grids()
    print("scene dump: ok")


def terrain_ir(source: Path, names: tuple[str, ...] = ("Terrain",)) -> dict:
    return {"sourcePath": str(source), "roots": [{
        "className": "Workspace", "name": "Workspace", "props": {},
        "children": [{"className": "Terrain", "name": name, "props": {}, "children": []} for name in names]}]}


def terrain_xml(*grids: str | None) -> str:
    """A place whose Terrains hold these base64 SmoothGrids (None: no SmoothGrid at all)."""
    items = "".join(
        '<Item class="Terrain"><Properties><string name="Name">T</string>'
        + (f'<BinaryString name="SmoothGrid">{grid}</BinaryString>' if grid is not None else "")
        + "</Properties></Item>" for grid in grids)
    return f'<roblox version="4"><Item class="Workspace"><Properties></Properties>{items}</Item></roblox>'


def terrain_grids() -> None:
    """A Terrain with no SmoothGrid is the empty grid, and a file with only that is no
    world; a SmoothGrid that cannot be read is not called empty, and a file with only
    that says why it was not read."""
    import base64
    import tempfile

    from rhr.scene_dump import build_scene_dump, dump_json

    def scene_dump(ir: dict, folder: Path) -> subprocess.CompletedProcess:
        path = folder / "ir.json"
        path.write_text(json.dumps(ir), encoding="utf-8")
        return subprocess.run([*RHR, "scene-dump", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=120)

    with tempfile.TemporaryDirectory(prefix="rhr-terrain-") as directory:
        folder = Path(directory)
        place = folder / "place.rbxlx"

        place.write_text(terrain_xml(None), encoding="utf-8")
        ir = folder / "absent.json"
        ir.write_text(json.dumps(terrain_ir(place)), encoding="utf-8")
        dump = build_scene_dump(ir)
        assert dump["terrain"][0]["empty"] is True, dump["terrain"]
        assert "Terrain" not in dump["unsupportedVisualClasses"], dump["unsupportedVisualClasses"]
        proc = scene_dump(terrain_ir(place), folder)
        assert proc.returncode == 2 and "no 3D world" in proc.stderr, (proc.returncode, proc.stderr)

        # One SmoothGrid per Terrain, in order, though the first has none.
        grid = base64.b64encode(b"\x01\x05\x99").decode()
        place.write_text(terrain_xml(None, grid), encoding="utf-8")
        ir.write_text(json.dumps(terrain_ir(place, ("Terrain", "Terrain2"))), encoding="utf-8")
        dump = build_scene_dump(ir)
        assert [t["empty"] for t in dump["terrain"]] == [True, False], dump["terrain"]
        proc = scene_dump(terrain_ir(place, ("Terrain", "Terrain2")), folder)
        assert proc.returncode == 0, proc.stderr

        proc = scene_dump(terrain_ir(folder / "gone.rbxlx"), folder)
        assert proc.returncode == 2 and "could not be read" in proc.stderr and "gone.rbxlx" in proc.stderr, \
            (proc.returncode, proc.stderr)

        place.write_text(terrain_xml("not base64!"), encoding="utf-8")
        ir.write_text(json.dumps(terrain_ir(place)), encoding="utf-8")
        dump = build_scene_dump(ir)
        assert dump["terrain"][0]["empty"] is None, dump["terrain"]
        assert not any(key.startswith("_") for key in json.loads(dump_json(dump))), "the reason stays internal"
        proc = scene_dump(terrain_ir(place), folder)
        assert proc.returncode == 2 and "could not be read" in proc.stderr and "base64" in proc.stderr, \
            (proc.returncode, proc.stderr)
    print("scene dump: an absent SmoothGrid is empty, an unreadable one is named")


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    main()
