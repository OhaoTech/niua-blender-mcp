"""Senior task battery loader.

Each task is a folder with task.json plus rubric.md.
"""

from __future__ import annotations

import json
import os

_HERE = os.path.dirname(__file__)


def load_task(task_id: str) -> dict:
    folder = os.path.join(_HERE, task_id)
    with open(os.path.join(folder, "task.json")) as handle:
        task = json.load(handle)
    with open(os.path.join(folder, "rubric.md")) as handle:
        task["rubric"] = handle.read()
    return task
