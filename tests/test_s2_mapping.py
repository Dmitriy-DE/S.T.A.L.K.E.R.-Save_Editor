from __future__ import annotations

import hashlib

import pytest

import save_format as sf
from editor.s2_mapping import analyze_s2_samples


def _with_type_key(data: bytes, handle: int, type_key: bytes) -> bytes:
    raw = bytearray(sf.decompress_save(data))
    record_offset, _count, _weight, _kind = sf.locate_object_record(raw, handle)
    raw[record_offset + 8 : record_offset + 11] = type_key
    return sf.rebuild_uncompressed(bytes(raw))


def test_s2_mapping_report_keeps_type_key_opaque_and_detects_changes(
    synthetic_save: bytes,
) -> None:
    changed = _with_type_key(synthetic_save, 0x30000001, b"\x09\x08\x07")

    report = analyze_s2_samples(
        {
            "save-a": synthetic_save,
            "save-b": changed,
        }
    )

    assert report.mapping_status == "unconfirmed"
    assert report.sample_count == 2
    assert report.samples[0].sha256 == hashlib.sha256(synthetic_save).hexdigest()
    comparison = next(
        item for item in report.shared_handles if item.handle == 0x30000001
    )
    assert comparison.stable_type_key is False
    assert [item.type_key for item in comparison.observations] == [
        "010203",
        "090807",
    ]
    assert report.reused_type_keys == ()
    assert report.mapping_reason


def test_s2_mapping_report_records_key_reuse_without_assigning_a_sid(
    synthetic_save: bytes,
) -> None:
    raw = bytearray(sf.decompress_save(synthetic_save))
    first_offset, _count, _weight, _kind = sf.locate_object_record(raw, 0x30000001)
    second_offset, _count, _weight, _kind = sf.locate_object_record(raw, 0x30000002)
    raw[second_offset + 8 : second_offset + 11] = raw[first_offset + 8 : first_offset + 11]
    reused = sf.rebuild_uncompressed(bytes(raw))

    report = analyze_s2_samples({"save-a": synthetic_save, "save-b": reused})

    assert report.reused_type_keys == (("010203", (0x30000001, 0x30000002)),)
    assert report.mapping_status == "unconfirmed"
    assert report.shared_handles[0].observations[0].type_key == "010203"


def test_s2_mapping_rejects_duplicate_sample_labels(synthetic_save: bytes) -> None:
    with pytest.raises(ValueError, match="sample label"):
        analyze_s2_samples((("same", synthetic_save), ("same", synthetic_save)))
