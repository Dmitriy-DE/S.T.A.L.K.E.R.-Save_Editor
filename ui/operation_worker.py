"""Background preview and local-save workers for the Qt shell."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from editor.catalog import GameCatalog, ItemCatalog
from editor.formats import FormatDetectionError
from editor.models import EditPlan, PreparedEdit
from editor.service import EditorService


class OperationWorker(QThread):
    """Run one immutable preview or export request away from the UI thread."""

    preview_ready = Signal(object)
    apply_ready = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        service: EditorService,
        *,
        mode: str,
        data: bytes,
        plan: EditPlan,
        source_path: Path | None = None,
        output_path: Path | None = None,
        backup_dir: Path | None = None,
        catalog: ItemCatalog | None = None,
        game_catalog: GameCatalog | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.mode = mode
        self.data = bytes(data)
        self.plan = plan
        self.source_path = source_path
        self.output_path = output_path
        self.backup_dir = backup_dir
        self.catalog = catalog
        self.game_catalog = game_catalog

    def run(self) -> None:
        try:
            if self.mode == "preview":
                self.progress.emit("Подготовка preview: проверка SHA и round-trip…")
                prepared = self.service.prepare(
                    self.data,
                    self.plan,
                    source_name=self.plan.source.locator,
                    catalog=self.catalog,
                    game_catalog=self.game_catalog,
                )
                if not isinstance(prepared, PreparedEdit):
                    raise TypeError("EditorService.prepare вернул не PreparedEdit")
                self.preview_ready.emit(prepared)
                return
            if self.mode == "apply":
                if self.source_path is None or self.output_path is None or self.backup_dir is None:
                    raise ValueError("Для apply нужны source, output и backup paths")
                self.progress.emit("Создание backup, запись и read-back SHA…")
                receipt = self.service.export_local(
                    self.source_path,
                    self.output_path,
                    self.plan_prepared,
                    self.backup_dir,
                )
                self.apply_ready.emit(receipt)
                return
            if self.mode == "replace":
                if self.source_path is None or self.backup_dir is None:
                    raise ValueError("Для replace нужны source и backup paths")
                self.progress.emit("Создание backup, атомарная замена и read-back SHA…")
                receipt = self.service.replace_local(
                    self.source_path,
                    self.plan_prepared,
                    self.backup_dir,
                )
                self.apply_ready.emit(receipt)
                return
            raise ValueError(f"Неизвестный режим операции: {self.mode}")
        except FormatDetectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    @property
    def plan_prepared(self) -> PreparedEdit:
        # MainWindow assigns the immutable prepared value before starting an
        # apply worker.  Keeping it separate from mutable widgets is the core
        # stale-preview invariant.
        prepared = getattr(self, "_prepared", None)
        if not isinstance(prepared, PreparedEdit):
            raise ValueError("Для apply отсутствует PreparedEdit")
        return prepared

    def set_prepared(self, prepared: PreparedEdit) -> None:
        self._prepared = prepared


__all__ = ["OperationWorker"]
