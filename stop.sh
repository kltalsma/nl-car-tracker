#!/bin/bash
# NL Car Tracker - Docker Stop Script
# Stops the web dashboard and scraper services

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=================================${NC}"
echo -e "${BLUE}  NL Car Tracker - Stopping...${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    exit 1
fi

# Check if containers are running
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠ No containers are currently running${NC}"
    exit 0
fi

# Ask if user wants to remove containers or just stop them
echo -e "${YELLOW}How do you want to stop the services?${NC}"
echo "  1) Stop containers (keeps containers, can restart quickly)"
echo "  2) Stop and remove containers (clean shutdown, frees resources)"
echo ""
read -p "Choose option (1 or 2): " -n 1 -r
echo ""

if [[ $REPLY == "2" ]]; then
    echo -e "${BLUE}Stopping and removing containers...${NC}"
    echo -e "${BLUE}  Allowing up to 30 seconds for graceful shutdown...${NC}"
    docker-compose down -t 30
    echo ""
    echo -e "${GREEN}✓ Containers stopped and removed${NC}"
    echo -e "${GREEN}  Data has been preserved in ./data and ./logs${NC}"
else
    echo -e "${BLUE}Stopping containers...${NC}"
    echo -e "${BLUE}  Allowing up to 30 seconds for graceful shutdown...${NC}"
    docker-compose stop -t 30
    echo ""
    echo -e "${GREEN}✓ Containers stopped${NC}"
    echo -e "${YELLOW}  To start again: ${BLUE}./start.sh${NC}"
    echo -e "${YELLOW}  To remove containers: ${BLUE}docker-compose down${NC}"
fi

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}  Stopped Successfully!${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
