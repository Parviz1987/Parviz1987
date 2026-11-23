"""The browser scripts must at least parse: a syntax error blanks the whole panel."""
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "static"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("js", sorted(p.name for p in STATIC.glob("*.js")))
def test_script_parses(js):
    r = subprocess.run(["node", "--check", str(STATIC / js)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
