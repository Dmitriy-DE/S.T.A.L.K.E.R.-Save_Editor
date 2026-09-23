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
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from editor.capabilities import FormatCapabilities
from editor.catalog_bundle import load_catalog_file
from editor.formats import STALKER2_FORMAT, STALKER_COP_FORMAT
from editor.releases import release_by_id
from editor.service import EditorService
from editor.storage import BackupRecord, ExportReceipt
from editor.xray_save import COP_FORMAT, inspect_xray
from save_format import inspect_save
from steam_cloud import CloudFile
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
    geometry: dict[str, object]
    screen_rects: dict[str, object]


def _rect(rect: QRect) -> dict[str, int]:
    return {
        "x": rect.x(),
        "y": rect.y(),
        "width": rect.width(),
        "height": rect.height(),
    }


def _absolute_rect(window: QWidget, child: QWidget | None) -> dict[str, int] | None:
    """Return a visible widget's viewport rect in the captured window."""

    if child is None or not child.isVisible() or child.width() <= 0 or child.height() <= 0:
        return None
    point = child.mapTo(window, QPoint(0, 0))
    return _rect(QRect(point, child.size()))


def _capture_layout_metrics(
    window: MainWindow,
    name: str,
    widget: QWidget,
) -> tuple[dict[str, object], dict[str, object]]:
    """Capture geometry while each review state is actually visible."""

    header = window.app_shell.findChild(QWidget, "referenceHeader")
    content = window.app_shell.findChild(QWidget, "referenceContent")
    footer = window.app_shell.findChild(QWidget, "referenceFooter")
    view: Any
    if name == "01-library":
        view = window.library_view
        screen_rects: dict[str, object] = {
            "game_rail": _absolute_rect(window, view.game_rail),
            "centre": _absolute_rect(window, view.findChild(QWidget, "libraryCentre")),
            "save_table": _absolute_rect(window, view.save_table),
            "preview_panel": _absolute_rect(window, view.preview_panel),
            "recent_activity": _absolute_rect(window, view.recent_activity),
            "open_cta": _absolute_rect(window, view.open_button),
        }
    elif name == "02-editor":
        view = window.editor_view
        screen_rects = {
            "status_equipment_column": _absolute_rect(window, view.status_column),
            "inventory_column": _absolute_rect(window, view.inventory_column),
            "inventory_table": _absolute_rect(window, view.table),
            "detail_column": _absolute_rect(window, view.detail_column),
            "save_cta": _absolute_rect(window, view.save_button),
        }
    elif name == "03-settings":
        view = window.settings_reference_view
        screen_rects = {
            "category_rail": _absolute_rect(window, view.findChild(QWidget, "settingsCategoryRail")),
            "content": _absolute_rect(window, view.settings_content),
            "visible_panels": {
                page.objectName(): _absolute_rect(window, page)
                for page in view._settings_pages
                if page.isVisible()
            },
            "save_cta": _absolute_rect(window, view.save_button),
        }
    elif name == "04-cloud":
        view = window.cloud_reference_view
        screen_rects = {
            "game_rail": _absolute_rect(window, view.findChild(QWidget, "cloudGameRail")),
            "workspace": _absolute_rect(window, view.findChild(QWidget, "cloudWorkspace")),
            "controls": _absolute_rect(window, view.findChild(QWidget, "cloudControlsPanel")),
            "table_panel": _absolute_rect(window, view.findChild(QWidget, "cloudTablePanel")),
            "save_table": _absolute_rect(window, view.save_table),
            "detail_panel": _absolute_rect(window, view.detail_panel),
            "detail_image": _absolute_rect(window, view.detail_image),
            "download_cta": _absolute_rect(window, view.download_button),
            "upload_cta": _absolute_rect(window, view.upload_button),
            "safety_panel": _absolute_rect(window, view.findChild(QWidget, "cloudSafetyPanel")),
        }
    elif name == "05-history":
        view = window.history_reference_view
        screen_rects = {
            "game_rail": _absolute_rect(window, view.findChild(QWidget, "historyGameRail")),
            "workspace": _absolute_rect(window, view.findChild(QWidget, "historyWorkspace")),
            "table_panel": _absolute_rect(window, view.table_panel),
            "source_filter": _absolute_rect(window, view.source_filter_edit),
            "table": _absolute_rect(window, view.table),
            "detail_panel": _absolute_rect(window, view.detail_panel),
            "detail_image": _absolute_rect(window, view.detail_image),
            "preview_cta": _absolute_rect(window, view.preview_button),
            "restore_cta": _absolute_rect(window, view.restore_button),
            "restore_in_place_cta": _absolute_rect(window, view.restore_in_place_button),
        }
    elif name == "06-character":
        view = window.character_view
        screen_rects = {
            "game_rail": _absolute_rect(window, view.findChild(QWidget, "characterGameRail")),
            "workspace": _absolute_rect(window, view.findChild(QWidget, "characterWorkspace")),
            "profile_panel": _absolute_rect(window, view.findChild(QWidget, "characterProfilePanel")),
            "relations_panel": _absolute_rect(window, view.findChild(QWidget, "characterRelationsPanel")),
            "faction_table": _absolute_rect(window, view.faction_table),
            "warning": _absolute_rect(window, view.warning_label),
        }
    elif name == "07-review":
        view = window.save_review_view
        screen_rects = {
            "modal_card": _absolute_rect(window, window.reference_modal_card),
            "changes_panel": _absolute_rect(window, view.findChild(QWidget, "reviewChangesPanel")),
            "changes_table": _absolute_rect(window, view.changes_table),
            "pipeline_panel": _absolute_rect(window, view.findChild(QWidget, "reviewPipelinePanel")),
            "confirm_cta": _absolute_rect(window, view.confirm_button),
            "cancel_cta": _absolute_rect(window, view.cancel_button),
        }
    elif name == "08-result":
        view = window.save_result_view
        screen_rects = {
            "modal_card": _absolute_rect(window, window.reference_modal_card),
            "receipt_panel": _absolute_rect(window, view.findChild(QWidget, "resultReceiptPanel")),
            "receipt_table": _absolute_rect(window, view.receipt_table),
            "editor_cta": _absolute_rect(window, view.editor_button),
            "history_cta": _absolute_rect(window, view.history_button),
            "library_cta": _absolute_rect(window, view.library_button),
            "reconcile_cta": _absolute_rect(window, view.reconcile_button),
        }
    elif name == "09-unsupported":
        view = window.unsupported_view
        screen_rects = {
            "modal_card": _absolute_rect(window, window.reference_modal_card),
            "detail_panel": _absolute_rect(window, view.detail_panel),
            "preview_image": _absolute_rect(window, view.preview_image),
            "folder_cta": _absolute_rect(window, view.folder_button),
            "diagnostics_cta": _absolute_rect(window, view.diagnostics_button),
            "library_cta": _absolute_rect(window, view.back_button),
        }
    else:
        screen_rects = {}
    geometry: dict[str, object] = {
        "window": _rect(window.geometry()),
        "shell": _rect(window.app_shell.geometry()),
        "header": _absolute_rect(window, header),
        "content": _absolute_rect(window, content),
        "footer": _absolute_rect(window, footer),
        "active_view": _absolute_rect(window, widget),
    }
    return geometry, screen_rects


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy_image(source: Path, destination: Path) -> None:
    image = QImage(str(source))
    if image.isNull():
        raise RuntimeError(f"Could not read reference image: {source}")
    if not image.save(str(destination), "PNG"):  # type: ignore[call-overload]
        raise RuntimeError(f"Could not write reference image: {destination}")


