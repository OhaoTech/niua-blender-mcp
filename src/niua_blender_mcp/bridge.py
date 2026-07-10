"""TCP bridge client: the server's link to the Blender add-on.

Newline-delimited JSON over a localhost socket. One request, one response line.
The add-on enqueues the request and a main-thread timer produces the result, so the
only thing this client does is frame, send, and parse, with timeouts and a uniform
error type.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any

from .kernel.errors import McpError, TRANSPORT


class BridgeError(McpError):
    """A failure talking to (or reported by) the Blender add-on."""


@dataclass(frozen=True)
class BlenderBridge:
    host: str = "127.0.0.1"
    port: int = 8765
    timeout: float = 30.0

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

        if not line:
            raise BridgeError(TRANSPORT, "empty response from Blender bridge")
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BridgeError(TRANSPORT, f"invalid JSON from bridge: {line!r}") from exc

        if not isinstance(decoded, dict):
            raise BridgeError(TRANSPORT, "bridge response was not a JSON object")
        if decoded.get("ok") is not True:
            error = decoded.get("error") or {}
            raise BridgeError(
                str(error.get("code", "bridge_error")),
                str(error.get("message", "Blender bridge command failed")),
                error.get("detail"),
            )
        result = decoded.get("result")
        return result if isinstance(result, dict) else {}
