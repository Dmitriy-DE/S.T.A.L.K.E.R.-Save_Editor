"""Qt Steam Cloud source selection and fail-closed upload states."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from editor.capabilities import FormatCapabilities
from editor.catalog import GameCatalog, ItemCatalog
from editor.cloud_capabilities import CloudWriteCapability, cloud_write_capability
from editor.formats import STALKER2_FORMAT, FormatDetectionError
from editor.models import CloudReceipt, PreparedEdit
from editor.platforms import backup_dirs
from editor.service import EditorService
from editor.steam_backend import make_cloud_worker
from editor.steam_cdp import restart_steam_with_debugging
from editor.steam_profiles import (
    SteamCloudProfile,
    is_editor_cloud_artifact,
    steam_cloud_profile_for_app_id,
    steam_cloud_profile_for_release,
    steam_cloud_profiles,
)
from editor.transactions import CloudTransport
from save_format import SaveError, SaveInfo
from steam_cloud import APP_ID, CloudFile, discover_helper

LOGGER = logging.getLogger("stalker2_save_editor.cloud")


class CloudSession(CloudTransport, Protocol):
    """A transport this view also owns the lifecycle of.

    ``editor.transactions.CloudTransport`` only describes what an upload needs.
    The Cloud tab additionally starts, connects and closes the helper process,
    so the widget-level contract is stated here instead of being assumed.
    """

    @property
    def write_capability(self) -> CloudWriteCapability: ...

    def start(self) -> None: ...

    def connect(self, app_id: int) -> None: ...

    def close(self) -> None: ...

    def list_files(self) -> list[CloudFile]: ...

    def read_cloud_file(self, cloud_file: CloudFile) -> bytes: ...


WorkerFactory = Callable[[Path | None], CloudSession]
HelperFinder = Callable[[], Path | None]


@dataclass(frozen=True)
class CloudSnapshot:
    """Immutable remote bytes and inspection result for the selected Data save."""

    name: str
    data: bytes
    info: SaveInfo
    file: CloudFile
    format_id: str = "stalker2"
    format_title: str = "S.T.A.L.K.E.R. 2: Heart of Chornobyl"
    release_id: str = "stalker2"
    edition: str = "s2"
    capabilities: FormatCapabilities = field(
        default_factory=lambda: STALKER2_FORMAT.capabilities
    )
    catalog: ItemCatalog | None = None
    game_catalog: GameCatalog | None = None


class CloudOperationWorker(QThread):
    """Run helper lifecycle, remote reads, and upload transactions off the UI thread."""

    completed = Signal(object)
    transport_ready = Signal(object)
    failed = Signal(str)
    progress = Signal(str)

    def __init__(
        self,
        service: EditorService,
        *,
        mode: str,
        helper_path: Path | None = None,
        transport: CloudSession | None = None,
        worker_factory: WorkerFactory = make_cloud_worker,
        cloud_file: CloudFile | None = None,
        prepared: PreparedEdit | None = None,
        backup_dir: Path | None = None,
        app_id: int = APP_ID,
        profile: SteamCloudProfile | None = None,
        release_id: str | None = None,
        catalog_roots: tuple[Path, ...] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.mode = mode
        self.helper_path = helper_path
        self.transport = transport
        self.worker_factory = worker_factory
        self.cloud_file = cloud_file
        self.prepared = prepared
        self.backup_dir = backup_dir
        if profile is not None:
            self.profile = profile
        elif release_id is not None:
            self.profile = steam_cloud_profile_for_release(release_id)
        else:
            self.profile = steam_cloud_profile_for_app_id(app_id)
        self.app_id = self.profile.app_id
        self.catalog_roots = tuple(catalog_roots)

    def run(self) -> None:
        created_transport = False
        transport = self.transport
        prepared_source = self.prepared.plan.source if self.prepared is not None else None
        operation_path = (
            self.cloud_file.name
            if self.cloud_file is not None
            else prepared_source.locator
            if prepared_source is not None
            else "-"
        )
        operation_source = (
            self.cloud_file.source
            if self.cloud_file is not None
            else prepared_source.kind
            if prepared_source is not None
            else "-"
        )
        expected_bytes = len(self.prepared.data) if self.prepared is not None else None
        LOGGER.info(
            "cloud operation start mode=%s app_id=%s path=%s source=%s expected_bytes=%s",
            self.mode,
            self.app_id,
            operation_path,
            operation_source,
            expected_bytes if expected_bytes is not None else "-",
        )
        try:
            if self.mode == "list":
                # A helper is optional: the native worker needs no AppImage.
                # The factory tries native first and only needs the helper path
                # for its fallback, so pass it through even when absent.
                self.progress.emit("Steam Cloud: подключение…")
                transport = self.worker_factory(self.helper_path)
                self.transport = transport
                created_transport = True
                if self.isInterruptionRequested():
                    raise SaveError("Steam Cloud operation отменена")
                setter = getattr(transport, "set_file_filter", None)
                if callable(setter):
                    setter(self.profile.accepts)
                transport.start()
                transport.connect(self.app_id)
                files = transport.list_files()
                self.transport_ready.emit(transport)
                self.completed.emit(files)
                LOGGER.info("cloud operation complete mode=list files=%s", len(files))
                return

            if transport is None:
                raise SaveError("Steam Cloud не подключён; сначала нажми «Подключить и обновить»")

            if self.mode == "analyze":
                cloud_file = self.cloud_file
                if cloud_file is None:
                    raise SaveError("Cloud save не выбран")
                self.progress.emit(f"Cloud: скачивание {cloud_file.name}…")
                reader = getattr(transport, "read_cloud_file", None)
                if callable(reader):
                    data = bytes(reader(cloud_file))
                else:
                    data = bytes(transport.read_file(cloud_file.name))
                if self.catalog_roots:
                    result = self.service.inspect_result(
                        data,
                        with_inventory=True,
                        source_name=cloud_file.name,
                        catalog_roots=self.catalog_roots,
                    )
                else:
                    result = self.service.inspect_result(
                        data,
                        with_inventory=True,
                        source_name=cloud_file.name,
                    )
                if result.release_id != self.profile.release_id:
                    raise SaveError(
                        f"Cloud save распознан как {result.release_id!r}, "
                        f"а выбран профиль {self.profile.release_id!r}"
                    )
                self.completed.emit(
                    CloudSnapshot(
                        cloud_file.name,
                        data,
                        result.info,
                        cloud_file,
                        result.format_id,
                        result.format_title,
                        result.release_id,
                        result.edition,
                        result.capabilities,
                        result.catalog,
                        result.game_catalog,
                    )
                )
                LOGGER.info("cloud operation complete mode=analyze bytes=%s", len(data))
                return

            if self.mode == "upload":
                if self.prepared is None or self.backup_dir is None:
                    raise SaveError("Для cloud upload нужна проверенная копия")
                prepared = self.prepared
                self.progress.emit("Cloud: fresh read и SHA…")

                def report_stage(stage: str) -> None:
                    LOGGER.info(
                        "cloud upload stage path=%s stage=%s expected_bytes=%s",
                        prepared.plan.source.locator,
                        stage,
                        len(prepared.data),
                    )
                    self.progress.emit(stage)

                receipt = self.service.upload_cloud(
                    transport,
                    prepared,
                    self.backup_dir,
                    persisted_timeout=180,
                    on_stage=report_stage,
                )
                self.completed.emit(receipt)
                LOGGER.info(
                    "cloud operation complete mode=upload status=%s path=%s expected_bytes=%s "
                    "sha256=%s reason=%s backup=%s recovery=%s",
                    receipt.status,
                    receipt.remote_path,
                    len(prepared.data),
                    receipt.output_sha256,
                    receipt.reason or "-",
                    receipt.backup_path,
                    receipt.recovery_path,
                )
                return

            raise SaveError(f"Неизвестный cloud operation: {self.mode}")
        except FormatDetectionError as exc:
            LOGGER.exception("cloud operation failed mode=%s path=%s", self.mode, operation_path)
            self.failed.emit(self._diagnostic_message(exc))
        except Exception as exc:
            if created_transport and transport is not None:
                try:
                    transport.close()
                except Exception:
                    pass
            LOGGER.exception("cloud operation failed mode=%s path=%s", self.mode, operation_path)
            self.failed.emit(self._diagnostic_message(exc))

    def _diagnostic_message(self, exc: BaseException) -> str:
        """Keep backend, selected app and remote path visible in failures."""

        context = f"{self.profile.title} (app_id={self.app_id})"
        if self.cloud_file is not None:
            context += f" · path={self.cloud_file.name}"
        return f"{context}: {type(exc).__name__}: {exc}"

    def cancel(self) -> None:
        """Request cancellation and kill an active native child if present."""

        self.requestInterruption()
        transport = self.transport
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass


class SteamWebEnableWorker(QThread):
    """Restart Steam with its local CEF debug channel on explicit user action."""

    completed = Signal()
    failed = Signal(str)

    def run(self) -> None:
        try:
            restart_steam_with_debugging()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.completed.emit()


class CloudController(QObject):
    """Own Steam Cloud lifecycle and fail-closed transactions without UI."""

    files_ready = Signal(object)
    snapshot_ready = Signal(object)
    reconciliation_ready = Signal(object)
    reconciliation_failed = Signal(str)
    upload_ready = Signal(object)
    operation_failed = Signal(str)
    operation_progress = Signal(str)
    busy_changed = Signal(bool)
    status_changed = Signal(str)
    result_changed = Signal(str)
    error_changed = Signal(str)
    upload_available_changed = Signal(bool)

    PATH_COLUMN = 0
    SIZE_COLUMN = 1
    TIMESTAMP_COLUMN = 2
    PERSISTED_COLUMN = 3
    SOURCE_COLUMN = 4

    def __init__(
        self,
        service: EditorService,
        *,
        worker_factory: WorkerFactory = make_cloud_worker,
        helper_finder: HelperFinder = discover_helper,
        helper_path: Path | None = None,
        backup_dir: Path | None = None,
        app_id: int = APP_ID,
        catalog_roots: tuple[Path, ...] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.worker_factory = worker_factory
        self.helper_finder = helper_finder
        self.helper_path = (
            Path(helper_path).expanduser()
            if helper_path is not None
            else self.helper_finder()
        )
        if self.helper_path is not None:
            self.helper_path = self.helper_path.expanduser()
        self.backup_dir = (
            Path(backup_dir).expanduser()
            if backup_dir is not None
            else backup_dirs()[0]
        )
        self.profile = steam_cloud_profile_for_app_id(app_id)
        self.app_id = self.profile.app_id
        self.catalog_roots = tuple(catalog_roots)
        self.transport: CloudSession | None = None
        self._files: tuple[CloudFile, ...] = ()
        self._hidden_editor_artifacts = 0
        self._snapshot: CloudSnapshot | None = None
        self._prepared: PreparedEdit | None = None
        self._thread: CloudOperationWorker | None = None
        self._debug_thread: SteamWebEnableWorker | None = None
        self._debug_succeeded = False
        self._selected_file: CloudFile | None = None
        self._external_busy = False
        self._reconciliation_receipt: CloudReceipt | None = None
        self._reconciliation_target: str | None = None
        self._reconciliation_status = "idle"
        self._reconcile_after_finish = False
        self._reconcile_analyze_after_finish = False
        self.status_text = "Steam Cloud: не подключено"
        self.result_text = ""
        self.error_text = ""

    @property
    def files(self) -> tuple[CloudFile, ...]:
        return self._files

    @property
    def snapshot(self) -> CloudSnapshot | None:
        return self._snapshot

    @property
    def is_busy(self) -> bool:
        return bool(
            (self._thread is not None and self._thread.isRunning())
            or (self._debug_thread is not None and self._debug_thread.isRunning())
        )

    @property
    def profiles(self) -> tuple[SteamCloudProfile, ...]:
        return tuple(steam_cloud_profiles())

    @property
    def reconciliation_status(self) -> str:
        return self._reconciliation_status

    @property
    def reconciliation_pending(self) -> bool:
        return self._reconciliation_receipt is not None

    def _set_status(self, text: str) -> None:
        self.status_text = text
        self.status_changed.emit(text)

    def _set_result(self, text: str) -> None:
        self.result_text = text
        self.result_changed.emit(text)

    def _set_error(self, text: str) -> None:
        self.error_text = text
        self.error_changed.emit(text)

    def _resolve_helper(self) -> Path | None:
        # The native worker needs no helper; the discovered AppImage is only a
        # fallback. Resolve it silently, never surfacing a path to the user.
        found = self.helper_finder()
        if found is not None:
            self.helper_path = Path(found).expanduser()
        return self.helper_path

    def _refuse_while_busy(self) -> bool:
        """Report a declined action instead of returning silently.

        The buttons are disabled while an operation runs, so this path is
        reached by keyboard and by automation - where a control that does
        nothing and says nothing looks exactly like a broken one.
        """

        if not self.is_busy:
            return False
        self._set_status("Steam Cloud: дождись завершения текущей операции")
        return True

    def _start_worker(self, worker: CloudOperationWorker) -> None:
        if self.is_busy:
            return
        self._thread = worker
        self._thread.transport_ready.connect(self._on_transport_ready)
        self._thread.progress.connect(self._on_progress)
        self._thread.failed.connect(self._on_failed)
        self._thread.finished.connect(self._on_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self.set_busy(True)
        worker.start()

    def start_connect(self) -> None:
        if self._refuse_while_busy():
            return
        # A helper is optional — the native worker connects without one. Pass
        # whatever discovery found (possibly None) so the factory can use it
        # only if it needs the fallback.
        helper = self._resolve_helper()
        self._close_transport()
        self.clear_error()
        self._set_status("Steam Cloud: подключение…")
        worker = CloudOperationWorker(
            self.service,
            mode="list",
            helper_path=helper,
            worker_factory=self.worker_factory,
            app_id=self.app_id,
            profile=self.profile,
            catalog_roots=self.catalog_roots,
            parent=self,
        )
        worker.completed.connect(self._on_files_ready)
        self._start_worker(worker)
        # Watchdog: if the connect is still running after a while, tell the user
        # what to check instead of leaving a silent "подключение…" forever.
        self._connect_deadline = time.monotonic()
        QTimer.singleShot(30_000, self._warn_if_still_connecting)

    def start_steam_web(self) -> None:
        if self.is_busy:
            self._set_status("Steam Cloud: дождись завершения текущей операции")
            return
        self._debug_succeeded = False
        self._set_status(
            "Steam Cloud web: закрываю Steam и запускаю его с debug-портом…"
        )
        worker = SteamWebEnableWorker(self)
        worker.completed.connect(self._on_steam_web_ready)
        worker.failed.connect(self._on_steam_web_failed)
        worker.finished.connect(self._on_steam_web_finished)
        worker.finished.connect(worker.deleteLater)
        self._debug_thread = worker
        worker.start()

    def reconcile_remote(self) -> None:
        """Refresh/list and, when possible, read back the remote target once.

        This method never starts another write. It is safe for both verified and
        uncertain receipts and is the only recovery action exposed after an
        ambiguous cloud result.
        """

        if self._reconciliation_receipt is None:
            self._set_status("Steam Cloud: нет незавершённой reconciliation")
            return
        self._reconcile_after_finish = True
        self._reconciliation_status = "refreshing"
        if not self.is_busy:
            self._reconcile_after_finish = False
            self.start_connect()

    def _on_steam_web_ready(self) -> None:
        self._debug_succeeded = True

    def _on_steam_web_failed(self, message: str) -> None:
        self._debug_succeeded = False
        self._set_error(message)

    def _on_steam_web_finished(self) -> None:
        succeeded = self._debug_succeeded
        self._debug_thread = None
        if succeeded:
            self._set_status("Steam Cloud web включён; обновляю список…")
            QTimer.singleShot(0, self.start_connect)
        elif not self.error_text:
            self._set_status("Steam Cloud web не включён")

    def _warn_if_still_connecting(self) -> None:
        if self.is_busy and self.transport is None:
            self._set_status(
                "Steam Cloud: всё ещё подключаюсь… Проверь, что клиент Steam "
                "запущен и вошёл в аккаунт. Список появится, как только Steam "
                "ответит; можно закрыть вкладку и вернуться позже."
            )

    def selected_file(self) -> CloudFile | None:
        return self._selected_file

    def select_file(self, cloud_file: CloudFile | None) -> None:
        """Set the selected Data path after the presentation validates its row."""

        self._selected_file = cloud_file if cloud_file in self._files else None
        self._on_selection_changed(preserve_prepared=self._reconciliation_receipt is not None)

    def set_review_files(
        self,
        files: tuple[CloudFile, ...] | list[CloudFile],
        *,
        status: str = "Steam Cloud: демосписок · 4 файла",
    ) -> None:
        """Publish deterministic read-only rows for the visual-review harness.

        The method never starts a transport, reads a remote slot, or enables a
        write.  It exists so review rendering can exercise the same table and
        selection path without masquerading as live Steam state.
        """

        if self.is_busy:
            raise RuntimeError("нельзя заменить cloud review fixture во время операции")
        self._files = tuple(files)
        self._selected_file = self._files[0] if self._files else None
        self._snapshot = None
        self._prepared = None
        self._set_status(status)
        self._set_result("Демо-данные списка; запись в Cloud не выполнялась")
        self._on_selection_changed()
        self.files_ready.emit(self._files)

    def analyze_selected(self) -> None:
        if self._refuse_while_busy():
            return
        cloud_file = self.selected_file()
        if cloud_file is None:
            self._on_failed(
                f"Сначала выбери сохранение из профиля {self.profile.title}"
            )
            return
        if self.transport is None:
            self._on_failed("Steam Cloud не подключён; запись не выполнялась")
            return
        self.clear_error()
        worker = CloudOperationWorker(
            self.service,
            mode="analyze",
            transport=self.transport,
            cloud_file=cloud_file,
            worker_factory=self.worker_factory,
            profile=self.profile,
            catalog_roots=self.catalog_roots,
            parent=self,
        )
        worker.completed.connect(self._on_snapshot_ready)
        self._start_worker(worker)

    def set_prepared(self, prepared: PreparedEdit | None) -> None:
        self._prepared = None
        if prepared is None:
            self._set_result("")
            self.upload_available_changed.emit(False)
            return
        selected = self.selected_file()
        source = prepared.plan.source
        if source.kind != "cloud" or selected is None or source.locator != selected.name:
            self._set_result("Проверка не относится к выбранному cloud Data path; upload запрещён")
            self.upload_available_changed.emit(False)
            return
        self._prepared = prepared
        self._set_result(
            f"Проверка Cloud готова для {selected.name}; SHA {prepared.output_sha256[:12]}…"
        )
        self._refresh_upload_state()

    def set_catalog_roots(self, roots: tuple[Path, ...]) -> None:
        """Use the selected S2 Zone Kit/Workshop tree on the next analysis."""

        self.catalog_roots = tuple(Path(root).expanduser() for root in roots)

    def _refresh_upload_state(self, *, blocked: bool = False) -> CloudWriteCapability:
        capability = cloud_write_capability(self.transport)
        can_upload = (
            not blocked
            and not self.is_busy
            and self._prepared is not None
            and self._reconciliation_receipt is None
            and capability.writable
        )
        self.upload_available_changed.emit(can_upload)
        if self._prepared is not None and not capability.writable:
            self._set_result(
                "Проверка Cloud готова, но upload отключён: "
                f"{capability.reason}. WriteFile не запускался."
            )
        return capability

    def start_upload(self) -> None:
        if self._refuse_while_busy():
            return
        if self._reconciliation_receipt is not None:
            self._on_failed(
                "Cloud upload заблокирован до reconciliation; повторный WriteFile не выполнялся"
            )
            return
        selected = self.selected_file()
        prepared = self._prepared
        if self.transport is None:
            self._on_failed("Steam Cloud не подключён; upload не выполнялся")
            return
        capability = cloud_write_capability(self.transport)
        if not capability.writable:
            self._on_failed(
                f"Upload недоступен: {capability.reason}; WriteFile не запускался"
            )
            self._refresh_upload_state()
            return
        if prepared is None or selected is None:
            self._on_failed("Сначала выбери cloud slot и выполни проверку")
            return
        if prepared.plan.source.kind != "cloud" or prepared.plan.source.locator != selected.name:
            self._on_failed("Выбранный cloud slot не совпадает с проверкой; WriteFile не выполнялся")
            return
        self.clear_error()
        worker = CloudOperationWorker(
            self.service,
            mode="upload",
            transport=self.transport,
            prepared=prepared,
            backup_dir=self.backup_dir,
            worker_factory=self.worker_factory,
            profile=self.profile,
            catalog_roots=self.catalog_roots,
            parent=self,
        )
        worker.completed.connect(self._on_upload_ready)
        self._start_worker(worker)

    def _on_transport_ready(self, transport: CloudSession) -> None:
        self.transport = transport

    def _on_files_ready(self, files) -> None:
        reconciling = self._reconciliation_receipt is not None
        accepted: list[CloudFile] = []
        hidden_editor_artifacts = 0
        for cloud_file in files:
            if not isinstance(cloud_file, CloudFile):
                continue
            if not self.profile.accepts(cloud_file.name):
                if is_editor_cloud_artifact(cloud_file.name):
                    hidden_editor_artifacts += 1
                continue
            accepted.append(cloud_file)
        self._files = tuple(accepted)
        self._hidden_editor_artifacts = hidden_editor_artifacts
        self._snapshot = None
        # Keep the committed edit in memory while a Cloud receipt is being
        # reconciled.  It remains blocked by ``_reconciliation_receipt`` and
        # can never trigger an automatic retry; it is cleared only after the
        # remote SHA has been read back and verified.
        if not reconciling:
            self._prepared = None
        self._selected_file = None
        self._on_selection_changed(preserve_prepared=reconciling)
        hint = str(getattr(self.transport, "status_hint", "") or "").strip()
        status_prefix = (
            "Steam Cloud: найдено в Steam cache"
            if "Steam cache" in hint
            else "Steam Cloud: подключено"
        )
        if self._files:
            status = f"{status_prefix} · {len(self._files)} · {self.profile.save_label}"
        else:
            status = f"{status_prefix} · 0 · {self.profile.save_label} (список пуст)"
        if hint:
            status += f" · {hint}"
        if hidden_editor_artifacts:
            status += (
                f" · скрыто {hidden_editor_artifacts} старых editor-файлов "
                "(-edited.sav)"
            )
        capability = cloud_write_capability(self.transport)
        if not capability.writable:
            status += f" · только чтение: {capability.reason}"
        self._set_status(status)
        reconciliation_target = self._reconciliation_target
        reconciliation_selected = (
            next(
                (item for item in self._files if item.name == reconciliation_target),
                None,
            )
            if reconciling
            else None
        )
        # Publish the target before the presentation rebuilds its table.  That
        # lets the view preserve the selected row while the read-back worker is
        # being scheduled, instead of clearing it and racing into a stale
        # "select a slot" error during the busy-state transition.
        if reconciliation_selected is not None:
            self._selected_file = reconciliation_selected
        self.files_ready.emit(self._files)
        if self._reconciliation_receipt is not None:
            if reconciliation_selected is None:
                message = (
                    f"Cloud reconciliation не нашла удалённый слот: "
                    f"{reconciliation_target or '—'}"
                )
                self._reconciliation_status = "uncertain"
                self._set_error(message)
                self.reconciliation_failed.emit(message)
                return
            self._set_status("Cloud: список обновлён; проверяю удалённые bytes…")
            # The list worker is still busy while this callback runs.  Defer
            # the read-back until its finished signal, otherwise the busy guard
            # reports a misleading missing-selection error.
            self._reconcile_analyze_after_finish = True

    def select_profile(self, release_id: str) -> None:
        try:
            profile = steam_cloud_profile_for_release(str(release_id))
        except KeyError:
            return
        if profile.release_id == self.profile.release_id:
            return
        if self.is_busy:
            return
        self._close_transport()
        self.profile = profile
        self.app_id = profile.app_id
        self._files = ()
        self._snapshot = None
        self._prepared = None
        self._selected_file = None
        self._on_selection_changed()
        self.clear_error()
        self._set_status(
            f"Steam Cloud: выбран профиль {profile.title}; нажми «Обновить список»"
        )

    def _on_snapshot_ready(self, snapshot: CloudSnapshot) -> None:
        self._snapshot = snapshot
        if self._reconciliation_receipt is not None:
            receipt = self._reconciliation_receipt
            if snapshot.info.sha256 == receipt.output_sha256:
                self._reconciliation_receipt = None
                self._reconciliation_target = None
                self._reconciliation_status = "verified"
                self._prepared = None
                self._set_result(
                    f"Cloud reconciliation verified / подтверждена: {snapshot.name}; SHA совпал."
                )
                self._set_status("Cloud: reconciliation verified")
                self.reconciliation_ready.emit(snapshot)
            else:
                message = (
                    f"Cloud reconciliation не подтверждена: SHA remote {snapshot.info.sha256[:12]}… "
                    f"не совпал с receipt {receipt.output_sha256[:12]}…."
                )
                self._reconciliation_status = "uncertain"
                self._set_error(message)
                self.reconciliation_failed.emit(message)
            return
        self._prepared = None
        self._set_result(
            f"Cloud snapshot: {snapshot.name}; CRC={'OK' if snapshot.info.crc_ok else 'FAIL'}; "
            f"SHA256 {snapshot.info.sha256}"
        )
        self._set_status("Cloud save скачан и проанализирован; изменения ещё не подготовлены")
        self.snapshot_ready.emit(snapshot)

    def _on_upload_ready(self, receipt: CloudReceipt) -> None:
        prepared = self._prepared
        output_size = len(prepared.data) if prepared is not None else None
        # Do not discard the committed draft yet. A verified receipt still
        # requires remote reconciliation, while an uncertain receipt must keep
        # the state available for explicit reconciliation without permitting a
        # second WriteFile attempt.
        self._reconciliation_receipt = receipt
        self._reconciliation_target = receipt.remote_path
        self._reconciliation_status = "pending"
        self._reconcile_after_finish = receipt.status == "verified"
        self.upload_available_changed.emit(False)
        size_text = f"; размер {output_size} B" if output_size is not None else ""
        if receipt.status == "verified":
            self._set_result(
                "Cloud verified: persisted=true и read-back SHA совпали. "
                f"Target: {receipt.remote_path}{size_text}. "
                f"Original backup: {receipt.backup_path}; recovery: {receipt.recovery_path}"
            )
            self._set_status("Cloud: verified")
        else:
            self._set_result(
                "Cloud uncertain: WriteFile уже отправлен, но результат не подтверждён. "
                f"Target: {receipt.remote_path}{size_text}. Причина: {receipt.reason}. "
                f"Original backup: {receipt.backup_path}; "
                f"recovery: {receipt.recovery_path}. Повторный WriteFile запрещён."
            )
            self._set_status("Cloud: uncertain — требуется reconciliation")
        self.upload_ready.emit(receipt)

    def _on_selection_changed(self, *, preserve_prepared: bool = False) -> None:
        self._snapshot = None
        if not preserve_prepared:
            self._prepared = None
        self.upload_available_changed.emit(False)

    def _on_progress(self, message: str) -> None:
        self._set_status(message)
        self.operation_progress.emit(message)

    def _on_failed(self, message: str) -> None:
        self._set_status("Cloud operation не выполнена; WriteFile мог не запускаться")
        self._set_error(message)
        self.operation_failed.emit(message)

    def _on_finished(self) -> None:
        self._thread = None
        if self._reconcile_analyze_after_finish:
            self._reconcile_analyze_after_finish = False
            # Keep the controller busy across the list -> read-back handoff so
            # callers cannot observe a false idle state and tear down the view
            # before the reconciliation worker starts.
            self.analyze_selected()
            return
        if self._reconcile_after_finish and self._reconciliation_receipt is not None:
            self._reconcile_after_finish = False
            # Start the explicit read/list reconciliation before returning from
            # the worker lifecycle callback.  Starting it before emitting the
            # idle transition prevents callers from racing the next QThread.
            self.start_connect()
            return
        self.set_busy(False)
        self.operation_progress.emit("Cloud operation завершена")

    def set_busy(self, busy: bool) -> None:
        if not busy:
            self._refresh_upload_state()
        self.busy_changed.emit(busy)

    def set_external_busy(self, busy: bool) -> None:
        """Disable cloud controls while an unrelated local operation runs."""

        if self.is_busy:
            return
        self._external_busy = busy
        self._refresh_upload_state(blocked=busy)

    def clear_error(self) -> None:
        self._set_error("")

    def set_error(self, message: str) -> None:
        self._set_error(message)
        self._set_status("Cloud operation остановлена")

    def stop_worker(self, timeout_ms: int) -> bool:
        """Cancel the cloud thread and prove it stopped before widget teardown."""

        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.cancel()
            if not thread.wait(timeout_ms):
                return False
        debug_thread = self._debug_thread
        if debug_thread is not None and debug_thread.isRunning():
            debug_thread.requestInterruption()
            if not debug_thread.wait(timeout_ms):
                return False
        if self._thread is thread:
            self._thread = None
        if self._debug_thread is debug_thread:
            self._debug_thread = None
        self.set_busy(False)
        self._close_transport()
        return True

    def _close_transport(self) -> None:
        transport, self.transport = self.transport, None
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass

    def close(self) -> None:
        """Stop workers and release the transport during application teardown."""

        self.stop_worker(30_000)


__all__ = ["CloudController", "CloudOperationWorker", "CloudSnapshot", "SteamWebEnableWorker"]
