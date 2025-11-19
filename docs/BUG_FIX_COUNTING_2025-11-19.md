# Bug Fix: Incorrect New vs Updated Car Counting

**Date:** 2025-11-19  
**Issue:** Scraper consistently reports 0 new cars even when adding new cars to database

## Problem Description

The scraper was showing 0 new cars in all runs, even when it successfully added new cars to the database. For example:
- Database showed 30 cars added today (first_seen = 2025-11-19)
- Scraper log showed: 33 cars found, 0 new, 33 updated

## Root Cause

The bug was in scrapers/base_scraper.py line 869:

The logic compared timestamps (first_seen == last_seen) to determine if a car was new. However:

1. SQLAlchemy last_seen column has onupdate=datetime.utcnow
2. When a new car is created, last_seen is automatically updated by SQLAlchemy on ANY field modification
3. The scraper enriches car data (WLTP range, boot space, etc.) after creating the record
4. These enrichments trigger SQLAlchemy onupdate, making last_seen != first_seen
5. Result: ALL cars (even brand new ones) were counted as updated

### Evidence

Test of a car created today showed:
- First seen: 2025-11-19 07:41:54
- Last seen:  2025-11-19 07:59:23
- Time diff: 17 minutes 28 seconds
- OLD logic incorrectly counted this as UPDATED (it was actually NEW)

## Solution

Changed _save_car_to_db() to return a tuple (car, was_new_car: bool) instead of just the car object.

### Changes Made

1. Line 308: return existing_car -> return (existing_car, False)
2. Line 328: return new_car -> return (new_car, True)  
3. Line 333: return None -> return (None, False)
4. Line 867: if result: -> if result[0]:
5. Line 869: timestamp comparison -> if result[1]:
6. Lines 177-179: Updated docstring

### Files Modified

- scrapers/base_scraper.py (backup: base_scraper.py.backup-20251119-091153)

## Impact

- More accurate metrics in scraper logs
- Correct tracking of new vs updated cars
- Better visibility into scraping effectiveness
- No impact on database structure or stored data
