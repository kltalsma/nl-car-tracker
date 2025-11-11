#!/bin/bash
# Database Restoration Script
# Replaces corrupted database with recovered version

set -e  # Exit on error

DB_DIR="data"
CORRUPTED_DB="$DB_DIR/cars.db"
RECOVERED_DB="$DB_DIR/cars_recovered.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="$DB_DIR/cars.db.corrupted-backup-$TIMESTAMP"

echo "=================================="
echo "Database Restoration Tool"
echo "=================================="
echo ""

# Check if recovered database exists
if [ ! -f "$RECOVERED_DB" ]; then
    echo "Error: Recovered database not found at $RECOVERED_DB"
    exit 1
fi

# Check integrity of recovered database
echo "Checking integrity of recovered database..."
INTEGRITY=$(sqlite3 "$RECOVERED_DB" "PRAGMA integrity_check;")
if [ "$INTEGRITY" != "ok" ]; then
    echo "Error: Recovered database has integrity issues!"
    echo "$INTEGRITY"
    exit 1
fi
echo "✓ Recovered database integrity: OK"

# Count records
RECORD_COUNT=$(sqlite3 "$RECOVERED_DB" "SELECT COUNT(*) FROM cars;")
echo "✓ Recovered database contains: $RECORD_COUNT car records"
echo ""

# Backup corrupted database
echo "Backing up corrupted database to: $BACKUP_NAME"
cp "$CORRUPTED_DB" "$BACKUP_NAME"
echo "✓ Backup created"
echo ""

# Remove WAL files
echo "Removing WAL files..."
rm -f "$CORRUPTED_DB-shm" "$CORRUPTED_DB-wal"
echo "✓ WAL files removed"
echo ""

# Replace database
echo "Replacing corrupted database with recovered version..."
cp "$RECOVERED_DB" "$CORRUPTED_DB"
echo "✓ Database replaced"
echo ""

# Verify new database
echo "Verifying new database..."
NEW_INTEGRITY=$(sqlite3 "$CORRUPTED_DB" "PRAGMA integrity_check;")
if [ "$NEW_INTEGRITY" != "ok" ]; then
    echo "Error: New database has integrity issues!"
    exit 1
fi

NEW_COUNT=$(sqlite3 "$CORRUPTED_DB" "SELECT COUNT(*) FROM cars;")
echo "✓ New database integrity: OK"
echo "✓ New database contains: $NEW_COUNT car records"
echo ""

echo "=================================="
echo "Database restoration complete!"
echo "=================================="
echo ""
echo "You can now restart your application."
