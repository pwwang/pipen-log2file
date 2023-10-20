"""Test for #1:
Wrong working directory used when a different pipeline name passed via
pipen-args
"""
import sys
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def test_1():
    logfile = Path(".").joinpath(".pipen", "Pipeline2", "run-latest.log")
    logfile.unlink(missing_ok=True)
    cmd = [
        sys.executable,
        str(HERE / "pipeline.py"),
        f"@{HERE.joinpath('pipeline.config.toml')}",
    ]
    p = subprocess.Popen(cmd)
    p.wait()
    assert p.returncode == 0
    assert logfile.exists()
