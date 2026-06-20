"""Playbook store: senior recipes and heuristics for the growing Layer 2.

Seeded by hand, then extended by the Phase-B convergence loop. Plain markdown
keeps every playbook change human-reviewable at checkpoints.
"""

from __future__ import annotations

import os

_HERE = os.path.dirname(__file__)


def list_playbooks() -> list[str]:
    return sorted(name[:-3] for name in os.listdir(_HERE) if name.endswith(".md"))


def load_playbook(name: str) -> str:
    with open(os.path.join(_HERE, f"{name}.md")) as handle:
        return handle.read()
