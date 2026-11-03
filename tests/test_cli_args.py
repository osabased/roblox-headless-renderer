#!/usr/bin/env python3
"""A vector whose first coordinate is negative is taken as a value, on every Python.

Before Python 3.13, argparse read `--camera -10,5,3` as two options and failed; CI's
Python 3.12 caught it in tests/test_scene_sun_rays.py. `rhr` joins such values to
their option first.

Every command's `--path` is read the same way: its spaces and slashes at the ends are
dropped, and one `_under` (rhr.hitmap) says what is under it.

    python tests/test_cli_args.py
"""

from __future__ import annotations

import argparse


def main() -> int:
    from rhr.cli import _join_negative_lists, build_parser

    parser = build_parser()
    for command in ("scene", "preview"):
        args = parser.parse_args(_join_negative_lists(
            [command, "place.rbxl", "--camera", "-10,5,3", "--look-at", "-47.5,132.1,-31.2", "--seed", "-3"]))
        assert (args.camera, args.look_at, args.seed) == ((-10, 5, 3), (-47.5, 132.1, -31.2), -3), args
        print(f"  ok   {command}: --camera {args.camera}, --look-at {args.look_at}")

    # Every --path is read once, the way rhr prints paths: no spaces or slashes at its
    # ends, so `Gui/Shop/` filters the same elements its guard found.
    commands = {name: sub for action in parser._actions if isinstance(action, argparse._SubParsersAction)
                for name, sub in action.choices.items()}
    with_path = sorted(name for name, sub in commands.items()
                       if any("--path" in action.option_strings for action in sub._actions))
    assert {"layout", "check", "hitmap", "scene-dump"} <= set(with_path), with_path
    for command in with_path:
        for text in ("Gui/Shop/", "/Gui/Shop", " Gui/Shop "):
            args = parser.parse_args([command, "x.rbxmx", "--path", text])
            assert args.path == "Gui/Shop", (command, text, args.path)
        try:
            parser.parse_args([command, "x.rbxmx", "--path", " / "])
        except SystemExit:
            pass
        else:
            raise AssertionError(f"{command} --path ' / ' was accepted")
        print(f"  ok   {command}: --path is read without the slashes and spaces at its ends")

    from rhr import cli, hitmap, scene_dump
    assert cli._under is hitmap._under is scene_dump._under, "one _under"
    return 0


def test_main():
    from _harness import run_main

    run_main(main)


if __name__ == "__main__":
    raise SystemExit(main())
