#!/usr/bin/env python3
"""Every image a picture leaves out is listed missing, where it would be and why, and only those.

A reviewer judges the PNG alone, so `rhr ui --json` lists in `missingAssets` each
image the picture should show but draws as nothing: a file built into the Roblox
client (`rbxasset://`), a thumbnail Roblox makes at run time (`rbxthumb://`), an id
that isn't cached, an id Roblox refused. An image that drew isn't listed, and neither
is one Roblox wouldn't show either: hidden, fully transparent, off screen, clipped
away, faded out with its CanvasGroup, on a bar that doesn't show, or a hover image.
Each row has the part of the picture the image would cover (`rect`) and, where rhr
can say, how to get it drawn (`hint`).

`rhr check` reports them as `image-missing`: a warning for an id Roblox shows as
unavailable, which is blank in Roblox too, a hover image's included; info for rhr's
own gaps, so a UI built on Roblox's own textures passes; nothing for an id that just
isn't downloaded yet, which `rhr ui` would fetch.
In-world GUIs note theirs the same way, at their place in the GUI's picture.

The models are built here and drawn by `rhr ui` and `rhr check` in a process of their
own, against a scratch cache that holds only the test images of four flat quadrants.

Run: python tests/test_missing_images.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import QUADRANTS, content, item, offset, quadrant_cache, token, vec2, write_model  # noqa: E402
from test_fixtures import emit_ir  # noqa: E402

OUT = REPO / "out" / "missing_images"
RHR = [sys.executable, "-m", "rhr"]
SCREEN = (800, 600)
CELL = 64
WHITE = (255, 255, 255)
FILE = "rbxasset://textures/ui/GuiImagePlaceholder.png"
SLICE_FILE = "rbxasset://textures/ui/dialog_white.png"
BAR_FILE = "rbxasset://textures/DevConsole/Arrow.png"
THUMB = "rbxthumb://type=Asset&id=990000150&w=150&h=150"
HEADSHOT = "rbxthumb://type=AvatarHeadShot&id=1&w=48&h=48"
UNCACHED = "rbxassetid://990000101"
REFUSED = "rbxassetid://990000102"
TILE_UNCACHED = "rbxassetid://990000103"
HOVER_UNCACHED = "rbxassetid://990000104"
BAR_UNCACHED = "rbxassetid://990000105"
ELSEWHERE = "rbxassetid://990000106"
ELSEWHERE_COLOUR = (200, 0, 200)
# A link form rhr.fetch reads as the cached 990000002: listed exactly when it doesn't draw.
OLD_URL = "http://www.roblox.com/asset?id=990000002"
DRAWN, BAR_DRAWN, _ = QUADRANTS
SLICE_CENTER = ("Rect2D", "<min><X>8</X><Y>8</Y></min><max><X>56</X><Y>56</Y></max>")


def at(index: int) -> tuple[int, int]:
    return 16 + index % 9 * 80, 16 + index // 9 * 80


def cell(index: int) -> tuple[int, int, int, int]:
    return (*at(index), CELL, CELL)


# path: (where the image would be, as x, y, w, h; class; uri; what the reason says).
LISTED = {
    "Probe/File": (cell(0), "ImageLabel", FILE, "client"),
    "Probe/SliceFile": (cell(1), "ImageLabel", SLICE_FILE, "client"),
    "Probe/Thumb": (cell(2), "ImageLabel", THUMB, "thumbnail"),
    "Probe/ButtonThumb": (cell(3), "ImageButton", HEADSHOT, "thumbnail"),
    "Probe/Uncached": (cell(4), "ImageLabel", UNCACHED, "offline"),
    "Probe/TileUncached": (cell(5), "ImageLabel", TILE_UNCACHED, "offline"),
    "Probe/Refused": (cell(6), "ImageLabel", REFUSED, "unavailable"),
    "Probe/Elsewhere": (cell(7), "ImageLabel", ELSEWHERE, "offline"),
    "Probe/BarFile": (cell(9), "ScrollingFrame", BAR_FILE, "client"),
    "Probe/BarUncached": (cell(10), "ScrollingFrame", BAR_UNCACHED, "offline"),
    "Probe/Edge": ((768, 256, 32, 64), "ImageLabel", FILE, "client"),
    "Probe/HalfClipper/Image": ((48, 256, 32, 64), "ImageLabel", FILE, "client"),
    "GlobalProbe/File": (cell(36), "ImageLabel", FILE, "client"),
    "GlobalProbe/Faded/Image": (cell(37), "ImageLabel", FILE, "client"),
    "GlobalProbe/BarFile": (cell(38), "ScrollingFrame", BAR_FILE, "client"),
}
# A bar's missing part is somewhere in its frame, which draws Roblox's own parts around it.
BARS = {"Probe/BarFile", "Probe/BarUncached", "GlobalProbe/BarFile"}
NOT_LISTED = (
    "Probe/Drawn", "Probe/HoverUncached", "Probe/HoverRefused", "Probe/BarDrawn", "Probe/BarDefaults", "Probe/Hidden",
    "Probe/HiddenParent/Image", "Probe/HiddenUncached", "Probe/Transparent", "Probe/OffScreen", "Probe/Clipper/Image",
    "Probe/ZeroSize", "Probe/Faded/Image", "Probe/BarHidden", "Probe/BarTransparent", "Probe/IdZero", "Probe/NoImage",
    "GlobalProbe/Drawn", "GlobalProbe/Hidden", "GlobalProbe/Clipper/Image",
)


def image(name: str, index: int, uri: str = "", cls: str = "ImageLabel", **props) -> dict:
    x, y = at(index)
    return item(cls, name, {"Position": offset(x, y), "Size": offset(CELL, CELL), "BackgroundTransparency": 1.0,
                            **({"Image": content(uri)} if uri else {}), **props})


def inner(uri: str, x: int = 0) -> dict:
    return item("ImageLabel", "Image", {"Position": offset(x, 0), "Size": offset(CELL, CELL),
                                        "BackgroundTransparency": 1.0, "Image": content(uri)})


def holder(cls: str, name: str, index: int, children=(), **props) -> dict:
    x, y = at(index)
    return item(cls, name, {"Position": offset(x, y), "Size": offset(CELL, CELL), "BackgroundTransparency": 1.0,
                            "BorderSizePixel": 0, **props}, children)


def bars(name: str, index: int, **props) -> dict:
    return holder("ScrollingFrame", name, index, **{"ScrollBarThickness": 12, "CanvasSize": offset(0, 100), **props})


def screens() -> list[dict]:
    probe = [
        image("File", 0, FILE),
        image("SliceFile", 1, SLICE_FILE, ScaleType=token(1), SliceCenter=SLICE_CENTER),
        image("Thumb", 2, THUMB),
        image("ButtonThumb", 3, HEADSHOT, "ImageButton"),
        image("Uncached", 4, UNCACHED),
        image("TileUncached", 5, TILE_UNCACHED, ScaleType=token(2), TileSize=offset(16, 16)),
        image("Refused", 6, REFUSED),
        image("Elsewhere", 7, ELSEWHERE),
        image("OldUrl", 8, OLD_URL),
        bars("BarFile", 9, TopImage=content(BAR_FILE)),
        bars("BarUncached", 10, MidImage=content(BAR_UNCACHED)),
        image("Drawn", 11, DRAWN),
        image("HoverUncached", 12, DRAWN, "ImageButton", HoverImage=content(HOVER_UNCACHED)),
        bars("BarDrawn", 13, MidImage=content(BAR_DRAWN)),
        bars("BarDefaults", 14),
        image("Hidden", 15, FILE, Visible=False),
        holder("Frame", "HiddenParent", 16, [inner(FILE)], Visible=False),
        image("HiddenUncached", 17, UNCACHED, Visible=False),
        image("Transparent", 18, FILE, ImageTransparency=1.0),
        holder("Frame", "Clipper", 19, [inner(FILE, 100)], ClipsDescendants=True),
        image("ZeroSize", 20, FILE, Size=offset(0, 0)),
        holder("CanvasGroup", "Faded", 21, [inner(FILE)], GroupTransparency=1.0),
        bars("BarHidden", 22, TopImage=content(BAR_FILE), CanvasSize=offset(0, 0)),
        bars("BarTransparent", 23, TopImage=content(BAR_FILE), ScrollBarImageTransparency=1.0),
        image("IdZero", 24, "rbxassetid://0"),
        image("NoImage", 25),
        image("OffScreen", 26, FILE, Position=offset(-300, -300)),
        holder("Frame", "HalfClipper", 27, [inner(FILE, 32)], ClipsDescendants=True),
        image("HoverRefused", 28, DRAWN, "ImageButton", HoverImage=content(REFUSED)),
        image("Edge", 0, FILE, Position=offset(768, 256)),
    ]
    # Under Global a CanvasGroup's GroupTransparency reaches its own background only.
    global_probe = [
        image("File", 36, FILE),
        holder("CanvasGroup", "Faded", 37, [inner(FILE)], GroupTransparency=1.0),
        bars("BarFile", 38, TopImage=content(BAR_FILE)),
        image("Drawn", 39, DRAWN),
        image("Hidden", 40, FILE, Visible=False),
        holder("Frame", "Clipper", 41, [inner(FILE, 100)], ClipsDescendants=True),
    ]
    return [item("ScreenGui", "Probe", {"ScreenInsets": token(0), "ZIndexBehavior": token(1)}, probe),
            item("ScreenGui", "GlobalProbe", {"ScreenInsets": token(0), "ZIndexBehavior": token(0)}, global_probe)]


def gaps() -> list[dict]:
    return [item("ScreenGui", "Gaps", {"ScreenInsets": token(0)},
                 [image("File", 0, FILE), image("Thumb", 1, THUMB), image("Uncached", 2, UNCACHED)])]


def in_world() -> list[dict]:
    surface = item("SurfaceGui", "Surface", {"CanvasSize": vec2(300, 100), "ZIndexBehavior": token(1)},
                   [image("File", 0, FILE), image("Thumb", 1, THUMB), image("Drawn", 2, DRAWN)])
    billboard = item("BillboardGui", "Billboard", {"Size": offset(200, 100), "ClipsDescendants": False}, [
        image("File", 0, FILE), image("Drawn", 1, DRAWN),
        image("Thumb", 0, THUMB, Position=offset(250, 16)),
        image("LeftDrawn", 0, DRAWN, Position=offset(-40, 16)),
    ])
    return [item("Part", "SurfacePart", {}, [surface]), item("Part", "BillboardPart", {}, [billboard])]


def scratch_cache(folder: Path) -> Path:
    """An rhr cache holding the quadrant images, and Roblox's refusal of REFUSED."""
    quadrant_cache(folder)
    refused = REFUSED.removeprefix("rbxassetid://")
    (folder / "cache" / "fetch_failures.json").write_text(json.dumps({f"images:{refused}": {
        "status": "missing (Roblox shows it as unavailable)", "time": time.time()}}), encoding="utf-8")
    return folder


