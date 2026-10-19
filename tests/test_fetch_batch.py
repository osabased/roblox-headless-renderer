#!/usr/bin/env python3
"""Asset downloads (rhr.fetch.ensure): where each file is asked for, and what is kept.

Roblox is faked: `locate_signed_in`, `locate_public` and `_download` are replaced, and
the batch endpoint's HTTP call is answered in process, so nothing here needs a login
or the network. Checked: the signed-in answer is used first; the public endpoint is
asked only for what that could not answer; refusals without a login are not recorded
as failures (signing in must count at once); batches hold at most 256 assets. An image
with no download falls back to a thumbnail (`fetch_icons` faked too): one that fails
keeps the download's reason, a failed connection is not recorded, and an id that is
not an Image (a Decal, a Model, audio), which Roblox draws as nothing, is not drawn.

    python tests/test_fetch_batch.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


MESH = b"version 2.00\n" + b"\0" * 32


def png(red: int = 255) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (2, 2), (red, 0, 0, 255)).save(buffer, "PNG")
    return buffer.getvalue()


class Fake:
    """Stand-ins for Roblox: links by id, and the calls made."""

    def __init__(self, fetch, signed: dict[str, str], public: dict[str, str], files: dict | None = None):
        self.fetch, self.signed, self.public, self.files = fetch, signed, public, files or {}
        self.asked_signed: list[str] = []
        self.asked_public: list[str] = []
        self.saved = (fetch.locate_signed_in, fetch.locate_public, fetch._download)

    def __enter__(self):
        def signed_in(ids):
            self.asked_signed += ids
            return {i: self.signed.get(i, "missing (signed in: HTTP 404: not found)") for i in ids}

        def public(ids):
            self.asked_public += ids
            return {i: self.public.get(i, self.fetch._refused(401, "auth", signed_in=False)) for i in ids}

        def download(location):
            if location in self.files:
                return self.files[location]
            return png() if location.endswith(".png") else MESH

        self.fetch.locate_signed_in, self.fetch.locate_public, self.fetch._download = signed_in, public, download
        return self

    def __exit__(self, *exc):
        self.fetch.locate_signed_in, self.fetch.locate_public, self.fetch._download = self.saved


def clear(fetch, ids: list[str]) -> None:
    failures_record = fetch._load_json(fetch.FAILURES)
    for asset in ids:
        for kind in ("images", "meshes"):
            fetch._destination(kind, asset).unlink(missing_ok=True)
            failures_record.pop(f"{kind}:{asset}", None)
        failures_record.pop(f"original:{asset}", None)
    failures_record.pop("login", None)
    fetch._save_json(fetch.FAILURES, failures_record)


def ensure_cases(fetch) -> None:
    ids = ["990000101", "990000102", "990000103"]
    link = "https://cdn.example/"

    print("signed in: every link from the login, the public endpoint not asked")
    clear(fetch, ids)
    with Fake(fetch, {i: link + i for i in ids[:2]} | {ids[2]: link + ids[2] + ".png"}, {}) as fake:
        result = fetch.ensure({"meshes": set(ids[:2]), "images": {ids[2]}})
    check(result["meshes"] == {ids[0]: "fetched", ids[1]: "fetched"}, f"meshes fetched: {result['meshes']}")
    check(result["images"] == {ids[2]: "fetched"}, f"image fetched: {result['images']}")
    check(fetch._destination("meshes", ids[0]).read_bytes() == MESH, "the mesh is in the cache")
    check(not fake.asked_public, "the public endpoint was not asked")
    check(fetch._load_json(fetch.ORIGINALS).get(ids[2]) is True, "the image is marked as the original")

    print("signed in, one refused: recorded, not asked again without a login")
    clear(fetch, ids)
    with Fake(fetch, {ids[0]: link + ids[0]}, {}) as fake:
        result = fetch.ensure({"meshes": set(ids[:2])})
    check(result["meshes"][ids[1]].startswith("missing (signed in: HTTP 404"), result["meshes"][ids[1]])
    check(ids[1] not in fake.asked_public, "a refusal with a login is not asked again without one")
    check(f"meshes:{ids[1]}" in fetch._load_json(fetch.FAILURES), "the refusal is recorded for a day")

    print("no login: the public endpoint for everything; its refusals not recorded")
    clear(fetch, ids)
    with Fake(fetch, {}, {ids[0]: link + ids[0]}):
        fetch.locate_signed_in = lambda asked: {i: fetch._NO_LOGIN for i in asked}
        result = fetch.ensure({"meshes": set(ids[:2])})
    check(result["meshes"][ids[0]] == "fetched", "a mesh Roblox serves to anyone is fetched")
    check(result["meshes"][ids[1]] == fetch._NO_LOGIN, f"the other says there is no login: {result['meshes'][ids[1]]}")
    record = fetch._load_json(fetch.FAILURES)
    check(f"meshes:{ids[1]}" not in record, "a refusal without a login is not recorded")
    check("login" in record, "the missing login is remembered for a few minutes")

    print("login turned off (--no-studio-login): signed-in step skipped, nothing recorded")
    clear(fetch, ids)
    with Fake(fetch, {i: link + i for i in ids}, {}) as fake:
        result = fetch.ensure({"meshes": {ids[0]}}, login=False)
    check(not fake.asked_signed, "the login is not used")
    check("needs a signed-in account" in result["meshes"][ids[0]], result["meshes"][ids[0]])
    check(f"meshes:{ids[0]}" not in fetch._load_json(fetch.FAILURES), "the refusal is not recorded")
    clear(fetch, ids)


class Thumbnails:
    """Roblox's thumbnail service: id -> (picture URL, PNG bytes); the ids asked for."""

    def __init__(self, fetch, answers: dict[str, tuple[str, bytes]]):
        from rhr.ui_engine import asset_fetcher

        self.fetch, self.answers, self.module = fetch, answers, asset_fetcher
        self.asked: list[str] = []
        self.saved = asset_fetcher.fetch_icons

    def __enter__(self):
        def fetch_icons(ids, cache_dir, **_):
            self.asked += sorted(ids)
            urls, fails = self.module._load_state(cache_dir)
            for asset in ids:
                if asset in self.answers:
                    urls[asset], payload = self.answers[asset]
                    (cache_dir / f"{asset}.png").write_bytes(payload)
            self.module._save_state(cache_dir, urls, fails)
            yield from ()

        self.module.fetch_icons = fetch_icons
        return self

    def __exit__(self, *exc):
        self.module.fetch_icons = self.saved


