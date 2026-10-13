"""Documented extract CLI, backed by the real local-text pipeline.

Run from the repository root or this service directory with ``uvicorn app.main:app``.
This entrypoint does not construct the retired OCR/LLM or simulated service objects.
"""

import os
import sys
from pathlib import Path

# Preserve service-directory CLI usage while sharing the canonical implementation.
repository_root = Path(__file__).resolve().parents[3]
if str(repository_root) not in sys.path:
    sys.path.insert(0, str(repository_root))

from services.pipeline.runtime import create_app  # noqa: E402

mode = os.getenv("EXTRACTION_MODE", "local_text")
if mode != "local_text":
    raise ValueError(
        "Only EXTRACTION_MODE=local_text is supported; live OCR/AI providers "
        "are not implemented by this pipeline"
    )

app = create_app(role="extract")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8001"))
    )
