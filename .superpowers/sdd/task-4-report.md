Status: DONE_WITH_CONCERNS

Commit SHA(s):
- `2f61900105e96345f9c06dc685e713dc5d7188e2` (`docs: update Layer 2 workflow breadth map`)

Files changed:
- `tests/test_smoke_headless.py`
- `docs/layer2-architecture.html`

Red/green evidence:
- Added `test_layer2_wave9b_workflow_breadth_acceptance` after `test_layer2_wave9a_craft_workflow_acceptance` in `tests/test_smoke_headless.py` per brief.
- Focused smoke command run exactly as required:
  - `pytest tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
- Red-phase result:
  - Command exited `1`.
  - Failure occurred at `generated_quality = bridge.call("feedback.quality", {"object": "GeneratedWorkflowHero"})`.
  - Assertion failure summary: expected `generated_quality["asset_class"]["id"] == "generated_cleanup"`, actual value was `hard_surface_prop`.
  - This is a real failing acceptance case, not the "already green because Tasks 2-3 already landed" limitation.
- Green-phase status:
  - Not achieved within Task 4 ownership constraints.
  - The failing behavior is outside the two allowed files and appears to be an implementation issue in existing workflow/quality state propagation.

Diagram browser-check evidence:
- Refreshed architecture counts with:
  - `PYTHONPATH=src:blender_addon python - <<'PY'`
  - `from niua_blender_mcp.domains import build_router`
  - `from niua_mcp_bridge.domains import build_default_registry`
  - `print(len(build_router().specs()))`
  - `print(len(build_default_registry().names()))`
  - `PY`
- Count results:
  - Server specs: `328`
  - Add-on commands: `311`
- Updated `docs/layer2-architecture.html` to show:
  - Wave 9B built/current
  - generated cleanup and organic workflow breadth built
  - Wave 10 as UV/bake/material workflow breadth
  - Wave 9A hard-surface still built
- HTML parse check:
  - `python - <<'PY' ...`
  - Output: `html_parse_ok`
- Browser screenshots captured from the worktree file URL:
  - Desktop: `/tmp/layer2-architecture-wave9b-desktop.png`
  - Mobile: `/tmp/layer2-architecture-wave9b-mobile.png`
- Browser command summaries:
  - Desktop `browse chain` navigated to `file:///home/frankyin/Desktop/lab/lab-niua-blender/.worktrees/layer2-wave9b-workflow-breadth/docs/layer2-architecture.html` with status `200`, waited for load, saved screenshot.
  - Mobile `browse chain` navigated to the same worktree file URL with status `200`, waited for load, saved screenshot.
- Visual check summary:
  - Both screenshots are nonblank and readable.
  - Desktop screenshot shows the updated metrics and Wave 9B current badge.
  - Mobile screenshot shows the same updated header/metric content without overlap.

