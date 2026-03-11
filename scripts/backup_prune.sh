#!/usr/bin/env bash
set -euo pipefail

# Prune timestamped backup directories older than RETENTION_DAYS.
# Usage:
#   scripts/backup_prune.sh
#   BACKUP_ROOT=./backups RETENTION_DAYS=14 scripts/backup_prune.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "No backup root found: $BACKUP_ROOT"
  exit 0
fi

echo "Pruning backups older than ${RETENTION_DAYS} days in $BACKUP_ROOT"

# Only delete directories matching YYYY-MM-DD_HHMMSS format.
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d \
  -name "20??-??-??_??????" -mtime "+$RETENTION_DAYS" -print -exec rm -rf {} \;

echo "Prune completed"
