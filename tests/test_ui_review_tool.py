import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from editor.formats import detect
from editor.releases import release_by_id
from editor.service import EditorService
from tools import build_ui_review_decorations, render_ui_review
from tools.render_ui_review import (
    ROOT,
    _parse_args,
    _review_cloud_files,
    _review_library_payload,
    _review_library_slots,
    _snapshot,
)
from ui.library_view import LibraryView
from ui.main_window import MainWindow
from ui.save_discovery import SaveDiscovery


@pytest.fixture(scope="module")
def review_output(tmp_path_factory: pytest.TempPathFactory, qapp) -> Path:
    """Render the review screens from the current code into a temp dir.

    The tests used to read metrics.json files committed next to the code,
    so they kept passing whatever the UI actually rendered.
    """

    del qapp
    output = tmp_path_factory.mktemp("ui-review")
    with pytest.MonkeyPatch.context() as patch:
        from PySide6.QtWidgets import QMessageBox

        patch.setattr(render_ui_review, "OUTPUT", output)
        patch.setattr(
            QMessageBox,
            "question",
            staticmethod(lambda *_a, **_k: QMessageBox.StandardButton.No),
        )
        render_ui_review.main()
    return output


def _near(actual: int, expected: int, tolerance: int = 2) -> bool:
    """Vertical anchors move by a pixel between Linux and Windows fonts."""

    return abs(actual - expected) <= tolerance


def _metrics(output: Path, screen: str) -> dict:
    return json.loads((output / screen / "metrics.json").read_text(encoding="utf-8"))


def test_review_renderer_uses_repo_local_reference_assets_by_default() -> None:
    args = _parse_args([])

    assert args.reference_dir == ROOT / "tools" / "ui_review" / "references"


def test_review_renderer_accepts_an_explicit_reference_directory(tmp_path: Path) -> None:
    args = _parse_args(["--reference-dir", str(tmp_path)])

    assert args.reference_dir == tmp_path


