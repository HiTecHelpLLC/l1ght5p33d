"""The preserved upstream checkout must not shadow the installed Flow release."""

import subprocess
import sys


def test_module_launcher_uses_isolated_dependencies_and_preserves_failure(tmp_path):
    shadow = tmp_path / "openadapt_flow"
    shadow.mkdir()
    (shadow / "__init__.py").write_text(
        "raise RuntimeError('unqualified source shadow')"
    )
    result = subprocess.run(
        [sys.executable, "-m", "l1ght5p33d", "validate", "missing.json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "unqualified source shadow" not in result.stderr
    assert "missing.json" in result.stderr
