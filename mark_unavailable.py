#!/usr/bin/env python3
"""
Mark Car as Unavailable/Sold

Quick utility to manually mark cars as unavailable when you spot they're sold
but the availability checker hasn't caught it yet.

Usage:
    python mark_unavailable.py <car_id_or_url> [--reason "reason text"]
    
Examples:
    python mark_unavailable.py 43
    python mark_unavailable.py 43 --reason "VERKOCHT banner visible"
    python mark_unavailable.py "https://www.autoscout24.nl/aanbod/...f7e5c834-56d6..."
"""

import argparse
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

def extract_external_id_from_url(url):
    """Extract external ID from AutoScout24 or other website URLs"""
    if 'autoscout24.nl' in url:
        # Extract the UUID at the end of AutoScout24 URLs
        parts = url.split('/')
        for part in parts:
            if len(part) == 36 and part.count('-') == 4:  # UUID format
                # Get everything after 'aanbod/' to construct the external_id
                try:
                    aanbod_idx = parts.index('aanbod')
                    listing_slug = parts[aanbod_idx + 1].split('?')[0]  # Remove query params
                    return f"autoscout24_{listing_slug}"
                except (ValueError, IndexError):
                    return None
    elif 'autotrack.nl' in url:
        # autotrack uses numeric IDs
        parts = url.split('/')
        for part in parts:
            if part.isdigit() and len(part) > 4:
                return f"autotrack_{part}"
    elif 'vandenbrug.nl' in url:
        # Extract ID from vandenbrug URLs
        if '/occasions/' in url:
            parts = url.split('/occasions/')
            if len(parts) > 1:
                listing_id = parts[1].split('/')[0].split('?')[0]
                return f"vandenbrug_{listing_id}"
    elif 'gaspedaal.nl' in url:
        # Extract ID from gaspedaal URLs
        if '/occasion/' in url:
            parts = url.split('/occasion/')
            if len(parts) > 1:
                listing_id = parts[1].split('/')[0].split('?')[0]
                return f"gaspedaal_{listing_id}"
    
    return None

def mark_car_unavailable(db_path, car_identifier, reason):
    """Mark a car as unavailable by ID or URL"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Determine if identifier is numeric ID or URL
    if car_identifier.isdigit():
        # It's a database ID
        cursor.execute("""
            SELECT id, external_id, make, model, year, price, is_available 
            FROM cars 
            WHERE id = ?
        """, (int(car_identifier),))
    elif car_identifier.startswith('http'):
        # It's a URL - extract external_id
        external_id = extract_external_id_from_url(car_identifier)
        if not external_id:
            print(f"❌ Could not extract car ID from URL: {car_identifier}")
            print("   Supported sites: autoscout24.nl, autotrack.nl, vandenbrug.nl, gaspedaal.nl")
            conn.close()
            return False
        
        cursor.execute("""
            SELECT id, external_id, make, model, year, price, is_available 
            FROM cars 
            WHERE external_id = ?
        """, (external_id,))
    else:
        # Try as external_id directly
        cursor.execute("""
            SELECT id, external_id, make, model, year, price, is_available 
            FROM cars 
            WHERE external_id = ?
        """, (car_identifier,))
    
    car = cursor.fetchone()
    
    if not car:
        print(f"❌ Car not found: {car_identifier}")
        conn.close()
        return False
    
    car_id, external_id, make, model, year, price, is_available = car
    
    # Show current status
    print(f"\n📋 Found car:")
    print(f"   ID: {car_id}")
    print(f"   Car: {make} {model} ({year})")
    print(f"   Price: €{price:,.0f}")
    print(f"   Current status: {'Available' if is_available else 'Unavailable'}")
    print(f"   External ID: {external_id}")
    
    if not is_available:
        print(f"\n⚠️  Car is already marked as unavailable")
        # Get current reason
        cursor.execute("SELECT unavailable_reason FROM cars WHERE id = ?", (car_id,))
        current_reason = cursor.fetchone()[0]
        if current_reason:
            print(f"   Current reason: {current_reason}")
        
        response = input("\n   Update anyway? (y/N): ")
        if response.lower() != 'y':
            print("   Cancelled.")
            conn.close()
            return False
    
    # Confirm action
    print(f"\n❓ Mark as unavailable?")
    print(f"   Reason: {reason}")
    response = input("   Confirm (y/N): ")
    
    if response.lower() != 'y':
        print("   Cancelled.")
        conn.close()
        return False
    
    # Update the car
    cursor.execute("""
        UPDATE cars 
        SET is_available = 0,
            unavailable_reason = ?,
            marked_unavailable_at = ?
        WHERE id = ?
    """, (reason, datetime.now().isoformat(), car_id))
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Successfully marked car as unavailable!")
    print(f"   {make} {model} ({year}) - €{price:,.0f}")
    print(f"   Reason: {reason}")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Mark a car as unavailable/sold in the database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 43
  %(prog)s 43 --reason "VERKOCHT banner visible on images"
  %(prog)s "https://www.autoscout24.nl/aanbod/kia-ev6-..."
  %(prog)s --list-recent 10
        """
    )
    
    parser.add_argument(
        'identifier',
        nargs='?',
        help='Car database ID, external_id, or full listing URL'
    )
    
    parser.add_argument(
        '--reason',
        '-r',
        default='Manually marked as sold/unavailable',
        help='Reason for marking unavailable (default: "Manually marked as sold/unavailable")'
    )
    
    parser.add_argument(
        '--db',
        default='data/cars.db',
        help='Path to database file (default: data/cars.db)'
    )
    
    parser.add_argument(
        '--list-recent',
        type=int,
        metavar='N',
        help='List N most recently added available cars'
    )
    
    args = parser.parse_args()
    
    # Check if database exists
    if not Path(args.db).exists():
        print(f"❌ Database not found: {args.db}")
        return 1
    
    # List recent cars if requested
    if args.list_recent:
        conn = sqlite3.connect(args.db)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, make, model, year, price, mileage_km, source_website, first_seen
            FROM cars 
            WHERE is_available = 1
            ORDER BY first_seen DESC
            LIMIT ?
        """, (args.list_recent,))
        
        print(f"\n📋 {args.list_recent} Most recently added available cars:\n")
        print(f"{'ID':<6} {'Make':<12} {'Model':<20} {'Year':<6} {'Price':<12} {'Mileage':<10} {'Source':<20} {'Added'}")
        print("-" * 120)
        
        for row in cursor.fetchall():
            car_id, make, model, year, price, mileage, source, first_seen = row
            first_seen_date = datetime.fromisoformat(first_seen).strftime('%Y-%m-%d')
            print(f"{car_id:<6} {make:<12} {model:<20} {year:<6} €{price:>10,.0f} {mileage:>9,} km {source:<20} {first_seen_date}")
        
        print()
        conn.close()
        return 0
    
    # Require identifier if not listing
    if not args.identifier:
        parser.print_help()
        print("\n❌ Error: Please provide a car identifier (ID or URL) or use --list-recent")
        return 1
    
    # Mark the car
    success = mark_car_unavailable(args.db, args.identifier, args.reason)
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
