from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_blender_coverage.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_blender_coverage", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_blender_source(root: Path) -> Path:
    (root / "source/blender/makesrna/intern").mkdir(parents=True)
    (root / "source/blender/editors/space_view3d").mkdir(parents=True)
    (root / "source/blender/editors/space_buttons").mkdir(parents=True)
    (root / "source/blender/editors/space_sequencer").mkdir(parents=True)
    (root / "scripts/startup/bl_ui").mkdir(parents=True)
    (root / "source/blender/makesrna/intern/rna_space.cc").write_text(
        """
        const EnumPropertyItem buttons_context_items[] = {
          {BCONTEXT_OBJECT, "OBJECT", ICON_OBJECT_DATA, "Object", "Object Properties"},
          {BCONTEXT_MODIFIER, "MODIFIER", ICON_MODIFIER, "Modifiers", "Modifier Properties"},
          {BCONTEXT_CONSTRAINT,
           "CONSTRAINT",
           ICON_CONSTRAINT,
           "Constraints",
           "Object Constraint Properties"},
          {BCONTEXT_PARTICLE, "PARTICLES", ICON_PARTICLES, "Particles", "Particle Properties"},
          {BCONTEXT_STRIP, "STRIP", ICON_SEQ_SEQUENCER, "Strip", "Strip Properties"},
          {0, nullptr, 0, nullptr, nullptr},
        };
        """,
        encoding="utf-8",
    )
    (root / "scripts/startup/bl_ui/properties_object.py").write_text("class OBJECT_PT_transform: pass\n")
    (root / "scripts/startup/bl_ui/properties_particle.py").write_text("class PARTICLE_PT_context: pass\n")
    (root / "scripts/startup/bl_ui/properties_data_mesh.py").write_text("class DATA_PT_mesh: pass\n")
    (root / "scripts/startup/bl_ui/properties_data_volume.py").write_text("class DATA_PT_volume: pass\n")
    (root / "scripts/startup/bl_ui/properties_data_unimplemented_fixture.py").write_text(
        "class DATA_PT_unimplemented_fixture: pass\n"
    )
    return root


def test_scans_blender_source_taxonomy(tmp_path: Path) -> None:
    audit = _load_audit_module()
    source = _fake_blender_source(tmp_path / "blender")

    scan = audit.scan_blender_source(source)

    assert scan["properties_contexts"] == ["OBJECT", "MODIFIER", "CONSTRAINT", "PARTICLES", "STRIP"]
    assert scan["editor_spaces"] == ["buttons", "sequencer", "view3d"]
    assert scan["properties_files"] == [
        "properties_data_mesh.py",
        "properties_data_unimplemented_fixture.py",
        "properties_data_volume.py",
        "properties_object.py",
        "properties_particle.py",
    ]
    assert scan["object_data_types"] == ["mesh", "unimplemented_fixture", "volume"]


def test_builds_context_and_data_type_coverage(tmp_path: Path) -> None:
    audit = _load_audit_module()
    source = _fake_blender_source(tmp_path / "blender")
    tools = {
        *audit.PREFIX_TOOL_RULES["modifiers"],
        *audit.PREFIX_TOOL_RULES["object"],
        "properties.report",
    }
    mcp = audit.McpSurface(
        prefixes={"object", "modifiers", "properties", "rna", "capabilities"},
        tool_count=len(tools),
        addon_command_count=10,
        tools=tools,
    )

    report = audit.build_report(source, mcp)
    by_context = {row["name"]: row for row in report["coverage"]["properties_contexts"]}
    by_data = {row["name"]: row for row in report["coverage"]["object_data_types"]}

    assert by_context["OBJECT"]["status"] == "covered"
    assert by_context["MODIFIER"]["status"] == "covered"
    assert by_context["PARTICLES"]["status"] == "partial"
    assert by_context["PARTICLES"]["missing_prefixes"] == ["particles"]
    assert by_context["STRIP"]["status"] == "partial"
    assert by_data["mesh"]["status"] == "partial"
    assert by_data["volume"]["status"] == "partial"
    assert report["summary"]["partial"] >= 3
    assert report["summary"]["missing"] == 0


def test_required_tools_prevent_placeholder_prefix_coverage(tmp_path: Path) -> None:
    audit = _load_audit_module()
    source = _fake_blender_source(tmp_path / "blender")
    (source / "source/blender/editors/space_spreadsheet").mkdir(parents=True)
    mcp = audit.McpSurface(
        prefixes={"spreadsheet"},
        tool_count=1,
        addon_command_count=1,
        tools={"spreadsheet.placeholder"},
    )

    report = audit.build_report(source, mcp)
    by_editor = {row["name"]: row for row in report["coverage"]["editor_spaces"]}

    assert by_editor["spreadsheet"]["status"] == "partial"
    assert by_editor["spreadsheet"]["missing_prefixes"] == []
    assert by_editor["spreadsheet"]["missing_tools"] == [
        "spreadsheet.columns",
        "spreadsheet.report",
        "spreadsheet.rows",
    ]


def test_cli_json_and_fail_on_partial(tmp_path: Path, capsys) -> None:
    audit = _load_audit_module()
    source = _fake_blender_source(tmp_path / "blender")

    code = audit.main(["--source", str(source), "--json", "--fail-on", "partial"])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["summary"]["partial"] > 0
    assert out["source"]["properties_contexts"] == ["OBJECT", "MODIFIER", "CONSTRAINT", "PARTICLES", "STRIP"]


def test_default_source_resolves_from_nested_worktree_root() -> None:
    audit = _load_audit_module()
    repo_root = Path("/home/frankyin/Desktop/lab/lab-niua-blender/.worktrees/layer2-wave9b-workflow-breadth")

    resolved = audit.default_blender_source(repo_root)

    assert resolved == Path("/home/frankyin/Desktop/lab/blender-source")
