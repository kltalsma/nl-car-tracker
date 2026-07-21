# Session Log: Log Files Reference
**Date**: 2025-11-04 11:04  
**Session Focus**: Log file locations and monitoring commands

---

## Session Context

This session followed the completion of the depreciation calculator feature. The user asked about which log files to monitor for the nl-car-tracker application.

## System Status Check

### Flask Application
- **Status**: Running ✅
- **PID**: 73210
- **Port**: 5001
- **Process**: `python app/app.py`

### Depreciation API
- **Endpoint**: `GET /api/calculate-depreciation`
- **Status**: Working ✅
- **Current Value**: €7,553 (from €16,750 purchase price)
- **Depreciation**: €9,197 (54.91%)
- **Car Age**: 7.38 years

### Database
- **Current Car**: XX-XXX-X (OPEL ASTRA SPORTS TOURER+ 2018)
- **Current Mileage**: 151,000 km
- **Purchase Date**: 2018-06-18
- **Purchase Price**: €16,750
- **Actual km/year**: 20,457 (high mileage)

---

## Log Files Reference

### Primary Log Files

#### 1. Flask Application Log (Main)
**Location**: `./tmp/flask.log`  
**Size**: 14K (as of session)  
**Purpose**: Primary Flask application log
- Real-time Flask requests/responses
- Depreciation API calls
- Template rendering
- Application errors

**Monitor Command**:
```bash
tail -f ./tmp/flask.log
```

#### 2. Scraper Log
**Location**: `./logs/scraper.log`  
**Purpose**: AutoScout24 scraping activity
- Scraping progress
- Car additions/updates
- Geocoding results
- Scraping errors

**Monitor Command**:
```bash
tail -f ./logs/scraper.log
```

#### 3. Flask Output Log
**Location**: `./tmp/flask_output.log`  
**Size**: 42K  
**Purpose**: Detailed Flask output
- Debug messages
- Performance info
- Startup logs

**Monitor Command**:
```bash
tail -f ./tmp/flask_output.log
```

---

### Additional Log Files Available

#### Test/Debug Logs (in ./tmp/)
- `app.log` - 150B
- `autoscout24_debug.log` - 30K
- `autoscout24_test.log` - 15K
- `autotrack_direct_test.log` - 2.9K
- `autotrack_scrape.log` - 3.5K
- `autotrack_scrape2.log` - 13K
- `autotrack_test.log` - 3.9K
- `availability_check.log` - 6.9K
- `dashboard.log` - 5.4K
- `flask_test.log` - 972K (large)
- `full_autoscout24_run.log` - 9.0K
- `full_scraper_run.log` - 9.8K
- `full_scraper_test.log` - 72K
- `quick_autoscout24_run.log` - 8.7K
- `rescrape_progress.log` - 67K
- `scrape_output.log` - 18K
- `scraper_output.log` - 105K
- `scraper_test_*.log` - Various
- `webapp_output.log` - 43K

#### Production Logs (in ./logs/)
- `scraper.log` - Main scraper log
- `flask_app.log` - Flask application
- `flask_test.log` - Flask testing
- `web.log` - Web server logs
- `flask.log` - Flask instance log

#### Root Level
- `flask.log` - Flask root log

---

## Recommended Monitoring Commands

### Monitor Single Log
```bash
# Main Flask log
tail -f ./tmp/flask.log

# Scraper activity
tail -f ./logs/scraper.log

# Last 50 lines
tail -50 ./tmp/flask.log
```

### Monitor Multiple Logs
```bash
# Both Flask and scraper
tail -f ./tmp/flask.log ./logs/scraper.log

# Flask with labels
tail -f ./tmp/flask.log | while read line; do echo "[FLASK] $line"; done
```

### Search and Filter
```bash
# Search for errors
grep -i error ./tmp/flask.log

# Watch for depreciation API calls
tail -f ./tmp/flask.log | grep -i depreciation

# Check scraper errors
grep -i "error\|warning" ./logs/scraper.log | tail -20

# Count errors today
grep -i error ./tmp/flask.log | grep "$(date +%Y-%m-%d)" | wc -l
```

### Advanced Monitoring
```bash
# Watch multiple logs with multitail (if installed)
multitail ./tmp/flask.log ./logs/scraper.log

# Continuous error monitoring
watch -n 5 'tail -20 ./tmp/flask.log | grep -i error'

# Real-time stats
tail -f ./tmp/flask.log | grep -E "GET|POST|PUT|DELETE"
```

---

## Quick Reference Card

| What to Monitor | Command | Purpose |
|----------------|---------|---------|
| **Flask App** | `tail -f ./tmp/flask.log` | API requests, errors |
| **Scrapers** | `tail -f ./logs/scraper.log` | Scraping activity |
| **Both** | `tail -f ./tmp/flask.log ./logs/scraper.log` | Complete activity |
| **Errors Only** | `grep -i error ./tmp/flask.log` | Debug issues |
| **API Calls** | `tail -f ./tmp/flask.log \| grep depreciation` | Track specific endpoint |

---

## Current Flask Status

### Application Info
```
Process: python app/app.py
PID: 73210
Port: 5001
Working Directory: /path/to/nl-car-tracker
Log File: ./tmp/flask.log
```

### Restart Command
```bash
pkill -f "python.*app/app.py" && cd /path/to/nl-car-tracker && nohup python app/app.py > ./tmp/flask.log 2>&1 &
```

### Test Endpoints
```bash
# Health check
curl http://127.0.0.1:5001/

# Depreciation API
curl http://127.0.0.1:5001/api/calculate-depreciation

# Pretty JSON output
curl -s http://127.0.0.1:5001/api/calculate-depreciation | python -m json.tool
```

---

## Log Rotation Recommendations

Currently, logs are not rotated. Consider implementing:

```bash
# Manual cleanup (keeps last 100 lines)
tail -100 ./tmp/flask.log > ./tmp/flask.log.tmp && mv ./tmp/flask.log.tmp ./tmp/flask.log

# Archive old logs
mkdir -p ./tmp/archive
mv ./tmp/*.log ./tmp/archive/ && gzip ./tmp/archive/*.log
```

Or use `logrotate` configuration:
```
/path/to/nl-car-tracker/tmp/archive/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

---

## Troubleshooting

### No Logs Appearing
1. Check Flask is running: `ps aux | grep "python.*app.py"`
2. Check log file permissions: `ls -l ./tmp/flask.log`
3. Check disk space: `df -h`

### Logs Too Large
1. Check sizes: `du -sh ./tmp/*.log`
2. Archive old logs: `gzip ./tmp/flask_test.log`
3. Clear test logs: `rm ./tmp/*test*.log`

### Missing Log Files
1. Create tmp directory: `mkdir -p ./tmp ./logs`
2. Restart Flask to recreate logs
3. Check application configuration

---

## Session Summary

**Primary Answer**: The main log file to monitor is **`./tmp/flask.log`** ✅

This session:
1. ✅ Verified Flask application running (PID 73210)
2. ✅ Tested depreciation API endpoint (working)
3. ✅ Confirmed database state (XX-XXX-X populated)
4. ✅ Identified all available log files
5. ✅ Provided monitoring commands and best practices
6. ✅ Created this reference documentation

**Related Documentation**:
- Previous session: `./tmp/DEPRECIATION_SETUP_COMPLETE.md`
- Usage guide: `./tmp/DEPRECIATION_READY.md`
- Validation fix: `./tmp/VALIDATION_FIX.md`

---

**Document Created**: 2025-11-04 11:04  
**Created By**: Debug Agent  
**Session Type**: Support/Documentation  
**Status**: Complete ✅