def run(args: list[str], cache: Path, **env: str) -> tuple[dict, int]:
    base = {key: value for key, value in os.environ.items() if key != "ICON_CACHE_DIR"}
    proc = subprocess.run([*RHR, *args], capture_output=True, text=True, cwd=str(REPO), timeout=300,
                          env={**base, "RHR_CACHE_DIR": str(cache), "RHR_OFFLINE": "1", "RHR_SERVER": "0", **env})
    try:
        return json.loads(proc.stdout), proc.returncode
    except json.JSONDecodeError:
        print(f"rhr {args[0]} gave no JSON (exit {proc.returncode}): {proc.stderr[-1500:]}")
        return {}, proc.returncode


def pixels(png: Path) -> np.ndarray:
    return np.asarray(Image.open(png).convert("RGB")).astype(float)


def blank(img: np.ndarray, rect: tuple[int, int, int, int]) -> bool:
    x, y, w, h = rect
    return float(np.abs(img[y:y + h, x:x + w] - WHITE).max()) <= 10


def shows(img: np.ndarray, index: int, colours) -> bool:
    x, y = at(index)
    points = ((x + 16, y + 16), (x + 48, y + 16), (x + 16, y + 48), (x + 48, y + 48))
    return all(float(np.abs(img[py, px] - colour).max()) <= 10 for (px, py), colour in zip(points, colours))


