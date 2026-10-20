"""The sizes a running story reads: its layout passes, answered with the render's layout.

With sizes on, the story runtime (luau/story-runtime.luau) saves its live screen at each
layout pass and prints `RHR-PASS <file>`; `run` lays that file out with rhr.ui_layout,
as the render will, and answers with one JSON line: each element's path -> what Roblox
works out in layout. `s` AbsoluteSize, `p` AbsolutePosition (from the area's corner, as
the story's target reads it), `c` a layout's AbsoluteContentSize, `t` TextBounds, `cs`
and `w` a ScrollingFrame's AbsoluteCanvasSize and AbsoluteWindowSize. The runtime
writes the values that changed and fires their signals.

RHR_STORY_SIZES=0 runs stories without passes: what Roblox works out in layout then
reads as it does before layout, zero.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

OFF = {"0", "false", "no", "off"}


def enabled() -> bool:
    return os.environ.get("RHR_STORY_SIZES", "").strip().lower() not in OFF


def _document(file: Path, data: bytes) -> dict:
    from rhr.ir import _own_reader, emit_ir
    from rhr.rbx import binary, emit

    if _own_reader(data):
        try:
            return emit.emit(binary.read(data), profile="ui", source_path=str(file))[0]
        except Exception:  # noqa: BLE001 - the Lune reader below, as emit_ir does
            pass
    out = file.with_suffix(".json")
    try:
        emit_ir(file, out, profile="ui")
        return json.loads(out.read_text(encoding="utf-8"))
    finally:
        out.unlink(missing_ok=True)


def _pair(a: float, b: float) -> list[float]:
    # Rounded so a value the layout works out again reads as unchanged.
    return [round(float(a), 3), round(float(b), 3)]


def answer(document: dict, rect: tuple[float, float, float, float]) -> dict[str, dict]:
    """What Roblox works out in layout for each element of the story's screen (the IR
    document's first root), laid out in the area `rect` of the screen."""
    from rhr.ir import ensure_paths
    from rhr.ui_layout import TEXT_CLASSES, lay_out_pane, text_bounds

    ensure_paths(document["roots"])
    screen = document["roots"][0]
    scrolls: dict = {}
    contents: dict = {}
    boxes = lay_out_pane(screen, rect, scrolls, contents)
    x0, y0, width, height = rect
    reply: dict[str, dict] = {screen["path"]: {"s": _pair(width, height), "p": _pair(0, 0)}}

    def visit(node: dict) -> None:
        path = node["path"]
        box = boxes.get(path)
        if box is not None:
            entry = {"s": _pair(box.w, box.h), "p": _pair(box.x - x0, box.y - y0)}
            if node.get("className") in TEXT_CLASSES:
                entry["t"] = _pair(*text_bounds(node, box))
            scroll = scrolls.get(path)
            if scroll is not None:
                entry["cs"] = _pair(*scroll.canvas)
                entry["w"] = _pair(scroll.window[2], scroll.window[3])
            reply[path] = entry
        content = contents.get(path)
        if content is not None:
            reply[path] = {"c": _pair(*content)}
        for child in node.get("children") or []:
            visit(child)

    for child in screen.get("children") or []:
        visit(child)
    return reply


@dataclass
class Passes:
    """A story run's layout passes, answered in this process."""

    rect: tuple[float, float, float, float]
    count: int = 0
    skipped: int = 0
    seconds: float = 0.0
    problems: list[str] = field(default_factory=list)
    _last: tuple[str, str] | None = None

    def reply(self, file: Path) -> str:
        """The JSON line for the pass saved at `file`. A screen saved byte for byte as
        the last one gets the last answer again without a layout, all of it: the
        runtime writes only what differs, and an element the story rebuilt as it was
        still needs its sizes."""
        began = time.perf_counter()
        self.count += 1
        try:
            data = file.read_bytes()
            digest = hashlib.sha1(data).hexdigest()
            if self._last is not None and self._last[0] == digest:
                self.skipped += 1
                return self._last[1]
            line = json.dumps(answer(_document(file, data), self.rect), separators=(",", ":"))
            self._last = (digest, line)
            return line
        except Exception as problem:  # noqa: BLE001 - the story still runs, without sizes
            if len(self.problems) < 3:
                self.problems.append(f"a layout pass failed ({type(problem).__name__}: {str(problem)[:200]}); "
                                     "the story read the sizes it had")
            return "{}"
        finally:
            self.seconds += time.perf_counter() - began


def run(cmd: list[str], passes: Passes | None, *, timeout: float) -> tuple[subprocess.CompletedProcess, dict]:
    """Run the story runtime, answering its layout passes, within `timeout` seconds (a
    subprocess.TimeoutExpired past it). Returns the finished process, its stdout less
    the pass lines, and the runtime's own count of its passes (empty without passes)."""
    from rhr.procs import no_window

    if passes is None:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              stdin=subprocess.DEVNULL, timeout=timeout, **no_window()), {}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **no_window())
    lines: queue.Queue = queue.Queue()
    errors: list[str] = []

    def pump_out() -> None:
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    readers = [threading.Thread(target=pump_out, daemon=True),
               threading.Thread(target=lambda: errors.append(proc.stderr.read()), daemon=True)]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    out: list[str] = []
    stats: dict = {}
    try:
        while True:
            try:
                line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd, timeout) from None
            if line is None:
                break
            if line.startswith("RHR-PASS "):
                file = Path(line[len("RHR-PASS "):].strip())
                try:
                    proc.stdin.write(passes.reply(file) + "\n")
                    proc.stdin.flush()
                except OSError:
                    pass  # the runtime ended; its exit says why
            elif line.startswith("RHR-SIZES "):
                try:
                    stats = json.loads(line[len("RHR-SIZES "):])
                except ValueError:
                    pass
            else:
                out.append(line)
        proc.wait(max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise subprocess.TimeoutExpired(cmd, timeout) from None
    finally:
        if proc.stdin:
            try:
                proc.stdin.close()
            except OSError:
                pass
        for reader in readers:
            reader.join(5)
    return subprocess.CompletedProcess(cmd, proc.returncode, "".join(out), "".join(errors)), stats
