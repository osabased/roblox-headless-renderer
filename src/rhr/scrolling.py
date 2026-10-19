"""ScrollingFrame scrolling and scroll bars, with Studio's rules.

`solve` places a ScrollingFrame's bars, window and canvas once its own rect is known.
The layout pass (rhr.ui_layout) lays its children out on the canvas; the renderer clips
them to the window and draws the bars. Measured in Studio (tests/test_scroll_bars.py
holds the cases):

  * A bar shows on an axis ScrollingDirection allows when the canvas is longer than
    the frame, less the other bar's strip when that one shows. A strip is
    ScrollBarThickness wide, at the right (VerticalScrollBarPosition Left: the left) or
    the bottom, and the window is the frame less its strips.
  * The canvas is CanvasSize, its Scale of the box the frame's own Size resolved
    against, and at least the frame, less a bar's strip when that bar is inset
    (ScrollBarInset Always, or ScrollBar while the bar shows). AutomaticCanvasSize
    grows it to the children's extent plus UIPadding. An inset left bar puts the
    canvas past its strip. CanvasPosition is clamped to the canvas.
  * The thumb is the window's share of the track, at least two thicknesses long, drawn
    in three parts: TopImage, MidImage and BottomImage, top to bottom (left to right on
    a horizontal bar, each image turned a quarter turn counter-clockwise), tinted by
    ScrollBarImageColor3 and faded by ScrollBarImageTransparency. Roblox's own images,
    which RHR can't ship, are drawn as the shape they make in their own places; a
    custom image is drawn from its asset id; one RHR can't draw (another file the
    client ships, a thumbnail, an id not downloaded) draws nothing, and the render
    lists it in `missingAssets` (rhr.missing_images).
  * A frame with ScrollingEnabled false still draws its bars.

Not measured: bars against the frame's UICorner (drawn inside it); thickness,
CanvasSize and CanvasPosition under a UIScale (scaled like the frame's other pixel
sizes); a track shorter than two thicknesses; whether content shows under a left bar
that is not inset (RHR clips it to the window); UIPadding's Scale; AutomaticCanvasSize
with Scale-sized children; a ScrollingFrame as a UITableLayout cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from rhr.fetch import asset_id
from rhr.missing_images import CLIENT_FILE, THUMBNAIL, UNKNOWN_LINK, no_image
from rhr.studio import content_path

BAR_IMAGES = {
    "TopImage": "rbxasset://textures/ui/Scroll/scroll-top.png",
    "MidImage": "rbxasset://textures/ui/Scroll/scroll-middle.png",
    "BottomImage": "rbxasset://textures/ui/Scroll/scroll-bottom.png",
}
DEFAULT_THICKNESS = 12.0
# Roblox's own images make a white bar at 128/255 opacity with corners 0.39 thicknesses
# round, from the middle of the top part to the middle of the bottom one.
DEFAULT_ALPHA = 128 / 255
DEFAULT_CORNER = 0.39

Rect = tuple[float, float, float, float]


@dataclass
class Bar:
    vertical: bool
    track: Rect
    start: float  # the thumb, along the track
    length: float
    thickness: float

    def parts(self) -> list[tuple[str, Rect]]:
        """Each part's box, TopImage first, leaving out a part with no length."""
        t, start, length = self.thickness, self.start, self.length
        spans = (("TopImage", start, t), ("MidImage", start + t, length - 2 * t),
                 ("BottomImage", start + length - t, t))
        return [(part, self._box(along, size)) for part, along, size in spans if size > 0]

    def pill(self) -> tuple[Rect, float]:
        """The box of the bar Roblox's own images make, and its corner radius."""
        t = self.thickness
        return self._box(self.start + t / 2, self.length - t), DEFAULT_CORNER * t

    def _box(self, along: float, size: float) -> Rect:
        x, y, w, h = self.track
        return (x, y + along, w, size) if self.vertical else (x + along, y, size, h)


@dataclass
class Scroll:
    """A ScrollingFrame's scrolling, in screen pixels."""

    window: Rect
    canvas: tuple[float, float]
    position: tuple[float, float]  # CanvasPosition, clamped
    origin: tuple[float, float]  # the canvas's top left
    thickness: float
    bars: tuple[Bar, ...]
    colour: tuple[int, int, int]
    transparency: float
    images: dict[str, str]  # TopImage, MidImage, BottomImage


def _props(node: dict) -> dict:
    return node.get("props") or {}


