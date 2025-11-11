#!/usr/bin/env python3
"""
Recalculate driving distances for all cars in database using OSRM API

This script updates the distance_from_heerenveen_km field with actual
driving distances instead of geodesic (straight-line) distances.
"""

import sys
import os
import argparse
import sqlite3

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.helpers import calculate_distance_from_heerenveen, extract_city_from_address
import time


def recalculate_distances(db_path: str = 'cars.db', dry_run: bool = True):
    """
    Recalculate distances from Heerenveen for all cars
    
    Args:
        db_path: Path to SQLite database
        dry_run: If True, only show what would be changed without committing
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all cars with location data
    cursor.execute("""
        SELECT id, dealer_location, location_city, distance_from_heerenveen_km
        FROM cars
        WHERE dealer_location IS NOT NULL OR location_city IS NOT NULL
    """)
    
    cars = cursor.fetchall()
    total = len(cars)
    print(f"\nFound {total} cars with location data")
    print(f"Mode: {'DRY RUN (no changes will be made)' if dry_run else 'COMMIT (changes will be saved)'}")
    print("-" * 80)
    
    updated = 0
    skipped = 0
    failed = 0
    
    for car_id, dealer_location, location_city, old_distance in cars:
        # Use city if available, otherwise dealer_location
        location_to_use = location_city or dealer_location
        
        if not location_to_use:
            skipped += 1
            continue
        
        try:
            # Calculate new driving distance using OSRM
            new_distance = calculate_distance_from_heerenveen(location=location_to_use)
            
            if new_distance is None:
                print(f"❌ Car ID {car_id}: Failed to calculate distance for {location_to_use}")
                failed += 1
                continue
            
            # Show difference
            if old_distance is not None:
                diff = new_distance - old_distance
                diff_pct = (diff / old_distance * 100) if old_distance > 0 else 0
                status = "↗" if diff > 0 else "↘" if diff < 0 else "="
                print(f"{status} Car ID {car_id}: {location_to_use:30s} | Old: {old_distance:6.2f} km → New: {new_distance:6.2f} km (diff: {diff:+6.2f} km, {diff_pct:+5.1f}%)")
            else:
                print(f"✓ Car ID {car_id}: {location_to_use:30s} | New: {new_distance:6.2f} km")
            
            # Update database
            if not dry_run:
                cursor.execute("""
                    UPDATE cars
                    SET distance_from_heerenveen_km = ?
                    WHERE id = ?
                """, (new_distance, car_id))
            
            updated += 1
            
            # Small delay to be nice to OSRM API
            time.sleep(0.1)
            
        except Exception as e:
            print(f"❌ Car ID {car_id}: Error processing {location_to_use}: {e}")
            failed += 1
            continue
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    
    print("-" * 80)
    print(f"\nResults:")
    print(f"  Total cars checked: {total}")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    
    if dry_run:
        print(f"\n⚠️  DRY RUN - No changes were saved to the database")
        print(f"   Run with --commit to apply changes")
    else:
        print(f"\n✅ Changes committed to database")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recalculate driving distances from Heerenveen')
    parser.add_argument('--db', default='cars.db', help='Path to database file')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Show changes without committing (default)')
    parser.add_argument('--commit', action='store_true', help='Commit changes to database')
    
    args = parser.parse_args()
    
    # If --commit is specified, turn off dry-run
    dry_run = not args.commit
    
    recalculate_distances(args.db, dry_run=dry_run)
