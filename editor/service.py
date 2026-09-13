"""UI-free orchestration shared by the Tk application, CLI and future Qt UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from save_format import SaveInfo, inspect_save

from .models import CloudReceipt, EditPlan, PreparedEdit
from .prepare import prepare_edit
from .storage import (
    BackupRecord,
    ExportReceipt,
    RestoreReceipt,
    restore_backup as storage_restore_backup,
    export_local as storage_export_local,
)
from .transactions import CloudTransport, upload_cloud as transactions_upload_cloud


InspectFn = Callable[..., SaveInfo]
PrepareFn = Callable[[bytes, EditPlan], PreparedEdit]
ExportFn = Callable[[Path, Path, PreparedEdit, Path], ExportReceipt]
UploadFn = Callable[..., CloudReceipt]
RestoreFn = Callable[[Path | BackupRecord, Path], RestoreReceipt]


class EditorService:
    """Coordinate the parser, immutable edit preparation and safe writers.

    The default functions are the production implementations.  Each boundary
    is injectable so UI and CLI tests can use synthetic bytes and fake cloud
    transports without importing a desktop toolkit or starting Steam.
    """

    def __init__(
        self,
        *,
        inspect_fn: InspectFn | None = None,
        prepare_fn: PrepareFn | None = None,
        export_fn: ExportFn | None = None,
        upload_fn: UploadFn | None = None,
        restore_fn: RestoreFn | None = None,
    ) -> None:
        self._inspect_fn = inspect_fn or inspect_save
        self._prepare_fn = prepare_fn or prepare_edit
        self._export_fn = export_fn or storage_export_local
        self._upload_fn = upload_fn or transactions_upload_cloud
        self._restore_fn = restore_fn or storage_restore_backup

    def inspect(self, data: bytes, *, with_inventory: bool = True) -> SaveInfo:
        """Return the read-only save snapshot used by every front end."""

        return self._inspect_fn(data, with_inventory=with_inventory)

    def prepare(self, data: bytes, plan: EditPlan) -> PreparedEdit:
        """Prepare and verify one immutable edit plan."""

        return self._prepare_fn(data, plan)

    def export_local(
        self,
        source_path: Path,
        output_path: Path,
        prepared: PreparedEdit,
        backup_dir: Path,
    ) -> ExportReceipt:
        """Export a prepared edit through the shared atomic local writer."""

        return self._export_fn(source_path, output_path, prepared, backup_dir)

    def upload_cloud(
        self,
        worker: CloudTransport,
        prepared: PreparedEdit,
        backup_dir: Path,
        *,
        persisted_timeout: int = 120,
        on_stage: Callable[[str], None] | None = None,
    ) -> CloudReceipt:
        """Upload through the shared fail-closed cloud transaction."""

        return self._upload_fn(
            worker,
            prepared,
            backup_dir,
            persisted_timeout=persisted_timeout,
            on_stage=on_stage,
        )

    def restore_local(
        self,
        journal_or_record: Path | BackupRecord,
        output_path: Path,
    ) -> RestoreReceipt:
        """Restore a verified local backup through the shared storage boundary."""

        return self._restore_fn(journal_or_record, output_path)


__all__ = ["EditorService"]
