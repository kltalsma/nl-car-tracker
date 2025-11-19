#!/usr/bin/env python3
"""
Diagnose AutoScout24 feature extraction
Fetch a real listing and inspect what data is available
"""
import sys
import json
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# URL from database
url = "https://www.autoscout24.nl/aanbod/8b5fef13-a1d2-48d9-8146-47a9c98485e8"

print("=" * 80)
print(f"Diagnosing AutoScout24 Feature Extraction")
print("=" * 80)
print(f"URL: {url}\n")

# Setup headless Chrome
chrome_options = Options()
chrome_options.add_argument('--headless=new')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')

print("Initializing Chrome WebDriver...")
driver = webdriver.Chrome(options=chrome_options)
driver.set_page_load_timeout(30)

try:
    print(f"Fetching page...")
    driver.get(url)
    
    import time
    time.sleep(3)  # Wait for JS to load
    
    page_source = driver.page_source
    print(f"✓ Page loaded ({len(page_source)} bytes)\n")
    
    # 1. Check for __NEXT_DATA__
    print("-" * 80)
    print("1. Checking for __NEXT_DATA__ script tag...")
    print("-" * 80)
    
    json_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_source, re.DOTALL)
    
    if json_match:
        print("✓ Found __NEXT_DATA__ script tag")
        try:
            data = json.loads(json_match.group(1))
            print(f"✓ Successfully parsed JSON ({len(json_match.group(1))} bytes)")
            
            # Navigate to equipment
            props = data.get('props', {})
            page_props = props.get('pageProps', {})
            listing_details = page_props.get('listingDetails', {})
            vehicle = listing_details.get('vehicle', {})
            equipment = vehicle.get('equipment', {})
            
            print(f"\nJSON Structure:")
            print(f"  props: {type(props)} - {list(props.keys())[:5]}")
            print(f"  pageProps: {type(page_props)} - {list(page_props.keys())[:5]}")
            print(f"  listingDetails: {type(listing_details)} - {list(listing_details.keys())[:5]}")
            print(f"  vehicle: {type(vehicle)} - {list(vehicle.keys())[:10]}")
            print(f"  equipment: {type(equipment)} - {list(equipment.keys())}")
            
            if equipment:
                print(f"\n Equipment categories found: {len(equipment)}")
                for category, items in equipment.items():
                    if isinstance(items, list):
                        print(f"  - {category}: {len(items)} items")
                        if items:
                            # Show first few items
                            for i, item in enumerate(items[:3]):
                                if isinstance(item, dict):
                                    print(f"      [{i}] {item}")
                    else:
                        print(f"  - {category}: {type(items)}")
                
                # Extract features
                features = []
                for category, items in equipment.items():
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and 'id' in item:
                                feature_name = item['id'].strip()
                                if feature_name:
                                    features.append(feature_name)
                
                print(f"\n✓ Extracted {len(features)} features:")
                for f in features[:20]:
                    print(f"    • {f}")
                if len(features) > 20:
                    print(f"    ... and {len(features) - 20} more")
            else:
                print("\n✗ equipment dictionary is empty!")
                
                # Check alternative paths
                print("\n  Checking alternative paths in vehicle data:")
                for key in vehicle.keys():
                    print(f"    - vehicle.{key}: {type(vehicle[key])}")
                    if key in ['features', 'ausstattung', 'options', 'extras']:
                        print(f"      Value: {vehicle[key]}")
                
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse JSON: {e}")
        except KeyError as e:
            print(f"✗ Missing expected key: {e}")
    else:
        print("✗ __NEXT_DATA__ script tag NOT found!")
        
        # Check what scripts DO exist
        script_matches = re.findall(r'<script[^>]*id="([^"]*)"', page_source)
        print(f"\nFound {len(script_matches)} script tags with IDs:")
        for script_id in script_matches[:10]:
            print(f"  - {script_id}")
    
    # 2. Check for alternative feature sources
    print("\n" + "-" * 80)
    print("2. Checking for alternative feature sources...")
    print("-" * 80)
    
    # Look for feature-related HTML elements
    feature_keywords = ['equipment', 'ausstattung', 'features', 'uitrusting', 'options']
    for keyword in feature_keywords:
        pattern = f'<[^>]*{keyword}[^>]*>'
        matches = re.findall(pattern, page_source, re.IGNORECASE)
        if matches:
            print(f"  Found {len(matches)} elements with '{keyword}'")
    
    # Check for data-testid or data-qa attributes (common in modern React apps)
    testid_matches = re.findall(r'data-testid="([^"]*feature[^"]*)"', page_source, re.IGNORECASE)
    if testid_matches:
        print(f"  Found {len(testid_matches)} feature-related test IDs:")
        for tid in set(testid_matches)[:5]:
            print(f"    - {tid}")
    
    # Look for visible feature lists
    feature_list_pattern = r'<li[^>]*>([^<]*(?:Android Auto|Cruise Control|LED|Camera|Climate)[^<]*)</li>'
    feature_list_matches = re.findall(feature_list_pattern, page_source, re.IGNORECASE)
    if feature_list_matches:
        print(f"  Found {len(feature_list_matches)} feature list items:")
        for item in feature_list_matches[:10]:
            print(f"    • {item.strip()}")

finally:
    driver.quit()
    print("\n✓ Browser closed")

print("\n" + "=" * 80)
print("Diagnosis Complete")
print("=" * 80)