def test_library_review_fixture_uses_the_official_enhanced_candidate(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    descriptor = release_by_id("stalker-soc-ee")
    slots = _review_library_slots(
        tmp_path,
        _snapshot(synthetic_save, tmp_path),
    )
    candidate = next(slot for slot in slots if slot.path.name == "slot_ee.sav")

    assert candidate.candidate_release_id == descriptor.id
    assert candidate.candidate_game_title == descriptor.title
    assert candidate.format_id is None
    assert candidate.detected_release_id is None
    assert candidate.unsupported_reason is not None
    assert candidate.unsupported_reason.code == "unsupported_release"


def test_library_review_slots_match_the_bytes_detected_by_registered_formats(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    local = _snapshot(synthetic_save, tmp_path)
    slots = _review_library_slots(tmp_path, local)

    for slot in slots:
        payload = _review_library_payload(slot, local)
        detected = detect(payload)
        if slot.candidate_release_id == release_by_id("stalker-soc-ee").id:
            assert detected is None
            assert slot.detected_release_id is None
        else:
            assert detected is not None
            assert slot.detected_release_id == detected.release_id
            assert slot.format_id == detected.id


def test_library_save_rows_separate_filename_from_release_subtitle(
    qtbot, synthetic_save: bytes, tmp_path: Path
) -> None:
    local = _snapshot(synthetic_save, tmp_path)
    slots = _review_library_slots(tmp_path, local)
    view = LibraryView()
    qtbot.addWidget(view)
    view.set_discovery(SaveDiscovery(slots, (tmp_path,)))

    s2_cell = view.save_table.cellWidget(0, 0)
    cop_cell = view.save_table.cellWidget(1, 0)

    assert s2_cell is not None and cop_cell is not None
    assert view.save_table.item(0, 0).text() == ""
    title = s2_cell.findChild(QLabel, "libraryRowTitle")
    # Long GUID names are elided in the middle; the full name stays reachable.
    assert title.toolTip() == slots[0].path.name
    head, _, tail = title.text().partition("…")
    assert slots[0].path.stem.startswith(head) and slots[0].path.stem.endswith(tail)
    assert s2_cell.findChild(QLabel, "libraryRowSubtitle").text() == "S.T.A.L.K.E.R. 2"
    assert cop_cell.findChild(QLabel, "libraryRowSubtitle").text() == "Быстрое сохранение"
    assert s2_cell.property("selected") is True
    assert s2_cell.findChild(QLabel, "libraryRowTitle").property("rowSelected") is True

    view.save_table.selectRow(1)

    assert s2_cell.property("selected") is False
    assert cop_cell.property("selected") is True
    assert s2_cell.findChild(QLabel, "libraryRowTitle").property("rowSelected") is False
    assert cop_cell.findChild(QLabel, "libraryRowTitle").property("rowSelected") is True


def test_library_review_rows_use_multiple_bundled_zone_illustrations(
    synthetic_save: bytes, tmp_path: Path
) -> None:
    slots = _review_library_slots(tmp_path, _snapshot(synthetic_save, tmp_path))
    art_paths = {LibraryView._thumbnail_art_path(slot) for slot in slots}

    assert len(art_paths) >= 3
    assert all(path.is_file() for path in art_paths)


def test_cloud_review_fixture_fills_the_reference_list_without_live_state() -> None:
    files = _review_cloud_files(15_600_000)

    assert len(files) == 8
    assert files[0].name == "Stalker2/Saved/Steam/auto_save_12.sav"
    assert files[-1].name == "Stalker2/Saved/Steam/slot_008.sav"
    assert all(file.exists and file.is_persisted for file in files)
    assert {file.source for file in files} == {"native_remote_storage"}
    assert len({file.timestamp for file in files}) == len(files)


def test_cloud_review_table_uses_populated_canonical_height_rows(qtbot) -> None:
    window = MainWindow(EditorService(), auto_update_check=False)
    qtbot.addWidget(window)
    files = _review_cloud_files(15_600_000)

    window.cloud_controller.set_review_files(
        files,
        status=f"Steam Cloud: демосписок · {len(files)} файлов",
    )

    table = window.cloud_reference_view.save_table
    assert table.rowCount() == 8
    assert table.rowHeight(0) == 58
    assert table.item(7, 0).text() == "slot_008.sav"
    assert table.item(0, 1).text() == "15.1 МБ"


@pytest.mark.parametrize(
    ("screen", "required_rects"),
    (
        (
            "01-library",
            {"game_rail", "centre", "save_table", "preview_panel", "recent_activity", "open_cta"},
        ),
        (
            "02-editor",
            {"status_equipment_column", "inventory_column", "inventory_table", "detail_column", "save_cta"},
        ),
        ("03-settings", {"category_rail", "content", "visible_panels", "save_cta"}),
    ),
)
def test_primary_review_metrics_report_canvas_and_layout_evidence(
    screen: str,
    required_rects: set[str],
    review_output: Path,
) -> None:
    metrics = _metrics(review_output, screen)

    assert metrics["comparison"]["mode"] == "full-canvas-pixel-diff"
    assert 0.0 <= metrics["diff"]["changed_pixel_ratio"] <= 1.0
    assert metrics["diff"]["channel_delta_tolerance"] == 12
    assert metrics["diff"]["width"] > 0
    assert metrics["diff"]["height"] > 0
    assert required_rects <= metrics["screen_rects"].keys()


def test_editor_review_metrics_track_visible_equipment_rows_and_breadcrumb(review_output: Path) -> None:
    metrics = _metrics(review_output, "02-editor")
    rects = metrics["screen_rects"]
    cards = rects["equipment_cards"]

    # The fixture's loadout: two weapons, a helmet and a detector.
    assert len(cards) == 4
    assert len({(card["x"], card["y"]) for card in cards}) == 4
    assert {"back_button", "breadcrumb_separator", "breadcrumb"} <= rects.keys()
    assert _near(rects["back_button"]["y"], 130)
    assert rects["status_equipment_column"] == {
        "x": 24,
        "y": 173,
        "width": 362,
        "height": 757,
    }


def test_editor_review_metrics_keep_detail_stack_on_the_canonical_anchors(review_output: Path) -> None:
    metrics = _metrics(review_output, "02-editor")
    rects = metrics["screen_rects"]

    assert _near(rects["detail_header"]["y"], 174)
    assert rects["detail_header"]["height"] == 40
    assert _near(rects["detail_name"]["y"], 218)
    assert _near(rects["detail_type"]["y"], 262)
    assert _near(rects["detail_image"]["y"], 281)
    # Description moved into the "ХАРАКТЕРИСТИКИ" tab; tabs follow the art.
    assert _near(rects["detail_tabs"][0]["y"], 379)
    assert _near(rects["detail_fields"]["y"], 429)
    assert _near(rects["save_cta"]["y"], 829)


def test_editor_review_metrics_place_equipment_title_above_canonical_cards(review_output: Path) -> None:
    metrics = _metrics(review_output, "02-editor")
    rects = metrics["screen_rects"]

    assert _near(rects["equipment_header"]["y"], 414)
    assert rects["equipment_header"]["height"] == 31
    assert _near(rects["equipment_cards"][0]["y"], 451)


def test_library_search_and_sort_controls_match_canonical_proportions(review_output: Path) -> None:
    metrics = _metrics(review_output, "01-library")
    rects = metrics["screen_rects"]

    assert rects["sort_control"]["width"] == 204
    assert rects["sort_control"]["x"] == 952
    assert rects["search_control"]["x"] == 307
    assert rects["search_control"]["width"] == 635


def test_editor_inventory_table_starts_at_the_canonical_vertical_anchor(review_output: Path) -> None:
    metrics = _metrics(review_output, "02-editor")

    rects = metrics["screen_rects"]
    assert _near(rects["inventory_table"]["y"], 319)
    assert _near(rects["inventory_header"]["y"], 320)
    assert rects["inventory_header"]["height"] == 34
    assert _near(rects["inventory_first_row"]["y"], 354)


def test_decoration_builder_writes_review_textures_to_its_asset_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(build_ui_review_decorations, "ASSETS", tmp_path)

    build_ui_review_decorations.main()

    assert (tmp_path / "header_panorama.png").is_file()
    assert (tmp_path / "selection_paper.png").is_file()
    assert (tmp_path / "amber_paper.png").is_file()
