"""Router: the registry that maps tool names to ToolSpecs.

Domain packs register their specs here. Curated specs win over RNA-generated ones
on a name collision, regardless of registration order, so hand-tuned tools always
override the auto-generated long tail. ``select`` supports lazy loading by category.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import ToolSpec


@dataclass
class Router:
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        existing = self._specs.get(spec.name)
        if existing is not None and existing.source == "curated" and spec.source != "curated":
            return  # never let a generated spec clobber a curated one
        self._specs[spec.name] = spec

    def add(self, specs: list[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def categories(self) -> set[str]:
        return {spec.category for spec in self._specs.values()}

    def select(self, categories: set[str] | None = None) -> list[ToolSpec]:
        if categories is None:
            return self.specs()
        return [spec for spec in self._specs.values() if spec.category in categories]
