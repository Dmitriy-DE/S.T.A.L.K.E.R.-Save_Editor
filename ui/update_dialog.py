"""Qt presentation and background workers for application updates."""

from __future__ import annotations

import logging
import platform
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from editor.i18n import tr
from editor.update_manifest import ArtifactSpec, ManifestError
from editor.updater import (
    InstallationInfo,
    UpdateCheckResult,
    build_update_command,
    launch_installer,
    launch_update,
)

from .technical_details_dialog import TechnicalDetailsDialog
from .ux_copy import technical_details

LOGGER = logging.getLogger("stalker2_save_editor.updater")


class UpdateCheckWorker(QThread):
    """Run a manifest check away from the Qt event loop."""

    result = Signal(object)

    def __init__(self, client: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client

    def run(self) -> None:
        try:
            LOGGER.info("update check start")
            self.result.emit(self.client.check())
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            LOGGER.exception("update check failed")
            self.result.emit(UpdateCheckResult("unavailable", error=f"{type(exc).__name__}: {exc}"))


class UpdateDownloadWorker(QThread):
    """Download one verified artifact without blocking the dialog."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, client: Any, artifact: ArtifactSpec, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.artifact = artifact

    def run(self) -> None:
        destination = Path(tempfile.gettempdir()) / (
            f"SaveEditor-update-{self.artifact.file}"
        )
        try:
            LOGGER.info(
                "update download start kind=%s file=%s",
                self.artifact.kind,
                self.artifact.file,
            )
            self.completed.emit(self.client.download(self.artifact, destination))
        except Exception as exc:
            LOGGER.exception("update download failed kind=%s", self.artifact.kind)
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class UpdateDialog(QDialog):
    """Show a checked update and make applying it an explicit user action."""

    def __init__(
        self,
        result: UpdateCheckResult,
        *,
        installation: InstallationInfo,
        client: Any | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumWidth(480)  # titles and buttons were clipped at the default width
        self.setWindowTitle(tr("Обновление Save Editor"))
        self.setModal(True)
        self.installation = installation
        self.client = client
        self.check_result = result
        self._download_thread: UpdateDownloadWorker | None = None
        self._downloaded_archive: Path | None = None
        self._technical_detail_text = ""
        self._details_dialog: TechnicalDetailsDialog | None = None

        layout = QVBoxLayout(self)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setObjectName("updateTechnicalDetails")
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(
            self.details_label.textInteractionFlags()
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.details_label.setVisible(False)
        layout.addWidget(self.details_label)
        self.details_button = QPushButton(tr("Технические детали"))
        self.details_button.setObjectName("updateDetailsButton")
        self.details_button.setVisible(False)
        self.details_button.clicked.connect(self._toggle_details)
        layout.addWidget(self.details_button)

        self.download_button = QPushButton(tr("Скачать обновление"))
        self.download_button.setObjectName("updateDownloadButton")
        self.download_button.clicked.connect(self._start_download)
        layout.addWidget(self.download_button)
        self.restart_button = QPushButton(tr("Перезапустить и применить"))
        self.restart_button.setObjectName("updateRestartButton")
        self.restart_button.setEnabled(False)
        self.restart_button.clicked.connect(self._apply_update)
        layout.addWidget(self.restart_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Закрыть"))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._render_result()

    def _render_result(self) -> None:
        if self.check_result.state == "current":
            self.status_label.setText(tr("Текущая версия актуальна"))
            self.download_button.setEnabled(False)
        elif self.check_result.state == "available" and self.check_result.artifact is not None:
            manifest = self.check_result.manifest
            latest = manifest.version if manifest is not None else tr("новая версия")
            artifact = self.check_result.artifact
            self.status_label.setText(tr("Доступно обновление: {0}", latest))
            self._set_technical_details(
                tr("Файл: {0}\nРазмер: {1:.1f} МБ\nSHA-256: {2}", artifact.file, artifact.size / 1024 / 1024, artifact.sha256)
            )
            self.download_button.setEnabled(self.client is not None)
        elif self.check_result.state == "invalid":
            self.status_label.setText(tr("Не удалось проверить обновление"))
            self._set_technical_details(
                self.check_result.error or tr("Данные обновления некорректны.")
            )
            self.download_button.setEnabled(False)
        else:
            self.status_label.setText(tr("Сеть недоступна. Попробуй позже."))
            self._set_technical_details(
                self.check_result.error or tr("Приложение можно использовать дальше.")
            )
            self.download_button.setEnabled(False)

    def _start_download(self) -> None:
        if self.client is None or self.check_result.artifact is None:
            return
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        self.download_button.setEnabled(False)
        self.status_label.setText(tr("Скачивание и проверка обновления…"))
        worker = UpdateDownloadWorker(self.client, self.check_result.artifact, self)
        worker.completed.connect(self._on_downloaded)
        worker.failed.connect(self._on_download_failed)
        worker.finished.connect(worker.deleteLater)
        self._download_thread = worker
        worker.start()

    def _on_downloaded(self, path: Path) -> None:
        self._downloaded_archive = Path(path)
        LOGGER.info(
            "update download verified kind=%s file=%s",
            self.check_result.artifact.kind if self.check_result.artifact else "-",
            self.check_result.artifact.file if self.check_result.artifact else "-",
        )
        self.status_label.setText(tr("Файл обновления проверен; установка ещё не запускалась."))
        self._set_technical_details(tr("Проверенный файл: {0}", Path(path)))
        artifact_kind = self.check_result.artifact.kind if self.check_result.artifact else ""
        if artifact_kind == "disk-image":
            button_text = tr("Открыть образ")
        elif artifact_kind in {"package", "installer"}:
            button_text = tr("Открыть установщик")
        else:
            button_text = tr("Перезапустить и применить")
        self.restart_button.setText(button_text)
        self.restart_button.setEnabled(True)

    def _on_download_failed(self, message: str) -> None:
        LOGGER.error("update download failed in UI: %s", message)
        self.status_label.setText(tr("Не удалось скачать или проверить обновление."))
        self._set_technical_details(message)
        self.download_button.setEnabled(True)

    def _apply_update(self) -> None:
        archive = self._downloaded_archive
        artifact = self.check_result.artifact
        if archive is None or artifact is None:
            return
        if artifact.kind in {"package", "installer", "disk-image"}:
            LOGGER.info("update installer handoff start kind=%s file=%s", artifact.kind, artifact.file)
            try:
                launch_installer(archive, self.installation, kind=artifact.kind)
            except (OSError, ValueError, ManifestError) as exc:
                LOGGER.exception("update installer handoff rejected kind=%s", artifact.kind)
                message = (
                    tr("Не удалось открыть образ обновления.")
                    if artifact.kind == "disk-image"
                    else tr("Не удалось запустить установку.")
                )
                self.status_label.setText(message)
                self._set_technical_details(str(exc))
            else:
                LOGGER.info("update installer handoff opened kind=%s", artifact.kind)
                if artifact.kind == "disk-image":
                    self.status_label.setText(
                        tr(
                            "Образ открыт. Закрой Save Editor, перетащи приложение из образа в папку «Программы» и подтверди замену. Затем запусти редактор снова. Установленная версия не подтверждена."
                        )
                    )
                else:
                    self.status_label.setText(
                        tr("Установщик запущен; подтверди обновление в системе. Приложение закрывается.")
                    )
                    application = QApplication.instance()
                    if application is not None:
                        application.quit()
            return
        updater_name = "SaveEditor-updater.exe" if platform.system().casefold() == "windows" else "SaveEditor-updater"
        updater = self.installation.root / updater_name
        if not updater.is_file():
            self.status_label.setText(tr("Не удалось найти компонент обновления."))
            self._set_technical_details(tr("Ожидаемый путь: {0}", updater))
            return
        command = build_update_command(updater, archive, self.installation)
        try:
            launch_update(command)
        except (OSError, ValueError, ManifestError) as exc:
            LOGGER.exception("portable update handoff failed")
            self.status_label.setText(tr("Не удалось запустить обновление."))
            self._set_technical_details(str(exc))
            return
        LOGGER.info("portable update handoff started")
        self.status_label.setText(tr("Приложение закрывается; обновление будет применено."))
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _set_technical_details(self, value: object) -> None:
        self._technical_detail_text = technical_details(value)
        self.details_label.setText(self._technical_detail_text)
        visible = bool(value)
        self.details_button.setVisible(visible)
        if not visible:
            self.details_label.setVisible(False)
            self.details_button.setText(tr("Технические детали"))

    def _toggle_details(self) -> None:
        if not self._technical_detail_text:
            return
        if self._details_dialog is not None:
            self._details_dialog.close()
        self._details_dialog = TechnicalDetailsDialog(self._technical_detail_text, self)
        self._details_dialog.open()


__all__ = ["UpdateCheckWorker", "UpdateDialog"]
