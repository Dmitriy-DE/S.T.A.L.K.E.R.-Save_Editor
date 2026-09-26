from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from editor.drafts import DraftJournal, DraftStore
from editor.models import EditPlan, SourceRef


def _source(data: bytes, locator: str) -> SourceRef:
    return SourceRef(
        kind="local",
        locator=locator,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def test_saved_draft_survives_store_recreation_without_persisting_source_locator(
    tmp_path,
) -> None:
    data = b"synthetic save bytes"
    source = _source(data, "private-slot-name.sav")
    empty = EditPlan(source=source)
    plan = EditPlan(source=source, money=450_000, stacks=((0x1234, 12),))
    drafts_dir = tmp_path / "drafts"

    DraftStore(drafts_dir).save(source.sha256, (empty, plan), 1)
    draft_path = drafts_dir / f"{source.sha256}.json"
    serialized = draft_path.read_text(encoding="utf-8")
    recovered = DraftStore(drafts_dir).load(
        source.sha256,
        _source(data, "another-current-locator.sav"),
    )

    assert "private-slot-name.sav" not in serialized
    assert "another-current-locator.sav" not in serialized
    assert recovered == DraftJournal(
        (
            EditPlan(source=_source(data, "another-current-locator.sav")),
            EditPlan(
                source=_source(data, "another-current-locator.sav"),
                money=450_000,
                stacks=((0x1234, 12),),
            ),
        ),
        1,
    )


def test_draft_survives_abrupt_process_exit(tmp_path) -> None:
    data = b"synthetic save"
    source = _source(data, "synthetic-slot.sav")
    drafts_dir = tmp_path / "drafts"
    project_root = Path(__file__).resolve().parents[1]
    script = """
import os
import sys
from pathlib import Path
from editor.drafts import DraftStore
from editor.models import EditPlan, SourceRef

source = SourceRef(kind="local", locator="synthetic-slot.sav", sha256=sys.argv[2])
empty = EditPlan(source=source)
plan = EditPlan(source=source, money=451)
DraftStore(Path(sys.argv[1])).save(source.sha256, (empty, plan), 1)
os._exit(23)
"""

    process = subprocess.run(
        [sys.executable, "-c", script, str(drafts_dir), source.sha256],
        cwd=project_root,
        check=False,
    )

    assert process.returncode == 23
    recovered = DraftStore(drafts_dir).load(source.sha256, source)
    assert recovered is not None
    assert recovered.current.money == 451


def test_draft_for_old_save_sha_is_not_loaded_for_changed_save(tmp_path) -> None:
    original = b"original synthetic save"
    changed = b"changed synthetic save"
    old_source = _source(original, "slot.sav")
    new_source = _source(changed, "slot.sav")
    plan = EditPlan(source=old_source, money=123)
    store = DraftStore(tmp_path / "drafts")

    store.save(old_source.sha256, (EditPlan(source=old_source), plan), 1)

    assert store.load(new_source.sha256, new_source) is None
    assert (tmp_path / "drafts" / f"{old_source.sha256}.json").is_file()


def test_discarding_all_staged_changes_removes_recovery_file(tmp_path) -> None:
    source = _source(b"save", "slot.sav")
    store = DraftStore(tmp_path / "drafts")
    draft_path = tmp_path / "drafts" / f"{source.sha256}.json"

    store.save(
        source.sha256,
        (EditPlan(source=source), EditPlan(source=source, money=900)),
        1,
    )
    store.save(source.sha256, (EditPlan(source=source),), 0)

    assert not draft_path.exists()


def test_invalid_or_mismatched_draft_file_is_ignored(tmp_path) -> None:
    data = b"synthetic save"
    source = _source(data, "slot.sav")
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    draft_path = drafts_dir / f"{source.sha256}.json"
    draft_path.write_text(
        json.dumps({"schema": 1, "source_sha256": "0" * 64, "plans": [], "index": 0}),
        encoding="utf-8",
    )

    assert DraftStore(drafts_dir).load(source.sha256, source) is None


def test_boolean_schema_version_is_not_treated_as_version_one(tmp_path) -> None:
    data = b"synthetic save"
    source = _source(data, "slot.sav")
    store = DraftStore(tmp_path / "drafts")
    store.save(
        source.sha256,
        (EditPlan(source=source), EditPlan(source=source, money=123)),
        1,
    )
    draft_path = store.path_for(source.sha256)
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    payload["schema"] = True
    draft_path.write_text(json.dumps(payload), encoding="utf-8")

    assert store.load(source.sha256, source) is None


def test_oversized_history_keeps_current_draft_recoverable(tmp_path) -> None:
    source = _source(b"synthetic save", "slot.sav")
    empty = EditPlan(source=source)
    current = EditPlan(
        source=source,
        money=900,
        stacks=tuple((handle, 2) for handle in range(1, 1001)),
    )
    history = (empty,) + (current,) * 400
    store = DraftStore(tmp_path / "drafts")

    store.save(source.sha256, history, len(history) - 1)

    recovered = store.load(source.sha256, source)
    assert recovered is not None
    assert recovered.current == current
    assert len(recovered.plans) == 2
