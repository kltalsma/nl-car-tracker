#!/usr/bin/env python3
"""
Database backup utility
Creates timestamped backups and maintains backup rotation
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = 'data/cars.db'
BACKUP_DIR = 'data/backups'
MAX_BACKUPS = 10  # Keep last 10 backups


def create_backup(reason='manual'):
    """Create a timestamped backup of the database"""
    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database not found at {DB_PATH}")
        return False
    
    # Generate backup filename
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_name = f"cars.db.backup-{reason}-{timestamp}"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        # Use SQLite's backup API for safe online backup
        print(f"Creating backup: {backup_name}")
        
        # Connect to source and destination
        source = sqlite3.connect(DB_PATH)
        dest = sqlite3.connect(backup_path)
        
        # Perform backup
        with dest:
            source.backup(dest)
        
        source.close()
        dest.close()
        
        # Get file size
        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        print(f"✓ Backup created successfully ({size_mb:.2f} MB)")
        
        # Verify backup integrity
        if verify_backup(backup_path):
            print("✓ Backup integrity verified")
        else:
            print("⚠ Warning: Backup integrity check failed")
            return False
        
        # Rotate old backups
        rotate_backups()
        
        return True
        
    except Exception as e:
        print(f"Error creating backup: {e}")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        return False


def verify_backup(db_path):
    """Verify database integrity"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()[0]
        conn.close()
        return result == 'ok'
    except Exception as e:
        print(f"Verification error: {e}")
        return False


def rotate_backups():
    """Remove old backups, keeping only MAX_BACKUPS most recent"""
    if not os.path.exists(BACKUP_DIR):
        return
    
    # Get all backup files
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith('cars.db.backup-'):
            path = os.path.join(BACKUP_DIR, f)
            backups.append((path, os.path.getmtime(path)))
    
    # Sort by modification time (newest first)
    backups.sort(key=lambda x: x[1], reverse=True)
    
    # Remove old backups
    if len(backups) > MAX_BACKUPS:
        print(f"\nRemoving {len(backups) - MAX_BACKUPS} old backup(s)...")
        for path, _ in backups[MAX_BACKUPS:]:
            print(f"  Removing: {os.path.basename(path)}")
            os.remove(path)


def list_backups():
    """List all available backups"""
    if not os.path.exists(BACKUP_DIR):
        print("No backups found.")
        return
    
    backups = []
    for f in os.listdir(BACKUP_DIR):
        if f.startswith('cars.db.backup-'):
            path = os.path.join(BACKUP_DIR, f)
            size = os.path.getsize(path) / (1024 * 1024)
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            backups.append((f, size, mtime))
    
    if not backups:
        print("No backups found.")
        return
    
    backups.sort(key=lambda x: x[2], reverse=True)
    
    print("\nAvailable backups:")
    print("-" * 80)
    for name, size, mtime in backups:
        print(f"{name:60} {size:6.2f} MB  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Database backup utility')
    parser.add_argument('--list', action='store_true', help='List all backups')
    parser.add_argument('--reason', default='manual', help='Backup reason/tag')
    
    args = parser.parse_args()
    
    if args.list:
        list_backups()
    else:
        create_backup(args.reason)
