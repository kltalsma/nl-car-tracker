#!/usr/bin/env python3
"""
Hybrid cleanup strategy (Option C):
- Keep: Cars within 80km (all)
- Keep: Preferred cars 80-150km
- Keep: Unknown location cars from autotrack.nl (might be local)
- Try to geocode: Unknown location autoscout24.nl cars (have addresses)
- Remove: Non-preferred cars 80-150km
- Remove: All cars beyond 150km
"""

import yaml
from models import Car, Database
from sqlalchemy import and_, or_
from utils.helpers import calculate_distance_from_heerenveen, get_coordinates

# Load config
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Get preferred makes and models
preferred_config = config.get('preferred_cars', {})
preferred_makes = [m.lower() for m in preferred_config.get('makes', [])]
preferred_models = [m.lower() for m in preferred_config.get('models', [])]

print("=" * 70)
print("HYBRID DISTANCE-BASED DATABASE CLEANUP")
print("=" * 70)
print("Preferred makes:", ', '.join(preferred_makes))
print("Preferred models:", ', '.join(preferred_models))
print()

db = Database()
session = db.get_session()

try:
    # Get counts before cleanup
    total_cars = session.query(Car).filter(Car.is_available == True).count()
    within_80 = session.query(Car).filter(
        and_(Car.is_available == True, Car.distance_from_heerenveen_km <= 80)
    ).count()
    between_80_150 = session.query(Car).filter(
        and_(
            Car.is_available == True,
            Car.distance_from_heerenveen_km > 80,
            Car.distance_from_heerenveen_km <= 150
        )
    ).count()
    beyond_150 = session.query(Car).filter(
        and_(Car.is_available == True, Car.distance_from_heerenveen_km > 150)
    ).count()
    no_location = session.query(Car).filter(
        and_(Car.is_available == True, Car.distance_from_heerenveen_km == None)
    ).count()
    
    print(f"Current database state:")
    print(f"  Total available cars: {total_cars}")
    print(f"  Within 80km: {within_80}")
    print(f"  80-150km: {between_80_150}")
    print(f"  Beyond 150km: {beyond_150}")
    print(f"  No location: {no_location}")
    print()
    
    # STEP 1: Try to geocode unknown locations from autoscout24
    print("STEP 1: Attempting to geocode unknown locations...")
    print("-" * 70)
    
    unknown_location_cars = session.query(Car).filter(
        and_(
            Car.is_available == True,
            Car.distance_from_heerenveen_km == None
        )
    ).all()
    
    geocoded_count = 0
    autotrack_no_location = 0
    autoscout_no_location = 0
    
    for car in unknown_location_cars:
        if car.source_website == 'autotrack.nl':
            autotrack_no_location += 1
            continue  # Skip autotrack - keeping them
        
        # Try to geocode autoscout24 cars with dealer_location
        if car.dealer_location:
            try:
                coords = get_coordinates(car.dealer_location)
                if coords:
                    distance = calculate_distance_from_heerenveen(coords=coords)
                    if distance and distance < 500:  # Sanity check
                        car.distance_from_heerenveen_km = distance
                        geocoded_count += 1
                        print(f"  ✓ Geocoded: {car.make} {car.model} at {car.dealer_location} = {distance:.1f}km")
                    else:
                        print(f"  ✗ Suspicious distance for {car.make} {car.model}: {distance}km")
                        autoscout_no_location += 1
                else:
                    autoscout_no_location += 1
            except Exception as e:
                print(f"  ✗ Geocoding failed for {car.make} {car.model}: {e}")
                autoscout_no_location += 1
        else:
            autoscout_no_location += 1
    
    if geocoded_count > 0:
        session.commit()
    
    print(f"\nGeocoding results:")
    print(f"  Successfully geocoded: {geocoded_count}")
    print(f"  autotrack.nl without location (keeping): {autotrack_no_location}")
    print(f"  autoscout24.nl still without location: {autoscout_no_location}")
    print()
    
    # STEP 2: Categorize 80-150km cars
    print("STEP 2: Categorizing cars in 80-150km range...")
    print("-" * 70)
    
    cars_80_150 = session.query(Car).filter(
        and_(
            Car.is_available == True,
            Car.distance_from_heerenveen_km > 80,
            Car.distance_from_heerenveen_km <= 150
        )
    ).all()
    
    non_preferred_80_150 = []
    preferred_80_150 = []
    
    for car in cars_80_150:
        car_make = car.make.lower() if car.make else ''
        car_model = car.model.lower() if car.model else ''
        
        is_preferred = (
            car_make in preferred_makes or
            any(pm in car_model for pm in preferred_models)
        )
        
        if is_preferred:
            preferred_80_150.append(car)
        else:
            non_preferred_80_150.append(car)
    
    print(f"  Preferred cars to keep: {len(preferred_80_150)}")
    print(f"  Non-preferred cars to remove: {len(non_preferred_80_150)}")
    print()
    
    # STEP 3: Categorize newly geocoded cars
    print("STEP 3: Checking newly geocoded cars...")
    print("-" * 70)
    
    newly_geocoded_to_remove = []
    newly_geocoded_to_keep = []
    
    for car in unknown_location_cars:
        if car.distance_from_heerenveen_km is not None:
            if car.distance_from_heerenveen_km > 150:
                newly_geocoded_to_remove.append(car)
            elif car.distance_from_heerenveen_km > 80:
                car_make = car.make.lower() if car.make else ''
                car_model = car.model.lower() if car.model else ''
                is_preferred = (
                    car_make in preferred_makes or
                    any(pm in car_model for pm in preferred_models)
                )
                if not is_preferred:
                    newly_geocoded_to_remove.append(car)
                else:
                    newly_geocoded_to_keep.append(car)
            else:
                newly_geocoded_to_keep.append(car)
    
    print(f"  Newly geocoded cars to keep: {len(newly_geocoded_to_keep)}")
    print(f"  Newly geocoded cars to remove: {len(newly_geocoded_to_remove)}")
    print()
    
    # STEP 4: Get all cars beyond 150km
    cars_beyond_150 = session.query(Car).filter(
        and_(Car.is_available == True, Car.distance_from_heerenveen_km > 150)
    ).all()
    
    # Calculate totals
    still_no_location = autotrack_no_location + autoscout_no_location
    total_to_remove = len(non_preferred_80_150) + len(cars_beyond_150) + len(newly_geocoded_to_remove)
    total_to_keep = within_80 + len(preferred_80_150) + still_no_location + len(newly_geocoded_to_keep)
    
    # SUMMARY
    print("=" * 70)
    print("CLEANUP SUMMARY")
    print("=" * 70)
    print(f"Cars to KEEP: {total_to_keep}")
    print(f"  - Within 80km: {within_80}")
    print(f"  - 80-150km (preferred): {len(preferred_80_150)}")
    print(f"  - Newly geocoded (keep): {len(newly_geocoded_to_keep)}")
    print(f"  - autotrack.nl no location: {autotrack_no_location}")
    print(f"  - autoscout24.nl no location: {autoscout_no_location}")
    print()
    print(f"Cars to REMOVE: {total_to_remove}")
    print(f"  - 80-150km (non-preferred): {len(non_preferred_80_150)}")
    print(f"  - Beyond 150km: {len(cars_beyond_150)}")
    print(f"  - Newly geocoded (remove): {len(newly_geocoded_to_remove)}")
    print()
    print(f"Database reduction: {total_cars} → {total_to_keep} ({total_to_remove} removed, {100*total_to_remove/total_cars:.1f}%)")
    print("=" * 70)
    print()
    
    # Ask for confirmation
    response = input(f"Proceed with removing {total_to_remove} cars? (yes/no): ")
    
    if response.lower() == 'yes':
        removed_count = 0
        
        print("\nRemoving cars...")
        
        # Remove non-preferred cars in 80-150km range
        for car in non_preferred_80_150:
            print(f"  - {car.make} {car.model} ({car.distance_from_heerenveen_km:.0f}km) - €{car.price}")
            session.delete(car)
            removed_count += 1
        
        # Remove all cars beyond 150km
        for car in cars_beyond_150:
            print(f"  - {car.make} {car.model} ({car.distance_from_heerenveen_km:.0f}km) - €{car.price}")
            session.delete(car)
            removed_count += 1
        
        # Remove newly geocoded cars that are too far
        for car in newly_geocoded_to_remove:
            print(f"  - {car.make} {car.model} ({car.distance_from_heerenveen_km:.0f}km) - €{car.price}")
            session.delete(car)
            removed_count += 1
        
        session.commit()
        print(f"\n✓ Successfully removed {removed_count} cars")
        
        # Show final counts
        final_total = session.query(Car).filter(Car.is_available == True).count()
        print(f"\nFinal database state:")
        print(f"  Total available cars: {final_total} (was {total_cars})")
        print(f"  Reduction: {total_cars - final_total} cars ({100*(total_cars - final_total)/total_cars:.1f}%)")
    else:
        print("\nCleanup cancelled. No changes made.")

except Exception as e:
    session.rollback()
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.close()
