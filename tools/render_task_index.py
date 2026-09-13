#!/usr/bin/env python3
"""Render the task table in docs/tasks/INDEX.md from docs/tasks/tasks.json.

The queue used to be maintained by hand in four places (INDEX.md, tasks.json,
STATUS.md and ROADMAP.md) and had already drifted.  tasks.json is the source of
truth for ID, title, dependencies, status and GitHub links; this script writes
that table into INDEX.md between the generated markers and leaves the
surrounding prose alone.

    python3 tools/render_task_index.py           # rewrite INDEX.md
    python3 tools/render_task_index.py --check   # fail if INDEX.md is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_JSON = ROOT / "docs" / "tasks" / "tasks.json"
INDEX_MD = ROOT / "docs" / "tasks" / "INDEX.md"
BEGIN = "<!-- BEGIN GENERATED TASK TABLE -->"
END = "<!-- END GENERATED TASK TABLE -->"
HEADER = (
    "| ID | Задача | Зависимости | Статус | GitHub |\n"
    "|---|---|---|---|---|"
)


def _issue_link(url: str) -> str:
    return f"[#{url.rstrip('/').rsplit('/', 1)[-1]}]({url})"


def _pr_link(url: str) -> str:
    return f"[PR #{url.rstrip('/').rsplit('/', 1)[-1]}]({url})"


def render_row(task: dict[str, object]) -> str:
    task_id = str(task["id"])
    raw_depends = task.get("depends_on")
    depends_list = raw_depends if isinstance(raw_depends, list) else []
    depends = ", ".join(str(item) for item in depends_list) or "—"
    status = str(task.get("status_display") or task["status"])
    links = []
    issue = task.get("github_issue")
    if isinstance(issue, str) and issue:
        links.append(_issue_link(issue))
    pull = task.get("github_pr")
    if isinstance(pull, str) and pull:
        links.append(_pr_link(pull))
    github = ", ".join(links) or "—"
    return f"| [{task_id}]({task_id}.md) | {task['title']} | {depends} | {status} | {github} |"


def render_table(tasks: list[dict[str, object]]) -> str:
    rows = "\n".join(render_row(task) for task in tasks)
    return f"{BEGIN}\n\n{HEADER}\n{rows}\n\n{END}"


def render_index(index_text: str, tasks: list[dict[str, object]]) -> str:
    if BEGIN not in index_text or END not in index_text:
        raise SystemExit(
            f"{INDEX_MD} has no generated-table markers; add {BEGIN} / {END} around the table"
        )
    head, rest = index_text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + render_table(tasks) + tail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify INDEX.md is up to date")
    args = parser.parse_args(argv)

    tasks = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
    current = INDEX_MD.read_text(encoding="utf-8")
    rendered = render_index(current, tasks)

    if args.check:
        if rendered != current:
            print(
                "docs/tasks/INDEX.md is out of date; run python3 tools/render_task_index.py",
                file=sys.stderr,
            )
            return 1
        return 0

    if rendered != current:
        INDEX_MD.write_text(rendered, encoding="utf-8")
        print(f"updated {INDEX_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
