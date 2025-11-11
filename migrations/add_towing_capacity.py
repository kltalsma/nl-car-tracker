"""
Migration script to add towing_capacity_kg column to cars table
"""
import sqlite3
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path='data/cars.db'):
    """
    Add towing_capacity_kg column to cars table
    
    New column:
    - towing_capacity_kg: Maximum braked towing capacity in kilograms
    """
    # Convert relative path to absolute
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, db_path)
    
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return False
    
    logger.info(f"Running towing capacity migration on database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Step 1: Add towing_capacity_kg column
        logger.info("Adding towing_capacity_kg column...")
        
        cursor.execute("""
            ALTER TABLE cars ADD COLUMN towing_capacity_kg INTEGER
        """)
        logger.info("  ✓ Added towing_capacity_kg column")
        
        # Step 2: Create index for performance (useful for filtering)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cars_towing_capacity_kg 
            ON cars(towing_capacity_kg)
        """)
        logger.info("  ✓ Created index on towing_capacity_kg")
        
        conn.commit()
        
        # Step 3: Show current state
        cursor.execute("""
            SELECT COUNT(*) 
            FROM cars 
            WHERE is_available = 1
        """)
        total_cars = cursor.fetchone()[0]
        
        logger.info(f"\n✅ Migration completed successfully!")
        logger.info(f"   Total available cars: {total_cars}")
        logger.info(f"   Towing capacity column added (currently NULL for all)")
        logger.info(f"\nNext steps:")
        logger.info(f"   1. Create data/towing_capacity.yaml with towing specs")
        logger.info(f"   2. Update scrapers to extract towing capacity from listings")
        logger.info(f"   3. Run enrichment script to populate from YAML")
        
        return True
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.warning(f"⚠️  Column towing_capacity_kg already exists")
            logger.info("Migration may have been run before - no changes needed")
            return True
        else:
            logger.error(f"Migration error: {e}")
            conn.rollback()
            return False
    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
