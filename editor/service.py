"""UI-free orchestration shared by the Tk application, CLI and future Qt UI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from save_format import SaveInfo

from .formats import FormatInspection, SaveFormat, detect_or_raise
from .models import CloudReceipt, EditPlan, PreparedEdit
from .storage import (
    BackupRecord,
    ExportReceipt,
    RestoreReceipt,
)
from .storage import (
    export_local as storage_export_local,
)
from .storage import (
    restore_backup as storage_restore_backup,
)
from .transactions import CloudTransport
from .transactions import upload_cloud as transactions_upload_cloud

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
        self._inspect_fn = inspect_fn
        self._prepare_fn = prepare_fn
        self._export_fn = export_fn or storage_export_local
        self._upload_fn = upload_fn or transactions_upload_cloud
        self._restore_fn = restore_fn or storage_restore_backup

    @staticmethod
    def _format_for(
        data: bytes, *, source_name: str | None = None
    ) -> SaveFormat:
        return detect_or_raise(data, display_name=source_name)

    def inspect_result(
        self,
        data: bytes,
        *,
        with_inventory: bool = True,
        source_name: str | None = None,
    ) -> FormatInspection:
        """Return parser data together with the selected format metadata."""

        format_ = self._format_for(data, source_name=source_name)
        inspector = self._inspect_fn or format_.inspect
        info = inspector(data, with_inventory=with_inventory)
        return FormatInspection(
            format_id=format_.id,
            format_title=format_.title,
            info=info,
            release_id=format_.release_id,
            edition=format_.edition,
            capabilities=format_.capabilities,
        )

    def inspect(
        self,
        data: bytes,
        *,
        with_inventory: bool = True,
        source_name: str | None = None,
    ) -> SaveInfo:
        """Return the read-only save snapshot used by every front end."""

        if self._inspect_fn is not None:
            return self._inspect_fn(data, with_inventory=with_inventory)
        return self.inspect_result(
            data,
            with_inventory=with_inventory,
            source_name=source_name,
        ).info

    def prepare(
        self,
        data: bytes,
        plan: EditPlan,
        *,
        source_name: str | None = None,
    ) -> PreparedEdit:
        """Prepare and verify one immutable edit plan."""

        if self._prepare_fn is not None:
            return self._prepare_fn(data, plan)
        format_ = self._format_for(data, source_name=source_name)
        return format_.prepare(data, plan)

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
