"""How much a default JSON output may hold.

An agent reads stdout through a shell tool that cuts long output (Claude Code at
30,000 characters), and every character is paid in context. A list that grows with
the file (rects, findings, interactive elements, missing assets) is cut on stdout to
an allowance under BUDGET; the document counts the rows left out (`moreRects`,
`moreFindings`, ...), and `--all` gives every row (so does `--out` where it names the
JSON file; on `ui`, `scene` and `preview` it names the PNG). A row too big for the
whole allowance is kept with its long strings shortened, and says so in `shortened`.
tests/test_output_budget.py holds each default output under BUDGET on a 100k-part
place.
"""

from __future__ import annotations

import json
from collections import Counter

BUDGET = 30_000  # characters of JSON on stdout
ALLOWANCE = 24_000  # for the list a document grows with; its other fields take the rest
# `cut` entries: the paths with the most rows left out under them, each the deepest of a
# left-out row's path and its ancestor paths that the kept rows reach (a kept row's path
# or an ancestor of one), or its first path segment where they reach none.
CUT_LIMIT = 20
PER_CHECK = 10  # findings of one check on stdout, so one kind cannot crowd out the rest
SUMMARY_LIMIT = 40  # groups and missing assets a summary names before it only counts the rest
SHORT = 200  # characters a string keeps in a row too big for the whole allowance
# The keys whose values are instance paths as rhr prints them (a node's or script's
# `path`, a finding's `paths`, a hit test's `stack` and `target`): --path takes them
# back, so they are never shortened.
PATH_KEYS = frozenset({"path", "paths", "stack", "target"})


def _size(row) -> int:
    text = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
    # Claude Code cuts output by JS string length, UTF-16 units: an emoji is two.
    return (len(text) if text.isascii() else len(text.encode("utf-16-le", "surrogatepass")) // 2) + 1


def _shortened(row):
    """A copy of *row* with each string over SHORT characters cut to SHORT and
    `shortened` naming each such field (dotted, list items by index) with its full
    length; *row* itself when it is no dict."""
    if not isinstance(row, dict):
        return row
    lengths: dict[str, int] = {}

    def walk(value, name: str):
        if isinstance(value, str) and len(value) > SHORT:
            lengths[name] = len(value)
            return value[:SHORT]
        if isinstance(value, dict):
            return {key: item if key in PATH_KEYS else walk(item, f"{name}.{key}" if name else key)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item, f"{name}.{i}") for i, item in enumerate(value)]
        return value

    short = walk(row, "")
    if lengths:
        short["shortened"] = lengths
    return short


def count_shortened(rows) -> int:
    """How many of *rows* were shortened to fit."""
    return sum(1 for row in rows if isinstance(row, dict) and "shortened" in row)


def cut(rows: list, allowance: int, limit: int | None = None) -> tuple[list, int]:
    """The rows whose JSON fits in *allowance* characters, in order, and with *limit* at
    most that many; a row that does not fit is left out and the later ones are still
    tried. A row bigger than the whole allowance is shortened first (`_shortened`), and
    the first row is always kept, so rows never come out as none. Returns the kept rows
    and how many were left out."""
    kept, size = [], 0
    for row in rows:
        if limit is not None and len(kept) >= limit:
            break
        row_size = _size(row)
        if row_size > allowance:
            row = _shortened(row)
            row_size = _size(row)
        if kept and size + row_size > allowance:
            continue
        kept.append(row)
        size += row_size
    return kept, len(rows) - len(kept)


def _ancestor(path: str, stop) -> str | None:
    """The nearest ancestor of *path* that *stop* accepts, or None."""
    while "/" in path:
        path = path.rsplit("/", 1)[0]
        if stop(path):
            return path
    return None


def cut_tree(rows: list[tuple[str, object]], allowance: int) -> tuple[list[tuple[str, object]], list[dict]]:
    """Breadth-first: the (path, row) pairs nearest the top of the tree (fewest path
    segments first) that fit in *allowance*, in their original order, each pair sized
    as the JSON of `[path, row]`. A row that does not fit is left out with every row
    under its path, unless another row at that same path was kept (two siblings of one
    name), so a row is kept at every ancestor path that has rows; the later rows are
    still tried. A pair bigger than the whole allowance has its row shortened first,
    and the first row is always kept. Then where the rest went, for `--path`: each
    left-out row counted under the deepest of its path and its ancestor paths that the
    kept rows reach (a kept row's path, or an ancestor path of one), or under its first
    path segment where they reach none of them; the CUT_LIMIT paths with the most:
    [{"path", "more"}]. In a tree where every node is a row (layout --rich) that is the
    nearest kept ancestor; where only leaves are rows (hitmap's buttons) it is the
    container the kept rows share."""
    order = sorted(range(len(rows)), key=lambda i: (rows[i][0].count("/"), i))
    paths = {path for path, _ in rows}
    keep: dict[int, tuple[str, object]] = {}
    kept_at: set[str] = set()
    left_at: set[str] = set()
    left: list[str] = []
    size = 0
    for i in order:
        path, row = rows[i]
        parent = _ancestor(path, paths.__contains__)
        if parent not in left_at or parent in kept_at:
            # With the row's size, _size([path, row]), without serializing the row twice.
            path_size = _size(path) + 2
            row_size = path_size + _size(row)
            if row_size > allowance:
                row = _shortened(row)
                row_size = path_size + _size(row)
            if not keep or size + row_size <= allowance:
                keep[i] = (path, row)
                kept_at.add(path)
                size += row_size
                continue
        left_at.add(path)
        left.append(path)
    kept = [keep[i] for i in sorted(keep)]
    if not left:
        return kept, []
    reached: set[str] = set()
    for path in kept_at:
        while path not in reached:
            reached.add(path)
            if "/" not in path:
                break
            path = path.rsplit("/", 1)[0]
    under: dict[str, int] = {}
    for path in left:
        parent = path if path in reached else _ancestor(path, reached.__contains__)
        if parent is None:
            parent = path.split("/", 1)[0]
        under[parent] = under.get(parent, 0) + 1
    biggest = sorted(under.items(), key=lambda item: (-item[1], item[0]))[:CUT_LIMIT]
    return kept, [{"path": path, "more": count} for path, count in biggest]


def finding_counts(findings: list[dict]) -> dict[str, int]:
    """How many of *findings* each check found (`findingCounts`)."""
    return dict(Counter(finding["check"] for finding in findings))


def cut_findings(findings: list[dict], allowance: int) -> dict:
    """What stdout shows of *findings* (sorted, most severe first, each with a `check`):
    at most PER_CHECK of each check, as many as fit in *allowance*, and how many were
    left out (`check`, `inspect`)."""
    shown: dict[str, int] = {}
    picked = []
    for finding in findings:
        if shown.get(finding["check"], 0) < PER_CHECK:
            shown[finding["check"]] = shown.get(finding["check"], 0) + 1
            picked.append(finding)
    kept, _ = cut(picked, allowance)
    return {"findings": kept, "moreFindings": len(findings) - len(kept)}
