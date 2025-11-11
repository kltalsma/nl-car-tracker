# NL Car Tracker

A comprehensive car tracking system for finding used Electric Vehicles (EVs) and Plug-in Hybrid Electric Vehicles (PHEVs) in the Netherlands. Automatically scrapes multiple car listing websites and presents results in a beautiful web dashboard.

## Features

- **Continuous Background Scraping**: Automatically scrapes car listings from multiple Dutch websites every 30-60 minutes
- **Web Dashboard**: Modern, responsive interface for browsing and filtering cars
- **Advanced Filtering**: Filter by vehicle type, fuel type, price, distance, and features
- **Price Tracking**: Monitors price changes over time for each listing
- **Top Matches**: Highlights cars with all 32 required features
- **Analytics**: View trends, statistics, and scraping activity
- **Trade-In Value Tracking**: Track your current car's market value over time with manual entry from multiple sources
- **Docker Support**: Easy deployment with Docker and persistent data volumes

## Search Criteria

### Vehicle Types
- **SUV** (max €35,000)
- **Stationwagon** (max €30,000)

### Fuel Types
- **Full Electric**: Minimum 550km range
- **PHEV** (Plug-in Hybrid): Minimum 100km electric-only range

### Additional Filters
- Maximum mileage: 60,000 km
- Minimum year: 2022
- Location: Within 50km of Heerenveen

### Required Features (All 32 Must Be Present)
1. 4x4
2. Adaptive Cruise Control
3. Android Auto
4. Apple CarPlay
5. Achteruitrijcamera (Rear view camera)
6. Airconditioning
7. Bluetooth
8. Climate Control
9. Cruise Control
10. Elektrisch verstelbare stoelen (Electric adjustable seats)
11. Head-up display
12. Keyless entry
13. Lederen bekleding (Leather upholstery)
14. LED koplampen (LED headlights)
15. Lichtmetalen velgen (Alloy wheels)
16. Navigatiesysteem (Navigation system)
17. Panoramadak (Panoramic roof)
18. Parkeersensoren achter (Rear parking sensors)
19. Parkeersensoren voor (Front parking sensors)
20. Stoelverwarming (Heated seats)
21. Stuurverwarming (Heated steering wheel)
22. Trekhaak (Towbar)
23. Getint glas (Tinted glass)
24. Alarm
25. Centrale vergrendeling (Central locking)
26. Elektrische ramen (Electric windows)
27. Boordcomputer (Trip computer)
28. Regensensor (Rain sensor)
29. Lichtsensor (Light sensor)
30. Lane assist
31. Blind spot monitoring
32. Wireless charging

## Scraped Websites

- autoscout24.nl
- autotrack.nl
- gaspedaal.nl

## Installation

## Quick Start Scripts

The easiest way to start and stop the application is using the provided scripts:

### Docker Mode (Recommended)

Start the application:
```bash
./start.sh
```

Stop the application:
```bash
./stop.sh
```

The `start.sh` script will:
- Check if Docker is installed and running
- Create necessary directories
- Build and start both web dashboard and scraper containers
- Display the dashboard URL and useful commands

The `stop.sh` script gives you the option to:
1. Stop containers (keeps them for quick restart)
2. Stop and remove containers (clean shutdown)

### Local/Native Mode

Start the application:
```bash
./start-local.sh
```

Stop the application:
```bash
./stop-local.sh
```

The `start-local.sh` script will:
- Check Python version (3.10+ required)
- Create necessary directories
- Install dependencies if needed (with confirmation)
- Initialize the database if not present
- Start both web server and scraper in background
- Store process IDs in `tmp/` directory

The `stop-local.sh` script will:
- Gracefully stop both processes
- Clean up PID files
- Preserve all data

### Viewing Logs

**Docker mode:**
```bash
# All logs
docker compose logs -f

# Web dashboard only
docker compose logs -f web

# Scraper only
docker compose logs -f scraper
```

**Local mode:**
```bash
# Web dashboard
tail -f logs/web.log

# Scraper
tail -f logs/scraper.log
```


### Using Docker (Recommended)

1. **Clone or create the project directory**
   ```bash
   cd nl-car-tracker
   ```

2. **Build and start the containers**
   ```bash
   docker-compose up -d
   ```

