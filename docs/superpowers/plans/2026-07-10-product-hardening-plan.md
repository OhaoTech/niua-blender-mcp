# Product Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the MCP-to-Blender product along the ratified spec (docs/superpowers/specs/2026-07-10-product-hardening.md): Workstream 1 reliability (health, timeout tiers, progress/cancel, supervisor), Workstream 2 agent ergonomics (tool navigation, teaching errors, param-convention lint, turns metric), Workstream 4 observability (session JSONL log + HTML replay report) — in that order.

**Architecture:** Everything is interface-layer (Part 1) except the bench-report glue in Task 9. Server side: `ToolSpec` gains a validated `timeout_tier`; the server enforces it per call and answers one new tool (`capabilities.tools`) locally from the router without a bridge round-trip. Add-on side: `bridge_server.py` gains a wire-carried per-request timeout, a last-error ring buffer, and a thread-safe operation table with sideband (never-enqueued) `system.operations`/`system.cancel` so a wedged main thread can still be observed and cancelled. A dependency-injected `Supervisor` state machine (offline-testable) drives a self-healing launcher script. Observability is server-dispatch middleware writing JSONL, rendered by a zero-dependency script.

**Tech Stack:** Python 3 stdlib only (matching the repo: no new dependencies). pytest offline suite with fake-bpy doubles. Live checks via `scripts/blender_gui.py` + `scripts/bridge_call.py`.

## Global Constraints

Copied verbatim from the ratified spec + current repo state. Every task's requirements implicitly include this section.

- **Parity green:** tool surface changes must keep parity green (`tests/test_parity.py`: every server tool's command must have a matching add-on handler, and vice versa; a `generated`-tier spec dispatches as `capabilities.invoke`).
- **Interface/finishing boundary respected:** `tests/test_layer_boundary.py` defines it — interface modules must never import `finishing`/`evals`, at any nesting depth. All of this plan is interface-layer except bench-report glue (Task 9, which edits `scripts/run_objective_benchmark.py`, already in the evals-importing script zone).
- **Objective bench stays byte-identical in baseline mode:** `python scripts/run_objective_benchmark.py --no-godot` must keep per-item readiness **0.36 / 0.36 / 0.36 / 0.24 / 0.28** with preservation **1.0** on every item. (Note: `meta.timestamp` already varies run-to-run; "byte-identical" binds the `items` and `reading` sections. Task 9 adds new keys to `meta` only.)
- **ZERO niua knowledge in code.** No niua-generator or niua-platform concepts in any code path.
- **Offline suite baseline:** `NIUA_SKIP_BLENDER=1 python -m pytest -q` currently reports **720 passed, 71 skipped**. Every task ends with a full run: previous count + that task's new tests, still 71 skipped, zero failures.
- **Commit trailer on every commit:** `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## File Structure

Created:
- `src/niua_blender_mcp/supervisor.py` — dependency-injected watchdog state machine (Task 5)
- `scripts/blender_supervise.py` — one-command self-healing launcher CLI (Task 5)
- `src/niua_blender_mcp/session_log.py` — JSONL session-log middleware (Task 10)
- `scripts/session_report.py` — HTML replay report generator (Task 11)
- Tests: `tests/test_timeout_tiers.py`, `tests/domains/test_system_health.py`, `tests/test_operations.py`, `tests/test_supervisor.py`, `tests/test_describe_tools.py`, `tests/test_teaching_errors.py`, `tests/test_spec_conventions.py`, `tests/test_bench_turns.py`, `tests/test_session_log.py`, `tests/test_session_report.py`

Modified:
- `src/niua_blender_mcp/kernel/contract.py` (+`timeout_tier`, `TIMEOUT_SECONDS`), `kernel/__init__.py`, `kernel/errors.py` (+`CANCELLED`)
- `src/niua_blender_mcp/bridge.py` (per-call timeout on the wire)
- `src/niua_blender_mcp/server.py` (tier enforcement, `LOCAL_COMMANDS` + `capabilities.tools`, teaching errors, session-log wiring)
- `src/niua_blender_mcp/domains/{system.py, capabilities.py, io.py, finishing_feedback.py, context.py, outliner.py}`
- `blender_addon/niua_mcp_bridge/{bridge_server.py, dispatch.py, context.py, errors.py}`
- `blender_addon/niua_mcp_bridge/domains/{system.py, io.py, finishing_feedback.py}`
- `scripts/run_objective_benchmark.py` (Task 9, bench-report glue)
- `tests/test_parity.py` (timeout-tier mirror + `LOCAL_COMMANDS` exemption)

---

# Workstream 1 — Reliability

### Task 1: `ToolSpec.timeout_tier` + server-side per-call timeout enforcement

Per-call timeout tiers declared on ToolSpec (fast ~5s / normal ~60s / heavy ~600s) instead of one global bridge timeout; the server enforces per spec. This task is the server half; Task 2 makes the add-on honor the wire timeout and mirrors the field onto `Command`.

**Files:**
- Modify: `src/niua_blender_mcp/kernel/contract.py`
- Modify: `src/niua_blender_mcp/kernel/__init__.py`
- Modify: `src/niua_blender_mcp/bridge.py`
- Modify: `src/niua_blender_mcp/server.py`
- Modify: `src/niua_blender_mcp/domains/io.py` (mark `io.import`, `io.export`, `io.prepare_asset` heavy)
- Modify: `src/niua_blender_mcp/domains/finishing_feedback.py` (mark the five heavy feedback tools; this file is a declared policy area, editable — `tests/test_layer_boundary.py` locks its tool *names* only)
- Test: `tests/test_timeout_tiers.py` (new)

**Interfaces:**
- Consumes: `ToolSpec` (frozen dataclass, `kernel/contract.py`), `BlenderBridge.call(command, payload)` (`bridge.py`), `NiuaBlenderMCP._tools_call` (`server.py`).
- Produces: `ToolSpec.timeout_tier: str = "normal"` (validated against `{"fast","normal","heavy"}` in `__post_init__`); `TIMEOUT_SECONDS: dict[str, float] = {"fast": 5.0, "normal": 60.0, "heavy": 600.0}` exported from `niua_blender_mcp.kernel`; `BlenderBridge.call(command: str, payload: dict | None = None, timeout: float | None = None) -> dict` which embeds `"timeout": <seconds>` in the wire request JSON. Tasks 2, 3, 4, 5, 9 rely on these exact signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_timeout_tiers.py`:

```python
"""Per-call timeout tiers: ToolSpec declares fast/normal/heavy, the server enforces
per spec, and the bridge carries the chosen timeout on the wire so the add-on's
main-thread wait matches (add-on side is Task 2 / tests/test_dispatch.py)."""

from __future__ import annotations

import contextlib
import json
import socket
import threading

import pytest

from niua_blender_mcp.bridge import BlenderBridge
from niua_blender_mcp.domains import build_router
from niua_blender_mcp.kernel import TIMEOUT_SECONDS, Router, ToolSpec
from niua_blender_mcp.server import create_server


@contextlib.contextmanager
def fake_server(responder):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        with contextlib.suppress(OSError):
            conn, _ = srv.accept()
            with conn:
                line = conn.makefile("rb").readline()
                request = json.loads(line.decode("utf-8"))
                conn.sendall((json.dumps(responder(request)) + "\n").encode("utf-8"))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        srv.close()
        thread.join(timeout=2)


class RecordingBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.timeouts: list[float | None] = []

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        self.timeouts.append(timeout)
        return {"ok": True}


def test_timeout_tier_default_is_normal() -> None:
    spec = ToolSpec(name="x.y", category="x", summary="s", command="x.y")
    assert spec.timeout_tier == "normal"


def test_unknown_timeout_tier_rejected() -> None:
    with pytest.raises(ValueError, match="unknown timeout tier"):
        ToolSpec(name="x.y", category="x", summary="s", command="x.y", timeout_tier="slow")


def test_tier_seconds_are_fast_normal_heavy() -> None:
    assert TIMEOUT_SECONDS == {"fast": 5.0, "normal": 60.0, "heavy": 600.0}


def test_per_call_timeout_travels_on_the_wire() -> None:
    seen: dict = {}

    def responder(request):
        seen.update(request)
        return {"ok": True, "result": {}}

    with fake_server(responder) as port:
        BlenderBridge(port=port).call("scene.info", {}, timeout=600.0)
    assert seen["timeout"] == 600.0


def test_default_timeout_travels_on_the_wire_too() -> None:
    seen: dict = {}

    def responder(request):
        seen.update(request)
        return {"ok": True, "result": {}}

    with fake_server(responder) as port:
        BlenderBridge(port=port, timeout=30.0).call("scene.info", {})
    assert seen["timeout"] == 30.0


def test_server_dispatches_tier_timeouts() -> None:
    router = Router()
    router.add(
        [
            ToolSpec(name="t.heavy", category="t", summary="s", command="t.heavy", timeout_tier="heavy"),
            ToolSpec(name="t.fast", category="t", summary="s", command="t.fast", timeout_tier="fast"),
            ToolSpec(name="t.normal", category="t", summary="s", command="t.normal"),
        ]
    )
    bridge = RecordingBridge()
    server = create_server(bridge=bridge, router=router)
    server._tools_call({"name": "t.heavy", "arguments": {}})
    server._tools_call({"name": "t.fast", "arguments": {}})
    server._tools_call({"name": "t.normal", "arguments": {}})
    assert bridge.timeouts == [600.0, 5.0, 60.0]


def test_heavy_measure_and_io_tools_are_marked_heavy() -> None:
    router = build_router()
    heavy = [
        "feedback.quality",
        "feedback.readiness",
        "feedback.preservation",
        "feedback.capture_intake",
        "feedback.critique",
        "io.import",
        "io.export",
        "io.prepare_asset",
    ]
    for name in heavy:
        assert router.get(name).timeout_tier == "heavy", name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_timeout_tiers.py -v`
Expected: FAIL — `ImportError: cannot import name 'TIMEOUT_SECONDS'` (and, once that exists, `TypeError: ... unexpected keyword argument 'timeout_tier'`).

- [ ] **Step 3: Implement**

In `src/niua_blender_mcp/kernel/contract.py`, after the `_KINDS` line add:

```python
#: Per-call timeout tiers a ToolSpec may declare. The MCP server enforces these on
#: every dispatch (bridge.call(..., timeout=TIMEOUT_SECONDS[spec.timeout_tier])) and the
#: add-on's main-thread wait honors the same number carried on the wire (bridge_server).
TIMEOUT_SECONDS: dict[str, float] = {"fast": 5.0, "normal": 60.0, "heavy": 600.0}
```

In the `ToolSpec` dataclass add one field (after `tier`) and a `__post_init__`:

```python
    timeout_tier: str = "normal"  # "fast" (~5s reads) | "normal" (~60s ops) | "heavy" (~600s measures/IO)

    def __post_init__(self) -> None:
        if self.timeout_tier not in TIMEOUT_SECONDS:
            raise ValueError(f"unknown timeout tier: {self.timeout_tier}")
```

In `src/niua_blender_mcp/kernel/__init__.py` extend the contract import and `__all__`:

```python
from .contract import TIMEOUT_SECONDS, Bool, Enum, Float, Int, Param, Str, ToolSpec, Vec3, validate
```

and add `"TIMEOUT_SECONDS",` to `__all__`.

In `src/niua_blender_mcp/bridge.py` replace the `call` method:

```python
    def call(self, command: str, payload: dict | None = None, timeout: float | None = None) -> dict[str, Any]:
        # The chosen timeout rides on the wire so the add-on's main-thread wait matches;
        # the socket gets +5s grace so the add-on's structured timeout error (not a raw
        # socket cut) is what the caller sees.
        wait = self.timeout if timeout is None else timeout
        request = json.dumps({"command": command, "payload": payload or {}, "timeout": wait}) + "\n"
        try:
            with socket.create_connection((self.host, self.port), timeout=wait + 5.0) as sock:
                sock.settimeout(wait + 5.0)
                sock.sendall(request.encode("utf-8"))
                line = sock.makefile("r", encoding="utf-8").readline()
        except OSError as exc:
            raise BridgeError(
                TRANSPORT, f"cannot reach Blender bridge at {self.host}:{self.port}: {exc}"
            ) from exc
```

(rest of the method unchanged).

In `src/niua_blender_mcp/server.py`: import `TIMEOUT_SECONDS` (extend the existing kernel import to `from .kernel import McpError, Router, validate` → add `TIMEOUT_SECONDS`), then in `_tools_call` replace the dispatch block:

```python
        timeout = TIMEOUT_SECONDS[spec.timeout_tier]
        try:
            if spec.tier == "generated":
                result = self.bridge.call(
                    "capabilities.invoke",
                    {"idname": spec.command, "args": json.dumps(clean)},
                    timeout=timeout,
                )
            else:
                result = self.bridge.call(spec.command, clean, timeout=timeout)
        except BridgeError as exc:
            return self._tool_error(exc.code, exc.message, exc.detail)
```

`tests/test_server.py`'s `RecordingBridge.call(self, command, payload)` must accept the new kwarg — change its signature to `def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:` (body unchanged).

Mark heavy tiers. In `src/niua_blender_mcp/domains/io.py` add `timeout_tier="heavy",` inside the three `ToolSpec(...)` entries named `io.import`, `io.export`, `io.prepare_asset` (one line each, next to `command=`). In `src/niua_blender_mcp/domains/finishing_feedback.py` add `timeout_tier="heavy",` to the five `ToolSpec(...)` entries named `feedback.quality`, `feedback.critique`, `feedback.capture_intake`, `feedback.preservation`, `feedback.readiness` (leave `io.profile_validate` at the default).

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_timeout_tiers.py -v`
Expected: 7 passed.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 727 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/kernel/contract.py src/niua_blender_mcp/kernel/__init__.py \
        src/niua_blender_mcp/bridge.py src/niua_blender_mcp/server.py \
        src/niua_blender_mcp/domains/io.py src/niua_blender_mcp/domains/finishing_feedback.py \
        tests/test_timeout_tiers.py tests/test_server.py
git commit -m "feat: per-call timeout tiers on ToolSpec; server enforces per spec

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Add-on honors the wire timeout; `Command` mirrors `timeout_tier`; parity guards it

The add-on's `_Handler` currently hardcodes a 60s wait. It must use the timeout the client sent (clamped to [1s, 600s]), and the add-on `Command` mirror gains the same `timeout_tier` field so parity can catch tier drift between the two halves.

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/bridge_server.py`
- Modify: `blender_addon/niua_mcp_bridge/dispatch.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/io.py`
- Modify: `blender_addon/niua_mcp_bridge/domains/finishing_feedback.py`
- Modify: `tests/test_parity.py`
- Test: `tests/test_operations.py` (new file, started here; Task 4 extends it)

**Interfaces:**
- Consumes: wire field `"timeout"` produced by `BlenderBridge.call` (Task 1); `Command` dataclass (`dispatch.py`); `_enqueue(command, payload, timeout)` (`bridge_server.py`).
- Produces: `Command.timeout_tier: str = "normal"`; `bridge_server._clamp_timeout(value: Any) -> float` (default 60.0, clamped to [1.0, 600.0]). The parity metadata test asserting `command.timeout_tier == spec.timeout_tier` is what every later tier assignment must satisfy (Tasks 3 and 4 set `timeout_tier="fast"` on both sides of their new tools).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_operations.py` (Task 4 will extend this file with op-table tests):

```python
"""Add-on request-timeout handling and (Task 4) the operation table + cancellation."""

from __future__ import annotations

from niua_mcp_bridge import bridge_server


def _drain_queue() -> None:
    """Leave the module-global request queue empty for other tests."""
    while not bridge_server._REQUESTS.empty():
        bridge_server._REQUESTS.get_nowait()


def test_clamp_timeout_defaults_and_bounds() -> None:
    assert bridge_server._clamp_timeout(None) == 60.0
    assert bridge_server._clamp_timeout("nonsense") == 60.0
    assert bridge_server._clamp_timeout(5.0) == 5.0
    assert bridge_server._clamp_timeout(0.001) == 1.0
    assert bridge_server._clamp_timeout(9999) == 600.0


def test_enqueue_times_out_with_structured_error() -> None:
    # Nothing is draining the queue, so a tiny wait must return the structured
    # timeout error (not hang, not raise).
    response = bridge_server._enqueue("slow.op", {}, 0.05)
    _drain_queue()
    assert response["ok"] is False
    assert response["error"]["code"] == "timeout"
    assert response["error"]["message"].startswith("slow.op exceeded")
```

Extend `tests/test_parity.py` — replace `test_server_command_metadata_matches_addon_handlers` with:

```python
def test_server_command_metadata_matches_addon_handlers() -> None:
    registry = build_default_registry()
    for spec in build_router().specs():
        command_name = "capabilities.invoke" if spec.tier == "generated" else spec.command
        command = registry.get(command_name)
        assert command is not None
        assert command.mutates == spec.mutates, command_name
        assert command.feedback == spec.feedback, command_name
        if spec.tier != "generated":
            # Generated specs all dispatch through capabilities.invoke; their own
            # (default) tier is not the invoke command's tier, so only mirror-check
            # the 1:1 commands.
            assert command.timeout_tier == spec.timeout_tier, command_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_operations.py tests/test_parity.py -v`
Expected: `test_clamp_timeout_defaults_and_bounds` FAILS with `AttributeError: ... no attribute '_clamp_timeout'`; parity metadata FAILS with `AttributeError: 'Command' object has no attribute 'timeout_tier'`.

- [ ] **Step 3: Implement**

In `blender_addon/niua_mcp_bridge/dispatch.py` add a field to `Command` (after `feedback`):

```python
@dataclass(frozen=True)
class Command:
    name: str
    handler: Handler
    mutates: bool = False
    feedback: str | None = None
    timeout_tier: str = "normal"  # mirror of ToolSpec.timeout_tier; parity-checked
```

In `blender_addon/niua_mcp_bridge/bridge_server.py` add above `_Handler`:

```python
def _clamp_timeout(value) -> float:
    """Per-request wait from the wire (BlenderBridge sends 'timeout'), clamped sane."""
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 60.0
    return min(max(timeout, 1.0), 600.0)
```

and change `_Handler.handle`'s enqueue line to:

```python
            request = json.loads(line.decode("utf-8"))
            timeout = _clamp_timeout(request.get("timeout"))
            response = _enqueue(str(request.get("command", "")), request.get("payload") or {}, timeout)
```

Mirror the heavy tiers from Task 1 on the add-on side. In `blender_addon/niua_mcp_bridge/domains/io.py` change the `COMMANDS` list:

```python
COMMANDS = [
    Command("io.import", import_file, mutates=True, feedback="viewport", timeout_tier="heavy"),
    Command("io.export", export, mutates=False, timeout_tier="heavy"),
    Command("io.prepare_asset", prepare_asset, mutates=True, feedback="viewport", timeout_tier="heavy"),
]
```

(keep any other entries in that list — e.g. `io.profile_validate` lives in `finishing_feedback.py` — exactly as they are). In `blender_addon/niua_mcp_bridge/domains/finishing_feedback.py` add `timeout_tier="heavy"` to the five `Command(...)` entries named `feedback.quality`, `feedback.critique`, `feedback.capture_intake`, `feedback.preservation`, `feedback.readiness` (leave `io.profile_validate` at the default).

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_operations.py tests/test_parity.py -v`
Expected: all pass.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 729 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/bridge_server.py blender_addon/niua_mcp_bridge/dispatch.py \
        blender_addon/niua_mcp_bridge/domains/io.py blender_addon/niua_mcp_bridge/domains/finishing_feedback.py \
        tests/test_parity.py tests/test_operations.py
git commit -m "feat: add-on honors per-request timeout from the wire; Command mirrors timeout_tier (parity-checked)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `system.health` — liveness, Blender version, queue depth, last-error ring buffer

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/bridge_server.py` (error ring + `health_snapshot()`)
- Modify: `blender_addon/niua_mcp_bridge/domains/system.py` (handler + `COMMANDS` entry)
- Modify: `src/niua_blender_mcp/domains/system.py` (ToolSpec)
- Test: `tests/domains/test_system_health.py` (new)

**Interfaces:**
- Consumes: `bridge_server._REQUESTS` queue, `_drain`/`_enqueue`; `Ctx(bpy, allow_python=...)`; `Command(..., timeout_tier=...)` from Task 2.
- Produces: `bridge_server._record_error(command: str, error: dict) -> None`, `bridge_server.health_snapshot() -> dict` (keys: `bridge`, `queue_depth`, `socket_running`, `last_errors`); tool `system.health` returning additionally `blender_version: str`, `blend_path: str`, `python_enabled: bool`. Task 5's supervisor probes `system.health` and reads `blend_path`.

- [ ] **Step 1: Write the failing tests**

Create `tests/domains/test_system_health.py`:

```python
"""system.health: liveness, version, queue depth, and the last-error ring buffer."""

from __future__ import annotations

import types

from niua_mcp_bridge import bridge_server
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry


class FakeBpy:
    def __init__(self) -> None:
        self.app = types.SimpleNamespace(version_string="4.4.0")
        self.data = types.SimpleNamespace(filepath="/tmp/scene.blend")
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="": None))


