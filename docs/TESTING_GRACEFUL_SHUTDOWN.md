# Testing Graceful Shutdown - Quick Guide

This guide provides step-by-step instructions to test the graceful shutdown implementation.

## Prerequisites

Before testing, ensure:
- [ ] No scraper or web processes are currently running
- [ ] You have terminal access to the project directory
- [ ] You can run `./start-local.sh` and `./stop-local.sh`

## Test Suite

### Test 1: Basic Graceful Shutdown (Idle State)

**Purpose**: Verify clean shutdown when processes are idle

```bash
# 1. Start the services
./start-local.sh

# 2. Wait 5-10 seconds for startup to complete

# 3. In another terminal, stop the services
./stop-local.sh

# 4. Expected output:
#    - "Stopping web dashboard (PID: XXXX)..."
#    - "Shutdown completed gracefully in X seconds"
#    - "Stopping scraper (PID: XXXX)..."
#    - "Shutdown completed gracefully in X seconds"
#    - "✓ web dashboard stopped"
#    - "✓ scraper stopped"
#    - No "Forcing shutdown..." messages
```

**Verification**:
```bash
# Check no Python processes remain
ps aux | grep -E "(python.*run_scraper|python.*app/app\.py)" | grep -v grep
# Expected: No output

# Check no ChromeDriver processes
ps aux | grep chromedriver | grep -v grep
# Expected: No output

# Check no Chrome webdriver processes
ps aux | grep "Chrome.*webdriver" | grep -v grep
# Expected: No output

# Check PID files removed
ls -la tmp/*.pid 2>/dev/null
# Expected: No such file or directory
```

**Result**: ☐ PASS  ☐ FAIL

---

### Test 2: Mid-Scrape Shutdown

**Purpose**: Verify shutdown completes current scraping operation gracefully

```bash
# 1. Start the services
./start-local.sh

# 2. Wait until scraper starts actively scraping (check logs)
tail -f logs/scraper.log
# Wait for messages like: "Starting scrape for AutoScout24"
# Wait for: "Processing URL: ..."

# 3. While scraper is active, stop the services
# In another terminal:
./stop-local.sh

# 4. Expected behavior:
#    - Current scraping operation completes
#    - May take 5-15 seconds
#    - "Received signal 15. Initiating graceful shutdown..." in logs
#    - "Shutdown requested, stopping scraper loop" in logs
#    - "Cleaning up resources..." in logs
#    - "Cleanup complete. Exiting." in logs
#    - No forced shutdown after 30 seconds
```

**Check Logs**:
```bash
# Check scraper log for clean shutdown
tail -20 logs/scraper.log

# Look for:
# - "Received signal 15. Initiating graceful shutdown..."
# - "Shutdown requested, stopping scraper loop"
# - "Cleaning up resources..."
# - "Cleanup complete. Exiting."

# Should NOT see:
# - Traceback or error messages
# - "Forcing shutdown..."
```

**Verification**:
```bash
# Same process verification as Test 1
ps aux | grep -E "(python|chrome)" | grep -v grep
ls -la tmp/*.pid 2>/dev/null
```

**Result**: ☐ PASS  ☐ FAIL

---

### Test 3: Database Integrity After Shutdown

**Purpose**: Ensure database is not corrupted by shutdown

```bash
# 1. Run Test 1 or Test 2 to perform a shutdown

# 2. Check database integrity
sqlite3 data/cars.db "PRAGMA integrity_check;"
# Expected output: ok

# 3. Check WAL (Write-Ahead Log) checkpoint
sqlite3 data/cars.db "PRAGMA wal_checkpoint(FULL);"
# Expected output: 0|0|0 (no pending WAL frames)

# 4. Query database to ensure it's accessible
sqlite3 data/cars.db "SELECT COUNT(*) FROM cars;"
# Expected: A number (not an error)

# 5. Restart services
./start-local.sh

# 6. Check logs for any database errors
tail -20 logs/scraper.log
tail -20 logs/flask.log

# Should NOT see:
# - "database is locked"
# - "database disk image is malformed"
# - "unable to open database file"
```

