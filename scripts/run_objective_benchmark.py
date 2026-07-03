#!/usr/bin/env python3
"""Objective benchmark runner (deterministic, no LLM judge). PRIMARY grade for this ruler.

Per item: run the input recipe from item.input.recipe, rename the freshly-created object to
'bench_<id>', feedback.capture_intake (do-no-harm baseline), run a FINISHER, then read
feedback.readiness + feedback.preservation and score with evals.objective_bench. Aggregate +
write {outdir}/objective-reading.json.

HONEST SCOPING (read this before trusting a number out of this script):
  baseline (default) : the finisher is a no-op. The reading is the INPUT-QUALITY of each
                        benchmark item's untouched intake mesh -- readiness + preservation of
                        geometry nobody has finished yet. This is a BASELINE PROBE. It does
                        NOT claim "the pipeline preserves form" -- there is no pipeline run in
                        this mode, only the raw recipe output.
  agent               : a real finisher callable is wired in via --finisher module:function;
                        it does the actual finishing work before scoring, so the reading is of
                        the FINISHED asset. This is the mode that can honestly support a claim
                        about a finishing pipeline.
Scoring is deterministic and judge-free in both modes -- no LLM reads any render or metric here.
The forced-damage acceptance (plan Task 5's A3) proves the preservation metric detects harm
regardless of mode; this script does not itself fabricate or claim that proof.

STARTUP REGISTRATION GUARD: every tool name this script or an item's recipe will call is
checked against build_router().specs() *before* any live bridge call is made, so a renamed or
mistyped tool (e.g. the nonexistent 'objects.rename') fails loudly and offline, not silently
mid-benchmark against a live Blender.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from niua_blender_mcp.bridge import BlenderBridge, BridgeError  # noqa: E402
from niua_blender_mcp.domains import build_router  # noqa: E402
from niua_blender_mcp.evals.benchmark import list_items, load_item  # noqa: E402
from niua_blender_mcp.evals.objective_bench import aggregate_objective, score_item_objective  # noqa: E402

# Fixed tools the runner itself calls; recipe tools are added dynamically in the guard.
_RUNNER_TOOLS = {
    "scene.info",
    "object.rename",
    "feedback.capture_intake",
    "feedback.readiness",
    "feedback.preservation",
}


def known_tools() -> set[str]:
    """Every tool name callable over the live bridge, by the same rule tests/test_parity.py
    uses server-side: a 'generated' (RNA passthrough) spec is actually invoked as
    capabilities.invoke; every other tier is invoked by its own command name."""
    return {
        "capabilities.invoke" if spec.tier == "generated" else spec.command
        for spec in build_router().specs()
    }


def assert_tools_registered(items: list[dict]) -> None:
    """Startup registration guard: fail LOUD + OFFLINE if the runner would call a missing tool.

    Runs before any bridge/socket connection is opened, so a rename or typo (e.g. the
    nonexistent 'objects.rename') is caught at startup, not discovered mid-benchmark against a
    live Blender process.
    """
    needed = set(_RUNNER_TOOLS)
    for item in items:
        for step in item["input"]["recipe"]:
            needed.add(step["tool"])
    missing = sorted(needed - known_tools())
    if missing:
        raise SystemExit(f"registration guard: tools not in build_router().specs(): {missing}")


def _build_input(bridge: BlenderBridge, item: dict, subject: str) -> None:
    """Run the item's creation recipe, then rename the freshly-created object to `subject`.

    The created object's name is derived from a before/after diff of the scene.info() object
    list -- robust to any recipe shape, including a recipe whose first step is a bare
    capabilities.invoke RNA primitive-add (e.g. organic_rock's ico-sphere) rather than
    scene.create_object. This never reads a nonexistent "active" key from scene.info().
    """
    before = {o["name"] for o in bridge.call("scene.info", {}).get("objects", [])}
    created: str | None = None
    for step in item["input"]["recipe"]:
        args = dict(step.get("args", {}))
        # The recipe's first step creates the object; every later step must target it. The
        # item.json recipes omit the object name (the old judged altimeter relied on the finish
        # agent to fill it in), so inject the created object's name into the subsequent steps.
        # `object` is a top-level param on both plain mutating tools and capabilities.invoke.
        if created is not None and "object" not in args:
            args["object"] = created
        bridge.call(step["tool"], args)
        if created is None:
            now = [o["name"] for o in bridge.call("scene.info", {}).get("objects", []) if o["name"] not in before]
            if now:
                created = now[-1]
    if created is None:
        raise RuntimeError(f"item {item['id']!r}: recipe created no new object")
    bridge.call("object.rename", {"object": created, "name": subject})


def _no_op_finisher(bridge: BlenderBridge, subject: str, item: dict) -> None:
    """BASELINE mode (default): do nothing.

    The reading that follows this finisher is the INPUT-QUALITY of the untouched intake mesh --
    it is a baseline probe, not a claim that any finishing pipeline preserves form. Plug a real
    finisher in with --mode agent --finisher module:function to score an actual finishing pass.
    """
    return None


def run_item(bridge: BlenderBridge, item: dict, finisher) -> dict:
    subject = f"bench_{item['id']}"
    _build_input(bridge, item, subject)
    intake = bridge.call("feedback.capture_intake", {"object": subject})
    finisher(bridge, subject, item)                      # real work in agent mode; no-op in baseline
    readiness = bridge.call("feedback.readiness", {"object": subject, "asset_class": item["asset_class"]})
    pres = bridge.call("feedback.preservation", {"object": subject})
    preservation_available = bool(intake.get("available")) and bool(pres.get("available"))
    return score_item_objective(
        item,
        readiness=readiness.get("readiness"),
        stage_pass_fraction=readiness.get("stage_pass_fraction_mean"),
        preservation=pres.get("preservation"),
        preservation_available=preservation_available,
    )


def _load_finisher(spec: str):
    module_name, _, func_name = spec.partition(":")
    if not module_name or not func_name:
        raise SystemExit(f"--finisher must be 'module:function', got {spec!r}")
    return getattr(importlib.import_module(module_name), func_name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Objective benchmark runner (deterministic, no LLM judge). Default --mode baseline "
            "is an input-quality probe, not a finishing-pipeline claim -- see module docstring."
        )
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--outdir", default="/tmp/niua_objective_run")
    ap.add_argument("--items", default="", help="comma-separated item ids (all if empty)")
    ap.add_argument("--mode", choices=["baseline", "agent"], default="baseline")
    ap.add_argument("--finisher", default="", help="agent mode only: 'module:function(bridge, subject, item)'")
    args = ap.parse_args(argv)

    if args.mode == "agent" and not args.finisher:
        ap.error("--mode agent requires --finisher module:function")

    ids = list_items()
    if args.items:
        wanted = set(args.items.split(","))
        ids = [i for i in ids if i in wanted]
    items = [load_item(i) for i in ids]

    assert_tools_registered(items)                       # loud, offline, before any bridge call
    finisher = _no_op_finisher if args.mode == "baseline" else _load_finisher(args.finisher)

    bridge = BlenderBridge(port=args.port, timeout=120.0)
    try:
        cards = [run_item(bridge, it, finisher) for it in items]
    except BridgeError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}}))
        return 1

    reading = aggregate_objective(cards)
    grade = "PRIMARY" if reading["valid"] else "INVALID"  # headless / unmeasured -> INVALID
    out = {
        "meta": {
            "grade": grade,
            "runner": "objective",
            "judge": None,
            "mode": args.mode,
            "finisher": args.finisher or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "items": cards,
        "reading": reading,
    }
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "objective-reading.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
