"""ToolSession: the code-mode entrypoint. session.<domain>.<tool>(**kwargs) -> bridge.call."""

from __future__ import annotations

import importlib
from typing import Any


def _drop_none(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if v is not None}


class _DomainNamespace:
    """Binds a domain's generated functions to a session: ns.tool(**kw)."""

    def __init__(self, session: "ToolSession", module: Any) -> None:
        self._session = session
        self._module = module

    def __getattr__(self, tool: str):
        fn = getattr(self._module, tool, None)
        if fn is None or tool.startswith("_"):
            raise AttributeError(tool)
        return lambda **kwargs: fn(self._session, **kwargs)


class ToolSession:
    """Wraps a bridge; exposes generated tool functions as session.<domain>.<tool>()."""

    def __init__(self, bridge: Any) -> None:
        self.bridge = bridge
        self._namespaces: dict[str, _DomainNamespace] = {}

    def call(self, command: str, args: dict) -> Any:
        return self.bridge.call(command, args)

    def __getattr__(self, domain: str):
        if domain.startswith("_"):
            raise AttributeError(domain)
        cache = self.__dict__.setdefault("_namespaces", {})
        if domain not in cache:
            try:
                module = importlib.import_module(f"niua_blender_mcp.client.tools.{domain}")
            except ModuleNotFoundError as exc:
                raise AttributeError(domain) from exc
            cache[domain] = _DomainNamespace(self, module)
        return cache[domain]
