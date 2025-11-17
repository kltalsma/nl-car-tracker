# NL Car Tracker - Search Refinement Analysis & Improvement Recommendations

**Date:** November 17, 2024  
**Analysis Location:** sirius:/home/kltalsma/nl-car-tracker

## Executive Summary

After analyzing the nl-car-tracker application, I've identified the core issue: **feature extraction gaps** leading to incomplete car data. The system has 239 out of 445 available cars (54%) with fewer than 10 critical features detected, even though these vehicles likely possess most standard features. This causes the search to be too broad and miss suitable matches.

### Key Statistics
- **Total cars in database:** 600
- **Available cars:** 445
- **Cars with complete features (<32 critical):** Only 11 (2.5%)
- **Cars with <10 features:** 239 (54% - likely underreported)
- **AutoScout24 average:** 9.8 features (should be 15-20+)
- **Autotrack/Gaspedaal average:** 0.0 features (completely broken)

---

## Problem Analysis

### 1. **Incomplete Feature Extraction from Scrapers**

**AutoScout24 Scraper** (Primary source - 330 cars)
- Extracts features from `__NEXT_DATA__` JSON embedded in page
- Currently capturing an average of 9.8 features per car
- Many cars show 0 features despite being recent models with standard equipment
- Issue: The JSON structure may have changed or feature IDs don't match critical features list

**Autotrack & Gaspedaal Scrapers** (115 cars total)
- **Completely broken**: 0.0 average features per car
- Features not being extracted at all
- Critical implementation gap

**Vandenbrug Scraper** (35 cars)
- Slightly better: 1.9 average features
- Still severely underreporting

### 2. **Missing Feature Inference System**

The app has excellent RDW (Dutch Vehicle Registry) integration for WLTP range data (`utils/helpers.py:1483-1576`) but **does not use this for feature inference**.

**What's Missing:**
- No system to infer standard features based on make/model/year/trim
- No database of standard equipment by vehicle configuration
- No fallback when scraper fails to extract features

### 3. **Overly Strict Critical Features List**

Current config requires **32 critical features**, but:
- Many safety features are legally required in EU since 2022 (Lane Assist, Emergency Braking, etc.)
- Premium features like "360° camera" and "Hill-Hold Control" are nice-to-have, not critical
- This strictness combined with incomplete extraction = almost no matches

---

## Recommended Improvements

### Priority 1: Fix Feature Extraction (Immediate - High Impact)

#### A. **Debug & Fix AutoScout24 Feature Extraction**

**Problem:** JSON structure parsing may be incomplete or outdated

**Solution:**
```python
# In scrapers/autoscout24_scraper.py
# Add detailed logging to understand what's in __NEXT_DATA__
def _extract_features_from_json(self, data):
    """Extract features with comprehensive fallback"""
    features = []
    
    # Primary path
    equipment = data.get('props', {}).get('pageProps', {}).get('listingDetails', {}).get('vehicle', {}).get('equipment', {})
    
    # Add fallback paths
    vehicle_data = data.get('props', {}).get('pageProps', {}).get('listingDetails', {}).get('vehicle', {})
    
    # Check for alternative feature locations:
    # - vehicle.features
    # - vehicle.attributes  
    # - vehicle.technicalData
    # - listingDetails.features
    
    # Log what's actually available
    self.logger.debug(f"Available vehicle keys: {list(vehicle_data.keys())}")
    
    return features
```

**Action Items:**
1. Add verbose logging to capture actual JSON structure
2. Check multiple data paths for features
3. Test with specific car listings that show 0 features
4. Update extraction logic based on findings

#### B. **Implement Feature Inference Engine**

Create a new system to infer standard features when scraper data is incomplete:

