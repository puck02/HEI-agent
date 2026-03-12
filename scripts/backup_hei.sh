#!/usr/bin/env bash
set -euo pipefail

# Automated backup for HEI-agent:
# 1) PostgreSQL logical dump
# 2) Docker named volumes archive (postgres/redis/qdrant)
# 3) Keep backups for a configurable number of days

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DATE_TAG="$(date +%F_%H-%M-%S)"

# Optional override if container names differ.
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-hel-postgres}"
POSTGRES_USER="${POSTGRES_USER:-helagent}"
POSTGRES_DB="${POSTGRES_DB:-helagent}"

mkdir -p "$BACKUP_DIR"

echo "[backup] start at $(date '+%F %T')"
echo "[backup] output dir: $BACKUP_DIR"

DB_DUMP_FILE="$BACKUP_DIR/postgres_${DATE_TAG}.sql.gz"
echo "[backup] dumping postgres from container: $POSTGRES_CONTAINER"
sudo docker exec "$POSTGRES_CONTAINER" \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$DB_DUMP_FILE"

for volume in hei-agent_postgres_data hei-agent_redis_data hei-agent_qdrant_data; do
  ARCHIVE_FILE="$BACKUP_DIR/${volume}_${DATE_TAG}.tar.gz"
  echo "[backup] archiving docker volume: $volume"
  sudo docker run --rm \
    -v "${volume}:/source:ro" \
    -v "${BACKUP_DIR}:/backup" \
    alpine:3.20 \
    sh -c "tar -C /source -czf /backup/$(basename "$ARCHIVE_FILE") ."
done

echo "[backup] writing latest symlink"
ln -sfn "$DB_DUMP_FILE" "$BACKUP_DIR/latest_postgres.sql.gz"

echo "[backup] pruning files older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -maxdepth 1 -type f -mtime +"$RETENTION_DAYS" -name "*.gz" -delete

echo "[backup] done at $(date '+%F %T')"
