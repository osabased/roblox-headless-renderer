"""UI that code builds: run a story file and draw what it made.

`rhr ui Shop.story.luau` (and `layout`, `check`, `hitmap`): the story is a
ModuleScript in a Rojo project, in any of the usual forms: a function(target)
(Hoarcekat, UI Labs), a UI Labs table (react + reactRoblox, roact, fusion, vide, or a
generic render), a Flipbook table. RHR builds the project with Rojo, finds the story's
ModuleScript with `rojo sourcemap`, runs it in Lune with a copy of the Roblox side
(luau/story-runtime.luau: instances, events, the services UI code touches, require by
instance or relative path), and saves the UI it built as a model file, which the
command then reads like any other. Nothing about a UI library is special-cased: they
all end in Instance.new and property sets.

The story mounts where a game's own UI does in Play: in a default ScreenGui
(CoreUISafeInsets), below the top bar and inside the device's insets, so
`target.AbsoluteSize` is that area, its AbsolutePosition that area's corner (0, 0), and
`GuiService:GetGuiInset()` reads the top bar.
It reads the `--device`'s input and player settings as a Studio play-test on that
device does (desktop without one): UserInputService.PreferredInput and the
*Enabled flags, GuiService.ViewportDisplaySize, Roblox's default PreferredTextSize,
PreferredTransparency and ReducedMotionEnabled, and a TopbarInset that is the whole
top bar between the device's side insets (RHR draws none of Roblox's buttons there).

The story runs on story time, 1/60 s a frame: task.wait, delay, defer and cancel,
os.clock, tick and time follow it, so a timer fires on the frame it would at 60 fps.
After it mounts, once a frame between PreRender and Heartbeat, and before it is saved,
RHR lays the screen out as the render will (rhr.story_sizes) and the story reads the
result, with its change signals: AbsoluteSize, AbsolutePosition, TextBounds, a layout's
AbsoluteContentSize, a ScrollingFrame's AbsoluteCanvasSize and AbsoluteWindowSize.
RHR_STORY_SIZES=0 turns that off.

What does not carry over: a read in the same resumption that parented the element
comes before any layout and reads zero, as do the other layout reads (AbsoluteRotation,
a UIGridLayout's AbsoluteCellSize and AbsoluteCellCount) and elements outside the
story's screen; TextFits and an image's IsLoaded read true; the camera's ViewportSize
is the whole screen, where Studio leaves out a notch's side insets;
TextService:GetTextBoundsAsync and GetTextSize are rough estimates; tweens end at their
goal; the story's controls take their defaults; nothing is clicked.

A story is run again only when something it runs on changed (the project's files,
the screen, its insets and device, RHR's runtime and version, whether sizes are on):
`check` then `ui` of the same story runs it once. A story that builds something
different each run (random numbers, the date) keeps its first.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from rhr.paths import IR_DIR, PACKAGE

SUFFIXES = (".story.luau", ".story.lua")
TIMEOUT_S = 120


def is_story(path: Path) -> bool:
    return path.name.lower().endswith(SUFFIXES)


def story_name(path: Path) -> str:
    name = path.name
    for suffix in SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def find_project(story: Path) -> Path:
    """The default.project.json nearest above the story."""
    for folder in story.resolve().parents:
        candidate = folder / "default.project.json"
        if candidate.is_file():
            return candidate
    raise ValueError(f"{story} is not inside a Rojo project (no default.project.json above it): a story "
                     "runs in its project, where its require() calls lead")


def _same(a: Path, b: Path) -> bool:
    return str(a).casefold() == str(b).casefold() if __import__("os").name == "nt" else a == b


def module_path(project: Path, story: Path) -> tuple[list[str], dict[str, str]]:
    """The story's ModuleScript as names from the built file's root, and every script's
    full name -> file (to point errors at files)."""
    from rhr.procs import no_window
    from rhr.tools import require

    rojo = require("rojo", "to run a story in its Rojo project")
    proc = subprocess.run([rojo, "sourcemap", "--absolute", str(project)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=project.parent, stdin=subprocess.DEVNULL,
                          timeout=TIMEOUT_S, **no_window())
    if proc.returncode != 0:
        raise RuntimeError(f"rojo sourcemap failed for {project}:\n{(proc.stderr or proc.stdout).strip()}")
    tree = json.loads(proc.stdout or "null")
    if not tree:
        raise ValueError(f"{project} has no scripts, so no story to run")
    place = tree.get("className") == "DataModel"
    target = story.resolve()
    found: list[str] | None = None
    files: dict[str, str] = {}

    def walk(node: dict, names: list[str]) -> None:
        nonlocal found
        full = ".".join(names)
        for file in node.get("filePaths") or []:
            # (On Windows Rojo writes verbatim paths: //?/C:/...)
            path = Path(re.sub(r"^(?://|\\\\)\?[/\\]", "", file))
            if path.suffix in (".luau", ".lua"):
                files[full] = str(path)
            if found is None and _same(path.resolve(), target):
                found = list(names)
        for child in node.get("children") or []:
            walk(child, [*names, child["name"]])

    # A place's scripts hang from its services; a model's root is kept in ReplicatedStorage.
    walk(tree, [] if place else ["ReplicatedStorage", tree["name"]])
    if found is None:
        raise ValueError(f"{story} is not part of the Rojo project {project} (rojo sourcemap does not list it)")
    return found, files


def _point_at_files(text: str, files: dict[str, str], root: Path) -> str:
    """Instance full names in an error -> the files they come from."""
    for full in sorted(files, key=len, reverse=True):
        if full and full in text:
            try:
                shown = str(Path(files[full]).relative_to(root))
            except ValueError:
                shown = files[full]
            text = re.sub(rf"(?<![\w.]){re.escape(full)}(?![\w])", shown.replace("\\", "\\\\"), text)
    return text


def _tidy(text: str) -> str:
    """The error and the lines of the project's own files it went through; not Lune's
    internals or the runtime's."""
    message: list[str] = []
    frames: list[str] = []
    for line in text.splitlines():
        frame = re.search(r'\[string "([^"]+)"\]:(\d+)(?::\s*(.+))?', line)
        if frame:
            if frame.group(3) and not message and not frames:  # `[string "x"]:3: the error`
                message.append(frame.group(3))
            where = f"  at {frame.group(1)}:{frame.group(2)}"
            if where not in frames:
                frames.append(where)
        elif line.strip() and not line.startswith((" ", "\t", "stack traceback")) and not frames and not re.match(
                r"^(?:__mlua|\[C\]|[A-Za-z]:\\)", line):
            message.append(re.sub(r"^(?:runtime|syntax) error: ", "", line))
    return "\n".join(message + frames) or text