def test_system_health_reports_liveness_version_queue_and_errors() -> None:
    bridge_server._ERRORS.clear()
    bridge_server._record_error("mesh.boom", {"code": "handler_error", "message": "kaboom"})
    result = dispatch_on_main(build_default_registry(), "system.health", {}, Ctx(FakeBpy()))
    assert result["bridge"] == "alive"
    assert result["blender_version"] == "4.4.0"
    assert result["blend_path"] == "/tmp/scene.blend"
    assert result["queue_depth"] == 0
    assert result["python_enabled"] is False
    assert result["last_errors"][-1]["command"] == "mesh.boom"
    assert result["last_errors"][-1]["code"] == "handler_error"


def test_error_ring_buffer_is_bounded_to_twenty() -> None:
    bridge_server._ERRORS.clear()
    for i in range(30):
        bridge_server._record_error(f"op{i}", {"code": "handler_error", "message": "x"})
    assert len(bridge_server._ERRORS) == 20
    assert bridge_server._ERRORS[0]["command"] == "op10"


def test_enqueue_timeout_lands_in_the_error_ring() -> None:
    bridge_server._ERRORS.clear()
    bridge_server._enqueue("slow.op", {}, 0.05)
    while not bridge_server._REQUESTS.empty():
        bridge_server._REQUESTS.get_nowait()
    assert bridge_server._ERRORS[-1]["command"] == "slow.op"
    assert bridge_server._ERRORS[-1]["code"] == "timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_system_health.py -v`
Expected: FAIL with `AttributeError: ... no attribute '_ERRORS'`.

- [ ] **Step 3: Implement**

In `blender_addon/niua_mcp_bridge/bridge_server.py`:

Add `import collections` to the imports. Below `_LAST_ACTIVITY = 0.0` add:

