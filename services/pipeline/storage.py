"""Explicit local S3 mirror. No ambient credentials or remote cloud discovery."""

import hashlib
import ipaddress
import json
import os
from urllib.parse import urlsplit


class S3Mirror:
    def __init__(
        self,
        endpoint_url,
        access_key,
        secret_key,
        raw_bucket,
        processed_bucket,
        client=None,
    ):
        parsed = urlsplit(endpoint_url)
        host = parsed.hostname or ""
        local = host in {"localhost", "localstack", "minio", "s3"}
        try:
            address = ipaddress.ip_address(host)
            local = address.is_loopback or (
                address.is_private
                and not any(
                    (
                        address.is_link_local,
                        address.is_unspecified,
                        address.is_reserved,
                        address.is_multicast,
                    )
                )
            )
        except ValueError:
            pass
        if (
            parsed.scheme not in {"http", "https"}
            or not local
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("S3 endpoint must be an explicit local emulator URL")
        if not all((access_key, secret_key, raw_bucket, processed_bucket)):
            raise ValueError("S3 mirror requires explicit credentials and both buckets")
        self.raw_bucket, self.processed_bucket = raw_bucket, processed_bucket
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name="us-east-1",
                config=Config(
                    connect_timeout=2,
                    read_timeout=3,
                    retries={"max_attempts": 1},
                    s3={"addressing_style": "path"},
                ),
            )
        self.client = client

    @classmethod
    def from_env(cls):
        endpoint = os.getenv("S3_ENDPOINT_URL")
        configured = any(
            os.getenv(name) for name in ("S3_BUCKET_INVOICES", "S3_BUCKET_PROCESSED")
        )
        if not endpoint:
            if configured:
                raise ValueError("S3 buckets require an explicit local S3_ENDPOINT_URL")
            return None
        return cls(
            endpoint,
            os.getenv("AWS_ACCESS_KEY_ID"),
            os.getenv("AWS_SECRET_ACCESS_KEY"),
            os.getenv("S3_BUCKET_INVOICES"),
            os.getenv("S3_BUCKET_PROCESSED"),
        )

    @staticmethod
    def source_key(invoice_id):
        return f"invoices/{invoice_id}/source.pdf"

    def get_source(self, invoice_id):
        response = self.client.get_object(
            Bucket=self.raw_bucket, Key=self.source_key(invoice_id)
        )
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def put_source(self, invoice_id, content):
        response = self.client.put_object(
            Bucket=self.raw_bucket,
            Key=self.source_key(invoice_id),
            Body=content,
            ContentType="application/pdf",
        )
        if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200:
            raise RuntimeError("S3 did not confirm source storage")
        restored = self.get_source(invoice_id)
        if hashlib.sha256(restored).digest() != hashlib.sha256(content).digest():
            raise RuntimeError("S3 source roundtrip bytes differ")

    def put_fields(self, invoice_id, fields):
        response = self.client.put_object(
            Bucket=self.processed_bucket,
            Key=f"invoices/{invoice_id}/fields.json",
            Body=json.dumps(fields, sort_keys=True).encode(),
            ContentType="application/json",
        )
        if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200:
            raise RuntimeError("S3 did not confirm extracted fields storage")

    def check_ready(self):
        for bucket in (self.raw_bucket, self.processed_bucket):
            response = self.client.head_bucket(Bucket=bucket)
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200:
                raise RuntimeError("S3 bucket unavailable")

    def delete_source(self, invoice_id):
        self.client.delete_object(
            Bucket=self.raw_bucket, Key=self.source_key(invoice_id)
        )
