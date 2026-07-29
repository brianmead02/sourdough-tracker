#!/usr/bin/env bash
#
# Back up the database and the photo bucket.
#
#   ./scripts/backup.sh [destination-directory]
#
# Two stores, both needed: Postgres holds every row, MinIO holds the photos.
# Restoring one without the other leaves bakes pointing at objects that are not
# there. Redis is deliberately not backed up — it holds a job queue and
# rate-limit counters, both of which regenerate.
#
# Designed to be safe to run from cron: it writes to a temporary name and
# renames on success, so a partial backup is never mistaken for a good one.

set -euo pipefail

DEST="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
COMPOSE="${COMPOSE:-docker compose}"

mkdir -p "$DEST"

echo "==> Backing up to $DEST (timestamp $STAMP)"

# --- database ---------------------------------------------------------------
# `pg_dump -Fc` is the custom format: compressed, and restorable selectively
# with pg_restore rather than being an all-or-nothing SQL replay.
DB_TMP="$DEST/.db-$STAMP.dump.partial"
DB_OUT="$DEST/db-$STAMP.dump"

echo "--> postgres"
$COMPOSE exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-sourdough}" \
    -d "${POSTGRES_DB:-sourdough}" \
    --format=custom --no-owner --no-acl > "$DB_TMP"
mv "$DB_TMP" "$DB_OUT"
echo "    $(du -h "$DB_OUT" | cut -f1)  $DB_OUT"

# --- object storage ---------------------------------------------------------
# Mirrored through the mc client already present in the stack, so this works
# against MinIO or a real S3 without a second tool.
MEDIA_TMP="$DEST/.media-$STAMP.tar.gz.partial"
MEDIA_OUT="$DEST/media-$STAMP.tar.gz"

echo "--> minio"
docker run --rm \
    --network "$($COMPOSE ps --format '{{.Name}}' postgres | head -1 | sed 's/-postgres-1$//')_default" \
    -v "$(cd "$DEST" && pwd):/backup" \
    --entrypoint sh \
    minio/mc:latest -c "
        mc alias set src http://minio:9000 '${MINIO_ACCESS_KEY:-minioadmin}' '${MINIO_SECRET_KEY:-minioadmin}' >/dev/null &&
        mc mirror --quiet src/'${MINIO_BUCKET:-sourdough-media}' /tmp/media >/dev/null 2>&1 || true
        tar czf /backup/$(basename "$MEDIA_TMP") -C /tmp media 2>/dev/null || tar czf /backup/$(basename "$MEDIA_TMP") -T /dev/null
    "
mv "$MEDIA_TMP" "$MEDIA_OUT"
echo "    $(du -h "$MEDIA_OUT" | cut -f1)  $MEDIA_OUT"

# --- prune ------------------------------------------------------------------
if [ "$KEEP_DAYS" -gt 0 ]; then
    echo "--> pruning backups older than $KEEP_DAYS days"
    find "$DEST" -maxdepth 1 -name 'db-*.dump' -mtime "+$KEEP_DAYS" -delete
    find "$DEST" -maxdepth 1 -name 'media-*.tar.gz' -mtime "+$KEEP_DAYS" -delete
fi

echo "==> Done."
echo
echo "Restore with:"
echo "  $COMPOSE exec -T postgres pg_restore -U ${POSTGRES_USER:-sourdough} \\"
echo "      -d ${POSTGRES_DB:-sourdough} --clean --if-exists < $DB_OUT"
echo "  tar xzf $MEDIA_OUT -C /tmp && mc mirror /tmp/media dst/${MINIO_BUCKET:-sourdough-media}"
echo
echo "A backup you have never restored is a hypothesis, not a backup."
