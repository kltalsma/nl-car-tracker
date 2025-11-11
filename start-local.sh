#!/bin/bash
# NL Car Tracker - Local Start Script
# Starts the web dashboard and optionally scraper as native Python processes
# Usage: ./start-local.sh [web-only]

set -e

# Parse arguments
WEB_ONLY=false
if [[ "$1" == "web-only" ]]; then
    WEB_ONLY=true
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================${NC}"
if [[ "$WEB_ONLY" == true ]]; then
    echo -e "${BLUE}  NL Car Tracker - Starting${NC}"
    echo -e "${BLUE}  (Local Web Only Mode)${NC}"
else
    echo -e "${BLUE}  NL Car Tracker - Starting${NC}"
    echo -e "${BLUE}  (Local Web + Scraper)${NC}"
fi
echo -e "${BLUE}=================================${NC}"
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
    echo "Please install Python 3.11 or higher"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}❌ Error: Python 3.10+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION detected${NC}"
echo ""

# Create necessary directories
echo -e "${BLUE}Creating necessary directories...${NC}"
mkdir -p data logs tmp cookies

# Check if processes are already running
if [ -f tmp/web.pid ] && ps -p $(cat tmp/web.pid) > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Web server is already running (PID: $(cat tmp/web.pid))${NC}"
    WEB_RUNNING=true
else
    WEB_RUNNING=false
fi

if [ -f tmp/scraper.pid ] && ps -p $(cat tmp/scraper.pid) > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Scraper is already running (PID: $(cat tmp/scraper.pid))${NC}"
    SCRAPER_RUNNING=true
else
    SCRAPER_RUNNING=false
fi

if [ "$WEB_RUNNING" = true ] && ([ "$SCRAPER_RUNNING" = true ] || [ "$WEB_ONLY" = true ]); then
    echo ""
    if [ "$WEB_ONLY" = true ]; then
        read -p "Web service is running. Restart it? (y/n) " -n 1 -r
    else
        read -p "Both services are running. Restart them? (y/n) " -n 1 -r
    fi
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ./stop-local.sh
    else
        echo -e "${GREEN}Keeping existing processes running${NC}"
        echo ""
        echo -e "${GREEN}Dashboard: ${BLUE}http://localhost:5001${NC}"
        exit 0
    fi
fi

# Check if requirements are installed
echo -e "${BLUE}Checking dependencies...${NC}"
if ! python3 -c "import flask" 2>/dev/null; then
    echo -e "${YELLOW}⚠ Dependencies not installed${NC}"
    read -p "Install dependencies now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Installing dependencies...${NC}"
        pip3 install -r requirements.txt
    else
        echo -e "${RED}❌ Cannot start without dependencies${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi
echo ""

# Initialize database if it doesn't exist
if [ ! -f data/cars.db ]; then
    echo -e "${BLUE}Initializing database...${NC}"
    python3 -c "from models.database import init_db; init_db()"
    echo -e "${GREEN}✓ Database initialized${NC}"
    echo ""
fi

# Start web server
if [ "$WEB_RUNNING" = false ]; then
    echo -e "${BLUE}Starting web dashboard...${NC}"
    # Get port from config.yaml (default to 5001 if not found)
    PORT=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['dashboard']['port'])" 2>/dev/null || echo "5001")
    
    # Set DISABLE_SCHEDULER environment variable if web-only mode
    if [ "$WEB_ONLY" = true ]; then
        export DISABLE_SCHEDULER=true
        nohup python3 app/app.py > logs/web.log 2>&1 &
        unset DISABLE_SCHEDULER
    else
        nohup python3 app/app.py > logs/web.log 2>&1 &
    fi
    
    WEB_PID=$!
    echo $WEB_PID > tmp/web.pid
    echo -e "${GREEN}✓ Web dashboard started on port $PORT (PID: $WEB_PID)${NC}"
    
    # Wait a moment to check if it started successfully
    sleep 2
    if ! ps -p $WEB_PID > /dev/null; then
        echo -e "${RED}❌ Web dashboard failed to start. Check logs/web.log${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Web dashboard already running${NC}"
fi

# Start scraper
if [ "$WEB_ONLY" = false ]; then
    if [ "$SCRAPER_RUNNING" = false ]; then
        echo -e "${BLUE}Starting scraper...${NC}"
        nohup python3 run_scraper.py > logs/scraper.log 2>&1 &
        SCRAPER_PID=$!
        echo $SCRAPER_PID > tmp/scraper.pid
        echo -e "${GREEN}✓ Scraper started (PID: $SCRAPER_PID)${NC}"
        
        # Wait a moment to check if it started successfully
        sleep 2
        if ! ps -p $SCRAPER_PID > /dev/null; then
            echo -e "${RED}❌ Scraper failed to start. Check logs/scraper.log${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}✓ Scraper already running${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Skipping scraper (web-only mode)${NC}"
fi

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}  ✓ Started Successfully!${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo -e "📊 Dashboard: ${BLUE}http://localhost:5001${NC}"
echo ""

if [[ "$WEB_ONLY" == true ]]; then
    echo -e "${YELLOW}Note: Scraper is NOT running (web-only mode).${NC}"
    echo -e "${YELLOW}You can trigger scraping from the admin page.${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo -e "  View web logs:    ${BLUE}tail -f logs/web.log${NC}"
    echo -e "  Start scraper:    ${BLUE}nohup python3 run_scraper.py > logs/scraper.log 2>&1 & echo \$! > tmp/scraper.pid${NC}"
    echo -e "  View scraper logs: ${BLUE}tail -f logs/scraper.log${NC}"
    echo -e "  Stop services:    ${BLUE}./stop-local.sh${NC}"
    echo -e "  Check status:     ${BLUE}ps aux | grep python${NC}"
else
    echo -e "${GREEN}✓ The scraper will begin collecting data in the background.${NC}"
    echo -e "${GREEN}  Check the dashboard in a few minutes to see results.${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo -e "  View web logs:    ${BLUE}tail -f logs/web.log${NC}"
    echo -e "  View scraper logs: ${BLUE}tail -f logs/scraper.log${NC}"
    echo -e "  Stop services:    ${BLUE}./stop-local.sh${NC}"
    echo -e "  Check status:     ${BLUE}ps aux | grep python${NC}"
fi
echo ""
