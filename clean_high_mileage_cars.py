#!/usr/bin/env python3
"""
Clean High Mileage Cars Script
Removes all vehicles from the database that exceed the maximum mileage threshold
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.database import Database, Car
import yaml
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Maximum mileage threshold in kilometers
MAX_MILEAGE_KM = 80000

def clean_high_mileage_cars():
    """Remove all cars exceeding the maximum mileage threshold"""
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize database
    db = Database(config['database']['path'])
    session = db.Session()
    
    try:
        # Get all cars
        total_cars = session.query(Car).count()
        logger.info(f"Total cars in database: {total_cars}")
        
        # Find high-mileage cars
        high_mileage_cars = session.query(Car).filter(
            Car.mileage_km > MAX_MILEAGE_KM
        ).all()
        
        logger.info(f"Found {len(high_mileage_cars)} cars exceeding {MAX_MILEAGE_KM:,} km")
        
        if not high_mileage_cars:
            logger.info("No high-mileage vehicles found. Database is clean!")
            return
        
        # Display what will be removed
        print("\n" + "="*70)
        print(f"VEHICLES TO BE REMOVED (Mileage > {MAX_MILEAGE_KM:,} km):")
        print("="*70)
        
        # Sort by mileage for better display
        high_mileage_cars.sort(key=lambda c: c.mileage_km, reverse=True)
        
        for car in high_mileage_cars[:20]:  # Show first 20
            print(f"{car.make} {car.model} ({car.year}) - {car.mileage_km:,} km - €{car.price:,.0f}")
        
        if len(high_mileage_cars) > 20:
            print(f"... and {len(high_mileage_cars) - 20} more")
        
        # Show mileage distribution
        mileages = [c.mileage_km for c in high_mileage_cars]
        print(f"\nMileage range: {min(mileages):,} km - {max(mileages):,} km")
        print(f"Average mileage: {sum(mileages)//len(mileages):,} km")
        
        print("\n" + "="*70)
        
        # Ask for confirmation
        response = input(f"\nRemove {len(high_mileage_cars)} vehicles? (yes/no): ").strip().lower()
        
        if response not in ['yes', 'y']:
            logger.info("Cleanup cancelled by user")
            return
        
        # Remove high-mileage cars
        deleted_count = 0
        for car in high_mileage_cars:
            session.delete(car)
            deleted_count += 1
            logger.debug(f"Deleted: {car.make} {car.model} - {car.mileage_km:,} km (ID: {car.id})")
        
        # Commit changes
        session.commit()
        
        print("\n" + "="*70)
        print(f"✓ Successfully removed {deleted_count} high-mileage vehicles!")
        print("="*70)
        
        # Show updated stats
        remaining_cars = session.query(Car).count()
        logger.info(f"Remaining cars in database: {remaining_cars}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        session.rollback()
        raise
    finally:
        session.close()

if __name__ == '__main__':
    clean_high_mileage_cars()
