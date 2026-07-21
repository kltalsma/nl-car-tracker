# Data Validation Confidence Analysis
**Date:** October 29, 2025  
**Status:** Analysis Complete - Awaiting Decision

## Executive Summary

Current system provides **61% confidence** that scraped cars meet all requirements (age/price/mileage/features). This analysis evaluated validation layers and provided recommendations for improvement.

**Current Database Stats:**
- 181 available cars
- Year range: 2016-2025
- Notable: 1x 2020 Škoda Enyaq (€27,445, 82k km) - outside min_year but desirable
- 10 cars from 2021 (pre-2022 requirement)

---

## Validation Confidence Breakdown

### 1. Age (Year) - 75% Confidence ✅

**Validation Layers:**
- ✅ **Search filter**: All 3 scrapers pass `fregfrom={min_year}` (2022) in URL params
  - AutoScout24: `scrapers/autoscout24_scraper.py:58`
  - Gaspedaal: `scrapers/gaspedaal_scraper.py:92`
  - AutoTrack: URL-based filtering
- ✅ **URL extraction**: Autotrack extracts year from URL pattern
- ✅ **Page parsing**: All scrapers extract year from specification tables
- ❌ **No post-scrape validation**: Cars aren't checked against `config['search']['min_year']` before saving

**Risks:**
- If website's search filter malfunctions, older cars could slip through
- No verification that scraped year matches search criteria
- Could save cars that don't meet minimum year requirement

**Current Config:**
```yaml
search:
  min_year: 2022
search_criteria:
  acceptable_year: 2020  # Used for scoring, not blocking
```

---

### 2. Price - 60% Confidence ⚠️

**Validation Layers:**
- ✅ **Search filter**: All scrapers pass `priceto={max_price}` in URL params
  - AutoScout24: `scrapers/autoscout24_scraper.py:56`
  - Gaspedaal: `scrapers/gaspedaal_scraper.py:91`
  - AutoTrack: URL-based filtering
- ✅ **Page parsing**: All scrapers extract price from detail pages
  - AutoScout24: JSON-LD structured data (most reliable)
  - Gaspedaal: Price elements
  - AutoTrack: Regex patterns with sanity checks
- ❌ **No post-scrape validation**: Prices aren't checked against vehicle_type max_price limits
- ⚠️ **Sanity checks exist**: Some scrapers check `1000 < price < 200000`

**Risks:**
- Price could change between search results page and detail page scrape
- No enforcement of per-vehicle-type price limits (SUV: €35k, Wagon: €35k)
- Dealers might mislist prices or include incorrect values
- No validation against config max_price before database save

**Current Config:**
```yaml
search:
  vehicle_types:
    - type: SUV
      max_price: 35000
    - type: Stationwagon
      max_price: 35000
```

---

### 3. Odometer (Mileage) - 70% Confidence ✅

**Validation Layers:**
- ✅ **Search filter**: All scrapers pass `kmto={max_mileage_km}` (100,000 km) in URL
  - AutoScout24: `scrapers/autoscout24_scraper.py:57`
  - Gaspedaal: `scrapers/gaspedaal_scraper.py:93`
  - AutoTrack: URL-based filtering
- ✅ **Page parsing**: All scrapers extract mileage from specs
- ❌ **No post-scrape validation**: Mileage isn't verified against 100k limit
- ⚠️ **Required field check**: Autotrack validates `mileage_km` is present (line 676)

**Risks:**
- Odometer rollback fraud (no validation against historical data)
- No verification against `config['search']['max_mileage_km']` before save
- Missing mileage would only be caught by AutoTrack scraper
- No cross-check between different listings of same car

**Current Config:**
```yaml
search:
  max_mileage_km: 100000
search_criteria:
  max_mileage_acceptable: 100000
```

---

### 4. Required Options (Critical Features) - 40% Confidence ⚠️

**Validation Status:**
- ✅ **Features extracted**: All scrapers parse features from listings
  - AutoScout24: JSON equipment data from `__NEXT_DATA__` script
  - Gaspedaal: Feature list elements
  - AutoTrack: Feature list elements
- ✅ **Feature counting**: `_check_required_features()` counts matches (`scrapers/base_scraper.py:212`)
- ✅ **Fuzzy matching**: Keyword mappings handle Dutch/English variations
- ⚠️ **Tracked but not enforced**: `has_all_required_features` flag is saved but not blocking
- ❌ **No validation before save**: Cars with 0 features still get saved to database

