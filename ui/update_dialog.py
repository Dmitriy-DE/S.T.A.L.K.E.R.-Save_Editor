"""Qt presentation and background workers for application updates."""

from __future__ import annotations

import logging
import os
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

from editor.update_manifest import ArtifactSpec, ManifestError
from editor.updater import (
    InstallationInfo,
    UpdateCheckResult,
    build_update_command,
    launch_installer,
    launch_update,
)

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
            f"SaveEditor-update-{os.getpid()}-{self.artifact.file}"
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
        self.setWindowTitle("Обновление Save Editor")
        self.setModal(True)
        self.installation = installation
        self.client = client
        self.check_result = result
        self._download_thread: UpdateDownloadWorker | None = None
        self._downloaded_archive: Path | None = None

        layout = QVBoxLayout(self)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(
            self.details_label.textInteractionFlags()
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.details_label)

        self.download_button = QPushButton("Скачать обновление")
        self.download_button.setObjectName("updateDownloadButton")
        self.download_button.clicked.connect(self._start_download)
        layout.addWidget(self.download_button)
        self.restart_button = QPushButton("Перезапустить и применить")
        self.restart_button.setObjectName("updateRestartButton")
        self.restart_button.setEnabled(False)
        self.restart_button.clicked.connect(self._apply_update)
        layout.addWidget(self.restart_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._render_result()

    def _render_result(self) -> None:
        if self.check_result.state == "current":
            self.status_label.setText("Текущая версия актуальна")
            self.download_button.setEnabled(False)
        elif self.check_result.state == "available" and self.check_result.artifact is not None:
            manifest = self.check_result.manifest
            latest = manifest.version if manifest is not None else "новая версия"
            artifact = self.check_result.artifact
            self.status_label.setText(f"Доступно обновление: {latest}")
            self.details_label.setText(
                f"Файл: {artifact.file}\n"
                f"Размер: {artifact.size / 1024 / 1024:.1f} MB\n"
                f"SHA-256: {artifact.sha256}"
            )
            self.download_button.setEnabled(self.client is not None)
        elif self.check_result.state == "invalid":
            self.status_label.setText("Манифест обновления отклонён")
            self.details_label.setText(self.check_result.error or "Данные релиза некорректны")
            self.download_button.setEnabled(False)
        else:
            self.status_label.setText("Проверка обновлений недоступна")
            self.details_label.setText(self.check_result.error or "Сеть недоступна; приложение можно использовать дальше")
            self.download_button.setEnabled(False)

    def _start_download(self) -> None:
        if self.client is None or self.check_result.artifact is None:
            return
        if self._download_thread is not None and self._download_thread.isRunning():
            return
        self.download_button.setEnabled(False)
        self.status_label.setText("Скачивание и проверка SHA-256…")
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
        self.status_label.setText("Файл скачан и проверен; применение ещё не запускалось")
        self.restart_button.setText(
            "Открыть установщик"
            if self.check_result.artifact
            and self.check_result.artifact.kind in {"package", "installer"}
            else "Перезапустить и применить"
        )
        self.restart_button.setEnabled(True)

    def _on_download_failed(self, message: str) -> None:
        LOGGER.error("update download failed in UI: %s", message)
        self.status_label.setText("Обновление не скачано")
        self.details_label.setText(message)
        self.download_button.setEnabled(True)

    def _apply_update(self) -> None:
        archive = self._downloaded_archive
        artifact = self.check_result.artifact
        if archive is None or artifact is None:
            return
        if artifact.kind in {"package", "installer"}:
            LOGGER.info("update installer handoff start kind=%s file=%s", artifact.kind, artifact.file)
            try:
                launch_installer(archive, self.installation, kind=artifact.kind)
            except (OSError, ValueError, ManifestError) as exc:
                LOGGER.exception("update installer handoff rejected kind=%s", artifact.kind)
                self.status_label.setText(f"Установщик скачан, но не запущен: {exc}")
            else:
                LOGGER.info("update installer handoff opened kind=%s", artifact.kind)
                self.status_label.setText(
                    "Установщик запущен; подтверди обновление в системе. "
                    "Приложение закрывается."
                )
                application = QApplication.instance()
                if application is not None:
                    application.quit()
            return
        updater_name = "SaveEditor-updater.exe" if platform.system().casefold() == "windows" else "SaveEditor-updater"
        updater = self.installation.root / updater_name
        if not updater.is_file():
            self.status_label.setText(f"Updater не найден: {updater}")
            return
        command = build_update_command(updater, archive, self.installation)
        try:
            launch_update(command)
        except (OSError, ValueError, ManifestError) as exc:
            LOGGER.exception("portable update handoff failed")
            self.status_label.setText(f"Не удалось запустить обновление: {exc}")
            return
        LOGGER.info("portable update handoff started")
        self.status_label.setText("Приложение закрывается; updater применит новую версию")
        application = QApplication.instance()
        if application is not None:
            application.quit()


__all__ = ["UpdateCheckWorker", "UpdateDialog"]