3. **Access the dashboard**
   Open your browser and navigate to: `http://localhost:5000`

The scraper will automatically start running in the background, scraping every 30-60 minutes.

### Manual Installation

1. **Install Python 3.11+**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Chrome/Chromium**
   The scraper requires Chrome or Chromium to be installed.

4. **Initialize the database**
   ```bash
   python -c "from models.database import init_db; init_db()"
   ```

5. **Run the scraper (in one terminal)**
   ```bash
   python run_scraper.py
   ```

6. **Run the dashboard (in another terminal)**
   ```bash
   python app/app.py
   ```

7. **Access the dashboard**
   Open your browser: `http://localhost:5000`

## Project Structure

```
nl-car-tracker/
├── app/
│   ├── app.py              # Flask web application
│   └── templates/          # HTML templates
│       ├── base.html
│       ├── index.html
│       ├── car_detail.html
│       ├── top_matches.html
│       └── analytics.html
├── scrapers/
│   ├── base_scraper.py     # Base scraper class
│   ├── autoscout24_scraper.py
│   ├── autotrack_scraper.py
│   └── gaspedaal_scraper.py
├── models/
│   └── database.py         # SQLAlchemy models
├── utils/
│   └── helpers.py          # Utility functions
├── data/
│   └── cars.db             # SQLite database (created automatically)
├── logs/
│   ├── scraper.log         # Application logs
│   └── screenshots/        # Error screenshots
├── config.yaml             # Configuration file
├── requirements.txt        # Python dependencies
├── Dockerfile
├── docker-compose.yml
├── run_scraper.py          # Continuous scraper runner
└── README.md
```

## Configuration

Edit `config.yaml` to customize:

- Search criteria (price limits, mileage, year, etc.)
- Required features list
- Scraping intervals and rate limits
- Dashboard settings
- Logging levels

## Dashboard Pages

### Home
- Browse all car listings
- Filter by vehicle type, fuel type, price, distance
- Sort by price, distance, features, or newest
- View basic car information and images

### Top Matches
- Shows only cars with all 32 required features
- Sorted by distance from Heerenveen
- Quick access to perfect matches

### Car Details
- Complete vehicle specifications
- Price history tracking
- Feature checklist (present vs. missing)
- Dealer information
- Direct link to original listing

### Analytics
- Price distribution charts
- Cars by source website
- Scraping activity logs
- Statistics and trends

## API Endpoints

The dashboard also provides JSON API endpoints:

- `GET /api/cars` - Get all car listings (with optional filters)
- `GET /api/stats` - Get statistics

Example:
```bash
curl "http://localhost:5000/api/cars?fuel_type=Full%20Electric&only_complete=true"
```

## Data Persistence

When using Docker, all data is persisted in volumes:

- **Database**: `./data/cars.db` - Contains all car listings and price history
- **Logs**: `./logs/` - Application logs and screenshots

Data survives container restarts and can be backed up by copying these directories.

## Managing the Application

### View logs
```bash
# Scraper logs
docker-compose logs -f scraper

# Dashboard logs
docker-compose logs -f web
```

### Stop the application
```bash
docker-compose down
```

### Restart services
```bash
docker-compose restart
```

### Rebuild after code changes
```bash
docker-compose down
docker-compose build
docker-compose up -d
```

## Development

### Testing Individual Scrapers

```bash
# Test AutoScout24 scraper
python scrapers/autoscout24_scraper.py

# Test Autotrack scraper
python scrapers/autotrack_scraper.py

# Test Gaspedaal scraper
python scrapers/gaspedaal_scraper.py
```

### Adjusting Scrapers

The AutoScout24 scraper is fully implemented as a template. The CSS selectors and URL parameters need to be verified against the actual website structure and may need adjustment.

Autotrack and Gaspedaal scrapers are placeholder templates that need to be implemented based on their specific website structures.

## Important Notes

### Web Scraping Considerations

1. **CSS Selectors**: Website structures change frequently. The CSS selectors in the scrapers may need to be updated periodically.

2. **Rate Limiting**: The application includes built-in rate limiting (30-60 min between cycles, 2 sec between requests) to be respectful to the source websites.

