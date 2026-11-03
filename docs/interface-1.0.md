# The 1.0 interface: review

What RHR promises from 1.0 on, and what changes before then. After 1.0, anything
listed as **contract** here changes only in a major version; everything else may change
in any release. Status: **decided 2026-09-27** (proposed 2026-09-26); the changes
shipped in 1.0.0rc1 (see the CHANGELOG), browser items (`RHR_BROWSER`, `setup
--browser`, the browser in reports) with RHR's own browser client.

Taken from the code as of v0.7.0 (argparse, `rhr.schema.VERSIONS`, real outputs on the
test fixtures), so "Now" and "Today" below mean v0.7.0. tests/test_contract.py holds
the interface as it is.

## Rules for the whole interface

1. **JSON is the contract; pictures and stderr are not.** A PNG may change in any
   minor version to get closer to Studio. Text on stderr is for people and may change
   any time. Every fact an agent needs (fallbacks, missing assets, particles drawn,
   which browser drew it) is also available as JSON.
2. **Two kinds of command.** *Data* commands (`layout`, `check`, `hitmap`,
   `scene-dump`, `compare`) print one JSON document to stdout, or write it with
   `--out`. *Picture* commands (`ui`, `scene`, `preview`) print the PNG's path on
   stdout; with `--json` they print a JSON report instead (the path, the size, the
   notes, the browser used, the camera). Today `compare` prints text unless `--json`
   is given, and picture commands have no JSON report at all.
3. **Exit codes:** 0 success; 1 only from `check`, meaning error-class findings; 2 the
   command failed (bad arguments, unreadable file, render error). Today three internal
   error paths in the UI commands return 1, which an agent would read as "check found
   errors"; they become 2. **Decided 2026-09-28:** a UI command with no UI to draw
   exits 2 with the reason and a hint (never 0 with an empty document).
4. **JSON style:** camelCase keys everywhere, every document stamped
   `"schema": "rhr.<kind>/<n>"`, adding a field never changes `<n>`, renaming or
   removing one does. Today `compare` uses snake_case (`changed_pct`, `diff_bbox`):
   renamed, so it becomes `rhr.compare/2`.
5. **Paths:** one format everywhere, `Model/Child/Grandchild`, the same in `layout`,
   `hitmap`, `scene-dump` and `--focus` (checked: it already is). Contract.
6. **Inputs** (added 2026-09-27, additive): wherever a command takes a file it also
   takes a Roblox asset id, `rbxassetid://<id>`, or a Creator Store / library /
   catalog / game link, when no file of that name exists (rhr.remote). The asset is
   downloaded into the cache (`models` area) and used as a file; default outputs are
   named after the id.
7. **Units:** UI rects in pixels `{x, y, w, h}` from the viewport's top-left; 3D
   positions and sizes in studs as `[x, y, z]`, orientations in degrees. Contract.

## Commands

| Now | Proposal | Why |
|---|---|---|
| `render` (UI to PNG) | **Decided:** renamed to `ui` (default output `<stem>-ui.png`) | `render` sounds like "draw anything", but it draws only the ScreenGuis. `ui` / `scene` / `preview` says what each draws. No alias: few users before 1.0, and the upgrade note covers it. |
| `scene` (3D to PNG) | keep | |
| `preview` (3D + UI) | keep | The one to reach for when unsure; docs/AGENTS.md says so. |
| `layout` | keep | |
| `layout --rich` | keep; fix its help text (it says "Task 2.1") | |
| `check` | keep | |
| `hitmap` | keep | |
| `scene-dump` | keep | |
| `compare` | keep; JSON by default (rule 2), `--json` becomes a hidden no-op for one release | |
| `fetch` | keep | |
| `setup` | keep, now optional: pre-downloads Lune, Rojo and, with `--browser`, the pinned browser (for CI and offline machines) | No longer a required step. |
| `doctor` | keep; names the browser RHR would use | |
| `cache` | keep | |
| `browser start/status/stop` | keep as advanced | The warm worker starts by itself; this is for scripts that want control. |
| new: `inspect` (2026-09-27) | JSON `rhr.inspect/1`: kind, instances, classCounts, roots, scripts (path, className, lines, bytes, disabled), assets (images, meshes, sounds, animations: ids), findings (check, severity, path, line, detail), findingCounts, scriptsTotal (count, lines), assetCounts, moreFindings, moreScripts, moreRoots (all three 0 with `--all`, which carries scriptsTotal and assetCounts too) | A data command: `--out`; exit 0 whatever it finds (findings are reasons to look, not verdicts). |
| new: `icons` (2026-09-27) | square transparent PNGs of models, one per file, folder entry or asset id; paths on stdout | Flags: `--out-dir`, `--size`, `--view`, `--margin`, `--fov`, `--background`, `--no-shadows`, `--no-effects`, `--offline`. Exit 2 if any failed. |
| new: `view` (2026-09-27) | the 3D world in a local page to move around in; prints the page's address on stdout, serves until stopped, redraws when the source changes | For people: "have a look" without Studio. Flags: `--focus`, `--view`, `--no-shadows`, `--flat-materials`, `--no-effects`, `--no-open`, `--port`, `--offline`. |
| new input: stories (2026-09-28) | `ui`, `layout`, `check`, `hitmap` take a `*.story.luau` in a Rojo project; documents name it `<Name>.story.json` | Experimental in 1.0 (decided 2026-09-28): its limits may narrow, its outputs are the same documents as for a file. |
| new flag: `--story-time T` (2026-10-26) | `ui`, `layout`, `check`, `hitmap`, `preview` save a story T seconds in (0 to 60), not once it has settled; an error for anything that is not a story | Tweens play in stories; this picks the moment, as `--effect-time` does for effects. `--at` and `--time` were taken. |
| `ir` | keep, but **not contract**: its JSON may change in any release | It is RHR's internal format; agents should use `scene-dump`/`layout`. |
| `particles` (contact sheet) | **Decided:** removed | A calibration tool; `--effect-time` covers "show another moment". Its checks in tests/test_particles.py now run through `rhr scene`. |

