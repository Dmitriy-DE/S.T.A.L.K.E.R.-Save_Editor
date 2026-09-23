"""Render deterministic desktop UI review artifacts from the canonical Qt shell.

The reference images are used only as comparison inputs.  The actual images are
always produced by the application widgets and the normal stylesheet/assets.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import sys
import tempfile
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from editor.capabilities import FormatCapabilities
from editor.formats import STALKER2_FORMAT
from editor.service import EditorService
from editor.storage import ExportReceipt
from save_format import inspect_save
from ui.fonts import REFERENCE_FONT_FAMILY
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot
from ui.theme import COLORS, SPACING, TYPOGRAPHY

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = Path("/home/dmytro/Downloads")
OUTPUT = ROOT / "artifacts" / "ui-review"
VIEWPORT = QSize(1586, 992)


class RenderedState(TypedDict):
    actual: QImage
    actual_path: str
    widget: str


def _rect(rect: QRect) -> dict[str, int]:
    return {
        "x": rect.x(),
        "y": rect.y(),
        "width": rect.width(),
        "height": rect.height(),
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_image(source: Path, destination: Path) -> None:
    image = QImage(str(source))
    if image.isNull():
        raise RuntimeError(f"Could not read reference image: {source}")
    if not image.save(str(destination), b"PNG"):
        raise RuntimeError(f"Could not write reference image: {destination}")


def _board_reference(source: Path, destination: Path, panel_index: int) -> None:
    image = QImage(str(source))
    if image.isNull():
        raise RuntimeError(f"Could not read board reference: {source}")
    # The supplied board is a 2x3 contact sheet.  Keep the selected panel's
    # aspect ratio and place it on the fixed review canvas instead of stretching
    # it into a fake full-screen screenshot.
    margin_x = 18
    margin_y = 27
    gutter_x = 20
    gutter_y = 28
    cell_width = (image.width() - (2 * margin_x) - gutter_x) // 2
    cell_height = (image.height() - (2 * margin_y) - (2 * gutter_y)) // 3
    column = panel_index % 2
    row = panel_index // 2
    source_rect = QRect(
        margin_x + column * (cell_width + gutter_x),
        margin_y + row * (cell_height + gutter_y),
        cell_width,
        cell_height,
    )
    crop = image.copy(source_rect)
    canvas = QImage(VIEWPORT, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#080a09"))
    scaled = crop.scaled(QSize(VIEWPORT.width() - 72, VIEWPORT.height() - 116), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    painter.drawImage(QPoint((canvas.width() - scaled.width()) // 2, (canvas.height() - scaled.height()) // 2), scaled)
    painter.end()
    if not canvas.save(str(destination), b"PNG"):
        raise RuntimeError(f"Could not write board reference: {destination}")


def _side_by_side(reference: QImage, actual: QImage, destination: Path) -> None:
    image = QImage(reference.width() + actual.width(), max(reference.height(), actual.height()), QImage.Format.Format_ARGB32)
    image.fill(QColor("#080a09"))
    painter = QPainter(image)
    painter.drawImage(0, 0, reference)
    painter.drawImage(reference.width(), 0, actual)
    painter.setPen(QPen(QColor("#d6a62d"), 2))
    painter.drawLine(reference.width(), 0, reference.width(), image.height())
    painter.end()
    image.save(str(destination), b"PNG")


def _diff(reference: QImage, actual: QImage, destination: Path) -> dict[str, int | float]:
    reference = reference.convertToFormat(QImage.Format.Format_RGBA8888)
    actual = actual.convertToFormat(QImage.Format.Format_RGBA8888)
    width = min(reference.width(), actual.width())
    height = min(reference.height(), actual.height())
    left = bytes(reference.bits())
    right = bytes(actual.bits())
    pixels = width * height
    diff_bytes = bytearray(pixels * 4)
    total = 0
    changed = 0
    maximum = 0
    for index in range(0, pixels * 4, 4):
        red = abs(left[index] - right[index])
        green = abs(left[index + 1] - right[index + 1])
        blue = abs(left[index + 2] - right[index + 2])
        value = max(red, green, blue)
        total += red + green + blue
        maximum = max(maximum, value)
        if value > 12:
            changed += 1
        diff_bytes[index:index + 4] = bytes((min(255, value * 4), min(255, value * 2), 0, 255))
    image = QImage(bytes(diff_bytes), width, height, width * 4, QImage.Format.Format_RGBA8888)
    image.save(str(destination), b"PNG")
    return {
        "width": width,
        "height": height,
        "changed_pixels_threshold_12": changed,
        "changed_pixel_ratio_threshold_12": round(changed / pixels, 6) if pixels else 0.0,
        "mean_rgb_delta": round(total / (pixels * 3), 3) if pixels else 0.0,
        "max_channel_delta": maximum,
    }


def _snapshot(raw: bytes, directory: Path, *, release_id: str = "stalker2", format_id: str = "stalker2", title: str = "S.T.A.L.K.E.R. 2: Heart of Chornobyl") -> LocalSnapshot:
    path = directory / ("99457897416AC2273A59B826C7F6306.sav" if release_id == "stalker2" else "xray_state.sav")
    path.write_bytes(raw)
    info = inspect_save(raw, with_inventory=True)
    return LocalSnapshot(
        path=path,
        data=raw,
        info=info,
        format_id=format_id,
        format_title=title,
        release_id=release_id,
        capabilities=STALKER2_FORMAT.capabilities if release_id == "stalker2" else FormatCapabilities(read_inventory=True),
    )


def _fixture_bytes() -> bytes:
    namespace = runpy.run_path(str(ROOT / "tests" / "conftest.py"))
    fixture = namespace["synthetic_save"]
    return fixture.__wrapped__()


def _prepare_window(app: QApplication, raw: bytes, directory: Path) -> tuple[MainWindow, LocalSnapshot, LocalSnapshot]:
    def empty_discovery() -> SaveDiscovery:
        return SaveDiscovery((), (directory,))

    window = MainWindow(EditorService(), slot_discovery=empty_discovery, auto_update_check=False)
    window.resize(VIEWPORT)
    window.show()
    app.processEvents()
    local = _snapshot(raw, directory)
    xray = _snapshot(raw, directory, release_id="soc", format_id="soc", title="S.T.A.L.K.E.R.: Shadow of Chernobyl")
    slot = SaveSlot(
        path=local.path,
        candidate_game_id="stalker2",
        candidate_game_title=local.format_title,
        size=len(raw),
        modified_ns=0,
        format_id=local.format_id,
        format_title=local.format_title,
        detected_release_id=local.release_id,
    )
    window.library_view.set_discovery(SaveDiscovery((slot,), (directory,)))
    window._render_snapshot(local)
    # Do not let host-machine backup history leak into deterministic review
    # frames; the history surface itself remains wired to BackupController.
    window.backup_controller._records = ()
    window.history_reference_view._render()
    return window, local, xray


def _show(window: MainWindow, widget_name: str, *, destination: str) -> None:
    widget = getattr(window, widget_name)
    window.reference_stack.setCurrentWidget(widget)
    window.app_shell.set_active_destination(destination, emit=False)
    QApplication.processEvents()


def _render_states(app: QApplication, window: MainWindow, local: LocalSnapshot, xray: LocalSnapshot, directory: Path) -> dict[str, RenderedState]:
    receipt = ExportReceipt(
        output_path=directory / "edited.sav",
        backup_path=directory / "backup.sav",
        output_sha256=hashlib.sha256(local.data).hexdigest(),
    )
    window.save_review_view.set_source("Источник: 99457897416AC2273A59B826C7F6306.sav · изменений: 2 · bytes исходного сейва пока не изменены")
    window.save_review_view.set_changes((("Баланс", "100 ₽", "999 ₽"), ("Инвентарь", "2", "3")))
    window.save_result_view.set_receipt(receipt)
    window.character_view.set_snapshot(xray)
    window.character_view.set_state({}, None)
    window.unsupported_view.set_snapshot(xray, "Обнаружен релиз, для которого безопасное редактирование пока не подтверждено.")
    states = (
        ("01-library", "library_view", "library"),
        ("02-editor", "editor_view", "library"),
        ("03-settings", "settings_reference_view", "settings"),
        ("04-cloud", "cloud_reference_view", "cloud"),
        ("05-history", "history_reference_view", "history"),
        ("06-character", "character_view", "library"),
        ("07-review", "save_review_view", "library"),
        ("08-result", "save_result_view", "library"),
        ("09-unsupported", "unsupported_view", "library"),
    )
    results: dict[str, RenderedState] = {}
    for name, widget_name, destination in states:
        _show(window, widget_name, destination=destination)
        actual = window.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        actual_path = OUTPUT / name / "actual.png"
        actual.save(str(actual_path), b"PNG")
        results[name] = {"actual": actual, "actual_path": str(actual_path), "widget": widget_name}
    return results


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PYTEST_CURRENT_TEST", "ui-review")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for child in OUTPUT.iterdir():
        if child.is_dir():
            for path in child.iterdir():
                if path.is_file():
                    path.unlink()
        elif child.is_file():
            child.unlink()

    application = QApplication.instance()
    app = application if isinstance(application, QApplication) else QApplication([])
    raw = _fixture_bytes()
    with tempfile.TemporaryDirectory(prefix="save-editor-ui-review-") as temp:
        directory = Path(temp)
        window, local, xray = _prepare_window(app, raw, directory)
        rendered = _render_states(app, window, local, xray, directory)
        app.processEvents()

        reference_sources = {
            "01-library": DOWNLOADS / "01_LIBRARY_CANONICAL.png",
            "02-editor": DOWNLOADS / "02_EDITOR_CANONICAL.png",
            "03-settings": DOWNLOADS / "03_SETTINGS_CANONICAL.png",
        }
        board_source = DOWNLOADS / "04_REMAINING_STATES_BOARD_CANONICAL.png"
        board_panels = {"04-cloud": 0, "05-history": 1, "06-character": 2, "07-review": 3, "08-result": 4, "09-unsupported": 5}
        for name in rendered:
            target = OUTPUT / name
            target.mkdir(parents=True, exist_ok=True)
            reference_path = target / "reference.png"
            if name in reference_sources:
                _copy_image(reference_sources[name], reference_path)
                reference_kind = "full canonical reference"
                source_name = reference_sources[name].name
            else:
                _board_reference(board_source, reference_path, board_panels[name])
                reference_kind = "panel crop from canonical board placed on fixed canvas"
                source_name = board_source.name
            reference = QImage(str(reference_path)).convertToFormat(QImage.Format.Format_ARGB32)
            actual = rendered[name]["actual"]
            _side_by_side(reference, actual, target / "side-by-side.png")
            diff_stats = _diff(reference, actual, target / "diff.png")
            widget = getattr(window, rendered[name]["widget"])
            header = window.app_shell.findChild(QWidget, "referenceHeader")
            content = window.app_shell.findChild(QWidget, "referenceContent")
            footer = window.app_shell.findChild(QWidget, "referenceFooter")
            metrics = {
                "screen": name,
                "reference_source": source_name,
                "reference_kind": reference_kind,
                "viewport": {"width": VIEWPORT.width(), "height": VIEWPORT.height(), "dpr": 1},
                "actual_image": {"width": actual.width(), "height": actual.height()},
                "geometry": {
                    "window": _rect(window.geometry()),
                    "shell": _rect(window.app_shell.geometry()),
                    "header": _rect(header.geometry()) if header else None,
                    "content": _rect(content.geometry()) if content else None,
                    "footer": _rect(footer.geometry()) if footer else None,
                    "active_view": _rect(widget.geometry()),
                },
                "tokens": {"palette": COLORS, "spacing": SPACING, "typography": TYPOGRAPHY, "font_family": REFERENCE_FONT_FAMILY},
                "diff": diff_stats,
                "data_policy": "synthetic parser fixture; no invented save fields are asserted",
            }
            _write_json(target / "metrics.json", metrics)
        window.discovery_controller.wait_for_worker()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
