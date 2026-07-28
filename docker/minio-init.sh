#!/bin/sh
# One-shot: create the media bucket. Objects stay private — the API hands out
# presigned URLs (docs/PLAN.md §2), so no anonymous read policy is set.
set -eu

mc alias set local http://minio:9000 "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"

if mc ls "local/$MINIO_BUCKET" >/dev/null 2>&1; then
  echo "bucket $MINIO_BUCKET already exists"
else
  mc mb "local/$MINIO_BUCKET"
  echo "created bucket $MINIO_BUCKET"
fi

mc anonymous set none "local/$MINIO_BUCKET"
echo "minio-init complete"