## Flags to remove or change

- **Remove hidden leftovers:** `scene --shadows`, `preview --shadows` (on by
  default), `scene --coverage` (a no-op), `preview --time` (old name of
  `--effect-time`), `fetch --use-studio-login` (the default), `particles --burst`.
- **`--ir PATH`** (on `render`, `layout`, `hitmap`, `scene`, `scene-dump`, `preview`,
  `particles`): **Decided:** removed. It saves the internal IR next to the output, a
  debugging aid; `rhr ir` does the same, and the IR is not contract.
- **`--texture-dir`, `--mesh-dir`**: keep working (the tests use them) but hide from
  `--help` and leave out of the contract. They are test hooks.
- **`--no-effects`**: leaves out only particles today; make it leave out Beams and
  Trails too, as its name says.
- **`--offline`**: stays on the commands that download before drawing (`ui`,
  `scene`, `preview`). The data commands never download, so they do not need it.
- **`render --dump-layout`**: keep (one run gives the picture and the numbers).
- **Defaults kept as contract:** `--viewport 1920x1080` (Phase 2), `--topbar-height
  58`, shadows on, effects on at their fullest moment, `--seed 0`.

## Check severities (decided 2026-09-28)

`error` (exit 1), `warning`, and `info`: patterns that are often intended
(`duplicate-zindex`, `invisible-content`, `child-outside-clip`, `max-visible-graphemes`,
an off-screen panel, contrast between 1.5:1 and 3:1), left out unless
`--min-severity info`. The check ids are listed in `rhr.checks` and are contract;
new checks are additive. `--ignore <id>`, `--baseline <json>` and the `RhrIgnore`
attribute leave findings out; stderr says how many and why.

## JSON outputs

