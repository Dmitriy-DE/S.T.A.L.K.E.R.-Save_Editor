"""Render deterministic desktop UI review artifacts from the canonical Qt shell.

The reference images are used only as comparison inputs.  The actual images are
always produced by the application widgets and the normal stylesheet/assets.
"""

from __future__ import annotations

import argparse
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

from PySide6.QtCore import QEvent, QPoint, QRect, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from editor.capabilities import FormatCapabilities
from editor.catalog_bundle import load_catalog_file
from editor.formats import STALKER2_FORMAT, STALKER_COP_FORMAT, formats
from editor.releases import release_by_id
from editor.service import EditorService
from editor.storage import BackupRecord, ExportReceipt
from editor.xray_save import COP_FORMAT, XRAY_FORMATS, inspect_xray
from save_format import inspect_save
from steam_cloud import CloudFile
from ui.fonts import REFERENCE_FONT_FAMILY
from ui.main_window import LocalSnapshot, MainWindow
from ui.save_discovery import SaveDiscovery, SaveSlot, UnsupportedSaveReason
from ui.theme import COLORS, SPACING, TYPOGRAPHY

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "ui-review"
VIEWPORT = QSize(1586, 992)
DEFAULT_REFERENCE_DIR = ROOT / "tools" / "ui_review" / "references"


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
            "search_control": _absolute_rect(window, view.search_edit),
            "sort_control": _absolute_rect(window, view.sort_combo),
            "save_table": _absolute_rect(window, view.save_table),
            "preview_panel": _absolute_rect(window, view.preview_panel),
            "preview_scroll": _absolute_rect(window, view.preview_scroll),
            "preview_image": _absolute_rect(window, view.preview_image),
            "preview_name": _absolute_rect(window, view.preview_name),
            "preview_metadata": _absolute_rect(window, view.preview_metadata),
            "capability_heading": _absolute_rect(window, view.capability_heading),
            "summary_heading": _absolute_rect(window, view.summary_heading),
            "quick_summary": _absolute_rect(window, view.quick_summary),
            "recent_activity": _absolute_rect(window, view.recent_activity),
            "activity_table": _absolute_rect(window, view.activity_table),
            "open_cta": _absolute_rect(window, view.open_button),
            "import_cta": _absolute_rect(window, view.import_button),
            "refresh_cta": _absolute_rect(window, view.refresh_button),
            "restore_cta": _absolute_rect(window, view.restore_button),
        }
    elif name == "02-editor":
        view = window.editor_view
        inventory_model = view.table.model()
        first_row_rect: QRect | None = None
        if inventory_model is not None and inventory_model.rowCount() > 0:
            first_index = inventory_model.index(0, 0)
            first_row_viewport_rect = view.table.visualRect(first_index)
            viewport_origin = view.table.viewport().mapTo(window, QPoint(0, 0))
            first_row_rect = QRect(
                viewport_origin + first_row_viewport_rect.topLeft(),
                first_row_viewport_rect.size(),
            )
        screen_rects = {
            "back_button": _absolute_rect(window, view.back_button),
            "breadcrumb_separator": _absolute_rect(window, view.breadcrumb_separator),
            "breadcrumb": _absolute_rect(window, view.breadcrumb),
            "status_equipment_column": _absolute_rect(window, view.status_column),
            "save_status_header": _absolute_rect(
                window,
                view.status_column.findChildren(QWidget, "sectionHeader")[0],
            ),
            "equipment_header": _absolute_rect(window, view.equipment_section_header),
            "equipment_scroll": _absolute_rect(window, view.equipment_scroll),
            "equipment_viewport": _absolute_rect(window, view.equipment_scroll.viewport()),
            "artifact_heading": _absolute_rect(window, view.artifact_heading),
            "money_icon": _absolute_rect(window, view.money_icon),
            "money_field": _absolute_rect(window, view.money_spin),
            "weight_icon": _absolute_rect(window, view.weight_icon),
            "weight_value": _absolute_rect(window, view.weight_label),
            "inventory_column": _absolute_rect(window, view.inventory_column),
            "inventory_table": _absolute_rect(window, view.table),
            "inventory_header": _absolute_rect(window, view.table.horizontalHeader()),
            "inventory_first_row": _rect(first_row_rect) if first_row_rect is not None else None,
            "detail_column": _absolute_rect(window, view.detail_column),
            "detail_scroll": _absolute_rect(window, view.detail_view.detail_scroll),
            "detail_viewport": _absolute_rect(
                window, view.detail_view.detail_scroll.viewport()
            ),
            "detail_header": _absolute_rect(window, view.detail_view.findChild(QWidget, "detailHeader")),
            "detail_name": _absolute_rect(window, view.detail_view.name_label),
            "detail_type": _absolute_rect(window, view.detail_view.type_label),
            "detail_image": _absolute_rect(window, view.detail_view.image_label),
            "detail_description": _absolute_rect(window, view.detail_view.description_label),
            "detail_tabs": [
                _absolute_rect(window, button) for button in view.detail_view.detail_tabs
            ],
            "detail_fields": _absolute_rect(window, view.detail_view.findChild(QWidget, "detailFields")),
            "detail_upgrades": _absolute_rect(window, view.detail_view.upgrade_list),
            "detail_upgrades_heading": _absolute_rect(
                window, view.detail_view.upgrade_heading
            ),
            "equipment_cards": [
                _absolute_rect(window, row)
                for row in view.status_column.findChildren(QWidget, "equipmentSlot")
                if row.isVisible()
            ],
            "artifact_strip": [
                _absolute_rect(window, button)
                for button in view.status_column.findChildren(QWidget, "artifactSlot")
                if button.isVisible()
            ],
            "save_cta": _absolute_rect(window, view.save_button),
            "reset_cta": _absolute_rect(window, view.detail_view.reset_button),
            "remove_cta": _absolute_rect(window, view.detail_view.remove_button),
        }
    elif name == "03-settings":
        view = window.settings_reference_view
        screen_rects = {
            "category_rail": _absolute_rect(window, view.findChild(QWidget, "settingsCategoryRail")),
            "category_buttons": [
                _absolute_rect(window, button) for button in view.category_buttons
            ],
            "content": _absolute_rect(window, view.settings_content),
            "settings_scroll": _absolute_rect(window, view.settings_scroll),
            "settings_viewport": _absolute_rect(
                window, view.settings_scroll.viewport()
            ),
            "visible_panels": {
                page.objectName(): _absolute_rect(window, page)
                for page in view._settings_pages
                if page.isVisible()
            },
            "save_cta": _absolute_rect(window, view.save_button),
            "cancel_cta": _absolute_rect(window, view.cancel_button),
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
            "detail_scroll": _absolute_rect(window, view.detail_scroll),
            "detail_image": _absolute_rect(window, view.detail_image),
            "detail_name": _absolute_rect(window, view.detail_name),
            "detail_meta": _absolute_rect(window, view.detail_meta),
            "read_only_banner": _absolute_rect(window, view.read_only_banner),
            "download_cta": _absolute_rect(window, view.download_button),
            "upload_cta": _absolute_rect(window, view.upload_button),
            "result_label": _absolute_rect(window, view.result_label),
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
            "detail_name": _absolute_rect(window, view.detail_name),
            "detail_status": _absolute_rect(window, view.detail_status),
            "destination_field": _absolute_rect(window, view.destination_edit),
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
        "channel_delta_tolerance": 12,
        "changed_pixels": changed,
        "changed_pixel_ratio": round(changed / pixels, 6) if pixels else 0.0,
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


def _review_library_slots(directory: Path, local: LocalSnapshot) -> tuple[SaveSlot, ...]:
    """Create deterministic rows whose metadata matches their registered bytes."""

    names = (
        "99457897416AC2273A59B826C7F6306.sav",
        "Pripyat_quicksave.sav",
        "autosave_12.sav",
        "bar_100.sav",
        "slot_ee.sav",
        "manual_save.sav",
        "escape.sav",
    )
    families = ("stalker2", "cop", "clear_sky", "soc", "soc", "stalker2", "clear_sky")
    times = (
        datetime(2026, 9, 23, 0, 18),
        datetime(2026, 9, 22, 23, 41),
        datetime(2026, 9, 21, 18, 13),
        datetime(2026, 9, 18, 16, 3),
        datetime(2026, 9, 17, 12, 31),
        datetime(2026, 9, 14, 20, 24),
        datetime(2026, 9, 12, 11, 10),
    )
    sizes = tuple(int(value * 1024 * 1024) for value in (15.6, 6.5, 6.8, 5.9, 7.3, 8.1, 4.2))
    enhanced = release_by_id("stalker-soc-ee")
    formats_by_family = {
        release_by_id(format_.release_id).family: format_
        for format_ in formats()
    }
    slots: list[SaveSlot] = []
    for name, family, modified, size in zip(names, families, times, sizes, strict=True):
        is_enhanced_candidate = name == "slot_ee.sav"
        format_ = formats_by_family[family]
        release = release_by_id(format_.release_id)
        slots.append(
            SaveSlot(
                path=directory / name,
                candidate_game_id=family,
                candidate_game_title=(enhanced.title if is_enhanced_candidate else release.title),
                size=size,
                modified_ns=int(modified.timestamp() * 1_000_000_000),
                format_id=None if is_enhanced_candidate else format_.id,
                format_title=None if is_enhanced_candidate else format_.title,
                candidate_release_id=(
                    enhanced.id if is_enhanced_candidate else format_.release_id
                ),
                detected_release_id=(
                    None if is_enhanced_candidate else format_.release_id
                ),
                unsupported_reason=(
                    UnsupportedSaveReason(
                        "unsupported_release",
                        "Найден официальный сейв Enhanced Edition, но его формат не поддерживается",
                    )
                    if is_enhanced_candidate
                    else None
                ),
            )
        )
    return tuple(slots)


def _review_library_payload(slot: SaveSlot, local: LocalSnapshot) -> bytes:
    """Create parser-valid review bytes for the row's release descriptor."""

    enhanced_id = release_by_id("stalker-soc-ee").id
    if slot.candidate_release_id == enhanced_id:
        marker = b"STALKER-EE-REVIEW-CANDIDATE\x00"
        return marker + bytes(max(0, slot.size - len(marker)))
    if slot.detected_release_id == local.release_id:
        return local.data
    return _xray_fixture_bytes(slot.detected_release_id or "")


def _review_cloud_files(size: int) -> tuple[CloudFile, ...]:
    """Return a populated, deterministic list without touching Steam Cloud."""

    names = (
        "auto_save_12.sav",
        "quicksave.sav",
        "manual_save.sav",
        "slot_004.sav",
        "auto_save_11.sav",
        "escape.sav",
        "quicksave_03.sav",
        "slot_008.sav",
    )
    base_time = datetime(2026, 9, 23, 12, 20)
    return tuple(
        CloudFile(
            name=f"Stalker2/Saved/Steam/{name}",
            size=size + index * 256 * 1024,
            timestamp=int((base_time.replace(minute=20 + index)).timestamp()),
            is_persisted=True,
            exists=True,
            source="native_remote_storage",
        )
        for index, name in enumerate(names, start=1)
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


def _xray_fixture_bytes(release_id: str = COP_FORMAT.id) -> bytes:
    namespace = runpy.run_path(str(ROOT / "tests" / "test_xray_save.py"))
    spec = next(spec for spec in XRAY_FORMATS if spec.id == release_id)
    return namespace["_fixture"](
        min(spec.actor_versions),
        min(spec.outer_versions),
    )


def _review_inventory(info, catalog_bundle):
    """Expand one real X-Ray observation with official-catalog review rows."""

    base = info.inventory[0]
    keys = (
        "mp_wpn_ak74",
        "mp_wpn_toz34",
        "cs_heavy_outfit",
        "helm_respirator",
        "detector_advanced",
        "ammo_9x39_pab9",
        "ammo_5.45x39_fmj",
        "medkit",
        "bandage",
        "bread",
        "energy_drink",
        "af_gravi",
        "af_cristall",
        "af_electra_sparkler",
        "zat_b33_safe_container",
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
    presentation_counts = {
        "ammo_9x39_pab9": 120,
        "ammo_5.45x39_fmj": 300,
        "medkit": 5,
        "bandage": 12,
        "bread": 7,
        "energy_drink": 4,
    }
    rows = []
    for index, key in enumerate(review_keys, start=1):
        definition = catalog_bundle.items.resolve(key)
        if definition is None:
            continue
        category = forced_categories.get(key, definition.category or "other")
        count = presentation_counts.get(
            key,
            30 if category == "ammo" else (5 if category == "consumable" else 1),
        )
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


def _prepare_window(
    app: QApplication,
    raw: bytes,
    directory: Path,
    *,
    show_window: bool = True,
) -> tuple[MainWindow, LocalSnapshot, LocalSnapshot]:
    def empty_discovery() -> SaveDiscovery:
        return SaveDiscovery((), (directory,))

    window = MainWindow(EditorService(), slot_discovery=empty_discovery, auto_update_check=False)
    window.resize(VIEWPORT)
    if show_window:
        window.show()
    app.processEvents()
    if not window.discovery_controller.wait_for_worker():
        raise RuntimeError("save discovery did not stop before preparing review fixtures")
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
    slots = _review_library_slots(directory, local)
    for slot in slots:
        slot.path.write_bytes(_review_library_payload(slot, local))
    window.library_view.set_discovery(SaveDiscovery(slots, (directory,)))
    window._render_snapshot(local)
    review_records: list[BackupRecord] = []
    raw_sha = hashlib.sha256(raw).hexdigest()
    for index in range(1, 9):
        backup_path = directory / f"review-backup-{index}.sav"
        journal_path = directory / f"journal-{index}.json"
        backup_path.write_bytes(raw)
        journal_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "status": "verified",
                    "created_at": f"2026-09-23 00:{index:02d}:00",
                    "source_path": str(slots[(index - 1) % len(slots)].path),
                    "source_sha256": raw_sha,
                    "output_path": str(slots[(index - 1) % len(slots)].path),
                    "output_sha256": raw_sha,
                    "backup_path": backup_path.name,
                    "operation": {
                        "mode": "replace" if index % 2 else "restore",
                        "stack_count": index % 3,
                        "money": 9999999 if index == 1 else None,
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        review_records.append(
            BackupRecord(
                journal_path=journal_path,
                backup_path=backup_path,
                created_at=f"2026-09-23 00:{index:02d}:00",
                source_path=str(slots[(index - 1) % len(slots)].path),
                source_sha256=raw_sha,
                output_path=str(slots[(index - 1) % len(slots)].path),
                output_sha256=raw_sha,
                operation={
                    "mode": "replace" if index % 2 else "restore",
                    "stack_count": index % 3,
                    "money": 9999999 if index == 1 else None,
                },
                status="verified",
                actual_sha256=raw_sha,
            )
        )
    window.backup_controller.set_review_records(tuple(review_records))
    window.library_view.set_recent_activity(
        tuple(
            (
                "Резервная копия",
                Path(record.source_path).name,
                record.created_at,
                "Проверено" if record.status == "verified" else record.status,
            )
            for record in review_records[-3:]
        )
    )
    cloud_files = _review_cloud_files(15_600_000)
    window.cloud_controller.set_review_files(
        cloud_files,
        status=f"Steam Cloud: демосписок · {len(cloud_files)} файлов",
    )
    window.history_reference_view._render()
    if window.cloud_reference_view.save_table.rowCount():
        window.cloud_reference_view.save_table.selectRow(0)
    if window.history_reference_view.table.rowCount():
        window.history_reference_view.table.selectRow(0)
        window.history_reference_view.preview_selected()
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
            settings_view = window.settings_reference_view
            # Presentation-only canonical values: these edit widgets in the
            # temporary renderer process only. They are never saved and do
            # not assert that the host has a Steam client or an active Cloud
            # session.
            settings_view.steam_root_edit.setText("/home/dmytro/.steam/steam")
            settings_view.catalog_root_edit.setText(
                "Не найдено — использовать автопоиск"
            )
            settings_view.steam_hint.setText("●  НАЙДЕНО")
            settings_view.steam_hint.setProperty("discoveryState", "found")
            settings_view.catalog_hint.setText("●  НЕОБЯЗАТЕЛЬНО")
            settings_view.catalog_hint.setProperty("discoveryState", "optional")
            for hint in (settings_view.steam_hint, settings_view.catalog_hint):
                hint.style().unpolish(hint)
                hint.style().polish(hint)
            backup_path = settings_view.findChild(QLabel, "settingsBackupPathValue")
            if backup_path is not None:
                backup_path.setText(
                    "~/.local/share/StalkerSaveEditor/backups"
                )
            cloud_status = settings_view.findChild(
                QLabel, "settingsCloudConnectionValue"
            )
            if cloud_status is not None:
                cloud_status.setText("●  Доступно")
                cloud_status.setProperty("reviewAvailable", "true")
                cloud_status.style().unpolish(cloud_status)
                cloud_status.style().polish(cloud_status)
        elif widget_name == "cloud_reference_view":
            window._show_cloud()
        elif widget_name == "history_reference_view":
            window._show_history()
        elif widget_name == "character_view":
            window._render_snapshot(xray, show_editor=False)
            window._show_character_state()
        elif widget_name == "save_review_view":
            # Exercise the real review builder with a deterministic in-memory
            # draft; the fixture is never confirmed and no save bytes are
            # written by this visual-review path.
            window._render_snapshot(xray, show_editor=False)
            window._show_reference_editor()
            inventory = xray.info.inventory
            rifle = next(item for item in inventory if item.type_key == "mp_wpn_ak74")
            stack_item = next(item for item in inventory if item.type_key == "bandage")
            assert xray.info.money is not None
            assert stack_item.count is not None
            window._stage_money(xray.info.money + 1)
            window._stage_stack_change(stack_item.handle, stack_item.count - 1)
            window._stage_item_durability(rifle.handle, 0.92)
            assert stack_item.handle in window.staged_counts
            assert rifle.handle in window.staged_durability
            assert window.staged_money == xray.info.money + 1
            window._request_reference_save()
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
        if widget_name == "editor_view":
            # A second snapshot rebuild schedules the previous equipment-card
            # widgets for deferred deletion. Flush only those delete events so
            # the captured geometry contains the live cards, not stale rows.
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        QApplication.processEvents()
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-dir",
        type=Path,
        default=DEFAULT_REFERENCE_DIR,
        help="directory containing the four canonical reference images",
    )
    return parser.parse_args(argv)


def main(reference_dir: Path | None = None) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PYTEST_CURRENT_TEST", "ui-review")
    reference_dir = Path(reference_dir or DEFAULT_REFERENCE_DIR).expanduser().resolve()
    if not reference_dir.is_dir():
        raise SystemExit(f"canonical reference directory does not exist: {reference_dir}")
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
            "01-library": reference_dir / "01_LIBRARY_CANONICAL.png",
            "02-editor": reference_dir / "02_EDITOR_CANONICAL.png",
            "03-settings": reference_dir / "03_SETTINGS_CANONICAL.png",
        }
        board_source = reference_dir / "04_REMAINING_STATES_BOARD_CANONICAL.png"
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
            captured = rendered[name]
            metrics = {
                "screen": name,
                "reference_source": source_name,
                "reference_kind": reference_kind,
                "viewport": {
                    "width": VIEWPORT.width(),
                    "height": VIEWPORT.height(),
                    "dpr": round(window.devicePixelRatioF(), 2),
                },
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
                "data_policy": "review saves use parser-valid registered-format fixtures and official release metadata; displayed dates and sizes are deterministic visual fixture values; Cloud rows are a demo list with no live connection/read/write; Settings values are temporary",
            }
            _write_json(target / "metrics.json", metrics)
        window.discovery_controller.wait_for_worker()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main(_parse_args().reference_dir)
