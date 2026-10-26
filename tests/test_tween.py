#!/usr/bin/env python3
"""Tweens in stories, against Roblox's own.

`tests/fixtures/tween/` holds what Studio did, recorded with the scripts in
`scripts/studio/record_tween_*.luau` (their headers say how):

- getvalue.json: TweenService:GetValue for every easing style and direction at 101
  alphas, and at alphas outside 0..1.
- trajectories.json: 14 tweens and 5 legacy GuiObject tweens (TweenPosition, TweenSize,
  TweenSizeAndPosition) sampled every frame of a Studio client for 4.5 s, with delays,
  repeats (one forever), reverses, Pause, Cancel, a tween taking over another's
  property, PlaybackState, Completed and the legacy callbacks.
- legacy.json: the legacy tweens' easing for every style and direction, and what a
  property reads after a value outside its range is set.
- semantics.json: Play, Pause and Cancel from each state, takeovers, every tweenable
  value type, whole-number goals, an empty goal table, a legacy tween and a Tween on one
  property, a property set after Play or during a delay, the errors TweenService and
  TweenInfo raise, and TweenInfo's defaults.

`tests/tween_replay.luau` rebuilds each recording's tweens on RHR's tween clock
(src/rhr/luau/tween.luau), sets the clock to each sample's time and reads the same
values. Each sample's time is the engine's own elapsed time for the tweens, from clock
probe tweens and, on a Server, Heartbeat's dt, so values compare at the moment Studio
read them: GetValue and the legacy easing within 1e-4, pixel offsets within 0.5 px,
anything else within 1e-3, and Completed and the legacy callbacks within 2 ms. A probe
reads up to 3 us off, so in the client's recording, timed by the probe alone, a value
that matches only when read that much earlier or later is noted, not failed (more than
two fail). Probes that disagree by more than 10 us fail the recording.

Stories in `tests/fixtures/rojo_tween/` play tweens at mount. A story is captured once
it has settled (nothing changed for 10 frames), or at 5 s of story time with what is
still moving named; --story-time captures a chosen moment.

    python tests/test_tween.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "tween"
STORIES = ROOT / "tests" / "fixtures" / "rojo_tween" / "src"
sys.path.insert(0, str(ROOT / "src"))

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


def summary(label: str, problems: list[str], total: int) -> None:
    """One line for a set of comparisons, with the first few that failed."""
    shown = "; ".join(problems[:4]) + (f"; and {len(problems) - 4} more" if len(problems) > 4 else "")
    check(not problems, f"{label}: {total - len(problems)} of {total} match" + (f" ({shown})" if problems else ""))


def close(got, want, slack: float) -> bool:
    if isinstance(want, bool) or isinstance(want, str) or want is None:
        return got == want
    if isinstance(want, (int, float)):
        return isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - want) <= slack
    return isinstance(got, list) and len(got) == len(want) and all(close(a, b, slack) for a, b in zip(got, want))


def same_value(got, want, kind: str) -> bool:
    """`kind` is the encoded type: UDim2 and UDim carry pixel offsets, checked to 0.5 px."""
    if kind in ("UDim2", "UDim"):
        return (isinstance(got, list) and len(got) == len(want) and close(got[0::2], want[0::2], 1e-3)
                and all(abs(a - b) <= 0.5 for a, b in zip(got[1::2], want[1::2])))
    return close(got, want, 1e-3)


UDIM2 = {"Position", "Size"}
UDIM = {"CornerRadius", "PaddingLeft"}


def kind_of(track: str) -> str:
    prop = track.split(".", 1)[1]
    return "UDim2" if prop in UDIM2 else "UDim" if prop in UDIM else "other"


def replay(*shift: str) -> dict | None:
    from rhr.ir import lune_executable

    proc = subprocess.run([lune_executable(), "run", str(ROOT / "tests" / "tween_replay.luau"), str(FIXTURES), *shift],
                          cwd=ROOT, capture_output=True, text=True, timeout=300)
    check(proc.returncode == 0, f"the replay {' '.join(shift)} runs {proc.stderr[-600:] if proc.returncode else ''}")
    return json.loads(proc.stdout) if proc.returncode == 0 else None


# A clock probe is a 100 s Linear tween, whose progress Studio rounds to about 2^-25 of
# its length.
PROBE_ERROR = 100 * 2**-25
# A value sits within a probe's error of a rounding edge rarely; many that do mean the
# replay's clock is off, not the probe.
MAX_NUDGED = 2


def clock_spread(recording: dict) -> float:
    """How far apart Studio's tween clocks drift: each action's probe tween against the
    main probe, from when the action ran."""
    starts: dict[str, float] = {}
    spread = 0.0
    for sample in recording["samples"]:
        probes = sample["probes"] if isinstance(sample["probes"], dict) else {}
        for name, elapsed in probes.items():
            if elapsed > 0:
                start = starts.setdefault(name, sample["e"] - elapsed)
                spread = max(spread, abs(sample["e"] - elapsed - start))
    return spread


def dt_drift(recording: dict) -> float:
    """How far the main probe reads from the sum of Heartbeat's dt, which a Server steps
    its tweens by."""
    since, sums = 0.0, []
    for index, sample in enumerate(recording["samples"]):
        since += sample["dt"] if index else 0.0
        sums.append(sample["e"] - since)
    start = sum(sums) / len(sums)
    return max(abs(offset - start) for offset in sums)


def compare_getvalue(studio: dict, rhr: dict) -> None:
    problems, total = [], 0
    for style, by_direction in studio["values"].items():
        for direction, values in by_direction.items():
            for key, alphas in (("values", studio["alphas"]), ("extra", studio["extraAlphas"])):
                want = studio[key][style][direction]
                got = rhr[key].get(style, {}).get(direction, [])
                for i, alpha in enumerate(alphas):
                    total += 1
                    if i >= len(got) or abs(got[i] - want[i]) > 1e-4:
                        problems.append(f"{style}.{direction} at {alpha:g}: {got[i] if i < len(got) else None} "
                                        f"!= {want[i]}")
    summary("GetValue, 11 styles x 3 directions, within 1e-4", problems, total)


def compare_run(label: str, studio: dict, rhr: dict, shifted: list[dict]) -> None:
    """A recording's samples, PlaybackStates, Completed events, callbacks and action results.

    A value that differs is still Studio's when the replay read a probe's error earlier
    or later (`shifted`) gives it."""
    check(rhr["tracks"] == studio["tracks"], f"{label}: the replay reads the recording's tracks")
    by_track: dict[str, list[str]] = {}
    nudged: list[str] = []
    for index, (sample, got) in enumerate(zip(studio["samples"], rhr["samples"])):
        for column, (name, want, value) in enumerate(zip(studio["tracks"], sample["values"], got["values"])):
            if same_value(value, want, kind_of(name)):
                continue
            if any(same_value(other["samples"][index]["values"][column], want, kind_of(name)) for other in shifted):
                nudged.append(f"{name} at {sample['e']:.4f} reads {value}, Studio {want}")
            else:
                by_track.setdefault(name, []).append(f"at {sample['e']:.4f} {value} != {want}")
    for name in studio["tracks"]:
        problems = by_track.get(name, [])
        summary(f"{label} {name}", problems, len(studio["samples"]))
    if nudged:
        print(f"  note {label}: {len(nudged)} value(s) match when read within a probe's error: {'; '.join(nudged[:4])}")
    check(len(nudged) <= MAX_NUDGED, f"{label}: at most {MAX_NUDGED} values match only within a probe's error "
                                     f"({len(nudged)})")

    problems, total = [], 0
    for sample, got in zip(studio["samples"], rhr["samples"]):
        for tween, state in sample["states"].items():
            total += 1
            if got["states"].get(tween) != state:
                problems.append(f"{tween} at {sample['e']:.4f} {got['states'].get(tween)} != {state}")
    summary(f"{label} PlaybackState of every tween at every sample", problems, total)

    want = [(c["tween"], c["state"]) for c in studio["completions"]]
    got = [(c["tween"], c["state"]) for c in rhr["completions"]]
    check(got == want, f"{label} Completed fires in Studio's order: {got if got != want else len(want)}"
                       + (f" != {want}" if got != want else " events"))

    def by_occurrence(completions: list[dict]) -> dict:
        """Each event by tween, state and how many times it had fired, so one out of order
        is still compared with its own."""
        counts: dict[tuple, int] = {}
        out = {}
        for c in completions:
            key = (c["tween"], c["state"])
            counts[key] = counts.get(key, 0) + 1
            out[(*key, counts[key])] = c
        return out

    problems = []
    got_by = by_occurrence(rhr["completions"])
    for key, want_c in by_occurrence(studio["completions"]).items():
        name = f"{want_c['tween']} {want_c['state']}"
        got_c = got_by.get(key)
        if got_c is None:
            problems.append(f"{name} does not fire")
            continue
        issues = []
        if abs(got_c["e"] - want_c["e"]) > 2e-3:
            issues.append(f"{name} at {got_c['e']:.4f}, Studio {want_c['e']:.4f}")
        for prop, value in (want_c["values"] or {}).items():
            kind = "UDim2" if prop in UDIM2 else "UDim" if prop in UDIM else "other"
            if not same_value(got_c["values"].get(prop), value, kind):
                issues.append(f"{name} {prop} {got_c['values'].get(prop)} != {value}")
        if issues:
            problems.append(", ".join(issues))
    summary(f"{label} Completed: when, and the values it reads", problems, len(studio["completions"]))

    want = studio.get("callbacks", [])
    got = rhr["callbacks"]
    check([(c["callback"], c["status"]) for c in got] == [(c["callback"], c["status"]) for c in want]
          and all(abs(g["e"] - w["e"]) <= 2e-3 for g, w in zip(got, want)),
          f"{label} legacy callbacks {[(c['callback'], c['status'], round(c['e'], 4)) for c in got]} == Studio's "
          f"{[(c['callback'], c['status'], round(c['e'], 4)) for c in want]}")
    want = [(a["action"], a.get("result")) for a in studio["actions"]]
    got = [(a["action"], a.get("result")) for a in rhr["actions"]]
    check(got == want, f"{label} action results {got if got != want else 'match'}" + (f" != {want}" if got != want else ""))


def compare_legacy(studio: dict, rhr: dict) -> None:
    problems, total = [], 0
    for key, samples in studio["curves"].items():
        got = rhr["curves"].get(key, [])
        for i, sample in enumerate(samples):
            e, alpha = (float(part) for part in sample.split())
            total += 1
            if i >= len(got) or abs(got[i] - alpha) > 1e-4:
                problems.append(f"{key} at {e:.4f}: {got[i] if i < len(got) else None} != {alpha}")
    summary("legacy easing, 11 styles x 3 directions, within 1e-4", problems, total)
    check(not studio["errors"], f"Studio's legacy tweens all started: {studio['errors']}")


def compare_setters(label: str, studio: list, rhr: list) -> None:
    problems = []
    for want, got in zip(studio, rhr):
        if "error" in got or not close(got.get("read"), want["read"], 1e-4):
            problems.append(f"{want['class']}.{want['property']} set {want['set']} reads {got.get('read', got.get('error'))}"
                            f", Studio {want['read']}")
    summary(f"{label}: a tween's write past a property's range reads as Studio's", problems, len(studio))


def compare_semantics(studio: dict, rhr: dict, shifted: list[dict]) -> None:
    compare_run("semantics", studio, rhr, shifted)
    for want, got in zip(studio["errors"], rhr["errors"]):
        check(got.get("error") == want["error"], f"error for {want['case']}: {got.get('error')!r}"
                                                 + ("" if got.get("error") == want["error"] else f" != {want['error']!r}"))
    for want, got in zip(studio["infos"], rhr["infos"]):
        check(got == want, f"TweenInfo {want['case']}: {got if got != want else 'as Studio'}"
                           + (f" != {want}" if got != want else ""))
    compare_setters("semantics", studio["setters"], rhr["setters"])


def layout(story: str, *extra: str) -> tuple[dict | None, str]:
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORIES / f"{story}.story.luau"), "--rich",
                           "--device", "desktop", *extra], cwd=ROOT, capture_output=True, text=True, timeout=300,
                          env=os.environ)
    check(proc.returncode == 0, f"{story} {' '.join(extra)} exits 0 {proc.stderr[-600:] if proc.returncode else ''}")
    return (json.loads(proc.stdout) if proc.returncode == 0 else None), proc.stderr


def nodes(found: dict) -> dict[str, dict]:
    by_name = {node["path"].rsplit("/", 1)[-1]: node for node in found["nodes"]}
    target = by_name.get("Target")
    for node in by_name.values():
        if target is not None:
            node["at"] = (node["rect"]["x"] - target["rect"]["x"], node["rect"]["y"] - target["rect"]["y"])
    return by_name


def label(found: dict[str, dict], name: str) -> str | None:
    node = found.get(name)
    return ((node or {}).get("text") or {}).get("content")


def stories() -> None:
    # The story cache does not key on RHR's Python code (rhr.story_sizes answers the
    # layout passes these stories read), so each story runs again.
    from rhr.paths import IR_DIR

    for saved in (IR_DIR / "stories").glob("*/*.story.rbxm"):
        if saved.name in ("Motion.story.rbxm", "Forever.story.rbxm", "Drift.story.rbxm", "Poll.story.rbxm"):
            shutil.rmtree(saved.parent, ignore_errors=True)

    print("tween: a story is captured once its motion has settled")
    settled, log = layout("Motion")
    if settled is not None:
        got = nodes(settled)
        check(got.get("Slide", {}).get("at") == (400, 0), f"Slide ends at 400,0: {got.get('Slide', {}).get('at')}")
        chain = got.get("Chain", {})
        check(chain.get("at") == (300, 120) and chain.get("rect", {}).get("w") == 200,
              f"Chain's second tween, played from the first's Completed, ends at 300,120 200 wide: "
              f"{chain.get('at')} {chain.get('rect', {}).get('w')}")
        check(got.get("Legacy", {}).get("rect", {}).get("w") == 200,
              f"TweenSize ends 200 wide: {got.get('Legacy', {}).get('rect', {}).get('w')}")
        check(label(got, "SlideState") == "SlideState = Completed", f"{label(got, 'SlideState')!r}")
        check(label(got, "DriftAt") == "DriftAt = 100",
              f"a story reads where layout puts what only moved: {label(got, 'DriftAt')!r}")
        check("still moving" not in log, f"nothing is named as moving: {log[-300:]!r}")

    print("tween: --story-time captures a chosen moment, and has its own cache entry")
    mid, log = layout("Motion", "--story-time", "0.5")
    if mid is not None:
        got = nodes(mid)
        slide = got.get("Slide", {}).get("at")
        check(slide is not None and abs(slide[0] - 300) <= 0.5 and slide[1] == 0,
              f"Quad Out at 0.5 of 1 s is 75% of the way: Slide at {slide}, want 300,0")
        fade = (got.get("Fade") or {}).get("background", {}).get("transparency")
        check(fade is not None and abs(fade - 0.5) <= 1e-3,
              f"Fade, after its 0.25 s delay, is halfway to transparent: {fade}")
        chain = got.get("Chain", {})
        check(chain.get("rect", {}).get("w") == 200 and chain.get("at") is not None
              and abs(chain["at"][0] - 60) <= 0.5,
              f"Chain's second tween is 0.1 s into 0.5 s: {chain.get('at')} {chain.get('rect', {}).get('w')}, want 60,120 200")
        legacy = got.get("Legacy", {}).get("rect", {}).get("w")
        check(legacy is not None and abs(legacy - 120) <= 0.5, f"TweenSize is halfway: {legacy} wide, want 120")
        check(label(got, "SlideState") == "SlideState = Playing", f"{label(got, 'SlideState')!r}")
    _, log = layout("Motion", "--story-time", "0.01")
    check("captured at 0.02 s of story time, the first frame from 0.01 s" in log,
          f"a time between frames is captured at the next frame, and the log says so: {log[-300:]!r}")

    for bad in ("-1", "x"):
        proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORIES / "Motion.story.luau"),
                               "--story-time", bad], cwd=ROOT, capture_output=True, text=True, timeout=120)
        check(proc.returncode != 0 and "story-time" in proc.stderr and "unrecognized" not in proc.stderr,
              f"--story-time {bad} is refused: exit {proc.returncode} {proc.stderr[-200:]!r}")
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(ROOT / "tests" / "fixtures" / "autosize_padding.rbxmx"),
                           "--story-time", "1"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    check(proc.returncode == 2 and "--story-time is for a story" in proc.stderr,
          f"--story-time on a place is refused: exit {proc.returncode} {proc.stderr[-200:]!r}")

    print("tween: a story still moving at 5 s is captured there, with what moves named")
    forever, log = layout("Forever")
    if forever is not None:
        check("still moving" in log and "Spinner" in log and "Rotation" in log,
              f"the log names Spinner's Rotation as still moving: {log[-400:]!r}")
        counts = re.search(r"(\d+) layout passes \((\d+) with nothing new to lay out\)", log)
        check(counts is not None and int(counts[2]) >= int(counts[1]) - 3,
              f"a turning spinner is not laid out again each frame: {counts[0] if counts else log[-300:]!r}")

    print("tween: motion a timer starts on Heartbeat is captured at the cap, named")
    drift, log = layout("Drift")
    if drift is not None:
        check("still moving" in log and "Drifter Position" in log,
              f"the log names Drifter's Position as still moving: {log[-400:]!r}")
        at = nodes(drift).get("Drifter", {}).get("at")
        check(at is not None and at[0] >= 200, f"Drifter, moving a pixel a frame from 1 s, is at the cap's place: {at}")

    print("tween: a loop that waits forever is named where it waits")
    _, log = layout("Poll")
    check("1 timer(s) still waiting" in log and re.search(r"src[\\/]Poll\.story\.luau:8\b", log) is not None,
          f"the log names the loop's task.wait by file and line: {log[-400:]!r}")


def drawn_only() -> None:
    """Layout must not read what a pass skips on: each property _drawn_only names is
    changed in UI fixtures, and the layout's answer stays the same."""
    print("tween: a layout pass skips only what layout never reads")
    import tempfile

    from rhr.ir import emit_ir
    from rhr.story_sizes import _drawn_only, answer

    def nudge(value):
        if isinstance(value, bool) or isinstance(value, str) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value + 0.37
        if isinstance(value, list):
            return [nudge(item) for item in value]
        if isinstance(value, dict):
            return {key: nudge(item) for key, item in value.items()}
        return value

    def nudged(node: dict, names: set[str]) -> dict:
        props = {name: nudge(value) if _drawn_only(name.encode()) else value
                 for name, value in (node.get("props") or {}).items()}
        names.update(name for name in props if _drawn_only(name.encode()))
        return {**node, "props": props, "children": [nudged(child, names) for child in node.get("children") or []]}

    rect = (0.0, 0.0, 1920.0, 1080.0)
    for fixture in ("autosize_padding", "centered_grid_buttons", "scroll_scale", "text_overflow", "textscaled",
                    "line_height", "canvas_group_transparency", "gradient_transparency"):
        with tempfile.TemporaryDirectory() as scratch, contextlib.redirect_stderr(io.StringIO()):
            out = emit_ir(ROOT / "tests" / "fixtures" / f"{fixture}.rbxmx", Path(scratch) / "ir.json", profile="ui")
            document = json.loads(out.read_text(encoding="utf-8"))
        names: set[str] = set()
        changed = {**document, "roots": [nudged(root, names) for root in document["roots"]]}
        check(bool(names) and answer(changed, rect) == answer(document, rect),
              f"{fixture}: the same layout with {', '.join(sorted(names)) or 'nothing'} changed")


