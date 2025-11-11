#!/usr/bin/env python3
"""
Normalize make values in the database to fix filtering issues.
Removes diacritics from make names (e.g., Škoda -> Skoda)
"""

import sys
import os
import unicodedata

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.database import Database, Car
import yaml

def remove_diacritics(text):
    """
    Remove diacritics from text (e.g., Škoda -> Skoda, Citroën -> Citroen)
    """
    if not text:
        return text
    
    # Normalize to NFD (decompose characters)
    nfd = unicodedata.normalize('NFD', text)
    # Filter out combining characters (diacritics)
    return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')


def normalize_make_values(db_path):
    """Normalize all make values in the database"""
    db = Database(db_path)
    session = db.get_session()
    
    try:
        # Get all cars
        cars = session.query(Car).all()
        
        updates = []
        for car in cars:
            if car.make:
                normalized_make = remove_diacritics(car.make)
                
                # Also standardize capitalization for common makes
                # First letter uppercase, rest as-is
                if normalized_make.lower() == 'bmw':
                    normalized_make = 'BMW'
                elif normalized_make.lower() == 'mg':
                    normalized_make = 'MG'
                elif normalized_make.lower() == 'cupra':
                    normalized_make = 'CUPRA'
                elif normalized_make.lower() == 'seat':
                    normalized_make = 'SEAT'
                elif normalized_make.lower() == 'mercedes-benz':
                    normalized_make = 'Mercedes-Benz'
                else:
                    # Capitalize first letter only
                    normalized_make = normalized_make.capitalize()
                
                if car.make != normalized_make:
                    updates.append({
                        'id': car.id,
                        'old': car.make,
                        'new': normalized_make
                    })
                    car.make = normalized_make
        
        if updates:
            print(f"Found {len(updates)} make values to normalize:")
            for update in updates:
                print(f"  Car ID {update['id']}: '{update['old']}' -> '{update['new']}'")
            
            # Commit changes
            session.commit()
            print(f"\n✓ Successfully normalized {len(updates)} make values")
        else:
            print("No make values need normalization")
        
        session.close()
        return len(updates)
        
    except Exception as e:
        print(f"Error normalizing make values: {e}")
        session.rollback()
        session.close()
        return 0


if __name__ == "__main__":
    # Load config to get database path
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    db_path = config['database']['path']
    
    print(f"Normalizing make values in: {db_path}")
    normalize_make_values(db_path)
