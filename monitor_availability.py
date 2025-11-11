#!/usr/bin/env python3
"""
Availability Monitoring Script for NL Car Tracker
Monitors and reports on car availability status and potential false positives
"""

from models.database import Database, Car, ScraperLog
from sqlalchemy import func
from datetime import datetime, timedelta
import sys


def check_availability_health(db_path='data/cars.db'):
    """Check for potential availability issues and anomalies"""
    
    db = Database(db_path)
    session = db.get_session()
    
    print('='*80)
    print('NL CAR TRACKER - AVAILABILITY HEALTH CHECK')
    print(f'Report Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('='*80)
    print()
    
    # Overall statistics
    print('OVERALL STATISTICS')
    print('-'*80)
    total = session.query(Car).count()
    available = session.query(Car).filter_by(is_available=True).count()
    unavailable = session.query(Car).filter_by(is_available=False).count()
    
    print(f'Total cars:      {total:4}')
    print(f'Available:       {available:4} ({available/total*100:.1f}%)')
    print(f'Unavailable:     {unavailable:4} ({unavailable/total*100:.1f}%)')
    print()
    
    # Unavailability reasons
    print('UNAVAILABILITY BREAKDOWN')
    print('-'*80)
    reasons = session.query(
        Car.unavailable_reason, 
        func.count(Car.id)
    ).filter_by(is_available=False).group_by(Car.unavailable_reason).all()
    
    has_false_positives = False
    for reason, count in reasons:
        print(f'{reason or "None":30} : {count:3} cars')
        if reason == 'not_found_in_scrape' and count > 0:
            has_false_positives = True
            print('  ⚠️  WARNING: Potential false positives detected!')
    
    if not has_false_positives:
        print('✓ No false positives detected (no "not_found_in_scrape" entries)')
    print()
    
    # By source website
    print('AVAILABILITY BY SOURCE')
    print('-'*80)
    results = session.query(
        Car.source_website,
        Car.is_available,
        func.count(Car.id)
    ).group_by(Car.source_website, Car.is_available).all()
    
    by_source = {}
    for website, is_available, count in results:
        if website not in by_source:
            by_source[website] = {'available': 0, 'unavailable': 0}
        if is_available:
            by_source[website]['available'] = count
        else:
            by_source[website]['unavailable'] = count
    
    for website in sorted(by_source.keys()):
        avail = by_source[website]['available']
        unavail = by_source[website]['unavailable']
        total_site = avail + unavail
        print(f'{website:20} | Available: {avail:3} | Unavailable: {unavail:3} | Total: {total_site:3}')
    print()
    
    # Recent scraper performance
    print('RECENT SCRAPER PERFORMANCE (Last 10 runs)')
    print('-'*80)
    recent_logs = session.query(ScraperLog).order_by(
        ScraperLog.started_at.desc()
    ).limit(10).all()
    
    for log in recent_logs:
        print(f'{log.website:15} | {log.started_at.strftime("%Y-%m-%d %H:%M")} | '
              f'Found: {log.cars_found:3} | Status: {log.status}')
    print()
    
    # Scraper completeness check
    print('SCRAPER COMPLETENESS CHECK')
    print('-'*80)
    for website in by_source.keys():
        total_in_db = by_source[website]['available'] + by_source[website]['unavailable']
        
        # Get latest scrape result
        latest_log = session.query(ScraperLog).filter_by(
            website=website
        ).order_by(ScraperLog.started_at.desc()).first()
        
        if latest_log:
            cars_found = latest_log.cars_found
            completeness = (cars_found / total_in_db * 100) if total_in_db > 0 else 0
            
            status = '✓ Good' if completeness > 80 else '⚠️ Poor' if completeness > 30 else '❌ Critical'
            print(f'{website:20} | DB: {total_in_db:3} | Latest scrape: {cars_found:3} | '
                  f'Completeness: {completeness:5.1f}% | {status}')
    print()
    
    # Stale cars (not seen in 3+ days)
    print('STALE CARS (Not seen in 7+ days but marked available)')
    print('-'*80)
    week_ago = datetime.now() - timedelta(days=3)
    stale_cars = session.query(Car).filter(
        Car.is_available == True,
        Car.last_seen < week_ago
    ).count()
    
    print(f'Stale cars: {stale_cars}')
    if stale_cars > 0:
        print('ℹ️  These cars may need availability verification')
    else:
        print('✓ No stale cars detected')
    print()
    
    print('='*80)
    print('HEALTH CHECK COMPLETE')
    print('='*80)
    
    session.close()
    
    # Return exit code based on health
    if has_false_positives:
        return 1  # Warning condition
    return 0


if __name__ == '__main__':
    exit_code = check_availability_health()
    sys.exit(exit_code)