| Schema | Today | Proposal |
|---|---|---|
| `rhr.layout/1` | `{viewport, rects: {path: {x,y,w,h}}, moreRects, cut}` | keep |
| `rhr.layout-rich/1` | `{model, viewport, nodes: [{path, class, rect, zIndex, paintOrder, visible, clipsDescendants, background, gradient, strokes, ..., shortened}], moreNodes, cut}` | keep |
| `rhr.check/1` | `{model, findings: [{check, severity, path(s), detail}], findingCounts, moreFindings}` | keep; list every `check` id in docs/AGENTS.md as contract (new checks may be added) |
| `rhr.hitmap/1` | `{model, viewport, panes, nodes, hitTests, moreNodes, moreHitTests, cut}` | keep |
| `rhr.scene-dump/1` | `{source, bounds, parts, cameras, lights, beams, trails, terrain, lighting, sky, atmosphere, fallbacks, unsupportedVisualClasses, experimental, ...}` | keep, `experimental` included: it flags what is drawn with less checking (Atmosphere, post effects, local lights, decals; materials without Studio). The first draft of this review wrongly called it always empty. |
| `rhr.compare/1` | snake_case keys | `rhr.compare/2`, camelCase |
| `rhr.browser/1` | `{running}` | keep; add the browser used |
| new: `rhr.render/1` | none | the `--json` report of `ui`, `scene`, `preview` (rule 2): `{command, source, out, size, notes}`, plus `screens` (`ui`, `preview`) and `camera {position, lookDirection, fieldOfView}`, `fallbacks`, `materialFallbacks`, `unsupportedVisualClasses`, `experimental`, `missingAssets` and `moreMissingAssets` (`ui`, `scene`, `preview`; a UI image's row adds `reason`, `rect`, and `hint` where RHR can say; `view` with `scene --views`) |
| new: `rhr.render/1` `views` (Phase 3) | none | `scene --views`: `views: [{view, out, camera}]`; `out` and `camera` stay the first view's |
| new: `rhr.batch/1` (Phase 3) | none | `rhr batch`: `{results: [{command, exitCode, stdout, stderr}]}`; `stdout` the parsed document when it is JSON, else the text |
| `rhr.ir/1` | internal format | not contract |

**Shape tests** (tests/test_contract.py, snapshot in tests/contract/interface.json):
every public command with its flags, choices and defaults; every JSON output's fields
and their types, from real runs on fixtures and a contract scene that fills every
list; the schema versions; and the exit codes. A removed or retyped field, a removed
or changed flag, a version bump or a changed exit code fails the suite; a new field
or flag is allowed and printed. After an intentional change:
`python tests/test_contract.py --update`, and review the snapshot's diff.

## Environment variables

| Variable | Proposal |
|---|---|
| `RHR_OFFLINE`, `RHR_CACHE_DIR`, `RHR_CACHE_LIMIT_MB`, `RHR_WEBGL`, `RHR_BROWSER_SANDBOX`, `RHR_PERSISTENT_BROWSER`, `RHR_BROWSER_IDLE_S`, `RHR_SERVER`, `RHR_SERVER_IDLE_S`, `RHR_SERVER_MEMORY_MB`, `RHR_SERVER_WAIT_S`, `RHR_PROFILE`, `RHR_STUDIO_DIR` | contract |
| `RHR_CHROME` | becomes **`RHR_BROWSER`** (any Chromium-family browser); `RHR_CHROME` still read for one release |
| new: `RHR_BROWSER_DOWNLOAD=0` | never download a browser; fail with a clear message instead |
| new: `RHR_TOOL_DOWNLOAD=0` | never download Lune or Rojo on first use (added with step 5); `RHR_OFFLINE=1` / `--offline` turns off every download, these two only one kind |
| new: `RHR_ROBLOX_API_KEY` (2026-09-27) | an Open Cloud API key (user key, `legacy-asset:manage`) used for assets the Studio login cannot get: machines without Studio. Contract |
| `RHR_ROBLOX_FONTS`, `RHR_SYSTEM_FONT_FALLBACK` | test switches: work, not contract |
| `RHR_SCENE_TUNE`, `RHR_EFFECTS_UNDER`, `RHR_TABLE_Y_SCALE*`, `RHR_TABLE_NODRAW_*` | calibration hooks: not contract; `RHR_TABLE_*` removed with the pinevex fork (2026-09-27) |
| `RHR_MCP_WORKER` | removed with the MCP server |
| `RHR_NEEDS_FRESH_PAGE` | not a variable: an internal error marker |

## Decisions (2026-09-27)

1. `render` renamed to `ui`.
2. `particles` removed.
3. `--ir` removed from the render and data commands.
4. `--json` report (`rhr.render/1`) added to `ui`, `scene` and `preview`.

## Phase 2 (2026-09-28): outputs an agent can use

- **Default screen 1920x1080**; `--device desktop|laptop|phone|android|tablet|console`
  on `ui`, `layout`, `check`, `hitmap`, `preview` (rhr.devices, measured in Studio's
  emulator); `check --devices all|NAMES` adds `devices` to each finding.
- **Bounded defaults** (the budget: 30,000 characters, below):
  `scene-dump` prints `rhr.scene-summary/1` (`--parts` for `rhr.scene-dump/1`, with
  `--path`, `--class`, `--limit` and `partsTotal`); `hitmap` lists visible elements
  (`--all`), stacks cut to four (`stackMore`), `--path`, `--at X,Y`; `inspect` lists
  flagged scripts and 25 ids per asset kind (`scriptsTotal`, `assetCounts`, also with `--all`;
  since 2026-11-02 also cut to fit, below);
  `--path` on `layout`, `check`, `hitmap` and `scene-dump`, with the spaces and slashes
  at its ends dropped (`Gui/Shop/` and `/Gui/Shop` name `Gui/Shop`; an empty one is
  refused).
- **Pictures**: `ui --crop PATH`, `--fit`, `--annotate` (report: `crop`, `scale`,
  `annotations[]` of `{n, path, class, rect}`), `--max-size PX` on `ui`, `scene`,
  `preview` (report: `scale`, `size` of the written PNG).
- **`rhr skill [--install DIR]`**: the agent skill.

## Before the freeze (2026-11-02): an output budget, and nothing to show

1.0 criteria 1 and 4 (docs/road-to-1.0.md).

- **The budget is 30,000 characters of JSON on stdout** (rhr.budget), where Claude Code
  cuts a tool's output, counted as Claude Code counts it: UTF-16 units, so an emoji is
  two. Every default output on a 100k-part place stays under it
  (tests/test_output_budget.py).
- **A list that grows with the file is cut on stdout only.** `--all` prints the whole
  document. On `layout`, `check`, `hitmap` and `inspect`, `--out` writes the default
  document uncut: every rect, node and finding on `layout` and `check`, every visible
  element on `hitmap`, and on `inspect` every finding, the flagged scripts, 25 ids per
  asset kind and every root. `--all` also adds what the default leaves out by design: hidden elements
  on `hitmap`, every script and asset id on `inspect`. On `ui`, `scene` and `preview`,
  `--out` is the PNG, and only `--all` lists every missing asset (`ui --dump-layout`
  writes every rect). stderr says what was left out and how to get it. Each cut
  document counts the rows it left out, exactly:
  - `layout`: rects nearest the top of the tree first, so a kept rect's parent is kept;
    `moreRects`, and `cut: [{path, more}]` for `--path`: each rect left out is counted
    under the deepest of its own path and its ancestor paths that the kept rects reach
    (a kept rect's path, or an ancestor of one), or under its first path segment where
    they reach none; the 20 paths with the most, most first. `layout --rich`:
    `moreNodes` and `cut`, where that path is the nearest kept ancestor.
  - `check`: at most 10 findings of each check, the most severe first, so one kind
    cannot crowd out the rest; `moreFindings`, and `findingCounts` by check id over
    every finding. The exit code counts every finding. `--baseline` refuses stdout that
    was cut: write the baseline with `rhr check <target> --out before.json`.
  - `hitmap`: nodes nearest the top first, and the hit tests at their centres;
    `moreNodes`, `moreHitTests` (every probe left out, of the kept nodes or not), and
    `cut` as on `layout`, where only the interactive elements are rows, so a path in it
    is the container the kept ones share (1,000 cards of 2 buttons: `.../Scroll`). stderr
    counts every node and probe point (`hitmap N interactive nodes, M probe points`)
    and says of each list that was cut how much stdout kept. `--all` also lists hidden
    elements, as before.
  - `inspect`: at most 10 findings of each check, as on `check` (`findingCounts`,
    `moreFindings`), the flagged scripts that fit, those with a finding shown first
    (`moreScripts`), and the first 40 roots (`moreRoots`). `classCounts` is not cut.
  - `ui`, `scene`, `preview --json`: the first 40 `missingAssets`;
    `moreMissingAssets`.
  - A row too long for the whole budget on its own (a label of 30,000 characters) is
    kept, not dropped: each string in it over 200 characters, but its `path`, `paths`,
    `stack` and `target` (the instance paths `--path` takes back), is cut to 200, and
    `shortened` maps each such field to its full length (`{"text.content": 30000}`). A
    row that does not fit what is left is skipped, and the rows after it still get
    their turn; on a tree, the rows under it are skipped with it, unless another row at
    its path was kept (two siblings of one name), when they still get their turn.
- **Not cut:** hitmap `panes` and ui `screens` (one per ScreenGui), `ui --annotate`
  entries, `scene-dump --parts` (asked for by name), any command with `--all`, and
  `rhr batch` (the sum of its commands).
- **`--all` no longer stands for `--all-guis`** on `ui`, `preview`, `layout` and
  `check`: argparse took the prefix for the only flag it matched, and `--all` is now a
  flag of its own there.
- **Nothing to show exits 2** (rule 3), with the reason on stderr: `layout`, `check` or
  `hitmap` with a `--path` that names no element; `check --path` over only hidden UI
  (`only hidden UI under {path} ({n}): check skips hidden UI, and --show {path} checks
  it as shown`); `hitmap --path` over only hidden elements (they take no clicks; `--all`
  lists them); `scene-dump` of a file with no parts, terrain, sky, atmosphere, lights or
  effects, in the world or in storage, where terrain counts only when its voxels
  (SmoothGrid) were read and are not empty (a Terrain the file holds no SmoothGrid for
  is empty), and a file whose only Terrain could not be read says so and why
  (`no 3D world to show: the file holds only Terrain, and its voxels (SmoothGrid) could
  not be read: ...`); and a story that builds no UI that draws, on every command: one
  that builds nothing, only layouts or Folders (`the story built only Folder,
  UIListLayout, which draw nothing alone`), or only hidden elements (`every GuiObject
  the story built is hidden (Visible = false): ...`, at most 5). A story captured while
  a timer was still waiting says so, with when the next is due, and names
  `--story-time`. tests/test_nothing_to_show.py runs
  every command on each kind of input (UI only, 3D only, an empty Model, scripts only,
  Rojo projects with only code or a missing `$path`, cached and uncached asset ids):
  each one shows something or exits 2 with a reason. `hitmap` without `--path` on a UI
  where nothing takes a click exits 0: its `panes` say what is there, and an empty
  `nodes` is the answer, as a clean `check` is.
