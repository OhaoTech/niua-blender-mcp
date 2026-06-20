# Subsystem 12 Design: UI Automation / GUI Parity Layer

Date: 2026-06-20
Status: planned

## Goal

Make Blender's GUI context visible and operator-addressable through MCP, while being
honest about what Blender Python can and cannot do in background mode.

Subsystems 1-11 expose Blender's durable data model and stable operators. Subsystem 12
adds the missing GUI parity substrate:

- inspect windows, screens, workspaces, areas, regions, and their geometry
- report whether foreground-only UI capabilities are actually available
- poll operators in an explicit editor context
- invoke operators with an explicit window/area/region override
- capture UI screenshots when Blender's own screenshot operator is available
- request viewport/window redraw when Blender's redraw operator is available

This layer is not a replacement for domain tools. It is the bridge for GUI-shaped
workflows that still need a specific editor area, plus a clear diagnostic surface for
cases where true physical keyboard/mouse input is not available.

## What We Have

Existing related tools:

- `app.*` covers session/file lifecycle, undo/redo, workspace switching, add-ons, and
  preference summaries.
- `context.*` covers active object, selection, mode, mesh select mode, editor-area
  discovery, and operator polling in current/proposed object context.
- `capabilities.*` and `rna.*` expose search/describe/invoke for Blender operators and
  RNA paths.
- `Ctx.ensure(...)` already uses `bpy.context.temp_override` for a requested area when
  available and skips it safely in headless/background mode.
- `feedback.*` captures diagnostic rendered/viewport-like views for visual inspection.

Current gaps:

- No first-class report of Blender's UI topology: windows, screens, areas, regions,
  geometry, active workspace, and background status.
- No explicit operator poll/invoke surface that chooses a particular editor area and
  region.
- No structured answer for "can this MCP click, type, screenshot, or redraw the GUI in
  the current session?"
- No screenshot wrapper that returns `available: false` instead of surfacing a raw poll
  failure in headless/background sessions.

## Capability Surface

### UI State

`ui.state()`

Read-only. Reports:

- `background`
- `window_count`
- `active_window`
- UI capability flags:
  - `context_override`
  - `screen_screenshot`
  - `redraw`
  - `keyboard_events`
  - `mouse_events`

`keyboard_events` and `mouse_events` are explicit capability reports, not promises.
The initial bridge does not synthesize OS-level input. GUI work should prefer direct
domain tools or `ui.operator_invoke` with area context.

`ui.windows()`

Read-only. Returns all windows with screen/workspace names, areas, regions, and area/
region rectangles. This is the address book for editor-specific operations.

### Area-Aware Operators

`ui.operator_poll(idname, area="VIEW_3D", region="WINDOW", window_index=-1, area_index=-1, object?, mode?, select?, require_area=false)`

Checks whether an operator polls in a chosen UI context. `select` is a JSON array string
of object names, matching `rna.call_operator`.

Targeting rules:

- `window_index >= 0` chooses that window; otherwise the first matching window is used.
- `area_index >= 0` chooses that area in the target window; otherwise the first area of
  type `area` is used.
- `region` chooses a region type inside the area, defaulting to `WINDOW`.
- If no matching area exists and `require_area=false`, the poll runs without a UI
  override and returns `override: false`.
- If no matching area exists and `require_area=true`, the result is unavailable with a
  reason instead of an exception.

`ui.operator_invoke(idname, args?, area="VIEW_3D", region="WINDOW", window_index=-1, area_index=-1, object?, mode?, select?, require_area=false)`

Runs any Blender operator with explicit UI context. Arguments are JSON object strings and
are validated/coerced using the existing RNA executor helpers. The command is undo-safe:
the dispatcher pushes one undo marker only after successful invocation.

This is the GUI-context sibling of `capabilities.invoke`. Use it when an operator's
success depends on being run inside a specific editor such as `VIEW_3D`,
`NODE_EDITOR`, `IMAGE_EDITOR`, `DOPESHEET_EDITOR`, `GRAPH_EDITOR`, or `OUTLINER`.

### UI Screenshot And Redraw

`ui.screenshot(path, full=false)`

Calls Blender's `screen.screenshot` operator when it polls true. In headless/background
sessions where the operator is present but unavailable, it returns:

```json
{"available": false, "reason": "..."}
```

It does not pretend to capture a screenshot. Diagnostic scene captures remain
`feedback.*`.

`ui.redraw(type="DRAW_WIN_SWAP", iterations=1)`

Calls Blender's `wm.redraw_timer` when it polls true and returns unavailable otherwise.
This is useful in visible sessions after a batch of operations, but should not be
required for data correctness.

## Error Handling

- Unknown operators return `not_found`.
- Bad JSON args/select values return `invalid_params`.
- Missing objects in active/select hints return `precondition_failed`.
- A requested UI target that does not exist returns unavailable for poll-like commands
  and `precondition_failed` for mutating invoke commands when `require_area=true`.
- Operators that poll false return unavailable from `ui.operator_poll` and
  `precondition_failed` from `ui.operator_invoke`.

## Testing

Fake-bpy unit tests cover:

- server/add-on parity for all `ui.*` tools
- window/area/region reporting, including geometry
- capability flags for screenshot/redraw/event availability
- area-aware operator poll with and without an override
- area-aware operator invoke with validated args, active/mode/select hints, and returned
  UI target metadata
- screenshot/redraw unavailable results when polls fail
- screenshot success with file output under a fake operator

Real Blender smoke covers:

1. `ui.state` and `ui.windows` in background Blender.
2. `ui.operator_poll` for a harmless operator in `VIEW_3D`.
3. `ui.operator_invoke` creating an object through a UI context override.
4. `ui.screenshot` returning unavailable in background mode without crashing.

## Deferred

- True OS-level keyboard and mouse event injection. Blender Python does not provide a
  portable background-safe event injector. If we need literal clicks/typing, that belongs
  in a separate foreground desktop automation adapter outside the Blender add-on process.
- Modal drag workflows such as knife strokes, box/lasso selection, transform gizmo drags,
  graph handle dragging, node wire dragging, and compositor region drags. Where Blender
  exposes non-modal operators or data APIs, use domain tools or `ui.operator_invoke`.
- Higher-level artist judgment for when to use GUI-shaped operations remains Layer 2.