```python
#: Last-error ring buffer: the most recent N failures crossing the bridge, surfaced by
#: system.health so an agent (or the supervisor) can see what has been going wrong.
_ERRORS: "collections.deque[dict]" = collections.deque(maxlen=20)


def _record_error(command: str, error: dict) -> None:
    _ERRORS.append(
        {
            "command": command,
            "code": str(error.get("code", "unknown")),
            "message": str(error.get("message", ""))[:200],
            "time": time.time(),
        }
    )


def health_snapshot() -> dict:
    """Thread-safe-enough snapshot (qsize/deque reads) used by the system.health tool."""
    return {
        "bridge": "alive",
        "queue_depth": _REQUESTS.qsize(),
        "socket_running": _SERVER is not None,
        "last_errors": list(_ERRORS),
    }
```

In `_enqueue`, record the timeout before returning it:

```python
    if not box.event.wait(timeout):
        error = {"code": "timeout", "message": f"{command} exceeded {timeout}s"}
        _record_error(command, error)
        return {"ok": False, "error": error}
```

In `_drain`, record both error branches:

```python
        except BridgeError as exc:
            box.error = exc.to_dict()
            _record_error(command, box.error)
        except Exception as exc:  # noqa: BLE001
            box.error = {"code": "handler_error", "message": str(exc), "traceback": traceback.format_exc()}
            _record_error(command, box.error)
```

In `blender_addon/niua_mcp_bridge/domains/system.py` add the handler and register it:

```python
def health(ctx: Ctx, payload: dict) -> dict:
    from .. import bridge_server  # noqa: PLC0415 - lazy, matches repo style; no import cycle at runtime

    snapshot = bridge_server.health_snapshot()
    snapshot.update(
        {
            "blender_version": getattr(ctx.bpy.app, "version_string", ""),
            "blend_path": getattr(ctx.bpy.data, "filepath", ""),
            "python_enabled": ctx.allow_python,
        }
    )
    return snapshot
```

```python
COMMANDS = [
    # Wrapped in undo so whatever the snippet mutates is one rollback-able step.
    Command("system.execute_python", execute_python, mutates=True),
    Command("system.health", health, mutates=False, timeout_tier="fast"),
]
```

In `src/niua_blender_mcp/domains/system.py` append to `SPECS`:

```python
    ToolSpec(
        name="system.health",
        category="system",
        summary="Bridge health: Blender version, open .blend, queue depth, last-error ring buffer",
        command="system.health",
        timeout_tier="fast",
    ),
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/domains/test_system_health.py tests/test_parity.py -v`
Expected: all pass (parity stays green: both sides added `system.health` with matching metadata).
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 732 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/bridge_server.py blender_addon/niua_mcp_bridge/domains/system.py \
        src/niua_blender_mcp/domains/system.py tests/domains/test_system_health.py
git commit -m "feat: system.health tool — liveness, Blender version, queue depth, last-error ring buffer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Long-op progress + cancellation (`system.operations` / `system.cancel`, sideband)

An operation table tracks every in-flight command. Handlers report progress cooperatively via `ctx.progress()` and honor `ctx.check_cancelled()`. Crucially, `system.operations` and `system.cancel` are answered **sideband** — directly in the socket thread, never enqueued — so they work even while a heavy op has the main thread busy: the main thread never *looks* wedged, and a wedged op can be cancelled. Both commands are also registered normally (parity + unit tests).

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/bridge_server.py` (op table, sideband dispatch, `_enqueue`/`_drain` integration)
- Modify: `blender_addon/niua_mcp_bridge/context.py` (`Ctx.progress` / `cancelled` / `check_cancelled`)
- Modify: `blender_addon/niua_mcp_bridge/errors.py` (+`CANCELLED`)
- Modify: `src/niua_blender_mcp/kernel/errors.py` (+`CANCELLED`, kept in sync per the errors-module docstring)
- Modify: `blender_addon/niua_mcp_bridge/domains/system.py` (registry handlers)
- Modify: `src/niua_blender_mcp/domains/system.py` (ToolSpecs)
- Test: `tests/test_operations.py` (extend)

**Interfaces:**
- Consumes: `_enqueue`/`_drain`/`_Handler` (`bridge_server.py`), `Ctx.__init__` (`context.py`), `_record_error` (Task 3).
- Produces: `bridge_server._op_start(command: str) -> dict`, `_op_finish(op: dict) -> None`, `list_operations() -> dict` (`{"operations": [{"id","command","started","elapsed","progress","message","done","cancel_requested"}]}`), `cancel_operation(op_id: str) -> dict` (`{"ok": True, "result": {...}}` or `{"ok": False, "error": {...}}`); `Ctx(bpy, allow_python=False, op: dict | None = None)` with `progress(fraction: float, message: str = "") -> None`, `cancelled() -> bool`, `check_cancelled() -> None` (raises `BridgeError(CANCELLED, ...)`); error code `CANCELLED = "cancelled"` on both sides. Any heavy handler may opt in with `ctx.progress(...)` / `ctx.check_cancelled()` inside its loop — no further plumbing needed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_operations.py`:

```python
import types

import pytest

from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.dispatch import dispatch_on_main
from niua_mcp_bridge.domains import build_default_registry
from niua_mcp_bridge.errors import CANCELLED, NOT_FOUND, BridgeError


class FakeBpy:
    def __init__(self) -> None:
        self.app = types.SimpleNamespace(version_string="4.4.0")
        self.data = types.SimpleNamespace(filepath="")
        self.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message="": None))


@pytest.fixture(autouse=True)
def _clean_ops():
    bridge_server._OPS.clear()
    yield
    bridge_server._OPS.clear()


def test_op_lifecycle_progress_and_cancel() -> None:
    op = bridge_server._op_start("mesh.heavy")
    ctx = Ctx(FakeBpy(), op=op)
    ctx.progress(0.5, "halfway")
    listed = bridge_server.list_operations()["operations"]
    mine = next(o for o in listed if o["id"] == op["id"])
    assert mine["command"] == "mesh.heavy"
    assert mine["progress"] == 0.5
    assert mine["message"] == "halfway"
    assert mine["done"] is False

    assert bridge_server.cancel_operation(op["id"])["ok"] is True
    assert ctx.cancelled() is True
    with pytest.raises(BridgeError) as exc:
        ctx.check_cancelled()
    assert exc.value.code == CANCELLED

    bridge_server._op_finish(op)
    finished = next(o for o in bridge_server.list_operations()["operations"] if o["id"] == op["id"])
    assert finished["done"] is True and finished["progress"] == 1.0


def test_ctx_without_op_never_cancels() -> None:
    ctx = Ctx(FakeBpy())
    ctx.progress(0.9)  # no-op, must not raise
    assert ctx.cancelled() is False
    ctx.check_cancelled()  # must not raise


def test_cancel_unknown_op_teaches_next_call() -> None:
    response = bridge_server.cancel_operation("op-nope")
    assert response["ok"] is False
    assert response["error"]["code"] == NOT_FOUND
    assert response["error"]["detail"]["next_call"] == "system.operations"


def test_system_operations_and_cancel_are_registered_commands() -> None:
    registry = build_default_registry()
    ctx = Ctx(FakeBpy())
    op = bridge_server._op_start("mesh.heavy")
    listed = dispatch_on_main(registry, "system.operations", {}, ctx)
    assert any(o["id"] == op["id"] for o in listed["operations"])
    result = dispatch_on_main(registry, "system.cancel", {"op_id": op["id"]}, ctx)
    assert result == {"op_id": op["id"], "was_running": True}
    with pytest.raises(BridgeError) as exc:
        dispatch_on_main(registry, "system.cancel", {"op_id": "op-nope"}, ctx)
    assert exc.value.code == NOT_FOUND


def test_enqueue_timeout_names_the_op_for_cancellation() -> None:
    response = bridge_server._enqueue("slow.op", {}, 0.05)
    _drain_queue()
    detail = response["error"]["detail"]
    assert detail["op_id"].startswith("op-")
    assert detail["next_call"] == "system.operations"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_operations.py -v`
Expected: new tests FAIL (`ImportError: cannot import name 'CANCELLED'`, then `AttributeError: ... '_OPS'`). The two Task-2 tests still pass.

- [ ] **Step 3: Implement**

`blender_addon/niua_mcp_bridge/errors.py` — add after `PYTHON_DISABLED`:

```python
CANCELLED = "cancelled"
```

`src/niua_blender_mcp/kernel/errors.py` — add after `PYTHON_DISABLED`:

```python
CANCELLED = "cancelled"
```

`blender_addon/niua_mcp_bridge/context.py` — replace `__init__` and add three methods:

```python
    def __init__(self, bpy_module: Any, allow_python: bool = False, op: dict | None = None) -> None:
        self.bpy = bpy_module
        self.allow_python = allow_python
        self._op = op  # live operation record (bridge_server._op_start); None in bare tests

    def progress(self, fraction: float, message: str = "") -> None:
        """Cooperative progress for long ops; visible via system.operations."""
        if self._op is not None:
            self._op["progress"] = max(0.0, min(float(fraction), 1.0))
            self._op["message"] = str(message)

    def cancelled(self) -> bool:
        return self._op is not None and self._op["cancel"].is_set()

    def check_cancelled(self) -> None:
        """Raise a structured error if system.cancel was called for this operation."""
        if self.cancelled():
            from .errors import CANCELLED  # noqa: PLC0415 - avoid widening the module import surface

            raise BridgeError(
                CANCELLED,
                "operation cancelled by request",
                {"fix": "the partial work (if any) is one undo step away", "next_call": "system.operations"},
            )
```

`blender_addon/niua_mcp_bridge/bridge_server.py`:

Add `import itertools` to the imports. Below the `_ERRORS` block add:

```python
#: Operation table: every request gets a record; system.operations/system.cancel read it
#: SIDEBAND (socket thread, never enqueued) so a busy main thread never looks wedged.
_OPS: dict[str, dict] = {}
_OPS_LOCK = threading.Lock()
_OP_IDS = itertools.count(1)
_OPS_KEEP = 50


def _op_start(command: str) -> dict:
    op = {
        "id": f"op-{next(_OP_IDS)}",
        "command": command,
        "started": time.time(),
        "progress": 0.0,
        "message": "",
        "done": False,
        "cancel": threading.Event(),
    }
    with _OPS_LOCK:
        _OPS[op["id"]] = op
        done_ids = [k for k, v in _OPS.items() if v["done"]]
        while len(_OPS) > _OPS_KEEP and done_ids:
            del _OPS[done_ids.pop(0)]
    return op


def _op_finish(op: dict) -> None:
    op["done"] = True
    op["progress"] = 1.0


def _op_public(op: dict) -> dict:
    return {
        "id": op["id"],
        "command": op["command"],
        "started": op["started"],
        "elapsed": round(time.time() - op["started"], 3),
        "progress": op["progress"],
        "message": op["message"],
        "done": op["done"],
        "cancel_requested": op["cancel"].is_set(),
    }


def list_operations() -> dict:
    with _OPS_LOCK:
        return {"operations": [_op_public(op) for op in _OPS.values()]}


def cancel_operation(op_id: str) -> dict:
    with _OPS_LOCK:
        op = _OPS.get(op_id)
    if op is None:
        return {
            "ok": False,
            "error": {
                "code": "not_found",
                "message": f"unknown operation: {op_id}",
                "detail": {"fix": "list live operations to find the id", "next_call": "system.operations"},
            },
        }
    op["cancel"].set()
    return {"ok": True, "result": {"op_id": op_id, "was_running": not op["done"]}}
```

Replace `_enqueue`:

