"""Text Editor GUI-parity handlers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..context import Ctx
from ..dispatch import Command
from ..errors import INVALID_PARAMS, NOT_FOUND, PRECONDITION, BridgeError


def _require_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(PRECONDITION, f"{field} is required")
    return value


def _require_body(value: Any) -> str:
    if not isinstance(value, str):
        raise BridgeError(INVALID_PARAMS, "body must be a string")
    return value


def _require_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise BridgeError(INVALID_PARAMS, "path is required")
    path = os.path.abspath(os.path.expanduser(value))
    if not os.path.exists(path):
        raise BridgeError(INVALID_PARAMS, f"path does not exist: {value}")
    return path


def _texts(ctx: Ctx) -> list[Any]:
    try:
        return list(getattr(ctx.bpy.data, "texts", []) or [])
    except TypeError:
        return []


def _require_text(ctx: Ctx, name: Any) -> Any:
    text_name = _require_name(name, "name")
    text = getattr(ctx.bpy.data.texts, "get", lambda _name: None)(text_name)
    if text is None:
        raise BridgeError(NOT_FOUND, f"text not found: {text_name}")
    return text


def _body(text: Any) -> str:
    as_string = getattr(text, "as_string", None)
    if callable(as_string):
        return str(as_string())
    return ""


def _line_count(body: str) -> int:
    return len(body.splitlines())


def _summary(text: Any, include_body: bool = False) -> dict[str, Any]:
    body = _body(text)
    out = {
        "name": getattr(text, "name", ""),
        "filepath": getattr(text, "filepath", ""),
        "is_dirty": bool(getattr(text, "is_dirty", False)),
        "is_modified": bool(getattr(text, "is_modified", False)),
        "is_in_memory": bool(getattr(text, "is_in_memory", False)),
        "use_module": bool(getattr(text, "use_module", False)),
        "indentation": getattr(text, "indentation", None),
        "line_count": _line_count(body),
        "char_count": len(body),
    }
    if include_body:
        out["body"] = body
    return out


def _replace_body(text: Any, body: str) -> None:
    from_string = getattr(text, "from_string", None)
    if callable(from_string):
        from_string(body)
        return
    clear = getattr(text, "clear", None)
    write = getattr(text, "write", None)
    if callable(clear):
        clear()
    if callable(write):
        write(body)
        return
    raise BridgeError(INVALID_PARAMS, "text data-block does not support writing")


def list_texts(ctx: Ctx, payload: dict) -> dict:
    texts = [_summary(text) for text in _texts(ctx)]
    return {"text_count": len(texts), "texts": texts}


def create(ctx: Ctx, payload: dict) -> dict:
    name = _require_name(payload.get("name"), "name")
    text = ctx.bpy.data.texts.new(name)
    body = payload.get("body", "")
    if body:
        _replace_body(text, _require_body(body))
    return _summary(text, include_body=True)


def open_text(ctx: Ctx, payload: dict) -> dict:
    path = _require_path(payload.get("path"))
    text = ctx.bpy.data.texts.load(path)
    name = payload.get("name")
    if isinstance(name, str) and name:
        text.name = name
    return _summary(text, include_body=True)


def read(ctx: Ctx, payload: dict) -> dict:
    return _summary(_require_text(ctx, payload.get("name")), include_body=True)


def write(ctx: Ctx, payload: dict) -> dict:
    text = _require_text(ctx, payload.get("name"))
    _replace_body(text, _require_body(payload.get("body")))
    return _summary(text, include_body=True)


def append(ctx: Ctx, payload: dict) -> dict:
    text = _require_text(ctx, payload.get("name"))
    write_method = getattr(text, "write", None)
    if not callable(write_method):
        raise BridgeError(INVALID_PARAMS, "text data-block does not support append")
    write_method(_require_body(payload.get("body")))
    return _summary(text, include_body=True)


def save(ctx: Ctx, payload: dict) -> dict:
    text = _require_text(ctx, payload.get("name"))
    raw_path = payload.get("path")
    path = raw_path if isinstance(raw_path, str) and raw_path else getattr(text, "filepath", "")
    if not isinstance(path, str) or not path:
        raise BridgeError(INVALID_PARAMS, "path is required when text has no filepath")
    path = os.path.abspath(os.path.expanduser(path))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(_body(text), encoding="utf-8")
    if hasattr(text, "filepath"):
        text.filepath = path
    out = _summary(text, include_body=True)
    out["path"] = path
    return out


def remove(ctx: Ctx, payload: dict) -> dict:
    text = _require_text(ctx, payload.get("name"))
    name = getattr(text, "name", "")
    ctx.bpy.data.texts.remove(text)
    return {"removed": name, "text_count": len(_texts(ctx))}


COMMANDS = [
    Command("text.list", list_texts, mutates=False),
    Command("text.create", create, mutates=True, feedback="viewport"),
    Command("text.open", open_text, mutates=True, feedback="viewport"),
    Command("text.read", read, mutates=False),
    Command("text.write", write, mutates=True, feedback="viewport"),
    Command("text.append", append, mutates=True, feedback="viewport"),
    Command("text.save", save, mutates=True, feedback="viewport"),
    Command("text.remove", remove, mutates=True, feedback="viewport"),
]
