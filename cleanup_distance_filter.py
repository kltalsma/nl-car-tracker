#!/usr/bin/env python3
import yaml
from models import db_session, Car
from sqlalchemy import and_, or_

# Load config
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Get preferred makes and models
preferred_config = config.get('preferred_cars', {})
preferred_makes = [m.lower() for m in preferred_config.get('makes', [])]
preferred_models = [m.lower() for m in preferred_config.get('models', [])]

print("Preferred makes:", preferred_makes)
print("Preferred models:", preferred_models)
print()

session = db_session()

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
    
    # Find cars to remove in 80-150km range (non-preferred)
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
    
    print(f"80-150km breakdown:")
    print(f"  Preferred cars (keep): {len(preferred_80_150)}")
    print(f"  Non-preferred cars (remove): {len(non_preferred_80_150)}")
    print()
    
    # Calculate total to remove
    total_to_remove = len(non_preferred_80_150) + beyond_150
    
    print(f"Summary of cleanup:")
    print(f"  Cars to KEEP:")
    print(f"    - Within 80km: {within_80} (all cars)")
    print(f"    - 80-150km preferred: {len(preferred_80_150)}")
    print(f"    - No location: {no_location} (keeping for now)")
    print(f"  Cars to REMOVE:")
    print(f"    - 80-150km non-preferred: {len(non_preferred_80_150)}")
    print(f"    - Beyond 150km: {beyond_150}")
    print(f"  Total to remove: {total_to_remove}")
    print()
    
    # Ask for confirmation
    response = input(f"Do you want to remove {total_to_remove} cars? (yes/no): ")
    
    if response.lower() == 'yes':
        removed_count = 0
        
        # Remove non-preferred cars in 80-150km range
        for car in non_preferred_80_150:
            print(f"Removing: {car.make} {car.model} - {car.distance_from_heerenveen_km:.0f}km - EUR{car.price}")
            session.delete(car)
            removed_count += 1
        
        # Remove all cars beyond 150km
        cars_beyond_150 = session.query(Car).filter(
            and_(Car.is_available == True, Car.distance_from_heerenveen_km > 150)
        ).all()
        
        for car in cars_beyond_150:
            print(f"Removing: {car.make} {car.model} - {car.distance_from_heerenveen_km:.0f}km - EUR{car.price}")
            session.delete(car)
            removed_count += 1
        
        session.commit()
        print(f"Successfully removed {removed_count} cars")
        
        # Show final counts
        final_total = session.query(Car).filter(Car.is_available == True).count()
        print(f"Final database state:")
        print(f"  Total available cars: {final_total} (was {total_cars})")
        print(f"  Removed: {total_cars - final_total}")
    else:
        print("Cleanup cancelled.")

except Exception as e:
    session.rollback()
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    session.close()