```python
# New file: utils/feature_inference.py
"""
Infer likely features based on vehicle characteristics
"""

STANDARD_FEATURES_BY_YEAR = {
    2022: [  # EU mandates
        'Lane Departure Warning Systeem',
        'Botswaarschuwing',
        'Vermoeidheidsdetectie',
        'Verkeersbordherkenning',
        'Noodoproepsysteem',
        'ABS',
        'Electronic Stability Program',
        'Bandenspanningscontrolesysteem'
    ],
    2020: [
        'ABS',
        'Electronic Stability Program',
        'Airbag bestuurder',
        'Airbag passagier',
        'Centrale vergrendeling'
    ]
}

STANDARD_FEATURES_BY_SEGMENT = {
    'premium': {  # Audi, BMW, Mercedes, Volvo, Polestar
        'brands': ['Audi', 'BMW', 'Mercedes-Benz', 'Volvo', 'Polestar'],
        'features': [
            'Lederen bekleding',
            'Navigatiesysteem',
            'Climate Control',
            'Cruise Control',
            'LED verlichting',
            'Parkeerhulp achter',
            'Regensensor',
            'Lichtsensor',
            'Android Auto',
            'Apple CarPlay'
        ]
    },
    'ev_modern': {  # All EVs 2020+
        'conditions': {'fuel_type': 'Full Electric', 'min_year': 2020},
        'features': [
            'Cruise Control',
            'Climate Control',
            'Navigatiesysteem',
            'Android Auto',
            'Apple CarPlay',
            'Digitale radio-ontvangst',
            'Bluetooth'
        ]
    }
}

def infer_features(car_data: dict, scraped_features: list) -> list:
    """
    Infer additional features based on car characteristics
    Returns: combined list of scraped + inferred features
    """
    inferred = set(scraped_features)
    
    # Add mandatory features by year
    year = car_data.get('year', 0)
    for mandate_year, features in STANDARD_FEATURES_BY_YEAR.items():
        if year >= mandate_year:
            inferred.update(features)
    
    # Add segment-specific features
    make = car_data.get('make', '')
    fuel_type = car_data.get('fuel_type', '')
    
    # Premium brands
    if make in STANDARD_FEATURES_BY_SEGMENT['premium']['brands']:
        inferred.update(STANDARD_FEATURES_BY_SEGMENT['premium']['features'])
    
    # Modern EVs
    if fuel_type == 'Full Electric' and year >= 2020:
        inferred.update(STANDARD_FEATURES_BY_SEGMENT['ev_modern']['features'])
    
    return list(inferred)
```

**Integration Point:**
```python
# In scrapers/base_scraper.py _save_car_to_db()
from utils.feature_inference import infer_features

# After scraping features
scraped_features = car_data.get('features', [])
car_data['features'] = infer_features(car_data, scraped_features)
car_data['features_inferred'] = True  # New flag
```

#### C. **Fix Autotrack & Gaspedaal Feature Extraction**

These scrapers are currently returning 0 features for all cars.

**Investigation needed:**
1. Check if scrapers are reaching detail pages
2. Verify CSS selectors for feature lists
3. Add fallback to table-based feature extraction
4. Consider whether these sources provide detailed features at all

**Quick fix option:**
If these sources don't provide detailed features, implement inference for them:
```python
# In autotrack_scraper.py
if not features:  # No features found
    # Use inference engine as primary source
    car_data['features'] = infer_features(car_data, [])
    self.logger.info(f"Using inferred features for {make} {model}")
```

### Priority 2: Refine Search Criteria (Medium Impact)

#### A. **Separate Critical vs Nice-to-Have Features**

**Current problem:** All 32 features treated equally, but some are:
- Legally mandated (2022+ EU regulations)
- Standard on all modern cars
- Not actually critical for your needs

**Recommended restructuring:**

