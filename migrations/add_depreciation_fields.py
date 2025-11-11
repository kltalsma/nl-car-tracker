#!/usr/bin/env python3
"""
Migration: Add depreciation calculation fields to current_car table
Adds: initial_purchase_price, purchase_date, average_km_per_year
"""
import sqlite3
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config_loader import load_config

def run_migration():
    """Add depreciation fields to current_car table"""
    config = load_config()
    db_path = config['database']['path']
    
    print(f"Running migration on database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(current_car)")
        columns = [row[1] for row in cursor.fetchall()]
        
        migrations_run = []
        
        # Add initial_purchase_price if it doesn't exist
        if 'initial_purchase_price' not in columns:
            print("Adding column: initial_purchase_price")
            cursor.execute("""
                ALTER TABLE current_car 
                ADD COLUMN initial_purchase_price FLOAT
            """)
            migrations_run.append('initial_purchase_price')
        else:
            print("Column initial_purchase_price already exists, skipping")
        
        # Add purchase_date if it doesn't exist
        if 'purchase_date' not in columns:
            print("Adding column: purchase_date")
            cursor.execute("""
                ALTER TABLE current_car 
                ADD COLUMN purchase_date DATETIME
            """)
            migrations_run.append('purchase_date')
        else:
            print("Column purchase_date already exists, skipping")
        
        # Add average_km_per_year if it doesn't exist
        if 'average_km_per_year' not in columns:
            print("Adding column: average_km_per_year")
            cursor.execute("""
                ALTER TABLE current_car 
                ADD COLUMN average_km_per_year INTEGER
            """)
            migrations_run.append('average_km_per_year')
        else:
            print("Column average_km_per_year already exists, skipping")
        
        conn.commit()
        
        if migrations_run:
            print(f"\n✅ Migration completed successfully!")
            print(f"   Added columns: {', '.join(migrations_run)}")
        else:
            print("\n✅ All columns already exist, no migration needed")
        
        # Show current table structure
        print("\nCurrent current_car table structure:")
        cursor.execute("PRAGMA table_info(current_car)")
        for row in cursor.fetchall():
            print(f"  - {row[1]} ({row[2]})")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    run_migration()