def _num(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _enum(node: dict, name: str, default: str) -> str:
    value = _props(node).get(name)
    if isinstance(value, dict):
        return str(value.get("name", default))
    if isinstance(value, str):
        return value.rsplit(".", 1)[-1]
    return default


def _vec2(node: dict, name: str) -> tuple[float, float]:
    value = _props(node).get(name)
    if not isinstance(value, dict):
        return (0.0, 0.0)
    return (_num(value.get("X"), 0.0), _num(value.get("Y"), 0.0))


def _colour(node: dict, name: str) -> tuple[int, int, int]:
    value = _props(node).get(name)
    if not isinstance(value, dict):
        return (255, 255, 255)
    r, g, b = (min(255, max(0, round(_num(value.get(key), 1.0) * 255))) for key in ("R", "G", "B"))
    return (r, g, b)


def _image(node: dict, part: str) -> str:
    value = _props(node).get(part, BAR_IMAGES[part])
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""


def _inset(node: dict, name: str, shown: bool) -> bool:
    mode = _enum(node, name, "None")
    return mode == "Always" or (mode == "ScrollBar" and shown)


def _bar(vertical: bool, track: Rect, window: float, canvas: float, position: float, t: float) -> Bar:
    length = max(2 * t, window * window / canvas) if canvas > 0 else 2 * t
    start = (window - length) * position / (canvas - window) if canvas > window else 0.0
    return Bar(vertical, track, start, length, t)


def solve(node: dict, frame: Rect, scale: float, raw: tuple[float, float]) -> Scroll:
    """The scrolling of a ScrollingFrame at `frame` whose CanvasSize came to `raw`;
    `scale` is the UIScale on its pixel sizes."""
    x, y, w, h = frame
    raw_w, raw_h = raw
    t = max(0.0, _num(_props(node).get("ScrollBarThickness"), DEFAULT_THICKNESS)) * scale
    direction = _enum(node, "ScrollingDirection", "XY")
    vertical = horizontal = False
    for _ in range(2):  # one bar's strip can make the other axis overflow
        vertical = direction in ("Y", "XY") and raw_h > h - (t if horizontal else 0.0)
        horizontal = direction in ("X", "XY") and raw_w > w - (t if vertical else 0.0)
    left = _enum(node, "VerticalScrollBarPosition", "Right") == "Left"
    strip_v, strip_h = (t if vertical else 0.0), (t if horizontal else 0.0)
    window = (x + (strip_v if left else 0.0), y, max(0.0, w - strip_v), max(0.0, h - strip_h))
    inset_v = _inset(node, "VerticalScrollBarInset", vertical)
    inset_h = _inset(node, "HorizontalScrollBarInset", horizontal)
    canvas_w = max(raw_w, w - (t if inset_v else 0.0))
    canvas_h = max(raw_h, h - (t if inset_h else 0.0))
    cx, cy = _vec2(node, "CanvasPosition")
    cx = min(max(cx * scale, 0.0), max(0.0, canvas_w - window[2]))
    cy = min(max(cy * scale, 0.0), max(0.0, canvas_h - window[3]))
    bars: list[Bar] = []
    if t > 0 and vertical:
        bars.append(_bar(True, (x if left else x + w - t, y, t, window[3]), window[3], canvas_h, cy, t))
    if t > 0 and horizontal:
        bars.append(_bar(False, (x, y + h - t, window[2], t), window[2], canvas_w, cx, t))
    transparency = min(1.0, max(0.0, _num(_props(node).get("ScrollBarImageTransparency"), 0.0)))
    return Scroll(window=window, canvas=(canvas_w, canvas_h), position=(cx, cy),
                  origin=(x - cx + (t if left and inset_v else 0.0), y - cy), thickness=t, bars=tuple(bars),
                  colour=_colour(node, "ScrollBarImageColor3"), transparency=transparency,
                  images={part: _image(node, part) for part in BAR_IMAGES})


def classify(part: str, value: str) -> tuple[str, str]:
    """How a bar part's image draws: ("default", "") as Roblox's own, ("asset", id),
    ("missing", why) for one RHR can't draw, or ("none", "") for a value Roblox draws
    nothing for either (rhr.missing_images.no_image)."""
    path = content_path(value)
    if path is not None:
        if path == content_path(BAR_IMAGES[part]):
            return "default", ""
        return "missing", CLIENT_FILE
    ref = asset_id(value)
    if ref:
        return "asset", ref
    if value.startswith("rbxthumb://"):
        return "missing", THUMBNAIL
    if no_image(value):
        return "none", ""
    return "missing", UNKNOWN_LINK
