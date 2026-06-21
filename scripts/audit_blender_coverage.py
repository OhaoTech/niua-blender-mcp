#!/usr/bin/env python3
"""Audit Blender source/UI surface against the MCP tool surface.

This is a source-backed coverage map, not a live-Blender runtime test. It answers:

- what Blender editor/property contexts exist in the pulled source tree?
- what MCP prefixes/tools exist in this repo?
- which contexts have curated coverage, only generic fallback, or no coverage?

Default Blender source path is the sibling clone `../blender-source`.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT.parent / "blender-source"
for import_path in (REPO_ROOT / "src", REPO_ROOT / "blender_addon", REPO_ROOT):
    path_text = str(import_path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


@dataclass(frozen=True)
class McpSurface:
    prefixes: set[str]
    tool_count: int
    addon_command_count: int | None
    tools: set[str]


CONTEXT_RULES: dict[str, dict[str, Any]] = {
    "TOOL": {"required": ["tool"], "partial": ["app", "ui", "properties"]},
    "SCENE": {"required": ["scene"], "partial": ["properties", "rna"]},
    "RENDER": {"required": ["render"], "partial": ["properties", "rna"]},
    "OUTPUT": {"required": ["render"], "partial": ["io", "properties", "rna"]},
    "VIEW_LAYER": {"required": ["outliner"], "partial": ["render", "properties", "rna"]},
    "WORLD": {"required": ["world"], "partial": ["properties", "rna"]},
    "COLLECTION": {"required": ["outliner"], "partial": ["properties", "rna"]},
    "OBJECT": {"required": ["object"], "partial": ["outliner", "properties", "rna"]},
    "CONSTRAINT": {"required": ["constraints"], "partial": ["rig", "properties", "rna"]},
    "MODIFIER": {"required": ["modifiers"], "partial": ["geometry_nodes", "properties", "rna"]},
    "DATA": {"required": ["properties"], "partial": ["mesh", "geometry", "camera", "light", "rig", "rna"]},
    "BONE": {"required": ["rig"], "partial": ["properties", "rna"]},
    "BONE_CONSTRAINT": {"required": ["rig"], "partial": ["properties", "rna"]},
    "MATERIAL": {"required": ["shading"], "partial": ["textures", "properties", "rna"]},
    "TEXTURE": {"required": ["textures"], "partial": ["shading", "properties", "rna"]},
    "PARTICLES": {"required": ["particles"], "partial": ["properties", "rna"]},
    "PHYSICS": {"required": ["physics"], "partial": ["properties", "rna"]},
    "SHADERFX": {"required": ["shaderfx"], "partial": ["properties", "rna"]},
    "STRIP": {"required": ["sequencer"], "partial": ["properties", "rna"]},
    "STRIP_MODIFIER": {"required": ["sequencer"], "partial": ["properties", "rna"]},
}

DATA_TYPE_RULES: dict[str, dict[str, Any]] = {
    "armature": {"required": ["rig"], "partial": ["properties", "rna"]},
    "bone": {"required": ["rig"], "partial": ["properties", "rna"]},
    "camera": {"required": ["camera"], "partial": ["properties", "rna"]},
    "curve": {"required": ["geometry"], "partial": ["properties", "rna"]},
    "curves": {"required": ["geometry"], "partial": ["properties", "rna"]},
    "empty": {"required": ["object"], "partial": ["properties", "rna"]},
    "grease_pencil": {"required": ["geometry"], "partial": ["properties", "rna"]},
    "lattice": {"required": ["lattice"], "partial": ["properties", "rna"]},
    "light": {"required": ["light"], "partial": ["properties", "rna"]},
    "lightprobe": {"required": ["lightprobe"], "partial": ["properties", "rna"]},
    "mesh": {"required": ["mesh", "uv"], "partial": ["properties", "rna"]},
    "metaball": {"required": ["geometry"], "partial": ["properties", "rna"]},
    "modifier": {"required": ["modifiers"], "partial": ["properties", "rna"]},
    "pointcloud": {"required": ["pointcloud"], "partial": ["properties", "rna"]},
    "shaderfx": {"required": ["shaderfx"], "partial": ["properties", "rna"]},
    "speaker": {"required": ["speaker"], "partial": ["properties", "rna"]},
    "volume": {"required": ["volume"], "partial": ["properties", "rna"]},
}

EDITOR_SPACE_RULES: dict[str, dict[str, Any]] = {
    "view3d": {"required": ["ui"], "partial": ["object", "mesh", "context"]},
    "buttons": {"required": ["properties"], "partial": ["ui"]},
    "outliner": {"required": ["outliner"], "partial": ["ui"]},
    "node": {"required": ["geometry_nodes"], "partial": ["shading", "compositor", "ui", "rna"]},
    "image": {"required": ["uv"], "partial": ["textures", "ui", "rna"]},
    "action": {"required": ["anim"], "partial": ["ui", "rna"]},
    "graph": {"required": ["anim"], "partial": ["ui", "rna"]},
    "nla": {"required": ["anim"], "partial": ["ui", "rna"]},
    "sequencer": {"required": ["sequencer"], "partial": ["ui", "rna"]},
    "file": {"required": ["io"], "partial": ["app", "ui"]},
    "userpref": {"required": ["app"], "partial": ["ui", "rna"]},
    "text": {"required": ["text"], "partial": ["ui", "rna"]},
    "console": {"required": ["system"], "partial": ["ui"]},
    "spreadsheet": {"required": ["spreadsheet"], "partial": ["ui", "properties"]},
    "clip": {"required": ["tracking"], "partial": ["ui", "rna"]},
}


def scan_blender_source(source: Path) -> dict[str, Any]:
    source = source.resolve()
    rna_space = source / "source/blender/makesrna/intern/rna_space.cc"
    bl_ui = source / "scripts/startup/bl_ui"
    editors = source / "source/blender/editors"
    if not source.exists():
        raise FileNotFoundError(f"Blender source path does not exist: {source}")
    if not rna_space.exists():
        raise FileNotFoundError(f"missing Blender RNA source file: {rna_space}")

    text = rna_space.read_text(encoding="utf-8", errors="replace")
    block_match = re.search(r"buttons_context_items\[\]\s*=\s*\{(?P<body>.*?)\n\s*\};", text, re.S)
    body = block_match.group("body") if block_match else ""
    contexts = re.findall(r'\{\s*BCONTEXT_[A-Z_]+\s*,\s*"([^"]+)"', body, re.S)

    properties_files = sorted(path.name for path in bl_ui.glob("properties_*.py")) if bl_ui.exists() else []
    data_types = sorted(
        path.stem.removeprefix("properties_data_")
        for path in bl_ui.glob("properties_data_*.py")
    ) if bl_ui.exists() else []
    editor_spaces = sorted(
        path.name.removeprefix("space_")
        for path in editors.glob("space_*")
        if path.is_dir()
    ) if editors.exists() else []

    return {
        "path": str(source),
        "properties_contexts": contexts,
        "properties_files": properties_files,
        "object_data_types": data_types,
        "editor_spaces": editor_spaces,
    }


def scan_mcp_surface() -> McpSurface:
    # Import lazily so tests can load parser helpers without requiring package import first.
    from niua_blender_mcp.domains import build_router

    specs = build_router().specs()
    tools = {spec.name for spec in specs}
    prefixes = {tool.split(".", 1)[0] for tool in tools if "." in tool}
    addon_count: int | None = None
    try:
        from blender_addon.niua_mcp_bridge.domains import build_default_registry

        addon_count = len(build_default_registry().names())
    except Exception:  # noqa: BLE001 - server-only installs can still audit server specs
        addon_count = None
    return McpSurface(prefixes=prefixes, tool_count=len(tools), addon_command_count=addon_count, tools=tools)


def _coverage_row(name: str, rules: dict[str, Any], prefixes: set[str]) -> dict[str, Any]:
    required = list(rules.get("required", []))
    partial = list(rules.get("partial", []))
    present_required = [prefix for prefix in required if prefix in prefixes]
    present_partial = [prefix for prefix in partial if prefix in prefixes]
    missing = [prefix for prefix in required if prefix not in prefixes]
    if required and not missing:
        status = "covered"
    elif present_required or present_partial:
        status = "partial"
    else:
        status = "missing"
    return {
        "name": name,
        "status": status,
        "required_prefixes": required,
        "partial_prefixes": partial,
        "present_prefixes": sorted(set(present_required + present_partial)),
        "missing_prefixes": missing,
    }


def _summarize(*groups: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"covered": 0, "partial": 0, "missing": 0}
    for rows in groups:
        for row in rows:
            summary[row["status"]] += 1
    return summary


def build_report(source: Path, mcp: McpSurface | None = None) -> dict[str, Any]:
    source_scan = scan_blender_source(source)
    mcp = mcp or scan_mcp_surface()
    context_rows = [
        _coverage_row(context, CONTEXT_RULES.get(context, {"required": [], "partial": ["properties", "rna"]}), mcp.prefixes)
        for context in source_scan["properties_contexts"]
    ]
    data_rows = [
        _coverage_row(data_type, DATA_TYPE_RULES.get(data_type, {"required": [data_type], "partial": ["properties", "rna"]}), mcp.prefixes)
        for data_type in source_scan["object_data_types"]
    ]
    editor_rows = [
        _coverage_row(space, EDITOR_SPACE_RULES.get(space, {"required": [space], "partial": ["ui", "rna"]}), mcp.prefixes)
        for space in source_scan["editor_spaces"]
    ]
    return {
        "source": source_scan,
        "mcp": {
            "server_specs": mcp.tool_count,
            "addon_commands": mcp.addon_command_count,
            "prefixes": sorted(mcp.prefixes),
            "tools": sorted(mcp.tools),
        },
        "coverage": {
            "properties_contexts": context_rows,
            "object_data_types": data_rows,
            "editor_spaces": editor_rows,
        },
        "summary": _summarize(context_rows, data_rows, editor_rows),
    }


def _print_table(title: str, rows: list[dict[str, Any]]) -> None:
    print(title)
    print("-" * len(title))
    print(f"{'STATUS':8} {'NAME':18} {'MISSING':24} PRESENT")
    for row in rows:
        print(
            f"{row['status']:8} {row['name']:18} "
            f"{','.join(row['missing_prefixes']) or '-':24} "
            f"{','.join(row['present_prefixes']) or '-'}"
        )
    print()


def _human(report: dict[str, Any]) -> None:
    print(f"Blender source: {report['source']['path']}")
    print(f"Server specs: {report['mcp']['server_specs']}")
    print(f"Add-on commands: {report['mcp']['addon_commands']}")
    print(f"Summary: {report['summary']}")
    print()
    _print_table("Properties Context Coverage", report["coverage"]["properties_contexts"])
    _print_table("Object Data Type Coverage", report["coverage"]["object_data_types"])
    _print_table("Editor Space Coverage", report["coverage"]["editor_spaces"])


def _exit_code(report: dict[str, Any], fail_on: str) -> int:
    if fail_on == "none":
        return 0
    if report["summary"]["missing"] > 0:
        return 1
    if fail_on == "partial" and report["summary"]["partial"] > 0:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Path to Blender source checkout")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--fail-on",
        choices=["none", "missing", "partial"],
        default="missing",
        help="Exit nonzero on missing coverage, or on partial+missing coverage",
    )
    args = parser.parse_args(argv)

    report = build_report(args.source)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _human(report)
    return _exit_code(report, args.fail_on)


if __name__ == "__main__":
    sys.exit(main())
