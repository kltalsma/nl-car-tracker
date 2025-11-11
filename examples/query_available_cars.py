#!/usr/bin/env python3
"""
Example script demonstrating how to query available and unavailable cars
using the new helper methods and fields.
"""
from models.database import Database, Car
from datetime import datetime, timedelta


def main():
    # Initialize database
    db = Database('data/cars.db')
    session = db.get_session()
    
    print("=" * 70)
    print("NL Car Tracker - Availability Query Examples")
    print("=" * 70)
    
    # Example 1: Get all available cars
    print("\n1. Get all available cars:")
    available_cars = session.query(Car).filter(Car.is_available == True).all()
    print(f"   Total available cars: {len(available_cars)}")
    
    # Example 2: Get unavailable cars
    print("\n2. Get all unavailable cars:")
    unavailable_cars = session.query(Car).filter(Car.is_available == False).all()
    print(f"   Total unavailable cars: {len(unavailable_cars)}")
    
    # Example 3: Get unavailable cars by reason
    print("\n3. Unavailable cars grouped by reason:")
    reasons = session.query(Car.unavailable_reason).filter(
        Car.is_available == False
    ).distinct().all()
    
    for (reason,) in reasons:
        count = session.query(Car).filter(
            Car.is_available == False,
            Car.unavailable_reason == reason
        ).count()
        print(f"   {reason}: {count} cars")
    
    # Example 4: Show details of unavailable cars
    if unavailable_cars:
        print("\n4. Details of unavailable cars:")
        for car in unavailable_cars[:5]:  # Show first 5
            print(f"\n   {car.year} {car.make} {car.model}")
            print(f"   - Source: {car.source_website}")
            print(f"   - Last seen: {car.last_seen}")
            print(f"   - Reason: {car.unavailable_reason}")
            print(f"   - Marked unavailable: {car.marked_unavailable_at}")
            print(f"   - URL: {car.listing_url[:60]}...")
    
    # Example 5: Find cars that became unavailable recently
    print("\n5. Cars marked unavailable in the last 7 days:")
    cutoff = datetime.utcnow() - timedelta(days=7)
    recent_unavailable = session.query(Car).filter(
        Car.is_available == False,
        Car.marked_unavailable_at >= cutoff
    ).all()
    print(f"   {len(recent_unavailable)} cars became unavailable in the last week")
    
    # Example 6: Using the helper method - mark a car unavailable
    print("\n6. Example: Marking a car unavailable manually")
    print("   (Not executing - this is just an example)")
    print("   ")
    print("   car = session.query(Car).filter(Car.external_id == 'some_id').first()")
    print("   if car:")
    print("       car.mark_unavailable('manual')")
    print("       session.commit()")
    
    # Example 7: Re-activate a car that becomes available again
    print("\n7. Example: Re-activating a car")
    print("   (Not executing - this is just an example)")
    print("   ")
    print("   car = session.query(Car).filter(Car.external_id == 'some_id').first()")
    print("   if car and not car.is_available:")
    print("       car.mark_available()")
    print("       session.commit()")
    
    # Statistics
    print("\n" + "=" * 70)
    print("Database Statistics:")
    print("=" * 70)
    total = session.query(Car).count()
    available = session.query(Car).filter(Car.is_available == True).count()
    unavailable = session.query(Car).filter(Car.is_available == False).count()
    
    print(f"Total cars: {total}")
    print(f"Available: {available} ({100*available/total:.1f}%)")
    print(f"Unavailable: {unavailable} ({100*unavailable/total:.1f}%)")
    print("=" * 70)
    
    session.close()


if __name__ == "__main__":
    main()
