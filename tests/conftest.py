"""Shared helpers. Skill scripts run through `uv run`, exactly as an agent runs them."""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class Result:
    def __init__(self, proc):
        self.code, self.out, self.err = proc.returncode, proc.stdout, proc.stderr

    def json(self):
        return json.loads(self.out)


def run_script(script, *args, cwd=None, timeout=300):
    """Run a skill script by absolute path from `cwd`, the way SKILL.md instructs."""
    proc = subprocess.run(
        ["uv", "run", "-q", str(ROOT / script), *map(str, args)],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )
    return Result(proc)


@pytest.fixture
def run(tmp_path):
    def _run(script, *args, **kwargs):
        kwargs.setdefault("cwd", tmp_path)
        return run_script(script, *args, **kwargs)

    return _run
