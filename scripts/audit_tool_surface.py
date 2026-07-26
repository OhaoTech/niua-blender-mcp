"""Exercise every shipped tool against a live Blender and report what is actually broken.

The unit tests run against a fake bpy, so they prove the dispatch plumbing, not that the
Blender call underneath still exists. Blender's Python API drifts between releases and a
tool can rot silently for a whole major version. This walks the real surface.

Reading the output matters as much as running it. A tool that rejects a bad argument is
*working* -- the validation is the feature -- so results are classified, not merely
pass/fail:

    ok           the handler ran and returned
    precondition refused for a stated reason (no armature selected, not a mesh, ...)
    invalid      the ARGUMENTS were wrong; this harness guessed them, so it is a
                 harness problem until proven otherwise, never a tool verdict
    unknown      the command does not exist -- a genuine hole
    error        the handler raised: the real bug signal
    crash        Blender died. The worst kind: it takes the session with it.

Nothing here is a verdict on its own. Anything in `error`/`crash`/`unknown` needs hand
verification before it is called broken -- guessed arguments produce false positives, and
this repo has a history of "bugs" that turned out to be the caller passing `objects` where
the tool wanted `object`.

Usage::

    python scripts/audit_tool_surface.py --port 8765
    python scripts/audit_tool_surface.py --only mesh,uv --out /tmp/audit.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import socket
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from niua_blender_mcp.bridge import BlenderBridge  # noqa: E402

#: Tools that would end the session, replace the scene, or write outside a temp dir.
#: They are not skipped because they are trusted -- they are reported as `manual` so the
#: audit stays honest about what it did not cover, and are checked by hand instead.
MANUAL_ONLY = {
    "app.file_new",        # wipes the scene
    "app.file_open",       # replaces the scene
    "app.file_revert",     # discards everything since the last save
    "app.file_save",       # writes over the user's file
    "app.preferences_save",  # persistent change to the user's Blender install
    "app.addon_disable",   # can disable this very add-on and kill the bridge
    "app.addon_enable",
    "script.reload",       # re-imports scripts under a running add-on
    "script.run_file",     # executes an arbitrary file
    "system.cancel",       # cancels the in-flight operation, i.e. this call
    "session.revert",      # rolls the scene back mid-audit
    "ui.operator_invoke",  # invokes an arbitrary operator by name
}

#: Fixture objects, created directly through bpy so the audit does not depend on the
#: create tools it is auditing. Domain prefix -> the object a tool of that domain wants.
FIXTURE_SETUP = """
import bpy

# A tool left in EDIT mode makes every later tool fail for the wrong reason.
try:
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
except Exception:
    pass

for name in list(bpy.data.objects.keys()):
    if name.startswith("AUD_"):
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj

mesh = bpy.data.meshes.new("AUD_meshdata")
import bmesh
bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2.0); bm.to_mesh(mesh); bm.free()
link(bpy.data.objects.new("AUD_mesh", mesh))
link(bpy.data.objects.new("AUD_mesh2", mesh.copy()))
link(bpy.data.objects.new("AUD_camera", bpy.data.cameras.new("AUD_cameradata")))
link(bpy.data.objects.new("AUD_light", bpy.data.lights.new("AUD_lightdata", type="POINT")))
link(bpy.data.objects.new("AUD_armature", bpy.data.armatures.new("AUD_armaturedata")))
link(bpy.data.objects.new("AUD_curve", bpy.data.curves.new("AUD_curvedata", type="CURVE")))
link(bpy.data.objects.new("AUD_text", bpy.data.curves.new("AUD_textdata", type="FONT")))
link(bpy.data.objects.new("AUD_lattice", bpy.data.lattices.new("AUD_latticedata")))
link(bpy.data.objects.new("AUD_speaker", bpy.data.speakers.new("AUD_speakerdata")))
link(bpy.data.objects.new("AUD_empty", None))
try:
    link(bpy.data.objects.new("AUD_pointcloud", bpy.data.pointclouds.new("AUD_pcdata")))
except Exception:
    pass
try:
    link(bpy.data.objects.new("AUD_volume", bpy.data.volumes.new("AUD_voldata")))
except Exception:
    pass
