"""Skills registry: the cheap progressive-disclosure index over finishing skills."""

from __future__ import annotations

from .base import Skill
from .bake_and_finish import SKILL as _BAKE_AND_FINISH
from .make_game_ready import SKILL as _MAKE_GAME_READY

_SKILLS: dict[str, Skill] = {
    _MAKE_GAME_READY.name: _MAKE_GAME_READY,
    _BAKE_AND_FINISH.name: _BAKE_AND_FINISH,
}


def list_skills() -> list[dict]:
    return [{"name": s.name, "description": s.description, "asset_classes": list(s.asset_classes)}
            for s in _SKILLS.values()]


def get_skill(name: str) -> Skill:
    try:
        return _SKILLS[name]
    except KeyError as exc:
        raise KeyError(f"unknown skill: {name}") from exc
