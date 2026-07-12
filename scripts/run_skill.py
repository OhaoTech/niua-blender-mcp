#!/usr/bin/env python3
"""Code-mode skill runner: run one skill on benchmark assets in a single pass, and measure
the token win vs tool-by-tool.

Each item: build the intake (reusing the benchmark's builders), run the skill through a
RecordingSession (which captures every SDK call + full result), then compute the token
accounting from those records. The skill's whole loop runs here in the runner; only its
summary would return to an agent's context — that is the code-mode win the accounting sizes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling: run_objective_benchmark

from niua_blender_mcp.bridge import BlenderBridge  # noqa: E402
from niua_blender_mcp.client import ToolSession, accounting, generate  # noqa: E402
from niua_blender_mcp.domains import build_router  # noqa: E402
from niua_blender_mcp.evals.benchmark import list_items, load_item  # noqa: E402
from niua_blender_mcp.finishing.skills import get_skill  # noqa: E402
from run_objective_benchmark import _build_input, _clear_meshes, assert_tools_registered  # noqa: E402


class RecordingSession(ToolSession):
    """A ToolSession that records {tool, arguments, result} for every call (for accounting)."""

    def __init__(self, bridge):
        super().__init__(bridge)
        self.recorded: list[dict] = []

    def call(self, command, args):
        result = super().call(command, args)
        self.recorded.append({"tool": command, "arguments": args, "result": result})
        return result


def known_tools() -> set[str]:
    return {("capabilities.invoke" if s.tier == "generated" else s.command)
            for s in build_router().specs()}


def _schemas_for(tools: set[str]) -> dict[str, dict]:
    by_name = {s.name: s for s in build_router().specs()}
    out = {}
    for t in tools:
        spec = by_name.get(t)
        if spec is not None:
            out[t] = spec.input_schema()
    return out


def _sdk_sources_for(tools: set[str]) -> dict[str, str]:
    domains = {t.split(".", 1)[0] for t in tools}
    generated = generate.generate_all()
    return {d: generated[d] for d in domains if d in generated}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a skill in code mode and size the token win.")
    ap.add_argument("--skill", default="make_game_ready")
    ap.add_argument("--items", default="", help="comma-separated item ids (all if empty)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--outdir", default="/tmp/niua_skill_run")
    args = ap.parse_args(argv)

    skill = get_skill(args.skill)
    ids = list_items()
    if args.items:
        wanted = set(args.items.split(","))
        ids = [i for i in ids if i in wanted]
    items = [load_item(i) for i in ids]

    # The skill declares its tools on the module; guard them offline before any bridge call.
    from niua_blender_mcp.finishing.skills import make_game_ready
    assert_tools_registered(items, extra_tools=frozenset(make_game_ready.TOOLS_USED))

    schemas = _schemas_for(make_game_ready.TOOLS_USED)
    sdk_sources = _sdk_sources_for(make_game_ready.TOOLS_USED)

    bridge = BlenderBridge(port=args.port, timeout=600.0)
    cards = []
    for item in items:
        subject = f"bench_{item['id']}"
        _clear_meshes(bridge)
        _build_input(bridge, item, subject)
        session = RecordingSession(bridge)
        summary = skill.run(session, subject, {"asset_class": item["asset_class"], "id": item["id"]})
        acct = accounting.token_accounting(session.recorded, sdk_sources, schemas, summary)
        cards.append({"id": item["id"], "readiness_final": summary.get("readiness_final"),
                      "accounting": acct})
        print(f"[{item['id']}] readiness_final={summary.get('readiness_final')} "
              f"tool_by_tool={acct['tool_by_tool_tokens']} code_mode={acct['code_mode_tokens']} "
              f"ratio={acct['ratio']:.1f}x" if acct["ratio"] else f"[{item['id']}] (no ratio)",
              file=sys.stderr)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "skill-run.json").write_text(
        json.dumps({"skill": args.skill, "items": cards}, indent=2), encoding="utf-8")
    print(json.dumps({"skill": args.skill, "items": cards}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
