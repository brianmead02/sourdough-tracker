"""Direct-to-storage uploads. The API issues grants; it never handles bytes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import RateLimiter, VerifiedUser
from app.config import get_settings
from app.schemas.media import (
    ConfirmUploadRequest,
    ConfirmUploadResponse,
    PresignUploadRequest,
    PresignUploadResponse,
)
from app.services import storage

router = APIRouter(prefix="/media", tags=["media"])


@router.post(
    "/presign-upload",
    response_model=PresignUploadResponse,
    dependencies=[Depends(RateLimiter(times=60, seconds=3600, scope="presign-upload"))],
)
async def presign_upload(
    payload: PresignUploadRequest, user: VerifiedUser
) -> PresignUploadResponse:
    try:
        grant = storage.presign_upload(user.id, payload.purpose, payload.content_type)
    except storage.StorageError as exc:
        settings = get_settings()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{exc}. Allowed: {', '.join(settings.allowed_image_types)}",
        ) from exc

    return PresignUploadResponse(
        object_key=grant.object_key,
        url=grant.url,
        fields=grant.fields,
        max_bytes=grant.max_bytes,
        expires_in=grant.expires_in,
    )


@router.post("/confirm", response_model=ConfirmUploadResponse)
async def confirm_upload(
    payload: ConfirmUploadRequest, user: VerifiedUser
) -> ConfirmUploadResponse:
    """Verify an upload landed before anything is attached to it."""
    if storage.key_owner(payload.object_key) != user.id:
        # Same 404 as a missing object: whether someone else's key exists is
        # not something to disclose.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    info = await storage.head(payload.object_key)
    if info is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    return ConfirmUploadResponse(
        object_key=info.object_key,
        size_bytes=info.size_bytes,
        content_type=info.content_type,
        url=storage.presign_download(info.object_key),
    )
