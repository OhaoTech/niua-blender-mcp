"""Skills registry: finishing procedures the product can run.

DEFAULT_SKILL is the only path agents and the benchmark should use for dense
generator meshes. Legacy skills remain callable by name for comparison/debug.
"""

from __future__ import annotations

from .base import Skill
from .bake_and_finish import SKILL as _BAKE_AND_FINISH
from .make_game_ready import SKILL as _MAKE_GAME_READY

# Product default (anti-blob bake path). evals/finisher.py and run_skill.py align with this.
DEFAULT_SKILL = _BAKE_AND_FINISH.name

# name -> skill; default listed first in list_skills()
_SKILLS: dict[str, Skill] = {
    _BAKE_AND_FINISH.name: _BAKE_AND_FINISH,
    _MAKE_GAME_READY.name: _MAKE_GAME_READY,
}

# Explicit legacy set (raw decimate / no bake). Prefer DEFAULT_SKILL for production.
LEGACY_SKILLS = frozenset({_MAKE_GAME_READY.name})


def list_skills() -> list[dict]:
    """Default skill first; each entry notes whether it is legacy."""
    names = [DEFAULT_SKILL] + [n for n in _SKILLS if n != DEFAULT_SKILL]
    out = []
    for name in names:
        s = _SKILLS[name]
        out.append({
            "name": s.name,
            "description": s.description,
            "asset_classes": list(s.asset_classes),
            "default": name == DEFAULT_SKILL,
            "legacy": name in LEGACY_SKILLS,
        })
    return out


def get_skill(name: str) -> Skill:
    try:
        return _SKILLS[name]
    except KeyError as exc:
        raise KeyError(f"unknown skill: {name}") from exc


def get_default_skill() -> Skill:
    return _SKILLS[DEFAULT_SKILL]
