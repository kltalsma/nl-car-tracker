#!/bin/bash
# NL Car Tracker - Start Web Dashboard Only (Local Mode)
# Starts only the web dashboard without the scraper

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================${NC}"
echo -e "${BLUE}  NL Car Tracker - Web Only${NC}"
echo -e "${BLUE}  (Local/Native Mode)${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python detected${NC}"
echo ""

# Create necessary directories
mkdir -p data logs tmp cookies

# Check if web server is already running
if [ -f tmp/web.pid ] && ps -p $(cat tmp/web.pid) > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Web server is already running (PID: $(cat tmp/web.pid))${NC}"
    echo -e "${GREEN}Dashboard: ${BLUE}http://localhost:5000${NC}"
    exit 0
fi

# Check dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Dependencies not installed${NC}"
    read -p "Install dependencies now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip3 install -r requirements.txt
    else
        echo -e "${RED}❌ Cannot start without dependencies${NC}"
        exit 1
    fi
fi

# Initialize database if it doesn't exist
if [ ! -f data/cars.db ]; then
    echo -e "${BLUE}Initializing database...${NC}"
    python3 -c "from models.database import init_db; init_db()"
    echo -e "${GREEN}✓ Database initialized${NC}"
fi

# Start web server only
echo -e "${BLUE}Starting web dashboard...${NC}"
nohup python3 app/app.py > logs/web.log 2>&1 &
WEB_PID=$!
echo $WEB_PID > tmp/web.pid

# Wait to check if it started successfully
sleep 2
if ! ps -p $WEB_PID > /dev/null; then
    echo -e "${RED}❌ Web dashboard failed to start. Check logs/web.log${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Web dashboard started (PID: $WEB_PID)${NC}"
echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}  ✓ Web Dashboard Started!${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo -e "📊 Dashboard: ${BLUE}http://localhost:5000${NC}"
echo ""
echo -e "${YELLOW}Note: Scraper is NOT running${NC}"
echo -e "  The dashboard will show existing data only."
echo -e "  No new cars will be added until you start the scraper."
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo -e "  View logs:         ${BLUE}tail -f logs/web.log${NC}"
echo -e "  Start scraper:     ${BLUE}nohup python3 run_scraper.py > logs/scraper.log 2>&1 & echo \$! > tmp/scraper.pid${NC}"
echo -e "  Stop web:          ${BLUE}kill \$(cat tmp/web.pid) && rm tmp/web.pid${NC}"
echo ""
