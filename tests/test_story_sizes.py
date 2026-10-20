#!/usr/bin/env python3
"""Sizes a story reads while it runs, against Studio's, and the clock its timers run on.

`tests/fixtures/rojo_sizes/` is a place project with three stories that report what
they read as "name = value" labels:

- Responsive: plain Roblox API (the same function runs in Studio), arranging UI from
  AbsoluteContentSize, TextBounds, AbsoluteSize and AbsolutePosition through their
  signals, a task.defer read and a read right after mount.
- Sizes: Vide (Packages/vide, upstream's source, MIT), reading a frame's AbsoluteSize
  before parenting, at mount, in task.defer, on Heartbeat and from its signal.
- Scheduler: when task.defer, task.delay and task.wait resume, counted in frames, and
  what os.clock reads across frames.

The expected values are Studio's, measured in Edit with each story function on a
Target of the area's size (desktop 1920x1022, phone 734x314), read at 0.5 s. Rows from
text metrics may be 1 px off; the pill is in FredokaOne, whose advances RHR has from
Studio (in other faces RHR's widths are a few percent off). A read in the same
resumption that parented the element (GSync, HalfAtMount) cannot be served: it reads
0,0 where Studio has the real size. On the phone only rows measured from the target
are checked; where Roblox puts the target in that space is not settled.

    python tests/test_story_sizes.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "tests" / "fixtures" / "rojo_sizes" / "src"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def rows(story: str, device: str, **env: str) -> dict[str, str] | None:
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORIES / f"{story}.story.luau"), "--rich",
                           "--device", device], cwd=ROOT, capture_output=True, text=True, timeout=300,
                          env={**os.environ, **env})
    check(proc.returncode == 0, f"{story} on {device} exits 0 {proc.stderr[-400:] if proc.returncode else ''}")
    if proc.returncode:
        return None
    found = {}
    for node in json.loads(proc.stdout)["nodes"]:
        name, said, value = ((node.get("text") or {}).get("content") or "").partition(" = ")
        if said:
            found[name] = value
    return found


def numbers(text: str | None) -> list[float] | None:
    try:
        return [float(part) for part in re.split(r",\s*", text or "")]
    except ValueError:
        return None


def expect(got: dict[str, str], label: str, row: str, studio: str, slack: float = 0) -> None:
    value = got.get(row)
    if slack:
        a, b = numbers(value), numbers(studio)
        ok = a is not None and b is not None and len(a) == len(b) and all(
            abs(x - y) <= slack for x, y in zip(a, b))
    else:
        ok = value == studio
    check(ok, f"{label} {row} = {value!r}, Studio {studio!r}" + (f" (within {slack:g} px)" if slack else ""))


def unservable(got: dict[str, str], label: str, row: str, studio: str) -> None:
    value = got.get(row)
    check(numbers(value) == [0, 0], f"{label} {row} = {value!r}: a synchronous read at mount reads 0,0 "
                                    f"(Studio {studio!r})")


RESPONSIVE = {
    "desktop": [("AListCanvas", "280", 0), ("AContentSize", "300,280", 0), ("BPillTextBounds", "176,18", 1),
                ("BPillSize", "200,32", 1), ("CBadgePosition", "520,0", 1), ("DCellSize", "377,188", 0),
                ("DCell5Position", "387,418", 0), ("EMode", "wide", 0), ("FDeferred", "1152,1022", 0),
                ("TargetSize", "1920,1022", 0), ("TargetPosition", "0,0", 0)],
    "phone": [("AListCanvas", "280", 0), ("AContentSize", "300,280", 0), ("BPillTextBounds", "176,18", 1),
              ("BPillSize", "200,32", 1), ("CBadgePosition", "520,0", 1), ("DCellSize", "140,70", 0),
              ("EMode", "narrow", 0), ("FDeferred", "440.4,314", 0), ("TargetSize", "734,314", 0)],
}
SYNC = {"desktop": "1152,1022", "phone": "440.4,314"}
HALF = {"desktop": "960, 511", "phone": "367, 157"}


def main() -> int:
    for device in ("desktop", "phone"):
        print(f"story sizes: responsive layouts on the {device}")
        got = rows("Responsive", device)
        if got is not None:
            for row, studio, slack in RESPONSIVE[device]:
                expect(got, device, row, studio, slack)
            unservable(got, device, "GSync", SYNC[device])

        print(f"story sizes: Vide reads on the {device}")
        got = rows("Sizes", device)
        if got is not None:
            for row in ("HalfDeferred", "HalfHeartbeat", "HalfChanged"):
                expect(got, device, row, HALF[device])
            expect(got, device, "HalfBeforeParent", "0, 0")
            expect(got, device, "HalfPositionAtMount", "0, 0")
            unservable(got, device, "HalfAtMount", HALF[device])

    print("story sizes: timers and the clock run on story time, 1/60 s a frame")
    got = rows("Scheduler", "desktop")
    if got is not None:
        for row, value, why in (
                ("DeferFrame", "0", "task.defer runs before the first frame"),
                ("DelayFrame", "15", "task.delay(0.25) fires on frame 15"),
                ("WaitElapsed", "0.1000 at frame 6", "task.wait(0.1) resumes on frame 6 and returns 0.1"),
                ("CancelledDelay", "not fired", "task.cancel stops a delay"),
                ("ClockFrames6To30", "0.4000", "os.clock() moves 24/60 s over 24 frames")):
            check(got.get(row) == value, f"{why}: {row} = {got.get(row)!r}")

    print("story sizes: RHR_STORY_SIZES=0 turns the passes off")
    got = rows("Responsive", "desktop", RHR_STORY_SIZES="0")
    if got is not None:
        check(got.get("AListCanvas") == "0" and got.get("FDeferred") == "0,0",
              f"without passes, sizes read as before layout: {got.get('AListCanvas')!r}, {got.get('FDeferred')!r}")

    print(f"story sizes: {len(failures)} failed" if failures else "story sizes: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
