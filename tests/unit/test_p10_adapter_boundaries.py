"""P10: the command line is an adapter. The engine never imports it, and loading it loads no benchmark code (ARCHITECTURE §19)."""

from __future__ import annotations

import re
import subprocess
import sys

from app.api.cli import REPO_ROOT

APP = REPO_ROOT / "app"
ADAPTER_IMPORT = re.compile(r"^\s*(from\s+app\.api\b|import\s+app\.api\b|from\s+app\s+import\s+api\b)", re.MULTILINE)


def test_no_engine_module_imports_the_command_line():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP)
        if relative.parts[0] == "api":
            continue
        if ADAPTER_IMPORT.search(path.read_text(encoding="utf-8")):
            offenders.append(relative.as_posix())
    assert offenders == []


def test_loading_the_command_line_loads_no_benchmark_module():
    code = "import sys, app.api.cli; print(sorted(name for name in sys.modules if name.startswith('app.benchmark')))"
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=300
    )
    assert completed.stdout.strip() == "[]"