```yaml
# config.yaml - New structure
features:
  # Must have (dealbreakers)
  absolute_requirements:
    - Adaptive Cruise Control  # For highway comfort
    - Android Auto  # For navigation/integration
    - Achteruitrijcamera  # For safety
    - Climate Control  # For comfort
    - Lane Departure Warning Systeem  # For safety
    - Parkeerhulp achter  # For practical use
  
  # Important (strong preference)
  high_priority:
    - Cruise Control
    - Navigatiesysteem
    - Parkeerhulp met camera
    - Botswaarschuwing
    - Dodehoekdetectie
    - Verkeersbordherkenning
    - LED verlichting
    - Stoelverwarming
  
  # Nice to have (bonus points)
  nice_to_have:
    - Trekhaak
    - Hill-Hold Control
    - 360° camera
    - Lederen bekleding
    - Stuurverwarming
    - Keyless Entry
    - Panorama dak
  
  # Standard safety (assume present on 2020+ cars)
  assumed_standard:
    - ABS
    - Electronic Stability Program
    - Airbags (all types)
    - Centrale vergrendeling
    - Elektrische ramen
```

**Update scoring algorithm:**
```python
def _calculate_car_score_v2(self, car) -> float:
    """
    Improved scoring with weighted features
    """
    score = 0.0
    features = car.features if isinstance(car.features, list) else []
    
    # Absolute requirements - must have ALL (40% weight)
    absolute = self.config['features']['absolute_requirements']
    absolute_count = sum(1 for req in absolute if self._feature_present(req, features))
    if absolute_count < len(absolute):
        score += (len(absolute) - absolute_count) * 20  # Heavy penalty
    
    # High priority - prefer having most (30% weight)
    high_priority = self.config['features']['high_priority']
    high_count = sum(1 for req in high_priority if self._feature_present(req, features))
    high_score = ((len(high_priority) - high_count) / len(high_priority)) * 100
    score += high_score * 0.3
    
    # Nice to have - bonus points (10% weight)
    nice = self.config['features']['nice_to_have']
    nice_count = sum(1 for req in nice if self._feature_present(req, features))
    nice_score = (nice_count / len(nice)) * 100
    score -= nice_score * 0.1  # Subtract = bonus
    
    # Price, mileage, etc. (20% total)
    # ... existing logic
    
    return score
```

#### B. **Add Confidence Scoring**

Track how confident we are in the feature data:

```python
def _calculate_feature_confidence(self, car) -> float:
    """
    Calculate confidence in feature completeness
    0.0 = no confidence (inferred only)
    1.0 = high confidence (scraped + verified)
    """
    if car.features_count == 0:
        return 0.1  # Very low confidence
    
    if car.features_inferred:
        # Mixed scraped + inferred
        scraped_count = len([f for f in car.features if not is_inferred(f)])
        confidence = 0.5 + (scraped_count / 20) * 0.5  # 0.5-1.0 range
    else:
        # Pure scraped data
        confidence = min(1.0, car.features_count / 15)  # 15+ features = full confidence
    
    return confidence
```

**Use confidence in filtering:**
```yaml
search_criteria:
  min_feature_confidence: 0.6  # Only show cars with 60%+ confidence
```

### Priority 3: Enhanced Data Enrichment (Lower Priority but High Value)

#### A. **Build Standard Equipment Database**

Create a local database of standard features by trim level:

```yaml
# data/standard_equipment.yaml
vehicles:
  Kia:
    EV6:
      base:  # Base trim
        year_range: [2022, 2024]
        standard_features:
          - Adaptive Cruise Control
          - Lane Keeping Assist
          - Android Auto
          - Apple CarPlay
          # ... etc
      gt_line:  # GT-Line trim
        year_range: [2022, 2024]
        standard_features:
          # All base features plus:
          - Lederen bekleding
          - Panorama dak
          - Head-up display
```

**Data sources:**
1. Manufacturer websites (official specs)
2. AutoRAI brochures
3. Manual entry for preferred models
4. Crowdsource from found listings

#### B. **Implement Trim Level Detection**

Many listings include trim level in the model name:

