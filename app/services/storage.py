"""Object storage for user media.

The API never touches image bytes (docs/PLAN.md §2): clients receive a presigned
POST and upload straight to S3/MinIO, then hand back the object key.

Presigned **POST** rather than PUT, because only POST supports a
`content-length-range` condition — with PUT there is nothing stopping a client
from uploading a 4 GB "photo".

Object keys embed the owner's id (`u/{user_id}/{purpose}/{uuid}.{ext}`), so a
key can be checked against the caller before it is attached to anything. Without
that, one user could attach another user's object to their own bake.
"""

import re
import uuid
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from starlette.concurrency import run_in_threadpool

from app.config import Settings, get_settings

EXTENSION_BY_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

KEY_PATTERN = re.compile(r"^u/(?P<user_id>[0-9a-f-]{36})/(?P<purpose>[a-z_]+)/[0-9a-f-]{36}\.\w+$")


@dataclass(slots=True)
class PresignedUpload:
    object_key: str
    url: str
    fields: dict[str, str]
    max_bytes: int
    expires_in: int


@dataclass(slots=True)
class ObjectInfo:
    object_key: str
    size_bytes: int
    content_type: str


class StorageError(Exception):
    """Object storage rejected the operation."""


_client: Any | None = None


def client(settings: Settings | None = None) -> Any:
    """One S3 client per process, created on first use."""
    global _client
    if _client is None:
        s = settings or get_settings()
        _client = boto3.client(
            "s3",
            endpoint_url=s.minio_client_url,
            aws_access_key_id=s.minio_access_key,
            aws_secret_access_key=s.minio_secret_key,
            region_name=s.minio_region,
            config=Config(signature_version="s3v4"),
        )
    return _client


def reset_client_cache() -> None:
    """Drop the cached client after a settings change (used by tests)."""
    global _client
    _client = None


def build_key(user_id: uuid.UUID, purpose: str, content_type: str) -> str:
    extension = EXTENSION_BY_TYPE.get(content_type)
    if extension is None:
        raise StorageError(f"unsupported content type: {content_type}")
    return f"u/{user_id}/{purpose}/{uuid.uuid4()}.{extension}"


def key_owner(object_key: str) -> uuid.UUID | None:
    """The user id embedded in a key, or None if it is not a well-formed key."""
    match = KEY_PATTERN.match(object_key)
    if match is None:
        return None
    try:
        return uuid.UUID(match.group("user_id"))
    except ValueError:
        return None


def presign_upload(
    user_id: uuid.UUID, purpose: str, content_type: str, settings: Settings | None = None
) -> PresignedUpload:
    """Generate a one-shot upload grant. Purely local — no network call."""
    s = settings or get_settings()
    if content_type not in s.allowed_image_types:
        raise StorageError(f"unsupported content type: {content_type}")

    key = build_key(user_id, purpose, content_type)
    presigned = client(s).generate_presigned_post(
        Bucket=s.minio_bucket,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, s.max_upload_bytes],
        ],
        ExpiresIn=s.upload_url_ttl_seconds,
    )
    return PresignedUpload(
        object_key=key,
        url=presigned["url"],
        fields=presigned["fields"],
        max_bytes=s.max_upload_bytes,
        expires_in=s.upload_url_ttl_seconds,
    )


def presign_download(object_key: str, settings: Settings | None = None) -> str:
    """Time-limited read URL. Objects are private; this is the only way to read one."""
    s = settings or get_settings()
    url: str = client(s).generate_presigned_url(
        "get_object",
        Params={"Bucket": s.minio_bucket, "Key": object_key},
        ExpiresIn=s.download_url_ttl_seconds,
    )
    return url


async def head(object_key: str, settings: Settings | None = None) -> ObjectInfo | None:
    """Confirm an object landed. Returns None when it does not exist."""
    s = settings or get_settings()

    def _head() -> ObjectInfo | None:
        try:
            response = client(s).head_object(Bucket=s.minio_bucket, Key=object_key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") in (403, 404):
                return None
            raise StorageError(str(exc)) from exc
        return ObjectInfo(
            object_key=object_key,
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType", "application/octet-stream")),
        )

    return await run_in_threadpool(_head)


async def delete(object_key: str, settings: Settings | None = None) -> None:
    s = settings or get_settings()

    def _delete() -> None:
        client(s).delete_object(Bucket=s.minio_bucket, Key=object_key)

    await run_in_threadpool(_delete)
