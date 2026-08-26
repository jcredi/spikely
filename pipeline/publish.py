"""Publish a complete preview tile set to Cloudflare R2 atomically."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import boto3


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required for R2 publication")
    return value


def publish_to_r2(run_dir: Path, run_metadata: dict[str, Any]) -> dict[str, Any]:
    """Upload an immutable run, then replace ``latest.json`` as the commit."""

    account_id = _required_env("R2_ACCOUNT_ID")
    bucket = _required_env("R2_BUCKET")
    public_base_url = _required_env("R2_PUBLIC_BASE_URL").rstrip("/")
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=_required_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_required_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
    )

    run_id = str(run_metadata["runId"])
    prefix = f"runs/{run_id}"
    for path in sorted(Path(run_dir).rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(run_dir).as_posix()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        client.upload_file(
            str(path),
            bucket,
            f"{prefix}/{relative}",
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )

    latest = dict(run_metadata)
    latest["manifestUrl"] = f"{public_base_url}/latest.json"
    latest["tiles"] = [f"{public_base_url}/{prefix}/tiles/{{z}}/{{x}}/{{y}}.png"]
    latest["publishedAt"] = datetime.now(UTC).isoformat()
    client.put_object(
        Bucket=bucket,
        Key="latest.json",
        Body=json.dumps(latest, indent=2).encode(),
        ContentType="application/json",
        CacheControl="no-cache, max-age=0",
    )
    return latest

