#!/usr/bin/env python3
"""An ImageLabel draws its own Image whatever it is named.

Every label here has "sunburst" or "rays" in its name, as "Grayscale", "Arrays" and
"Trays" do. The scratch icon library's "Custom/Sunburst", RHR's own sunburst icon, is a
magenta square, so a label drawn as that icon instead of its Image shows magenta. A
cached image draws as it is, and an image RHR can't draw is left as nothing and listed
in `missingAssets`, whatever the name.

Run: python tests/test_image_names.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import QUADRANTS, content, item, offset, quadrant_cache, token, write_model  # noqa: E402
from test_fixtures import emit_ir  # noqa: E402

OUT = REPO / "out" / "image_names"
SCREEN = (800, 600)
CELL = 64
WHITE = (255, 255, 255)
STAND_IN = (255, 0, 255)
UNCACHED = "rbxassetid://990000101"
DRAWN = next(iter(QUADRANTS))
NAMES = ("GrayscaleIcon", "Arrays", "Strays", "Trays", "Rays", "Sunburst", "SunRays", "SunburstEffect")


def at(index: int) -> tuple[int, int]:
    return 16 + index * 80, 16


def label(name: str, index: int, uri: str) -> dict:
    x, y = at(index)
    return item("ImageLabel", name, {"Position": offset(x, y), "Size": offset(CELL, CELL),
                                     "BackgroundTransparency": 1.0, "Image": content(uri)})


def screen() -> list[dict]:
    drawn = [label(f"Shown{name}", i, DRAWN) for i, name in enumerate(NAMES)]
    missing = [label(f"Gone{name}", i, UNCACHED) for i, name in enumerate(NAMES)]
    for i, node in enumerate(missing):
        node["props"]["Position"] = offset(at(i)[0], 96)
    return [item("ScreenGui", "Names", {"ScreenInsets": token(0), "ZIndexBehavior": token(1)}, drawn + missing)]


def sample(img: np.ndarray, x: int, y: int) -> np.ndarray:
    return img[y:y + CELL, x:x + CELL]


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    ir = emit_ir(write_model(OUT / "names.rbxmx", screen()), OUT / "names.json")
    png = OUT / "names.png"
    with tempfile.TemporaryDirectory(prefix="rhr-image-names-") as directory:
        cache = Path(directory) / "rhr"
        library = quadrant_cache(cache)
        (library / "png").mkdir(parents=True)
        Image.new("RGBA", (64, 64), STAND_IN + (255,)).save(library / "png" / "sunburst.png")
        (library / "manifest.json").write_text(json.dumps({"Custom/Sunburst": {"file": "sunburst.png"}}), encoding="utf-8")
        base = {key: value for key, value in os.environ.items() if key != "ICON_CACHE_DIR"}
        proc = subprocess.run(
            [sys.executable, "-m", "rhr", "ui", str(ir), "--json", "--viewport", "x".join(map(str, SCREEN)),
             "--out", str(png)],
            capture_output=True, text=True, cwd=str(REPO), timeout=300,
            env={**base, "RHR_CACHE_DIR": str(cache), "RHR_OFFLINE": "1", "RHR_SERVER": "0"})
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"rhr ui gave no JSON (exit {proc.returncode}): {proc.stderr[-1500:]}")
        report = {}
    img = np.asarray(Image.open(png).convert("RGB")).astype(float) if png.is_file() else np.zeros((SCREEN[1], SCREEN[0], 3))
    listed = {row.get("path"): row for row in report.get("missingAssets", [])}
    top_left, top_right, bottom_left, bottom_right = QUADRANTS[DRAWN]
    for i, name in enumerate(NAMES):
        x, y = at(i)
        points = ((x + 16, y + 16), (x + 48, y + 16), (x + 16, y + 48), (x + 48, y + 48))
        colours = (top_left, top_right, bottom_left, bottom_right)
        check(all(float(np.abs(img[py, px] - colour).max()) <= 10 for (px, py), colour in zip(points, colours)),
              f"Shown{name}: a cached image draws as it is")
        check(float(np.abs(sample(img, x, 96) - WHITE).max()) <= 10, f"Gone{name}: an uncached image draws as nothing")
        row = listed.get(f"Names/Gone{name}")
        check(bool(row) and row.get("uri") == UNCACHED, f"Gone{name}: an uncached image is listed in missingAssets")
    print(f"\n{len(failures)} image-name checks failed" if failures else "\nimage names: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
