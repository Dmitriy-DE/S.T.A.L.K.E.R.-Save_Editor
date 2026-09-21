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
_RUNNER_LABEL_RE = re.compile(
    r"^\s*(?:-\s*)?(?:os|runs-on):\s*(?:\$\{\{[^}]+\}\}|[\"']?([^\"'\s]+)[\"']?)\s*$",
    re.MULTILINE,
)


def _declared_runner_labels(path: Path) -> set[str]:
    return {
        match.group(1)
        for match in _RUNNER_LABEL_RE.finditer(path.read_text(encoding="utf-8"))
        if match.group(1)
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


def test_release_packages_run_the_complete_source_gate_before_building() -> None:
    """A tag must not package source that the normal CI matrix rejects."""

    import yaml

    workflow = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    source_gate = workflow["jobs"]["source-gate"]
    linux_package = workflow["jobs"]["package-linux"]
    assert linux_package["needs"] == "source-gate"
    assert linux_package["container"]["image"] == "ubuntu:22.04"
    source_steps = source_gate["steps"]
    body = next(step["run"] for step in source_steps if step.get("name") == "Run complete source gate")
    for required in (
        '"ruff", "check", "."',
        '"mypy"',
        '"tools/render_task_index.py", "--check"',
        '"tools/build_web_bundle.py", "--check"',
        '"tools/export_theme.py", "--check"',
        '"py_compile"',
        '"pytest", "tests", "-q"',
    ):
        assert required in body
    assert any(
        step.get("name") == "Build Linux artifacts against the declared glibc floor"
        for step in linux_package["steps"]
    )


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


def test_release_workflow_collects_native_builds_and_publishes_manifest() -> None:
    text = BUILD_WORKFLOW.read_text(encoding="utf-8")

    assert "download-artifact" in text
    assert "latest.json" in text
    assert "gh release" in text
    assert "--publish-r2" in text
    assert "r2" in (ROOT / "tools" / "publish_release.py").read_text(encoding="utf-8")
    assert "CLOUDFLARE_API_TOKEN" in text
    assert "CLOUDFLARE_ACCOUNT_ID" in text
    assert "contents: write" in text
    assert "wrangler@4 deploy" in text
    assert "infra/downloads-worker/wrangler.toml" in text
    assert "r2 bucket lifecycle set" in text
    assert "infra/downloads-worker/lifecycle.json" in text
    assert "Install Windows installer tool" in text
    assert "Smoke Windows installer" in text
    assert "SaveEditor-windows-x86_64-setup.exe" in text
    assert "appstreamcli validate --no-net --strict" in text
    assert "lintian --no-tag-display-limit --pedantic" in text
    assert "^[EW]:" in text
    assert "SAVE_EDITOR_REQUIRE_GLIBC_BASELINE" in text
    assert "lsb-release" in text
    assert "tools/build_apt_repo.py" in text
    assert "tools/verify_apt_repo.py" in text

    import yaml

    workflow = yaml.safe_load(text)
    linux_steps = workflow["jobs"]["package-linux"]["steps"]
    python_setup = next(step for step in linux_steps if step.get("name") == "Set up Python 3.11")
    assert "cache" not in python_setup["with"]


def test_release_publication_is_atomic_across_r2_and_github() -> None:
    """A tag must never publish GitHub assets when the R2 channel is skipped."""

    import yaml

    workflow = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["release"]["steps"]
    names = [step.get("name") for step in steps]

    credentials_index = names.index("Validate release credentials before external mutations")
    worker_index = names.index("Deploy download Worker")
    prepare_index = names.index("Prepare stable release files")
    apt_index = names.index("Build signed APT repository")
    r2_index = names.index("Publish stable R2 objects and verify read-back")
    apt_verify_index = names.index("Verify public APT update and package discovery")
    github_index = names.index("Create or update GitHub Release")
    assert credentials_index < prepare_index < apt_index < worker_index < r2_index < apt_verify_index < github_index
    assert names.count("Prepare stable release files") == 1
    assert "Warn when R2 credentials are unavailable" not in names

    credential_body = steps[credentials_index]["run"]
    assert "CLOUDFLARE_API_TOKEN" in credential_body
    assert "CLOUDFLARE_ACCOUNT_ID" in credential_body
    assert "APT_SIGNING_KEY" in credential_body
    assert "APT_SIGNING_KEY_ID" in credential_body
    assert ":?" in credential_body
    assert "if" not in steps[worker_index]
    assert "if" not in steps[r2_index]

    r2_body = steps[r2_index]["run"]
    assert "--prepared" in r2_body
    assert "--require-apt" in r2_body
    assert "--artifacts" not in r2_body
    assert "--version" not in r2_body
    assert "--commit" not in r2_body
