"""The Skill abstraction: a named, described, code-mode finishing procedure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    asset_classes: tuple[str, ...]
    run: Callable[[Any, str, dict], dict]  # (ToolSession, subject, params) -> report