def build(story: Path, *, width: int = 1920, height: int = 1080, topbar_height: float | None = None,
          log=None) -> Path:
    """Run `story` on a `width` x `height` screen (the `--device` one's insets and
    input, a `topbar_height` top bar, 58 by default) and return the model file with
    the UI it built."""
    import rhr
    from rhr import devices, insets, rojo, story_sizes
    from rhr.ir import lune_executable

    from rhr.profile import add, phase

    project = find_project(story)
    name = story_name(story)
    topbar = insets.REFERENCE_TOPBAR_HEIGHT if topbar_height is None else float(topbar_height)
    core = insets.resolve("CoreUISafeInsets", topbar)
    device = devices.current()
    area = json.dumps({"insets": [core.left, core.top, core.right, core.bottom], "topbar": topbar,
                       "input": device.preferred_input, "displaySize": device.display_size})
    sizes = "on" if story_sizes.enabled() else "off"
    key = hashlib.sha1(f"{story.resolve()}|{width}x{height}|{area}|{sizes}".encode("utf-8")).hexdigest()[:12]
    # One folder per story and screen, the file named after the story: documents name
    # their source by this file's name ("model": "Shop.story.json").
    out = IR_DIR / "stories" / key / f"{name}.story.rbxm"
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = out.with_name(out.name + ".inputs")
    with phase("story: inputs check"):
        runtime = (PACKAGE / "luau" / "story-runtime.luau").stat()
        inputs = json.dumps([str(story.resolve()), rojo.inputs_digest(project), width, height, area, sizes,
                             runtime.st_size, runtime.st_mtime_ns, str(lune_executable()), rhr.__version__])
    try:
        kept = json.loads(stamp.read_text(encoding="utf-8"))
        if out.is_file() and kept.get("inputs") == inputs:
            if log is not None:
                log(f"story  {story.name}: unchanged since its last run, reused the UI it built "
                    f"({kept.get('count', '?')} instances)")
                for line in kept.get("problems", [])[:10]:
                    log(f"story  {line}")
            return out
    except (OSError, ValueError, AttributeError):
        pass
    stamp.unlink(missing_ok=True)
    with phase("story: rojo build"):
        built = rojo.build(project, IR_DIR)
    with phase("story: rojo sourcemap"):
        names, files = module_path(project, story)
    passes = story_sizes.Passes(core.rect(width, height)) if sizes == "on" else None
    with phase("story: run (Lune)"):
        proc, stats = story_sizes.run(
            [lune_executable(), "run", str(PACKAGE / "luau" / "story-runtime.luau"), str(built), json.dumps(names),
             str(out), str(width), str(height), name, area, sizes], passes, timeout=TIMEOUT_S)
    if passes is not None:
        add("story: layout passes (Python)", passes.seconds)
        add("story: layout passes (round trip)", float(stats.get("seconds") or 0))
    problems = _tidy(_point_at_files(proc.stderr.strip(), files, project.parent))
    if passes is not None and passes.problems:
        problems = "\n".join([*passes.problems, *filter(None, [problems])])
    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(f"the story {story.name} failed:\n{problems or proc.stdout.strip() or 'no output'}")
    count = proc.stdout.strip().rpartition(" ")[2]
    stamp.write_text(json.dumps({"inputs": inputs, "count": count, "problems": problems.splitlines()}),
                     encoding="utf-8")
    if log is not None:
        log(f"story  {story.name}: ran it in its Rojo project, {count} instances built" + (
            f", {passes.count} layout passes ({passes.skipped} on an unchanged screen) in {passes.seconds:.2f} s"
            if passes is not None else ""))
        for line in problems.splitlines()[:10]:
            log(f"story  {line}")
    return out
