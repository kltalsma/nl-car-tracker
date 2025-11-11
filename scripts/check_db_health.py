#!/usr/bin/env python3
"""
Database health check utility
Monitors database integrity and configuration
"""
import os
import sys
import sqlite3
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = 'data/cars.db'


def check_database_health():
    """Perform comprehensive database health check"""
    print("=" * 60)
    print("Database Health Check")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check file size
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        print(f"\n📊 Database Size: {size_mb:.2f} MB")
        
        # Check journal mode
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        journal_ok = journal_mode == 'wal'
        status = "✓" if journal_ok else "⚠"
        print(f"{status} Journal Mode: {journal_mode.upper()} {'(GOOD)' if journal_ok else '(SHOULD BE WAL)'}")
        
        # Check synchronous setting
        cursor.execute("PRAGMA synchronous;")
        sync = cursor.fetchone()[0]
        sync_names = {0: 'OFF', 1: 'NORMAL', 2: 'FULL', 3: 'EXTRA'}
        sync_ok = sync == 1  # NORMAL is optimal for WAL
        status = "✓" if sync_ok else "⚠"
        print(f"{status} Synchronous: {sync_names.get(sync, sync)} {'(GOOD)' if sync_ok else '(SHOULD BE NORMAL)'}")
        
        # Check integrity
        print("\n🔍 Checking database integrity...")
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchall()
        integrity_ok = len(result) == 1 and result[0][0] == 'ok'
        
        if integrity_ok:
            print("✓ Database integrity: OK")
        else:
            print("❌ Database integrity: FAILED")
            print("Errors:")
            for row in result[:10]:  # Show first 10 errors
                print(f"  - {row[0]}")
        
        # Check for WAL file
        wal_file = DB_PATH + '-wal'
        shm_file = DB_PATH + '-shm'
        if os.path.exists(wal_file):
            wal_size = os.path.getsize(wal_file) / 1024
            print(f"\n📝 WAL File: {wal_size:.2f} KB")
        if os.path.exists(shm_file):
            print(f"📝 Shared Memory File: Present")
        
        # Get table statistics
        cursor.execute("SELECT COUNT(*) FROM cars WHERE is_available = 1;")
        available = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM cars WHERE is_available = 0;")
        unavailable = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM price_history;")
        price_records = cursor.fetchone()[0]
        
        print(f"\n📈 Statistics:")
        print(f"  Available Cars: {available:,}")
        print(f"  Unavailable Cars: {unavailable:,}")
        print(f"  Total Cars: {available + unavailable:,}")
        print(f"  Price History Records: {price_records:,}")
        
        # Check for recent updates
        cursor.execute("SELECT MAX(last_seen) FROM cars;")
        last_update = cursor.fetchone()[0]
        if last_update:
            print(f"\n🕒 Last Update: {last_update}")
        
        # Check for duplicate external_ids
        cursor.execute("""
            SELECT external_id, COUNT(*) as count 
            FROM cars 
            GROUP BY external_id 
            HAVING count > 1
        """)
        duplicates = cursor.fetchall()
        if duplicates:
            print(f"\n⚠ Found {len(duplicates)} duplicate external_ids:")
            for ext_id, count in duplicates[:5]:
                print(f"  - {ext_id}: {count} occurrences")
        
        conn.close()
        
        print("\n" + "=" * 60)
        overall_health = integrity_ok and journal_ok
        if overall_health:
            print("✓ Overall Health: GOOD")
        else:
            print("⚠ Overall Health: NEEDS ATTENTION")
        print("=" * 60)
        
        return overall_health
        
    except Exception as e:
        print(f"\n❌ Error during health check: {e}")
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Check database health')
    parser.add_argument('--auto-fix', action='store_true', 
                       help='Automatically fix issues (enable WAL mode)')
    
    args = parser.parse_args()
    
    healthy = check_database_health()
    
    if not healthy and args.auto_fix:
        print("\n🔧 Attempting to fix issues...")
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            conn.commit()
            conn.close()
            print("✓ Fixed: Enabled WAL mode")
            print("\nRe-running health check...")
            check_database_health()
        except Exception as e:
            print(f"❌ Auto-fix failed: {e}")
    
    sys.exit(0 if healthy else 1)
