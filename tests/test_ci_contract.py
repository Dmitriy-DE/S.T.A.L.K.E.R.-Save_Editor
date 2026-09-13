from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "test.yml"


def test_ci_matrix_covers_supported_platforms_and_pythons() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "ubuntu-22.04" in text
    assert "windows-2022" in text
    assert "3.11" in text
    assert "3.12" in text
    assert "fail-fast: false" in text
    assert "continue-on-error" not in text


def test_ci_is_read_only_and_does_not_use_private_inputs() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:" in text
    assert "contents: read" in text
    assert ".local" in text
    assert "*.sav" in text
    assert "upload-artifact" in text
    assert "secrets." not in text
    assert "WriteFile" not in text
    assert "upload_cloud" not in text


def test_ci_runs_pinned_dependencies_and_full_suite() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "requirements.txt" in text
    assert "requirements-dev.txt" in text
    assert '"pytest"' in text
    assert '"tests"' in text
    assert "python -m py_compile" in text
