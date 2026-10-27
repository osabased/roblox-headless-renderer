#!/usr/bin/env python3
"""CHANGELOG.md has a section for pyproject's version, and the fork's sections run unbroken.

A release adds its `## <version> (fork)` section in one commit and sets pyproject's
version in the next, so the newest heading may be one ahead of pyproject but never
missing it. Rewording a section once dropped the heading of the one below it, which
nothing else would notice.

    python tests/test_changelog.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def problems(changelog: str, version: str) -> list[str]:
    headings = re.findall(r"^## (\S+)", changelog, flags=re.MULTILINE)
    found = []
    if version not in headings:
        found.append(f"pyproject's version {version} has no '## {version}' heading")
    forks = [int(n) for n in re.findall(r"^## \S+\+osabased\.(\d+)\b", changelog, flags=re.MULTILINE)]
    expected = list(range(max(forks, default=0), 0, -1))
    if forks != expected:
        missing = sorted(set(expected) - set(forks), reverse=True)
        found.append(f"fork sections run {forks}, not {expected[0]} down to 1"
                     + (f"; missing {missing}" if missing else ""))
    return found


def main() -> int:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    failures = problems((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    for failure in failures:
        print(f"  FAIL {failure}")
    if failures:
        return 1
    print(f"changelog: ok ({version})")
    return 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
