#!/bin/sh
# Nightly SQLite backup (V3-4-1). `sqlite3 .backup` is safe to run against a
# live database (it's the same mechanism SQLite itself uses for online
# backups, consistent even mid-write) — no need to stop the app first.
#
# Run via cron on the host, e.g.:
#   0 2 * * * /path/to/AI-SoulMatch/deploy/backup.sh >> /var/log/soulmatch-backup.log 2>&1
#
# [HUMAN]: pick where backups actually land. Local rotation always happens;
# uncomment the rclone line and configure an `rclone config` remote (e.g.
# Backblaze B2, S3, or a second VPS over SFTP) to also ship backups offsite
# — a backup that lives only on the server it's protecting against isn't
# a real backup.

set -eu

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="$PROJECT_DIR/data/soulmatch.db"
BACKUP_DIR="$PROJECT_DIR/data/backups"
DATE="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/soulmatch_$DATE.db"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "No database at $DB_PATH — nothing to back up." >&2
    exit 1
fi

sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
gzip "$BACKUP_FILE"
echo "Backed up to $BACKUP_FILE.gz"

# [HUMAN] uncomment and configure once an rclone remote exists:
# rclone copy "$BACKUP_FILE.gz" remote:soulmatch-backups/

# Local rotation — keep the last $KEEP_DAYS days regardless of offsite copy.
find "$BACKUP_DIR" -name "soulmatch_*.db.gz" -mtime "+$KEEP_DAYS" -delete