def main() -> int:
    print("tween: Roblox's tweens, replayed")
    studio = {name: json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
              for name in ("getvalue", "trajectories", "legacy", "semantics")}
    spread = max(clock_spread(studio["trajectories"]), clock_spread(studio["semantics"]), dt_drift(studio["semantics"]))
    check(spread <= 10e-6, f"Studio's clock probes and the Server's dt agree within 10 us ({spread * 1e6:.1f} us); "
                           "re-record a recording that drifts more")
    rhr = replay()
    shifted = [run for run in (replay(f"{-PROBE_ERROR:.9f}"), replay(f"{PROBE_ERROR:.9f}")) if run is not None]
    if rhr is not None:
        compare_getvalue(studio["getvalue"], rhr["getvalue"])
        compare_run("trajectories", studio["trajectories"], rhr["trajectories"],
                    [run["trajectories"] for run in shifted])
        check(rhr["trajectories"]["legacy"] == studio["trajectories"]["legacy"],
              f"legacy tweens return {rhr['trajectories']['legacy']}")
        compare_legacy(studio["legacy"], rhr["legacy"])
        compare_setters("legacy", studio["legacy"]["setters"], rhr["legacy"]["setters"])
        compare_semantics(studio["semantics"], rhr["semantics"], [])
    stories()
    drawn_only()
    print(f"tween: {len(failures)} failed" if failures else "tween: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