def rows_of(report: dict) -> dict:
    return {(row.get("path"), row.get("uri")): row for row in report.get("missingAssets", [])}


def rect_of(row: dict) -> tuple[float, ...] | None:
    try:
        return tuple(float(row["rect"][key]) for key in "xywh")
    except (KeyError, TypeError, ValueError):
        return None


def placed(row: dict, where: tuple[int, int, int, int], part: bool) -> bool:
    """Whether *row*'s rect is *where*, or with *part* a part of it."""
    rect = rect_of(row)
    if rect is None or not part:
        return rect == where
    x, y, w, h = rect
    left, top, width, height = where
    return w > 0 and h > 0 and left <= x and top <= y and x + w <= left + width and y + h <= top + height


def check_ui(check, ir: Path, cache: Path, tmp: Path) -> bool:
    png = OUT / "probe.png"
    rows = rows_of(run(["ui", str(ir), "--json", "--viewport", "x".join(map(str, SCREEN)), "--out", str(png)],
                       cache)[0])
    img = pixels(png) if png.is_file() else np.zeros((SCREEN[1], SCREEN[0], 3))
    for path, (where, cls, uri, says) in LISTED.items():
        row = rows.get((path, uri)) or {}
        check(row.get("class") == cls and says in str(row.get("reason", "")),
              f"ui: {path} ({uri}) is listed missing as a {cls}, saying {says!r} ({row or 'not listed'})")
        bar = path in BARS
        check(placed(row, where, bar),
              f"ui: {path} is listed {'within' if bar else 'at'} {where}, where it would be ({row.get('rect')})")
        if not bar:
            check(blank(img, where), f"ui: {path} draws nothing in its place, no stand-in")
    for path in NOT_LISTED:
        listed = [row for (where, _), row in rows.items() if where == path]
        check(not listed, f"ui: {path} isn't listed missing ({listed})")
    extra = sorted({where for where, _ in rows} - set(LISTED) - {"Probe/OldUrl"})
    check(not extra, f"ui: nothing else is listed missing ({extra})")
    check(shows(img, 11, QUADRANTS[DRAWN]), "ui: the cached image draws (Probe/Drawn)")
    check(shows(img, 12, QUADRANTS[DRAWN]), "ui: a button with an uncached HoverImage draws its Image")

    hints = {path: (rows.get((path, uri)) or {}).get("hint") or "" for path, (_, _, uri, _) in LISTED.items()}
    check("rhr fetch" in hints["Probe/Uncached"], f"ui: an id that isn't cached says how to get it "
                                                  f"({hints['Probe/Uncached']!r})")
    check(bool(hints["Probe/Refused"]), f"ui: an id Roblox refused says what to do ({hints['Probe/Refused']!r})")
    check(not hints["Probe/File"] and not hints["Probe/Thumb"],
          f"ui: an image rhr can't draw at all has no hint ({hints['Probe/File']!r}, {hints['Probe/Thumb']!r})")

    old_url = rows.get(("Probe/OldUrl", OLD_URL))
    old_url_drawn = not blank(img, cell(8))
    check(old_url_drawn != (old_url is not None) and (old_url is None or old_url.get("reason") not in ("", "offline")),
          f"ui: {OLD_URL} is listed missing exactly when it doesn't draw (drawn: {old_url_drawn}, listed: {old_url})")
    check(old_url is None or "rbxassetid://990000002" in (old_url.get("hint") or ""),
          f"ui: {OLD_URL}, if listed, says how to write it for rhr to read ({old_url})")

    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    Image.new("RGBA", (CELL, CELL), ELSEWHERE_COLOUR + (255,)).save(elsewhere / "990000106.png")
    png = OUT / "probe_elsewhere.png"
    rows = rows_of(run(["ui", str(ir), "--json", "--viewport", "x".join(map(str, SCREEN)), "--out", str(png)], cache,
                       ICON_CACHE_DIR=str(elsewhere))[0])
    img = pixels(png) if png.is_file() else np.zeros((SCREEN[1], SCREEN[0], 3))
    check(("Probe/Elsewhere", ELSEWHERE) not in rows and shows(img, 7, (ELSEWHERE_COLOUR,) * 4),
          f"ICON_CACHE_DIR: an image drawn from it isn't listed missing ({rows.get(('Probe/Elsewhere', ELSEWHERE))})")
    drawn = rows.get(("Probe/Drawn", DRAWN)) or {}
    check(str(elsewhere) in str(drawn.get("reason", "")) and blank(img, cell(11)),
          f"ICON_CACHE_DIR: an image cached only where it doesn't look is listed, naming it ({drawn or 'not listed'})")
    check("ICON_CACHE_DIR" in (drawn.get("hint") or ""),
          f"ICON_CACHE_DIR: that image says how to get it drawn ({drawn.get('hint')!r})")
    return old_url_drawn