```python
def _enqueue(command: str, payload: dict, timeout: float) -> dict:
    global _LAST_ACTIVITY
    _LAST_ACTIVITY = time.time()
    box = _Box()
    op = _op_start(command)
    _REQUESTS.put((command, payload, box, op))
    if not box.event.wait(timeout):
        error = {
            "code": "timeout",
            "message": f"{command} exceeded {timeout}s",
            "detail": {
                "op_id": op["id"],
                "fix": "the operation may still be running on Blender's main thread",
                "next_call": "system.operations",
            },
        }
        _record_error(command, error)
        return {"ok": False, "error": error}
    if box.error is not None:
        return {"ok": False, "error": box.error}
    return {"ok": True, "result": box.value}
```

In `_drain`, update the unpack and hand the op to `Ctx`, finishing it in `finally`:

```python
    while True:
        try:
            command, payload, box, op = _REQUESTS.get_nowait()
        except queue.Empty:
            break
        try:
            ctx = Ctx(bpy, allow_python=_ALLOW_PYTHON, op=op)
            box.value = dispatch_on_main(_REGISTRY, command, payload, ctx)
        except BridgeError as exc:
            box.error = exc.to_dict()
            _record_error(command, box.error)
        except Exception as exc:  # noqa: BLE001
            box.error = {"code": "handler_error", "message": str(exc), "traceback": traceback.format_exc()}
            _record_error(command, box.error)
        finally:
            _op_finish(op)
            box.event.set()
```

In `_Handler.handle`, intercept the sideband commands before enqueueing:

```python
        try:
            request = json.loads(line.decode("utf-8"))
            command = str(request.get("command", ""))
            if command == "system.operations":
                # Sideband: answered on the socket thread so a busy main thread is observable.
                response = {"ok": True, "result": list_operations()}
            elif command == "system.cancel":
                response = cancel_operation(str((request.get("payload") or {}).get("op_id", "")))
            else:
                timeout = _clamp_timeout(request.get("timeout"))
                response = _enqueue(command, request.get("payload") or {}, timeout)
        except Exception as exc:  # noqa: BLE001
            response = {"ok": False, "error": {"code": "internal_error", "message": str(exc)}}
```

`blender_addon/niua_mcp_bridge/domains/system.py` — add handlers + registrations (these run if dispatched on the main thread — unit tests, parity — while live traffic takes the sideband path):

```python
def operations(ctx: Ctx, payload: dict) -> dict:
    from .. import bridge_server  # noqa: PLC0415

    return bridge_server.list_operations()


def cancel(ctx: Ctx, payload: dict) -> dict:
    from .. import bridge_server  # noqa: PLC0415
    from ..errors import NOT_FOUND  # noqa: PLC0415

    response = bridge_server.cancel_operation(str(payload.get("op_id") or ""))
    if not response["ok"]:
        error = response["error"]
        raise BridgeError(NOT_FOUND, error["message"], error.get("detail"))
    return response["result"]
```

```python
COMMANDS = [
    # Wrapped in undo so whatever the snippet mutates is one rollback-able step.
    Command("system.execute_python", execute_python, mutates=True),
    Command("system.health", health, mutates=False, timeout_tier="fast"),
    Command("system.operations", operations, mutates=False, timeout_tier="fast"),
    Command("system.cancel", cancel, mutates=False, timeout_tier="fast"),
]
```

`src/niua_blender_mcp/domains/system.py` — append to `SPECS`:

```python
    ToolSpec(
        name="system.operations",
        category="system",
        summary="List in-flight and recent operations with progress (works even while the main thread is busy)",
        command="system.operations",
        timeout_tier="fast",
    ),
    ToolSpec(
        name="system.cancel",
        category="system",
        summary="Request cancellation of a running operation by id (from system.operations)",
        command="system.cancel",
        params={"op_id": Str(required=True, summary="Operation id, e.g. 'op-7'")},
        timeout_tier="fast",
    ),
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_operations.py tests/test_parity.py tests/domains/test_system_health.py -v`
Expected: all pass.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 737 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/bridge_server.py blender_addon/niua_mcp_bridge/context.py \
        blender_addon/niua_mcp_bridge/errors.py src/niua_blender_mcp/kernel/errors.py \
        blender_addon/niua_mcp_bridge/domains/system.py src/niua_blender_mcp/domains/system.py \
        tests/test_operations.py
git commit -m "feat: long-op progress + cancellation — op table, sideband system.operations/system.cancel

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Supervisor — one command, self-healing Blender

`scripts/blender_supervise.py` launches a visible Blender with the bridge, probes `system.health`, and on sustained failure kills/relaunches Blender and reopens the last-known `.blend`. The state machine lives in `src/niua_blender_mcp/supervisor.py` with injected probe/relaunch/restore callables so the offline suite covers every transition; process handling is the thin CLI, verified in the LIVE task.

**Files:**
- Create: `src/niua_blender_mcp/supervisor.py`
- Create: `scripts/blender_supervise.py`
- Test: `tests/test_supervisor.py` (new)

**Interfaces:**
- Consumes: `BlenderBridge.call("system.health", {}, timeout=5.0)` (Tasks 1+3; `blend_path` key), `capabilities.invoke` with `idname="wm.open_mainfile"` (existing RNA passthrough) for session restore.
- Produces: `Supervisor(probe: Callable[[], dict], relaunch: Callable[[], None], restore: Callable[[str], None], max_failures: int = 3)` with `tick() -> str` returning `"healthy" | "degraded" | "restarted"`, and attributes `failures: int`, `restarts: int`, `last_blend_path: str`. Task 12 (LIVE) runs the CLI end-to-end.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_supervisor.py`:

```python
"""Supervisor state machine: probe -> degraded -> relaunch + session restore."""

from __future__ import annotations

from niua_blender_mcp.supervisor import Supervisor


class Harness:
    def __init__(self, health: dict | None = None) -> None:
        self.health = health or {"bridge": "alive", "blend_path": ""}
        self.fail = False
        self.relaunches = 0
        self.restored: list[str] = []

    def probe(self) -> dict:
        if self.fail:
            raise ConnectionError("bridge down")
        return self.health

    def relaunch(self) -> None:
        self.relaunches += 1
        self.fail = False  # a fresh Blender answers again

    def restore(self, path: str) -> None:
        self.restored.append(path)


def make(harness: Harness, max_failures: int = 3) -> Supervisor:
    return Supervisor(
        probe=harness.probe, relaunch=harness.relaunch, restore=harness.restore, max_failures=max_failures
    )


def test_healthy_tick_remembers_the_open_blend() -> None:
    h = Harness({"bridge": "alive", "blend_path": "/tmp/hero.blend"})
    s = make(h)
    assert s.tick() == "healthy"
    assert s.last_blend_path == "/tmp/hero.blend"
    assert h.relaunches == 0


def test_failures_below_threshold_only_degrade() -> None:
    h = Harness()
    s = make(h, max_failures=3)
    h.fail = True
    assert s.tick() == "degraded"
    assert s.tick() == "degraded"
    assert h.relaunches == 0
    assert s.failures == 2


def test_threshold_failure_relaunches_and_restores_last_blend() -> None:
    h = Harness({"bridge": "alive", "blend_path": "/tmp/hero.blend"})
    s = make(h, max_failures=3)
    assert s.tick() == "healthy"  # learns the blend path
    h.fail = True
    s.tick()
    s.tick()
    assert s.tick() == "restarted"
    assert h.relaunches == 1
    assert h.restored == ["/tmp/hero.blend"]
    assert s.failures == 0
    assert s.restarts == 1


def test_restore_skipped_when_no_blend_was_ever_open() -> None:
    h = Harness({"bridge": "alive", "blend_path": ""})
    s = make(h, max_failures=1)
    assert s.tick() == "healthy"
    h.fail = True
    assert s.tick() == "restarted"
    assert h.relaunches == 1
    assert h.restored == []


def test_recovery_resets_the_failure_count() -> None:
    h = Harness()
    s = make(h, max_failures=3)
    h.fail = True
    s.tick()
    s.tick()
    h.fail = False
    assert s.tick() == "healthy"
    assert s.failures == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_supervisor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'niua_blender_mcp.supervisor'`.

- [ ] **Step 3: Implement**

Create `src/niua_blender_mcp/supervisor.py`:

```python
"""Bridge watchdog: probe system.health, relaunch a dead Blender, restore the session.

Interface-layer (Part 1): knows sockets, processes, and .blend paths -- nothing about
assets or finishing. The state machine takes injected probe/relaunch/restore callables
so the offline suite exercises every transition without a Blender or a subprocess;
scripts/blender_supervise.py provides the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Supervisor:
    probe: Callable[[], dict[str, Any]]  # raises on failure (e.g. BridgeError)
    relaunch: Callable[[], None]
    restore: Callable[[str], None]
    max_failures: int = 3
    failures: int = field(default=0, init=False)
    restarts: int = field(default=0, init=False)
    last_blend_path: str = field(default="", init=False)

    def tick(self) -> str:
        """One watchdog cycle: 'healthy' | 'degraded' | 'restarted'."""
        try:
            health = self.probe()
        except Exception:  # noqa: BLE001 - any probe failure counts against the bridge
            self.failures += 1
            if self.failures < self.max_failures:
                return "degraded"
            self.relaunch()
            if self.last_blend_path:
                self.restore(self.last_blend_path)
            self.failures = 0
            self.restarts += 1
            return "restarted"
        self.failures = 0
        path = str(health.get("blend_path") or "")
        if path:
            self.last_blend_path = path
        return "healthy"
```

Create `scripts/blender_supervise.py`:

```python
#!/usr/bin/env python3
"""Self-healing Blender launcher: one command that starts a visible Blender with the
bridge, then watchdogs it -- dead bridge => kill + relaunch => reopen the last .blend.

    python scripts/blender_supervise.py [--port 8765] [--blender blender] \
        [--addon-dir <repo>/blender_addon] [--interval 5] [--max-failures 3]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from niua_blender_mcp.bridge import BlenderBridge  # noqa: E402
