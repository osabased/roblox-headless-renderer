#!/usr/bin/env python3
"""`rhr skill` prints the skill rhr ships, and `--install` writes a stub of it: the same
name and description, and a body that sends the agent to `rhr skill`, so an installed
skill reads the guide of the rhr installed now, not the one it was installed with. Each
check is a pytest function.

    python -m pytest tests/test_skill.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RHR = [sys.executable, "-m", "rhr"]
SHIPPED = ROOT / "src" / "rhr" / "skill" / "SKILL.md"


def _front(text: str) -> str:
    """The frontmatter block, its `---` lines included."""
    assert text.startswith("---\n"), text[:40]
    return text[:text.index("\n---\n", 4) + 5]


def test_skill_prints_what_rhr_ships():
    proc = subprocess.run([*RHR, "skill"], capture_output=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-300:]
    assert proc.stdout.replace(b"\r\n", b"\n") == SHIPPED.read_bytes()


def test_install_writes_a_stub_that_reads_rhr_skill(tmp_path):
    target = tmp_path / "rhr" / "SKILL.md"
    target.parent.mkdir()
    # An older install, the whole skill as it was then: the stub replaces it.
    target.write_text(_front(SHIPPED.read_text(encoding="utf-8")) + "\n# an old guide\n", encoding="utf-8")
    proc = subprocess.run([*RHR, "skill", "--install", str(tmp_path)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-300:]
    assert proc.stdout.strip() == str(target)
    raw = target.read_bytes()
    assert b"\r" not in raw, "the stub is written with LF line endings"
    stub = raw.decode("utf-8")
    shipped = SHIPPED.read_text(encoding="utf-8")
    assert _front(stub) == _front(shipped), "the stub keeps the shipped name and description"
    body = stub[len(_front(stub)):]
    assert "`rhr skill`" in body, body
    assert "an old guide" not in body and "## The loop" not in body, "the stub carries no guide of its own"
    assert len(body) < 1000, len(body)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