def check_check(check, ir: Path, cache: Path, old_url_drawn: bool) -> None:
    result, code = run(["check", str(ir), "--viewport", "x".join(map(str, SCREEN)), "--min-severity", "info"], cache)
    findings = [f for f in result.get("findings", []) if f.get("check") == "image-missing"]
    found = [(f["paths"][0], f["severity"]) for f in findings]
    want = {(path, "warning" if uri == REFUSED else "info")
            for path, (_, _, uri, says) in LISTED.items() if says != "offline"}
    want.add(("Probe/HoverRefused", "warning"))
    if not old_url_drawn:
        want.add(("Probe/OldUrl", "info"))
    check(set(found) == want, f"check: image-missing for each image left out but an id not downloaded yet, a "
                              f"warning for one Roblox refused, info for rhr's gaps "
                              f"(missing {sorted(want - set(found))}, extra {sorted(set(found) - want)})")
    check(len(found) == len(set(found)), f"check: each image is reported once ({sorted(found)})")
    details = {f["paths"][0]: f.get("detail", "") for f in findings}
    for path, says in (("Probe/File", "client"), ("Probe/Thumb", "thumbnail"), ("Probe/BarFile", "client"),
                       ("Probe/Refused", "unavailable"), ("Probe/HoverRefused", "unavailable")):
        check(says in details.get(path, ""), f"check: {path}'s finding says {says!r} ({details.get(path)!r})")
    check(code == 0, f"check: no missing image fails the check (exit {code})")


