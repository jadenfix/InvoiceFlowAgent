"""Actual shared-provider integration contract (requires docker-compose.e2e.yml)."""

import subprocess
import sys
from pathlib import Path


def test_document_pipeline_shared_providers():
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, str(root / "scripts/check_legacy_storage.py")],
        cwd=root,
        check=True,
        timeout=180,
    )
