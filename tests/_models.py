"""Roblox models built in code, for tests that rebuild a Studio probe's setup.

`item` builds an Instance and `write_model` writes a tree of them as an .rbxmx file.
A property is a plain bool, int, float or string, or a (tag, body) pair from the value
helpers here.

QUADRANTS are test images of four flat quadrants, so a sample in each shows which way
up an image is drawn. `quadrant_cache` puts them where render_ir finds cached images.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

QUADRANTS = {
    "rbxassetid://990000001": ((255, 0, 0), (255, 128, 0), (255, 0, 128), (128, 0, 0)),
    "rbxassetid://990000002": ((0, 255, 0), (128, 255, 0), (0, 255, 128), (0, 128, 0)),
    "rbxassetid://990000003": ((0, 0, 255), (0, 128, 255), (128, 0, 255), (0, 0, 128)),
}


def udim2(xs, xo, ys, yo):
    return ("UDim2", f"<XS>{xs}</XS><XO>{xo}</XO><YS>{ys}</YS><YO>{yo}</YO>")


def offset(x, y):
    return udim2(0, x, 0, y)


def scale(x, y):
    return udim2(x, 0, y, 0)


def udim(s, o):
    return ("UDim", f"<S>{s}</S><O>{o}</O>")


def vec2(x, y):
    return ("Vector2", f"<X>{x}</X><Y>{y}</Y>")


def colour3(r: float, g: float, b: float):
    return ("Color3", f"<R>{r}</R><G>{g}</G><B>{b}</B>")


def rgb(colour):
    return colour3(*(value / 255 for value in colour))


def token(value: int):
    return ("token", str(value))


def content(uri: str):
    return ("Content", f"<url>{escape(uri)}</url>" if uri else "<null></null>")


def item(cls: str, name: str, props: dict | None = None, children=()) -> dict:
    return {"class": cls, "name": name, "props": props or {}, "children": list(children)}


def _value(name: str, value) -> str:
    if isinstance(value, bool):
        return f'<bool name="{name}">{str(value).lower()}</bool>'
    if isinstance(value, int):
        return f'<int name="{name}">{value}</int>'
    if isinstance(value, float):
        return f'<float name="{name}">{value}</float>'
    if isinstance(value, str):
        return f'<string name="{name}">{value}</string>'
    kind, body = value
    return f'<{kind} name="{name}">{body}</{kind}>'


def write_model(path: Path, roots: list[dict]) -> Path:
    referents = itertools.count(1)

    def emit(node: dict) -> str:
        props = "".join(_value(key, value) for key, value in {"Name": node["name"], **node["props"]}.items())
        children = "".join(emit(child) for child in node["children"])
        return (f'<Item class="{node["class"]}" referent="RBX{next(referents)}"><Properties>{props}</Properties>'
                f"{children}</Item>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<roblox version="4">' + "".join(emit(root) for root in roots) + "</roblox>", encoding="utf-8")
    return path


def quadrant_cache(folder: Path) -> Path:
    """The QUADRANTS images in an image cache under `folder`, as rhr caches a download.

    Returns the icons_dir that render_ir finds them through.
    """
    cache = folder / "cache" / "icons"
    cache.mkdir(parents=True)
    for uri, colours in QUADRANTS.items():
        image = Image.new("RGBA", (64, 64))
        for (qx, qy), colour in zip(((0, 0), (32, 0), (0, 32), (32, 32)), colours):
            image.paste(colour + (255,), (qx, qy, qx + 32, qy + 32))
        image.save(cache / f"{uri.removeprefix('rbxassetid://')}.png")
    return folder / "icon_library"
