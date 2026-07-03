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
    "object.delete",
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
        inp = item["input"]
        if inp.get("asset"):
            # asset items import a fixture and consolidate multi-part meshes via object.join
            needed.update({"io.import", "capabilities.invoke"})
            continue
        for step in inp["recipe"]:
            needed.add(step["tool"])
    missing = sorted(needed - known_tools())
    if missing:
        raise SystemExit(f"registration guard: tools not in build_router().specs(): {missing}")


def _build_input(bridge: BlenderBridge, item: dict, subject: str) -> None:
    """Build the item's intake object and rename it to `subject`.

    Two input shapes are supported. ASSET items (the real-generator benchmark) import a generic
    .glb/.obj fixture; a multi-part asset is consolidated into one object via object.join so the
    single-object eyes (capture_intake/readiness/preservation) can measure it. RECIPE items (legacy
    synthetic) run a create-recipe, injecting the created object's name into subsequent steps. In
    both cases the created object is discovered by a before/after scene.info diff (never a
    nonexistent "active" key) and renamed to `subject`.
    """
    inp = item["input"]
    before = {o["name"] for o in bridge.call("scene.info", {}).get("objects", [])}

    if inp.get("asset"):
        path = inp.get("asset_path") or inp["asset"]
        bridge.call("io.import", {"path": path})
        parts = [o["name"] for o in bridge.call("scene.info", {}).get("objects", [])
                 if o["name"] not in before and o.get("type") == "MESH"]
        if not parts:
            raise RuntimeError(f"item {item['id']!r}: asset {path!r} imported no mesh")
        if len(parts) > 1:
            # Consolidate a multi-part asset into one object: parts[0] active, all parts selected, join.
            bridge.call("capabilities.invoke", {"idname": "object.join", "object": parts[0], "select": json.dumps(parts)})
        created = parts[0]
        bridge.call("object.rename", {"object": created, "name": subject})
        return

    created: str | None = None
    for step in inp["recipe"]:
        args = dict(step.get("args", {}))
        # Recipe step 1 creates the object; later steps must target it (recipes omit the name).
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


def _clear_meshes(bridge: BlenderBridge) -> None:
    """Delete all MESH objects so each item is built + scored in a clean, deterministic scene.

    Without this, bench_* objects accumulate across items/runs and the before/after create-diff
    (and the isolated silhouette framing) become order-dependent -- the source of run-to-run drift.
    """
    names = [o["name"] for o in bridge.call("scene.info", {}).get("objects", []) if o.get("type") == "MESH"]
    if names:
        # Use the dedicated object.delete tool (captures names, then bpy.data.objects.remove) --
        # NOT capabilities.invoke object.delete, whose viewport-feedback summary post-accesses the
        # just-removed object and raises "StructRNA of type Object has been removed".
        bridge.call("object.delete", {"objects": ",".join(names)})


def _safe(bridge: BlenderBridge, tool: str, payload: dict) -> dict | None:
    """Call a measurement tool; on timeout/error (dense real generator meshes routinely exceed the
    per-call limit on feedback.quality) return None so the item scores as UNMEASURED, not a crash."""
    try:
        return bridge.call(tool, payload)
    except BridgeError as exc:
        print(f"  [{payload.get('object')}] {tool} unavailable: {str(exc)[:70]}", file=sys.stderr)
        return None


def run_item(bridge: BlenderBridge, item: dict, finisher) -> dict:
    subject = f"bench_{item['id']}"
    _clear_meshes(bridge)
    try:
        _build_input(bridge, item, subject)
    except BridgeError as exc:
        print(f"  [{item['id']}] BUILD FAILED (import/join): {str(exc)[:70]}", file=sys.stderr)
        return score_item_objective(item, readiness=None, stage_pass_fraction=None,
                                    preservation=None, preservation_available=False)
    intake = _safe(bridge, "feedback.capture_intake", {"object": subject})
    finisher(bridge, subject, item)                      # real work in agent mode; no-op in baseline
    readiness = _safe(bridge, "feedback.readiness", {"object": subject, "asset_class": item["asset_class"]})
    pres = _safe(bridge, "feedback.preservation", {"object": subject})
    preservation_available = bool((intake or {}).get("available")) and bool((pres or {}).get("available"))
    return score_item_objective(
        item,
        readiness=(readiness or {}).get("readiness"),
        stage_pass_fraction=(readiness or {}).get("stage_pass_fraction_mean"),
        preservation=(pres or {}).get("preservation"),
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
