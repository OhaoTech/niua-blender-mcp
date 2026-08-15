---
name: niua-blender-finisher
description: Drive the NIUA Blender Finisher MCP without exploding the token window. Use when calling blender-finisher, feedback-critique, feedback-capture, feedback-capture_views, system-execute_python, observing a Blender mesh, or finishing an asset game-ready.
---

# NIUA Blender Finisher

The MCP is the hands. This is how you look without paying for pixels twice.

## Connect

The bridge **autostarts with Blender** (0.2.2) — no N-panel click. `system-health`
tells you the truth: `bridge: alive` plus the open `.blend`. If it is down, the
N-panel (View3D → sidebar → Niua) has Start/Stop and the preference to opt out;
`NIUA_BLENDER_MCP_AUTOSTART=0` / `NIUA_BLENDER_MCP_PORT=<port>` override it.

## Observe

- **Numbers first:** `feedback-readiness` and `feedback-quality`. No images.
- **Look:** `feedback-critique` (or `feedback-capture` / `feedback-capture_views`). Images arrive as MCP **image parts**. The JSON is `report` / `uv` / view metadata only — `data` is omitted on purpose. Missing JSON `data` is not a failed capture; check `available` and the image parts.
- Do not `read_file` those PNGs after a critique. You already have the images.
- Leave `res` at the tool default (640 on critique). Do not raise it unless asked.
- Prefer `ortho4`. One visual call per turn. No turntable/lookdev loops.
- `feedback-capture` with `view: "current"` renders the **live scene camera** and
  honours `MATERIAL` / `RENDERED` — use it to judge a material. The `ortho4`
  presets frame every mesh in the scene, so a studio floor or backdrop will dwarf
  the subject; hide the set first, or pass `object`.

## Reach past the tool surface

`system-execute_python` is enabled by default and **returns what it learns**:
captured `stdout`, plus a `result` variable if the snippet sets one, plus partial
`stdout` on failure. Use it to answer questions the typed tools do not cover —
engine settings, node graphs, per-vertex data — not to bypass tools that exist.

```
result = {"engine": bpy.context.scene.render.engine,
          "raytracing": bpy.context.scene.eevee.use_raytracing}
```

If a call is refused, `system-health`'s `python_enabled` is the **effective**
answer for both gates (the add-on preference AND the server's
`NIUA_BLENDER_MCP_ALLOW_PYTHON`).

## Trust the reports

Derived fields (`matrix_world`, `dimensions`) come back **fresh** after a mutation
as of 0.2.2 — a read-back no longer contradicts the edit that just happened. If
one still looks stale, that is a bug worth reporting, not something to work around
by applying the edit twice.

## Finish

`session-checkpoint` → one edit → re-measure `feedback-readiness` +
`feedback-preservation` → keep or `session-revert`.

Long unattended passes: `scripts/run_skill.py --skill make_game_ready` so
intermediates never enter chat.
