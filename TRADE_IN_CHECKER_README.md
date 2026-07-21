# Trade-In Value Checker

## Overview

The Trade-In Value Checker is a new feature that helps you track the market value of your current car over time. It integrates with:
- **RDW (Dutch vehicle registration)**: Automatically fetches your car details from license plate
- **AutoScout24.nl**: Retrieves current market valuation (asking price, market value, selling price)

## What Was Implemented

### 1. Database Tables (models/database.py)

Two new database tables were added:

**CurrentCar Table:**
- Stores your current vehicle information
- Fields: license_plate, make, model, year, mileage, fuel_type, body_type, color
- Auto-populated from RDW API using license plate

**TradeInValue Table:**
- Tracks historical valuation data for your car
- Fields: asking_price, market_value, selling_price, mileage_km, checked_at
- Links to CurrentCar table
- Stores all valuation checks over time to show trends

### 2. Trade-In Checker Utility (utils/trade_in_checker.py)

A comprehensive utility class that:
- Fetches vehicle details from RDW Open Data API
- Scrapes AutoScout24.nl's valuation tool using Selenium
- Stores valuation history in the database
- Provides command-line interface for manual checks

### 3. Configuration (config.yaml)

Added new sections:

```yaml
current_car:
  license_plate: XX-XXX-X
  mileage_km: 0  # TODO: Update with actual mileage
  make: OPEL
  model: ASTRA SPORTS TOURER+
  year: 2018

trade_in_checker:
  enabled: true
  check_interval_hours: 168  # Check weekly
  autoscout24_url: https://www.autoscout24.nl/waardebepaling/
```

## Setup & Usage

### Step 1: Update Your Current Mileage

Edit `config.yaml` and update the mileage:

```yaml
current_car:
  license_plate: XX-XXX-X
  mileage_km: 45000  # <-- Update this with your actual mileage
```

### Step 2: Run the Trade-In Checker

Run manually from command line:

```bash
# Use values from config.yaml
python -m utils.trade_in_checker

# Or specify license plate and mileage directly
python -m utils.trade_in_checker XX-XXX-X 45000
```

### Step 3: View Results

The checker will:
1. Look up your car details from RDW (if not already in database)
2. Visit AutoScout24.nl's valuation page
3. Fill in license plate and mileage
4. Extract the valuation results
5. Save to database

## Your Vehicle Information

Based on RDW lookup for **XX-XXX-X**:

- **Make:** OPEL
- **Model:** ASTRA SPORTS TOURER+
- **Year:** 2018
- **Body Type:** Personenauto (Passenger car)
- **Color:** GRIJS (Grey)

## How It Works

### RDW API Integration

The checker uses the RDW Open Data API to fetch official vehicle registration data:

```python
checker = TradeInChecker()
rdw_data = checker.get_rdw_data('XX-XXX-X')
```

This automatically retrieves:
- Make and model
- Registration year
- Fuel type
- Body type
- Color

### AutoScout24 Valuation

The checker automates the AutoScout24.nl valuation process:

1. Opens the valuation page in headless browser (Selenium)
2. Fills in license plate and mileage
3. Submits the form
4. Extracts three values:
   - **Asking Price (Vraagprijs)**: Suggested asking price if selling privately
   - **Market Value (Dagwaarde)**: Current market value
   - **Selling Price (Verkoopprijs)**: Estimated actual selling price

### Database Storage

All valuations are stored with timestamps, allowing you to:
- Track value depreciation over time
- See how mileage affects value
- Make informed decisions about when to sell

## Scheduled Checks (Future Enhancement)

The configuration supports scheduled checks (weekly by default), but integration with the existing scheduler needs to be completed. This would allow automatic weekly valuation updates.

## Next Steps

### Required Before First Use:
1. ✅ Update mileage in config.yaml
2. ⏳ Run the checker to test AutoScout24 integration
3. ⏳ Verify the HTML selectors match AutoScout24's current page structure

### Optional Enhancements:
- Add dashboard page to view trade-in value history
- Create charts showing value depreciation over time
- Compare your car's value against potential new cars
- Email notifications when value drops significantly
- Integration with existing scheduler for automatic weekly checks

## Testing

A test script is included to verify RDW API integration:

```bash
python test_rdw_lookup.py
```

This confirms the license plate lookup works correctly.

## Important Notes

### AutoScout24 Page Scraping

The AutoScout24 valuation extraction uses CSS selectors that may need adjustment if the website changes their HTML structure. The current implementation includes:

- Placeholder selectors for asking price, market value, and selling price
- Screenshot capture on errors (saved to `tmp/` directory)
- Full page text logging for debugging

**You will likely need to inspect the AutoScout24 page and update the selectors in `check_autoscout24_value()` method.**

### Browser Requirements

- Chrome/Chromium browser must be installed
- ChromeDriver is managed automatically by webdriver-manager
- Headless mode is enabled by default (can be changed in config.yaml)

### Rate Limiting

AutoScout24 may have rate limiting. The weekly check interval (168 hours) is intentionally conservative to avoid issues.

## Troubleshooting

### License Plate Not Found
- Verify the license plate format (e.g., XX-123-X)
- Check that the vehicle is registered in the Netherlands
- The RDW API may have temporary outages

### AutoScout24 Extraction Fails
- Check the error screenshot in `tmp/` directory
- Inspect AutoScout24's page structure
- Update CSS selectors in `check_autoscout24_value()` method
- Try disabling headless mode for debugging (set `headless: false` in config.yaml)

### Database Errors
- Ensure database tables are created (they're auto-created on first run)
- Check database file permissions
- Verify SQLAlchemy version compatibility

## File Structure

```
nl-car-tracker/
├── config.yaml                    # Configuration (updated)
├── models/
│   └── database.py               # Database models (updated)
├── utils/
│   └── trade_in_checker.py       # New trade-in checker utility
├── test_rdw_lookup.py            # RDW API test script
├── tmp/                          # Screenshots and debug files
└── TRADE_IN_CHECKER_README.md    # This file
```

## API References

- **RDW Open Data API**: https://opendata.rdw.nl/
  - Endpoint: `/resource/m9d7-ebf2.json` (Gekentekende voertuigen)
- **AutoScout24 Valuation**: https://www.autoscout24.nl/waardebepaling/
