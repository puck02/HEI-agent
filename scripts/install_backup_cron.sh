#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_SCRIPT="$ROOT_DIR/scripts/backup_hei.sh"
LOG_DIR="$ROOT_DIR/dev_logs"
LOG_FILE="$LOG_DIR/backup-cron.log"

# Default schedule: every day at 03:30
CRON_SCHEDULE="${CRON_SCHEDULE:-30 3 * * *}"

mkdir -p "$LOG_DIR"
chmod +x "$BACKUP_SCRIPT"

CRON_LINE="$CRON_SCHEDULE cd $ROOT_DIR && $BACKUP_SCRIPT >> $LOG_FILE 2>&1"

TMP_FILE="$(mktemp)"
crontab -l 2>/dev/null | grep -v "backup_hei.sh" > "$TMP_FILE" || true
echo "$CRON_LINE" >> "$TMP_FILE"
crontab "$TMP_FILE"
rm -f "$TMP_FILE"

echo "Installed backup cron job:"
echo "$CRON_LINE"