def _board_reference(source: Path, destination: Path, panel_index: int) -> QRect:
    image = QImage(str(source))
    if image.isNull():
        raise RuntimeError(f"Could not read board reference: {source}")
    # The supplied board is a 2x3 contact sheet. Keep the selected panel at its
    # native geometry. It is a design reference, not a same-canvas pixel target.
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
    if not crop.save(str(destination), "PNG"):  # type: ignore[call-overload]
        raise RuntimeError(f"Could not write board reference: {destination}")
    return source_rect


def _side_by_side(reference: QImage, actual: QImage, destination: Path) -> None:
    image = QImage(reference.width() + actual.width(), max(reference.height(), actual.height()), QImage.Format.Format_ARGB32)
    image.fill(QColor("#080a09"))
    painter = QPainter(image)
    painter.drawImage(0, 0, reference)
    painter.drawImage(reference.width(), 0, actual)
    painter.setPen(QPen(QColor("#d6a62d"), 2))
    painter.drawLine(reference.width(), 0, reference.width(), image.height())
    painter.end()
    image.save(str(destination), "PNG")  # type: ignore[call-overload]


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
    image.save(str(destination), "PNG")  # type: ignore[call-overload]
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


def _xray_snapshot(raw: bytes, directory: Path, catalog_bundle) -> LocalSnapshot:
    path = directory / "xray_state.scop"
    path.write_bytes(raw)
    return LocalSnapshot(
        path=path,
        data=raw,
        info=inspect_xray(raw, COP_FORMAT),
        format_id=COP_FORMAT.id,
        format_title=COP_FORMAT.title,
        release_id=COP_FORMAT.id,
        edition=release_by_id(COP_FORMAT.id).edition,
        capabilities=STALKER_COP_FORMAT.capabilities,
        catalog=catalog_bundle.items,
        game_catalog=catalog_bundle.game_catalog,
    )


