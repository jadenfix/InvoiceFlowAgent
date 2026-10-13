"""Compatibility router for the canonical ingestion application.

Upload, status and statistics now use the real PostgreSQL/broker pipeline. Mount
this router without another prefix: its routes already include ``/api/v1/ingest``.
The documented ``app.main:app`` entrypoint mounts these routes directly and also
provides real dependency readiness. No legacy simulated endpoints remain here.
"""

from ..main import app

router = app.router
