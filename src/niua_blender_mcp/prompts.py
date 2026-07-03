"""MCP prompts: reusable workflow scaffolds the agent can pull in.

The server has the *primitives* (observe = ``feedback.critique`` / ``feedback.quality``,
safe-iterate = ``session.checkpoint`` / ``session.revert``); these prompts package the
**recipe** for using them so the do->observe->judge->revert loop is one prompt away
instead of re-derived each session. They are generic Blender workflows — nothing here is
tied to any particular asset pipeline.

Each prompt is described by a :class:`Prompt` (name + description + optional arguments) and
renders to MCP prompt messages via :func:`render`. The server exposes them through
``prompts/list`` (metadata) and ``prompts/get`` (rendered messages).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

JSON = dict[str, Any]


@dataclass(frozen=True)
class PromptArg:
    name: str
    description: str
    required: bool = False

    def to_meta(self) -> JSON:
        return {"name": self.name, "description": self.description, "required": self.required}


@dataclass(frozen=True)
class Prompt:
    name: str
    description: str
    render: Callable[[dict[str, Any]], str]
    arguments: list[PromptArg] = field(default_factory=list)

    def to_meta(self) -> JSON:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [a.to_meta() for a in self.arguments],
        }


def _target(args: dict[str, Any]) -> str:
    """Render the object clause from an optional 'object' argument."""
    obj = args.get("object")
    if isinstance(obj, str) and obj.strip():
        return f"the object named '{obj.strip()}'"
    return "the active object"


def _refine_mesh(args: dict[str, Any]) -> str:
    target = _target(args)
    obj = args.get("object")
    obj_arg = f'"object": "{obj}"' if isinstance(obj, str) and obj.strip() else "(omit to use the active object)"
    return f"""You are refining {target} in a live Blender through this MCP. Drive the
do -> observe -> judge -> keep-or-revert loop yourself; the MCP gives you the primitives
but never runs the loop for you. You are the critic — you are multimodal, so look at the
rendered angles AND read the numbers.

Loop:

1. CHECKPOINT a known-good state: call `session.checkpoint` with {{{obj_arg}}}. This snapshots
   the object's data + transform into a dedicated store, independent of Blender's shared undo.

2. MAKE ONE EDIT — a single deliberate change (`mesh.*`, `modifiers.*`, `rna.call_operator`,
   etc.). One change per iteration so you can attribute the result.

3. OBSERVE: call `feedback.critique` with {{{obj_arg}}}. You get back, in one round-trip:
   - multi-angle images (silhouette / proportion / the anti-blob view), and
   - `report` including a compact `quality` sub-dict (quad_ratio, ngon_ratio, pole_count,
     non_manifold_edges, loose_verts, symmetry, aspect_ratio, transform_applied).
   For the full objective block (topology / symmetry / proportion / scale broken out) call
   `feedback.quality`.

4. JUDGE against concrete targets, not vibes:
   - Silhouette & proportion: from the images — does the form read correctly from every angle?
     Cross-check `proportion.aspect_ratio` (extreme ratios = a stretched/lopsided shape).
   - Symmetry: if the form is meant to be symmetric, `symmetry.symmetry_x/y/z` should be near
     1.0 on the intended axis; a low value means it is lopsided.
   - Topology: prefer high `quad_ratio`, low `ngon_ratio`, low `pole_count`, and
     `non_manifold_edges == 0` and `loose_verts == 0` (those last two are hard defects).
   - Do-no-harm: after establishing a baseline with `feedback.capture_intake` (once, at intake),
     call `feedback.preservation` to check the silhouette IoU vs that baseline. A drop below ~0.85
     (or `bbox_delta.changed == true`) means the form itself was altered — that is HARM on a finisher,
     even if the topology numbers improved.
   - Game-ready: call `feedback.readiness` for the objective definition-of-done — the fraction of
     all game-ready gates passed (topology / UV / material / engine / export), aggregated in no
     order. Read `per_group` to see which axis is blocking.

5. KEEP OR REVERT:
   - If the edit improved the form against the targets, keep it and `session.checkpoint`
     again to make it the new baseline.
   - If it regressed (worse silhouette, broke symmetry, introduced non-manifold/loose geometry,
     dropped quad_ratio), call `session.revert` with {{{obj_arg}}} and try a different edit.

   THE CORE LOOP (do no harm while making it game-ready): once per subject, `feedback.capture_intake`
   to set the baseline. Then, each iteration: `session.checkpoint` -> make ONE edit -> re-measure
   `feedback.readiness` AND `feedback.preservation` -> KEEP the edit only if readiness went up (or
   held) AND preservation stayed >= 0.85; otherwise `session.revert`. This keeps the pass a monotone
   hill-climb that cannot score below where it started — the machine does not revert for you.

6. REPEAT until the quality targets are met: clean silhouette from all angles, intended
   symmetry ~1.0, quad-dominant topology, zero non-manifold edges and loose verts.

Stop when the form is right or when further edits stop improving the metrics."""


def _inspect(args: dict[str, Any]) -> str:
    target = _target(args)
    obj = args.get("object")
    obj_arg = f'"object": "{obj}"' if isinstance(obj, str) and obj.strip() else "(omit to use the active object)"
    return f"""Do a READ-ONLY assessment of {target} before proposing any edits. Make no
mutations — only gather facts and form a judgment.

1. SCENE: call `scene.info` to see what exists (objects, the active object, counts).

2. OBSERVE: call `feedback.critique` with {{{obj_arg}}} for the bundle — multi-angle images
   plus the analytic `report` (with its compact `quality` sub-dict).

3. MEASURE: call `feedback.quality` with {{{obj_arg}}} for the full objective block:
   - topology (faces, tris, quads, ngons, quad_ratio, ngon_ratio, pole_count,
     non_manifold_edges, loose_verts),
   - symmetry (symmetry_x / symmetry_y / symmetry_z — mirror-partner fractions),
   - proportion (bbox_dimensions, aspect_ratio, boxiness),
   - scale (bbox_dimensions, transform_applied).

4. REPORT what you found and ONLY THEN propose concrete edits: call out broken symmetry, n-gons,
   poles, non-manifold edges, loose verts, extreme aspect ratios, or an unapplied transform, and
   say which edit would address each. Do not run the edits in this assessment step."""


PROMPTS: list[Prompt] = [
    Prompt(
        name="refine_mesh",
        description=(
            "Scaffold the iterative refinement loop: checkpoint -> edit -> "
            "feedback.critique (images + quality) -> judge -> keep or session.revert -> repeat "
            "until quality targets are met."
        ),
        render=_refine_mesh,
        arguments=[PromptArg("object", "Object to refine; defaults to the active object", required=False)],
    ),
    Prompt(
        name="inspect",
        description=(
            "Guide a read-only assessment (scene.info -> feedback.critique -> feedback.quality) "
            "before proposing any edits."
        ),
        render=_inspect,
        arguments=[PromptArg("object", "Object to inspect; defaults to the active object", required=False)],
    ),
]

_BY_NAME = {p.name: p for p in PROMPTS}


def list_prompts() -> list[JSON]:
    """Metadata for ``prompts/list``."""
    return [p.to_meta() for p in PROMPTS]


def get_prompt(name: str, arguments: dict[str, Any] | None) -> JSON:
    """Render a prompt for ``prompts/get``. Raises KeyError if the name is unknown."""
    prompt = _BY_NAME[name]
    text = prompt.render(arguments or {})
    return {
        "description": prompt.description,
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }
