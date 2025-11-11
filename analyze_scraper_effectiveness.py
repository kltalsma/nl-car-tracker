"""
Comprehensive analysis of scraper effectiveness, data quality, and scoring system
"""
import sqlite3
import json
from datetime import datetime, timedelta
from collections import defaultdict
import yaml

def analyze_database():
    conn = sqlite3.connect('data/cars.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("NL CAR TRACKER - SCRAPER EFFECTIVENESS ANALYSIS")
    print("=" * 80)
    print()
    
    # 1. OVERALL STATISTICS
    print("📊 OVERALL STATISTICS")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            COUNT(*) as total_cars,
            COUNT(DISTINCT source_website) as sources,
            SUM(CASE WHEN is_available = 1 THEN 1 ELSE 0 END) as available,
            SUM(CASE WHEN is_available = 0 THEN 1 ELSE 0 END) as unavailable,
            MIN(first_seen) as oldest_listing,
            MAX(last_seen) as newest_scrape
        FROM cars
    """)
    stats = cursor.fetchone()
    print(f"Total cars in database:      {stats['total_cars']}")
    print(f"Currently available:         {stats['available']} ({stats['available']/stats['total_cars']*100:.1f}%)")
    print(f"Unavailable/sold:            {stats['unavailable']} ({stats['unavailable']/stats['total_cars']*100:.1f}%)")
    print(f"Active sources:              {stats['sources']}")
    print(f"Data range:                  {stats['oldest_listing']} to {stats['newest_scrape']}")
    print()
    
    # 2. SCRAPER PERFORMANCE BY SOURCE
    print("🔍 SCRAPER PERFORMANCE BY SOURCE")
    print("-" * 80)
    cursor.execute("""
        SELECT 
            source_website,
            COUNT(*) as total_cars,
            SUM(CASE WHEN is_available = 1 THEN 1 ELSE 0 END) as available_cars,
            AVG(price) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price
        FROM cars
        GROUP BY source_website
        ORDER BY total_cars DESC
    """)
    
    for row in cursor.fetchall():
        print(f"\n{row['source_website']}:")
        print(f"  Total cars found:          {row['total_cars']}")
        print(f"  Currently available:       {row['available_cars']} ({row['available_cars']/row['total_cars']*100:.1f}%)")
        print(f"  Avg price:                 €{row['avg_price']:,.0f}")
        print(f"  Price range:               €{row['min_price']:,.0f} - €{row['max_price']:,.0f}")
    
    # Recent scraper activity
    print("\n" + "-" * 80)
    print("Recent Scraper Activity (Last 24 hours):")
    cursor.execute("""
        SELECT 
            website,
            COUNT(*) as runs,
            SUM(cars_found) as total_found,
            SUM(cars_new) as total_new,
            SUM(cars_updated) as total_updated,
            AVG(julianday(completed_at) - julianday(started_at)) * 24 * 60 as avg_duration_mins
        FROM scraper_logs
        WHERE started_at >= datetime('now', '-1 day')
        GROUP BY website
        ORDER BY total_found DESC
    """)
    
    for row in cursor.fetchall():
        print(f"\n{row['website']}:")
        print(f"  Runs in 24h:               {row['runs']}")
        print(f"  Total found:               {row['total_found']}")
        print(f"  New cars:                  {row['total_new']}")
        print(f"  Updated:                   {row['total_updated']}")
        if row['avg_duration_mins']:
            print(f"  Avg duration:              {row['avg_duration_mins']:.1f} minutes")
    
    print()
    
    # 3. REQUIREMENTS COMPLIANCE
    print("\n📋 REQUIREMENTS COMPLIANCE")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN has_all_required_features = 1 THEN 1 ELSE 0 END) as with_all_features,
            SUM(CASE WHEN fuel_type = 'Full Electric' AND ad_listed_range_km >= 300 THEN 1 
                     WHEN fuel_type = 'PHEV' AND ad_listed_range_km >= 30 THEN 1 
                     ELSE 0 END) as meets_range_req,
            SUM(CASE WHEN price <= 35000 THEN 1 ELSE 0 END) as within_budget,
            SUM(CASE WHEN year >= 2020 THEN 1 ELSE 0 END) as year_ok,
            SUM(CASE WHEN mileage_km <= 150000 THEN 1 ELSE 0 END) as mileage_ok
        FROM cars
        WHERE is_available = 1
    """)
    
    req = cursor.fetchone()
    print(f"Available cars:              {req['total']}")
    print(f"With all required features:  {req['with_all_features']} ({req['with_all_features']/req['total']*100:.1f}%)")
    print(f"Meets range requirement:     {req['meets_range_req']} ({req['meets_range_req']/req['total']*100:.1f}%)")
    print(f"Within budget (≤€35k):       {req['within_budget']} ({req['within_budget']/req['total']*100:.1f}%)")
    print(f"Year ≥ 2020:                 {req['year_ok']} ({req['year_ok']/req['total']*100:.1f}%)")
    print(f"Mileage ≤ 150k km:           {req['mileage_ok']} ({req['mileage_ok']/req['total']*100:.1f}%)")
    
    # Fully compliant cars
    cursor.execute("""
        SELECT COUNT(*) as fully_compliant
        FROM cars
        WHERE is_available = 1
          AND has_all_required_features = 1
          AND price <= 35000
          AND year >= 2020
          AND mileage_km <= 150000
          AND (
              (fuel_type = 'Full Electric' AND ad_listed_range_km >= 300) OR
              (fuel_type = 'PHEV' AND ad_listed_range_km >= 30)
          )
    """)
    compliant = cursor.fetchone()['fully_compliant']
    print(f"\n✅ FULLY COMPLIANT CARS:     {compliant} ({compliant/req['total']*100:.1f}%)")
    
    print()
    
    # 4. DATA COMPLETENESS ANALYSIS
    print("\n📝 DATA COMPLETENESS ANALYSIS")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN ad_listed_range_km IS NOT NULL THEN 1 ELSE 0 END) as with_ad_range,
            SUM(CASE WHEN wltp_reference_range_km IS NOT NULL THEN 1 ELSE 0 END) as with_wltp,
            SUM(CASE WHEN evdb_real_range_km IS NOT NULL THEN 1 ELSE 0 END) as with_evdb,
            SUM(CASE WHEN storage_capacity_liters IS NOT NULL THEN 1 ELSE 0 END) as with_boot,
            SUM(CASE WHEN storage_capacity_seats_down_liters IS NOT NULL THEN 1 ELSE 0 END) as with_boot_down,
            SUM(CASE WHEN towing_capacity_kg IS NOT NULL THEN 1 ELSE 0 END) as with_towing,
            SUM(CASE WHEN vehicle_type IS NOT NULL THEN 1 ELSE 0 END) as with_vehicle_type,
            SUM(CASE WHEN distance_from_heerenveen_km IS NOT NULL THEN 1 ELSE 0 END) as with_distance
        FROM cars
        WHERE is_available = 1
    """)
    
    data = cursor.fetchone()
    total = data['total']
    
    print("Field Completeness (Available Cars Only):")
    print(f"  Ad-listed range:           {data['with_ad_range']}/{total} ({data['with_ad_range']/total*100:.1f}%)")
    print(f"  WLTP reference range:      {data['with_wltp']}/{total} ({data['with_wltp']/total*100:.1f}%)")
    print(f"  EV-Database real range:    {data['with_evdb']}/{total} ({data['with_evdb']/total*100:.1f}%)")
    print(f"  Boot capacity:             {data['with_boot']}/{total} ({data['with_boot']/total*100:.1f}%)")
    print(f"  Boot capacity (seats down):{data['with_boot_down']}/{total} ({data['with_boot_down']/total*100:.1f}%)")
    print(f"  Towing capacity:           {data['with_towing']}/{total} ({data['with_towing']/total*100:.1f}%)")
    print(f"  Vehicle type (SUV/Wagon):  {data['with_vehicle_type']}/{total} ({data['with_vehicle_type']/total*100:.1f}%)")
    print(f"  Distance from Heerenveen:  {data['with_distance']}/{total} ({data['with_distance']/total*100:.1f}%)")
    
    print()
    
    # 5. RANGE DATA QUALITY
    print("\n🔋 RANGE DATA QUALITY")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            fuel_type,
            COUNT(*) as total,
            SUM(CASE WHEN ad_listed_range_km IS NOT NULL THEN 1 ELSE 0 END) as with_ad_range,
            AVG(ad_listed_range_km) as avg_ad_range,
            AVG(wltp_reference_range_km) as avg_wltp,
            AVG(evdb_real_range_km) as avg_evdb,
            SUM(CASE WHEN ad_listed_range_km IS NOT NULL AND wltp_reference_range_km IS NOT NULL THEN 1 ELSE 0 END) as can_compare_wltp,
            SUM(CASE WHEN ad_listed_range_km IS NOT NULL AND evdb_real_range_km IS NOT NULL THEN 1 ELSE 0 END) as can_compare_evdb
        FROM cars
        WHERE is_available = 1
        GROUP BY fuel_type
    """)
    
    for row in cursor.fetchall():
        print(f"\n{row['fuel_type']}:")
        print(f"  Total cars:                {row['total']}")
        print(f"  With ad-listed range:      {row['with_ad_range']} ({row['with_ad_range']/row['total']*100:.1f}%)")
        if row['avg_ad_range']:
            print(f"  Avg ad-listed range:       {row['avg_ad_range']:.0f} km")
        if row['avg_wltp']:
            print(f"  Avg WLTP reference:        {row['avg_wltp']:.0f} km")
        if row['avg_evdb']:
            print(f"  Avg EV-DB real-world:      {row['avg_evdb']:.0f} km")
        print(f"  Can compare with WLTP:     {row['can_compare_wltp']} cars")
        print(f"  Can compare with EV-DB:    {row['can_compare_evdb']} cars")
    
    print()
    
    # 6. POPULAR MAKES AND MODELS
    print("\n🚗 POPULAR MAKES AND MODELS")
    print("-" * 80)
    
    cursor.execute("""
        SELECT 
            make,
            COUNT(*) as count,
            AVG(price) as avg_price,
            COUNT(DISTINCT model) as model_variants
        FROM cars
        WHERE is_available = 1
        GROUP BY make
        ORDER BY count DESC
        LIMIT 10
    """)
    
    print("Top 10 Makes:")
    for row in cursor.fetchall():
        print(f"  {row['make']:20s} {row['count']:3d} cars, {row['model_variants']:2d} models, avg €{row['avg_price']:,.0f}")
    
    print()
    
    # 7. SCORING SYSTEM EVALUATION
    print("\n⭐ SCORING SYSTEM EVALUATION")
    print("-" * 80)
    print("\nProposed Scoring Criteria:")
    print("1. Required Features (0-30 pts): 3 pts per required feature (10 features)")
    print("2. Range Score (0-20 pts):")
    print("   - EV: 20pts if ≥400km, 15pts if 350-399, 10pts if 300-349")
    print("   - PHEV: 20pts if ≥50km, 15pts if 40-49, 10pts if 30-39")
    print("3. Price Value (0-20 pts): (35000-price)/35000 * 20")
    print("4. Mileage (0-15 pts): (150000-mileage)/150000 * 15")
    print("5. Vehicle Age (0-10 pts): max(10 - (2025-year), 0)")
    print("6. Distance (0-5 pts): max(5 - distance/50, 0)")
    print("7. Storage Capacity (0-10 pts): Based on boot space")
    print("8. Towing Capacity (0-10 pts): 10pts if ≥1500kg, 5pts if ≥1000kg")
    
    # Calculate scores for top cars
    cursor.execute("""
        SELECT 
            make, model, year, price, mileage_km, fuel_type,
            ad_listed_range_km, features_count, has_all_required_features,
            distance_from_heerenveen_km, storage_capacity_seats_down_liters,
            towing_capacity_kg, vehicle_type
        FROM cars
        WHERE is_available = 1
          AND price <= 35000
          AND year >= 2020
          AND mileage_km <= 150000
        ORDER BY price ASC
        LIMIT 20
    """)
    
    scored_cars = []
    for row in cursor.fetchall():
        score = 0
        details = []
        
        # Required features (30 pts)
        if row['has_all_required_features']:
            feature_score = 30
        else:
            feature_score = (row['features_count'] or 0) * 3
        score += feature_score
        details.append(f"Features: {feature_score}/30")
        
        # Range (20 pts)
        range_score = 0
        if row['ad_listed_range_km']:
            if row['fuel_type'] == 'Full Electric':
                if row['ad_listed_range_km'] >= 400:
                    range_score = 20
                elif row['ad_listed_range_km'] >= 350:
                    range_score = 15
                elif row['ad_listed_range_km'] >= 300:
                    range_score = 10
            elif row['fuel_type'] == 'PHEV':
                if row['ad_listed_range_km'] >= 50:
                    range_score = 20
                elif row['ad_listed_range_km'] >= 40:
                    range_score = 15
                elif row['ad_listed_range_km'] >= 30:
                    range_score = 10
        score += range_score
        details.append(f"Range: {range_score}/20")
        
        # Price value (20 pts)
        price_score = min(20, (35000 - row['price']) / 35000 * 20)
        score += price_score
        details.append(f"Price: {price_score:.1f}/20")
        
        # Mileage (15 pts)
        mileage_score = min(15, (150000 - row['mileage_km']) / 150000 * 15)
        score += mileage_score
        details.append(f"Mileage: {mileage_score:.1f}/15")
        
        # Age (10 pts)
        age_score = max(0, 10 - (2025 - row['year']) * 2)
        score += age_score
        details.append(f"Age: {age_score}/10")
        
        # Distance (5 pts)
        distance_score = 0
        if row['distance_from_heerenveen_km']:
            distance_score = max(0, 5 - row['distance_from_heerenveen_km'] / 50)
        score += distance_score
        details.append(f"Distance: {distance_score:.1f}/5")
        
        scored_cars.append({
            'make': row['make'],
            'model': row['model'],
            'year': row['year'],
            'price': row['price'],
            'score': score,
            'details': details,
            'fuel_type': row['fuel_type'],
            'range': row['ad_listed_range_km']
        })
    
    scored_cars.sort(key=lambda x: x['score'], reverse=True)
    
    print("\n\nTop 10 Scored Cars (from available cars ≤€35k):")
    print("-" * 80)
    for i, car in enumerate(scored_cars[:10], 1):
        print(f"\n{i}. {car['make']} {car['model']} ({car['year']}) - €{car['price']:,.0f}")
        print(f"   Score: {car['score']:.1f}/120 pts")
        print(f"   {car['fuel_type']}, Range: {car['range'] or 'N/A'} km")
        print(f"   Breakdown: {', '.join(car['details'])}")
    
    print()
    
    # 8. DATA IMPROVEMENT OPPORTUNITIES
    print("\n💡 DATA IMPROVEMENT OPPORTUNITIES")
    print("-" * 80)
    
    # Missing range data
    cursor.execute("""
        SELECT COUNT(*) as missing_range
        FROM cars
        WHERE is_available = 1
          AND ad_listed_range_km IS NULL
    """)
    missing_range = cursor.fetchone()['missing_range']
    
    # Missing vehicle type
    cursor.execute("""
        SELECT COUNT(*) as missing_type
        FROM cars
        WHERE is_available = 1
          AND vehicle_type IS NULL
    """)
    missing_type = cursor.fetchone()['missing_type']
    
    # Missing storage data
    cursor.execute("""
        SELECT COUNT(*) as missing_storage
        FROM cars
        WHERE is_available = 1
          AND storage_capacity_seats_down_liters IS NULL
    """)
    missing_storage = cursor.fetchone()['missing_storage']
    
    print(f"1. Range Data Missing:         {missing_range} cars ({missing_range/total*100:.1f}%)")
    print(f"   → Improve ad parsing or use WLTP/EV-DB fallback")
    print()
    print(f"2. Vehicle Type Missing:       {missing_type} cars ({missing_type/total*100:.1f}%)")
    print(f"   → Enhance vehicle classification logic")
    print()
    print(f"3. Storage Capacity Missing:   {missing_storage} cars ({missing_storage/total*100:.1f}%)")
    print(f"   → Add external data source (manufacturer specs)")
    print()
    
    # WLTP/EVDB reference missing
    cursor.execute("""
        SELECT COUNT(*) as missing_wltp
        FROM cars
        WHERE is_available = 1
          AND wltp_reference_range_km IS NULL
    """)
    missing_wltp = cursor.fetchone()['missing_wltp']
    
    cursor.execute("""
        SELECT COUNT(*) as missing_evdb
        FROM cars
        WHERE is_available = 1
          AND evdb_real_range_km IS NULL
    """)
    missing_evdb = cursor.fetchone()['missing_evdb']
    
    print(f"4. WLTP Reference Missing:     {missing_wltp} cars ({missing_wltp/total*100:.1f}%)")
    print(f"5. EV-DB Real Range Missing:   {missing_evdb} cars ({missing_evdb/total*100:.1f}%)")
    print(f"   → Expand YAML vehicle range database")
    print()
    
    conn.close()

if __name__ == "__main__":
    analyze_database()
