"""Request/response models for direct-to-storage uploads."""

from pydantic import BaseModel, Field


class PresignUploadRequest(BaseModel):
    content_type: str = Field(max_length=100)
    purpose: str = Field(default="bake_photo", pattern=r"^[a-z_]{3,30}$")


class PresignUploadResponse(BaseModel):
    """A one-shot grant to POST a file straight to object storage.

    The client sends a multipart form to `url` containing every entry of
    `fields` plus a `file` part. The API never sees the bytes.
    """

    object_key: str
    url: str
    fields: dict[str, str]
    max_bytes: int
    expires_in: int


class ConfirmUploadRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=255)


class ConfirmUploadResponse(BaseModel):
    object_key: str
    size_bytes: int
    content_type: str
    url: str
