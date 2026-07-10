"""Socket server + main-thread drain.

Background socket threads enqueue requests; the queue is drained on Blender's main
thread. Two drivers:
  * GUI:      bpy.app.timers drives _drain every frame (Blender's event loop keeps it alive).
  * headless: serve_blocking() runs a main-thread drain loop (no GUI event loop exists).

bpy is imported lazily so this module stays importable for tests without Blender.
"""

from __future__ import annotations

import collections
import itertools
import json
import queue
import socketserver
import threading
import time
import traceback

from .dispatch import dispatch_on_main
from .errors import BridgeError

_REQUESTS: "queue.Queue" = queue.Queue()
_SERVER: socketserver.ThreadingTCPServer | None = None
_THREAD: threading.Thread | None = None
_REGISTRY = None
_ALLOW_PYTHON = False
_LAST_ACTIVITY = 0.0

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


class _Box:
    __slots__ = ("event", "value", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.value = None
        self.error = None


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


def _clamp_timeout(value) -> float:
    """Per-request wait from the wire (BlenderBridge sends 'timeout'), clamped sane."""
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 60.0
    return min(max(timeout, 1.0), 600.0)


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline()
        if not line:
            return
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
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


def _drain() -> float:
    """Run on the MAIN thread. Execute every queued request, then reschedule."""
    import bpy  # noqa: PLC0415 - runtime only

    from .context import Ctx

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
    return 0.02  # reschedule interval for the GUI timer


def _start_socket(port: int, allow_python: bool) -> None:
    global _SERVER, _THREAD, _REGISTRY, _ALLOW_PYTHON, _LAST_ACTIVITY
    from .domains import build_default_registry

    if _SERVER is not None:
        return
    _REGISTRY = build_default_registry()
    _ALLOW_PYTHON = allow_python
    _LAST_ACTIVITY = time.time()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), _Handler)
    server.daemon_threads = True
    _SERVER = server
    _THREAD = threading.Thread(target=server.serve_forever, daemon=True)
    _THREAD.start()


def start(port: int = 8765, allow_python: bool = False) -> None:
    """GUI start: socket server + bpy.app.timers drain."""
    import bpy  # noqa: PLC0415

    _start_socket(port, allow_python)
    if not bpy.app.timers.is_registered(_drain):
        bpy.app.timers.register(_drain, persistent=True)


def stop() -> None:
    global _SERVER, _THREAD
    try:
        import bpy  # noqa: PLC0415

        if bpy.app.timers.is_registered(_drain):
            bpy.app.timers.unregister(_drain)
    except Exception:  # noqa: BLE001
        pass
    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER.server_close()
    if _THREAD is not None:
        _THREAD.join(timeout=2)
    _SERVER = None
    _THREAD = None


def is_running() -> bool:
    return _SERVER is not None


def serve_blocking(port: int = 8765, allow_python: bool = False, idle_timeout: float = 30.0) -> None:
    """Headless driver: drain on the main thread until idle_timeout of no requests."""
    _start_socket(port, allow_python)
    try:
        while time.time() - _LAST_ACTIVITY < idle_timeout:
            _drain()
            time.sleep(0.01)
    finally:
        stop()