def _fixture_bytes() -> bytes:
    namespace = runpy.run_path(str(ROOT / "tests" / "conftest.py"))
    fixture = namespace["synthetic_save"]
    return fixture.__wrapped__()


def _xray_fixture_bytes() -> bytes:
    namespace = runpy.run_path(str(ROOT / "tests" / "test_xray_save.py"))
    return namespace["_fixture"]()


def _review_inventory(info, catalog_bundle):
    """Expand one real X-Ray observation with official-catalog review rows."""

    base = info.inventory[0]
    keys = (
        "mp_wpn_ak74",
        "mp_wpn_toz34",
        "cs_heavy_outfit",
        "helm_respirator",
        "detector_advanced",
        "zat_b33_safe_container",
        "ammo_9x39_pab9",
        "ammo_5.45x39_fmj",
        "medkit",
        "bandage",
        "bread",
        "energy_drink",
        "af_gravi",
        "af_cristall",
        "af_electra_sparkler",
        "af_dummy_battery",
        "bolt",
    )
    review_keys = (
        *keys,
        *tuple(
            item.key
            for item in catalog_bundle.items.items
            if item.key not in keys
        )[:25],
    )
    forced_categories = {
        "cs_heavy_outfit": "armor",
        "helm_respirator": "helmet",
        "detector_advanced": "device",
        "zat_b33_safe_container": "other",
    }
    presentation_names = {
        # These are catalog-backed display labels for the review fixture; the
        # serialized type keys remain the source of truth in every row.
        "mp_wpn_ak74": "AK-74",
        "mp_wpn_toz34": "TOZ-34",
        "cs_heavy_outfit": "ПСЗ-9Д",
        "helm_respirator": "ПСЗ-7",
        "detector_advanced": "«Велес»",
        "zat_b33_safe_container": "«ВЕРПИЛО-5»",
        "ammo_9x39_pab9": "9×39 мм СП-6",
        "ammo_5.45x39_fmj": "5.45×39 мм БП",
        "medkit": "Аптечка ИП-5",
        "bandage": "Бинт",
        "bread": "Хлеб",
        "energy_drink": "Энергетик «Non Stop»",
        "af_gravi": "Грави",
        "af_cristall": "Кристалл",
        "af_electra_sparkler": "Вспышка",
        "af_dummy_battery": "Пустышка",
    }
    presentation_weights = {
        "mp_wpn_ak74": 3.6,
        "mp_wpn_toz34": 3.4,
        "cs_heavy_outfit": 8.0,
        "helm_respirator": 3.2,
        "detector_advanced": 0.6,
        "zat_b33_safe_container": 2.0,
        "ammo_9x39_pab9": 1.4,
        "ammo_5.45x39_fmj": 3.6,
        "medkit": 0.5,
        "bandage": 0.1,
        "bread": 0.4,
        "energy_drink": 0.4,
    }
    presentation_conditions = {
        "mp_wpn_ak74": 0.87,
        "mp_wpn_toz34": 0.92,
        "cs_heavy_outfit": 0.76,
        "helm_respirator": 0.90,
        "detector_advanced": 1.0,
    }
    rows = []
    for index, key in enumerate(review_keys, start=1):
        definition = catalog_bundle.items.resolve(key)
        if definition is None:
            continue
        category = forced_categories.get(key, definition.category or "other")
        count = 30 if category == "ammo" else (5 if category == "consumable" else 1)
        condition = presentation_conditions.get(
            key,
            1.0 if category == "artifact" else None,
        )
        total_weight = presentation_weights.get(
            key,
            (definition.unit_weight or 0.4) * count,
        )
        unit_weight = total_weight / count if count else definition.unit_weight or 0.4
        rows.append(
            replace(
                base,
                handle=0x1000 + index,
                x=(index - 1) % 5,
                y=(index - 1) // 5,
                width=1,
                height=1,
                cells=(((index - 1) % 5, (index - 1) // 5),),
                count=count,
                total_weight=total_weight,
                unit_weight=unit_weight,
                kind_code=4,
                category=category,
                record_offset=base.record_offset + index,
                record_end_guess=base.record_end_guess + index,
                fingerprint=f"review-{key}",
                type_key=key,
                editable_count=category in {"ammo", "consumable"},
                display_name=presentation_names.get(key) or definition.display_name or key,
                count_max=definition.max_stack or (999 if category == "ammo" else 99),
                condition=condition,
                condition_editable=condition is not None,
                storage="equipped" if index <= 5 else "inventory",
                upgrades=(
                    (
                        "up_firsta_ak74",
                        "up_firstc_ak74",
                        "up_secona_ak74",
                        "up_second_ak74",
                    )
                    if key == "mp_wpn_ak74"
                    else ()
                ),
                upgrades_editable=key == "mp_wpn_ak74",
                placement_type="slot" if index <= 5 else "inventory",
                placement_slot=index if index <= 5 else None,
                placement_editable=True,
                remove_editable=True,
            )
        )
    return replace(info, inventory=tuple(rows), owned_handles=tuple(row.handle for row in rows))


def _prepare_window(app: QApplication, raw: bytes, directory: Path) -> tuple[MainWindow, LocalSnapshot, LocalSnapshot]:
    def empty_discovery() -> SaveDiscovery:
        return SaveDiscovery((), (directory,))

    window = MainWindow(EditorService(), slot_discovery=empty_discovery, auto_update_check=False)
    window.resize(VIEWPORT)
    window.show()
    app.processEvents()
    local = _snapshot(raw, directory)
    catalog_bundle = load_catalog_file(ROOT / "web" / "catalogs.json")["stalker-cop"]
    xray = _xray_snapshot(_xray_fixture_bytes(), directory, catalog_bundle)
    xray = replace(xray, info=_review_inventory(xray.info, catalog_bundle))
    # The library panel is a deterministic presentation fixture.  Its bytes
    # remain the real synthetic S2 fixture, while the summary uses the
    # catalog-backed item observations prepared for the editor review.
    local = replace(
        local,
        info=replace(
            local.info,
            money=9_999_999,
            inventory=xray.info.inventory,
        ),
    )
    review_names = (
        "99457897416AC2273A59B826C7F6306.sav",
        "Pripyat_quicksave.sav",
        "autosave_12.sav",
        "bar_100.sav",
        "slot_ee.sav",
        "manual_save.sav",
        "escape.sav",
    )
    review_families = (
        "stalker2",
        "cop",
        "clear_sky",
        "soc",
        "soc",
        "stalker2",
        "clear_sky",
    )
    review_times = (
        datetime(2026, 9, 23, 0, 18),
        datetime(2026, 9, 22, 23, 41),
        datetime(2026, 9, 21, 18, 13),
        datetime(2026, 9, 18, 16, 3),
        datetime(2026, 9, 17, 12, 31),
        datetime(2026, 9, 14, 20, 24),
        datetime(2026, 9, 12, 11, 10),
    )
    review_sizes = tuple(
        int(value * 1024 * 1024)
        for value in (15.6, 6.5, 6.8, 5.9, 7.3, 8.1, 4.2)
    )
    slots = tuple(
        SaveSlot(
            path=directory / review_names[index - 1],
            candidate_game_id=review_families[index - 1],
            candidate_game_title=local.format_title,
            size=review_sizes[index - 1],
            modified_ns=int(review_times[index - 1].timestamp() * 1_000_000_000),
            format_id=local.format_id,
            format_title=local.format_title,
            detected_release_id=local.release_id,
        )
        for index in range(1, 8)
    )
    for slot in slots:
        slot.path.write_bytes(raw)
    window.library_view.set_discovery(SaveDiscovery(slots, (directory,)))
    window._render_snapshot(local)
    window.backup_controller.set_review_records(
        tuple(
            BackupRecord(
                journal_path=directory / f"journal-{index}.json",
                backup_path=directory / f"review-backup-{index}.sav",
                created_at=f"2026-09-23 00:{index:02d}:00",
                source_path=str(slots[index - 1].path),
                source_sha256=hashlib.sha256(raw).hexdigest(),
                output_path=str(slots[index - 1].path),
                output_sha256=hashlib.sha256(raw).hexdigest(),
                operation={"mode": "replace", "stack_count": index % 3, "money": 9999999 if index == 1 else None},
                status="verified",
                actual_sha256=hashlib.sha256(raw).hexdigest(),
            )
            for index in range(1, 7)
        )
    )
    window.cloud_controller.set_review_files(
        tuple(
            CloudFile(
                name=f"Stalker2/Saved/STEAM/SaveGames/Data/cloud_slot_{index}.sav",
                size=len(raw) + index * 1024,
                timestamp=1_758_600_000 + index * 3600,
                is_persisted=True,
                exists=True,
                source="native_remote_storage",
            )
            for index in range(1, 5)
        )
    )
    window.history_reference_view._render()
    if window.cloud_reference_view.save_table.rowCount():
        window.cloud_reference_view.save_table.selectRow(0)
    if window.history_reference_view.table.rowCount():
        window.history_reference_view.table.selectRow(0)
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
    ee_data = b"STALKER-EE-REVIEW-CANDIDATE\x00"
    ee_info = inspect_save(local.data, with_inventory=False)
    ee_info = replace(ee_info, sha256=hashlib.sha256(ee_data).hexdigest(), inventory=(), money=None)
    ee = LocalSnapshot(
        path=directory / "enhanced-edition-candidate.sav",
        data=ee_data,
        info=ee_info,
        format_id="stalker-soc-ee",
        format_title=release_by_id("stalker-soc-ee").title,
        release_id="stalker-soc-ee",
        edition="enhanced",
        capabilities=FormatCapabilities(read_inventory=False),
    )
    window.unsupported_view.set_snapshot(ee, "Обнаружен кандидат Enhanced Edition. Без собственного parser/writer и load/re-save evidence редактирование отключено.")
    window.cloud_reference_view._on_files_ready(window.cloud_controller.files)
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
        if widget_name == "library_view":
            window._show_reference_library()
        elif widget_name == "editor_view":
            # The editor review must exercise the populated, parser-backed
            # inventory while retaining the canonical S.T.A.L.K.E.R. 2
            # release context shown by the reference editor.
            editor_snapshot = replace(
                local,
                catalog=xray.catalog,
                game_catalog=xray.game_catalog,
            )
            window._render_snapshot(editor_snapshot, show_editor=False)
            window.editor_view.character_button.setVisible(False)
            window._show_reference_editor()
            ak74 = next(
                (item.handle for item in xray.info.inventory if item.type_key == "mp_wpn_ak74"),
                None,
            )
            if ak74 is not None:
                window.editor_view.select_handle(ak74)
                # Review-only presentation state: exercise the single commit
                # CTA with a capability-backed money draft; no bytes are
                # written by the renderer and the selected item's condition
                # stays a clean catalog-backed value like the reference.
                window.staged_money = 9_999_999
                window.editor_view.set_money_draft(window.staged_money)
                window._render_changes()
                window._update_action_buttons()
        elif widget_name == "settings_reference_view":
            window._show_settings()
        elif widget_name == "cloud_reference_view":
            window._show_cloud()
        elif widget_name == "history_reference_view":
            window._show_history()
        elif widget_name == "character_view":
            window._show_character_state()
        elif widget_name == "save_review_view":
            window._render_snapshot(xray, show_editor=False)
            window._show_reference_editor()
            window._show_reference_modal(window.save_review_view, base_widget=window.editor_view)
            window.app_shell.set_footer_actions(
                (
                    ("Enter", "Подтвердить", window._confirm_reference_save),
                    ("Esc", "Отмена", window._cancel_reference_save),
                )
            )
        elif widget_name == "save_result_view":
            window._render_snapshot(xray, show_editor=False)
            window._show_reference_editor()
            window._show_save_result(receipt)
        else:
            if widget_name == "unsupported_view":
                window._show_reference_library()
                window._show_reference_modal(window.unsupported_view, base_widget=window.library_view)
            else:
                _show(window, widget_name, destination=destination)
        actual = window.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        actual_path = OUTPUT / name / "actual.png"
        actual.save(str(actual_path), "PNG")  # type: ignore[call-overload]
        geometry, screen_rects = _capture_layout_metrics(window, name, getattr(window, widget_name))
        results[name] = {
            "actual": actual,
            "actual_path": str(actual_path),
            "widget": widget_name,
            "geometry": geometry,
            "screen_rects": screen_rects,
        }
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
                board_rect = _board_reference(board_source, reference_path, board_panels[name])
                reference_kind = "board panel geometry reference; no same-canvas pixel score"
                source_name = board_source.name
            reference = QImage(str(reference_path)).convertToFormat(QImage.Format.Format_ARGB32)
            actual = rendered[name]["actual"]
            _side_by_side(reference, actual, target / "side-by-side.png")
            diff_stats = None
            if name in reference_sources:
                diff_stats = _diff(reference, actual, target / "diff.png")
            widget = getattr(window, rendered[name]["widget"])
            def absolute_rect(child: QWidget | None) -> dict[str, int] | None:
                if child is None or not child.isVisible():
                    return None
                point = child.mapTo(window, QPoint(0, 0))
                return _rect(QRect(point, child.size()))

            def visible_named(root_widget: QWidget) -> dict[str, dict[str, int] | None]:
                return {
                    child.objectName(): absolute_rect(child)
                    for child in root_widget.findChildren(QWidget)
                    if child.objectName() and child.width() > 0 and child.height() > 0
                }

            current_named = visible_named(widget)
            screen_rects: dict[str, object]
            if name == "01-library":
                library_view = window.library_view
                screen_rects = {
                    "game_rail": absolute_rect(library_view.game_rail),
                    "centre": absolute_rect(library_view.findChild(QWidget, "libraryCentre")),
                    "save_table": absolute_rect(library_view.save_table),
                    "preview_panel": absolute_rect(library_view.preview_panel),
                    "recent_activity": absolute_rect(library_view.recent_activity),
                    "open_cta": absolute_rect(library_view.open_button),
                }
            elif name == "02-editor":
                editor_view = window.editor_view
                screen_rects = {
                    "status_equipment_column": absolute_rect(editor_view.status_column),
                    "inventory_column": absolute_rect(editor_view.inventory_column),
                    "inventory_table": absolute_rect(editor_view.table),
                    "detail_column": absolute_rect(editor_view.detail_column),
                    "save_cta": absolute_rect(editor_view.save_button),
                }
            elif name == "03-settings":
                settings_view = window.settings_reference_view
                screen_rects = {
                    "category_rail": absolute_rect(settings_view.findChild(QWidget, "settingsCategoryRail")),
                    "content": absolute_rect(settings_view.settings_content),
                    "visible_panels": {
                        page.objectName(): absolute_rect(page)
                        for page in settings_view._settings_pages
                        if not page.isHidden()
                    },
                    "save_cta": absolute_rect(settings_view.save_button),
                }
            elif name == "04-cloud":
                cloud_view = window.cloud_reference_view
                screen_rects = {
                    "game_rail": absolute_rect(cloud_view.findChild(QWidget, "cloudGameRail")),
                    "workspace": absolute_rect(cloud_view.findChild(QWidget, "cloudWorkspace")),
                    "controls": absolute_rect(cloud_view.findChild(QWidget, "cloudControlsPanel")),
                    "table_panel": absolute_rect(cloud_view.findChild(QWidget, "cloudTablePanel")),
                    "save_table": absolute_rect(cloud_view.save_table),
                    "detail_panel": absolute_rect(cloud_view.detail_panel),
                    "detail_image": absolute_rect(cloud_view.detail_image),
                    "download_cta": absolute_rect(cloud_view.download_button),
                    "upload_cta": absolute_rect(cloud_view.upload_button),
                    "safety_panel": absolute_rect(cloud_view.findChild(QWidget, "cloudSafetyPanel")),
                }
            elif name == "05-history":
                history_view = window.history_reference_view
                screen_rects = {
                    "game_rail": absolute_rect(history_view.findChild(QWidget, "historyGameRail")),
                    "workspace": absolute_rect(history_view.findChild(QWidget, "historyWorkspace")),
                    "table_panel": absolute_rect(history_view.table_panel),
                    "source_filter": absolute_rect(history_view.source_filter_edit),
                    "table": absolute_rect(history_view.table),
                    "detail_panel": absolute_rect(history_view.detail_panel),
                    "detail_image": absolute_rect(history_view.detail_image),
                    "preview_cta": absolute_rect(history_view.preview_button),
                    "restore_cta": absolute_rect(history_view.restore_button),
                    "restore_in_place_cta": absolute_rect(history_view.restore_in_place_button),
                }
            elif name == "06-character":
                character_view = window.character_view
                screen_rects = {
                    "game_rail": absolute_rect(character_view.findChild(QWidget, "characterGameRail")),
                    "workspace": absolute_rect(character_view.findChild(QWidget, "characterWorkspace")),
                    "profile_panel": absolute_rect(character_view.findChild(QWidget, "characterProfilePanel")),
                    "relations_panel": absolute_rect(character_view.findChild(QWidget, "characterRelationsPanel")),
                    "faction_table": absolute_rect(character_view.faction_table),
                    "warning": absolute_rect(character_view.warning_label),
                }
            elif name == "07-review":
                review_view = window.save_review_view
                screen_rects = {
                    "modal_card": absolute_rect(window.reference_modal_card),
                    "changes_panel": absolute_rect(review_view.findChild(QWidget, "reviewChangesPanel")),
                    "changes_table": absolute_rect(review_view.changes_table),
                    "pipeline_panel": absolute_rect(review_view.findChild(QWidget, "reviewPipelinePanel")),
                    "confirm_cta": absolute_rect(review_view.confirm_button),
                    "cancel_cta": absolute_rect(review_view.cancel_button),
                }
            elif name == "08-result":
                result_view = window.save_result_view
                screen_rects = {
                    "modal_card": absolute_rect(window.reference_modal_card),
                    "receipt_panel": absolute_rect(result_view.findChild(QWidget, "resultReceiptPanel")),
                    "receipt_table": absolute_rect(result_view.receipt_table),
                    "editor_cta": absolute_rect(result_view.editor_button),
                    "history_cta": absolute_rect(result_view.history_button),
                    "library_cta": absolute_rect(result_view.library_button),
                    "reconcile_cta": absolute_rect(result_view.reconcile_button),
                }
            elif name == "09-unsupported":
                unsupported_view = window.unsupported_view
                screen_rects = {
                    "modal_card": absolute_rect(window.reference_modal_card),
                    "detail_panel": absolute_rect(unsupported_view.detail_panel),
                    "preview_image": absolute_rect(unsupported_view.preview_image),
                    "folder_cta": absolute_rect(unsupported_view.folder_button),
                    "diagnostics_cta": absolute_rect(unsupported_view.diagnostics_button),
                    "library_cta": absolute_rect(unsupported_view.back_button),
                }
            else:
                screen_rects = {
                    "visible_panels": {
                        key: value
                        for key, value in current_named.items()
                        if key.endswith("Panel") and value is not None
                    },
                }
            _ = screen_rects
            captured = rendered[name]
            metrics = {
                "screen": name,
                "reference_source": source_name,
                "reference_kind": reference_kind,
                "viewport": {"width": VIEWPORT.width(), "height": VIEWPORT.height(), "dpr": 1},
                "actual_image": {"width": actual.width(), "height": actual.height()},
                "geometry": {
                    **captured["geometry"],
                },
                "screen_rects": captured["screen_rects"],
                "tokens": {"palette": COLORS, "spacing": SPACING, "typography": TYPOGRAPHY, "font_family": REFERENCE_FONT_FAMILY},
                "comparison": {
                    "mode": "full-canvas-pixel-diff" if name in reference_sources else "board-derived-geometry",
                    "board_panel_rect": _rect(board_rect) if name not in reference_sources else None,
                },
                "diff": diff_stats,
                "data_policy": "review fixture derived from real parser bytes and official release catalog; no live write or remote state used",
            }
            _write_json(target / "metrics.json", metrics)
        window.discovery_controller.wait_for_worker()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
