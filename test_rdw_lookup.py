#!/usr/bin/env python3
"""
Test script to verify RDW API lookup for license plate
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.trade_in_checker import TradeInChecker

def main():
    print("=" * 60)
    print("Testing RDW API Lookup")
    print("=" * 60)
    
    checker = TradeInChecker()
    
    license_plate = os.environ.get('TEST_LICENSE_PLATE', 'XX-XXX-X')
    
    print(f"\nLooking up license plate: {license_plate}")
    print("-" * 60)
    
    rdw_data = checker.get_rdw_data(license_plate)
    
    if rdw_data:
        print("\n✅ SUCCESS! Found vehicle information:")
        print(f"   Make:       {rdw_data['make']}")
        print(f"   Model:      {rdw_data['model']}")
        print(f"   Year:       {rdw_data['year']}")
        print(f"   Fuel Type:  {rdw_data['fuel_type']}")
        print(f"   Body Type:  {rdw_data['body_type']}")
        print(f"   Color:      {rdw_data['color']}")
        print("\nYou can now update config.yaml with this information!")
        return 0
    else:
        print("\n❌ FAILED: Could not retrieve vehicle information")
        print("   Make sure the license plate is correct and the RDW API is accessible")
        return 1

if __name__ == "__main__":
    sys.exit(main())
