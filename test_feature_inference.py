#!/usr/bin/env python3
"""
Test script for feature inference system
"""
import sys
sys.path.insert(0, '/home/kltalsma/nl-car-tracker')

from utils.feature_inference import infer_features

# Test cases
test_cases = [
    {
        'name': 'Modern Premium EV (Audi e-tron 2020) - 0 scraped features',
        'car_data': {
            'make': 'Audi',
            'model': 'e-tron',
            'year': 2020,
            'fuel_type': 'Full Electric'
        },
        'scraped_features': []
    },
    {
        'name': 'Modern Mainstream EV (Kia EV6 2023) - 2 scraped features',
        'car_data': {
            'make': 'Kia',
            'model': 'EV6',
            'year': 2023,
            'fuel_type': 'Full Electric'
        },
        'scraped_features': ['Panorama dak', 'Trekhaak']
    },
    {
        'name': 'Premium Brand (BMW iX3 2022) - 5 scraped features',
        'car_data': {
            'make': 'BMW',
            'model': 'iX3',
            'year': 2022,
            'fuel_type': 'Full Electric'
        },
        'scraped_features': ['360° camera', 'Head-up display', 'Stoelverwarming', 'Stuurwielverwarming', 'Adaptive Cruise Control']
    },
    {
        'name': 'Older car (Skoda Enyaq 2021) - 8 scraped features',
        'car_data': {
            'make': 'Skoda',
            'model': 'Enyaq',
            'year': 2021,
            'fuel_type': 'Full Electric'
        },
        'scraped_features': ['Navigatiesysteem', 'Climate Control', 'Cruise Control', 'LED verlichting', 'Parkeerhulp achter', 'Android Auto', 'Apple CarPlay', 'Bluetooth']
    }
]

print("=" * 80)
print("FEATURE INFERENCE TEST SUITE")
print("=" * 80)

for test in test_cases:
    print(f"\n{'=' * 80}")
    print(f"TEST: {test['name']}")
    print(f"{'=' * 80}")
    print(f"Make: {test['car_data']['make']}")
    print(f"Model: {test['car_data']['model']}")
    print(f"Year: {test['car_data']['year']}")
    print(f"Fuel Type: {test['car_data']['fuel_type']}")
    print(f"\nScraped Features ({len(test['scraped_features'])}):")
    for feature in test['scraped_features']:
        print(f"  - {feature}")
    
    # Run inference
    enriched, inferred_count = infer_features(test['car_data'], test['scraped_features'])
    
    print(f"\n✓ RESULTS:")
    print(f"  Scraped: {len(test['scraped_features'])}")
    print(f"  Inferred: {inferred_count}")
    print(f"  Total: {len(enriched)}")
    print(f"  Improvement: +{round((inferred_count / max(len(test['scraped_features']), 1)) * 100, 1)}%")
    
    print(f"\nAll Features ({len(enriched)}):")
    # Group features
    scraped = [f for f in test['scraped_features']]
    inferred_features = [f for f in enriched if f not in scraped]
    
    if scraped:
        print(f"\n  [SCRAPED - {len(scraped)}]:")
        for f in scraped:
            print(f"    • {f}")
    
    if inferred_features:
        print(f"\n  [INFERRED - {len(inferred_features)}]:")
        for f in sorted(inferred_features):
            print(f"    • {f}")

print(f"\n{'=' * 80}")
print("TEST SUITE COMPLETE")
print(f"{'=' * 80}")
