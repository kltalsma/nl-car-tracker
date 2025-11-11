#!/bin/bash
# NL Car Tracker - Local Stop Script
# Stops the web dashboard and scraper processes

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================${NC}"
echo -e "${BLUE}  NL Car Tracker - Stopping...${NC}"
echo -e "${BLUE}  (Local/Native Mode)${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

STOPPED_ANY=false

# Function to kill a process gracefully
kill_process() {
    local PID=$1
    local NAME=$2
    
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${BLUE}Stopping $NAME (PID: $PID)...${NC}"
        echo -e "${BLUE}  Sending shutdown signal (SIGTERM)...${NC}"
        kill $PID 2>/dev/null || true
        
        # Wait for process to stop gracefully (30 seconds)
        # This allows time for:
        # - Current scraping operations to complete
        # - Database transactions to commit
        # - WebDriver cleanup
        echo -e "${BLUE}  Waiting for graceful shutdown (up to 30 seconds)...${NC}"
        for i in {1..60}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                echo -e "${GREEN}  Shutdown completed gracefully in $((i/2)) seconds${NC}"
                break
            fi
            sleep 0.5
            # Show progress indicator every 5 seconds
            if [ $((i % 10)) -eq 0 ]; then
                echo -e "${YELLOW}    Still waiting... ($((i/2))s elapsed)${NC}"
            fi
        done
        
        # Force kill if still running after 30 seconds
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}  Graceful shutdown timeout - forcing shutdown...${NC}"
            kill -9 $PID 2>/dev/null || true
            sleep 1
        fi
        
        echo -e "${GREEN}✓ $NAME stopped${NC}"
        return 0
    fi
    return 1
}

# Stop web server by PID file
if [ -f tmp/web.pid ]; then
    WEB_PID=$(cat tmp/web.pid)
    if kill_process $WEB_PID "web dashboard"; then
        STOPPED_ANY=true
    else
        echo -e "${YELLOW}⚠ Web dashboard process not running (PID $WEB_PID not found)${NC}"
    fi
    rm -f tmp/web.pid
else
    echo -e "${YELLOW}⚠ No web dashboard PID file found${NC}"
fi

# Stop scraper by PID file
if [ -f tmp/scraper.pid ]; then
    SCRAPER_PID=$(cat tmp/scraper.pid)
    if kill_process $SCRAPER_PID "scraper"; then
        STOPPED_ANY=true
    else
        echo -e "${YELLOW}⚠ Scraper process not running (PID $SCRAPER_PID not found)${NC}"
    fi
    rm -f tmp/scraper.pid
else
    echo -e "${YELLOW}⚠ No scraper PID file found${NC}"
fi

echo ""

if [ "$STOPPED_ANY" = true ]; then
    echo -e "${GREEN}=================================${NC}"
    echo -e "${GREEN}  Stopped Successfully!${NC}"
    echo -e "${GREEN}=================================${NC}"
    echo ""
    echo -e "${GREEN}  Data has been preserved in ./data and ./logs${NC}"
    echo -e "${YELLOW}  To start again: ${BLUE}./start-local.sh${NC}"
else
    echo -e "${YELLOW}=================================${NC}"
    echo -e "${YELLOW}  No Processes Were Running${NC}"
    echo -e "${YELLOW}=================================${NC}"
fi

echo ""

# Clean up any orphaned processes
echo -e "${YELLOW}Checking for orphaned processes...${NC}"

# Check for orphaned Flask/web processes (multiple patterns)
ORPHANED_WEB_COUNT=0
if pgrep -f "python.*app/app\.py" > /dev/null 2>&1; then
    ORPHANED_WEB_COUNT=$(pgrep -f "python.*app/app\.py" | wc -l | tr -d ' ')
    pkill -9 -f "python.*app/app\.py" 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up $ORPHANED_WEB_COUNT orphaned Flask/web processes${NC}"
    STOPPED_ANY=true
fi

# Check for orphaned scraper processes (multiple patterns)
ORPHANED_SCRAPER_COUNT=0
for pattern in "python.*run_scraper\.py" "python.*scraper/run_scraper\.py"; do
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        COUNT=$(pgrep -f "$pattern" | wc -l | tr -d ' ')
        ORPHANED_SCRAPER_COUNT=$((ORPHANED_SCRAPER_COUNT + COUNT))
        pkill -9 -f "$pattern" 2>/dev/null || true
    fi
done
if [ $ORPHANED_SCRAPER_COUNT -gt 0 ]; then
    echo -e "${GREEN}✓ Cleaned up $ORPHANED_SCRAPER_COUNT orphaned scraper processes${NC}"
    STOPPED_ANY=true
fi

# Clean up ChromeDriver processes
echo -e "${YELLOW}Checking for ChromeDriver processes...${NC}"
CHROMEDRIVER_COUNT=0
if pgrep -f "chromedriver.*--port" > /dev/null 2>&1; then
    CHROMEDRIVER_COUNT=$(pgrep -f "chromedriver.*--port" | wc -l | tr -d ' ')
    pkill -9 -f "chromedriver.*--port" 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up $CHROMEDRIVER_COUNT ChromeDriver processes${NC}"
    STOPPED_ANY=true
fi

# Clean up Chrome/Chromium processes from scrapers (headless selenium instances)
echo -e "${YELLOW}Checking for scraper Chrome processes...${NC}"
CHROME_COUNT=0
# More specific pattern to match only selenium-controlled Chrome instances
if pgrep -f "Chrome.*--test-type=webdriver" > /dev/null 2>&1; then
    CHROME_COUNT=$(pgrep -f "Chrome.*--test-type=webdriver" | wc -l | tr -d ' ')
    pkill -9 -f "Chrome.*--test-type=webdriver" 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up $CHROME_COUNT Chrome scraper processes${NC}"
    STOPPED_ANY=true
fi

# Also clean up any helper processes (GPU, Renderer, etc.)
HELPER_COUNT=0
if pgrep -f "Chrome Helper.*--test-type=webdriver" > /dev/null 2>&1; then
    HELPER_COUNT=$(pgrep -f "Chrome Helper.*--test-type=webdriver" | wc -l | tr -d ' ')
    pkill -9 -f "Chrome Helper.*--test-type=webdriver" 2>/dev/null || true
    if [ $HELPER_COUNT -gt 0 ]; then
        echo -e "${GREEN}✓ Cleaned up $HELPER_COUNT Chrome Helper processes${NC}"
        STOPPED_ANY=true
    fi
fi

# Clean up any tail processes monitoring logs
if pgrep -f "tail.*flask\.log" > /dev/null 2>&1; then
    pkill -9 -f "tail.*flask\.log" 2>/dev/null || true
    echo -e "${GREEN}✓ Cleaned up log monitoring processes${NC}"
    STOPPED_ANY=true
fi

echo ""
