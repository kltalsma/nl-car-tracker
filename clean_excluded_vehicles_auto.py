#!/usr/bin/env python3
"""
Clean Excluded Vehicles Script (Auto mode)
Removes all vehicles from the database that match the exclusion list in config.yaml
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.database import Database, Car
from utils.helpers import should_exclude_vehicle
import yaml
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def clean_excluded_vehicles(auto_confirm=False):
    """Remove all excluded vehicles from the database"""
    
    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize database
    db = Database(config['database']['path'])
    session = db.Session()
    
    try:
        # Get all cars
        all_cars = session.query(Car).all()
        logger.info(f"Total cars in database: {len(all_cars)}")
        
        # Find excluded cars
        excluded_cars = []
        for car in all_cars:
            make = str(car.make or '')
            model = str(car.model or '')
            
            if should_exclude_vehicle(make, model):
                excluded_cars.append((car.id, make, model))
        
        logger.info(f"Found {len(excluded_cars)} excluded vehicles to remove")
        
        if not excluded_cars:
            logger.info("No excluded vehicles found. Database is clean!")
            return
        
        # Display what will be removed
        print("\n" + "="*60)
        print("VEHICLES TO BE REMOVED:")
        print("="*60)
        
        # Group by make for better display
        by_make = {}
        for car_id, make, model in excluded_cars:
            if make not in by_make:
                by_make[make] = []
            by_make[make].append(model)
        
        for make in sorted(by_make.keys()):
            models = by_make[make]
            print(f"\n{make}: ({len(models)} vehicles)")
            for model in sorted(set(models)):
                count = models.count(model)
                print(f"  - {model} ({count}x)")
        
        print("\n" + "="*60)
        
        # Ask for confirmation (or auto-confirm)
        if not auto_confirm:
            response = input("\nDo you want to remove these vehicles? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                logger.info("Cleanup cancelled by user")
                return
        else:
            print("\nAuto-confirming removal...")
        
        # Remove excluded cars
        deleted_count = 0
        for car_id, make, model in excluded_cars:
            car = session.query(Car).filter(Car.id == car_id).first()
            if car:
                session.delete(car)
                deleted_count += 1
                logger.debug(f"Deleted: {make} {model} (ID: {car_id})")
        
        # Commit changes
        session.commit()
        
        print("\n" + "="*60)
        print(f"✓ Successfully removed {deleted_count} excluded vehicles!")
        print("="*60)
        
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
    # Auto-confirm if --yes flag is provided
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    clean_excluded_vehicles(auto_confirm=auto_confirm)
