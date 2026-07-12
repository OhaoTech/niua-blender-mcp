# Code-mode token win — measured on the real benchmark

**Date:** 2026-07-12 · **Skill:** `make_game_ready` (the finisher, ported onto the SDK) · **Assets:** the 5 real generator fixtures · **Runner:** `scripts/run_skill.py`

## Headline

Running one finishing skill in **code mode** — the skill emits one script that drives ~46–51 tool calls in the runner, and only its final summary would return to an agent's context — versus **tool-by-tool**, where every call's arguments and full result flow into context:

| framing | tool-by-tool tokens | code-mode tokens | ratio |
|---|---|---|---|
| **per asset** (pessimistic: SDK re-read every asset) | 16.3k–25.8k | ~11.2k | **1.5×–2.3×** |
| **per 5-asset batch** (realistic: SDK read once/session) | 92.7k | 12.2k | **7.6×** |
| per 5 batches (25 assets, one session) | 463k | 16.9k | **27.5×** |
| per 100 batches (500 assets, one session) | 9.27M | 128k | **72×** |

(Code-mode per session = the SDK read once (10,992 tokens for the 8 touched domain modules) + one ~230-token summary per asset. As the session finishes more assets, tool-by-tool cost recurs on every asset while the SDK read stays paid-once, so the ratio keeps climbing.)

Readiness is **byte-identical** to the objective benchmark's agent baseline (real_character 0.76, real_character_light 0.80, real_creature 0.80, real_multipart 0.60, real_prop 0.64), confirming the run measured the exact same finishing behavior — this is a token measurement of the identical pass, not a different one.

## Per-asset detail

| asset | tool calls | tool-by-tool tokens | code-mode tokens | ratio | readiness |
|---|---|---|---|---|---|
| real_character | 49 | 17,546 | 11,221 | 1.6× | 0.76 |
| real_character_light | 46 | 16,363 | 11,218 | 1.5× | 0.80 |
| real_creature | 46 | 16,311 | 11,220 | 1.5× | 0.80 |
| real_multipart | 51 | 25,809 | 11,253 | 2.3× | 0.60 |
| real_prop | 46 | 16,643 | 11,222 | 1.5× | 0.64 |

## The mechanism, and why the per-asset ratio understates it

The per-asset code-mode cost is **dominated by a single fixed 10,992-token item: reading the 8 touched SDK domain modules.** The part that actually varies per asset — the **summary returned to context — is ~230 tokens** (226–261 across the five assets; the *variance* between assets is only ~35 tokens, which is why the per-asset code-mode total barely moves). That is the thesis confirmed: the 40+ intermediate results that cost 14–25k tokens tool-by-tool (readiness dicts, quality dicts, scene diffs, preservation reads) **never enter context in code mode** — they stay in the runner. The agent pays for the SDK once and a ~230-token summary per asset instead of ~16–26k of intermediates.

So the honest reading is:
- **1.5×–2.3× is a pessimistic floor** — it charges the once-per-session SDK read to every single asset, which no real session does.
- **7.6× is the realistic single-batch number** — an agent reads the SDK once (10,992 tokens), then finishes 5 assets at ~230 tokens of summary each; the fixed cost amortizes immediately.
- **The ratio keeps climbing as the session does more work**, because tool-by-tool cost recurs on every asset while the code-mode SDK read is paid once (27× at 25 assets, 72× at 500).

This corrects the plan's `≥5×` expectation, which was written per-asset: per-asset it is **not** met (1.5–2.3×), because that framing mis-charges the SDK read; per-session amortized it is comfortably exceeded (7.6× and up). The mechanism the number was meant to prove — intermediates elided from context — is confirmed emphatically: ~16–26k tokens of intermediates per asset become a ~230-token summary.

## This is a lower bound

The finisher's intermediate results are **metric dicts, not renders.** A skill that *observes visually* (calls `feedback.capture` / preservation image reads, tens of thousands of tokens of base64 per call) would show a far larger gap, because those are exactly the payloads code mode keeps out of context. And the code-mode figure here is itself conservative in two more ways: (1) it charges the *entire* touched domain modules, whereas an agent needs only the functions it calls; (2) in a true code sandbox the SDK executes as an imported library and never enters context at all — the model writes calls from the compact per-domain listing. So the real product win is larger than any number in the table above; these are floors.

## Method (stated plainly, no false precision)

- **Approximation:** tokens ≈ `ceil(chars / 4)` (the standard rough estimate); raw utf-8 byte counts are recorded alongside in `skill-run.json`. Both are labelled approximate — this is not a tokenizer.
- **Tool-by-tool** charges, for each of the ~46–51 calls, `approx(arguments) + approx(full result)`, plus the `input_schema` of each distinct tool held (once). This is what an agent's context accretes when it calls tools one at a time.
- **Code-mode** charges the touched SDK domain modules' source read once, plus the single returned summary. Intermediates are not charged — they never reach context.
- **Amortized framings** hold the fixed SDK read constant across a session while letting the per-asset tool-by-tool cost and the ~230-token summary recur. One asymmetry to be honest about: the tool-by-tool sum recharges the distinct-tool schemas (~2.1k tokens) on every asset, whereas those are really held once per session too — so the multi-asset ratios are modestly softer than shown. It cuts the other way as well: tool-by-tool here charges only the 21 *used* schemas, not the ~300 an agent without tool-search holds continuously, which would push the ratio far higher. Net direction is right; treat the exact multipliers as approximate.
- Determinism: no LLM in this measurement; the finisher is deterministic, so the token figures are stable per asset.

Raw data: `/tmp/niua_skill_run/skill-run.json`.
