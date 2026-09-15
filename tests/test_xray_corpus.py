from __future__ import annotations

import json
from pathlib import Path

from test_xray_save import _fixture

from editor.releases import official_releases
from tools.verify_xray_corpus import verify_corpus


def test_corpus_verifier_reports_aggregate_fixture_evidence_without_paths(
    tmp_path: Path,
) -> None:
    save = tmp_path / "private-name.scop"
    save.write_bytes(_fixture(128, 6))
    roots = {release.id: () for release in official_releases()}
    roots["stalker-cop"] = (tmp_path,)

    result = verify_corpus(roots)
    cop = next(row for row in result["profiles"] if row["release_id"] == "stalker-cop")

    assert cop["candidate_count"] == 1
    assert cop["parsed_count"] == 1
    assert cop["sha_match_count"] == 1
    assert cop["edit_roundtrip_count"] >= 1
    rendered = json.dumps(result, ensure_ascii=False)
    assert "private-name.scop" not in rendered
    assert str(tmp_path) not in rendered
