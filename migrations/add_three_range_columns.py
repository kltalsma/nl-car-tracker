"""
Migration script to add three separate range columns and populate them
"""
import sqlite3
import os
import sys

# Add parent directory to path to import helpers
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import get_wltp_range, get_ev_database_range
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path='data/cars.db'):
    """
    Add three new range columns and migrate data from legacy columns
    
    New columns:
    - ad_listed_range_km: Range from the car listing ad
    - wltp_reference_range_km: Official WLTP manufacturer range
    - evdb_real_range_km: EV-Database real-world range
    """
    # Convert relative path to absolute
    if not os.path.isabs(db_path):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, db_path)
    
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return False
    
    logger.info(f"Running migration on database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Step 1: Add new columns
        logger.info("Adding new range columns...")
        
        cursor.execute("""
            ALTER TABLE cars ADD COLUMN ad_listed_range_km INTEGER
        """)
        logger.info("  ✓ Added ad_listed_range_km")
        
        cursor.execute("""
            ALTER TABLE cars ADD COLUMN wltp_reference_range_km INTEGER
        """)
        logger.info("  ✓ Added wltp_reference_range_km")
        
        cursor.execute("""
            ALTER TABLE cars ADD COLUMN evdb_real_range_km INTEGER
        """)
        logger.info("  ✓ Added evdb_real_range_km")
        
        # Step 2: Create index on ad_listed_range_km for performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cars_ad_listed_range_km 
            ON cars(ad_listed_range_km)
        """)
        logger.info("  ✓ Created index on ad_listed_range_km")
        
        conn.commit()
        
        # Step 3: Migrate existing data from legacy columns to new columns
        logger.info("\nMigrating existing range data...")
        
        # Copy range_km to ad_listed_range_km for Full Electric vehicles
        cursor.execute("""
            UPDATE cars 
            SET ad_listed_range_km = range_km 
            WHERE fuel_type = 'Full Electric' AND range_km IS NOT NULL
        """)
        full_ev_count = cursor.rowcount
        logger.info(f"  ✓ Migrated {full_ev_count} Full Electric vehicle ranges")
        
        # Copy electric_range_km to ad_listed_range_km for PHEV vehicles
        cursor.execute("""
            UPDATE cars 
            SET ad_listed_range_km = electric_range_km 
            WHERE fuel_type = 'PHEV' AND electric_range_km IS NOT NULL
        """)
        phev_count = cursor.rowcount
        logger.info(f"  ✓ Migrated {phev_count} PHEV vehicle ranges")
        
        conn.commit()
        
        # Step 4: Populate WLTP and EV-Database ranges for existing cars
        logger.info("\nPopulating WLTP and EV-Database ranges...")
        
        cursor.execute("""
            SELECT id, make, model, fuel_type 
            FROM cars 
            WHERE is_available = 1
        """)
        cars = cursor.fetchall()
        
        wltp_count = 0
        evdb_count = 0
        
        for car_id, make, model, fuel_type in cars:
            # Get WLTP range
            wltp_range = get_wltp_range(make, model, fuel_type)
            if wltp_range:
                cursor.execute("""
                    UPDATE cars 
                    SET wltp_reference_range_km = ? 
                    WHERE id = ?
                """, (wltp_range, car_id))
                wltp_count += 1
            
            # Get EV-Database range (only for Full Electric)
            if fuel_type == 'Full Electric':
                evdb_data = get_ev_database_range(make, model)
                if evdb_data and 'real_range' in evdb_data:
                    cursor.execute("""
                        UPDATE cars 
                        SET evdb_real_range_km = ? 
                        WHERE id = ?
                    """, (evdb_data['real_range'], car_id))
                    evdb_count += 1
        
        conn.commit()
        logger.info(f"  ✓ Populated WLTP ranges for {wltp_count} vehicles")
        logger.info(f"  ✓ Populated EV-Database ranges for {evdb_count} vehicles")
        
        # Step 5: Show summary statistics
        logger.info("\nMigration Summary:")
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(ad_listed_range_km) as has_ad_range,
                COUNT(wltp_reference_range_km) as has_wltp,
                COUNT(evdb_real_range_km) as has_evdb
            FROM cars
            WHERE is_available = 1
        """)
        total, has_ad, has_wltp, has_evdb = cursor.fetchone()
        
        logger.info(f"  Total available cars: {total}")
        logger.info(f"  Cars with ad-listed range: {has_ad} ({has_ad*100//total if total else 0}%)")
        logger.info(f"  Cars with WLTP range: {has_wltp} ({has_wltp*100//total if total else 0}%)")
        logger.info(f"  Cars with EV-DB range: {has_evdb} ({has_evdb*100//total if total else 0}%)")
        
        logger.info("\n✅ Migration completed successfully!")
        return True
        
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logger.warning(f"⚠️  Columns already exist - migration may have been run before")
            logger.info("Attempting to populate data for existing columns...")
            
            # Try to populate data even if columns exist
            try:
                cursor.execute("""
                    SELECT id, make, model, fuel_type 
                    FROM cars 
                    WHERE is_available = 1
                """)
                cars = cursor.fetchall()
                
                for car_id, make, model, fuel_type in cars:
                    wltp_range = get_wltp_range(make, model, fuel_type)
                    if wltp_range:
                        cursor.execute("""
                            UPDATE cars 
                            SET wltp_reference_range_km = ? 
                            WHERE id = ? AND wltp_reference_range_km IS NULL
                        """, (wltp_range, car_id))
                    
                    if fuel_type == 'Full Electric':
                        evdb_data = get_ev_database_range(make, model)
                        if evdb_data and 'real_range' in evdb_data:
                            cursor.execute("""
                                UPDATE cars 
                                SET evdb_real_range_km = ? 
                                WHERE id = ? AND evdb_real_range_km IS NULL
                            """, (evdb_data['real_range'], car_id))
                
                conn.commit()
                logger.info("✅ Data population completed!")
                return True
            except Exception as e2:
                logger.error(f"Error populating data: {e2}")
                conn.rollback()
                return False
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
