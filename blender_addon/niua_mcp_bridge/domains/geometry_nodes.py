"""Geometry Nodes handlers: create default node modifiers and inspect node groups."""

from __future__ import annotations

from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import NOT_FOUND, PRECONDITION, BridgeError


def _modifiers(obj: Any) -> list[Any]:
    return list(getattr(obj, "modifiers", []) or [])


def _find_node_modifier(obj: Any, name: str = "") -> Any:
    if name:
        getter = getattr(getattr(obj, "modifiers", None), "get", None)
        mod = getter(name) if callable(getter) else None
        if mod is None:
            raise BridgeError(NOT_FOUND, f"modifier not found: {name}", {"object": getattr(obj, "name", "?")})
    else:
        mod = next((candidate for candidate in _modifiers(obj) if getattr(candidate, "type", None) == "NODES"), None)
        if mod is None:
            raise BridgeError(NOT_FOUND, "geometry nodes modifier not found", {"object": getattr(obj, "name", "?")})
    if getattr(mod, "type", None) != "NODES":
        raise BridgeError(
            PRECONDITION,
            f"modifier is not Geometry Nodes: {getattr(mod, 'name', '?')}",
            {"type": getattr(mod, "type", None)},
        )
    if getattr(mod, "node_group", None) is None:
        raise BridgeError(PRECONDITION, f"Geometry Nodes modifier has no node group: {getattr(mod, 'name', '?')}")
    return mod


def _float_pair(value: Any) -> list[float]:
    try:
        return [float(value[0]), float(value[1])]
    except Exception:  # noqa: BLE001 - fake sockets and partial node locations
        return []


def _socket_report(socket: Any) -> dict:
    return {
        "name": getattr(socket, "name", ""),
        "identifier": getattr(socket, "identifier", ""),
        "type": getattr(socket, "type", ""),
        "enabled": bool(getattr(socket, "enabled", True)),
        "is_linked": bool(getattr(socket, "is_linked", False)),
    }


def _node_report(node: Any) -> dict:
    return {
        "name": getattr(node, "name", ""),
        "label": getattr(node, "label", ""),
        "bl_idname": getattr(node, "bl_idname", ""),
        "type": getattr(node, "type", ""),
        "location": _float_pair(getattr(node, "location", [])),
        "inputs": [_socket_report(socket) for socket in list(getattr(node, "inputs", []) or [])],
        "outputs": [_socket_report(socket) for socket in list(getattr(node, "outputs", []) or [])],
    }


def _interface_report(group: Any) -> list[dict]:
    interface = getattr(group, "interface", None)
    return [
        {
            "name": getattr(item, "name", ""),
            "item_type": getattr(item, "item_type", ""),
            "in_out": getattr(item, "in_out", ""),
            "socket_type": getattr(item, "socket_type", ""),
        }
        for item in list(getattr(interface, "items_tree", []) or [])
    ]


def _link_report(link: Any) -> dict:
    return {
        "from_node": getattr(getattr(link, "from_node", None), "name", ""),
        "from_socket": getattr(getattr(link, "from_socket", None), "name", ""),
        "to_node": getattr(getattr(link, "to_node", None), "name", ""),
        "to_socket": getattr(getattr(link, "to_socket", None), "name", ""),
    }


def _group_report(obj: Any, mod: Any) -> dict:
    group = mod.node_group
    return {
        "object": getattr(obj, "name", ""),
        "modifier": getattr(mod, "name", ""),
        "node_group": getattr(group, "name", ""),
        "interface": _interface_report(group),
        "nodes": [_node_report(node) for node in list(getattr(group, "nodes", []) or [])],
        "links": [_link_report(link) for link in list(getattr(group, "links", []) or [])],
    }


def _new_nodes_modifier(obj: Any, before_names: set[str]) -> Any:
    created = [
        mod
        for mod in _modifiers(obj)
        if getattr(mod, "type", None) == "NODES" and getattr(mod, "name", "") not in before_names
    ]
    if created:
        return created[-1]
    for mod in reversed(_modifiers(obj)):
        if getattr(mod, "type", None) == "NODES":
            return mod
    raise BridgeError(PRECONDITION, "Geometry Nodes modifier was not created")


def create_modifier(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    before_names = {getattr(mod, "name", "") for mod in _modifiers(obj)}
    op = ctx.bpy.ops.node.new_geometry_nodes_modifier
    with ctx.ensure(active=obj, mode="OBJECT", select=[obj]):
        ctx.check_poll(op)
        op()
    mod = _new_nodes_modifier(obj, before_names)
    name = payload.get("name")
    if isinstance(name, str) and name:
        mod.name = name
    return _group_report(obj, mod)


def report(ctx: Ctx, payload: dict) -> dict:
    obj = ctx.get_object(payload.get("object"))
    mod = _find_node_modifier(obj, str(payload.get("modifier", "")))
    return _group_report(obj, mod)


COMMANDS = [
    Command("geometry_nodes.create_modifier", create_modifier, mutates=True, feedback="viewport"),
    Command("geometry_nodes.report", report, mutates=False),
]
