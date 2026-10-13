"""Settings startup checks without database, queue, or paid API access."""
from pathlib import Path
import os
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module", [
    "app/core/config.py",
    "services/match/app/core/config.py",
    "services/auth/app/core/config.py",
])
def test_settings_import_with_pydantic_two(module, tmp_path):
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
        "RABBITMQ_URL": "amqp://test:test@localhost:5672/",
        "JWT_SECRET": "test-only-secret-at-least-32-characters",
        "ENVIRONMENT": "development",
    })
    result = subprocess.run(
        [sys.executable, "-c", "import runpy; runpy.run_path(" + repr(str(ROOT / module)) + ")"],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr
