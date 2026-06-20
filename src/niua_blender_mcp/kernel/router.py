"""Router: the registry that maps tool names to ToolSpecs.

Domain packs register their specs here. Curated specs win over RNA-generated ones
on a name collision, regardless of registration order, so hand-tuned tools always
override the auto-generated long tail. ``select`` supports lazy loading by category.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contract import ToolSpec

_TIER_RANK = {"curated": 3, "generated": 2, "reflection": 1}


def _rank(spec: ToolSpec) -> int:
    if spec.source != "curated" and spec.tier == "curated":
        return 0
    return _TIER_RANK.get(spec.tier, 0)


@dataclass
class Router:
    _specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        existing = self._specs.get(spec.name)
        if existing is not None:
            # Higher-priority tier wins; equal tier => last write wins.
            if _rank(existing) > _rank(spec):
                return
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

    def index(self) -> list[dict]:
        return [
            {"id": s.name, "summary": s.summary, "category": s.category, "tier": s.tier}
            for s in self._specs.values()
        ]

    def select(self, categories: set[str] | None = None) -> list[ToolSpec]:
        if categories is None:
            return self.specs()
        return [spec for spec in self._specs.values() if spec.category in categories]
