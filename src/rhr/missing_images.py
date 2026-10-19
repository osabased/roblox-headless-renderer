"""Why each image a render leaves out draws as nothing, for `missingAssets` and `rhr check`.

The UI renderer notes each image that draws as nothing where its picture shows it
(rhr.ui_engine.assets.record_undrawn); `explain` gives each a reason and, where RHR
can say, how to get it drawn. Roblox draws nothing for an empty link or id 0 either,
so those are not listed.
"""

from __future__ import annotations

import re
from pathlib import Path

from rhr.paths import ICONS_DIR

CLIENT_FILE = "a file built into the Roblox client, which RHR's UI renderer does not read"
THUMBNAIL = "a thumbnail Roblox makes at run time"
UNKNOWN_LINK = "a kind of link RHR's UI renderer does not read"
NOT_DOWNLOADED = "not downloaded"

_ICON_TOKEN = re.compile(r"<\|icon:(.+?)\|>")
_ID_ZERO = re.compile(r"(?:rbxassetid://|[?&]id=)0+(?!\d)", re.IGNORECASE)


def no_image(uri: str) -> bool:
    """Whether Roblox draws nothing for *uri* either: an empty link, or id 0."""
    text = uri.strip()
    return text in ("", "0") or _ID_ZERO.search(text) is not None


def explain(undrawn: list[dict], statuses: dict[str, str] | None = None, *, offline: bool = False,
            views: bool = False, icons_dir: Path = ICONS_DIR) -> list[dict]:
    """The `missingAssets` rows for the images a render drew as nothing, each once:
    {path, class, uri, reason}, with `hint`, how to get the image drawn, where RHR can
    say, and `rect`, the part of the picture it would cover, where the render noted one.
    With *views* (`rhr scene --views`) a row also names the `view` whose picture that is.
    *statuses* are rhr.fetch.ensure's answers for the ids it was asked for; *offline*
    says nothing was asked for."""
    from rhr import fetch

    refused = fetch.refused_recently("images", {fetch.asset_id(entry["uri"]) for entry in undrawn} - {None})
    rows = []
    for entry in undrawn:
        judged = _judge(entry["uri"], entry.get("key", ""), statuses or {}, refused, offline, icons_dir)
        if judged is None:
            continue
        reason, hint = judged
        row = {"path": entry["path"], "class": entry["class"], "uri": entry["uri"], "reason": reason}
        if hint:
            row["hint"] = hint
        if entry.get("rect"):
            row["rect"] = entry["rect"]
        if views and entry.get("view"):
            row["view"] = entry["view"]
        if row not in rows:
            rows.append(row)
    return sorted(rows, key=_order)


def download_hint(why: str) -> str | None:
    """How to get an image drawn that RHR has not downloaded, *why* being what rhr.fetch
    said, where RHR can say."""
    from rhr import fetch

    if why == fetch.UNAVAILABLE:
        return "Roblox draws nothing for it either (deleted, private or moderated): use another image"
    if "no thumbnail" in why:
        return "RHR asks Roblox again a day after it last asked"
    if "offline" in why:
        return _fetch_hint()
    return None


def refused_by_roblox(reason: str) -> bool:
    """Whether *reason* is Roblox's final refusal of an image, which leaves it blank in
    Roblox too: unavailable (deleted, private or moderated), HTTP 404 or 409, or not an
    image. A refusal only RHR meets (no sign-in, a failed connection) is not."""
    from rhr import fetch

    return (reason == fetch.UNAVAILABLE or reason.startswith("not an image")
            or any(f"HTTP {code}:" in reason for code in (404, 409)))


def _order(row: dict) -> tuple:
    rect = row.get("rect") or {}
    return str(row["path"]), row["uri"], row.get("view") or "", tuple(rect.get(key, 0) for key in "xywh")


def _judge(uri: str, key: str, statuses: dict[str, str], refused: dict[str, str], offline: bool,
           icons_dir: Path) -> tuple[str, str | None] | None:
    """(why the image draws as nothing, how to get it drawn or None), or None when
    Roblox draws nothing for it either. *key* is what the renderer looked up for *uri*."""
    from rhr import fetch
    from rhr.paths import ICON_CACHE
    from rhr.ui_engine import assets

    if no_image(uri):
        return None
    swap = _ICON_TOKEN.search(key)
    if swap:
        return _swapped(swap.group(1)), None
    scheme = uri.strip().lower()
    if scheme.startswith("rbxasset://"):
        return CLIENT_FILE, None
    if scheme.startswith("rbxthumb://"):
        return THUMBNAIL, None
    aid = fetch.asset_id(uri)
    if aid is None or aid != (assets._extract_asset_id(key) or (key if key.isdigit() else None)):
        return UNKNOWN_LINK, f"RHR draws it written as rbxassetid://{aid}" if aid else None
    override = assets._load_asset_icon_overrides(icons_dir).get(aid)
    if override:
        return _swapped(override), None
    status = statuses.get(aid, "")
    if status.startswith("missing"):
        why = status.removeprefix("missing").strip(" ()") or "unavailable"
        return why, download_hint(why)
    file = assets._asset_cache_dir(icons_dir) / f"{aid}.png"
    if file.exists():
        return f"RHR could not read the cached file {file}", "delete it, and `rhr fetch` downloads it again"
    if fetch._cached("images", aid):
        return (f"cached in {ICON_CACHE}, but RHR's UI renderer reads images from {file.parent}",
                f"unset ICON_CACHE_DIR, or copy the file into {file.parent}")
    if aid in refused:
        return refused[aid], download_hint(refused[aid])
    return "offline" if offline else NOT_DOWNLOADED, _fetch_hint()


def _fetch_hint() -> str:
    from rhr import fetch

    return "`rhr fetch` downloads it" + (" once RHR_OFFLINE is unset" if fetch.offline() else "")


def _swapped(icon: str) -> str:
    return f"RHR swaps it for its own icon {icon}, which it does not have"
