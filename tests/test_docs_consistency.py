"""The task queue must have exactly one source of truth.

docs/tasks/INDEX.md used to be maintained by hand next to tasks.json, and the
two had already started to disagree.  The table in INDEX.md is now generated
from tasks.json; these tests fail when it drifts or when a card goes missing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.render_task_index as render


def _tasks() -> list[dict[str, object]]:
    return json.loads(render.TASKS_JSON.read_text(encoding="utf-8"))


def test_index_table_is_generated_from_tasks_json() -> None:
    assert render.main(["--check"]) == 0, (
        "docs/tasks/INDEX.md is stale; run python3 tools/render_task_index.py"
    )


def test_every_task_has_a_card_and_a_unique_id() -> None:
    tasks = _tasks()
    ids = [task["id"] for task in tasks]
    assert len(ids) == len(set(ids))
    for task in tasks:
        card = Path(render.ROOT) / str(task["path"])
        assert card.is_file(), f"missing card for {task['id']}: {task['path']}"


def test_dependencies_reference_known_tasks() -> None:
    tasks = _tasks()
    known = {task["id"] for task in tasks}
    for task in tasks:
        for dependency in task.get("depends_on") or []:
            assert dependency in known, f"{task['id']} depends on unknown {dependency}"


@pytest.mark.parametrize("field", ["status", "title", "gate", "priority"])
def test_required_fields_are_present(field: str) -> None:
    for task in _tasks():
        assert task.get(field), f"{task['id']} has no {field}"


def test_status_values_are_from_the_documented_set() -> None:
    allowed = {"ready", "waiting_dependencies", "in_progress", "in_review", "accepted", "blocked"}
    for task in _tasks():
        assert task["status"] in allowed, f"{task['id']} has status {task['status']!r}"