from niua_blender_mcp.supervisor import Supervisor  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class BlenderProcess:
    """Owns the Blender subprocess: launch via scripts/blender_gui.py, wait for the bridge."""

    def __init__(self, blender: str, addon_dir: str, port: int) -> None:
        self.blender = blender
        self.addon_dir = addon_dir
        self.port = port
        self.proc: subprocess.Popen | None = None

    def launch(self) -> None:
        self.terminate()
        gui = os.path.join(REPO, "scripts", "blender_gui.py")
        self.proc = subprocess.Popen(  # noqa: S603 - trusted local dev launcher
            [self.blender, "--python", gui, "--", self.addon_dir, str(self.port)]
        )
        self._wait_for_bridge()

    def terminate(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def _wait_for_bridge(self, attempts: int = 60) -> None:
        bridge = BlenderBridge(port=self.port)
        for _ in range(attempts):
            try:
                bridge.call("system.health", {}, timeout=5.0)
                return
            except Exception:  # noqa: BLE001 - bridge not up yet
                time.sleep(1.0)
        raise RuntimeError(f"bridge did not come up on port {self.port}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-healing Blender bridge supervisor.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--addon-dir", default=os.path.join(REPO, "blender_addon"))
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--max-failures", type=int, default=3)
    args = ap.parse_args(argv)

    bridge = BlenderBridge(port=args.port)
    process = BlenderProcess(args.blender, args.addon_dir, args.port)

    def restore(path: str) -> None:
        # Reopen the last session via the generic RNA passthrough (no dedicated tool needed).
        bridge.call(
            "capabilities.invoke",
            {"idname": "wm.open_mainfile", "args": json.dumps({"filepath": path})},
            timeout=60.0,
        )

    supervisor = Supervisor(
        probe=lambda: bridge.call("system.health", {}, timeout=5.0),
        relaunch=process.launch,
        restore=restore,
        max_failures=args.max_failures,
    )

    process.launch()
    print(f"[niua-supervise] watching bridge on 127.0.0.1:{args.port}", flush=True)
    try:
        while True:
            state = supervisor.tick()
            if state != "healthy":
                print(f"[niua-supervise] {state} (restarts={supervisor.restarts})", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        process.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_supervisor.py -v`
Expected: 5 passed.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 742 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/supervisor.py scripts/blender_supervise.py tests/test_supervisor.py
git commit -m "feat: self-healing supervisor — watchdog state machine + one-command launcher

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

# Workstream 2 — Agent ergonomics

### Task 6: `capabilities.tools` — navigate the tool surface without dumping 298 specs

Mirror the niua-godot `describe_tools` pattern over this MCP's own ToolSpec surface (the existing `capabilities.domains/search/describe` answer about *Blender RNA operators*; this new tool answers about *this server's tools*, including the generated tier hidden from `tools/list`). It is answered **server-locally** from the router — no bridge round-trip, works with Blender down. The parity test learns an explicit `LOCAL_COMMANDS` exemption.

**Files:**
- Modify: `src/niua_blender_mcp/server.py` (`LOCAL_COMMANDS`, `_describe_tools`)
- Modify: `src/niua_blender_mcp/domains/capabilities.py` (ToolSpec)
- Modify: `tests/test_parity.py`
- Test: `tests/test_describe_tools.py` (new)

**Interfaces:**
- Consumes: `Router.specs() / get(name)`, `ToolSpec.input_schema()`, `_tool_result` / `_tool_error` (`server.py`), `UNKNOWN_TOOL` from `kernel.errors`.
- Produces: `niua_blender_mcp.server.LOCAL_COMMANDS: frozenset[str]` (imported by `tests/test_parity.py`); tool `capabilities.tools` — no args → `{"domains": [{"name", "tool_count"}], "total_tools", "next"}`; `{domain}` → `{"domain", "tools": [{"name","summary","mutates"}], "next"}`; `{name}` → `{"name","summary","domain","tier","mutates","timeout_tier","inputSchema"}`. Task 7's teaching errors point `next_call` at `capabilities.tools`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_describe_tools.py`:

```python
"""capabilities.tools: no args -> domain map; {domain} -> its tools; {name} -> one schema.
Answered by the server from the router -- no bridge call ever happens."""

from __future__ import annotations

from niua_blender_mcp.kernel.errors import UNKNOWN_TOOL
from niua_blender_mcp.server import LOCAL_COMMANDS, create_server


class ExplodingBridge:
    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        raise AssertionError(f"capabilities.tools must never hit the bridge (got {command})")


def call(server, arguments: dict) -> dict:
    return server._tools_call({"name": "capabilities.tools", "arguments": arguments})


def test_local_commands_declares_capabilities_tools() -> None:
    assert "capabilities.tools" in LOCAL_COMMANDS


def test_no_args_returns_the_domain_map() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {})
    assert result["isError"] is False
    body = result["structuredContent"]
    names = {d["name"] for d in body["domains"]}
    assert {"capabilities", "system", "scene"} <= names
    assert body["total_tools"] > 200
    assert all(d["tool_count"] >= 1 for d in body["domains"])


def test_domain_arg_lists_that_domains_tools() -> None:
    server = create_server(bridge=ExplodingBridge())
    body = call(server, {"domain": "capabilities"})["structuredContent"]
    tool_names = {t["name"] for t in body["tools"]}
    assert "capabilities.tools" in tool_names
    assert "capabilities.search" in tool_names


def test_name_arg_returns_one_full_schema() -> None:
    server = create_server(bridge=ExplodingBridge())
    body = call(server, {"name": "scene.create_object"})["structuredContent"]
    assert body["name"] == "scene.create_object"
    assert body["mutates"] is True
    assert body["timeout_tier"] == "normal"
    assert "type" in body["inputSchema"]["properties"]


def test_unknown_name_teaches_the_next_call() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {"name": "nope.nope"})
    assert result["isError"] is True
    body = result["structuredContent"]
    assert body["code"] == UNKNOWN_TOOL
    assert body["detail"]["next_call"] == "capabilities.tools"


def test_unknown_domain_lists_the_valid_domains() -> None:
    server = create_server(bridge=ExplodingBridge())
    result = call(server, {"domain": "nope"})
    assert result["isError"] is True
    assert "capabilities" in result["structuredContent"]["detail"]["domains"]
```

Update `tests/test_parity.py` — full replacement of the file:

```python
"""Guard against server/add-on command drift: every server tool's command must
have a matching add-on handler, and vice versa. Server-local tools (answered from
the router without a bridge round-trip) are declared in server.LOCAL_COMMANDS and
exempt -- by construction they have no add-on half."""

from __future__ import annotations

from niua_blender_mcp.domains import build_router
from niua_blender_mcp.server import LOCAL_COMMANDS
from niua_mcp_bridge.domains import build_default_registry


def test_server_commands_match_addon_handlers() -> None:
    server_commands = {
        "capabilities.invoke" if spec.tier == "generated" else spec.command
        for spec in build_router().specs()
        if spec.command not in LOCAL_COMMANDS
    }
    addon_commands = build_default_registry().names()
    assert server_commands == addon_commands


def test_server_command_metadata_matches_addon_handlers() -> None:
    registry = build_default_registry()
    for spec in build_router().specs():
        if spec.command in LOCAL_COMMANDS:
            continue
        command_name = "capabilities.invoke" if spec.tier == "generated" else spec.command
        command = registry.get(command_name)
        assert command is not None
        assert command.mutates == spec.mutates, command_name
        assert command.feedback == spec.feedback, command_name
        if spec.tier != "generated":
            # Generated specs all dispatch through capabilities.invoke; their own
            # (default) tier is not the invoke command's tier, so only mirror-check
            # the 1:1 commands.
            assert command.timeout_tier == spec.timeout_tier, command_name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_describe_tools.py tests/test_parity.py -v`
Expected: FAIL with `ImportError: cannot import name 'LOCAL_COMMANDS'`.

- [ ] **Step 3: Implement**

In `src/niua_blender_mcp/server.py`, below `SERVER_VERSION` add:

```python
#: Tools the server answers itself from the router -- no bridge round-trip, usable with
#: Blender down. tests/test_parity.py exempts these from the add-on-handler mirror.
LOCAL_COMMANDS = frozenset({"capabilities.tools"})
```

In `_tools_call`, right after the `validate` try/except (and before the `system.execute_python` gate) add:

```python
        if spec.command in LOCAL_COMMANDS:
            return self._describe_tools(clean)
```

Add the method (next to `_tool_defs`):

```python
    def _describe_tools(self, args: JSON) -> JSON:
        """capabilities.tools: no args -> domain map; {domain} -> its tools; {name} -> one schema."""
        name = args.get("name") or ""
        domain = args.get("domain") or ""
        specs = self.router.specs()
        if name:
            spec = self.router.get(name)
            if spec is None:
                close = sorted(s.name for s in specs if name.lower() in s.name.lower())[:10]
                return self._tool_error(
                    UNKNOWN_TOOL,
                    f"unknown tool: {name}",
                    {"close_matches": close, "fix": "browse the domain map first", "next_call": "capabilities.tools"},
                )
            return self._tool_result(
                {
                    "name": spec.name,
                    "summary": spec.summary,
                    "domain": spec.category,
                    "tier": spec.tier,
                    "mutates": spec.mutates,
                    "timeout_tier": spec.timeout_tier,
                    "inputSchema": spec.input_schema(),
                }
            )
        if domain:
            tools = sorted(
                (
                    {"name": s.name, "summary": s.summary, "mutates": s.mutates}
                    for s in specs
                    if s.category == domain
                ),
                key=lambda t: t["name"],
            )
            if not tools:
                return self._tool_error(
                    UNKNOWN_TOOL,
                    f"unknown domain: {domain}",
                    {
                        "domains": sorted({s.category for s in specs}),
                        "fix": "pick a domain from the list",
                        "next_call": "capabilities.tools",
                    },
                )
            return self._tool_result(
                {
                    "domain": domain,
                    "tools": tools,
                    "next": 'call capabilities.tools {"name": "<tool>"} for one schema',
                }
            )
        by_domain: dict[str, int] = {}
        for s in specs:
            by_domain[s.category] = by_domain.get(s.category, 0) + 1
        return self._tool_result(
            {
                "domains": [{"name": d, "tool_count": n} for d, n in sorted(by_domain.items())],
                "total_tools": len(specs),
                "next": 'call capabilities.tools {"domain": "<name>"} to list its tools',
            }
        )
```

In `src/niua_blender_mcp/domains/capabilities.py` append to `SPECS`:

```python
    ToolSpec(
        name="capabilities.tools",
        category="capabilities",
        summary="Navigate THIS server's tools: no args -> domain map; {domain} -> its tools; {name} -> one schema",
        command="capabilities.tools",
        params={
            "domain": Str(summary="Craft domain from the no-args map, e.g. 'mesh', 'uv'"),
            "name": Str(summary="Exact tool name for a full input schema, e.g. 'scene.create_object'"),
        },
        timeout_tier="fast",
        tier="reflection",
    ),
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_describe_tools.py tests/test_parity.py -v`
Expected: all pass.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 748 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/server.py src/niua_blender_mcp/domains/capabilities.py \
        tests/test_parity.py tests/test_describe_tools.py
git commit -m "feat: capabilities.tools — server-local navigation of the tool surface (domain map -> tools -> schema)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Teaching errors — every error names the fix and the right next call

Extend the gates' teaching style to the whole hands surface at its choke points: the shared object resolver (`Ctx.get_object`, behind most `not_found` errors), the server's unknown-tool error, and server-side validation errors. A `teach()` helper standardizes the shape: `detail = {"fix": ..., "next_call": ...}`.

**Files:**
- Modify: `blender_addon/niua_mcp_bridge/errors.py` (`teach` helper)
- Modify: `blender_addon/niua_mcp_bridge/context.py` (`Ctx.get_object`)
- Modify: `src/niua_blender_mcp/server.py` (unknown-tool + validation errors)
- Test: `tests/test_teaching_errors.py` (new)

**Interfaces:**
- Consumes: `BridgeError(code, message, detail)` (`errors.py`), `Ctx.get_object(name)` (`context.py`), `_tool_error` and `validate` flow in `server.py`, `capabilities.tools` (Task 6, as the `next_call` target).
- Produces: `teach(code: str, message: str, *, fix: str, next_call: str, detail: dict | None = None) -> BridgeError` in `niua_mcp_bridge.errors` — the standard constructor for any handler that wants to raise a teaching error from now on.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_teaching_errors.py`:

```python
"""Teaching errors: every error names the fix and the right next call
(detail = {"fix": ..., "next_call": ...}), extending the gates' style to the hands."""

from __future__ import annotations

import types

import pytest

from niua_blender_mcp.kernel.errors import INVALID_PARAMS, UNKNOWN_TOOL
from niua_blender_mcp.server import create_server
from niua_mcp_bridge.context import Ctx
from niua_mcp_bridge.errors import NOT_FOUND, BridgeError, teach


class RecordingBridge:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        return {"ok": True}


def test_teach_builds_a_structured_teaching_error() -> None:
    err = teach(NOT_FOUND, "object not found: Ghost", fix="list the scene", next_call="scene.info")
    assert isinstance(err, BridgeError)
    assert err.code == NOT_FOUND
    assert err.detail == {"fix": "list the scene", "next_call": "scene.info"}


def test_missing_object_error_teaches_scene_info() -> None:
    bpy = types.SimpleNamespace(data=types.SimpleNamespace(objects={}))
    with pytest.raises(BridgeError) as exc:
        Ctx(bpy).get_object("Ghost")
    assert exc.value.code == NOT_FOUND
    assert exc.value.detail["next_call"] == "scene.info"
    assert exc.value.detail["fix"]


def test_unknown_tool_error_teaches_capabilities_tools() -> None:
    server = create_server(bridge=RecordingBridge())
    result = server._tools_call({"name": "nope.nope", "arguments": {}})
    assert result["isError"] is True
    body = result["structuredContent"]
    assert body["code"] == UNKNOWN_TOOL
    assert body["detail"]["next_call"] == "capabilities.tools"


def test_validation_error_names_the_tools_schema() -> None:
    server = create_server(bridge=RecordingBridge())
    result = server._tools_call({"name": "scene.create_object", "arguments": {}})
    body = result["structuredContent"]
    assert body["code"] == INVALID_PARAMS
    assert "scene.create_object" in body["detail"]["next_call"]
    assert body["detail"]["fix"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_teaching_errors.py -v`
Expected: FAIL with `ImportError: cannot import name 'teach'`.

- [ ] **Step 3: Implement**

Append to `blender_addon/niua_mcp_bridge/errors.py`:

```python
def teach(code: str, message: str, *, fix: str, next_call: str, detail: dict[str, Any] | None = None) -> BridgeError:
    """Build a teaching error: every error names the fix and the right next call.

    Use this instead of bare BridgeError wherever the handler knows what the agent
    should do next -- the gates established the style; the hands follow it.
    """
    data: dict[str, Any] = dict(detail or {})
    data["fix"] = fix
    data["next_call"] = next_call
    return BridgeError(code, message, data)
```

In `blender_addon/niua_mcp_bridge/context.py` change the import line and `get_object`:

```python
from .errors import NOT_FOUND, BridgeError, teach
```

```python
    def get_object(self, name: str) -> Any:
        obj = self.bpy.data.objects.get(name)
        if obj is None:
            raise teach(
                NOT_FOUND,
                f"object not found: {name}",
                fix="object names are exact and case-sensitive; list the scene to find the right one",
                next_call="scene.info",
            )
        return obj
```

In `src/niua_blender_mcp/server.py` `_tools_call`, replace the unknown-tool return:

```python
        if spec is None:
            return self._tool_error(
                UNKNOWN_TOOL,
                f"unknown tool: {name}",
                {"fix": "navigate the tool surface first", "next_call": "capabilities.tools"},
            )
```

and replace the validation except-block:

```python
        try:
            clean = validate(spec, arguments)
        except McpError as exc:
            detail: JSON = dict(exc.detail) if isinstance(exc.detail, dict) else (
                {} if exc.detail is None else {"got": exc.detail}
            )
            detail.setdefault("fix", f"correct the argument and re-call {spec.name}")
            detail.setdefault("next_call", f'capabilities.tools {{"name": "{spec.name}"}}')
            return self._tool_error(exc.code, exc.message, detail)
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_teaching_errors.py tests/test_server.py tests/test_dispatch.py -v`
Expected: all pass (existing tests assert only `code`, unaffected by the added `detail`).
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 752 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add blender_addon/niua_mcp_bridge/errors.py blender_addon/niua_mcp_bridge/context.py \
        src/niua_blender_mcp/server.py tests/test_teaching_errors.py
git commit -m "feat: teaching errors — resolver, unknown-tool, and validation errors name the fix and next call

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Param-convention audit — one written convention, spec-lint enforced

The audit found two live conventions for multi-value params (comma-separated strings: 10 params; "JSON array string": 4 params on the RNA-passthrough quartet) plus 3 params with no documentation at all (`context.select_objects.action`, `context.select_all.action`, `outliner.describe.kind`). The convention is written down as the docstring of the lint test (the same "test file is the single source of truth" pattern as `tests/test_layer_boundary.py`), the JSON-array quartet is frozen as an allowlisted legacy exception (their runtime behavior is frozen surface), and the 3 undocumented params get summaries (description-only change — no runtime behavior, bench untouched).

**Files:**
- Modify: `src/niua_blender_mcp/domains/context.py` (2 param summaries)
- Modify: `src/niua_blender_mcp/domains/outliner.py` (1 param summary)
- Test: `tests/test_spec_conventions.py` (new)

**Interfaces:**
- Consumes: `build_router()`, `ToolSpec.params: dict[str, Param]`, `Param.kind/summary/description/default/choices`.
- Produces: the written convention (docstring below) + module constants `MULTI_VALUE_NAMES`, `JSON_ARRAY_ALLOWLIST` that future tool authors extend deliberately or not at all.

- [ ] **Step 1: Write the failing test**

Create `tests/test_spec_conventions.py`:

```python
"""Spec-lint: THE parameter convention, written once and enforced against every ToolSpec.

THE CONVENTION (single source of truth -- edit this docstring and the constants
below deliberately, never ad hoc):

1. Multi-value object/element params are STRING params with a plural name
   ("objects", "vertices", "edges", "indices", "maps") taking a COMMA-SEPARATED
   string; their summary/description must say "comma-separated" so an agent
   cannot guess the encoding wrong.
2. "JSON array string" params are a FROZEN legacy exception on the RNA-passthrough
   quartet only (JSON_ARRAY_ALLOWLIST). New tools must not add JSON-string params:
   use a real array param (kind="array") or rule 1's comma-separated string.
3. Every param carries at least a summary or a description.
4. Defaults type-match their kind; enum defaults are members of choices.

Generated-tier specs mirror live Blender RNA verbatim and are exempt (their
conventions are Blender's, not ours).
"""

from __future__ import annotations

from niua_blender_mcp.domains import build_router

MULTI_VALUE_NAMES = {"objects", "vertices", "edges", "indices", "maps"}

#: Frozen legacy exception (rule 2): the RNA-passthrough quartet's 'select' param.
JSON_ARRAY_ALLOWLIST = {
    ("capabilities.invoke", "select"),
    ("rna.call_operator", "select"),
    ("ui.operator_poll", "select"),
    ("ui.operator_invoke", "select"),
}


def _curated_params():
    for spec in build_router().specs():
        if spec.tier == "generated":
            continue
        for pname, param in spec.params.items():
            yield spec, pname, param


def _doc(param) -> str:
    return (param.summary + " " + param.description).lower()


def test_multi_value_string_params_document_comma_separated() -> None:
    bad = [
        f"{spec.name}.{pname}"
        for spec, pname, param in _curated_params()
        if param.kind == "string"
        and pname in MULTI_VALUE_NAMES
        and (spec.name, pname) not in JSON_ARRAY_ALLOWLIST
        and "comma" not in _doc(param)
    ]
    assert not bad, f"multi-value string params must document 'comma-separated': {bad}"


def test_json_array_string_params_are_frozen_to_the_allowlist() -> None:
    found = {
        (spec.name, pname)
        for spec, pname, param in _curated_params()
        if "json array" in _doc(param)
    }
    assert found <= JSON_ARRAY_ALLOWLIST, (
        f"new JSON-array-string params are banned (rule 2): {sorted(found - JSON_ARRAY_ALLOWLIST)}"
    )


def test_every_param_is_documented() -> None:
    bad = [
        f"{spec.name}.{pname}"
        for spec, pname, param in _curated_params()
        if not param.summary and not param.description
    ]
    assert not bad, f"params without any summary/description: {bad}"


def test_defaults_type_match_kind() -> None:
    bad = []
    for spec, pname, param in _curated_params():
        default = param.default
        if default is None:
            continue
        ok = True
        if param.kind == "boolean":
            ok = isinstance(default, bool)
        elif param.kind == "integer":
            ok = isinstance(default, int) and not isinstance(default, bool)
        elif param.kind == "number":
            ok = isinstance(default, (int, float)) and not isinstance(default, bool)
        elif param.kind == "string":
            ok = isinstance(default, str)
        elif param.kind == "enum":
            ok = default in (param.choices or ())
        elif param.kind == "array":
            ok = isinstance(default, (list, tuple))
        if not ok:
            bad.append(f"{spec.name}.{pname} ({param.kind} default {default!r})")
    assert not bad, f"defaults that don't match their kind: {bad}"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_spec_conventions.py -v`
Expected: `test_every_param_is_documented` FAILS listing exactly `['context.select_objects.action', 'context.select_all.action', 'outliner.describe.kind']`; the other three tests pass (audited against the current surface).

- [ ] **Step 3: Fix the three undocumented params (summaries only — zero runtime change)**

In `src/niua_blender_mcp/domains/context.py`, inside `context.select_objects`:

```python
            "action": Enum(
                ["REPLACE", "ADD", "REMOVE", "TOGGLE"],
                default="REPLACE",
                summary="How the named objects combine with the current selection",
            ),
```

inside `context.select_all`:

```python
        params={
            "action": Enum(
                ["SELECT", "DESELECT", "INVERT"],
                default="DESELECT",
                summary="Selection action applied to every scene object",
            )
        },
```

In `src/niua_blender_mcp/domains/outliner.py`, inside `outliner.describe`:

```python
            "kind": Enum(
                ["AUTO", "OBJECT", "COLLECTION", "SCENE", "VIEW_LAYER"],
                default="AUTO",
                summary="Restrict the lookup to one datablock kind (AUTO tries each in turn)",
            ),
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_spec_conventions.py -v`
Expected: 4 passed.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 756 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add tests/test_spec_conventions.py src/niua_blender_mcp/domains/context.py \
        src/niua_blender_mcp/domains/outliner.py
git commit -m "test: spec-lint enforces the one param convention; document the last 3 params

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Bench metric — "turns for a fresh agent to finish an asset"

Count the tool calls the finisher makes per item and report them in the bench output's `meta` block only (`meta.finisher_turns`, `meta.finisher_turns_mean`). The `items` and `reading` sections — the byte-identity surface — are untouched; in baseline mode the no-op finisher scores 0 turns everywhere. This is the plan's one bench-report-glue task (the script already imports `evals`; the layer-boundary test does not scan `scripts/`).

**Files:**
- Modify: `scripts/run_objective_benchmark.py`
- Test: `tests/test_bench_turns.py` (new)

**Interfaces:**
- Consumes: `run_item(bridge, item, finisher, godot_fn=None)` and `main()` in `scripts/run_objective_benchmark.py`; `BlenderBridge.call(command, payload, timeout=None)` (Task 1).
- Produces: `run_item(bridge, item, finisher, godot_fn=None, turns: dict[str, int] | None = None) -> dict` (records `turns[item_id] = finisher_call_count` when a dict is passed); `_CountingBridge(bridge)` with `.call(...)` counting into `.calls`; output keys `meta.finisher_turns: dict[str, int]`, `meta.finisher_turns_mean: float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bench_turns.py`:

```python
"""Bench 'turns' metric: finisher tool-call count per item, recorded in meta only
(items/reading -- the byte-identity surface -- stay untouched)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_objective_benchmark.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_objective_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeBridge:
    """Answers just enough of the tool surface for run_item's recipe path."""

    def __init__(self) -> None:
        self.objects: list[str] = []

    def call(self, command: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        payload = payload or {}
        if command == "scene.info":
            return {"objects": [{"name": n, "type": "MESH"} for n in self.objects]}
        if command == "scene.create_object":
            self.objects.append("Cube")
            return {"name": "Cube"}
        if command == "object.rename":
            self.objects[self.objects.index(payload["object"])] = payload["name"]
            return {"name": payload["name"]}
        if command == "object.delete":
            for name in payload["objects"].split(","):
                if name in self.objects:
                    self.objects.remove(name)
            return {"deleted": True}
        if command == "feedback.capture_intake":
            return {"available": True}
        if command == "feedback.readiness":
            return {"available": True, "readiness": 0.5, "stage_pass_fraction_mean": 0.5}
        if command == "feedback.preservation":
            return {"available": True, "preservation": 1.0}
        return {}


ITEM = {
    "id": "t1",
    "asset_class": "hard_surface_prop",
    "input": {"recipe": [{"tool": "scene.create_object", "args": {"type": "CUBE"}}]},
}


def test_finisher_turns_counts_tool_calls() -> None:
    module = _load_module()

    def three_call_finisher(bridge, subject, item):
        for _ in range(3):
            bridge.call("scene.info", {})

    turns: dict[str, int] = {}
    card = module.run_item(FakeBridge(), ITEM, three_call_finisher, None, turns=turns)
    assert turns == {"t1": 3}
    assert "finisher_turns" not in card  # never in the items section
    assert card["id"] == "t1"


def test_baseline_no_op_finisher_scores_zero_turns() -> None:
    module = _load_module()
    turns: dict[str, int] = {}
    module.run_item(FakeBridge(), ITEM, module._no_op_finisher, None, turns=turns)
    assert turns == {"t1": 0}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_bench_turns.py -v`
Expected: FAIL with `TypeError: run_item() got an unexpected keyword argument 'turns'`.

- [ ] **Step 3: Implement**

In `scripts/run_objective_benchmark.py`, add above `run_item`:

```python
class _CountingBridge:
    """Counts the finisher's tool calls: the 'turns for a fresh agent to finish an
    asset' metric. Reported in meta only -- items/reading stay byte-identical."""

    def __init__(self, bridge: Any) -> None:
        self._bridge = bridge
        self.calls = 0

    def call(self, command: str, payload: dict | None = None, **kwargs: Any) -> dict:
        self.calls += 1
        return self._bridge.call(command, payload, **kwargs)
```

Change `run_item`'s signature and finisher block:

```python
def run_item(bridge: BlenderBridge, item: dict, finisher, godot_fn=None, turns: dict | None = None) -> dict:
```

```python
    intake = _safe(bridge, "feedback.capture_intake", {"object": subject})
    counting = _CountingBridge(bridge)
    try:
        finisher(counting, subject, item)                # real work in agent mode; no-op in baseline
    except BridgeError as exc:
        print(f"  [{item['id']}] FINISHER FAILED: {str(exc)[:70]}", file=sys.stderr)
        if turns is not None:
            turns[item["id"]] = counting.calls
        return score_item_objective(item, readiness=None, stage_pass_fraction=None,
                                    preservation=None, preservation_available=False,
                                    godot_import=None)
    if turns is not None:
        turns[item["id"]] = counting.calls
```

In `main()`, thread the accumulator through and report it in `meta`:

```python
    turns: dict[str, int] = {}
    try:
        cards = [run_item(bridge, it, finisher, godot_fn, turns=turns) for it in items]
```

and inside the `out["meta"]` dict, after `"godot_bin"`:

```python
            "finisher_turns": turns,
            "finisher_turns_mean": (sum(turns.values()) / len(turns)) if turns else None,
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_bench_turns.py -v`
Expected: 2 passed.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 758 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_objective_benchmark.py tests/test_bench_turns.py
git commit -m "feat: bench meta tracks finisher turns per item (scores untouched)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

# Workstream 4 — Observability (session replay)

### Task 10: Session JSONL log — dispatch middleware for every mutating tool call

Record every mutating tool call (name, params, duration, result summary, optional thumbnail) to a JSONL session log via server-dispatch middleware. Enabled by `NIUA_BLENDER_MCP_SESSION_LOG=<path>`; a no-op when unset. Read-only tools are never logged (no noise, no image spam).

**Files:**
- Create: `src/niua_blender_mcp/session_log.py`
- Modify: `src/niua_blender_mcp/server.py` (wiring)
- Test: `tests/test_session_log.py` (new)

**Interfaces:**
- Consumes: `_tools_call` dispatch flow, `spec.mutates`, `result["_feedback"]["data"]` (the existing opt-in capture attachment), `BridgeError`.
- Produces: `SessionLog(path)` with `record(*, tool: str, arguments: dict, duration_ms: float, ok: bool, summary: dict, thumbnail: str | None = None) -> None` (appends one JSON line); `summarize_result(result: dict) -> dict` (scalar-only, image-free); `from_env(environ=None) -> SessionLog | None`; env var name `ENV_VAR = "NIUA_BLENDER_MCP_SESSION_LOG"`; `create_server(..., session_log=None)`. Task 11's report reads exactly these JSONL keys: `ts, tool, arguments, duration_ms, ok, summary, thumbnail?`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_log.py`:

```python
"""Session replay log: mutating tool calls -> JSONL via server-dispatch middleware."""

from __future__ import annotations

import json

from niua_blender_mcp.bridge import BridgeError
from niua_blender_mcp.kernel.errors import NOT_FOUND
from niua_blender_mcp.server import create_server
from niua_blender_mcp.session_log import ENV_VAR, SessionLog, from_env, summarize_result


class RecordingBridge:
    def __init__(self, result=None, raises=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.result = result if result is not None else {"ok": True}
        self.raises = raises

    def call(self, command: str, payload: dict, timeout: float | None = None) -> dict:
        self.calls.append((command, payload))
        if self.raises is not None:
            raise self.raises
        return dict(self.result)


def entries(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_mutating_call_is_logged(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    server = create_server(bridge=RecordingBridge(result={"name": "Hero"}), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE", "name": "Hero"}})
    (entry,) = entries(log_path)
    assert entry["tool"] == "scene.create_object"
    assert entry["ok"] is True
    assert entry["arguments"]["type"] == "CUBE"
    assert entry["duration_ms"] >= 0
    assert entry["summary"]["name"] == "Hero"
    assert entry["ts"]


def test_read_only_call_is_not_logged(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    server = create_server(bridge=RecordingBridge(), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.info", "arguments": {}})
    assert not log_path.exists()


def test_failed_mutation_is_logged_with_error_summary(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    bridge = RecordingBridge(raises=BridgeError(NOT_FOUND, "object not found: Ghost"))
    server = create_server(bridge=bridge, session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.set_transform", "arguments": {"object": "Ghost"}})
    (entry,) = entries(log_path)
    assert entry["ok"] is False
    assert entry["summary"]["code"] == NOT_FOUND


def test_thumbnail_captured_from_feedback_attachment(tmp_path) -> None:
    log_path = tmp_path / "session.jsonl"
    result = {"name": "Hero", "_feedback": {"available": True, "data": "QkFTRTY0"}}
    server = create_server(bridge=RecordingBridge(result=result), session_log=SessionLog(log_path))
    server._tools_call({"name": "scene.create_object", "arguments": {"type": "CUBE"}})
    (entry,) = entries(log_path)
    assert entry["thumbnail"] == "QkFTRTY0"


def test_summarize_result_is_scalar_only_and_image_free() -> None:
    summary = summarize_result(
        {"name": "Hero", "count": 3, "data": "HUGEBASE64", "_feedback": {"data": "x"}, "nested": {"a": 1}}
    )
    assert summary == {"count": 3, "name": "Hero"}


def test_from_env_toggles_the_middleware(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert from_env() is None
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "s.jsonl"))
    log = from_env()
    assert log is not None and log.path.name == "s.jsonl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_session_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'niua_blender_mcp.session_log'`.

- [ ] **Step 3: Implement**

Create `src/niua_blender_mcp/session_log.py`:

```python
"""Session replay log: JSONL middleware for every mutating tool call.

Interface-layer observability: what happened, with what arguments, how long it took,
whether it worked, and (when the tool attached a viewport capture) what it looked
like. scripts/session_report.py renders a log into the before/after HTML gallery.
Enabled by pointing NIUA_BLENDER_MCP_SESSION_LOG at a file path; off otherwise.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENV_VAR = "NIUA_BLENDER_MCP_SESSION_LOG"

_MAX_SUMMARY_FIELDS = 8
_SKIP_KEYS = {"data", "images", "_feedback"}  # image payloads never belong in a summary


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Small scalar-only view of a tool result (no image payloads, no nesting)."""
    summary: dict[str, Any] = {}
    for key in sorted(result):
        if key in _SKIP_KEYS:
            continue
        value = result[key]
        if isinstance(value, str):
            summary[key] = value[:120]
        elif isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
        if len(summary) >= _MAX_SUMMARY_FIELDS:
            break
    return summary


class SessionLog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(
        self,
        *,
        tool: str,
        arguments: dict[str, Any],
        duration_ms: float,
        ok: bool,
        summary: dict[str, Any],
        thumbnail: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "arguments": arguments,
            "duration_ms": round(duration_ms, 1),
            "ok": ok,
            "summary": summary,
        }
        if thumbnail:
            entry["thumbnail"] = thumbnail
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def from_env(environ: dict[str, str] | None = None) -> SessionLog | None:
    path = (os.environ if environ is None else environ).get(ENV_VAR)
    return SessionLog(path) if path else None
```

In `src/niua_blender_mcp/server.py`: add `import time` to the imports and

```python
from .session_log import from_env, summarize_result
```

Add a field to the dataclass (after `allow_python`):

```python
    session_log: Any = None
```

In `_tools_call`, wrap the dispatch (this builds on Task 1's `timeout` block):

```python
        timeout = TIMEOUT_SECONDS[spec.timeout_tier]
        started = time.perf_counter()
        try:
            if spec.tier == "generated":
                result = self.bridge.call(
                    "capabilities.invoke",
                    {"idname": spec.command, "args": json.dumps(clean)},
                    timeout=timeout,
                )
            else:
                result = self.bridge.call(spec.command, clean, timeout=timeout)
        except BridgeError as exc:
            self._record_session(spec, clean, started, ok=False,
                                 summary={"code": exc.code, "message": exc.message})
            return self._tool_error(exc.code, exc.message, exc.detail)
        self._record_session(spec, clean, started, ok=True, summary=summarize_result(result),
                             thumbnail=self._session_thumbnail(result))
        return self._tool_result(result)
```

Add the two helpers (next to `_tool_result`):

```python
    def _record_session(self, spec, arguments: JSON, started: float, *, ok: bool,
                        summary: JSON, thumbnail: str | None = None) -> None:
        if self.session_log is None or not spec.mutates:
            return
        self.session_log.record(
            tool=spec.name,
            arguments=arguments,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            ok=ok,
            summary=summary,
            thumbnail=thumbnail,
        )

    @staticmethod
    def _session_thumbnail(result: JSON) -> str | None:
        image = result if (result.get("available") and result.get("data")) else result.get("_feedback")
        if isinstance(image, dict) and image.get("available") and image.get("data"):
            return str(image["data"])
        return None
```

In `create_server`, add the parameter and wiring:

```python
def create_server(
    bridge: Any | None = None,
    router: Router | None = None,
    allow_python: bool | None = None,
    session_log: Any | None = None,
) -> NiuaBlenderMCP:
    if allow_python is None:
        allow_python = os.environ.get("NIUA_BLENDER_MCP_ALLOW_PYTHON") == "1"
    return NiuaBlenderMCP(
        bridge=bridge or BlenderBridge(),
        router=router or build_router(),
        allow_python=allow_python,
        session_log=session_log if session_log is not None else from_env(),
    )
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_session_log.py tests/test_server.py -v`
Expected: all pass.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 764 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/niua_blender_mcp/session_log.py src/niua_blender_mcp/server.py tests/test_session_log.py
git commit -m "feat: session replay JSONL — dispatch middleware records every mutating tool call

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: `scripts/session_report.py` — the before/after HTML gallery, automated

Render a session JSONL log into a standalone, zero-dependency HTML report: every mutating call in order with status, duration, arguments, result summary, and inline viewport thumbnails.

**Files:**
- Create: `scripts/session_report.py`
- Test: `tests/test_session_report.py` (new)

**Interfaces:**
- Consumes: the JSONL entry shape from Task 10 (`ts, tool, arguments, duration_ms, ok, summary, thumbnail?`), and `SessionLog` to write the test fixture.
- Produces: `load_entries(path) -> list[dict]`, `render_html(entries, title="Niua session report") -> str`, `main(argv=None) -> int` (CLI: `python scripts/session_report.py <session.jsonl> [-o report.html]`, default output alongside the log with `.html` suffix).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_report.py`:

```python
"""session_report.py: JSONL session log -> standalone HTML replay report."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from niua_blender_mcp.session_log import SessionLog

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "session_report.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("session_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_fixture(path: Path) -> None:
    log = SessionLog(path)
    log.record(tool="scene.create_object", arguments={"type": "CUBE"}, duration_ms=12.5,
               ok=True, summary={"name": "Cube"}, thumbnail="QkFTRTY0")
    log.record(tool="scene.set_transform", arguments={"object": "Ghost"}, duration_ms=3.0,
               ok=False, summary={"code": "not_found"})


def test_load_entries_round_trips_the_log(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    entries = module.load_entries(tmp_path / "s.jsonl")
    assert [e["tool"] for e in entries] == ["scene.create_object", "scene.set_transform"]


def test_render_html_shows_calls_failures_and_thumbnails(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    html_text = module.render_html(module.load_entries(tmp_path / "s.jsonl"))
    assert "scene.create_object" in html_text
    assert "data:image/png;base64,QkFTRTY0" in html_text
    assert "FAILED" in html_text
    assert "2 mutating calls" in html_text
    assert html_text.lstrip().startswith("<!doctype html>")


def test_main_writes_the_report_next_to_the_log(tmp_path) -> None:
    module = _load_module()
    _write_fixture(tmp_path / "s.jsonl")
    assert module.main([str(tmp_path / "s.jsonl")]) == 0
    out = tmp_path / "s.html"
    assert out.exists()
    assert "scene.set_transform" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_session_report.py -v`
Expected: FAIL — `FileNotFoundError` from `spec_from_file_location` (script does not exist yet).

- [ ] **Step 3: Implement**

Create `scripts/session_report.py`:

```python
#!/usr/bin/env python3
"""Render a session JSONL log (niua_blender_mcp.session_log) into standalone HTML.

    python scripts/session_report.py <session.jsonl> [-o report.html]

The gallery that earned trust, as a standing artifact: every mutating call in order,
with status, duration, arguments, result summary, and the viewport thumbnail when one
was recorded. Zero dependencies; thumbnails are inlined base64.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def load_entries(path: str | Path) -> list[dict]:
    entries: list[dict] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def _row(index: int, entry: dict) -> str:
    thumb = ""
    if entry.get("thumbnail"):
        alt = html.escape(str(entry.get("tool", "")))
        thumb = f'<img src="data:image/png;base64,{entry["thumbnail"]}" alt="{alt}" style="max-width:220px">'
    ok = bool(entry.get("ok"))
    return (
        "<tr>"
        f"<td>{index}</td>"
        f"<td><code>{html.escape(str(entry.get('tool', '')))}</code></td>"
        f"<td class=\"{'ok' if ok else 'fail'}\">{'ok' if ok else 'FAILED'}</td>"
        f"<td>{float(entry.get('duration_ms', 0.0)):.0f} ms</td>"
        f"<td><code>{html.escape(json.dumps(entry.get('arguments', {})))}</code></td>"
        f"<td><code>{html.escape(json.dumps(entry.get('summary', {})))}</code></td>"
        f"<td>{thumb}</td>"
        "</tr>"
    )


def render_html(entries: list[dict], title: str = "Niua session report") -> str:
    ok_count = sum(1 for e in entries if e.get("ok"))
    total_ms = sum(float(e.get("duration_ms", 0.0)) for e in entries)
    rows = "".join(_row(i, e) for i, e in enumerate(entries, 1))
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 6px 10px; vertical-align: top; text-align: left; }}
.ok {{ color: #2a7; }} .fail {{ color: #c33; font-weight: bold; }}
</style></head>
<body>
<h1>{html.escape(title)}</h1>
<p>{len(entries)} mutating calls &middot; {ok_count} ok &middot; {len(entries) - ok_count} failed &middot; {total_ms:.0f} ms total</p>
<table>
<tr><th>#</th><th>tool</th><th>status</th><th>duration</th><th>arguments</th><th>result</th><th>view</th></tr>
{rows}
</table>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render a session JSONL log to an HTML replay report.")
    ap.add_argument("log", help="path to the session .jsonl written by the MCP server")
    ap.add_argument("-o", "--out", default="", help="output .html path (default: alongside the log)")
    args = ap.parse_args(argv)
    log = Path(args.log)
    out = Path(args.out) if args.out else log.with_suffix(".html")
    entries = load_entries(log)
    out.write_text(render_html(entries, title=f"Niua session report — {log.name}"), encoding="utf-8")
    print(f"wrote {out} ({len(entries)} calls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest tests/test_session_report.py -v`
Expected: 3 passed.
Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 767 passed, 71 skipped.

- [ ] **Step 5: Commit**

```bash
git add scripts/session_report.py tests/test_session_report.py
git commit -m "feat: session_report.py — HTML replay gallery from a session JSONL log

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: LIVE verification (requires a real Blender)

Everything above is offline-verified. This task proves the live behaviors the fakes cannot: real timeouts, sideband observability while the main thread is busy, supervisor relaunch, session-log thumbnails from real captures, and — the hard gate — baseline bench identity.

**Files:** none created (fix-forward only: if a live check fails, fix, add/adjust the offline test that should have caught it, and commit that fix with the standard trailer).

**Interfaces:**
- Consumes: everything shipped in Tasks 1–11.
- Produces: a verified go/no-go for the branch.

- [ ] **Step 1: Launch a live Blender with the bridge**

```bash
blender --python scripts/blender_gui.py -- /home/frankyin/Desktop/lab/lab-niua-blender/blender_addon 8765
```

Expected: Blender window opens; terminal prints `[niua] GUI bridge listening on 127.0.0.1:8765`.

- [ ] **Step 2: system.health answers with real data**

```bash
python scripts/bridge_call.py 8765 system.health '{}'
```

Expected: JSON with `"bridge": "alive"`, a real `blender_version`, `queue_depth: 0`, `last_errors: []` (or recent entries), `python_enabled: false`.

- [ ] **Step 3: Sideband observability + cancel while the main thread is busy**

In terminal A start a heavy call, in terminal B immediately list ops:

```bash
# A (heavy op on a subdivided mesh; any long feedback.quality run works)
python scripts/bridge_call.py 8765 scene.create_object '{"type": "SPHERE", "name": "HeavyBall"}'
python scripts/bridge_call.py 8765 feedback.quality '{"object": "HeavyBall"}' &
# B (while A runs)
python scripts/bridge_call.py 8765 system.operations '{}'
```

Expected: B answers **immediately** even mid-op, showing the running `feedback.quality` op with `done: false` and its `elapsed`. Then `python scripts/bridge_call.py 8765 system.cancel '{"op_id": "op-nope"}'` returns the teaching error naming `system.operations`.

- [ ] **Step 4: Baseline bench identity (the hard gate)**

```bash
python scripts/run_objective_benchmark.py --no-godot
```

Expected: per-item readiness **0.36 / 0.36 / 0.36 / 0.24 / 0.28**, preservation **1.0** on every item — identical to the pre-plan baseline. `meta.finisher_turns` shows every item at 0, `meta.finisher_turns_mean` 0.0. Any drift in `items`/`reading` is a stop-the-line failure.

- [ ] **Step 5: Session log + report end-to-end**

```bash
export NIUA_BLENDER_MCP_SESSION_LOG=/tmp/niua_session/live.jsonl
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"scene.create_object","arguments":{"type":"CUBE","name":"LogMe"}}}' \
  | python -m niua_blender_mcp --port 8765
python scripts/session_report.py /tmp/niua_session/live.jsonl
```

Expected: `live.jsonl` has one entry for `scene.create_object` with a `thumbnail` (viewport feedback attaches on mutating scene tools); `live.html` renders it with the inline image. Open `live.html` and eyeball it.

- [ ] **Step 6: Supervisor self-healing (use a second port to avoid the running instance)**

```bash
python scripts/blender_supervise.py --port 8766 --interval 2 --max-failures 2
# once it prints "watching bridge", open any .blend in that Blender (File > Open), then:
pkill -f 'blender --python .*blender_gui'
```

Expected: within ~3 probe intervals the supervisor prints `degraded` then `restarted (restarts=1)`, a fresh Blender window appears, and the previously open .blend is reopened. Ctrl+C to stop; also close the Step-1 Blender.

- [ ] **Step 7: Full offline suite one last time, then wrap up**

Run: `NIUA_SKIP_BLENDER=1 python -m pytest -q`
Expected: 767 passed, 71 skipped. If live checks forced code changes, commit them:

```bash
git commit -am "fix: live-verification adjustments (product hardening)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review (performed while writing)

- **Spec coverage:** W1 `system.health` → Task 3; timeout tiers → Tasks 1–2; progress+cancel, never-wedged main thread → Task 4 (sideband); supervisor one-command self-heal + session restore → Task 5. W2 describe_tools navigation → Task 6; teaching errors → Task 7 (+ Task 4's cancel/timeout details, Task 6's navigation misses); param-convention audit + spec-lint → Task 8; turns metric in bench report → Task 9. W4 JSONL middleware → Task 10; HTML report script → Task 11. Live-only claims → Task 12.
- **Deliberate scope calls:** heavy-tier assignment is conservative (5 feedback measures + 3 io tools; everything else stays at today's de-facto 60s) — broad `fast` assignment risks false timeouts on giant scenes and is a later tuning pass. Cancellation is cooperative plumbing (`ctx.progress`/`ctx.check_cancelled` available to every handler) + always-on op visibility; wiring checks into individual finishing loops is policy-layer follow-up work, deliberately out of this interface-layer plan.
- **Byte-identity resolution:** `meta.timestamp` already varies per run, so "byte-identical" is interpreted (and enforced in Task 12) as: the `items` and `reading` sections and all five readiness/preservation numbers are unchanged; Task 9 adds keys to `meta` only.
- **Type consistency:** `timeout_tier` string field identical on `ToolSpec`/`Command`; `BlenderBridge.call(..., timeout: float | None)` used by server (Task 1), supervisor CLI (Task 5), `_CountingBridge` (Task 9); all fake bridges in tests accept the `timeout` kwarg; `teach(...)`/`detail={"fix","next_call"}` shape shared by Tasks 4, 6, 7; JSONL keys written by Task 10 = keys read by Task 11.
- **Placeholder scan:** every code step contains complete code; the one intentionally-deleted stub in Task 10 Step 1 is explicitly instructed to not exist in the final file.
