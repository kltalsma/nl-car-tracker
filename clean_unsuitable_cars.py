#!/usr/bin/env python3
"""
Clean up unsuitable vehicles from the database.
Removes vehicles that exceed mileage or price limits.
"""

import sys
import os
import argparse

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

# Limits
MAX_MILEAGE_KM = 80_000
MAX_PRICE_EUR = 40_000

def clean_unsuitable_cars(execute: bool = False):
    """Remove vehicles exceeding mileage or price limits"""
    try:
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Initialize database
        db = Database(config['database']['path'])
        session = db.Session()
        
        # Get current count
        total_cars = session.query(Car).count()
        logger.info(f"Total cars in database: {total_cars}")
        
        # Find unsuitable vehicles
        high_mileage = session.query(Car).filter(Car.mileage_km > MAX_MILEAGE_KM).all()
        high_price = session.query(Car).filter(Car.price > MAX_PRICE_EUR).all()
        
        # Combine and deduplicate
        unsuitable_cars = {car.id: car for car in high_mileage + high_price}
        unsuitable_cars = list(unsuitable_cars.values())
        
        if not unsuitable_cars:
            logger.info("No unsuitable vehicles found.")
            return
        
        # Statistics
        mileage_only = [c for c in unsuitable_cars if c.mileage_km > MAX_MILEAGE_KM]
        price_only = [c for c in unsuitable_cars if c.price > MAX_PRICE_EUR]
        both = [c for c in unsuitable_cars if c.mileage_km > MAX_MILEAGE_KM and c.price > MAX_PRICE_EUR]
        
        logger.info(f"Found {len(unsuitable_cars)} unsuitable vehicles:")
        logger.info(f"  - {len(mileage_only)} exceed {MAX_MILEAGE_KM:,} km")
        logger.info(f"  - {len(price_only)} exceed €{MAX_PRICE_EUR:,}")
        logger.info(f"  - {len(both)} exceed both limits")
        
        # Display vehicles to be removed
        print("\n" + "="*80)
        print("VEHICLES TO BE REMOVED:")
        print("="*80)
        
        if mileage_only:
            print(f"\n🚗 High Mileage (>{MAX_MILEAGE_KM:,} km): {len(mileage_only)} vehicles")
            print("-" * 80)
            for i, car in enumerate(sorted(mileage_only, key=lambda c: c.mileage_km, reverse=True)[:15]):
                print(f"  {car.make} {car.model} ({car.year}) - {car.mileage_km:,} km")
            if len(mileage_only) > 15:
                print(f"  ... and {len(mileage_only) - 15} more")
        
        if price_only:
            print(f"\n💰 High Price (>€{MAX_PRICE_EUR:,}): {len(price_only)} vehicles")
            print("-" * 80)
            for car in sorted(price_only, key=lambda c: c.price, reverse=True):
                details = f"  {car.make} {car.model} ({car.year}) - €{car.price:,}"
                if car.mileage_km > MAX_MILEAGE_KM:
                    details += f" + {car.mileage_km:,} km"
                print(details)
        
        mileages = [c.mileage_km for c in mileage_only if c.mileage_km]
        if mileages:
            print(f"\nMileage stats: {min(mileages):,} - {max(mileages):,} km (avg: {sum(mileages)//len(mileages):,} km)")
        
        print("\n" + "="*80)
        
        # Confirm removal
        if not execute:
            response = input(f"\nRemove {len(unsuitable_cars)} vehicles? (yes/no): ").strip().lower()
            if response != 'yes':
                logger.info("Cleanup cancelled by user.")
                return
        else:
            logger.info(f"--execute flag provided, removing {len(unsuitable_cars)} vehicles...")
        
        # Remove vehicles
        removed_count = 0
        for car in unsuitable_cars:
            session.delete(car)
            removed_count += 1
        
        session.commit()
        
        # Final stats
        remaining = session.query(Car).count()
        logger.info(f"\n✅ Successfully removed {removed_count} vehicles")
        logger.info(f"Remaining vehicles: {remaining}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean unsuitable vehicles from database")
    parser.add_argument('--execute', action='store_true', 
                       help='Execute cleanup without confirmation prompt')
    args = parser.parse_args()
    
    clean_unsuitable_cars(execute=args.execute)
