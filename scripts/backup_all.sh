#!/usr/bin/env bash
set -euo pipefail

# One-shot backup for PostgreSQL + Redis + Qdrant.
# Usage:
#   scripts/backup_all.sh
#   BACKUP_ROOT=./backups RETENTION_DAYS=14 PRUNE_AFTER_BACKUP=1 scripts/backup_all.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
PRUNE_AFTER_BACKUP="${PRUNE_AFTER_BACKUP:-0}"
POSTGRES_USER="${POSTGRES_USER:-helagent}"
POSTGRES_DB="${POSTGRES_DB:-helagent}"
TS="$(date +%F_%H%M%S)"
OUT_DIR="$BACKUP_ROOT/$TS"

mkdir -p "$OUT_DIR/postgres" "$OUT_DIR/redis" "$OUT_DIR/qdrant"

cd "$ROOT_DIR"

echo "[1/6] PostgreSQL logical backup..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$OUT_DIR/postgres/helagent.sql"
docker compose exec -T postgres pg_dump -s -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$OUT_DIR/postgres/schema.sql"

echo "[2/6] Redis flush-to-disk (best-effort BGSAVE)..."
docker compose exec -T redis redis-cli BGSAVE >/dev/null || true
sleep 2

echo "[3/6] Archive Redis /data ..."
docker compose exec -T redis sh -c "tar -czf - -C /data ." > "$OUT_DIR/redis/redis-data.tgz"

echo "[4/6] Archive Qdrant /qdrant/storage ..."
docker compose exec -T qdrant sh -c "tar -czf - -C /qdrant/storage ." > "$OUT_DIR/qdrant/qdrant-storage.tgz"

echo "[5/6] Build checksums and manifest..."
cd "$OUT_DIR"
shasum -a 256 postgres/helagent.sql postgres/schema.sql redis/redis-data.tgz qdrant/qdrant-storage.tgz > SHA256SUMS
cat > MANIFEST.txt <<EOF
timestamp=$TS
postgres_db=$POSTGRES_DB
postgres_user=$POSTGRES_USER
files:
  - postgres/helagent.sql
  - postgres/schema.sql
  - redis/redis-data.tgz
  - qdrant/qdrant-storage.tgz
checksum_file=SHA256SUMS
EOF

echo "[6/6] Optional retention prune..."
if [[ "$PRUNE_AFTER_BACKUP" == "1" ]]; then
  "$ROOT_DIR/scripts/backup_prune.sh"
else
  echo "skip prune (set PRUNE_AFTER_BACKUP=1 to enable)"
fi

echo "Backup completed: $OUT_DIR"
