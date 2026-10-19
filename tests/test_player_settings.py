#!/usr/bin/env python3
"""What a story reads of the player's device and settings, per `--device`.

A Studio play-test on each device emulator reads the device's input kind
(UserInputService.PreferredInput, the *Enabled flags, GetLastInputType) and display
size (GuiService.ViewportDisplaySize), and Roblox's default player settings:
PreferredTextSize Medium, PreferredTransparency 1, ReducedMotionEnabled false. The
TopbarInset is the whole top bar between the device's side insets, since RHR draws
none of Roblox's buttons there. `tests/fixtures/rojo_stories/src/Settings.story.luau`
reads each into a label, along with TextService:GetTextBoundsAsync (the same
estimate GetTextSize makes, wrapped at Width), GuiService:Select (the visible
Selectable descendant with the smallest SelectionOrder) and InputSink, which starts
at Activate on a button or TextBox and None on anything else.

    python tests/test_player_settings.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "tests" / "fixtures" / "rojo_stories" / "src" / "Settings.story.luau"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


KEYBOARD = {"PreferredInput": "KeyboardAndMouse", "LastInputType": "MouseButton1", "TouchEnabled": "false",
            "KeyboardEnabled": "true", "MouseEnabled": "true", "GamepadEnabled": "false"}
TOUCH = {"PreferredInput": "Touch", "LastInputType": "Touch", "TouchEnabled": "true", "KeyboardEnabled": "false",
         "MouseEnabled": "false", "GamepadEnabled": "false"}
GAMEPAD = {"PreferredInput": "Gamepad", "LastInputType": "Gamepad1", "TouchEnabled": "false",
           "KeyboardEnabled": "false", "MouseEnabled": "false", "GamepadEnabled": "true"}
DEVICES = {
    None: {**KEYBOARD, "ViewportDisplaySize": "Medium", "TopbarInset": "0,0,1920,58"},
    "desktop": {**KEYBOARD, "ViewportDisplaySize": "Medium", "TopbarInset": "0,0,1920,58"},
    "laptop": {**KEYBOARD, "ViewportDisplaySize": "Medium", "TopbarInset": "0,0,1366,58"},
    "phone": {**TOUCH, "ViewportDisplaySize": "Small", "TopbarInset": "59,0,793,58"},
    "android": {**TOUCH, "ViewportDisplaySize": "Small", "TopbarInset": "47,0,733,58"},
    "tablet": {**TOUCH, "ViewportDisplaySize": "Small", "TopbarInset": "0,0,1180,58"},
    "console": {**GAMEPAD, "ViewportDisplaySize": "Large", "TopbarInset": "0,0,1920,58"},
}
EVERY_DEVICE = {
    "PreferredTextSize": "Medium",
    "PreferredTransparency": "1",
    "ReducedMotionEnabled": "false",
    "BoundsLine": "110,20",
    "BoundsWrapped": "50,60",
    "BoundsLines": "25,20",
    "Select": "First",
    "SelectNothing": "Kept",
    "InputSink": "TextButton=Activate ImageButton=Activate TextBox=Activate Frame=None TextLabel=None",
}


def reads(device: str | None) -> dict[str, str] | None:
    flags = ["--device", device] if device else ["--viewport", "1920x1080"]
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORY), "--rich", *flags], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)
    check(proc.returncode == 0, f"{device or 'no --device'}: layout exits 0 "
                                f"{proc.stderr[-400:] if proc.returncode else ''}")
    if proc.returncode:
        return None
    prefix = "Settings/Target/"
    return {node["path"][len(prefix):]: node.get("text", {}).get("content")
            for node in json.loads(proc.stdout)["nodes"] if node["path"].startswith(prefix)}


def main() -> int:
    for device, expected in DEVICES.items():
        name = device or "no --device"
        print(f"player settings: {name}")
        got = reads(device)
        if got is None:
            continue
        for read, value in {**expected, **EVERY_DEVICE}.items():
            check(got.get(read) == value, f"{name}: {read} = {got.get(read)!r}, expected {value!r}")

    print(f"player settings: {len(failures)} failed" if failures else "player settings: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