def thumbnail_cases(fetch) -> None:
    import hashlib

    from rhr.missing_images import refused_by_roblox
    from rhr.ui_engine import asset_fetcher

    ids = [str(990004001 + n) for n in range(9)]
    net, gone, decal, file_decal, image, audio, no_thumb, unavailable, place = ids
    link = "https://cdn.example/"
    timed_out = "missing (download: <urlopen error timed out>)"
    model_file = b"<roblox!\x89\xff\r\n\x1a\n\0\0"
    tile = "https://tr.rbxcdn.com/180DAY-0/420/420/{}/Png/noFilter"
    sound = png(7)

    def no_login(asked):
        return {i: fetch._NO_LOGIN for i in asked}

    def recorded(asset: str) -> bool:
        return f"images:{asset}" in fetch._load_json(fetch.FAILURES)

    print("a download that fails and has no thumbnail keeps the download's reason")
    clear(fetch, ids)
    saved_unavailable = fetch.UNAVAILABLE_THUMBNAILS
    fetch.UNAVAILABLE_THUMBNAILS = {hashlib.md5(png(9)).hexdigest()}
    try:
        with Fake(fetch, {net: link + net, unavailable: link + unavailable}, {},
                  {link + net: timed_out, link + unavailable: timed_out}), \
                Thumbnails(fetch, {unavailable: ("https://t1.rbxcdn.com/180DAY-1", png(9))}):
            result = fetch.ensure({"images": {net, gone, unavailable}})["images"]
    finally:
        fetch.UNAVAILABLE_THUMBNAILS = saved_unavailable
    check(result[net] == timed_out, f"a failed connection says so: {result[net]}")
    check(not recorded(net), "a failed connection is not recorded for a day")
    reason = fetch.missing_reason(result[gone])
    check(result[gone] == "missing (signed in: HTTP 404: not found)" and refused_by_roblox(reason),
          f"Roblox's refusal is kept, graded as final: {result[gone]}")
    check(recorded(gone), "Roblox's refusal is recorded for a day")
    check(result[unavailable] == f"missing ({fetch.UNAVAILABLE})",
          f"a thumbnail Roblox shows as unavailable says so: {result[unavailable]}")

    print("an id that is not an Image draws as nothing, as in Roblox")
    clear(fetch, ids)
    with Fake(fetch, {file_decal: link + file_decal}, {}, {link + file_decal: model_file}), \
            Thumbnails(fetch, {file_decal: (tile.format("Decal"), png(1))}) as thumbs:
        result = fetch.ensure({"images": {file_decal}})["images"]
    reason = fetch.missing_reason(result[file_decal])
    check(reason.startswith("not an image") and refused_by_roblox(reason),
          f"a Decal's file is not an image: {result[file_decal]}")
    check(file_decal not in thumbs.asked, "its thumbnail is not asked for")
    check(not fetch._cached("images", file_decal) and recorded(file_decal), "nothing is cached; it is recorded")

    clear(fetch, ids)
    saved_audio = getattr(fetch, "AUDIO_THUMBNAILS", None)
    fetch.AUDIO_THUMBNAILS = {hashlib.md5(sound).hexdigest()}
    try:
        with Fake(fetch, {}, {}), Thumbnails(fetch, {
                decal: (tile.format("Decal"), png(2)), image: (tile.format("Image"), png(3)),
                audio: ("https://t7.rbxcdn.com/180DAY-2", sound), place: (tile.format("GameIcon4"), png(8))}):
            fetch.locate_signed_in = no_login
            result = fetch.ensure({"images": {decal, image, audio, no_thumb, place}})["images"]
    finally:
        fetch.AUDIO_THUMBNAILS = saved_audio
    for asset, kind in ((decal, "Decal"), (audio, "Audio"), (place, "another kind of asset")):
        reason = fetch.missing_reason(result[asset])
        check(reason.startswith("not an image") and kind in reason and refused_by_roblox(reason),
              f"no login: a thumbnail of {kind} is not drawn: {result[asset]}")
        check(not fetch._cached("images", asset) and recorded(asset), f"and not kept ({kind})")
    check(result[image] == "fetched" and fetch._cached("images", image), f"an Image's thumbnail is: {result[image]}")
    check(result[no_thumb] == fetch._NO_LOGIN, f"no thumbnail either: the missing login says why: {result[no_thumb]}")
    check(not recorded(no_thumb), "and it is not recorded (signing in must count at once)")

    print("a Decal's thumbnail cached before is not drawn")
    clear(fetch, ids)
    folder = fetch.ICON_CACHE
    folder.mkdir(parents=True, exist_ok=True)
    urls, fails = asset_fetcher._load_state(folder)
    urls.update({decal: tile.format("Decal"), image: tile.format("Image")})
    asset_fetcher._save_state(folder, urls, fails)
    for asset, red in ((decal, 4), (image, 5)):
        fetch._write(fetch._destination("images", asset), png(red))
    for marker in folder.glob(".placeholders-swept*"):
        marker.unlink()
    fetch._SWEPT.discard(str(folder))
    check(not fetch._cached("images", decal) and not fetch._destination("images", decal).exists(),
          "the cached thumbnail of a Decal is removed")
    check(fetch._cached("images", image), "the cached thumbnail of an Image stays")

    clear(fetch, ids)
    fetch._write(fetch._destination("images", file_decal), png(6))
    originals = fetch._load_json(fetch.ORIGINALS)
    originals.pop(file_decal, None)
    fetch._save_json(fetch.ORIGINALS, originals)
    with Fake(fetch, {file_decal: link + file_decal}, {}, {link + file_decal: model_file}), Thumbnails(fetch, {}):
        result = fetch.ensure({"images": {file_decal}})["images"]
    check(fetch.missing_reason(result[file_decal]).startswith("not an image")
          and not fetch._cached("images", file_decal),
          f"signed in: a thumbnail cached for an id whose file is a model is removed: {result[file_decal]}")
    clear(fetch, ids)


