# M01 Format Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the existing S.T.A.L.K.E.R. 2 inspection and edit preparation through a static save-format registry while exposing the selected format on UI snapshots.

**Architecture:** Add one registry module with a `SaveFormat` Protocol and a S.T.A.L.K.E.R. 2 adapter that delegates to the existing parser and prepare path. Keep `EditorService.inspect` and `.prepare` return types unchanged, add an internal typed inspection result for workers, and carry format metadata on local/cloud snapshots without modifying `save_format.py`.

**Tech Stack:** Python 3.11/3.12 target, current stdlib core, dataclasses, typing.Protocol, PySide6 snapshots, pytest/pytest-qt, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-09-15-m01-format-registry-design.md`

## Global Constraints

- The registry is static in code and contains exactly one implementation in M01.
- Do not change `save_format.py` or reuse a second parser implementation.
- Detection uses bytes only; filename and `.sav` extension are irrelevant.
- Preserve immutable `EditPlan`, source SHA binding, backup, atomic export, CRC, and round-trip checks.
- Shared format selection stays in `editor/`, not in Qt or CLI code.
- Keep `EditorService.inspect(data, *, with_inventory=True) -> SaveInfo` and `.prepare(data, plan) -> PreparedEdit` compatible.
- No personal saves, screenshots, credentials, or generated local settings enter Git.

---

### Task 1: Add failing registry and service-contract tests

**Files:**
- Create: `tests/test_formats.py`
- Modify: `tests/test_service_parity.py`
- Modify: `tests/test_ui_open.py`

**Interfaces:**
- Consumes: existing `synthetic_save` fixture, `save_format.inspect_save`, `editor.prepare.prepare_edit`.
- Produces: executable expectations for `editor.formats.formats`, `by_id`, `detect`, `EditorService.inspect_result`, and snapshot format metadata.

- [ ] **Step 1: Write the failing registry tests**

```python
def test_registry_starts_with_only_stalker2(synthetic_save: bytes) -> None:
    from editor.formats import by_id, detect, formats

    registered = formats()
    assert [item.id for item in registered] == ["stalker2"]
    assert by_id("stalker2") is registered[0]
    assert detect(synthetic_save) is registered[0]


def test_registry_returns_none_for_unknown_bytes() -> None:
    from editor.formats import detect

    assert detect(b"not a save") is None


def test_service_inspection_preserves_parser_result_and_format_metadata(
    synthetic_save: bytes,
) -> None:
    import save_format as sf
    from editor.service import EditorService

    result = EditorService().inspect_result(synthetic_save)
    assert result.format_id == "stalker2"
    assert result.info == sf.inspect_save(synthetic_save)
```

- [ ] **Step 2: Add service parity and worker snapshot assertions**

Extend the existing `test_service_inspect_and_dependencies_are_injectable` with
an equality assertion against `sf.inspect_save(synthetic_save)`. In
`test_local_open_is_async_and_populates_summary`, assert:

```python
assert window.snapshot.format_id == "stalker2"
assert window.snapshot.format_title == "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
```

- [ ] **Step 3: Run the focused tests and verify they fail for the intended reason**

Run: `PYTHON=.venv/bin/python .venv/bin/pytest tests/test_formats.py tests/test_service_parity.py tests/test_ui_open.py -q`

Expected: FAIL because `editor.formats` and `EditorService.inspect_result` do
not exist and snapshots do not yet expose format metadata. Existing tests may
also show the exact integration points that need updating.

### Task 2: Implement the static registry and route the service through it

**Files:**
- Create: `editor/formats.py`
- Modify: `editor/service.py`
- Modify: `ui/main_window.py`
- Modify: `ui/cloud_view.py`
- Modify: `tests/test_service_parity.py`

**Interfaces:**
- Consumes: `save_format.SaveInfo`, `save_format.SaveError`, `editor.models.EditPlan`, `editor.models.PreparedEdit`, `editor.prepare.prepare_edit`.
- Produces: `SaveFormat`, `FormatInspection`, `register`, `formats`, `by_id`, `detect`, `EditorService.inspect_result`, and format-aware local/cloud snapshots.

- [ ] **Step 1: Implement `editor/formats.py`**

Define the Protocol and immutable inspection result. Implement the S2 adapter
with `id = "stalker2"`, title
`"S.T.A.L.K.E.R. 2: Heart of Chornobyl"`, direct delegation for `inspect` and
`prepare`, and a `detect` method equivalent to:

```python
def detect(self, data: bytes) -> bool:
    try:
        return inspect_save(data, with_inventory=False).money_anchor_count == 1
    except Exception:
        return False
```

Keep registry storage private, reject duplicate IDs in `register`, return a
tuple from `formats`, raise `KeyError` from `by_id` when absent, and return
`None` from registry `detect` when no adapter accepts the bytes. Register only
the S2 adapter at module import.

- [ ] **Step 2: Route default service calls through the registry**

Keep optional injected callbacks. When no callback is supplied, resolve the
format from bytes, call the selected adapter, and raise `SaveError` if no
format is known. Implement `inspect_result` once and make `inspect` return its
`.info`; make `prepare` call the selected adapter's `prepare`.

- [ ] **Step 3: Carry metadata through workers and snapshots**

Add defaulted `format_id` and `format_title` fields to `LocalSnapshot` and
`CloudSnapshot` so existing direct test constructors remain valid. Make local
and cloud workers use `inspect_result` once, then pass its metadata into their
snapshots. Preserve the existing S2 badge text and add the format ID to the
snapshot-backed source/metadata presentation without introducing demo values.

- [ ] **Step 4: Run focused tests and type/lint checks**

Run: `PYTHON=.venv/bin/python .venv/bin/pytest tests/test_formats.py tests/test_service_parity.py tests/test_ui_open.py tests/test_ui_cloud.py -q`

Run: `PYTHON=.venv/bin/python -m ruff check editor/formats.py editor/service.py ui/main_window.py ui/cloud_view.py tests/test_formats.py tests/test_service_parity.py tests/test_ui_open.py`

Expected: all focused tests pass and Ruff exits 0.

### Task 3: Verify the full M01 gate and record evidence

**Files:**
- Modify: `docs/tasks/M01.md`
- Modify: `docs/STATUS.md`

**Interfaces:**
- Consumes: completed registry implementation and focused regression tests.
- Produces: card-level evidence without claiming unsupported games or platform/runtime coverage.

- [ ] **Step 1: Run the complete required checks**

Run: `PYTHON=.venv/bin/python make check`

Expected: exit 0, including Ruff, mypy, generated-file checks, and compile.

Run: `PYTHON=.venv/bin/python make test`

Expected: exit 0 with the full suite passing and no new skips caused by M01.

- [ ] **Step 2: Update only the current card and current status**

In `docs/tasks/M01.md`, record the actual commit, test commands, exit codes,
and the fact that only `stalker2` is registered. In `docs/STATUS.md`, add a
short current-state entry only for the registry capability; do not claim M02 or
any X-Ray support.

- [ ] **Step 3: Review the final diff and commit the M01 result**

Run: `git diff --check`

Run: `git status --short`

Expected: only the planned registry, service/snapshot, tests, and M01/status
documentation changes are present; `.venv/` and personal files remain ignored.

```bash
git add editor/formats.py editor/service.py ui/main_window.py ui/cloud_view.py \
  tests/test_formats.py tests/test_service_parity.py tests/test_ui_open.py \
  docs/tasks/M01.md docs/STATUS.md
git commit -m "feat: add save format registry"
```

