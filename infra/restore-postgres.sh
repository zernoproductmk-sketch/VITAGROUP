#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: restore-postgres.sh /backups/vitagroup_YYYYMMDDTHHMMSSZ.dump" >&2
  exit 2
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup not found: $BACKUP_FILE" >&2
  exit 2
fi

echo "This operation replaces the current database contents."
echo "Backup: $BACKUP_FILE"
echo "Database: $PGDATABASE"
echo "Type RESTORE to continue:"
read confirmation

if [ "$confirmation" != "RESTORE" ]; then
  echo "Restore cancelled."
  exit 1
fi

pg_restore   --clean   --if-exists   --no-owner   --no-acl   --dbname="$PGDATABASE"   "$BACKUP_FILE"

echo "Restore complete."
