#!/bin/bash
# NL Car Tracker - Start Web Dashboard Only (Docker Mode)
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
echo -e "${BLUE}=================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Error: Docker daemon is not running${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker is running${NC}"
echo ""

# Create necessary directories
mkdir -p data logs tmp cookies

# Check if web container is already running
if docker compose ps web | grep -q "Up"; then
    echo -e "${YELLOW}⚠ Web dashboard is already running${NC}"
    echo -e "${GREEN}Dashboard: ${BLUE}http://localhost:5000${NC}"
    exit 0
fi

# Start only the web service
echo -e "${BLUE}Starting web dashboard (without scraper)...${NC}"
docker compose up -d web

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
echo -e "  View web logs:     ${BLUE}docker compose logs -f web${NC}"
echo -e "  Start scraper too: ${BLUE}docker compose up -d scraper${NC}"
echo -e "  Stop web:          ${BLUE}docker compose stop web${NC}"
echo ""
