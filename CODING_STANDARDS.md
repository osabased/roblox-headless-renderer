# Coding standards

Three judgement calls a review of this repository checks every change against, beside
correctness. Each was missed at least once before review caught it. A review applies all
three to every hunk, and each finding names the rule it breaks.

## A loosened check is scoped

When a test compares RHR with a Studio recording less strictly than exactly (sorting,
comparing by name, skipping a row, widening a tolerance), the loosening names the cases
it covers and applies to those alone; every other case keeps the strict comparison. A
case that misses a timing tolerance is a finding about the model, and the tolerance stays.
The client recording's re-read is the pattern: it reads a missed value `PROBE_ERROR`
earlier and later (how far Studio rounds a probe's progress), only in that recording,
and a value that matches only there is noted, not passed silently.

Why: a loosening written for one case quietly stops checking every other one. b6d6f41
compared the callbacks on each step by name, in every recording, to cover three tweens
whose order it could not model, and that hid a wrong order in another case (LQ).
`in_order` in `tests/test_tween.py` now sorts only a consecutive LB, LT, TL triple.

## A claim about Roblox is cited and checked

A comment, doc line or commit message that says what Roblox does names the recording and
case that show it (`semantics.json: LQ1 to LQ4`), and a test fails if RHR stops doing
it. A claim that no rule fits a recording names each rule tried and the order it gave.
What RHR does differently from Roblox goes in `docs/known-approximations.md`.

Why: a claim reads as settled and stops the next person looking. b6d6f41 cited LQ and
said no queue kept the Tweens' way gives its order; trying that queue in d2fbe0f gave
exactly LQ's order. The `retire` comment in `src/rhr/luau/tween.luau` shows the form,
and d2fbe0f's message lists what each rule gave for LB, LT and TL.

## Comments say what the code does now

A change to behaviour rewrites every comment, doc line and test message that describes
the old behaviour. Before calling it done, search `src/`, `tests/` and `docs/` for the
old terms: the function, the case names, the rule it replaced.

Why: a stale comment is a wrong claim with no recording behind it. When d2fbe0f gave
legacy tweens Tweens' queue, three comments described the old order (`retire` and
`stepAll` in `tween.luau`, the callbacks check in `test_tween.py`), and all three were
rewritten with the code. The comment on clearing the story cache in `test_tween.py` said
a reused story logs none of what the checks read; it logs everything but its layout
passes, and the comment now says so.