bpy.context.view_layer.objects.active = bpy.data.objects["AUD_mesh"]
bpy.data.objects["AUD_mesh"].select_set(True)
"""

DOMAIN_FIXTURE = {
    "rig": "AUD_armature", "camera": "AUD_camera", "light": "AUD_light",
    "text": "AUD_text", "lattice": "AUD_lattice", "speaker": "AUD_speaker",
    "volume": "AUD_volume", "pointcloud": "AUD_pointcloud",
}


def fixture_for(tool: str) -> str:
    return DOMAIN_FIXTURE.get(tool.split(".")[0], "AUD_mesh")


def synthesize(tool: str, params: dict, tmp: pathlib.Path) -> dict:
    """A plausible valid call: required params only, so defaults do the rest."""
    args: dict = {}
    for name, spec in params.items():
        if not spec.get("required") and name not in ("object", "objects"):
            continue
        kind = (spec.get("kind") or "").lower()
        choices, default = spec.get("choices"), spec.get("default")

        if name in ("object", "objects"):
            args[name] = fixture_for(tool)
        elif choices:
            args[name] = default if default in choices else choices[0]
        elif default is not None:
            args[name] = default
        elif "int" in kind:
            args[name] = 1
        elif "float" in kind or "number" in kind:
            args[name] = 1.0
        elif "bool" in kind:
            args[name] = False
        elif "vec" in kind or "array" in kind or "list" in kind:
            args[name] = [0.0, 0.0, 0.0]
        elif "path" in name or "file" in name:
            args[name] = str(tmp / f"audit_{tool.replace('.', '_')}.txt")
        elif name == "code":
            args[name] = "pass"
        elif name in ("name", "new_name"):
            args[name] = f"AUD_new_{tool.split('.')[-1]}"
        else:
            args[name] = "AUD_mesh" if "object" in name else "x"
    return args


def classify(exc: Exception | None, result) -> tuple[str, str]:
    if exc is None:
        return "ok", ""
    text = str(exc)
    lowered = text.lower()
    for token, verdict in (("unknown command", "unknown"), ("unknown_tool", "unknown"),
                           ("invalid_params", "invalid"), ("is required", "invalid"),
                           ("must be", "invalid"), ("unsupported", "invalid"),
                           ("precondition", "precondition"), ("not a mesh", "precondition"),
                           ("not found", "precondition"), ("no active", "precondition"),
                           # Blender operators refuse with their own prose. These are the
                           # operator declining, not the tool failing to reach it.
                           ("selected", "precondition"), ("nothing to", "precondition"),
                           ("requires", "precondition"), ("no valid", "precondition"),
                           ("not supported for", "precondition"), ("cannot be used", "precondition")):
        if token in lowered:
            return verdict, text[:160]
    return "error", text[:220]


def bridge_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def relaunch(port: int, addon_dir: str, log: pathlib.Path) -> bool:
    subprocess.Popen(
        ["blender", "--python", str(REPO / "scripts" / "blender_gui.py"), "--",
         addon_dir, str(port), "1"],
        stdout=log.open("a"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        if bridge_alive(port):
            return True
        time.sleep(1)
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--addon-dir", default=str(REPO / "dist" / "addon-product"))
    ap.add_argument("--only", default="", help="comma-separated domain prefixes")
    ap.add_argument("--out", type=pathlib.Path, default=REPO / "dist" / "tool-audit.json")
    ap.add_argument("--tools-json", type=pathlib.Path, required=True,
                    help="tool name -> {mutates, params} map to audit")
    args = ap.parse_args(argv)

    tmp = pathlib.Path("/tmp/tool_audit"); tmp.mkdir(exist_ok=True)
    log = pathlib.Path("/tmp/tool_audit/blender.log")
    tools: dict = json.loads(args.tools_json.read_text())
    if args.only:
        wanted = tuple(p.strip() + "." for p in args.only.split(","))
        tools = {n: v for n, v in tools.items() if n.startswith(wanted)}

    bridge = BlenderBridge(port=args.port, timeout=180.0)

    def prepare() -> None:
        try:
            bridge.call("system.execute_python", {"code": FIXTURE_SETUP})
        except Exception as exc:  # noqa: BLE001
            print(f"!! fixture setup failed: {str(exc)[:160]}", flush=True)

    prepare()
    # read-only first: they cannot disturb the fixtures, so a later failure is real
    order = sorted(tools, key=lambda n: (tools[n]["mutates"], n))
    results: dict[str, dict] = {}

    for index, tool in enumerate(order, 1):
        if tool in MANUAL_ONLY:
            results[tool] = {"verdict": "manual", "detail": "excluded from the sweep by design"}
            continue

        call_args = synthesize(tool, tools[tool]["params"], tmp)
        exc = None
        result = None
        try:
            result = bridge.call(tool, call_args)
        except Exception as e:  # noqa: BLE001
            exc = e

        if exc is not None and not bridge_alive(args.port):
            results[tool] = {"verdict": "crash", "args": call_args,
                             "detail": "Blender died on this call"}
            print(f"[{index}/{len(order)}] {tool}: CRASH -- relaunching", flush=True)
            if not relaunch(args.port, args.addon_dir, log):
                print("could not relaunch Blender; stopping", flush=True)
                break
            prepare()
            continue

        verdict, detail = classify(exc, result)
        results[tool] = {"verdict": verdict, "args": call_args, "detail": detail}
        if verdict in ("error", "unknown"):
            print(f"[{index}/{len(order)}] {tool}: {verdict.upper()} {detail}", flush=True)

        if tools[tool]["mutates"] and index % 25 == 0:
            prepare()  # periodically restore the fixtures mutating tools chew through

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1))
    tally: dict[str, int] = {}
    for entry in results.values():
        tally[entry["verdict"]] = tally.get(entry["verdict"], 0) + 1
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
