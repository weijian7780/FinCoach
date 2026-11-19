"""Fix 5 (2026-11-19): settings copied from .env.example load without crashing.

The file is really read (the test checks the loaded value), and the import runs
in a clean subprocess so the developer's own .env or shell cannot hide a bad
example value. No network access is needed.
"""
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]


def test_env_example_values_load_into_config(tmp_path):
    values = {key: value for key, value in dotenv_values(BACKEND / ".env.example").items()
              if value is not None}
    assert values["COACH_RESEARCH_ANSWER_RESERVE_SECONDS"] == "30"

    keep = ("SYSTEMROOT", "SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "HOME", "USERPROFILE")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update(values)
    env["PYTHONPATH"] = str(BACKEND)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c",
         "import app.config as c; print(c.COACH_RESEARCH_ANSWER_RESERVE_SECONDS)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert completed.stdout.strip().splitlines()[-1] == "30.0"