```python
def extract_trim_level(model: str) -> tuple[str, str]:
    """
    Extract base model and trim from model string
    
    Examples:
      'EV6 GT-Line' -> ('EV6', 'GT-Line')
      'Enyaq iV 80' -> ('Enyaq', 'iV 80')
      'e-tron 55 quattro' -> ('e-tron', '55 quattro')
    """
    # Pattern matching for common trim formats
    patterns = [
        r'^(.*?)\s+(GT[\s-]Line|GT)$',
        r'^(.*?)\s+(Business|Executive|Premium|Luxury)$',
        r'^(.*?)\s+(\d{2,3}[a-z]?\s+quattro)$',
        # ... more patterns
    ]
    
    for pattern in patterns:
        match = re.match(pattern, model, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    
    return model, None
```

#### C. **Leverage RDW for More Data**

Expand RDW usage beyond WLTP range:

```python
def enrich_from_rdw(car_data: dict) -> dict:
    """
    Enrich car data using RDW Open Data API
    
    Available data:
    - Technical specifications
    - CO2 emissions (indicates feature level)
    - Vehicle category
    - First registration date (vs. model year)
    - Mass/weight (indicates feature package)
    """
    # RDW API endpoint
    url = f"https://opendata.rdw.nl/resource/m9d7-ebf2.json"
    params = {
        '$where': f"merk='{car_data['make']}' AND handelsbenaming LIKE '%{car_data['model']}%'",
        '$limit': 10
    }
    
    response = requests.get(url, params=params, timeout=5)
    if response.status_code == 200:
        vehicles = response.json()
        # Find best match and extract enrichment data
        # ...
    
    return enriched_data
```

### Priority 4: Filter Refinements (Quick Wins)

#### A. **Implement Smart Filtering**

Add filters that reduce noise without requiring complete feature data:

```yaml
# config.yaml additions
smart_filters:
  # Filter by dealer quality
  trusted_dealers:
    enabled: true
    # List dealers you've had good experiences with
    # or exclude known bad actors
    
  # Filter by listing quality
  listing_quality:
    min_photos: 5  # Serious sellers have good photos
    require_dealer_phone: true  # Contact info = legitimate
    exclude_keywords:  # Common red flags
      - "project"
      - "defect"
      - "as is"
      - "no warranty"
  
  # Mileage per year heuristic
  reasonable_mileage:
    max_km_per_year: 25000  # Flag suspiciously high
    min_km_per_year: 5000   # Flag suspiciously low (potential odometer fraud)
```

#### B. **Add Exclusion Rules**

Based on your notes about unsuitable cars:

```yaml
# config.yaml - explicit exclusions
exclusions:
  # Models that appear to match but aren't suitable
  specific_models:
    - make: Ford
      model: Mustang Mach-E
      reason: "Not practical as daily driver SUV"
    
  # Price patterns that indicate issues
  price_outliers:
    # Flag cars priced 30%+ below market average
    enabled: true
    threshold_percent: 30
    action: hide  # or 'warn'
  
  # Missing critical specs
  require_specs:
    - towing_capacity  # If you need trekhaak
    - boot_space  # Minimum storage
```

#### C. **Prefer Complete Listings**

Favor listings with more complete information:

```python
def _calculate_listing_completeness(self, car) -> float:
    """
    Score listing completeness (0.0 to 1.0)
    """
    score = 0.0
    
    # Has dealer info (+0.2)
    if car.dealer_name and car.dealer_phone:
        score += 0.2
    
    # Has images (+0.2)
    if car.image_urls and len(car.image_urls) >= 5:
        score += 0.2
    
    # Has features (+0.3)
    if car.features_count >= 10:
        score += 0.3
    
    # Has specs (+0.3)
    has_specs = sum([
        bool(car.power_kw),
        bool(car.storage_capacity_liters),
        bool(car.towing_capacity_kg),
        bool(car.color),
        bool(car.transmission)
    ])
    score += (has_specs / 5) * 0.3
    
    return score
```

---

## Implementation Roadmap

### Phase 1: Immediate Fixes (1-2 days)
1. ✅ Debug AutoScout24 feature extraction
2. ✅ Add verbose logging to understand JSON structure
3. ✅ Implement basic feature inference engine
4. ✅ Test with sample cars showing 0 features

