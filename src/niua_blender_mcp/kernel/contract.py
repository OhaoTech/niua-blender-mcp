"""The tool contract: ToolSpec + parameter descriptors + validation.

One ToolSpec defines a tool once. The server turns it into an MCP tool definition
and a bridge command; the add-on maps the command to a handler. Validation runs
server-side before dispatch so handlers receive clean, typed arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import ValidationError

# JSON-schema primitive kinds we support.
_KINDS = {"string", "number", "integer", "boolean", "enum", "array"}


@dataclass(frozen=True)
class Param:
    kind: str
    required: bool = False
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] | None = None
    length: int | None = None  # fixed array length (e.g. 3 for a vector)
    item: str = "number"  # element kind for arrays
    summary: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"unknown param kind: {self.kind}")


def Str(required: bool = False, default: Any = None, summary: str = "", description: str = "") -> Param:
    return Param("string", required, default, summary=summary, description=description)


def Int(
    required: bool = False,
    default: Any = None,
    minimum: float | None = None,
    maximum: float | None = None,
    summary: str = "",
    description: str = "",
) -> Param:
    return Param("integer", required, default, minimum, maximum, summary=summary, description=description)


def Float(
    required: bool = False,
    default: Any = None,
    minimum: float | None = None,
    maximum: float | None = None,
    summary: str = "",
    description: str = "",
) -> Param:
    return Param("number", required, default, minimum, maximum, summary=summary, description=description)


def Bool(required: bool = False, default: Any = None, summary: str = "", description: str = "") -> Param:
    return Param("boolean", required, default, summary=summary, description=description)


def Enum(
    choices: list[Any] | tuple[Any, ...],
    required: bool = False,
    default: Any = None,
    summary: str = "",
    description: str = "",
) -> Param:
    return Param("enum", required, default, choices=tuple(choices), summary=summary, description=description)


def Vec3(required: bool = False, default: Any = None, summary: str = "", description: str = "") -> Param:
    """A fixed-length 3-array of numbers (location / rotation / scale)."""
    return Param("array", required, default, length=3, item="number", summary=summary, description=description)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    category: str
    summary: str
    command: str
    params: dict[str, Param] = field(default_factory=dict)
    mutates: bool = False
    feedback: str | None = None
    source: str = "curated"  # "curated" | "rna"; curated wins on name collision

    def input_schema(self) -> dict[str, Any]:
        """Render an MCP/JSON-Schema object for this tool's arguments."""
        props: dict[str, Any] = {}
        required: list[str] = []
        for pname, p in self.params.items():
            entry: dict[str, Any] = {}
            if p.kind == "enum":
                entry["enum"] = list(p.choices or ())
            elif p.kind == "array":
                entry["type"] = "array"
                entry["items"] = {"type": p.item}
                if p.length is not None:
                    entry["minItems"] = p.length
                    entry["maxItems"] = p.length
            else:
                entry["type"] = p.kind
            if p.summary:
                entry["title"] = p.summary
            if p.description:
                entry["description"] = p.description
            if p.default is not None:
                entry["default"] = p.default
            if p.minimum is not None:
                entry["minimum"] = p.minimum
            if p.maximum is not None:
                entry["maximum"] = p.maximum
            props[pname] = entry
            if p.required:
                required.append(pname)
        schema: dict[str, Any] = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return schema


def _coerce(name: str, p: Param, value: Any) -> Any:
    if p.kind == "boolean":
        if not isinstance(value, bool):
            raise ValidationError(f"{name} must be a boolean", {"got": repr(value)})
        return value
    if p.kind == "string":
        if not isinstance(value, str):
            raise ValidationError(f"{name} must be a string", {"got": repr(value)})
        return value
    if p.kind == "integer":
        # bool is an int subclass; reject it explicitly.
        if isinstance(value, bool):
            raise ValidationError(f"{name} must be an integer", {"got": repr(value)})
        if isinstance(value, float) and not value.is_integer():
            raise ValidationError(f"{name} must be an integer", {"got": value})
        if not isinstance(value, (int, float)):
            raise ValidationError(f"{name} must be an integer", {"got": repr(value)})
        ivalue = int(value)
        _check_range(name, p, ivalue)
        return ivalue
    if p.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValidationError(f"{name} must be a number", {"got": repr(value)})
        fvalue = float(value)
        _check_range(name, p, fvalue)
        return fvalue
    if p.kind == "enum":
        if value not in (p.choices or ()):
            raise ValidationError(
                f"{name} must be one of {list(p.choices or ())}", {"got": repr(value)}
            )
        return value
    if p.kind == "array":
        if not isinstance(value, (list, tuple)):
            raise ValidationError(f"{name} must be an array", {"got": repr(value)})
        if p.length is not None and len(value) != p.length:
            raise ValidationError(f"{name} must have exactly {p.length} items", {"got": value})
        item = Param(p.item)
        return [_coerce(f"{name}[{i}]", item, v) for i, v in enumerate(value)]
    raise ValidationError(f"{name} has unsupported kind {p.kind}")


def _check_range(name: str, p: Param, value: float) -> None:
    if p.minimum is not None and value < p.minimum:
        raise ValidationError(f"{name} below minimum {p.minimum}", {"got": value})
    if p.maximum is not None and value > p.maximum:
        raise ValidationError(f"{name} above maximum {p.maximum}", {"got": value})


def validate(spec: ToolSpec, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and coerce a payload against a spec.

    Returns cleaned args with defaults filled. Unknown params are ignored for
    forward-compatibility. Raises ValidationError on any violation.
    """
    payload = payload or {}
    out: dict[str, Any] = {}
    for pname, p in spec.params.items():
        if pname in payload and payload[pname] is not None:
            out[pname] = _coerce(pname, p, payload[pname])
        elif p.required:
            raise ValidationError(f"missing required param: {pname}")
        elif p.default is not None:
            out[pname] = p.default
    return out
