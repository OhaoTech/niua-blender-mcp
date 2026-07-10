# Product hardening — ratified direction (2026-07-10)

Founder decision: make the project top-tier WITHOUT continuing Part-2 finishing craft (bake-transfer
and fidelity axis stay parked). Execute in this order: **(1) Reliability → (2) Agent ergonomics →
(4) Observability**, with (3) packaging and (5) benchmark-widening as later background tracks.

## Workstream 1 — Reliability (the bridge survives anything)
Evidence: this branch's history (Blender wedge on long feedback.quality; pkill/relaunch race;
StructRNA-removed class of crashes).
- `system.health` tool: bridge liveness, Blender version, queue depth, last-error ring buffer.
- Per-call timeout tiers declared on ToolSpec (fast reads ~5s / normal ops ~60s / heavy ops ~600s)
  instead of one global bridge timeout; server enforces per spec.
- Long-op progress + cancellation: heavy operations report progress via the queue and accept a
  cancel; the main thread must never look wedged.
- Supervisor: `scripts/blender_serve.py`-level watchdog — detect dead bridge, relaunch Blender,
  restore last session state (open .blend), reconnect. One command, self-healing.

## Workstream 2 — Agent ergonomics (the customer is an LLM)
- `capabilities.describe_tools`-style navigation (mirror the niua-godot MCP pattern): no-args →
  domain map; {domain} → its tools; {name} → one schema. Stop dumping 298 specs into context.
- Teaching errors: every error names the fix and the right next call (extend the gates' style to
  the whole hands surface).
- Param-convention unification audit: comma-string vs list, object-vs-objects, defaults — one
  written convention, enforced by a spec-lint test.
- Metric: "turns for a fresh agent to finish an asset" — track it in the bench report.

## Workstream 4 — Observability (session replay)
- Record every mutating tool call (name, params, duration, result summary, optional thumbnail)
  to a session log (JSONL) via dispatch middleware.
- `scripts/session_report.py`: generate the before/after HTML report from a session log
  automatically (the gallery that earned trust, as a standing artifact).

Constraints carried forward: tool surface changes must keep parity green; interface/finishing
boundary respected (all of this is interface-layer except bench-report glue); objective bench
stays byte-identical in baseline mode; ZERO niua knowledge in code.