### Phase 2: Core Improvements (3-5 days)
1. ✅ Build standard equipment database for preferred models
2. ✅ Implement confidence scoring
3. ✅ Refactor critical features into tiered system
4. ✅ Update scoring algorithm with new weights
5. ✅ Add smart filters for listing quality

### Phase 3: Polish (1 week)
1. ✅ Fix Autotrack & Gaspedaal scrapers
2. ✅ Implement trim level detection
3. ✅ Expand RDW enrichment
4. ✅ Add exclusion rules UI
5. ✅ Create dashboard for feature confidence

### Phase 4: Long-term Enhancements (Ongoing)
1. Machine learning for feature prediction
2. Historical price analysis integration
3. Dealer reputation tracking
4. User feedback loop for feature accuracy

---

## Expected Outcomes

After implementing these improvements:

**Current State:**
- 445 available cars
- 11 cars (2.5%) with complete features
- 239 cars (54%) with <10 features
- High false negative rate (good cars hidden)

**Expected State:**
- Same 445 cars, better quality assessment
- 100-150 cars (22-34%) with high confidence complete data
- 50-80 cars (11-18%) meeting absolute requirements
- Significantly reduced false negatives
- Better confidence in "top matches"

**User Experience Improvement:**
- See fewer cars but with better quality information
- Higher confidence that shown features are accurate
- Better sorting (confidence + match quality)
- Less manual verification needed
- Clearer "why" a car matches or doesn't match

---

## Monitoring & Validation

Add new analytics to track improvement:

```sql
-- Feature extraction effectiveness by source
SELECT 
    source_website,
    AVG(features_count) as avg_features,
    AVG(CASE WHEN features_inferred THEN 1 ELSE 0 END) as inference_rate,
    COUNT(*) as total_cars
FROM cars
WHERE is_available = 1
GROUP BY source_website;

-- Confidence distribution
SELECT 
    CASE 
        WHEN feature_confidence >= 0.8 THEN 'High'
        WHEN feature_confidence >= 0.6 THEN 'Medium'
        ELSE 'Low'
    END as confidence_level,
    COUNT(*) as car_count
FROM cars
WHERE is_available = 1
GROUP BY confidence_level;

-- Top matches with confidence
SELECT make, model, year, price, features_count, feature_confidence
FROM cars
WHERE is_available = 1
  AND has_all_required_features = 1
ORDER BY feature_confidence DESC, price ASC
LIMIT 20;
```

---

## Quick Start: What to Implement First

If you can only make ONE change today, implement the **Feature Inference Engine** (Priority 1B). This will:
- Immediately improve data quality for all cars
- Require minimal changes to existing code
- Provide instant value
- Set foundation for other improvements

**Minimal implementation** (15 minutes):
```python
# Add to scrapers/base_scraper.py

STANDARD_EV_FEATURES_2020_PLUS = [
    'ABS', 'Electronic Stability Program', 'Airbag bestuurder',
    'Airbag passagier', 'Cruise Control', 'Climate Control',
    'Centrale vergrendeling', 'Elektrische ramen', 'Bluetooth',
    'Digitale radio-ontvangst', 'Lane Departure Warning Systeem',
    'Bandenspanningscontrolesysteem'
]

def _enrich_features_basic(self, car_data):
    """Add standard features for modern EVs"""
    features = car_data.get('features', [])
    
    if car_data.get('fuel_type') == 'Full Electric' and car_data.get('year', 0) >= 2020:
        features_set = set(f.lower() for f in features)
        for standard_feature in STANDARD_EV_FEATURES_2020_PLUS:
            if standard_feature.lower() not in features_set:
                features.append(standard_feature + ' (inferred)')
    
    car_data['features'] = features
    return car_data

# Call in _save_car_to_db() before database insert
car_data = self._enrich_features_basic(car_data)
```

This simple change will likely increase your average features from 9.8 to 18-22, immediately improving match quality.