def batch_sizes(fetch) -> None:
    print("the public batch: at most 256 assets per request, answers matched by id")
    import urllib.request

    bodies: list[list[dict]] = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(request, timeout=None):
        items = json.loads(request.data)
        bodies.append(items)
        answers = []
        for item in items:
            asset = item["requestId"]
            if int(asset) % 2:
                answers.append({"requestId": asset, "locations": [{"location": f"https://cdn.example/{asset}"}]})
            else:
                answers.append({"requestId": asset, "errors": [{"code": 401, "message": "Authentication required"}]})
        return Response(json.dumps(answers).encode())

    saved = urllib.request.urlopen
    urllib.request.urlopen = urlopen
    try:
        ids = [str(990001000 + n) for n in range(600)]
        located = fetch.locate_public(ids)
    finally:
        urllib.request.urlopen = saved
    check(sorted(len(body) for body in bodies) == [88, 256, 256], f"batches of {[len(b) for b in bodies]}")
    check(located["990001001"] == "https://cdn.example/990001001", "a link comes back for its id")
    check("signed-in account: HTTP 401" in located["990001000"], located["990001000"])


def api_key(fetch) -> None:
    print("the API key: one request per asset; what it answers, and in which order it is asked")
    import os
    import urllib.error
    import urllib.request

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    limited = {"990003004": 1}
    seen_keys: list[str] = []

    def urlopen(request, timeout=None):
        seen_keys.append(request.get_header("X-api-key"))
        asset = request.full_url.rsplit("/", 1)[1]
        if request.get_header("X-api-key") != "good":
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {},
                                         io.BytesIO(b'{"errors":[{"code":401,"message":"Invalid API Key"}]}'))
        if limited.get(asset):
            limited[asset] -= 1
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"x-ratelimit-reset": "0"},
                                         io.BytesIO(b"{}"))
        if asset == "990003002":  # Roblox answers this refusal with HTTP 200
            return Response(b'{"errors":[{"code":403,"message":"Asset is not approved for the requester"}]}')
        return Response(json.dumps({"location": f"https://cdn.example/{asset}", "assetTypeId": 4}).encode())

    saved = urllib.request.urlopen, os.environ.get(fetch.API_KEY_ENV)
    urllib.request.urlopen = urlopen
    try:
        os.environ[fetch.API_KEY_ENV] = "good"
        answers = fetch.answers_api_key(["990003001", "990003002", "990003004"])
        check(answers["990003001"] == {"location": "https://cdn.example/990003001", "type": 4}, str(answers["990003001"]))
        check(answers["990003002"]["code"] == 403, f"a refusal sent with HTTP 200: {answers['990003002']}")
        check(answers["990003004"].get("location", "").endswith("990003004"), "a rate limit is waited out")
        check(set(seen_keys) == {"good"}, "the key goes in the x-api-key header")
        os.environ[fetch.API_KEY_ENV] = "bad"
        bad = fetch.answers_api_key(["990003001"])["990003001"]
        check(bad["code"] == 401 and "Invalid" in bad["message"], f"a bad key is reported: {bad}")
    finally:
        urllib.request.urlopen = saved[0]
        if saved[1] is None:
            os.environ.pop(fetch.API_KEY_ENV, None)
        else:
            os.environ[fetch.API_KEY_ENV] = saved[1]

    ids = ["990003101", "990003102", "990003103"]
    clear(fetch, ids)
    asked_key: list[str] = []
    saved_answers = fetch.answers_api_key

    def key_answers(asked):
        asked_key.extend(asked)
        return {i: ({"location": f"https://cdn.example/{i}"} if i != ids[1] else {"code": 401, "message": "Invalid API Key"})
                for i in asked}

    os.environ[fetch.API_KEY_ENV] = "good"
    try:
        with Fake(fetch, {}, {ids[1]: "https://cdn.example/" + ids[1]}) as fake:
            fetch.locate_signed_in = lambda asked: {i: fetch._NO_LOGIN for i in asked}
            fetch.answers_api_key = key_answers
            result = fetch.ensure({"meshes": set(ids)})
        check(result["meshes"][ids[0]] == "fetched", "no login: the key gets the asset")
        check(sorted(asked_key) == ids, "the key is asked for everything the login could not get")
        check(fake.asked_public == [ids[1]] and result["meshes"][ids[1]] == "fetched",
              "what the key could not get is asked for without it")
    finally:
        fetch.answers_api_key = saved_answers
        os.environ.pop(fetch.API_KEY_ENV, None)
        clear(fetch, ids)


def main() -> int:
    import os

    from rhr import fetch

    saved = os.environ.pop("RHR_OFFLINE", None)  # (the suite's switch; Roblox is faked here)
    try:
        ensure_cases(fetch)
        thumbnail_cases(fetch)
        batch_sizes(fetch)
        api_key(fetch)
    finally:
        if saved is not None:
            os.environ["RHR_OFFLINE"] = saved
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("fetch batch: ok")
    return 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