**Result**: ☐ PASS  ☐ FAIL

---

### Test 4: Ctrl+C Shutdown (SIGINT)

**Purpose**: Verify manual interrupt is handled gracefully

```bash
# 1. Start scraper in foreground (for testing Ctrl+C)
python run_scraper.py

# 2. Wait for scraper to start actively scraping

# 3. Press Ctrl+C in the terminal

# 4. Expected output:
#    - "Received signal 2. Initiating graceful shutdown..."
#    - "Shutdown requested, stopping scraper loop"
#    - "Cleaning up resources..."
#    - "Cleanup complete. Exiting."
#    - Process exits cleanly
```

**Verification**:
```bash
# Check process exited cleanly
echo $?
# Expected: 0 (clean exit)

# Check no orphaned processes
ps aux | grep -E "(python.*run_scraper|chromedriver|Chrome.*webdriver)" | grep -v grep
# Expected: No output
```

**Result**: ☐ PASS  ☐ FAIL

---

### Test 5: Docker Mode Shutdown

**Purpose**: Verify graceful shutdown works in Docker containers

**Note**: Skip this test if you're only using local mode

```bash
# 1. Start in Docker mode
./start.sh

# 2. Wait for containers to start
docker compose ps
# Both containers should show "Up"

# 3. Stop containers
./stop.sh
# Choose option 2 (stop and remove)

# 4. Expected output:
#    - "Allowing up to 30 seconds for graceful shutdown..."
#    - Containers stop within 30 seconds
#    - No force-kill messages from Docker

# 5. Check container logs for clean shutdown
docker compose logs scraper | tail -20
docker compose logs web | tail -20

# Look for same shutdown messages as Test 2
```

**Verification**:
```bash
# Check no containers running
docker compose ps
# Expected: Empty or "No containers"

# Check database integrity (same as Test 3)
sqlite3 data/cars.db "PRAGMA integrity_check;"
# Expected: ok
```

**Result**: ☐ PASS  ☐ FAIL

---

### Test 6: Forced Shutdown Fallback

**Purpose**: Verify force-kill works after 30-second timeout

**Note**: This test intentionally creates a hang scenario

```bash
# This test requires modifying the code temporarily to create a hang
# Skip this test unless you want to verify the force-kill mechanism

# 1. Temporarily modify run_scraper.py to hang on shutdown:
#    In signal_handler(), add: time.sleep(40)

# 2. Start services
./start-local.sh

# 3. Stop services
./stop-local.sh

# 4. Expected behavior:
#    - Script waits for 30 seconds
#    - Shows progress messages: "Still waiting... (5s elapsed)"
#    - After 30 seconds: "Graceful shutdown timeout - forcing shutdown..."
#    - Process is killed with SIGKILL
#    - "✓ scraper stopped"

# 5. Revert the code change before proceeding!
```

**Result**: ☐ PASS  ☐ FAIL (or ☐ SKIPPED)

---

## Common Issues and Solutions

### Issue: "Graceful shutdown timeout - forcing shutdown..."

**Cause**: Process took >30 seconds to shut down

**Solutions**:
1. Check logs for hanging operations
2. Verify no infinite loops in scraper code
3. Consider increasing timeout if operations legitimately take longer
4. Check for network timeouts or slow database operations

---

### Issue: Orphaned Chrome/ChromeDriver Processes

**Cause**: WebDriver cleanup failed

**Manual Cleanup**:
```bash
# Kill orphaned ChromeDriver
pkill -9 -f "chromedriver.*--port"

# Kill orphaned Chrome
pkill -9 -f "Chrome.*webdriver"

# Verify cleanup
ps aux | grep -E "(chromedriver|Chrome.*webdriver)" | grep -v grep
```

