from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is required for browser bootstrap tests")
def test_browser_bootstrap_javascript_runtime() -> None:
    subprocess.run(
        [NODE, "--test", "tests/js/web-bootstrap.test.mjs"],
        cwd=ROOT,
        check=True,
    )


def test_browser_app_integrates_deferred_catalog_bootstrap() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert 'from "./bootstrap.js"' in script
    assert "catalogsReady: null" in script
    assert "await state.catalogsReady" in script
    assert 'rel="modulepreload" href="bootstrap.js"' in html
