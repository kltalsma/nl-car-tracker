#!/usr/bin/env python3
"""Test the improved vandenbrug scraper on a real URL"""

import sys
sys.path.insert(0, '/home/kltalsma/nl-car-tracker')

from scrapers.vandenbrug_scraper import VandenBrugScraper

# Initialize scraper
scraper = VandenBrugScraper(
    config_path='/home/kltalsma/nl-car-tracker/config.yaml',
    db_path='/home/kltalsma/nl-car-tracker/data/cars.db'
)

# Test URL from database
test_url = "https://vandenbrug.nl/p/volkswagen-passat-gte-1-4-tsi-218-pk-dsg-phev-highline-49040800-262"

print(f"Testing improved scraper on: {test_url}")
print("=" * 80)

# Fetch detail page
specs = scraper.fetch_detail_page(test_url)

print(f"\nResults:")
print(f"  Features extracted: {len(specs.get('features', []))}")
print(f"  Specs extracted: {len([k for k in specs.keys() if k != 'features'])}")

print(f"\nFeatures list:")
for i, feature in enumerate(specs.get('features', []), 1):
    print(f"  {i}. {feature}")

print(f"\nSpecs:")
for key, value in specs.items():
    if key != 'features':
        print(f"  {key}: {value}")

print("=" * 80)
print("Test completed!")
