#!/usr/bin/env python3
"""What a story reads of GuiService and UserInputService beyond the device's input kind, per `--device`.

A Studio play-test reads Roblox's defaults for these (touch controls on, no key or
button down, the keyboard's characters for GetStringForKeyCode) and the gamepad state of
the device: the `console` preset has Gamepad1 connected and is a ten-foot interface, the
others have no gamepad. `tests/fixtures/rojo_stories/src/DeviceReads.story.luau` reads
each into a label; the ones that Roblox restricts to its own scripts (ViewportSizeInMM,
GetScreenResolution and the like) are not in it.

    python tests/test_device_reads.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "tests" / "fixtures" / "rojo_stories" / "src" / "DeviceReads.story.luau"

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


NO_GAMEPAD = {
    "IsTenFootInterface": "false",
    "GetConnectedGamepads": "[]",
    "GetNavigationGamepads": "[]",
    "GetGamepadConnected": "false false",
    "IsNavigationGamepad": "false false",
    "GetSupportedGamepadKeyCodes": "0 nil nil 0",
}
GAMEPAD = {
    "IsTenFootInterface": "true",
    "GetConnectedGamepads": "[Gamepad1]",
    "GetNavigationGamepads": "[Gamepad1]",
    "GetGamepadConnected": "true false",
    "IsNavigationGamepad": "true false",
    "GetSupportedGamepadKeyCodes": "18 ButtonX Thumbstick2 0",
}
DEVICES = {
    None: NO_GAMEPAD,
    "desktop": NO_GAMEPAD,
    "laptop": NO_GAMEPAD,
    "phone": NO_GAMEPAD,
    "android": NO_GAMEPAD,
    "tablet": NO_GAMEPAD,
    "console": GAMEPAD,
}
EVERY_DEVICE = {
    "TouchControlsEnabled": "true",
    "TouchControlsSetOff": "false",
    "GuiFlags": "true true true false false",
    "IsWindows": "true",
    "EmotesMenu": "false true",
    "SensorFlags": "false false false false",
    "Mouse": "Default 1 [] true",
    "MouseIconContent": "Content",
    "OnScreenKeyboard": "false 0,0 0,0",
    "UserHeadCFrame": "true true",
    "Pressed": "false false false",
    "Held": "[] [] 0,0 nil",
    "GetStringForKeyCode": "E=[E] One=[1] Space=[ ] Hash=[3] BackSlash=[\\] ButtonA=[ButtonA] DPadUp=[DPadUp] "
                           "Return=[] F1=[]",
    "GetImageForKeyCode": "ButtonA=[ButtonA@2x.png] Thumbstick2=[Thumbstick2@2x.png] E=[] Space=[]",
}


def reads(device: str | None) -> dict[str, str] | None:
    flags = ["--device", device] if device else ["--viewport", "1920x1080"]
    proc = subprocess.run([sys.executable, "-m", "rhr", "layout", str(STORY), "--rich", *flags], cwd=ROOT,
                          capture_output=True, text=True, timeout=300)
    check(proc.returncode == 0, f"{device or 'no --device'}: layout exits 0 "
                                f"{proc.stderr[-400:] if proc.returncode else ''}")
    if proc.returncode:
        return None
    prefix = "DeviceReads/Target/"
    return {node["path"][len(prefix):]: node.get("text", {}).get("content")
            for node in json.loads(proc.stdout)["nodes"] if node["path"].startswith(prefix)}


def main() -> int:
    for device, expected in DEVICES.items():
        name = device or "no --device"
        print(f"device reads: {name}")
        got = reads(device)
        if got is None:
            continue
        for read, value in {**expected, **EVERY_DEVICE}.items():
            check(got.get(read) == value, f"{name}: {read} = {got.get(read)!r}, expected {value!r}")

    print(f"device reads: {len(failures)} failed" if failures else "device reads: ok")
    return 1 if failures else 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
