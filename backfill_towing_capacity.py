"""
Backfill towing capacity data for existing cars in the database

This script enriches existing car records with towing capacity data from towing_capacity.yaml
"""

import logging
from models.database import Database, Car
from utils.helpers import get_towing_capacity

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_towing_capacity(db_path='data/cars.db', dry_run=False):
    """
    Backfill towing capacity data for all cars in database
    
    Args:
        db_path: Path to database file
        dry_run: If True, only show what would be updated without saving
    """
    db = Database(db_path)
    session = db.get_session()
    
    try:
        # Get all cars where towing capacity is not set
        cars_to_enrich = session.query(Car).filter(Car.towing_capacity_kg.is_(None)).all()
        logger.info(f"Found {len(cars_to_enrich)} cars without towing capacity data")
        
        # Get total cars for statistics
        total_cars = session.query(Car).count()
        already_set = total_cars - len(cars_to_enrich)
        
        stats = {
            'total': total_cars,
            'already_set': already_set,
            'enriched': 0,
            'not_found': 0,
            'zero_capacity': 0  # Cars rated at 0 kg (not rated for towing)
        }
        
        for car in cars_to_enrich:
            if not car.make or not car.model:
                stats['not_found'] += 1
                continue
            
            try:
                towing_capacity = get_towing_capacity(car.make, car.model)
                if towing_capacity is not None:
                    if towing_capacity == 0:
                        logger.info(f"✓ {car.make} {car.model}: Not rated for towing (0 kg)")
                        stats['zero_capacity'] += 1
                    else:
                        logger.info(f"✓ Enriching {car.make} {car.model}: {towing_capacity} kg")
                    
                    if not dry_run:
                        car.towing_capacity_kg = towing_capacity
                    stats['enriched'] += 1
                    
                    # Commit every 50 updates to avoid long transactions
                    if stats['enriched'] % 50 == 0 and not dry_run:
                        session.commit()
                        logger.info(f"  Committed batch update (progress: {stats['enriched']} enriched)")
                else:
                    stats['not_found'] += 1
                    logger.debug(f"  No towing capacity data found for {car.make} {car.model}")
            except Exception as e:
                logger.warning(f"  Error getting towing capacity for {car.make} {car.model}: {e}")
                stats['not_found'] += 1
        
        # Final commit
        if not dry_run:
            session.commit()
            logger.info("All changes committed to database")
        
        # Print statistics
        logger.info("\n" + "="*60)
        logger.info("TOWING CAPACITY ENRICHMENT STATISTICS")
        logger.info("="*60)
        logger.info(f"Total cars in database: {stats['total']}")
        logger.info(f"Already had towing capacity: {stats['already_set']}")
        logger.info(f"")
        logger.info(f"Enrichment results:")
        logger.info(f"  - Successfully enriched: {stats['enriched']}")
        logger.info(f"    • Can tow (>0 kg): {stats['enriched'] - stats['zero_capacity']}")
        logger.info(f"    • Not rated for towing (0 kg): {stats['zero_capacity']}")
        logger.info(f"  - No data found: {stats['not_found']}")
        logger.info(f"")
        logger.info(f"Final coverage: {((stats['enriched'] + stats['already_set']) / stats['total'] * 100):.1f}%")
        logger.info("="*60)
        
        if dry_run:
            logger.info("\nDRY RUN - No changes were saved to database")
        
    except Exception as e:
        logger.error(f"Error during backfill: {e}")
        if not dry_run:
            session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill towing capacity data for existing cars')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without saving')
    parser.add_argument('--db-path', default='data/cars.db', help='Path to database file')
    
    args = parser.parse_args()
    
    logger.info("Starting towing capacity backfill...")
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")
    
    backfill_towing_capacity(db_path=args.db_path, dry_run=args.dry_run)
    logger.info("Backfill complete!")
