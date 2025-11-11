"""
Backfill enrichment data for existing cars in the database

This script enriches existing car records with:
- WLTP reference range (from wltp_ranges.yaml)
- EV-Database real-world range (from ev_database_ranges.yaml)
- Boot space capacity (from boot_space.yaml)
"""

import logging
from models.database import Database, Car
from utils.helpers import get_wltp_range, get_ev_database_range, get_boot_space

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_enrichment_data(db_path='data/cars.db', dry_run=False):
    """
    Backfill enrichment data for all cars in database
    
    Args:
        db_path: Path to database file
        dry_run: If True, only show what would be updated without saving
    """
    db = Database(db_path)
    session = db.get_session()
    
    try:
        # Get all cars
        all_cars = session.query(Car).all()
        logger.info(f"Found {len(all_cars)} total cars in database")
        
        stats = {
            'total': len(all_cars),
            'wltp_enriched': 0,
            'evdb_enriched': 0,
            'boot_enriched': 0,
            'boot_seats_down_enriched': 0,
            'wltp_already_set': 0,
            'evdb_already_set': 0,
            'boot_already_set': 0,
            'wltp_not_found': 0,
            'evdb_not_found': 0,
            'boot_not_found': 0
        }
        
        for car in all_cars:
            updated = False
            
            # Enrich WLTP range if not already set
            if not car.wltp_reference_range_km and car.make and car.model:
                try:
                    wltp_range = get_wltp_range(car.make, car.model, car.fuel_type, car.ad_listed_range_km)
                    if wltp_range:
                        logger.info(f"✓ Enriching WLTP for {car.make} {car.model}: {wltp_range} km")
                        if not dry_run:
                            car.wltp_reference_range_km = wltp_range
                        stats['wltp_enriched'] += 1
                        updated = True
                    else:
                        stats['wltp_not_found'] += 1
                        logger.debug(f"  No WLTP data found for {car.make} {car.model}")
                except Exception as e:
                    logger.warning(f"  Error getting WLTP for {car.make} {car.model}: {e}")
                    stats['wltp_not_found'] += 1
            elif car.wltp_reference_range_km:
                stats['wltp_already_set'] += 1
            
            # Enrich EV-Database range if not already set
            if not car.evdb_real_range_km and car.make and car.model:
                try:
                    evdb_data = get_ev_database_range(car.make, car.model, car.fuel_type)
                    if evdb_data and 'real_range' in evdb_data:
                        logger.info(f"✓ Enriching EV-DB for {car.make} {car.model}: {evdb_data['real_range']} km")
                        if not dry_run:
                            car.evdb_real_range_km = evdb_data['real_range']
                        stats['evdb_enriched'] += 1
                        updated = True
                    else:
                        stats['evdb_not_found'] += 1
                        logger.debug(f"  No EV-DB data found for {car.make} {car.model}")
                except Exception as e:
                    logger.warning(f"  Error getting EV-DB for {car.make} {car.model}: {e}")
                    stats['evdb_not_found'] += 1
            elif car.evdb_real_range_km:
                stats['evdb_already_set'] += 1
            
            # Enrich boot space if not already set
            if not car.storage_capacity_liters and car.make and car.model:
                try:
                    boot_space = get_boot_space(car.make, car.model)
                    if boot_space:
                        if 'normal' in boot_space and boot_space['normal']:
                            logger.info(f"✓ Enriching boot space for {car.make} {car.model}: {boot_space['normal']} L")
                            if not dry_run:
                                car.storage_capacity_liters = boot_space['normal']
                            stats['boot_enriched'] += 1
                            updated = True
                        
                        if 'seats_down' in boot_space and boot_space['seats_down']:
                            logger.info(f"✓ Enriching boot space (seats down) for {car.make} {car.model}: {boot_space['seats_down']} L")
                            if not dry_run:
                                car.storage_capacity_seats_down_liters = boot_space['seats_down']
                            stats['boot_seats_down_enriched'] += 1
                            updated = True
                    else:
                        stats['boot_not_found'] += 1
                        logger.debug(f"  No boot space data found for {car.make} {car.model}")
                except Exception as e:
                    logger.warning(f"  Error getting boot space for {car.make} {car.model}: {e}")
                    stats['boot_not_found'] += 1
            elif car.storage_capacity_liters:
                stats['boot_already_set'] += 1
            
            # Commit every 50 updates to avoid long transactions
            if updated and not dry_run and stats['wltp_enriched'] % 50 == 0:
                session.commit()
                logger.info(f"  Committed batch update (progress: {stats['wltp_enriched']} enriched)")
        
        # Final commit
        if not dry_run:
            session.commit()
            logger.info("All changes committed to database")
        
        # Print statistics
        logger.info("\n" + "="*60)
        logger.info("ENRICHMENT STATISTICS")
        logger.info("="*60)
        logger.info(f"Total cars processed: {stats['total']}")
        logger.info("")
        logger.info(f"WLTP Range:")
        logger.info(f"  - Enriched: {stats['wltp_enriched']}")
        logger.info(f"  - Already set: {stats['wltp_already_set']}")
        logger.info(f"  - Not found: {stats['wltp_not_found']}")
        logger.info(f"  - Coverage: {((stats['wltp_enriched'] + stats['wltp_already_set']) / stats['total'] * 100):.1f}%")
        logger.info("")
        logger.info(f"EV-Database Range:")
        logger.info(f"  - Enriched: {stats['evdb_enriched']}")
        logger.info(f"  - Already set: {stats['evdb_already_set']}")
        logger.info(f"  - Not found: {stats['evdb_not_found']}")
        logger.info(f"  - Coverage: {((stats['evdb_enriched'] + stats['evdb_already_set']) / stats['total'] * 100):.1f}%")
        logger.info("")
        logger.info(f"Boot Space:")
        logger.info(f"  - Enriched (normal): {stats['boot_enriched']}")
        logger.info(f"  - Enriched (seats down): {stats['boot_seats_down_enriched']}")
        logger.info(f"  - Already set: {stats['boot_already_set']}")
        logger.info(f"  - Not found: {stats['boot_not_found']}")
        logger.info(f"  - Coverage: {((stats['boot_enriched'] + stats['boot_already_set']) / stats['total'] * 100):.1f}%")
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
    
    parser = argparse.ArgumentParser(description='Backfill enrichment data for existing cars')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without saving')
    parser.add_argument('--db-path', default='data/cars.db', help='Path to database file')
    
    args = parser.parse_args()
    
    logger.info("Starting enrichment backfill...")
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")
    
    backfill_enrichment_data(db_path=args.db_path, dry_run=args.dry_run)
    logger.info("Backfill complete!")
