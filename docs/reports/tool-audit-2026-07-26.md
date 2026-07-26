# Live tool audit — every shipped tool, 2026-07-26

Ran all 292 tools of the shipped (pure-MCP) surface against a live Blender 5.1.2 and cut
what could not work. Harness: `scripts/audit_tool_surface.py`, re-runnable.

## Result

| | count | |
|---|---|---|
| `ok` | 129 | ran and returned |
| `precondition` | 120 | refused for a stated reason — the guard rails working |
| `error` | 23 | **all 23 hand-retested**; 22 were the harness guessing bad arguments |
| `invalid` | 8 | argument validation rejecting my guesses, with teachable messages |
| `manual` | 12 | fenced off from the sweep, hand-tested separately — all pass |
| `unknown` | **0** | no missing commands |
| `crash` | **0** | nothing took Blender down |

**One tool was genuinely broken and has been removed: `lattice.convert_to_mesh`.**

## The one real failure

Blender cannot convert a lattice to a mesh. Verified on an operator-created 8-point
lattice, not just my synthetic fixture:

```
convert_poll()                      True
targets enum                        ['CURVE','MESH','POINTCLOUD','CURVES','GREASEPENCIL']
bpy.ops.object.convert(target=MESH) {'FINISHED'}     <- claims success
object type afterwards              LATTICE          <- unchanged
to_mesh()                           RuntimeError: Object does not have geometry data
```

A control confirms the plumbing is fine: `AUD_curve` converts to `MESH` through the same
operator. Blender simply no-ops on lattices — a lattice is a deformer cage, not geometry.

The tool detected this and raised a clean `precondition_failed`, so it never lied. But it
could *never* succeed, and a tool that always fails is worse than a missing one: it sends
an agent down a dead end and reads as a broken MCP. Removed from the add-on, the server
specs, and the generated client SDK. `tests/domains/test_lattice.py` now asserts its
absence, and the live smoke test asserts the command returns `unknown_tool`.

## Why 22 of 23 "errors" were not bugs

This is the important half of the report. Auto-generated arguments produce false
positives, and this repo has a history of "bugs" that were caller error. Every one was
retested by hand with correct arguments:

| Apparent failure | Truth |
|---|---|
| `io.export`, `io.prepare_asset`, `uv.export_layout` | my synthesized path ended `.txt`; fine with `.glb`/`.png` |
| `text.open`, `textures.load`, `tracking.clip_load`, `volume.import` | I passed a path that did not exist |
| `properties.get/set/unset` | custom properties need the documented `idprops/` segment: `object:X/idprops/KEY` |
| `rna.get_property`, `rna.set_property` | these take a **dotted `bpy.data` path** (`objects.Cube.location`), not the `object:` form |
| `rna.describe` | needs an `op:` or `type:` prefix |
| `compositor.add_node`, `tool.set` | I passed the literal string `"x"` as a node type / tool id |
| `geometry.set_curve/set_text`, `pointcloud.set`, `volume.set` | I aimed a typed tool at a mesh fixture |
| `outliner.orphans_purge`, `outliner.view_layer_delete` | destructive, and correctly demand `force=true` |

`system.cancel` also looked broken until I noticed its parameter is `op_id`, not
`operation`; with the right name it cancels a real in-flight operation and refuses a bogus
id. Cancellation is cooperative — it lands at the operation's next check — so a turntable
already mid-render finishes. That is the documented contract, not a defect.

## Coverage: no gaps left

The first pass left two tools unproven. Both are now closed.

**`volume.import`** — needed a real `.vdb`, and one cannot be synthesized: `pyopenvdb` is
absent from this Blender and `bpy` exposes no VDB writer. Blender *can* write one as a
side effect, though — a fluid cache. Baking a 24-resolution smoke sim for three frames
with `cache_data_format='OPENVDB'` produces `fluid_data_0001.vdb`, and importing that:

```
volume.import {"path": ".../fluid_data_0001.vdb"}  ->  {'object': 'AUD_imported_volume',
                                                        'type': 'VOLUME', ...}
volume.report {"name_or_object": "AUD_imported_volume"}  ->  reads the grid back
```

**`app.preferences_save`** — genuinely writes to the user's Blender install, so it was
tested against a backup: copy `config/userpref.blend` aside, call the tool, confirm the
file's mtime changed (proving it really saved), restore the backup. Result `{'ok': True,
'applied': ['wm.save_userpref']}`, and the user's preferences are byte-for-byte unchanged.
Destructive tools are testable; they just need the blast radius handled first.

Everything else in the `manual` bucket was exercised too: `app.file_new/open/save/save_as/
revert` through a temp `.blend`, `app.addon_disable`/`addon_enable` on a non-critical
add-on (restored immediately), `script.run_file`, `script.reload`, `session.checkpoint/
list_checkpoints/revert`, and `ui.operator_invoke`. The bridge survived every one,
including `script.reload` under a live add-on.

**Every one of the 291 shipped tools has now been exercised against live Blender.**

## The shipped surface, confirmed on the artifacts

Not on the repo tree — on the built wheel and the built add-on zip, each imported with no
repo fallback on the path:

```
add-on artifact  291 tools   policy present: NONE   lattice.convert_to_mesh: absent
wheel            309 specs   policy present: NONE
```

The twelve policy tools (`feedback.quality/readiness/critique/preservation/capture_intake`,
`io.profile_validate`, `asset_class.list/describe`, `object.retopo/lod_create/
collision_hulls_create/collision_proxy_create`) and the two finisher skills
(`bake_and_finish`, `make_game_ready`) are all absent from both artifacts. They remain in
the repo under benchmark — see ARCHITECTURE.md, "What is and isn't the MCP".

## Reproducing

```bash
python scripts/build_addon_zip.py --out dist/addon-product.zip   # the pure surface
python scripts/audit_tool_surface.py --tools-json <spec-map.json> --out dist/tool-audit.json
```

Read the output with the classifier in mind: `error` is a *lead*, not a verdict. Retest
by hand before cutting anything.