def check_gaps(check, cache: Path) -> None:
    ir = emit_ir(write_model(OUT / "gaps.rbxmx", gaps()), OUT / "gaps.json")
    args = ["check", str(ir), "--viewport", "x".join(map(str, SCREEN))]
    result, code = run(args, cache)
    shown = [f for f in result.get("findings", []) if f.get("check") == "image-missing" or f.get("severity") == "error"]
    check(not shown and code == 0,
          f"check: images only rhr can't draw are below a warning, so a UI built on them passes ({shown}, exit {code})")
    result, _ = run([*args, "--min-severity", "info"], cache)
    info = sorted((f["paths"][0], f["severity"]) for f in result.get("findings", [])
                  if f.get("check") == "image-missing")
    check(info == [("Gaps/File", "info"), ("Gaps/Thumb", "info")],
          f"check: they are info, and an id not downloaded yet isn't reported ({info})")


def check_grades(check) -> None:
    try:
        from rhr.fetch import missing_reason as why
        from rhr.missing_images import refused_by_roblox
    except ImportError as exc:
        check(False, f"check: Roblox's final refusals are warnings, a fetch that failed on rhr's side info ({exc})")
        return
    from rhr import fetch

    final = (fetch.UNAVAILABLE, why(fetch._refused(404, "Asset not found", signed_in=True)),
             why(fetch._refused(409, "Conflict", signed_in="API key")), "not an image: UnidentifiedImageError")
    ours = (why(fetch._NO_LOGIN), why(fetch._refused(401, "", signed_in=False)),
            why(fetch._refused(403, "Unauthorized", signed_in=True)), "signed-in download needs Lune: not found",
            "download: HTTP 404", "download: <urlopen error timed out>", "no thumbnail")
    check(all(map(refused_by_roblox, final)) and not any(map(refused_by_roblox, ours)),
          f"check: Roblox's final refusals are warnings, a fetch that failed on rhr's side info "
          f"({[r for r in final if not refused_by_roblox(r)]}, {[r for r in ours if refused_by_roblox(r)]})")
    nested = why("missing (signed in: timed out (os error 10060))")
    check(nested == "signed in: timed out (os error 10060)", f"check: a reason keeps its own parentheses ({nested!r})")


