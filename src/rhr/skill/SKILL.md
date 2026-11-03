---
name: rhr
description: "Check or look at Roblox UI and 3D builds without Studio. Use after editing a ScreenGui, UI story, model, place or Rojo project: rhr finds UI mistakes (check), prints layout rects and click targets as JSON, and draws PNGs of screens and builds; also to vet a Creator Store model before inserting it."
---

# rhr: see Roblox content without Studio

`rhr` (roblox-headless-renderer) turns a Roblox file, Rojo project, UI story or asset
id into small JSON and, when you need to look, a PNG. Run it from the shell: UI
commands take about a second, 3D and stories a few. `rhr <command> --help` lists every
option; the full guide is docs/AGENTS.md in rhr's repository
(https://github.com/osabased/roblox-headless-renderer/blob/main/docs/AGENTS.md).

## Where the UI lives decides the target

- UI saved as files in a Rojo repo: the project folder or the file.
- UI built by code (React-lua, Fusion, ...): a story, `src/Shop.story.luau`.
- Code in Rojo, UI saved in Studio: the place file (`Game.rbxl`) or its place id.
- Screens code opens are saved closed: `--only StarterGui/Shop` draws one alone,
  `--show StarterGui/Shop` opens it over what is open.

UI is laid out on a 1920x1080 screen below Roblox's 58 px top bar, as in a running
game: `--device phone` for a phone, `--topbar-height 0` to match Studio's edit view.

## The loop

1. Edit.
2. `rhr check <target>` (exit 1 = an error finding; fix errors, then warnings).
   Before the first edit `rhr check <target> --out before.json`; after each,
   `rhr check <target> --baseline before.json` shows only what the edit added.
3. `rhr layout <target> --path <screen>`: rects as numbers; compare with what you meant.
4. Look only when needed, small: `rhr ui <target> --only <screen> --fit --max-size 800
   --out shot.png` (`--annotate --json` numbers the buttons).
5. Before done: `rhr check <target> --devices all` (phones, tablets, consoles).

3D: `rhr preview <target> --view iso --max-size 800 --out frame.png --json` draws the
world with its in-world UI and the screens over it (the one to use when unsure);
`rhr scene` takes the same options and draws the world alone (`--views iso,front,top`
for several sides on one build);
`rhr scene-dump <target>` summarises a place (`--path <model>` to drill in).
Clicks: `rhr hitmap <target> --at X,Y`. Free models: `rhr inspect <id>`.
Two renders: `rhr compare before.png after.png` tells a geometry change from a colour one.
Several commands in one call: `rhr batch check <target> + layout <target>` (one JSON).

## Stories

A story runs the project's code (never a story from an untrusted pull request outside
a sandbox), on story time, 1/60 s a frame. Its tweens play, and rhr saves the UI once
it has settled, at most 5 s in, or at `--story-time T`; stderr says which: `settled at
1.58 s of story time`, or `captured at the 5 s cap` naming what still moved. Sizes the
code reads (AbsoluteSize, TextBounds, AbsoluteContentSize) are laid out while it runs:
read them from a change signal or `task.defer`, not in the resumption that parented
the element, where they are zero.

## Rules

- Pass paths back exactly as rhr printed them (`Card[2]`, not `Card`).
- Exit 2 means it failed or had nothing to draw; stderr says why and what to try.
- A long list is cut to fit stdout (`moreRects`, `moreFindings`, ... count the rest;
  stderr says so): narrow with `--path`. On `layout`, `check`, `hitmap` and `inspect`,
  `--out file.json` writes the default document uncut; `--all` prints it uncut too,
  with hidden elements on `hitmap` and every script and asset id on `inspect`. On `ui`,
  `scene` and `preview`, `--out` is the PNG.
- Findings: `error` fix, `warning` weigh, `info` (`--min-severity info`) often intended.
  An `image-missing` warning is an image Roblox leaves blank too: use another. At
  `info` only rhr's picture leaves it out: tell whoever reviews the picture.
  `--ignore <check>` leaves a check out of one run; an `RhrIgnore` string attribute
  ("all", or check ids separated by commas) leaves an instance alone for good.
- `missingAssets`, `fallbacks` and `notes` in the JSON say what was not drawn exactly.
- Images and meshes download with the machine's Studio login; `--offline` draws
  without them. No Studio on the machine (cloud, CI): ask for an Open Cloud API key
  and set `RHR_ROBLOX_API_KEY` from secrets, never in a committed file.
