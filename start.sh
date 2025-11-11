#!/bin/bash
# NL Car Tracker - Docker Start Script
# Starts the web dashboard and optionally scraper services using Docker Compose
# Usage: ./start.sh [web-only]

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
    echo -e "${BLUE}  (Web Only Mode)${NC}"
else
    echo -e "${BLUE}  NL Car Tracker - Starting${NC}"
    echo -e "${BLUE}  (Web + Scraper)${NC}"
fi
echo -e "${BLUE}=================================${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    echo "Please install Docker from https://www.docker.com/get-started"
    exit 1
fi

# Check if Docker Compose is available
if ! docker-compose version &> /dev/null; then
    echo -e "${RED}❌ Error: Docker Compose is not available${NC}"
    echo "Please install Docker Compose"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Error: Docker daemon is not running${NC}"
    echo "Please start Docker Desktop or the Docker daemon"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed and running${NC}"
echo ""

# Create necessary directories
echo -e "${BLUE}Creating necessary directories...${NC}"
mkdir -p data logs tmp cookies

# Check if containers are already running
if docker-compose ps | grep -q "Up"; then
    echo -e "${YELLOW}⚠ Containers are already running${NC}"
    echo ""
    read -p "Do you want to restart them? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Stopping and restarting containers...${NC}"
        docker-compose down
        if [[ "$WEB_ONLY" == true ]]; then
            echo -e "${BLUE}Starting web container only...${NC}"
            export DISABLE_SCHEDULER=true
            docker-compose up -d web
        else
            echo -e "${BLUE}Starting all containers...${NC}"
            export DISABLE_SCHEDULER=false
            docker-compose up -d
        fi
    else
        echo -e "${GREEN}Keeping existing containers running${NC}"
        echo ""
        echo -e "${GREEN}=================================${NC}"
        echo -e "${GREEN}  Services Status${NC}"
        echo -e "${GREEN}=================================${NC}"
        docker-compose ps
        echo ""
        echo -e "${GREEN}Dashboard: ${BLUE}http://localhost:5001${NC}"
        exit 0
    fi
# Check if containers exist but are stopped
elif docker-compose ps -a | grep -q "nl-car-tracker"; then
    echo -e "${YELLOW}⚠ Containers exist but are stopped${NC}"
    echo ""
    echo -e "${BLUE}Recreating and starting containers with current settings...${NC}"
    docker-compose down
    if [[ "$WEB_ONLY" == true ]]; then
        export DISABLE_SCHEDULER=true
        docker-compose up -d web
    else
        export DISABLE_SCHEDULER=false
        docker-compose up -d
    fi
else
    # Build and start containers
    if [[ "$WEB_ONLY" == true ]]; then
        echo -e "${BLUE}Building and starting web container only...${NC}"
        export DISABLE_SCHEDULER=true
        docker-compose up -d --build web
    else
        echo -e "${BLUE}Building and starting all containers...${NC}"
        export DISABLE_SCHEDULER=false
        docker-compose up -d --build
    fi
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
    echo -e "  View logs:        ${BLUE}docker-compose logs -f${NC}"
    echo -e "  View web logs:    ${BLUE}docker-compose logs -f web${NC}"
    echo -e "  Start scraper:    ${BLUE}docker-compose up -d scraper${NC}"
    echo -e "  View scraper logs: ${BLUE}docker-compose logs -f scraper${NC}"
    echo -e "  Stop services:    ${BLUE}./stop.sh${NC}"
    echo -e "  Check status:     ${BLUE}docker-compose ps${NC}"
else
    echo -e "${GREEN}✓ Scraper is running in the background.${NC}"
    echo -e "${GREEN}  Check the dashboard in a few minutes to see results.${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo -e "  View logs:        ${BLUE}docker-compose logs -f${NC}"
    echo -e "  View web logs:    ${BLUE}docker-compose logs -f web${NC}"
    echo -e "  View scraper logs: ${BLUE}docker-compose logs -f scraper${NC}"
    echo -e "  Stop services:    ${BLUE}./stop.sh${NC}"
    echo -e "  Check status:     ${BLUE}docker-compose ps${NC}"
fi
echo ""

# Show container status
docker-compose ps
echo ""
