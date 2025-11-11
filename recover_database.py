#!/usr/bin/env python3
"""
Database Recovery Script
Attempts to recover data from corrupted SQLite database
"""
import sqlite3
import shutil
from datetime import datetime
import os

DB_PATH = "cars.db"
BACKUP_PATH = f"cars_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
RECOVERED_PATH = f"cars_recovered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"

def create_backup():
    """Create a backup of the corrupted database"""
    print(f"Creating backup: {BACKUP_PATH}")
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print("Backup created successfully")

def check_integrity():
    """Check database integrity"""
    print("\nChecking database integrity...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchall()
        conn.close()
        
        if result[0][0] == "ok":
            print("✓ Database integrity check passed")
            return True
        else:
            print("✗ Database integrity check failed:")
            for row in result:
                print(f"  {row[0]}")
            return False
    except Exception as e:
        print(f"✗ Error during integrity check: {e}")
        return False

def recover_with_dump():
    """Attempt recovery by dumping and restoring"""
    print("\nAttempting recovery using SQL dump method...")
    
    # First, try to dump the database
    dump_file = f"cars_dump_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    
    try:
        print(f"Dumping database to {dump_file}...")
        os.system(f'sqlite3 {DB_PATH} .dump > {dump_file}')
        
        print(f"Creating recovered database: {RECOVERED_PATH}...")
        os.system(f'sqlite3 {RECOVERED_PATH} < {dump_file}')
        
        # Verify the recovered database
        conn = sqlite3.connect(RECOVERED_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        
        if result[0] == "ok":
            print("✓ Recovery successful!")
            cursor.execute("SELECT COUNT(*) FROM cars;")
            count = cursor.fetchone()[0]
            print(f"  Recovered {count} car records")
            conn.close()
            
            print(f"\nTo use the recovered database:")
            print(f"1. Stop your application")
            print(f"2. Run: mv {DB_PATH} {DB_PATH}.corrupted")
            print(f"3. Run: mv {RECOVERED_PATH} {DB_PATH}")
            print(f"4. Run: rm {DB_PATH}-shm {DB_PATH}-wal (if they exist)")
            print(f"5. Restart your application")
            return True
        else:
            print("✗ Recovered database still has issues")
            conn.close()
            return False
            
    except Exception as e:
        print(f"✗ Recovery failed: {e}")
        return False

def recover_from_backup():
    """List available backups for manual recovery"""
    print("\nLooking for backup databases...")
    backups = []
    
    # Check current directory
    for file in os.listdir("."):
        if file.startswith("cars") and file.endswith(".db") and file != "cars.db":
            stat = os.stat(file)
            backups.append((file, stat.st_size, datetime.fromtimestamp(stat.st_mtime)))
    
    # Check backups directory
    if os.path.exists("backups"):
        for root, dirs, files in os.walk("backups"):
            for file in files:
                if file.endswith(".db"):
                    full_path = os.path.join(root, file)
                    stat = os.stat(full_path)
                    backups.append((full_path, stat.st_size, datetime.fromtimestamp(stat.st_mtime)))
    
    if backups:
        print("\nAvailable backup databases:")
        backups.sort(key=lambda x: x[2], reverse=True)
        for path, size, mtime in backups[:10]:
            size_mb = size / (1024 * 1024)
            print(f"  {path}")
            print(f"    Size: {size_mb:.2f} MB, Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\nTo restore from a backup:")
        print("1. Stop your application")
        print(f"2. Run: mv {DB_PATH} {DB_PATH}.corrupted")
        print("3. Run: cp <backup_path> {DB_PATH}")
        print("4. Run: rm cars.db-shm cars.db-wal (if they exist)")
        print("5. Restart your application")
    else:
        print("No backup databases found")

def main():
    print("=" * 60)
    print("SQLite Database Recovery Tool")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file '{DB_PATH}' not found")
        return
    
    # Create backup first
    create_backup()
    
    # Check integrity
    is_ok = check_integrity()
    
    if not is_ok:
        # Try recovery
        recovered = recover_with_dump()
        
        if not recovered:
            # Show backup options
            recover_from_backup()
    else:
        print("\nDatabase appears to be OK. The error might be transient.")
        print("Try closing all applications using the database and restart.")

if __name__ == "__main__":
    main()
