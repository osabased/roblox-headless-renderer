#!/usr/bin/env python3
"""`rhr scene` and `rhr preview` list each image their in-world GUIs leave out, where it would be on the screen.

A SurfaceGui holds a file built into the Roblox client and a cached image, and a
BillboardGui a thumbnail Roblox makes at run time; `rhr preview` also draws a
ScreenGui holding a client file. Each image that draws as nothing is in the report's
`missingAssets`, saying why, with the part of the screen it would cover (`rect`), and
the cached image, which draws, isn't. With `--views` each row names its view. The
cached image is read from a scratch image folder (ICON_CACHE_DIR), so the suite's
cache stays as it is.

Run: python tests/test_scene_missing_images.py
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "tests")]

from _models import QUADRANTS, content, item, offset, quadrant_cache, token, vec2, write_model  # noqa: E402

OUT = REPO / "out" / "scene_missing_images"
RHR = [sys.executable, "-m", "rhr"]
FILE = "rbxasset://textures/ui/GuiImagePlaceholder.png"
THUMB = "rbxthumb://type=Asset&id=990000150&w=150&h=150"
DRAWN = next(iter(QUADRANTS))
SCREEN = (500, 350)


def cframe(x: float, y: float, z: float):
    rotation = "".join(f"<R{row}{col}>{int(row == col)}</R{row}{col}>" for row in range(3) for col in range(3))
    return ("CoordinateFrame", f"<X>{x}</X><Y>{y}</Y><Z>{z}</Z>{rotation}")


def vec3(x: float, y: float, z: float):
    return ("Vector3", f"<X>{x}</X><Y>{y}</Y><Z>{z}</Z>")


def image(name: str, x: int, y: int, uri: str) -> dict:
    return item("ImageLabel", name, {"Position": offset(x, y), "Size": offset(64, 64), "BackgroundTransparency": 1.0,
                                     "Image": content(uri)})


def model() -> list[dict]:
    surface = item("SurfaceGui", "Surface", {"Face": token(2), "SizingMode": token(0), "CanvasSize": vec2(400, 200),
                                             "AlwaysOnTop": True},
                   [image("File", 16, 16, FILE), image("Drawn", 96, 16, DRAWN)])
    tag = item("BillboardGui", "Tag", {"Size": offset(80, 80), "AlwaysOnTop": True}, [image("Thumb", 8, 8, THUMB)])
    world = item("Workspace", "Workspace", {}, [
        item("Part", "Panel", {"CFrame": cframe(0, 0, 0), "Size": vec3(8, 4, 1), "Anchored": True}, [surface]),
        item("Part", "Post", {"CFrame": cframe(0, 4, 0), "Size": vec3(1, 1, 1), "Anchored": True}, [tag]),
    ])
    return [world, item("ScreenGui", "Hud", {"ScreenInsets": token(0)}, [image("File", 16, 16, FILE)])]


def places(report: dict) -> dict[str, tuple[float, float, float, float]]:
    """Where each missing image would be, seen from (0, 0, 14). The Back face, 400 by 200
    canvas pixels on 8 by 4 studs, faces the camera 13.5 studs away; the billboard is 14
    away and 4 studs up, its 80 pixel square centred there and placed on whole pixels."""
    fov = math.radians(float((report.get("camera") or {}).get("fieldOfView") or 70))
    focal = SCREEN[1] / 2 / math.tan(fov / 2)
    per_pixel = focal / 13.5 / 50
    tag_left = round(SCREEN[0] / 2 - 40)
    tag_top = round(SCREEN[1] / 2 - 4 * focal / 14 - 40)
    return {
        "Surface/File": (SCREEN[0] / 2 + (16 - 200) * per_pixel, SCREEN[1] / 2 + (16 - 100) * per_pixel,
                         64 * per_pixel, 64 * per_pixel),
        "Tag/Thumb": (tag_left + 8, tag_top + 8, 64, 64),
        "Hud/File": (16, 16, 64, 64),
    }


def near(rect, want: tuple[float, ...], tolerance: float = 1.5) -> bool:
    try:
        got = [float(rect[key]) for key in "xywh"]
    except (KeyError, TypeError, ValueError):
        return False
    return all(abs(a - b) <= tolerance for a, b in zip(got, want))


def listed(report: dict, suffix: str) -> list[dict]:
    return [row for row in report.get("missingAssets", []) if str(row.get("path", "")).endswith(suffix)]


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    source = write_model(OUT / "world.rbxmx", model())
    with tempfile.TemporaryDirectory(prefix="rhr-scene-missing-images-") as directory:
        quadrant_cache(Path(directory))
        env = {**os.environ, "ICON_CACHE_DIR": str(Path(directory) / "cache" / "icons")}

        def render(command: str, name: str, *extra: str) -> dict | None:
            proc = subprocess.run(
                [*RHR, command, str(source), "--json", "--viewport", "x".join(map(str, SCREEN)), *extra,
                 "--out", str(OUT / f"{name}.png")],
                capture_output=True, text=True, cwd=str(REPO), env=env, timeout=600,
            )
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError:
                check(False, f"{name}: a JSON report (exit {proc.returncode}): {proc.stderr[-1500:]}")
                return None

        camera = ("--camera", "0,0,14", "--look-at", "0,0,0")
        for command, extra in (("scene", ()), ("preview", ("--topbar-height", "0"))):
            report = render(command, command, *camera, *extra)
            if report is None:
                continue
            expected = [("Surface/File", FILE, "client"), ("Tag/Thumb", THUMB, "thumbnail")]
            if command == "preview":
                expected.append(("Hud/File", FILE, "client"))
            else:
                check(not listed(report, "Hud/File"), "scene: draws no ScreenGui, so lists none of its images")
            where = places(report)
            for suffix, uri, says in expected:
                found = listed(report, suffix)
                check(len(found) == 1 and found[0].get("uri") == uri and says in str(found[0].get("reason", "")),
                      f"{command}: {suffix} is listed missing, saying {says!r} ({found or 'not listed'})")
                rect = found[0].get("rect") if found else None
                check(near(rect, where[suffix]),
                      f"{command}: {suffix} is listed at {tuple(round(v, 1) for v in where[suffix])} on the screen "
                      f"({rect})")
            check(not listed(report, "Surface/Drawn"),
                  f"{command}: the cached image, which draws, isn't listed ({listed(report, 'Surface/Drawn')})")
            check(not any("view" in row for row in report.get("missingAssets", [])),
                  f"{command}: one camera, so no row names a view ({report.get('missingAssets')})")

        report = render("scene", "views", "--views", "iso,back")
        if report is not None:
            rows = report.get("missingAssets", [])
            check(bool(rows) and all(row.get("view") in ("iso", "back") and row.get("rect") for row in rows),
                  f"scene --views: each row names its view and has a rect ({rows})")
            seen = {(row.get("view"), suffix) for row in rows for suffix in ("Surface/File", "Tag/Thumb")
                    if str(row.get("path", "")).endswith(suffix)}
            want = {("iso", "Tag/Thumb"), ("back", "Tag/Thumb"), ("back", "Surface/File")}
            check(want <= seen, f"scene --views: lists each view's missing images (missing {sorted(want - seen)})")
    print(f"\n{len(failures)} in-world missing-image checks failed" if failures else "\nin-world missing images: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
