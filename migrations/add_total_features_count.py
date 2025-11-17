"""
Migration: Add total_features_count column
Date: 2025-11-17
Description: Adds total_features_count to track all features (not just critical ones).
"""

import sqlite3
import sys
from pathlib import Path

def migrate():
    db_path = Path(__file__).parent.parent / 'data' / 'cars.db'
    
    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if total_features_count already exists
        cursor.execute("PRAGMA table_info(cars)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'total_features_count' in columns:
            print("Column total_features_count already exists, skipping migration.")
            return
        
        print("Adding total_features_count column...")
        
        # Add the new column
        cursor.execute('''
            ALTER TABLE cars 
            ADD COLUMN total_features_count INTEGER DEFAULT 0
        ''')
        
        # Populate total_features_count from features JSON
        print("Populating total_features_count from existing features...")
        cursor.execute('''
            UPDATE cars 
            SET total_features_count = (
                SELECT json_array_length(features)
                FROM cars AS c2
                WHERE c2.id = cars.id
            )
            WHERE features IS NOT NULL
        ''')
        
        rows_updated = cursor.rowcount
        print(f"Updated {rows_updated} rows with total feature counts")
        
        # Add index for better performance
        print("Adding index on total_features_count...")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_total_features_count 
            ON cars(total_features_count)
        ''')
        
        conn.commit()
        print("✓ Migration completed successfully!")
        
        # Show some stats
        cursor.execute('''
            SELECT 
                source_website,
                AVG(total_features_count) as avg_total,
                AVG(features_count) as avg_critical
            FROM cars
            WHERE is_available = 1
            GROUP BY source_website
        ''')
        
        print("\nFeature count comparison (available cars):")
        print(f"{'Source':<20} {'Avg Total':<12} {'Avg Critical':<12}")
        print("-" * 44)
        for row in cursor.fetchall():
            print(f"{row[0]:<20} {row[1]:<12.1f} {row[2]:<12.1f}")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