**Prevention**:
- Ensure signal handlers are working
- Check cleanup_resources() is called
- Verify no exceptions preventing cleanup

---

### Issue: Database Lock Errors After Restart

**Cause**: Database connection not properly closed

**Manual Fix**:
```bash
# Remove SQLite temporary files
rm -f data/cars.db-shm data/cars.db-wal

# Check integrity
sqlite3 data/cars.db "PRAGMA integrity_check;"

# Restart services
./start-local.sh
```

---

### Issue: PID Files Remain After Shutdown

**Cause**: Script interrupted before cleanup

**Manual Fix**:
```bash
# Remove stale PID files
rm -f tmp/web.pid tmp/scraper.pid

# Verify no processes actually running
ps aux | grep -E "(python.*run_scraper|python.*app/app\.py)" | grep -v grep

# If processes found, kill them manually
./stop-local.sh
```

---

## Test Results Summary

After completing all tests, fill in your results:

| Test | Status | Notes |
|------|--------|-------|
| Test 1: Basic Shutdown | ☐ PASS ☐ FAIL | |
| Test 2: Mid-Scrape | ☐ PASS ☐ FAIL | |
| Test 3: Database Integrity | ☐ PASS ☐ FAIL | |
| Test 4: Ctrl+C | ☐ PASS ☐ FAIL | |
| Test 5: Docker Mode | ☐ PASS ☐ FAIL ☐ SKIP | |
| Test 6: Force-Kill Fallback | ☐ PASS ☐ FAIL ☐ SKIP | |

**Overall Assessment**: ☐ All Critical Tests Pass  ☐ Issues Found

---

## Next Steps After Testing

If all tests pass:
- ✅ Graceful shutdown is working correctly
- ✅ Safe to use in production
- ✅ Can rely on clean shutdowns for maintenance

If tests fail:
1. Review logs in `logs/scraper.log` and `logs/flask.log`
2. Check for error messages or tracebacks
3. Refer to troubleshooting section in `GRACEFUL_SHUTDOWN.md`
4. Re-run failed tests after fixes

---

## Monitoring in Production

After deployment, monitor:

1. **Shutdown Time Distribution**
   ```bash
   # Check typical shutdown times from logs
   grep "Shutdown completed gracefully" logs/scraper.log
   ```

2. **Force-Kill Frequency**
   ```bash
   # Check if force-kills are happening
   grep "Forcing shutdown" logs/scraper.log
   ```

3. **Database Health**
   ```bash
   # Weekly integrity checks
   sqlite3 data/cars.db "PRAGMA integrity_check;"
   ```

4. **Orphaned Process Detection**
   ```bash
   # Run after each shutdown
   ps aux | grep -E "(chromedriver|Chrome.*webdriver)" | grep -v grep
   ```

---

## Automated Testing Script

For convenience, you can create an automated test runner:

```bash
#!/bin/bash
# save as: test_shutdown.sh

echo "Running graceful shutdown tests..."
echo ""

# Test 1: Basic shutdown
echo "Test 1: Basic Shutdown"
./start-local.sh > /dev/null 2>&1 &
sleep 10
./stop-local.sh | grep -q "Shutdown completed gracefully" && echo "✓ PASS" || echo "✗ FAIL"
echo ""

# Test 2: Database integrity
echo "Test 2: Database Integrity"
sqlite3 data/cars.db "PRAGMA integrity_check;" | grep -q "ok" && echo "✓ PASS" || echo "✗ FAIL"
echo ""

# Test 3: Process cleanup
echo "Test 3: Process Cleanup"
ORPHANS=$(ps aux | grep -E "(python.*run_scraper|chromedriver|Chrome.*webdriver)" | grep -v grep | wc -l)
[ "$ORPHANS" -eq "0" ] && echo "✓ PASS" || echo "✗ FAIL ($ORPHANS orphaned processes)"
echo ""

echo "Testing complete!"
```

Save this script and run it periodically to ensure shutdown continues working correctly.
