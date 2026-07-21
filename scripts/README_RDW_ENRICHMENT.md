# RDW WLTP Range Enrichment Tool

## Overview

This script verifies and enriches the `data/wltp_ranges.yaml` file using official RDW (Dutch Vehicle Authority) Open Data. It cross-validates existing YAML entries, identifies discrepancies, and can discover new popular EV models.

## Features

- **Cross-validation**: Compares YAML WLTP ranges against official RDW data
- **Discrepancy Detection**: Flags entries with >5% difference from official values
- **Automated Updates**: Can automatically update YAML with verified RDW data
- **Discovery Mode**: Finds popular models not yet in the YAML
- **Detailed Reporting**: Generates comprehensive verification reports

## Usage

### Basic Verification (Read-only)
```bash
cd /path/to/nl-car-tracker
python scripts/enrich_wltp_from_rdw.py
```

This will:
- Verify all YAML entries against RDW
- Print a detailed report to console
- Save report to `tmp/rdw_verification_report_TIMESTAMP.txt`
- **Not modify** the YAML file

### Auto-Update Mode
```bash
python scripts/enrich_wltp_from_rdw.py --auto-update
```

This will:
- Verify all entries
- Automatically update YAML with RDW-verified values
- Create a backup: `data/wltp_ranges.yaml.backup.TIMESTAMP`
- Save report to `tmp/`

### Discovery Mode
```bash
python scripts/enrich_wltp_from_rdw.py --discover-new
```

This will:
- Query RDW for popular EV models (recent registrations)
- List models not yet in the YAML
- Help you identify missing makes/models to add

### Output to Custom File
```bash
python scripts/enrich_wltp_from_rdw.py --output tmp/enriched_wltp.yaml
```

### Verbose Mode (for debugging)
```bash
python scripts/enrich_wltp_from_rdw.py --verbose
```

### Test Mode (limit processing)
```bash
python scripts/enrich_wltp_from_rdw.py --limit 5 --verbose
```

Tests the first 5 makes with detailed logging

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--auto-update` | Automatically update YAML file with verified RDW data (creates backup) |
| `--discover-new` | Query RDW for popular models not in YAML |
| `--output FILE` | Write enriched YAML to specified file |
| `--verbose` | Enable detailed logging (shows API calls and responses) |
| `--limit N` | Limit number of makes to process (useful for testing) |

## Output Report

The verification report includes:

### Summary Statistics
- Total entries checked
- ✓ Verified entries (within 5% of RDW)
- ⚠️ Discrepancies found (>5% difference)
- ❌ Not found in RDW

### Discrepancies Section
Lists all entries with significant differences:
```
BMW iX 105 kWh
  YAML: 630 km  |  RDW: 610 km  |  Diff: 3.2%
  Suggested: Update YAML to 610 km
```

### Not Found Section
Lists entries that couldn't be verified in RDW (may be discontinued models or naming mismatches)

## How It Works

### Data Flow
1. **Load YAML**: Reads `data/wltp_ranges.yaml`
2. **Query RDW**: For each make/model/battery combination:
   - Searches RDW vehicle registration database
   - Finds matching vehicles by make and model name
   - Fetches fuel/range data for those vehicles
   - Extracts WLTP range values
3. **Compare**: Calculates discrepancy between YAML and RDW
4. **Report**: Generates detailed verification report
5. **Update** (optional): Updates YAML with RDW-verified values

### RDW API Details
- **Vehicle Database**: `m9d7-ebf2` (Gekentekende voertuigen)
- **Fuel/Range Database**: `8ys7-d773` (Gekentekende voertuigen brandstof)
- **Coverage**: 699,332+ registered electric vehicles
- **Fields Used**:
  - `actie_radius_enkel_elektrisch_wltp` - Full EV WLTP range
  - `actie_radius_extern_opladen_wltp` - PHEV electric-only range
- **Free & Open**: No authentication required

### Matching Logic
- **Make/Model**: Case-insensitive matching using first word of model
- **Battery Capacity**: Optional matching with 20% tolerance
- **Range Selection**: Most common range among matching vehicles
- **Sanity Checks**: Filters out unrealistic values (<30 km or >1000 km)

## Rate Limiting

The script includes automatic rate limiting (0.5 seconds between API calls) to avoid overwhelming the RDW Open Data API. A full verification of the entire YAML file takes approximately 10-15 minutes.

## Example Workflow

### Monthly Verification
```bash
# Run verification to check for discrepancies
python scripts/enrich_wltp_from_rdw.py --discover-new

# Review the report in tmp/
cat tmp/rdw_verification_report_*.txt

# If discrepancies look reasonable, apply auto-update
python scripts/enrich_wltp_from_rdw.py --auto-update

# Check the changes
git diff data/wltp_ranges.yaml

# If satisfied, commit
git add data/wltp_ranges.yaml
git commit -m "Update WLTP ranges from RDW official data"
```

### Testing New Makes/Models
```bash
# Quick test with verbose output
python scripts/enrich_wltp_from_rdw.py --limit 3 --verbose

# Check what new models are popular
python scripts/enrich_wltp_from_rdw.py --discover-new | grep -A 20 "NEW MODELS"
```

## Safety Features

1. **Automatic Backups**: Always creates a timestamped backup before updating
2. **Read-only by Default**: Must explicitly use `--auto-update` to modify YAML
3. **5% Threshold**: Only flags significant discrepancies (>5% difference)
4. **Manual Review**: Outputs to `tmp/` for review before applying
5. **Sanity Checks**: Filters unrealistic range values

## Troubleshooting

### "Not found in RDW"
This can happen for:
- Discontinued models
- Very new models not yet registered
- Name mismatches (e.g., "XC40" in YAML, "XC40 RECHARGE" in RDW)
- Non-Dutch market models

### Unexpected Discrepancies
- Check if YAML lists an older/newer model year
- Verify battery capacity matches (some models have multiple battery options)
- RDW data reflects actual registered vehicles in NL, which may differ from manufacturer specs

### API Timeout/Errors
- Script includes 15-second timeouts and automatic retries
- If persistent, try running with `--limit` to process fewer entries
- Check https://opendata.rdw.nl/ for API status

## Files Generated

- **Report**: `tmp/rdw_verification_report_TIMESTAMP.txt`
- **Backup** (if --auto-update): `data/wltp_ranges.yaml.backup.TIMESTAMP`
- **Updated YAML** (if --auto-update or --output): Original or specified file

## Integration with Car Tracker

This script maintains the YAML file that is used as the **primary** WLTP lookup source in the car tracking system. The workflow is:

1. **YAML** (fast, curated) → Used first
2. **RDW API** (live fallback) → Used if not in YAML
3. **EV-Database** (real-world ranges) → Separate data source

By keeping the YAML verified with RDW data, you ensure:
- Fast lookups without API calls
- Accurate official WLTP values
- Coverage of popular models in the Netherlands
