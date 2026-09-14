import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS_DIR / "test.yml"
BUILD_WORKFLOW = WORKFLOWS_DIR / "build.yml"

# Runner images GitHub still hosts.  A run that names a retired label fails at
# startup before any job is created, so a stale label here is indistinguishable
# from a broken workflow in the Actions UI.
SUPPORTED_RUNNER_LABELS = frozenset(
    {
        "ubuntu-24.04",
        "ubuntu-latest",
        "windows-2025",
        "windows-latest",
    }
)
RETIRED_RUNNER_LABELS = frozenset({"ubuntu-20.04", "ubuntu-22.04", "windows-2019", "windows-2022"})
_RUNNER_LABEL_RE = re.compile(r"^\s*-?\s*os:\s*(\S+)\s*$", re.MULTILINE)


def _declared_runner_labels(path: Path) -> set[str]:
    return {
        match.group(1)
        for match in _RUNNER_LABEL_RE.finditer(path.read_text(encoding="utf-8"))
    }


def test_ci_matrix_covers_supported_platforms_and_pythons() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    labels = _declared_runner_labels(WORKFLOW)

    assert any(label.startswith("ubuntu") for label in labels)
    assert any(label.startswith("windows") for label in labels)
    assert "3.11" in text
    assert "3.12" in text
    assert "fail-fast: false" in text
    assert "continue-on-error" not in text


def test_every_workflow_names_a_hosted_runner_image() -> None:
    for path in (WORKFLOW, BUILD_WORKFLOW):
        labels = _declared_runner_labels(path)
        assert labels, f"{path.name} declares no runner labels"
        assert not labels & RETIRED_RUNNER_LABELS, (
            f"{path.name} names retired runner images: "
            f"{sorted(labels & RETIRED_RUNNER_LABELS)}"
        )
        assert labels <= SUPPORTED_RUNNER_LABELS, (
            f"{path.name} names unknown runner images: "
            f"{sorted(labels - SUPPORTED_RUNNER_LABELS)}"
        )


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
    assert "py_compile" in text


def test_ci_runs_the_static_analysis_gate() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '"ruff"' in text
    assert '"mypy"' in text
    assert (ROOT / "ruff.toml").is_file()
    assert (ROOT / "mypy.ini").is_file()


def test_ci_runs_the_qt_suite_headless() -> None:
    for path in (WORKFLOW, BUILD_WORKFLOW):
        text = path.read_text(encoding="utf-8")
        # PySide6 is a runtime dependency, so the UI suite runs on the runners.
        # Without an offscreen platform plugin and the Qt system libraries the
        # job fails on a missing display rather than on a real defect.
        assert "QT_QPA_PLATFORM: offscreen" in text, f"{path.name} runs Qt with no platform plugin"
        assert "libegl1" in text, f"{path.name} does not install the Qt runtime libraries"


def test_python_shell_steps_actually_contain_python() -> None:
    """A `shell: python` step whose body is a shell command dies at runtime.

    The compile step shipped as `shell: python` with `run: python -m py_compile …`,
    which the runner fed to the interpreter as source and rejected as a
    SyntaxError.  Nothing caught it for months because no run ever got that far.
    """

    import ast

    import yaml

    for path in (WORKFLOW, BUILD_WORKFLOW):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if step.get("shell") != "python":
                    continue
                body = step.get("run", "")
                try:
                    ast.parse(body)
                except SyntaxError as exc:  # pragma: no cover - failure path
                    raise AssertionError(
                        f"{path.name}:{job_name}: step {step.get('name')!r} declares "
                        f"shell: python but its body is not Python ({exc.msg})"
                    ) from exc