3. **Legal**: Ensure compliance with the terms of service of the scraped websites. This tool is for personal use only.

4. **Robots.txt**: The scrapers should respect robots.txt files. Consider adding robots.txt checking.

### First Run

On the first run:
- The database will be empty
- The scraper needs time to populate data (allow 1-2 cycles)
- Some features (like price history) need multiple scraping cycles to populate

### Performance

- The scraper runs continuously in the background
- Each full scraping cycle takes approximately 5-15 minutes depending on the number of listings
- The dashboard is responsive and can be accessed while scraping is in progress

## Troubleshooting

### Scraper not finding cars

1. Check the CSS selectors in the scraper files - they may need updating
2. Review logs in `logs/scraper.log`
3. Check screenshots in `logs/screenshots/` for visual debugging
4. Verify the search URL parameters are correct for each website

### Database errors

```bash
# Reset database (WARNING: deletes all data)
rm data/cars.db
python -c "from models.database import init_db; init_db()"
```

### Chrome/Selenium issues

Make sure Chrome/Chromium is properly installed:
```bash
# In Docker container
docker-compose exec scraper which chromium

# Or install manually
apt-get update && apt-get install -y chromium chromium-driver
```

## Trade-In Value Tracking

Track your current car's market value over time to help with trade-in decisions. Since most Dutch valuation services (AutoScout24, ANWB) require email submission or payment, this tool supports manual value entry from any source.

### Valuation Sources

You can get valuations from:
- **AutoScout24.nl** - [Waardebepaling](https://www.autoscout24.nl/waardebepaling/) (requires email)
- **ANWB Koerslijst** - Available to ANWB members
- **Spoticar** - Online valuation tool
- **Local Dealers** - Get trade-in quotes
- **AI Assistants** - Claude.ai, ChatGPT (provide car details and current market data)

### Usage

The trade-in tracker uses a CLI interface for managing valuations:

```bash
# Run from project root with PYTHONPATH set
export PYTHONPATH=/Users/kltalsma/Prive/nl-car-tracker

# Add a valuation
python utils/trade_in_checker.py add \
  --value 10500 \
  --source "AutoScout24" \
  --notes "Online estimate with 151k km"

# Add with specific mileage
python utils/trade_in_checker.py add \
  --value 11000 \
  --source "Local Dealer" \
  --mileage 155000 \
  --type asking_price

# View value history
python utils/trade_in_checker.py history

# Show latest valuation
python utils/trade_in_checker.py latest
```

### Value Types

The tracker supports three value types:

- **`market_value`** (default) - Fair market value for private sale
- **`asking_price`** - Price you could ask when selling privately
- **selling_price`** - Actual trade-in/dealer offer price

### Configuration

Your current car details are stored in `config.yaml`:

```yaml
current_car:
  license_plate: "SX-515-N"
  mileage_km: 151000
```

The tracker uses the RDW (Dutch vehicle registration) API to automatically fetch:
- Make and model
- Year of registration
- Fuel type
- Body type
- Color

### Database

Trade-in values are stored in the same SQLite database (`data/cars.db`) with:
- Historical value tracking
- Mileage at time of valuation
- Source of valuation
- Date/time stamps
- Optional notes

### Tips for Accurate Valuations

1. **Update regularly** - Check values monthly or quarterly to track depreciation
2. **Use multiple sources** - Compare values from different sources
3. **Be specific** - Include current mileage and any damage/condition notes
4. **Track trends** - Use the history to see how your car's value changes over time
5. **Consider context** - Trade-in values are typically 10-20% lower than private sale values

## Future Enhancements

Potential improvements:
- Email notifications for new perfect matches
- Integration of trade-in values into dashboard
- Value trend visualization and depreciation charts
- Automated reminders to check trade-in values
- Mobile app
- More sophisticated price prediction
- Additional car listing websites
- Export functionality (CSV, PDF)
- Saved searches
- Comparison feature
- Map view with geographic clustering

## License

This project is for personal use only. Ensure compliance with the terms of service of all scraped websites.

## Support

For issues or questions, check:
1. Application logs in `logs/scraper.log`
2. Error screenshots in `logs/screenshots/`
3. Database contents using any SQLite browser

---

Built with Python, Flask, Selenium, and SQLAlchemy.
