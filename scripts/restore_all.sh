#!/usr/bin/env bash
set -euo pipefail

# Restore PostgreSQL + Redis + Qdrant from one backup directory.
# Usage:
#   scripts/restore_all.sh --backup-dir backups/2026-03-11_030000 --yes
#   scripts/restore_all.sh --backup-dir backups/2026-03-11_030000 --reset-postgres --yes

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POSTGRES_USER="${POSTGRES_USER:-helagent}"
POSTGRES_DB="${POSTGRES_DB:-helagent}"

BACKUP_DIR=""
RESET_POSTGRES=0
SKIP_REDIS=0
SKIP_QDRANT=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir)
      BACKUP_DIR="$2"
      shift 2
      ;;
    --reset-postgres)
      RESET_POSTGRES=1
      shift
      ;;
    --skip-redis)
      SKIP_REDIS=1
      shift
      ;;
    --skip-qdrant)
      SKIP_QDRANT=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$BACKUP_DIR" ]]; then
  echo "Missing --backup-dir"
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Backup directory not found: $BACKUP_DIR"
  exit 1
fi

PG_DUMP="$BACKUP_DIR/postgres/helagent.sql"
REDIS_ARCHIVE="$BACKUP_DIR/redis/redis-data.tgz"
QDRANT_ARCHIVE="$BACKUP_DIR/qdrant/qdrant-storage.tgz"

if [[ ! -f "$PG_DUMP" ]]; then
  echo "Missing PostgreSQL dump: $PG_DUMP"
  exit 1
fi
if [[ $SKIP_REDIS -eq 0 && ! -f "$REDIS_ARCHIVE" ]]; then
  echo "Missing Redis archive: $REDIS_ARCHIVE"
  exit 1
fi
if [[ $SKIP_QDRANT -eq 0 && ! -f "$QDRANT_ARCHIVE" ]]; then
  echo "Missing Qdrant archive: $QDRANT_ARCHIVE"
  exit 1
fi

if [[ -f "$BACKUP_DIR/SHA256SUMS" ]]; then
  echo "Verifying checksum..."
  (cd "$BACKUP_DIR" && shasum -a 256 -c SHA256SUMS)
fi

echo "About to restore from: $BACKUP_DIR"
[[ $RESET_POSTGRES -eq 1 ]] && echo "- PostgreSQL will be RESET before import"
[[ $SKIP_REDIS -eq 1 ]] || echo "- Redis data will be replaced"
[[ $SKIP_QDRANT -eq 1 ]] || echo "- Qdrant data will be replaced"

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Continue? [y/N] " ans
  [[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Cancelled"; exit 1; }
fi

echo "[1/4] Restore PostgreSQL ..."
if [[ $RESET_POSTGRES -eq 1 ]]; then
  docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
SQL
fi
cat "$PG_DUMP" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

if [[ $SKIP_REDIS -eq 0 || $SKIP_QDRANT -eq 0 ]]; then
  echo "[2/4] Stop dependent services for volume-level restore ..."
  docker compose stop agent >/dev/null || true
fi

if [[ $SKIP_REDIS -eq 0 ]]; then
  echo "[3/4] Restore Redis ..."
  docker compose stop redis >/dev/null || true
  docker compose up -d redis >/dev/null
  docker compose exec -T redis sh -c "rm -rf /data/*"
  cat "$REDIS_ARCHIVE" | docker compose exec -T redis sh -c "tar -xzf - -C /data"
  docker compose restart redis >/dev/null
fi

if [[ $SKIP_QDRANT -eq 0 ]]; then
  echo "[4/4] Restore Qdrant ..."
  docker compose stop qdrant >/dev/null || true
  docker compose up -d qdrant >/dev/null
  docker compose exec -T qdrant sh -c "rm -rf /qdrant/storage/*"
  cat "$QDRANT_ARCHIVE" | docker compose exec -T qdrant sh -c "tar -xzf - -C /qdrant/storage"
  docker compose restart qdrant >/dev/null
fi

docker compose up -d agent >/dev/null || true
docker compose ps

echo "Restore completed"