Final verification commands and output summaries:
- `pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_modeling_verbs.py tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
  - Exit `1`.
  - Non-smoke targeted tests passed.
  - The single failing test was `tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance` with the same generated asset-class mismatch (`hard_surface_prop` vs `generated_cleanup`).
- `python scripts/audit_blender_coverage.py --fail-on partial`
  - Exit `1`.
  - Error: `FileNotFoundError: Blender source path does not exist: /home/frankyin/Desktop/lab/lab-niua-blender/.worktrees/blender-source`
  - This is an environment/worktree prerequisite issue, not caused by the two owned file edits.
- `pytest -q`
  - Exit `1`.
  - Suite progressed through the existing tests and then failed on the same new acceptance test.
  - No additional new failures were introduced by the owned-file changes beyond the surfaced workflow issue.
- `git diff --check`
  - Exit `0`.
  - No whitespace or patch formatting issues.

Concerns:
- Primary blocker: `feedback.quality` reports `hard_surface_prop` after the generated-cleanup workflow path in the headless acceptance test. This prevents Task 4 from reaching a green acceptance result without changing code outside the allowed files.
- Verification environment issue: `scripts/audit_blender_coverage.py --fail-on partial` cannot run successfully in this worktree because `/home/frankyin/Desktop/lab/lab-niua-blender/.worktrees/blender-source` is missing.
- Preserved unrelated worktree changes:
  - Existing unstaged `.gitignore` modification remains untouched.

---

Status: DONE

Commit SHA(s):
- `3f956d825a591dc32e17efaa0dc5714ec9d8d4f1`

Files changed:
- `blender_addon/niua_mcp_bridge/domains/feedback.py`
- `scripts/audit_blender_coverage.py`
- `tests/domains/test_quality.py`
- `tests/test_blender_coverage_audit.py`

Red test evidence and exact failure summaries:
- Added focused regression test `tests/domains/test_quality.py::test_quality_uses_pipeline_asset_class_state_when_payload_omits_class`.
- Added focused regression test `tests/test_blender_coverage_audit.py::test_default_source_resolves_from_nested_worktree_root`.
- Red-phase command:
  - `pytest tests/domains/test_quality.py::test_quality_uses_pipeline_asset_class_state_when_payload_omits_class tests/test_blender_coverage_audit.py::test_default_source_resolves_from_nested_worktree_root -q`
- Red-phase result:
  - Exit `1`
  - Failure 1 summary:
    - `assert meta["id"] == "generated_cleanup"`
    - actual value: `hard_surface_prop`
  - Failure 2 summary:
    - `AttributeError: module 'audit_blender_coverage' has no attribute 'default_blender_source'`

Green verification command summaries:
- `pytest tests/domains/test_quality.py::test_quality_uses_pipeline_asset_class_state_when_payload_omits_class tests/test_blender_coverage_audit.py -q`
  - Exit `0`
  - Result: `6 passed`
- `pytest tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
  - Exit `0`
  - Result: `1 passed`
- `python scripts/audit_blender_coverage.py --fail-on partial`
  - Exit `0`
  - Resolved source: `/home/frankyin/Desktop/lab/blender-source`
  - Summary: `{'covered': 58, 'partial': 0, 'missing': 0}`
- `pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_modeling_verbs.py tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
  - Exit `0`
  - Result: `28 passed`
- `git diff --check`
  - Exit `0`

Remaining concerns:
- No functional concerns in the fixed scope.
- Existing unstaged `.gitignore` change adding `.gstack/` was preserved and not modified.

---

Status: DONE

Files changed:
- `tests/domains/test_quality.py`
- `tests/test_smoke_headless.py`

Review-fix summary:
- Hardened the generated-cleanup smoke acceptance test so it always asserts the `skipped` payload contract for the optional `mesh.delete_loose` step.
- Reset pipeline global state in the `tests/domains/test_quality.py` fake-bpy fixture before each test so pipeline-backed asset-class inference cannot leak across tests.

Focused verification:
- `pytest tests/domains/test_quality.py::test_quality_uses_pipeline_asset_class_state_when_payload_omits_class tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
  - Exit `0`
  - Result: `2 passed`

Targeted verification:
- `pytest tests/test_craft_workflows.py tests/domains/test_craft_workflow.py tests/domains/test_modeling_verbs.py tests/test_smoke_headless.py::test_layer2_wave9b_workflow_breadth_acceptance -q`
  - Exit `0`
  - Result: `28 passed`
- `python scripts/audit_blender_coverage.py --fail-on partial`
  - Exit `0`
  - Summary: `{'covered': 58, 'partial': 0, 'missing': 0}`
- `git diff --check`
  - Exit `0`

Failure encountered while hardening the smoke assertion:
- Initial exact assertion of `generated["skipped"] == [{"operator": "mesh.delete_loose", "reason": "unavailable"}]` failed under real headless Blender because this environment exposes `mesh.delete_loose`, so `generated["skipped"]` was `[]`.
- Updated the acceptance test to assert the real command contract instead:
  - when `delete_loose` is applied, `skipped == []`
  - otherwise `skipped` must contain the unavailable-operator record

Remaining concerns:
- No functional concerns in the fixed scope.
- Existing unstaged `.gitignore` change remains untouched and unstaged.