def check_in_world(check, tmp: Path) -> None:
    try:
        from rhr.ui_engine.assets import record_undrawn
    except ImportError as exc:
        check(False, f"in-world GUIs note the images they leave out ({exc})")
        return
    from rhr import pipeline
    from rhr.ir import load_ir

    ir = load_ir(emit_ir(write_model(OUT / "in_world.rbxmx", in_world()), OUT / "in_world.json"))
    icons = tmp / "in_world"
    quadrant_cache(icons)
    before = os.environ.get("ICON_CACHE_DIR")
    os.environ["ICON_CACHE_DIR"] = str(icons / "cache" / "icons")
    # The billboard's picture grows by the 40 pixels LeftDrawn reaches past its left edge.
    places = {"SurfacePart/Surface": ((300, 100), {"File": (16, 16), "Thumb": (96, 16)}),
              "BillboardPart/Billboard": ((200, 100), {"File": (56, 16), "Thumb": (290, 16)})}
    try:
        for gui, (size, where) in places.items():
            with record_undrawn() as undrawn:
                pipeline.render_gui_node(ir, gui, *size, OUT / f"{gui.split('/')[1].lower()}.png")
            got = sorted(((entry["path"], entry["uri"], rect_of(entry)) for entry in undrawn),
                         key=lambda noted: (noted[0], noted[1], noted[2] or ()))
            want = [(f"{gui}/File", FILE, (*where["File"], CELL, CELL)),
                    (f"{gui}/Thumb", THUMB, (*where["Thumb"], CELL, CELL))]
            check(got == want, f"in-world {gui}: notes the file and the thumbnail once each, at their places in "
                               f"its picture, and not the drawn images ({got})")
    finally:
        if before is None:
            os.environ.pop("ICON_CACHE_DIR", None)
        else:
            os.environ["ICON_CACHE_DIR"] = before


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        print(f"{'ok' if ok else 'FAIL'}  {message}")
        if not ok:
            failures.append(message)

    ir = emit_ir(write_model(OUT / "probe.rbxmx", screens()), OUT / "probe.json")
    with tempfile.TemporaryDirectory(prefix="rhr-missing-images-") as directory:
        tmp = Path(directory)
        cache = scratch_cache(tmp / "rhr")
        old_url_drawn = check_ui(check, ir, cache, tmp)
        check_check(check, ir, cache, old_url_drawn)
        check_gaps(check, cache)
        check_grades(check)
        check_in_world(check, tmp)
    print(f"\n{len(failures)} missing-image checks failed" if failures else "\nmissing images: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
