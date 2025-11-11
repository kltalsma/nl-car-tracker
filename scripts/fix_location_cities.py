#!/usr/bin/env python3
"""
Migration script to fix location_city field in existing cars.

This script reads the dealer_location field (which contains full addresses)
and extracts just the city name to store in location_city field.

Usage:
    python scripts/fix_location_cities.py
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.helpers import extract_city_from_address


def fix_location_cities(db_path='data/cars.db', dry_run=False):
    """
    Fix location_city field for all cars in database.
    
    Args:
        db_path: Path to the SQLite database
        dry_run: If True, only show what would be changed without making changes
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all cars that have dealer_location but location_city is wrong
    # (either NULL or contains full address instead of just city)
    cursor.execute("""
        SELECT id, dealer_location, location_city 
        FROM cars 
        WHERE dealer_location IS NOT NULL
    """)
    
    cars = cursor.fetchall()
    total_cars = len(cars)
    updated_count = 0
    failed_count = 0
    skipped_count = 0
    
    print(f"Found {total_cars} cars with dealer_location data")
    print(f"Dry run mode: {dry_run}")
    print("-" * 80)
    
    for car_id, dealer_location, current_city in cars:
        # Extract the city from the full address
        new_city = extract_city_from_address(dealer_location)
        
        # Check if extraction was successful
        if not new_city:
            print(f"❌ Car ID {car_id}: Could not extract city from '{dealer_location}'")
            failed_count += 1
            continue
        
        # Check if city is already correct
        if current_city == new_city:
            skipped_count += 1
            continue
        
        # Show what will be changed
        print(f"Car ID {car_id}:")
        print(f"  Dealer location: {dealer_location}")
        print(f"  Old city:        {current_city}")
        print(f"  New city:        {new_city}")
        
        # Update the database (if not in dry run mode)
        if not dry_run:
            cursor.execute("""
                UPDATE cars 
                SET location_city = ? 
                WHERE id = ?
            """, (new_city, car_id))
            print(f"  ✓ Updated")
        else:
            print(f"  (Would update)")
        
        print()
        updated_count += 1
    
    # Commit changes if not in dry run mode
    if not dry_run:
        conn.commit()
        print("Changes committed to database")
    else:
        print("Dry run - no changes made to database")
    
    conn.close()
    
    # Print summary
    print("-" * 80)
    print(f"Summary:")
    print(f"  Total cars checked:    {total_cars}")
    print(f"  Cars to be updated:    {updated_count}")
    print(f"  Cars already correct:  {skipped_count}")
    print(f"  Cars failed to parse:  {failed_count}")
    
    return updated_count, failed_count


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Fix location_city field in cars database')
    parser.add_argument('--db', default='data/cars.db', help='Path to database file')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be changed without making changes')
    parser.add_argument('--commit', action='store_true',
                        help='Actually commit the changes to database')
    
    args = parser.parse_args()
    
    # If --commit is not specified, default to dry run
    dry_run = not args.commit
    
    if dry_run:
        print("=" * 80)
        print("DRY RUN MODE - No changes will be made")
        print("Use --commit to actually update the database")
        print("=" * 80)
        print()
    
    updated, failed = fix_location_cities(args.db, dry_run=dry_run)
    
    if not dry_run:
        print(f"\n✓ Successfully updated {updated} cars")
        if failed > 0:
            print(f"⚠ Failed to extract city for {failed} cars")
    else:
        print(f"\nWould update {updated} cars (run with --commit to apply)")
