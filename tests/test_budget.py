#!/usr/bin/env python3
"""rhr.budget on its own: which rows a cut keeps, where `cut` says the rest went, what
a too-big row keeps of its strings, and how a row's size is counted. Pure Python, no
`rhr` process: each check is a pytest function.

    python tests/test_budget.py
"""

from __future__ import annotations

import json

from rhr.budget import ALLOWANCE, CUT_LIMIT, SHORT, _shortened, _size, cut, cut_tree


def _reached(kept) -> set[str]:
    """Every kept path and every ancestor path of one."""
    out = set()
    for path, _ in kept:
        while True:
            out.add(path)
            if "/" not in path:
                break
            path = path.rsplit("/", 1)[0]
    return out


def test_cut_names_the_deepest_path_the_kept_rows_reach():
    """Hitmap rows: only buttons are rows, their cards and the Scroll are not. The rows
    left out are counted under Scroll, the deepest path the kept buttons reach, not
    under each card."""
    def button(path, z):
        return {"path": path, "class": "TextButton", "rect": {"x": 1.5, "y": 2.5, "w": 100, "h": 30},
                "visible": True, "active": True, "selectable": True, "interactable": True,
                "capturesClicks": True, "activatedTargetCandidate": True, "zOrder": z, "pane": 0}

    rows = sorted((f"StarterGui/Shop/Main/Scroll/ItemCard[{i}]/{name}", None)
                  for i in range(1, 1001) for name in ("Buy", "Info"))
    rows = [(path, button(path, i)) for i, (path, _) in enumerate(rows)]
    kept, cuts = cut_tree(rows, ALLOWANCE // 2)
    assert len(kept) == 38, len(kept)
    assert cuts == [{"path": "StarterGui/Shop/Main/Scroll", "more": len(rows) - len(kept)}], cuts


def test_cut_names_the_nearest_kept_ancestor_in_a_tree_of_rows():
    """layout --rich: every frame is a row, so the rows left out are counted under
    their nearest kept ancestor."""
    rows = [("Gui/Main", {}), ("Gui/Main/List", {})]
    rows += [(f"Gui/Main/List/Item{i}", {"t": "x" * 40}) for i in range(10)]
    rows += [(f"Gui/Main/List/Item{i}/Label", {}) for i in range(10)]
    kept, cuts = cut_tree(rows, 200)
    kept_paths = [path for path, _ in kept]
    assert kept_paths[:2] == ["Gui/Main", "Gui/Main/List"], kept_paths
    items = [path for path in kept_paths if path.count("/") == 3]
    assert items and len(items) < 10, kept_paths
    labels = [path for path in kept_paths if path.endswith("/Label")]
    # An item left out takes its Label with it, both under List; a kept item's Label
    # left out is counted under that item.
    expected = {"Gui/Main/List": 2 * (10 - len(items))}
    for item in items:
        if f"{item}/Label" not in labels:
            expected[item] = 1
    got = {entry["path"]: entry["more"] for entry in cuts}
    assert got == expected, (got, expected)
    assert sum(got.values()) == len(rows) - len(kept)


def test_cut_names_the_top_segment_when_no_kept_row_reaches_a_row():
    """Two ScreenGuis: rows under the second, which no kept row reaches, are counted
    under its first path segment; a row with no `/` under its own path."""
    rows = [("SG1", {"t": "a" * 50}), ("SG2", {"t": "b" * 50}), ("SG2/Frame", {"t": "c" * 10})]
    kept, cuts = cut_tree(rows, 80)
    assert [path for path, _ in kept] == ["SG1"], kept
    assert cuts == [{"path": "SG2", "more": 2}], cuts

    rows = [("SG1/A", {"t": "a" * 50}), ("SG2/B", {"t": "b" * 50}), ("SG2/B/C", {"t": "c" * 10})]
    kept, cuts = cut_tree(rows, 90)
    assert [path for path, _ in kept] == ["SG1/A"], kept
    assert cuts == [{"path": "SG2", "more": 2}], cuts


def test_cut_paths_are_reached_or_a_top_segment_and_add_up():
    rows = [(f"G{g}/F{f}/B{b}", {"t": "x" * 30}) for g in range(3) for f in range(30) for b in range(4)]
    kept, cuts = cut_tree(rows, 2_000)
    reached = _reached(kept)
    tops = {path.split("/", 1)[0] for path, _ in rows}
    assert all(entry["path"] in reached or entry["path"] in tops for entry in cuts), cuts
    assert len(cuts) <= CUT_LIMIT
    if len(cuts) < CUT_LIMIT:
        assert sum(entry["more"] for entry in cuts) == len(rows) - len(kept)


def test_a_row_at_a_kept_path_does_not_hide_the_rows_under_it():
    """Duplicate paths (two siblings of one name): a left-out row hides the rows under
    its path only when no row at that path was kept, and each row left out is counted."""
    kept, cuts = cut_tree([("A", {}), ("A", {"p": "z" * 80}), ("A/C", {})], 60)
    assert [path for path, _ in kept] == ["A", "A/C"], kept
    assert cuts == [{"path": "A", "more": 1}], cuts

    rows = [("S", {}), ("S/A", {"x": 1}), ("S/A", {"t": "q" * 300}), ("S/A/c", {})]
    kept, cuts = cut_tree(rows, 100)
    assert [path for path, _ in kept] == ["S", "S/A", "S/A/c"], kept
    assert cuts == [{"path": "S/A", "more": 1}], cuts


def test_a_row_is_shortened_when_it_and_its_path_overflow_the_allowance():
    """The row alone fits the allowance but with its path it does not: it is
    shortened, then fits, whether it is the first row or not."""
    allowance, path = 24_000, "S/L"
    row = {"t": "x" * (allowance - 10)}
    assert _size(row) <= allowance < _size([path, row])
    for rows in ([("S", {}), (path, row)], [(path, row)]):
        kept, cuts = cut_tree(rows, allowance)
        assert [p for p, _ in kept] == [p for p, _ in rows], kept
        long = kept[-1][1]
        assert long["shortened"] == {"t": allowance - 10}, long.get("shortened")
        assert sum(_size([p, r]) for p, r in kept) <= allowance
        assert cuts == []


def test_paths_are_never_shortened():
    """Every key whose value is an instance path rhr prints (`path`, `paths`, a hit
    test's `stack` and `target`) keeps it whole; other long strings are shortened."""
    long = "G/" + "/".join("X" * 50 for _ in range(60))
    test = {"point": {"x": 5, "y": 5}, "stack": [long] * 4, "stackMore": 6, "target": long,
            "targetIsButton": True, "targetVisible": True}
    (kept,), more = cut([test], 1_000)
    assert more == 0
    assert kept == test, kept

    finding = {"check": "c", "severity": "warning", "paths": [long, long], "detail": "d" * 500}
    (kept,), _ = cut([finding], 1_000)
    assert kept["paths"] == [long, long]
    assert kept["detail"] == "d" * SHORT and kept["shortened"] == {"detail": 500}, kept

    node = {"path": long, "class": "TextLabel", "text": {"content": "t" * 500}}
    (pair,), _ = cut_tree([(long, node)], 1_000)
    assert pair[0] == long and pair[1]["path"] == long
    assert pair[1]["text"]["content"] == "t" * SHORT and pair[1]["shortened"] == {"text.content": 500}


def test_size_counts_utf16_units():
    """Claude Code cuts output by a JS string's length: an emoji outside the BMP is two
    units there."""
    assert _size({"t": "ab"}) == len('{"t":"ab"}') + 1
    assert _size({"t": "é"}) == len('{"t":"é"}') + 1
    assert _size({"t": "\U0001F600"}) == len('{"t":""}') + 2 + 1
    assert _size({"t": "\U0001F600" * 100}) == len('{"t":""}') + 200 + 1
    rows = [{"t": "\U0001F600" * 10} for _ in range(10)]
    kept, more = cut(rows, 10 * (len('{"t":""}') + 20 + 1))
    assert (len(kept), more) == (10, 0)
    kept, more = cut(rows, 10 * (len('{"t":""}') + 10 + 1))
    assert len(kept) < 10 and more == 10 - len(kept)


def test_a_pair_costs_what_it_serializes_to():
    """cut_tree fits each (path, row) by the size of the pair `[path, row]` as JSON:
    an allowance of exactly the rows' total keeps them all, one less leaves one out."""
    rows = [("Gui", {"a": 1}), ("Gui/Kén\U0001F600", {"t": "\U0001F600 x"}), ("Gui/Plain", {"t": "y" * 30})]
    total = sum(_size([path, row]) for path, row in rows)
    kept, cuts = cut_tree(rows, total)
    assert kept == rows and cuts == [], (kept, cuts)
    kept, cuts = cut_tree(rows, total - 1)
    assert len(kept) == 2 and sum(entry["more"] for entry in cuts) == 1, (kept, cuts)


def test_shortened_names_fields_by_their_dotted_path():
    row = {"a": {"b": "w" * 300}, "list": ["q" * 250, "ok"]}
    short = _shortened(row)
    assert short["shortened"] == {"a.b": 300, "list.0": 250}, short["shortened"]
    assert json.loads(json.dumps(short))["list"][1] == "ok"


def main() -> int:
    failed = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"  ok   {name}")
            except AssertionError as exc:
                failed += 1
                print(f"  FAIL {name}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
