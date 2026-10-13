"""Storage boundary fault tests; real S3 delivery is verified by Compose E2E."""

import io
import json
import sys
from types import SimpleNamespace

import pytest

from services.pipeline.storage import S3Mirror


@pytest.fixture
def no_ambient_s3(monkeypatch):
    for key in (
        "S3_ENDPOINT_URL",
        "S3_BUCKET_INVOICES",
        "S3_BUCKET_PROCESSED",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    calls = []

    def unexpected_client(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Invalid configuration must not construct an S3 client")

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=unexpected_client))
    return calls


def test_disabled_mirror_does_not_discover_ambient_credentials(
    no_ambient_s3, monkeypatch
):
    monkeypatch.setenv("AWS_PROFILE", "production")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ambient-test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "ambient-test-secret")
    assert S3Mirror.from_env() is None
    assert no_ambient_s3 == []


@pytest.mark.parametrize("bucket", ["S3_BUCKET_INVOICES", "S3_BUCKET_PROCESSED"])
def test_bucket_without_explicit_endpoint_fails_before_client(
    no_ambient_s3, monkeypatch, bucket
):
    monkeypatch.setenv(bucket, "test-bucket")
    with pytest.raises(ValueError, match="explicit local"):
        S3Mirror.from_env()
    assert no_ambient_s3 == []


@pytest.mark.parametrize(
    "missing",
    [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "S3_BUCKET_INVOICES",
        "S3_BUCKET_PROCESSED",
    ],
)
def test_partial_configuration_never_uses_sdk_defaults(
    no_ambient_s3, monkeypatch, missing
):
    for key, value in {
        "S3_ENDPOINT_URL": "http://localhost:4566",
        "AWS_ACCESS_KEY_ID": "explicit-test-key",
        "AWS_SECRET_ACCESS_KEY": "explicit-test-secret",
        "S3_BUCKET_INVOICES": "raw",
        "S3_BUCKET_PROCESSED": "processed",
    }.items():
        if key != missing:
            monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="explicit credentials"):
        S3Mirror.from_env()
    assert no_ambient_s3 == []


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://s3.amazonaws.com",
        "https://s3.us-east-1.amazonaws.com",
        "https://localhost.example.org",
        "https://8.8.8.8",
        "file:///tmp/s3",
        "http://key:secret@localhost:4566",
        "http://localhost:4566?token=test",
        "http://localhost:4566#fragment",
        "http://169.254.169.254",
        "http://[fe80::1]",
        "http://0.0.0.0",
        "http://[::]",
    ],
)
def test_remote_metadata_or_ambiguous_endpoint_fails_before_sdk(
    no_ambient_s3, endpoint
):
    with pytest.raises(ValueError, match="local emulator"):
        S3Mirror(endpoint, "test-key", "test-secret", "raw", "processed")
    assert no_ambient_s3 == []


class BoundaryClient:
    def __init__(self, restored=b"pdf-bytes", put_status=200, error=None):
        self.restored, self.put_status, self.error = restored, put_status, error
        self.puts = []
        self.body = None

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        if self.error == "write":
            raise OSError("injected write outage")
        return {"ResponseMetadata": {"HTTPStatusCode": self.put_status}}

    def get_object(self, **kwargs):
        if self.error == "read":
            raise OSError("injected read outage")
        self.body = io.BytesIO(self.restored)
        return {"Body": self.body}

    def head_bucket(self, **kwargs):
        if self.error == "head":
            raise OSError("injected readiness outage")
        return {"ResponseMetadata": {"HTTPStatusCode": self.put_status}}


def mirror(client):
    return S3Mirror(
        "http://localhost:4566", "test-key", "test-secret", "raw", "processed", client
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:4566",
        "http://localstack:4566",
        "http://127.0.0.1:4566",
        "http://[::1]:4566",
        "http://10.0.0.2:4566",
        "http://[fd00::2]:4566",
    ],
)
def test_explicit_local_emulator_remains_usable(endpoint):
    client = BoundaryClient()
    configured = S3Mirror(
        endpoint, "test-key", "test-secret", "raw", "processed", client
    )
    configured.put_source("invoice-1", b"pdf-bytes")
    assert client.body.closed


@pytest.mark.parametrize("error", ["write", "read"])
def test_source_delivery_propagates_storage_failure(error):
    with pytest.raises(OSError, match=f"injected {error} outage"):
        mirror(BoundaryClient(error=error)).put_source("invoice-1", b"pdf-bytes")


@pytest.mark.parametrize("status", [201, 403, 503, None])
def test_unconfirmed_source_write_is_not_success(status):
    with pytest.raises(RuntimeError, match="confirm source"):
        mirror(BoundaryClient(put_status=status)).put_source("invoice-1", b"pdf-bytes")


def test_acknowledged_write_with_corrupted_readback_is_not_success():
    client = BoundaryClient(restored=b"different-pdf")
    with pytest.raises(RuntimeError, match="bytes differ"):
        mirror(client).put_source("invoice-1", b"pdf-bytes")
    assert client.body.closed


def test_verified_source_roundtrip_closes_read_body():
    client = BoundaryClient()
    mirror(client).put_source("invoice-1", b"pdf-bytes")
    assert client.body.closed
    assert client.puts[0]["Body"] == b"pdf-bytes"


def test_read_failure_closes_response_body():
    class BrokenBody(io.BytesIO):
        def read(self, *args):
            raise OSError("injected stream failure")

    body = BrokenBody()
    client = SimpleNamespace(get_object=lambda **kwargs: {"Body": body})
    with pytest.raises(OSError, match="stream failure"):
        mirror(client).get_source("invoice-1")
    assert body.closed


def test_fields_write_propagates_failure_and_preserves_document_values():
    fields = {"total_amount": "123.45", "vendor": "Actual document vendor"}
    client = BoundaryClient()
    mirror(client).put_fields("invoice-1", fields)
    assert json.loads(client.puts[0]["Body"]) == fields
    for client in [BoundaryClient(error="write"), BoundaryClient(put_status=503)]:
        with pytest.raises((OSError, RuntimeError)):
            mirror(client).put_fields("invoice-1", fields)


@pytest.mark.parametrize(
    "client", [BoundaryClient(error="head"), BoundaryClient(put_status=403)]
)
def test_readiness_cannot_report_healthy_when_bucket_check_fails(client):
    with pytest.raises((OSError, RuntimeError)):
        mirror(client).check_ready()