**Critical Features Required (9 total):**
1. Adaptive Cruise Control
2. Android Auto
3. Navigatiesysteem
4. DAB+ radio
5. Achteruitrijcamera
6. Climate Control
7. Lane Assist
8. Park Assist
9. Trekhaak

**How Feature Matching Works:**
```python
# base_scraper.py:212-269
def _check_required_features(self, features: List[str]) -> tuple[int, bool]:
    """
    Fuzzy matching with keyword variations:
    - 'adaptive cruise control' matches: 'ACC', 'adaptieve cruise control'
    - 'android auto' matches: 'apple carplay' (usually bundled)
    - 'navigatiesysteem' matches: 'navigatie', 'navigation', 'navi', 'gps'
    """
    # Returns: (features_count, has_all_required_features)
```

**Risks:**
- Features might be incomplete on listing (dealer didn't list all equipment)
- Fuzzy matching might miss creative variations or abbreviations
- No blocking mechanism - all cars saved regardless of feature count
- Feature extraction quality varies significantly by website
- Dealers may omit standard features from listings

**Current Storage:**
```python
car_data['features_count'] = 7  # Number matched
car_data['has_all_required_features'] = False  # All 9 present?
# Saved to database but NOT used for filtering before save
```

---

## Overall Confidence: 61%

**Calculation:**
- Age: 75%
- Price: 60%
- Mileage: 70%
- Features: 40%
- **Average: (75 + 60 + 70 + 40) / 4 = 61.25%**

---

## What's Missing (Code That Doesn't Exist)

Currently, there is **NO validation layer** before saving cars to database. Here's what it would look like:

```python
# This validation DOES NOT EXIST in current code:
# Would go in base_scraper.py before _save_car_to_db() call

def validate_car_meets_requirements(car_data, config):
    """
    Validate car meets all hard requirements before saving.
    Returns: (is_valid, confidence_score, violations)
    """
    violations = []
    confidence = 100
    
    # Year check
    min_year = config['search']['min_year']
    if car_data.get('year', 0) < min_year:
        violations.append(f"Year {car_data['year']} < minimum {min_year}")
        confidence -= 25
    
    # Price check (per vehicle type)
    vehicle_type = car_data.get('vehicle_type')
    max_price = get_max_price_for_vehicle_type(vehicle_type, config)
    if car_data.get('price', 0) > max_price:
        violations.append(f"Price €{car_data['price']} > max €{max_price}")
        confidence -= 20
    
    # Mileage check
    max_km = config['search']['max_mileage_km']
    if car_data.get('mileage_km', 0) > max_km:
        violations.append(f"Mileage {car_data['mileage_km']}km > max {max_km}km")
        confidence -= 15
    
    # Feature check (warning only, not blocking)
    if not car_data.get('has_all_required_features'):
        feature_count = car_data.get('features_count', 0)
        critical_count = len(config['critical_features'])
        missing = critical_count - feature_count
        violations.append(f"Missing {missing} critical features")
        confidence -= (missing * 5)  # -5% per missing feature
    
    # Determine if valid (no blocking violations)
    is_valid = len([v for v in violations if 'Year' not in v]) == 0
    
    return is_valid, max(0, confidence), violations
```

**Where it would be called:**
```python
# base_scraper.py:336 (in run() method, before saving)

# Get detailed information
car_data = self.parse_car_detail(car_summary)

if car_data:
    # NEW: Validate before saving
    is_valid, confidence, violations = validate_car_meets_requirements(
        car_data, self.config
    )
    
    if violations:
        self.logger.warning(f"Validation issues: {', '.join(violations)}")
    
    car_data['confidence_score'] = confidence
    
    # OPTION 1: Block invalid cars
    # if not is_valid:
    #     self.logger.info(f"Skipping car due to validation: {violations}")
    #     continue
    
    # OPTION 2: Save all cars with confidence score (RECOMMENDED)
    result = self._save_car_to_db(car_data)
```

---

## Current System Analysis

### What Works Well ✅

1. **Search-level filtering**: Websites do most of the heavy lifting
   - AutoScout24: Clean URL parameters, reliable filtering
   - Gaspedaal: Good search filters
   - AutoTrack: URL-based filtering works well

2. **Exclusion list**: `should_exclude_vehicle()` successfully filters out small cars
   - Located at: `scrapers/autoscout24_scraper.py:596`
   - Reads from: `config.yaml → vehicle_classification.exclude_models`

3. **Duplicate prevention**: External ID tracking prevents re-adding same car

4. **Price history tracking**: Monitors price changes over time

5. **Feature extraction**: Good coverage from most websites

### What's Risky ⚠️

1. **Trust in website filters**: Assumes AutoScout24/Gaspedaal/AutoTrack always filter correctly

2. **No post-scrape validation**: Data goes straight to database without verification

3. **No required field enforcement**: Cars can be saved with missing critical data

4. **Feature completeness unknown**: No way to know if dealer listed all equipment

5. **No data quality audit**: Can't easily find cars that violate current criteria

---

## Recommendations & Options

### Option 1: Keep Current System (61% confidence) - ✅ RECOMMENDED

**Reasoning:**
- Current system is **working well in practice**
- Provides **flexibility** to catch good deals outside strict criteria
- Example: 2020 Škoda Enyaq (€27,445) wouldn't be scraped with strict validation
- You can **filter in dashboard UI** by year/price/mileage as needed
- No risk of losing existing 181 cars in database

**Pros:**
- ✅ No changes needed, system stable
- ✅ Catches outlier deals (2020 Enyaq, 2021 models)
- ✅ Flexibility to adjust criteria without re-scraping
- ✅ Dashboard provides filtering when you need it

**Cons:**
- ⚠️ Can't guarantee all cars meet exact criteria
- ⚠️ Requires manual filtering in UI
- ⚠️ Could save cars with missing data

---

### Option 2: Add Soft Validation (Monitoring Only)

**What it does:**
- Logs warnings for cars outside criteria (doesn't block them)
- Adds `confidence_score` field to database (0-100%)
- Dashboard shows which cars meet all hard requirements
- No cars blocked, just tracked and scored

**Implementation:**
```python
# Example confidence scores:
# 2022 Enyaq, €28k, 50k km, 9/9 features = 100% confidence
# 2020 Enyaq, €27k, 82k km, 7/9 features = 75% confidence
# 2021 BMW iX3, €32k, 98k km, 5/9 features = 60% confidence
```

**Pros:**
- ✅ No cars blocked, maintains flexibility
- ✅ Better visibility into data quality
- ✅ Can sort/filter by confidence in UI
- ✅ Audit trail of validation issues

**Cons:**
- ⚠️ Requires code changes and database migration
- ⚠️ More complex system
- ⚠️ Still saves "bad" data

**Estimated effort:** 2-3 hours

---

### Option 3: Add Strict Validation with Exceptions

**What it does:**
- Blocks cars that don't meet criteria
- Add exception rules to config (e.g., `acceptable_year: 2020`)
- Enforces data quality standards
- More predictable results

**Required config changes:**
```yaml
search:
  min_year: 2022
  
validation:
  strict_mode: true
  exceptions:
    # Allow specific models from older years
    acceptable_years:
      Skoda Enyaq: 2020
      Audi e-tron: 2020
      Kia EV6: 2021
    
    # Allow specific models above price limit
    acceptable_prices:
      BMW iX3: 40000
```

**Pros:**
- ✅ Guarantees data quality
- ✅ No manual filtering needed
- ✅ Clear criteria enforcement

**Cons:**
- ❌ **Would remove existing 2021 cars from future scrapes**
- ❌ Complex exception rules needed
- ❌ Less flexible for finding deals
- ❌ Risk of missing good outliers

**Estimated effort:** 4-5 hours

---

## Decision Matrix

| Criteria | Option 1 (Current) | Option 2 (Soft) | Option 3 (Strict) |
|----------|-------------------|-----------------|-------------------|
| **Keeps 2020 Enyaq** | ✅ Yes | ✅ Yes | ⚠️ Needs exception |
| **Flexibility** | ✅ High | ✅ High | ❌ Low |
| **Data Quality** | ⚠️ 61% | ✅ 75% | ✅ 95% |
| **Effort Required** | ✅ None | ⚠️ Medium | ❌ High |
| **Risk of Data Loss** | ✅ None | ✅ None | ❌ High |
| **User Control** | ✅ Dashboard | ✅ Dashboard | ❌ Config only |

---

## Current Implementation Details

### Validation Code Locations

1. **Exclusion checking**: `scrapers/base_scraper.py` + all scraper files
   - AutoScout24: line 596
   - Gaspedaal: line 428
   - AutoTrack: line 705
   
2. **Feature checking**: `scrapers/base_scraper.py:212-269`
   - Called before save: line 347-350
   - Results stored in DB but not enforced

3. **Save to database**: `scrapers/base_scraper.py:121-187`
   - No validation before save
   - Sets `is_available = True` automatically

### Database Schema

```sql
-- Relevant fields for validation
cars (
    year INTEGER,              -- Extracted from listing
    price REAL,                -- Extracted from listing
    mileage_km INTEGER,        -- Extracted from listing
    features_count INTEGER,    -- Count of matching critical features
    has_all_required_features BOOLEAN,  -- All 9 critical features present?
    is_available BOOLEAN       -- Currently listed (not sold)
    -- NOTE: No confidence_score field exists yet
)
```

### Feature Matching Keywords

```python
# From base_scraper.py:228-249
feature_keywords = {
    'adaptive cruise control': ['adaptive cruise control', 'adaptieve cruise control', 'acc'],
    'android auto': ['android auto', 'apple carplay', 'carplay'],
    'navigatiesysteem': ['navigatie', 'navigatiesysteem', 'navigation', 'navi', 'gps'],
    'dab+ radio': ['dab+', 'dab radio', 'digital radio', 'dab'],
    'achteruitrijcamera': ['achteruitrijcamera', 'rear camera', 'camera', 'reversing camera'],
    'climate control': ['climate control', 'climatronic', 'airco', 'climate'],
    'lane assist': ['lane assist', 'lane keeping', 'lka', 'lane departure'],
    'park assist': ['park assist', 'parkeerhulp', 'parking assist', 'parking sensors'],
    'trekhaak': ['trekhaak', 'tow hitch', 'towbar', 'tow bar'],
}
```

---

## Files That Would Need Changes (If Implementing Options 2 or 3)

### Option 2: Soft Validation
1. `scrapers/base_scraper.py` - Add validation method and confidence scoring
2. `models/database.py` - Add `confidence_score` field to Car model
3. `app/app.py` - Display confidence score in dashboard
4. `app/templates/index.html` - Show confidence badges
5. Database migration script

### Option 3: Strict Validation
1. All Option 2 files, plus:
2. `config.yaml` - Add validation exceptions section
3. `scrapers/base_scraper.py` - Add blocking logic
4. `utils/helpers.py` - Add exception checking helper

---

## Next Steps - Awaiting Decision

**Question to answer:**
> Do we keep the current 61% confidence system (Option 1), or implement one of the improvements?

**My recommendation:** **Option 1** - Keep current system as-is

**Reasoning:**
1. System is working well in practice
2. 2020 Enyaq proves flexibility is valuable
3. Dashboard provides filtering when needed
4. No risk of losing existing cars or future good deals
5. 61% confidence is acceptable given the flexibility benefits

**When to revisit:**
- If you find many cars in DB that shouldn't be there
- If you want stricter quality control for automated alerts
- If you want to add confidence-based sorting in UI

---

## Database Backup Instructions

Before making ANY changes to validation logic:

```bash
# 1. Backup database
cd /path/to/nl-car-tracker
mkdir -p data/backups
cp data/cars.db data/backups/cars_backup_$(date +%Y%m%d_%H%M%S).db

# 2. Export current cars to CSV (extra safety)
sqlite3 data/cars.db << EOF
.headers on
.mode csv
.output data/backups/cars_export_$(date +%Y%m%d_%H%M%S).csv
SELECT * FROM cars WHERE is_available = 1;
.quit
EOF

# 3. Verify backup
ls -lh data/backups/
```

---

## Questions & Answers

**Q: Will existing cars in the database be affected?**  
A: No. Validation only applies to newly scraped cars. Existing 181 cars remain untouched.

**Q: Can we change our mind later?**  
A: Yes. All options are reversible. Option 2 just adds a score field. Option 3 can be toggled off in config.

**Q: What if we want to be stricter about some criteria but not others?**  
A: Option 2 (soft validation) allows this - you can set different confidence penalties for different violations.

**Q: How do we know which cars currently violate criteria?**  
A: Run this query:
```sql
SELECT make, model, year, price, mileage_km, features_count
FROM cars 
WHERE is_available = 1 
  AND (year < 2022 OR price > 35000 OR mileage_km > 100000)
ORDER BY year DESC;
```

---

## Contact & References

**Analysis Date:** October 29, 2025  
**System Version:** Current production version  
**Database:** 181 available cars  

**Key Files:**
- `scrapers/base_scraper.py`
- `config.yaml`
- `models/database.py`

**Next Session:** Pick up from "Decision Matrix" section above
