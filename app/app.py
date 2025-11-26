"""
Flask web dashboard for NL Car Tracker
Displays scraped car listings and analytics
"""
import sys
import os
# Add parent directory to path to import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, render_template, request, jsonify
from models.database import Database, Car, PriceHistory, ScraperLog
from sqlalchemy import desc, func, or_, case
from datetime import datetime, timedelta
from utils.helpers import match_required_features, should_exclude_vehicle, get_boot_space, get_ev_database_range, get_wltp_range, extract_battery_size, calculate_towing_range, find_duplicate_cars
from apscheduler.schedulers.background import BackgroundScheduler
import yaml
import os
import logging
import atexit
import threading
import signal

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# Load configuration
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml')
with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Initialize database
db = Database(config['database']['path'])

# Get latest trade-in value for net cost calculation
def get_latest_trade_in_value():
    """Get the latest trade-in value from the database"""
    try:
        from models.database import CurrentCar, TradeInValue
        session = db.get_session()
        
        # Get the current car from config
        license_plate = config.get('current_car', {}).get('license_plate')
        if not license_plate:
            session.close()
            return None
        
        # Find the car
        car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        if not car:
            session.close()
            return None
        
        # Get latest trade-in value
        latest_value = session.query(TradeInValue)\
            .filter_by(car_id=car.id)\
            .order_by(TradeInValue.checked_at.desc())\
            .first()
        
        session.close()
        
        if latest_value:
            # Prefer selling_price (trade-in), then market_value, then asking_price
            return latest_value.selling_price or latest_value.market_value or latest_value.asking_price
        
        return None
    except Exception as e:
        logger.error(f"Error getting trade-in value: {e}")
        return None

def initialize_current_car_from_config():
    """Initialize current car in database from config if not exists"""
    try:
        from models.database import CurrentCar
        
        # Get current car config
        current_car_config = config.get('current_car', {})
        license_plate = current_car_config.get('license_plate')
        
        if not license_plate:
            return  # No current car configured
        
        session = db.get_session()
        
        # Check if current car already exists
        existing_car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        
        if not existing_car:
            # Parse purchase_date from config if provided
            purchase_date = None
            if current_car_config.get('purchase_date'):
                from datetime import datetime, date
                try:
                    pd = current_car_config.get('purchase_date')
                    # Handle both string and date/datetime objects from YAML
                    if isinstance(pd, str):
                        purchase_date = datetime.strptime(pd, '%Y-%m-%d')
                    elif isinstance(pd, date):
                        purchase_date = datetime.combine(pd, datetime.min.time())
                    else:
                        purchase_date = pd
                except (ValueError, AttributeError) as e:
                    logger.error(f"Invalid purchase_date format in config: {current_car_config.get('purchase_date')} - {e}")
            
            # Create new current car record
            current_car = CurrentCar(
                license_plate=license_plate,
                make=current_car_config.get('make', '').upper(),
                model=current_car_config.get('model', ''),
                year=current_car_config.get('year'),
                mileage_km=current_car_config.get('mileage_km'),
                initial_purchase_price=current_car_config.get('initial_purchase_price'),
                purchase_date=purchase_date,
                average_km_per_year=current_car_config.get('average_km_per_year'),
                purchase_mileage_km=current_car_config.get('purchase_mileage_km'),
                estimated_new_price=current_car_config.get('estimated_new_price')
            )
            session.add(current_car)
            session.commit()
            logger.info(f"Initialized current car from config: {license_plate}")
        else:
            # Update existing record with config values if changed
            updated = False
            if current_car_config.get('make') and existing_car.make != current_car_config.get('make', '').upper():
                existing_car.make = current_car_config.get('make', '').upper()
                updated = True
            if current_car_config.get('model') and existing_car.model != current_car_config.get('model'):
                existing_car.model = current_car_config.get('model')
                updated = True
            if current_car_config.get('year') and existing_car.year != current_car_config.get('year'):
                existing_car.year = current_car_config.get('year')
                updated = True
            if current_car_config.get('mileage_km') and existing_car.mileage_km != current_car_config.get('mileage_km'):
                existing_car.mileage_km = current_car_config.get('mileage_km')
                updated = True
            if current_car_config.get('initial_purchase_price') and existing_car.initial_purchase_price != current_car_config.get('initial_purchase_price'):
                existing_car.initial_purchase_price = current_car_config.get('initial_purchase_price')
                updated = True
            
            # Update purchase_date if provided
            if current_car_config.get('purchase_date'):
                from datetime import datetime, date
                try:
                    pd = current_car_config.get('purchase_date')
                    # Handle both string and date/datetime objects from YAML
                    if isinstance(pd, str):
                        purchase_date = datetime.strptime(pd, '%Y-%m-%d')
                    elif isinstance(pd, date):
                        purchase_date = datetime.combine(pd, datetime.min.time())
                    else:
                        purchase_date = pd
                    
                    if existing_car.purchase_date != purchase_date:
                        existing_car.purchase_date = purchase_date
                        updated = True
                except (ValueError, AttributeError) as e:
                    logger.error(f"Invalid purchase_date format in config: {current_car_config.get('purchase_date')} - {e}")
            
            # Update average_km_per_year if provided
            if current_car_config.get('average_km_per_year') and existing_car.average_km_per_year != current_car_config.get('average_km_per_year'):
                existing_car.average_km_per_year = current_car_config.get('average_km_per_year')
                updated = True
            
            
            # Update purchase_mileage_km if provided
            if current_car_config.get("purchase_mileage_km") and existing_car.purchase_mileage_km != current_car_config.get("purchase_mileage_km"):
                existing_car.purchase_mileage_km = current_car_config.get("purchase_mileage_km")
                updated = True
            
            # Update estimated_new_price if provided
            if current_car_config.get("estimated_new_price") and existing_car.estimated_new_price != current_car_config.get("estimated_new_price"):
                existing_car.estimated_new_price = current_car_config.get("estimated_new_price")
                updated = True
            if updated:
                session.commit()
                logger.info(f"Updated current car from config: {license_plate}")
        
        session.close()
    except Exception as e:
        logger.error(f"Error initializing current car: {e}")

# Set up logging for scheduler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize current car from config on app start
initialize_current_car_from_config()

# Cache the trade-in value (updated on app start)
TRADE_IN_VALUE = get_latest_trade_in_value()

# Set up logging for scheduler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clean_excluded_vehicles_from_db():
    """
    Remove all vehicles from the database that match the exclusion list
    This runs automatically when the exclusion list is updated
    """
    session = None
    try:
        session = db.Session()
        
        # Get all cars
        all_cars = session.query(Car).all()
        
        # Find excluded cars
        excluded_cars = []
        for car in all_cars:
            make = str(car.make or '')
            model = str(car.model or '')
            
            if should_exclude_vehicle(make, model):
                excluded_cars.append(car.id)
        
        if not excluded_cars:
            logger.info("No excluded vehicles found in database")
            session.close()
            return 0
        
        logger.info(f"Found {len(excluded_cars)} excluded vehicles to remove")
        
        # Remove excluded cars
        deleted_count = 0
        for car_id in excluded_cars:
            car = session.query(Car).filter(Car.id == car_id).first()
            if car:
                session.delete(car)
                deleted_count += 1
        
        # Commit changes
        session.commit()
        logger.info(f"Successfully removed {deleted_count} excluded vehicles from database")
        
        session.close()
        return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning excluded vehicles: {e}")
        if session:
            session.rollback()
            session.close()
        return 0


def run_scrapers():
    """Background task to run all scrapers"""
    logger.info("Starting scheduled scraper run...")
    
    try:
        # Import scrapers here to avoid circular imports
        from scrapers.autoscout24_scraper import AutoScout24Scraper
        from scrapers.autotrack_scraper import AutotrackScraper
        from scrapers.gaspedaal_scraper import GaspedaalScraper
        
        scrapers = [
            AutoScout24Scraper(),
            AutotrackScraper(),
            GaspedaalScraper()
        ]
        
        for scraper in scrapers:
            try:
                logger.info(f"Running {scraper.__class__.__name__}...")
                scraper.run()
                logger.info(f"{scraper.__class__.__name__} completed successfully")
            except Exception as e:
                logger.error(f"Error running {scraper.__class__.__name__}: {e}")
                
    except Exception as e:
        logger.error(f"Error in scheduled scraper run: {e}")
    
    logger.info("Scheduled scraper run completed")


def check_car_availability():
    """
    Check availability of cars that haven't been seen recently
    Uses availability_checker config settings
    Returns stats about the check (cars_checked, cars_marked_unavailable)
    """
    from models.database import Database, ScraperLog
    from datetime import datetime
    
    # Get availability checker config
    av_config = config.get('availability_checker', {})
    if not av_config.get('enabled', True):
        logger.info("Availability checker is disabled in config")
        return {'cars_checked': 0, 'cars_marked_unavailable': 0}
    
    logger.info("Starting availability check for stale cars...")
    
    # Create scraper log entry
    db = Database(config['database']['path'])
    session = db.get_session()
    
    log_entry = ScraperLog(
        website='availability_checker',
        started_at=datetime.utcnow(),
        status='in_progress',
        cars_found=0,
        cars_new=0,
        cars_updated=0
    )
    session.add(log_entry)
    session.commit()
    log_id = log_entry.id
    
    try:
        from check_availability import AvailabilityChecker
        
        # Get config settings
        days_threshold = av_config.get('check_stale_cars_days', 3)
        scrape_alternatives = av_config.get('scrape_alternatives', False)
        max_cars = av_config.get('max_cars_per_run', 100)
        
        # Check cars not seen in the specified days
        checker = AvailabilityChecker(
            db_path=config['database']['path'],
            config_path=config_path,
            headless=True,
            scrape_alternatives=scrape_alternatives
        )
        
        # Run availability check with filters
        filters = {
            'older_than_days': days_threshold,
            'limit': max_cars
        }
        
        result = checker.check_and_update_availability(filters)
        
        # Handle case where result is None (no cars to check)
        if result is None:
            result = {'cars_checked': 0, 'cars_marked_unavailable': 0}
        
        # Update log entry with results
        log_entry = session.query(ScraperLog).get(log_id)
        if log_entry:
            log_entry.completed_at = datetime.utcnow()
            log_entry.status = 'success'
            log_entry.cars_found = result.get('cars_checked', 0)
            log_entry.cars_updated = result.get('cars_marked_unavailable', 0)
            session.commit()
        
        logger.info(f"Availability check complete: {result.get('cars_checked', 0)} checked, {result.get('cars_marked_unavailable', 0)} marked unavailable")
        
        session.close()
        return result
        
    except Exception as e:
        logger.error(f"Error in availability check: {e}", exc_info=True)
        
        # Update log entry with error
        log_entry = session.query(ScraperLog).get(log_id)
        if log_entry:
            log_entry.completed_at = datetime.utcnow()
            log_entry.status = 'error'
            log_entry.error_message = str(e)
            session.commit()
        session.close()
        
        return {'cars_checked': 0, 'cars_marked_unavailable': 0, 'error': str(e)}


def recheck_unavailable_cars():
    """
    Recheck unavailable cars to see if they're available again
    Uses availability_checker.recheck_unavailable config settings
    Returns stats about the recheck (cars_checked, cars_remarked_available)
    """
    from models.database import Database, ScraperLog
    from datetime import datetime
    
    # Get availability checker config
    av_config = config.get('availability_checker', {})
    recheck_config = av_config.get('recheck_unavailable', {})
    
    if not recheck_config.get('enabled', False):
        logger.info("Unavailable car rechecking is disabled in config")
        return {'cars_checked': 0, 'cars_remarked_available': 0}
    
    logger.info("Starting recheck of unavailable cars...")
    
    # Create scraper log entry
    db = Database(config['database']['path'])
    session = db.get_session()
    
    log_entry = ScraperLog(
        website='availability_recheck',
        started_at=datetime.utcnow(),
        status='in_progress',
        cars_found=0,
        cars_new=0,
        cars_updated=0
    )
    session.add(log_entry)
    session.commit()
    log_id = log_entry.id
    
    try:
        from check_availability import AvailabilityChecker
        
        # Get config settings
        max_cars = recheck_config.get('max_cars_per_run', 50)
        only_verified = recheck_config.get('only_recheck_verified', True)
        
        # Create availability checker
        checker = AvailabilityChecker(
            db_path=config['database']['path'],
            config_path=config_path,
            headless=True,
            scrape_alternatives=False  # Don't scrape alternatives when rechecking
        )
        
        # Run recheck with filters
        filters = {
            'limit': max_cars,
            'only_verified': only_verified
        }
        
        result = checker.check_unavailable_cars(filters)
        
        # Handle case where result is None
        if result is None:
            result = {'cars_checked': 0, 'cars_remarked_available': 0, 'still_unavailable': 0, 'errors': 0}
        
        # Update log entry with results
        log_entry = session.query(ScraperLog).get(log_id)
        if log_entry:
            log_entry.completed_at = datetime.utcnow()
            log_entry.status = 'success'
            log_entry.cars_found = result.get('cars_checked', 0)
            log_entry.cars_updated = result.get('cars_remarked_available', 0)
            session.commit()
        
        logger.info(f"Unavailable car recheck complete: {result.get('cars_checked', 0)} checked, {result.get('cars_remarked_available', 0)} remarked available")
        
        session.close()
        return result
        
    except Exception as e:
        logger.error(f"Error in unavailable car recheck: {e}", exc_info=True)
        
        # Update log entry with error
        log_entry = session.query(ScraperLog).get(log_id)
        if log_entry:
            log_entry.completed_at = datetime.utcnow()
            log_entry.status = 'error'
            log_entry.error_message = str(e)
            session.commit()
        session.close()
        
        return {'cars_checked': 0, 'cars_remarked_available': 0, 'error': str(e)}


# Initialize background scheduler
scheduler = BackgroundScheduler()

# Get scheduler config
scheduler_config = config.get('scraping', {}).get('scheduler', {})
# Allow environment variable to override scheduler config
scheduler_enabled = os.getenv('DISABLE_SCHEDULER', '').lower() != 'true' and scheduler_config.get('enabled', True)
interval_minutes = scheduler_config.get('interval_minutes', 5)

if scheduler_enabled:
    scheduler.add_job(
        func=run_scrapers,
        trigger="interval",
        minutes=interval_minutes,
        id='scraper_job',
        name='Run all scrapers',
        replace_existing=True
    )
    
    # Add availability check job - runs every 6 hours
    av_config = config.get('availability_checker', {})
    av_check_hours = av_config.get('check_interval_hours', 6)
    
    scheduler.add_job(
        func=check_car_availability,
        trigger="interval",
        hours=av_check_hours,
        id='availability_check_job',
        name='Check car availability',
        replace_existing=True
    )
    
    # Add unavailable car recheck job - runs weekly (if enabled)
    recheck_config = av_config.get('recheck_unavailable', {})
    if recheck_config.get('enabled', False):
        recheck_hours = recheck_config.get('check_interval_hours', 168)  # Default 7 days
        scheduler.add_job(
            func=recheck_unavailable_cars,
            trigger="interval",
            hours=recheck_hours,
            id='unavailable_recheck_job',
            name='Recheck unavailable cars',
            replace_existing=True
        )
        logger.info(f"Unavailable car recheck will run every {recheck_hours} hours ({recheck_hours/24:.1f} days)")
    
    # Start the scheduler
    scheduler.start()
    logger.info(f"Background scheduler started - scrapers will run every {interval_minutes} minutes")
    logger.info(f"Availability checks will run every {av_check_hours} hours for cars not seen in {av_config.get('check_stale_cars_days', 3)} days")
    
    # Run scrapers on startup if enabled
    if scheduler_config.get('run_on_startup', False):
        logger.info("Running scrapers on startup...")
        threading.Thread(target=run_scrapers, daemon=True).start()
    
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())
    
    # Register signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully"""
        signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.info(f"Received {signal_name} signal - initiating graceful shutdown...")
        
        # Shutdown scheduler
        if scheduler.running:
            logger.info("Shutting down scheduler...")
            scheduler.shutdown(wait=True)
            logger.info("Scheduler shutdown complete")
        
        # Close database connections
        logger.info("Closing database connections...")
        db.close()
        
        logger.info("Graceful shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("Signal handlers registered for graceful shutdown")
else:
    logger.info("Background scheduler is disabled in config.yaml")


def calculate_car_score(car, config, distance_weight=0.1, return_breakdown=False):
    """
    Calculate a numeric score for a car based on multiple factors.
    Lower score = better car.
    
    Scoring breakdown (penalties - higher numbers are worse):
    - Critical Features: 45% (missing features increase score)
    - Price: 20% (lower is better)
    - Odometer: 15% (lower is better)
    - Distance: 10% (closer is better - LOCAL DEALER PREFERENCE!)
    - Age: 5% (newer is better)
    - Range: 5% (higher is better)
    
    CONTENDER BONUSES:
    - Full Electric SUV with 500+ km range: -10 points (major bonus!)
    - PHEV/Hybrid with 100+ km electric range: -5 points (good bonus!)
    - Has trekhaak: -5 points (nice bonus, can install aftermarket)
    
    Args:
        car: Car object to score
        config: Configuration dictionary
        distance_weight: Weight for distance scoring (default 0.1 = 10%, can be increased for stronger local preference)
        return_breakdown: If True, returns tuple of (score, breakdown_dict)
    """
    score = 0
    breakdown = {
        'critical_features': {'raw': 0, 'weighted': 0, 'details': {}},
        'price': {'raw': 0, 'weighted': 0},
        'mileage': {'raw': 0, 'weighted': 0},
        'age': {'raw': 0, 'weighted': 0},
        'distance': {'raw': 0, 'weighted': 0},
        'range': {'raw': 0, 'weighted': 0},
        'bonuses': []
    }
    
    # CRITICAL FEATURES (45% weight - important but not disqualifying)
    critical_features = check_critical_features(car, config)
    total_critical = len(critical_features)
    
    if total_critical > 0:
        # Base features score - simple ratio of missing features
        missing_critical = sum(1 for has_it in critical_features.values() if not has_it)
        features_score = (missing_critical / total_critical) * 100
        weighted_features = features_score * 0.45
        score += weighted_features
        breakdown['critical_features']['raw'] = features_score
        breakdown['critical_features']['weighted'] = weighted_features
        breakdown['critical_features']['details'] = critical_features.copy()
    else:
        weighted_features = 50 * 0.45
        score += weighted_features  # Moderate penalty for no features data
        breakdown['critical_features']['raw'] = 50
        breakdown['critical_features']['weighted'] = weighted_features
    
    # Check for trekhaak for bonus later
    has_trekhaak = critical_features.get('Trekhaak', False) if critical_features else False
    
    # Check nice-to-have features for trekhaak
    if not has_trekhaak:
        nice_to_have = config.get('nice_to_have_features', [])
        if isinstance(car.features, str):
            car_features_str = car.features.lower()
        elif isinstance(car.features, list):
            car_features_str = ' '.join(car.features).lower()
        else:
            car_features_str = ""
        
        # Check if trekhaak is in nice_to_have and car has it
        if any('trekhaak' in str(f).lower() for f in nice_to_have):
            if any(keyword in car_features_str for keyword in ['trekhaak', 'tow hitch', 'towbar', 'tow bar', 'towing']):
                has_trekhaak = True
    
    # Price score (normalize to 0-100 scale, max price = 50000)
    if car.price:
        max_price = 50000
        price_score = min((car.price / max_price) * 100, 100)
        weighted_price = price_score * 0.2
        score += weighted_price
        breakdown['price']['raw'] = price_score
        breakdown['price']['weighted'] = weighted_price
    else:
        weighted_price = 100 * 0.2
        score += weighted_price  # Penalty for missing price
        breakdown['price']['raw'] = 100
        breakdown['price']['weighted'] = weighted_price
    
    # Odometer score (normalize to 0-100 scale, max mileage = 150000)
    if car.mileage_km:
        max_odometer = 150000
        odometer_score = min((car.mileage_km / max_odometer) * 100, 100)
        weighted_mileage = odometer_score * 0.15
        score += weighted_mileage
        breakdown['mileage']['raw'] = odometer_score
        breakdown['mileage']['weighted'] = weighted_mileage
    else:
        weighted_mileage = 100 * 0.15
        score += weighted_mileage  # Penalty for missing odometer
        breakdown['mileage']['raw'] = 100
        breakdown['mileage']['weighted'] = weighted_mileage
    
    # Age score (normalize to 0-100 scale, reference year = 2025, max age = 10 years)
    if car.year:
        current_year = 2025
        age = current_year - car.year
        max_age = 10
        age_score = min((age / max_age) * 100, 100)
        weighted_age = age_score * 0.05
        score += weighted_age
        breakdown['age']['raw'] = age_score
        breakdown['age']['weighted'] = weighted_age
    else:
        weighted_age = 100 * 0.05
        score += weighted_age  # Penalty for missing year
        breakdown['age']['raw'] = 100
        breakdown['age']['weighted'] = weighted_age
    
    # Distance score (normalize to 0-100 scale - LOCAL DEALER PREFERENCE!)
    # Favor cars from nearby dealers for easier maintenance access
    # distance_weight parameter allows customization (default 0.1 = 10%)
    if car.distance_from_heerenveen_km is not None:
        distance = car.distance_from_heerenveen_km
        # Distance bands with graduated scoring:
        # 0-30 km: Excellent (0-30 points)
        # 30-50 km: Good (30-50 points)
        # 50-75 km: Acceptable (50-75 points)
        # 75-100 km: Far (75-100 points)
        # 100+ km: Very far (100+ points)
        distance_score = min(distance, 100)  # Cap at 100 for scoring purposes
        weighted_distance = distance_score * distance_weight
        score += weighted_distance
        breakdown['distance']['raw'] = distance_score
        breakdown['distance']['weighted'] = weighted_distance
    else:
        weighted_distance = 75 * distance_weight
        score += weighted_distance  # Moderate penalty for missing distance (assume mid-range)
        breakdown['distance']['raw'] = 75
        breakdown['distance']['weighted'] = weighted_distance
    
    # Range score (normalize to 0-100 scale, higher is better, max range = 600km)
    # Use ad_listed_range_km (scraped from listings) with fallback to legacy field
    # Note: We don't use WLTP or EV-DB here as they're not always available in the Car object at scoring time
    range_km = car.ad_listed_range_km or car.electric_range_km
    if not range_km and car.model:
        # Known range estimates for popular models (WLTP)
        range_estimates = {
            # Skoda
            'Enyaq iV 80': 540,
            'Enyaq iV 60': 390,
            'Enyaq Coupe': 545,
            # Tesla
            'Model Y Long Range': 533,
            'Model Y': 455,
            'Model 3 Long Range': 629,
            'Model 3': 491,
            'Model X': 528,
            # Volkswagen
            'ID.4 Pro': 520,
            'ID.4 GTX': 480,
            'ID.4': 520,
            'Id 4': 520,
            'ID.5 Pro': 520,
            'ID.5 GTX': 490,
            'ID.5': 520,
            'Id 3': 420,
            'ID.3': 420,
            'e-Golf': 231,
            # Mercedes
            'EQA 250': 426,
            'EQA 300': 537,
            'EQA': 426,
            'EQB 250': 423,
            'EQB 300': 512,
            'EQB': 423,
            'EQC 400': 437,
            # Hyundai
            'Ioniq 5 Long Range': 481,
            'Ioniq 5': 384,
            'Ioniq 6 Long Range': 614,
            'Ioniq 6': 429,
            # Audi
            'e-tron 55': 441,
            'e-tron 50': 341,
            'E Tron': 436,
            'e-tron': 436,
            'Q4 e-tron 45': 520,
            'Q4 e-tron 40': 436,
            'Q4 e-tron': 520,
            'Q8 e-tron': 491,
            # BMW
            'iX xDrive50': 630,
            'iX xDrive40': 425,
            'iX3': 461,
            'i4 eDrive40': 590,
            'i4 M50': 521,
            # Volvo
            'XC40 Recharge': 418,
            'C40 Recharge': 440,
            'EX30 Extended Range': 480,
            'EX30': 344,
            # Ford
            'Mustang Mach-E Extended RWD 98': 600,
            'Mustang Mach-E': 440,
            # Kia
            'e-Niro EV ExecutiveLine 64.8': 460,
            'e-Niro 64': 455,
            'E Niro': 455,
            'e-Niro': 455,
            'E Soul': 452,
            'Soul e-Soul': 452,
            'EV6 Long Range': 528,
            'EV6': 394,
            # Renault
            'Megane E-Tech': 470,
            'Scenic E-Tech': 625,
            # Hyundai/others
            'Kona Electric': 484,
            # Nissan
            'Ariya': 520,
            # Mazda
            'MX-30': 200,
            # MINI
            'Business Edition 33': 203,
            # Peugeot
            'e-2008 EV GT 50': 340,
            'e-2008': 340,
            'e-208 EV 50': 362,
            'e-208': 362,
            # Toyota
            'bZ4X': 516,
            # Jaguar
            'I Pace': 470,
            'I-Pace': 470,
            # CUPRA
            'Tavascan 82': 550,
        }
        
        model_str = str(car.model)
        for model_key, estimated_range in range_estimates.items():
            if model_key in model_str:
                range_km = estimated_range
                break
    
    if range_km:
        max_range = 600
        # Invert the score so higher range = lower score
        range_score = max(0, 100 - min((range_km / max_range) * 100, 100))
        score += range_score * 0.05
        breakdown['range']['raw'] = range_score
        breakdown['range']['weighted'] = range_score * 0.05
        breakdown['range']['value'] = range_km
    else:
        score += 30 * 0.05  # Small penalty for missing range (assume decent 400km)
        breakdown['range']['raw'] = 30
        breakdown['range']['weighted'] = 30 * 0.05
        breakdown['range']['value'] = None
    
    # ===== CONTENDER BONUSES =====
    # These bonuses can significantly boost a car's ranking
    vehicle_type_str = str(car.vehicle_type).upper() if car.vehicle_type else ''
    is_suv = 'SUV' in vehicle_type_str
    is_stationwagon = 'STATIONWAGON' in vehicle_type_str or 'STATION' in vehicle_type_str
    is_full_electric = car.fuel_type == 'Full Electric'
    is_phev_or_hybrid = car.fuel_type in ['PHEV', 'Hybrid']
    
    # BONUS 1: Full Electric SUV with 500+ km range is a STRONG contender
    if is_full_electric and is_suv and range_km and range_km >= 500:
        score -= 10  # Major bonus! (lower score = better)
        breakdown['bonuses'].append({'name': 'Full Electric SUV 500+ km', 'value': -10})
    
    # BONUS 2: PHEV/Hybrid with 100+ km electric range is a good contender
    if is_phev_or_hybrid and range_km and range_km >= 100:
        score -= 5  # Good bonus!
        breakdown['bonuses'].append({'name': 'PHEV/Hybrid 100+ km', 'value': -5})
    
    # BONUS 3: SUV or Station Wagon body style (family-friendly)
    if is_suv or is_stationwagon:
        score -= 5  # Prefer larger family-friendly vehicles
        breakdown['bonuses'].append({'name': 'SUV/Station Wagon', 'value': -5})
    
    # BONUS 4: Preferred cars (based on config - Skoda Enyaq, Audi Q4, etc.)
    preferred_config = config.get('preferred_cars', {})
    if preferred_config:
        preferred_makes = [m.lower() for m in preferred_config.get('makes', [])]
        preferred_models = [m.lower() for m in preferred_config.get('models', [])]
        auto_prefer_wagons_min_range = preferred_config.get('auto_prefer_wagons_min_range', 100)
        
        car_make_lower = str(car.make).lower() if car.make else ''
        car_model_lower = str(car.model).lower() if car.model else ''
        
        # Check if this car is a preferred make/model
        is_preferred_make = any(pm in car_make_lower for pm in preferred_makes)
        is_preferred_model = any(pm in car_model_lower for pm in preferred_models)
        
        if is_preferred_make or is_preferred_model:
            score -= 15  # Major bonus for preferred cars!
            breakdown['bonuses'].append({'name': 'Preferred Car', 'value': -15})
        
        # Auto-prefer station wagons with 100+ km range
        if is_stationwagon and range_km and range_km >= auto_prefer_wagons_min_range:
            score -= 10  # Good bonus for practical wagons
            breakdown['bonuses'].append({'name': f'Station Wagon {auto_prefer_wagons_min_range}+ km', 'value': -10})
    
    # Nice-to-have bonus: Trekhaak
    if has_trekhaak:
        score -= 5  # Small bonus for having towbar
        breakdown['bonuses'].append({'name': 'Trekhaak', 'value': -5})
    
    if return_breakdown:
        return (score, breakdown)
    return score


def convert_score_to_value_rating(raw_score):
    """
    Convert raw score (lower = better) to a 0-100 Value Rating (higher = better)
    
    Raw score range explanation:
    - Best possible: ~-50 (all bonuses, no penalties)
    - Worst possible: ~100 (all penalties, no bonuses)
    - Typical range: -30 to +80
    
    Value Rating:
    - 90-100: Exceptional value (best deals)
    - 80-89: Excellent value
    - 70-79: Very good value
    - 60-69: Good value
    - 50-59: Fair value
    - 0-49: Poor value
    """
    # Define the expected range of raw scores
    # These are realistic bounds based on the scoring algorithm
    WORST_SCORE = 100   # Maximum penalties (missing all features, high price, high miles, old, low range)
    BEST_SCORE = -50    # Maximum bonuses (preferred model, SUV, great range, has features)
    
    # Clamp the score to our expected range
    clamped_score = max(BEST_SCORE, min(WORST_SCORE, raw_score))
    
    # Invert and normalize to 0-100 scale
    # Formula: ((WORST - score) / (WORST - BEST)) * 100
    value_rating = ((WORST_SCORE - clamped_score) / (WORST_SCORE - BEST_SCORE)) * 100
    
    # Round to 1 decimal place for cleaner display
    return round(value_rating, 1)


def check_critical_features(car, config):
    """
    Check if car has critical features (trekhaak, hill hold, etc.)
    Returns dict with feature name -> True/False
    """
    critical_features = config.get('critical_features', [])
    
    # car.features can be either a string or a list
    if isinstance(car.features, str):
        car_features_str = car.features.lower()
    elif isinstance(car.features, list):
        car_features_str = ' '.join(car.features).lower()
    else:
        car_features_str = ""
    
    # Feature keyword mappings for flexible matching
    feature_keywords = {
        'adaptive cruise control': ['adaptive cruise control', 'adaptieve cruise control', 'acc', 'adaptive cruise'],
        'android auto': ['android auto', 'apple carplay', 'carplay'],  # CarPlay usually comes with Android Auto
        'navigatiesysteem': ['navigatie', 'navigatiesysteem', 'navigation', 'navi', 'gps'],
        'stuurbekrachtiging': ['stuurbekrachtiging', 'power steering', 'servo', 'besturing'],  # Assume all modern cars have power steering
        'dab+ radio': ['dab+', 'dab radio', 'digital radio', 'dab', 'digitale radio', 'digitale radio-ontvangst'],
        'elektrisch bedienbare ramen': ['elektrisch bedienbare ramen', 'electric windows', 'elektrische ramen', 'power windows'],
        'achteruitrijcamera': ['achteruitrijcamera', 'rear camera', 'camera', 'reversing camera', 'parkeerhulp met camera'],
        'climate control': ['climate control', 'climatronic', 'airco', 'climate', 'airconditioning'],
        'hill hold': ['hill hold', 'hill-hold', 'hill start', 'heuvelstart', 'bergstart', 'hill-hold control'],
        'lane assist': ['lane assist', 'lane keeping', 'lka', 'lane departure', 'lane keeping assist'],
        'park assist': ['park assist', 'parkeerhulp', 'parking assist', 'parking sensors', 'parkeersensoren', 'parkeerassistent'],
        'trekhaak': ['trekhaak', 'tow hitch', 'towbar', 'tow bar', 'towing']
    }
    
    results = {}
    for feature in critical_features:
        feature_lower = feature.lower()
        
        # Check if we have keyword mappings for this feature
        if feature_lower in feature_keywords:
            # Check if ANY of the keywords match
            has_feature = any(keyword in car_features_str for keyword in feature_keywords[feature_lower])
        else:
            # Fall back to direct matching
            has_feature = feature_lower in car_features_str
        
        results[feature] = has_feature
    
    return results


@app.route('/')
def index():
    """Home page with car listings"""
    session = db.get_session()
    
    # Get filter parameters
    page = request.args.get('page', 1, type=int)
    per_page = config['dashboard']['items_per_page']
    
    vehicle_type = request.args.get('vehicle_type', '')
    fuel_type = request.args.get('fuel_type', '')
    make = request.args.get('make', '')
    model = request.args.get('model', '')
    min_year = request.args.get('min_year', type=int)
    max_year = request.args.get('max_year', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_mileage = request.args.get('min_mileage', type=int)
    max_mileage = request.args.get('max_mileage', type=int)
    max_distance = request.args.get('max_distance', type=float)
    min_storage = request.args.get('min_storage', type=int)
    only_complete = request.args.get('only_complete', type=bool, default=False)
    required_features = request.args.getlist('required_features')  # Get list of required features from checkboxes
    sort_by = request.args.get('sort_by', 'last_seen')
    
    # Build query
    query = session.query(Car).filter(Car.is_available == True)
    
    # Apply filters
    if vehicle_type:
        query = query.filter(Car.vehicle_type == vehicle_type)
    if fuel_type:
        query = query.filter(Car.fuel_type == fuel_type)
    if make:
        query = query.filter(Car.make == make)
    if model:
        query = query.filter(Car.model == model)
    if min_year:
        query = query.filter(Car.year >= min_year)
    if max_year:
        query = query.filter(Car.year <= max_year)
    if min_price:
        query = query.filter(Car.price >= min_price)
    if max_price:
        query = query.filter(Car.price <= max_price)
    if min_mileage:
        query = query.filter(Car.mileage_km >= min_mileage)
    if max_mileage:
        query = query.filter(Car.mileage_km <= max_mileage)
    if max_distance:
        query = query.filter(Car.distance_from_heerenveen_km <= max_distance)
    if min_storage:
        query = query.filter(Car.storage_capacity_liters >= min_storage)
    if only_complete:
        query = query.filter(Car.has_all_required_features == True)
    
    # Apply odometer/mileage filter from config
    max_mileage = config['search']['max_mileage_km']
    query = query.filter(Car.mileage_km <= max_mileage)
    
    # Apply sorting
    if sort_by == 'price_asc':
        query = query.order_by(Car.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Car.price.desc())
    elif sort_by == 'distance':
        query = query.order_by(Car.distance_from_heerenveen_km.asc())
    elif sort_by == 'features':
        query = query.order_by(Car.features_count.desc())
    else:  # last_seen
        query = query.order_by(Car.last_seen.desc())
    
    # Get all matching cars, then filter out excluded vehicles
    all_cars = query.all()
    filtered_cars = [
        car for car in all_cars 
        if not should_exclude_vehicle(str(car.make or ''), str(car.model or ''))
        and (car.doors is None or car.doors >= 4)  # Require 4+ doors (or unknown)
        and (car.seats is None or car.seats >= 5)  # Require 5+ seats (or unknown)
    ]
    
    # Filter by required features if specified
    if required_features:
        def car_has_required_features(car):
            """Check if car has all user-selected required features"""
            car_features = car.features if car.features else []
            # Normalize for case-insensitive matching
            car_features_lower = [f.lower() for f in car_features]
            for required_feature in required_features:
                if required_feature.lower() not in car_features_lower:
                    return False
            return True
        
        filtered_cars = [car for car in filtered_cars if car_has_required_features(car)]
    
    # Paginate filtered results
    total_cars = len(filtered_cars)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    cars = filtered_cars[start_idx:end_idx]
    
    # Calculate scores for each car
    for car in cars:
        # Load boot space if missing
        if not car.storage_capacity_liters:
            boot_data = get_boot_space(str(car.make), str(car.model))
            if boot_data:
                car.storage_capacity_liters = boot_data.get('normal', 0)
        
        # Load EV-Database range data
        fuel_type_str = str(car.fuel_type) if car.fuel_type is not None else None
        car.ev_db_range = get_ev_database_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        car.wltp_range = get_wltp_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        car.battery_size = extract_battery_size(str(car.model))
        car.towing_range = calculate_towing_range(car, car.ev_db_range)
        
        car.score, car.score_breakdown = calculate_car_score(car, config, return_breakdown=True)
    
    # Get statistics for sidebar
    # Calculate statistics for sidebar
    max_price = config.get('search_criteria', {}).get('max_price', 35000)
    stats = {
        'total_ever': session.query(Car).count(),
        'total_available': session.query(Car).filter(Car.is_available == True).count(),
        'within_budget': session.query(Car).filter(
            Car.is_available == True,
            Car.price <= max_price
        ).count(),
        'perfect_matches': session.query(Car).filter(
            Car.is_available == True,
            Car.has_all_required_features == True
        ).count(),
        'avg_price': session.query(func.avg(Car.price)).filter(Car.is_available == True).scalar() or 0
    }
    # Get unique makes and models for filter dropdowns
    available_makes = session.query(Car.make).filter(Car.is_available == True).distinct().order_by(Car.make).all()
    available_makes = [m[0] for m in available_makes if m[0]]
    
    available_models = []
    if make:
        available_models = session.query(Car.model).filter(
            Car.is_available == True,
            Car.make == make
        ).distinct().order_by(Car.model).all()
        available_models = [m[0] for m in available_models if m[0]]
    
    session.close()
    
    # Build user_reqs object from config for the sidebar
    class UserReqs:
        def __init__(self):
            self.min_price = config.get('search_criteria', {}).get('min_price', 15000)
            self.max_price = config.get('search_criteria', {}).get('max_price', 35000)
            self.min_year = config.get('search_criteria', {}).get('min_year', 2020)
            self.max_mileage_acceptable = config.get('search', {}).get('max_mileage_km', 150000)
    
    user_reqs_obj = UserReqs()
    
    return render_template('index.html',
                         cars=cars,
                         stats=stats,
                         page=page,
                         total_pages=(total_cars + per_page - 1) // per_page,
                         total_cars=total_cars,
                         available_makes=available_makes,
                         available_models=available_models,
                         trade_in_value=TRADE_IN_VALUE,
                         user_reqs=user_reqs_obj,
                         config=config)


@app.route('/car/<int:car_id>')
def car_detail(car_id):
    """Detailed view of a single car"""
    session = db.get_session()
    
    car = session.query(Car).get(car_id)
    if not car:
        session.close()
        return "Car not found", 404
    
    # Get price history
    price_history = session.query(PriceHistory).filter(
        PriceHistory.car_id == car_id
    ).order_by(PriceHistory.recorded_at.asc()).all()
    
    # Check critical features
    critical_features = config.get('critical_features', [])
    critical_present, critical_missing = match_required_features(
        critical_features, car.features if car.features else []
    )
    
    # Check nice-to-have features
    nice_to_have = config.get('nice_to_have_features', [])
    nice_present, nice_missing = match_required_features(
        nice_to_have, car.features if car.features else []
    )
    
    # Add EV-Database range data
    fuel_type_str = str(car.fuel_type) if car.fuel_type is not None else None
    car.ev_db_range = get_ev_database_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
    
    # Add WLTP range data
    car.wltp_range = get_wltp_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
    car.battery_size = extract_battery_size(str(car.model))
    car.towing_range = calculate_towing_range(car, car.ev_db_range)
    
    # Find potential duplicates
    duplicates = find_duplicate_cars(car, session)
    
    session.close()
    
    return render_template('car_detail.html',
                         car=car,
                         price_history=price_history,
                         critical_present=critical_present,
                         critical_missing=critical_missing,
                         nice_present=nice_present,
                         nice_missing=nice_missing,
                         duplicates=duplicates,
                         trade_in_value=TRADE_IN_VALUE,
                         config=config)


@app.route('/my-matches')
def my_matches():
    """Show cars matching user's specific requirements with clear indicators"""
    session = db.get_session()
    
    # Get filter parameters from request
    make = request.args.get('make', '')
    model = request.args.get('model', '')
    vehicle_type = request.args.get('vehicle_type', '')
    fuel_type = request.args.get('fuel_type', '')
    min_year = request.args.get('min_year', type=int)
    max_year = request.args.get('max_year', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_mileage = request.args.get('min_mileage', type=int)
    max_mileage = request.args.get('max_mileage', type=int)
    max_distance = request.args.get('max_distance', type=float)
    min_storage = request.args.get('min_storage', type=int)
    sort_by = request.args.get('sort_by', 'match_score')
    
    # Get search criteria from config  
    full_electric_criteria = {}
    phev_hybrid_criteria = {}
    station_wagon_criteria = {}
    
    for cat in config.get('categories', []):
        if cat.get('name') == 'Full Electric SUV':
            full_electric_criteria = cat
        elif cat.get('name') == 'PHEV/Hybrid SUV':
            phev_hybrid_criteria = cat
        elif cat.get('name') == 'Stationwagon (PHEV/Hybrid)':
            station_wagon_criteria = cat
    
    # Use the most restrictive criteria (from Gaspedaal URL requirements)
    user_reqs = {
        'min_price': config.get('search_criteria', {}).get('min_price', 20000),
        'max_price': config.get('search_criteria', {}).get('max_price', 35000),
        'min_year': config.get('search_criteria', {}).get('min_year', 2022),
        'acceptable_year': 2020,  # Still allow 2020 as acceptable
        'max_mileage_priority': config.get('search_criteria', {}).get('max_mileage_km', 60000),
        'max_mileage_acceptable': 100000,  # More flexible upper limit
        'preferred_makes': config.get('preferred_cars', {}).get('makes', []),
        'preferred_models': config.get('preferred_cars', {}).get('models', [])
    }
    
    # Build query with basic criteria
    query = session.query(Car).filter(
        Car.is_available == True,
        Car.price >= user_reqs['min_price'],
        Car.price <= user_reqs['max_price'],
        Car.year >= user_reqs['acceptable_year'],
        Car.mileage_km < user_reqs['max_mileage_acceptable'],
        Car.fuel_type.in_(['Full Electric', 'PHEV', 'Hybrid'])  # Only EV/PHEV/Hybrid
    )
    
    # Apply additional filters from request
    if make:
        query = query.filter(Car.make == make)
    if model:
        query = query.filter(Car.model == model)
    if vehicle_type:
        query = query.filter(Car.vehicle_type == vehicle_type)
    if fuel_type:
        query = query.filter(Car.fuel_type == fuel_type)
    if min_year:
        query = query.filter(Car.year >= min_year)
    if max_year:
        query = query.filter(Car.year <= max_year)
    if min_price:
        query = query.filter(Car.price >= min_price)
    if max_price:
        query = query.filter(Car.price <= max_price)
    if min_mileage:
        query = query.filter(Car.mileage_km >= min_mileage)
    if max_mileage:
        query = query.filter(Car.mileage_km <= max_mileage)
    if max_distance:
        query = query.filter(Car.distance_from_heerenveen_km <= max_distance)
    if min_storage:
        query = query.filter(Car.storage_capacity_liters >= min_storage)
    
    all_cars = query.all()
    
    # Filter out excluded vehicles
    # Also apply family car size filters: min boot space and proper doors/seats
    min_storage_from_config = config.get('search', {}).get('min_storage_capacity_liters', 400)
    filtered_cars = [
        car for car in all_cars 
        if not should_exclude_vehicle(str(car.make or ''), str(car.model or ''))
        and (car.doors is None or car.doors >= 4)  # 4+ doors for family use
        and (car.seats is None or car.seats >= 5)  # 5+ seats required
        and (car.storage_capacity_liters is None or car.storage_capacity_liters >= min_storage_from_config)  # Min boot space from config
    ]
    
    # Analyze each car for requirements
    analyzed_cars = []
    for car in filtered_cars:
        # Load boot space if missing
        if not car.storage_capacity_liters:
            boot_data = get_boot_space(str(car.make), str(car.model))
            if boot_data:
                car.storage_capacity_liters = boot_data.get('normal', 0)
        
        # Add EV-Database range data
        fuel_type_str = str(car.fuel_type) if car.fuel_type is not None else None
        car.ev_db_range = get_ev_database_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        
        # Add WLTP range data
        car.wltp_range = get_wltp_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        car.battery_size = extract_battery_size(str(car.model))
        car.towing_range = calculate_towing_range(car, car.ev_db_range)
        
        car_features_str = ''
        if isinstance(car.features, str):
            car_features_str = car.features.lower()
        elif isinstance(car.features, list):
            car_features_str = ' '.join(car.features).lower()
        
        # Check ALL 12 MUST-HAVE critical features (dealbreakers)
        critical_features_check = check_critical_features(car, config)
        
        # All critical features must be present for a perfect match
        dealbreakers_met = all(critical_features_check.values()) if critical_features_check else False
        missing_critical = sum(1 for has_it in critical_features_check.values() if not has_it) if critical_features_check else len(config.get('critical_features', []))
        
        # Check NICE-TO-HAVE features (from config) using enhanced matching
        nice_to_have_features = config.get('nice_to_have_features', [])
        nice_features_present, _ = match_required_features(
            nice_to_have_features, 
            car.features if car.features else []
        )
        nice_to_have_count = len(nice_features_present)
        
        # Mileage tier
        if car.mileage_km and car.mileage_km < user_reqs['max_mileage_priority']:
            mileage_tier = 'priority'
        else:
            mileage_tier = 'acceptable'
        
        # Year tier
        if car.year and car.year >= user_reqs['min_year']:
            year_tier = 'preferred'
        else:
            year_tier = 'acceptable'
        
        # Check if it's a preferred brand/model
        is_preferred_brand = car.make in user_reqs['preferred_makes']
        is_preferred_model = any(model.lower() in str(car.model).lower() for model in user_reqs['preferred_models'])
        
        # Check body style (prefer SUV/Station Wagon for family use)
        vehicle_type_str = str(car.vehicle_type).upper() if car.vehicle_type else ''
        # Calculate score breakdown for tooltip
        raw_score, score_breakdown = calculate_car_score(car, config, return_breakdown=True)
        value_rating = convert_score_to_value_rating(raw_score)

        is_family_body_style = 'SUV' in vehicle_type_str or 'STATIONWAGON' in vehicle_type_str or 'STATION' in vehicle_type_str
        
        analyzed_cars.append({
            'car': car,
            'dealbreakers_met': dealbreakers_met,
            'critical_features': critical_features_check,
            'missing_critical_count': missing_critical,
            'nice_features_present': nice_features_present,
            'nice_to_have_count': nice_to_have_count,
            'mileage_tier': mileage_tier,
            'year_tier': year_tier,
            'is_preferred_brand': is_preferred_brand,
            'is_preferred_model': is_preferred_model,
            'range_value': (
                # Prioritize electric_range_km (practical "Actieradius praktijk" from seller)
                car.electric_range_km or car.ad_listed_range_km or car.range_km
            ),
            'is_wltp_estimate': True if (car.ad_listed_range_km or car.range_km or car.electric_range_km) else False,  # Assume scraped/WLTP if we have range data
            'match_score': (
                (100 if dealbreakers_met else 0) +  # All critical features = 100 points
                (nice_to_have_count * 10) +  # Each nice-to-have is 10 points
                (10 if mileage_tier == 'priority' else 5) +  # Low mileage bonus
                (10 if year_tier == 'preferred' else 5) +  # Newer year bonus
                (20 if is_preferred_brand else 0) +  # Brand preference (increased boost)
                (30 if is_preferred_model else 0) +  # Model preference (strong boost)
                (5 if is_family_body_style else 0)  # SUV/Station Wagon preference
            ),
            'breakdown': score_breakdown,
            'value_rating': value_rating
        })
    
    # Sort by match score (highest first), then by price (lowest first)
    analyzed_cars.sort(key=lambda x: (-x['match_score'], x['car'].price))
    
    # Split into three tiers based on critical features count
    # Tier 1: Perfect Matches (8/8 critical features)
    # Tier 2: Great Matches (6-7/8 critical features)
    # Tier 3: Good Matches (4-5/8 critical features)
    # Below 4: Not shown (too many missing features)
    
    total_critical = len(config.get('critical_features', []))
    perfect_matches = []
    great_matches = []
    good_matches = []
    
    for item in analyzed_cars:
        features_met = total_critical - item['missing_critical_count']
        
        if item['dealbreakers_met']:  # 8/8
            perfect_matches.append(item)
        elif features_met >= 6:  # 6-7/8
            great_matches.append(item)
        elif features_met >= 4:  # 4-5/8
            good_matches.append(item)
        # Cars with fewer than 4 features are not shown
    
    # Get unique makes and models for filter dropdowns
    available_makes = session.query(Car.make).filter(Car.is_available == True).distinct().order_by(Car.make).all()
    available_makes = [m[0] for m in available_makes if m[0]]
    
    available_models = []
    if make:
        available_models = session.query(Car.model).filter(
            Car.is_available == True,
            Car.make == make
        ).distinct().order_by(Car.model).all()
        available_models = [m[0] for m in available_models if m[0]]
    
    # Calculate statistics for sidebar
    max_price = config.get('search_criteria', {}).get('max_price', 35000)
    stats = {
        'total_ever': session.query(Car).count(),
        'total_available': session.query(Car).filter(Car.is_available == True).count(),
        'within_budget': session.query(Car).filter(
            Car.is_available == True,
            Car.price <= max_price
        ).count(),
        'perfect_matches': session.query(Car).filter(
            Car.is_available == True,
            Car.has_all_required_features == True
        ).count(),
        'avg_price': session.query(func.avg(Car.price)).filter(Car.is_available == True).scalar() or 0
    }
    session.close()
    
    return render_template('my_matches.html',
                         perfect_matches=perfect_matches,
                         great_matches=great_matches,
                         good_matches=good_matches,
                         user_reqs=user_reqs,
                         trade_in_value=TRADE_IN_VALUE,
                         config=config,
                         total_critical=total_critical,
                         available_makes=available_makes,
                         available_models=available_models,
                         stats=stats)


@app.route('/top-matches')
def top_matches():
    """Show top 3 Full Electric and top 3 PHEV/Hybrid cars based on smart scoring (price, odometer, range, age)"""
    print("=" * 80, flush=True)
    print("TOP-MATCHES ROUTE CALLED", flush=True)
    print(f"Request URL: {request.url}", flush=True)
    print(f"Request args: {request.args}", flush=True)
    print(f"Request headers: {dict(request.headers)}", flush=True)
    print("=" * 80, flush=True)
    
    session = db.get_session()
    
    # Get filter parameters from request
    make = request.args.get('make', '')
    model = request.args.get('model', '')
    vehicle_type = request.args.get('vehicle_type', '')
    fuel_type = request.args.get('fuel_type', '')
    min_year = request.args.get('min_year', type=int)
    max_year = request.args.get('max_year', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_mileage = request.args.get('min_mileage', type=int)
    max_mileage = request.args.get('max_mileage', type=int)
    max_distance = request.args.get('max_distance', type=float)
    min_storage = request.args.get('min_storage', type=int)
    
    print(f"Filter params - make:{make}, model:{model}, type:{vehicle_type}, fuel:{fuel_type}", flush=True)
    print(f"Filter params - years:{min_year}-{max_year}, price:{min_price}-{max_price}", flush=True)
    print(f"Filter params - mileage:{min_mileage}-{max_mileage}, distance:{max_distance}, storage:{min_storage}", flush=True)
    
    # Build base query for Full Electric cars
    full_electric_query = session.query(Car).filter(
        Car.is_available == True,
        Car.fuel_type == 'Full Electric'
    )
    
    # Apply filters to Full Electric query
    if make:
        full_electric_query = full_electric_query.filter(Car.make == make)
    if model:
        full_electric_query = full_electric_query.filter(Car.model == model)
    if vehicle_type:
        full_electric_query = full_electric_query.filter(Car.vehicle_type == vehicle_type)
    if min_year:
        full_electric_query = full_electric_query.filter(Car.year >= min_year)
    if max_year:
        full_electric_query = full_electric_query.filter(Car.year <= max_year)
    if min_price:
        full_electric_query = full_electric_query.filter(Car.price >= min_price)
    if max_price:
        full_electric_query = full_electric_query.filter(Car.price <= max_price)
    if min_mileage:
        full_electric_query = full_electric_query.filter(Car.mileage_km >= min_mileage)
    if max_mileage:
        full_electric_query = full_electric_query.filter(Car.mileage_km <= max_mileage)
    if max_distance:
        full_electric_query = full_electric_query.filter(Car.distance_from_heerenveen_km <= max_distance)
    if min_storage:
        full_electric_query = full_electric_query.filter(Car.storage_capacity_liters >= min_storage)
    
    full_electric_all = full_electric_query.all()
    print(f"=== FULL ELECTRIC FILTERING DEBUG ===", flush=True)
    print(f"Initial query found: {len(full_electric_all)} Full Electric cars", flush=True)
    
    # Filter out excluded vehicles and apply family car size filters
    full_electric_filtered = [
        car for car in full_electric_all 
        if not should_exclude_vehicle(str(car.make or ''), str(car.model or ''))
        and (car.doors is None or car.doors >= 4)  # Require 4+ doors (or unknown)
        and (car.seats is None or car.seats >= 5)  # Require 5+ seats (or unknown)
        and (car.storage_capacity_liters is None or car.storage_capacity_liters >= 500)  # Min 500L boot when known
    ]
    print(f"After family car filters (4+ doors, 5+ seats, 500L+ boot): {len(full_electric_filtered)} cars", flush=True)
    
    # Define preferred makes and models (same as my-matches page)
    preferred_makes = ['Skoda', 'Audi', 'Kia']
    preferred_models = ['Enyaq', 'Kodiaq', 'e-tron', 'EV5', 'EV9', 'Leon Sportstourer', 'Leon ST', 'Cupra Leon']
    
    # Score and sort Full Electric cars
    full_electric_scored = []
    for car in full_electric_filtered:
        # Load boot space if missing
        if not car.storage_capacity_liters:
            boot_data = get_boot_space(str(car.make), str(car.model))
            if boot_data:
                car.storage_capacity_liters = boot_data.get('normal', 0)
        
        # Add EV-Database range data
        fuel_type_str = str(car.fuel_type) if car.fuel_type is not None else None
        car.ev_db_range = get_ev_database_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        
        # Add WLTP range data
        car.wltp_range = get_wltp_range(str(car.make), str(car.model), fuel_type_str)  # type: ignore
        car.battery_size = extract_battery_size(str(car.model))
        car.towing_range = calculate_towing_range(car, car.ev_db_range)
        
        # Check if it's a preferred brand/model
        is_preferred_brand = car.make in preferred_makes
        is_preferred_model = any(model.lower() in str(car.model).lower() for model in preferred_models)
        car.is_preferred = is_preferred_brand or is_preferred_model
        
        # Use higher distance weight for top-matches page to prioritize local cars (20% vs 10% default)
        raw_score, score_breakdown = calculate_car_score(car, config, distance_weight=0.20, return_breakdown=True)
        value_rating = convert_score_to_value_rating(raw_score)
        critical_features = check_critical_features(car, config)
        full_electric_scored.append({
            'car': car,
            'score': raw_score,
            'value_rating': value_rating,
            'critical_features': critical_features,
            'missing_critical': sum(1 for has_it in critical_features.values() if not has_it),
            'breakdown': score_breakdown
        })
    
    # Sort by score (lower is better)
    full_electric_scored.sort(key=lambda x: x['score'])
    # DEBUG: Log top 10 scores
    logger.info("=== TOP 10 FULL ELECTRIC SCORES (LOWER IS BETTER) ===")
    for i, item in enumerate(full_electric_scored[:10]):
        car = item["car"]
        logger.info(f"#{i+1}: {car.make} {car.model} ({car.year}) - Score: {item['score']:.2f} - Distance: {car.distance_from_heerenveen_km}km - Price: €{car.price:,} - Mileage: {car.mileage_km:,}km")
    logger.info("=" * 80)
    full_electric = [item['car'] for item in full_electric_scored[:3]]
    # Add score and value_rating to car objects for display
    for item in full_electric_scored[:3]:
        item['car'].score = item['score']
        item['car'].value_rating = item['value_rating']
        item['car'].breakdown = item['breakdown']
    
    # Build base query for PHEV/Hybrid cars
    phev_query = session.query(Car).filter(
        Car.is_available == True,
        Car.fuel_type.in_(['PHEV', 'Hybrid'])
    )
    
    # Apply filters to PHEV query
    if make:
        phev_query = phev_query.filter(Car.make == make)
    if model:
        phev_query = phev_query.filter(Car.model == model)
    if vehicle_type:
        phev_query = phev_query.filter(Car.vehicle_type == vehicle_type)
    if min_year:
        phev_query = phev_query.filter(Car.year >= min_year)
    if max_year:
        phev_query = phev_query.filter(Car.year <= max_year)
    if min_price:
        phev_query = phev_query.filter(Car.price >= min_price)
    if max_price:
        phev_query = phev_query.filter(Car.price <= max_price)
    if min_mileage:
        phev_query = phev_query.filter(Car.mileage_km >= min_mileage)
    if max_mileage:
        phev_query = phev_query.filter(Car.mileage_km <= max_mileage)
    if max_distance:
        phev_query = phev_query.filter(Car.distance_from_heerenveen_km <= max_distance)
    if min_storage:
        phev_query = phev_query.filter(Car.storage_capacity_liters >= min_storage)
    
    phev_all = phev_query.all()
    logger.info(f"=== PHEV/HYBRID FILTERING DEBUG ===")
    logger.info(f"Initial query found: {len(phev_all)} PHEV/Hybrid cars")
    
    # Filter out excluded vehicles and apply family car size filters
    phev_filtered = [
        car for car in phev_all 
        if not should_exclude_vehicle(str(car.make or ''), str(car.model or ''))
        and (car.doors is None or car.doors >= 4)  # Require 4+ doors (or unknown)
        and (car.seats is None or car.seats >= 5)  # Require 5+ seats (or unknown)
        and (car.storage_capacity_liters is None or car.storage_capacity_liters >= 500)  # Min 500L boot when known
    ]
    logger.info(f"After family car filters (4+ doors, 5+ seats, 500L+ boot): {len(phev_filtered)} cars")
    
    # Score and sort PHEV cars
    phev_scored = []
    for car in phev_filtered:
        # Load boot space if missing
        if not car.storage_capacity_liters:
            boot_data = get_boot_space(str(car.make), str(car.model))
            if boot_data:
                car.storage_capacity_liters = boot_data.get('normal', 0)
        
        # Check if it's a preferred brand/model
        is_preferred_brand = car.make in preferred_makes
        is_preferred_model = any(model.lower() in str(car.model).lower() for model in preferred_models)
        car.is_preferred = is_preferred_brand or is_preferred_model
        # Use higher distance weight for top-matches page to prioritize local cars (20% vs 10% default)
        
        raw_score, score_breakdown = calculate_car_score(car, config, distance_weight=0.20, return_breakdown=True)
        value_rating = convert_score_to_value_rating(raw_score)
        critical_features = check_critical_features(car, config)
        phev_scored.append({
            'car': car,
            'score': raw_score,
            'value_rating': value_rating,
            'critical_features': critical_features,
            'missing_critical': sum(1 for has_it in critical_features.values() if not has_it),
            'breakdown': score_breakdown
        })
    
    # Sort by score (lower is better)
    phev_scored.sort(key=lambda x: x['score'])
    phev = [item['car'] for item in phev_scored[:3]]
    # Add score and value_rating to car objects for display
    for item in phev_scored[:3]:
        item['car'].score = item['score']
        item['car'].value_rating = item['value_rating']
        item['car'].breakdown = item['breakdown']
    
    # Organize by fuel type for template
    cars_by_fuel = {}
    if full_electric:
        cars_by_fuel['Full Electric'] = full_electric
    if phev:
        cars_by_fuel['PHEV/Hybrid'] = phev
    
    print(f"=== FINAL RESULTS ===", flush=True)
    print(f"cars_by_fuel keys: {list(cars_by_fuel.keys())}", flush=True)
    print(f"Full Electric cars: {len(cars_by_fuel.get('Full Electric', []))}", flush=True)
    print(f"PHEV/Hybrid cars: {len(cars_by_fuel.get('PHEV/Hybrid', []))}", flush=True)
    
    # Get critical features info for all top matches
    critical_features_info = {}
    for car in full_electric + phev:
        critical_features_info[car.id] = check_critical_features(car, config)
    
    # Get unique makes and models for filter dropdowns
    available_makes = session.query(Car.make).filter(Car.is_available == True).distinct().order_by(Car.make).all()
    available_makes = [m[0] for m in available_makes if m[0]]
    
    available_models = []
    if make:
        available_models = session.query(Car.model).filter(
            Car.is_available == True,
            Car.make == make
        ).distinct().order_by(Car.model).all()
        available_models = [m[0] for m in available_models if m[0]]
    
    # Build user_reqs object for the sidebar
    user_reqs = {
        'min_price': config.get('search_criteria', {}).get('min_price', 20000),
        'max_price': config.get('search_criteria', {}).get('max_price', 35000),
        'min_year': config.get('search_criteria', {}).get('min_year', 2022),
        'max_mileage_acceptable': config.get('search_criteria', {}).get('max_mileage_km', 100000)
    }
    
    
    # Calculate statistics for sidebar
    max_price = config.get('search_criteria', {}).get('max_price', 35000)
    stats = {
        'total_ever': session.query(Car).count(),
        'total_available': session.query(Car).filter(Car.is_available == True).count(),
        'within_budget': session.query(Car).filter(
            Car.is_available == True,
            Car.price <= max_price
        ).count(),
        'perfect_matches': session.query(Car).filter(
            Car.is_available == True,
            Car.has_all_required_features == True
        ).count(),
        'avg_price': session.query(func.avg(Car.price)).filter(Car.is_available == True).scalar() or 0
    }
    session.close()
    
    return render_template('top_matches.html', 
                          cars_by_fuel=cars_by_fuel,
                          critical_features_info=critical_features_info,
                          trade_in_value=TRADE_IN_VALUE,
                          config=config,
                          available_makes=available_makes,
                          stats=stats,
                          available_models=available_models,
                          user_reqs=user_reqs)


@app.route('/analytics')
def analytics():
    """Analytics and charts page"""
    session = db.get_session()
    
    # Price distribution
    price_ranges = [
        (0, 15000),
        (15000, 20000),
        (20000, 25000),
        (25000, 30000),
        (30000, 35000)
    ]
    
    # Preferred cars configuration from config.yaml
    preferred_makes = config['preferred_cars']['makes']
    preferred_models = config['preferred_cars']['models']
    
    price_distribution = []
    preferred_counts = []
    
    for min_p, max_p in price_ranges:
        # Total cars in this range
        count = session.query(Car).filter(
            Car.is_available == True,
            Car.price >= min_p,
            Car.price < max_p
        ).count()
        
        # Cars matching specifications in this range (has all required features)
        matching_specs_count = session.query(Car).filter(
            Car.is_available == True,
            Car.price >= min_p,
            Car.price < max_p,
            Car.has_all_required_features == True
        ).count()
        
        price_distribution.append({
            'range': f"€{min_p//1000}k-{max_p//1000}k",
            'count': count
        })
        preferred_counts.append(matching_specs_count)
    
    # Find the range with most cars matching specifications
    # Only highlight if there's a clear winner (no ties)
    max_preferred_count = max(preferred_counts) if preferred_counts else 0
    count_of_max = preferred_counts.count(max_preferred_count) if max_preferred_count > 0 else 0
    
    # Only set preferred_range_indices if there's a unique maximum (not a tie)
    if max_preferred_count > 0 and count_of_max == 1:
        preferred_range_index = preferred_counts.index(max_preferred_count)
        preferred_range_indices = [preferred_range_index]  # Pass as list for template
    else:
        preferred_range_index = -1  # Don't highlight any range if there's a tie
        preferred_range_indices = []  # Empty list means no highlighting
    
    logger.info(f"Cars matching specs by range: {preferred_counts}, max={max_preferred_count}, ties={count_of_max}, index={preferred_range_index}")
    
    
    # Cars by source
    sources = session.query(
        Car.source_website,
        func.count(Car.id).label('count')
    ).filter(
        Car.is_available == True,
        Car.source_website.isnot(None)
    ).group_by(Car.source_website).all()
    
    # Cars by vehicle type (filter out None values)
    vehicle_types = session.query(
        Car.vehicle_type,
        func.count(Car.id).label('count')
    ).filter(
        Car.is_available == True,
        Car.vehicle_type.isnot(None)
    ).group_by(Car.vehicle_type).all()
    
    # Recent scraping activity
    recent_scrapes = session.query(ScraperLog).order_by(
        desc(ScraperLog.started_at)
    ).limit(20).all()
    
    # Average features count
    avg_features = session.query(func.avg(Car.features_count)).filter(
        Car.is_available == True
    ).scalar() or 0
    
    # Feature completion distribution (only count cars with features_count data)
    feature_distribution = [
        {'label': '0-3 features', 'count': session.query(Car).filter(
            Car.is_available == True,
            Car.features_count.isnot(None),
            Car.features_count >= 0,
            Car.features_count <= 3
        ).count()},
        {'label': '4-6 features', 'count': session.query(Car).filter(
            Car.is_available == True,
            Car.features_count.isnot(None),
            Car.features_count >= 4,
            Car.features_count <= 6
        ).count()},
        {'label': '7-8 features', 'count': session.query(Car).filter(
            Car.is_available == True,
            Car.features_count.isnot(None),
            Car.features_count >= 7,
            Car.features_count <= 8
        ).count()},
        {'label': 'All 9 features', 'count': session.query(Car).filter(
            Car.is_available == True,
            Car.features_count.isnot(None),
            Car.features_count == 9
        ).count()}
    ]
    
    # Fuel type statistics
    fuel_types = session.query(
        Car.fuel_type,
        func.count(Car.id).label('count')
    ).filter(Car.is_available == True).group_by(Car.fuel_type).all()
    
    fuel_type_stats = {}
    for fuel_type, count in fuel_types:
        avg_price = session.query(func.avg(Car.price)).filter(
            Car.is_available == True,
            Car.fuel_type == fuel_type
        ).scalar() or 0
        
        # Handle PHEV/Hybrid grouping
        display_name = fuel_type
        if fuel_type in ['PHEV', 'Hybrid']:
            display_name = 'PHEV'
            # Combine PHEV and Hybrid stats
            if 'PHEV' not in fuel_type_stats:
                combined_count = session.query(Car).filter(
                    Car.is_available == True,
                    Car.fuel_type.in_(['PHEV', 'Hybrid'])
                ).count()
                combined_avg = session.query(func.avg(Car.price)).filter(
                    Car.is_available == True,
                    Car.fuel_type.in_(['PHEV', 'Hybrid'])
                ).scalar() or 0
                fuel_type_stats['PHEV'] = {
                    'count': combined_count,
                    'avg_price': int(combined_avg)
                }
        else:
            fuel_type_stats[display_name] = {
                'count': count,
                'avg_price': int(avg_price)
            }
    
    # PHEV/Hybrid price distribution with individual prices
    phev_cars = session.query(Car).filter(
        Car.is_available == True,
        Car.fuel_type.in_(['PHEV', 'Hybrid'])
    ).order_by(Car.price.asc()).all()
    
    phev_price_data = []
    for car in phev_cars:
        phev_price_data.append({
            'label': f"{car.make} {car.model}",
            'price': int(car.price),
            'year': car.year
        })
    
    phev_avg_price = fuel_type_stats.get('PHEV', {}).get('avg_price', 0)
    
    # Full Electric price distribution with individual prices
    ev_cars = session.query(Car).filter(
        Car.is_available == True,
        Car.fuel_type == 'Full Electric'
    ).order_by(Car.price.asc()).all()
    
    ev_price_data = []
    for car in ev_cars:
        ev_price_data.append({
            'label': f"{car.make} {car.model}",
            'price': int(car.price),
            'year': car.year
        })
    
    ev_avg_price = fuel_type_stats.get('Full Electric', {}).get('avg_price', 0)
    
    # Price trends (last 30 days) - optional, set to empty list for now
    price_trends = []
    
    session.close()
    
    logger.info(f"Analytics - Passing avg_features={avg_features}, critical_features={len(config.get('critical_features', []))}")
    return render_template('analytics.html',
                         price_distribution=price_distribution,
                         preferred_range_indices=preferred_range_indices,
                         sources=sources,
                         vehicle_types=vehicle_types,
                         recent_scrapes=recent_scrapes,
                         avg_features=avg_features,
                         price_trends=price_trends,
                         feature_distribution=feature_distribution,
                         fuel_types=fuel_types,
                         fuel_type_stats=fuel_type_stats,
                         phev_price_data=phev_price_data,
                         phev_avg_price=phev_avg_price,
                         ev_price_data=ev_price_data,
                         ev_avg_price=ev_avg_price,
                         config=config)


@app.route('/api/cars')
def api_cars():
    """API endpoint for car listings (JSON)"""
    session = db.get_session()
    
    # Get filter parameters
    vehicle_type = request.args.get('vehicle_type')
    fuel_type = request.args.get('fuel_type')
    only_complete = request.args.get('only_complete', type=bool, default=False)
    
    query = session.query(Car).filter(Car.is_available == True)
    
    if vehicle_type:
        query = query.filter(Car.vehicle_type == vehicle_type)
    if fuel_type:
        query = query.filter(Car.fuel_type == fuel_type)
    if only_complete:
        query = query.filter(Car.has_all_required_features == True)
    
    all_cars = query.all()
    
    # Filter out excluded vehicles
    filtered_cars = [
        car for car in all_cars 
        if not should_exclude_vehicle(str(car.make or ''), str(car.model or ''))
    ]
    
    cars_data = [car.to_dict() for car in filtered_cars]
    
    session.close()
    
    return jsonify(cars_data)


@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics (JSON)"""
    session = db.get_session()
    
    stats = {
        'total_cars': session.query(Car).filter(Car.is_available == True).count(),
        'perfect_matches': session.query(Car).filter(
            Car.is_available == True,
            Car.has_all_required_features == True
        ).count(),
        'avg_price': float(session.query(func.avg(Car.price)).filter(Car.is_available == True).scalar() or 0),
        'by_source': {},
        'by_vehicle_type': {}
    }
    
    # By source
    sources = session.query(
        Car.source_website,
        func.count(Car.id).label('count')
    ).filter(Car.is_available == True).group_by(Car.source_website).all()
    
    for source, count in sources:
        stats['by_source'][source] = count
    
    # By vehicle type
    vehicle_types = session.query(
        Car.vehicle_type,
        func.count(Car.id).label('count')
    ).filter(Car.is_available == True).group_by(Car.vehicle_type).all()
    
    for vtype, count in vehicle_types:
        stats['by_vehicle_type'][vtype or 'Unknown'] = count
    
    session.close()
    
    return jsonify(stats)


@app.route('/unavailable-cars')
def unavailable_cars():
    """Show all unavailable cars with filter for preferred ones"""
    session = db.get_session()
    
    # Get preferred configuration
    preferred_makes = config.get('preferred_cars', {}).get('makes', [])
    preferred_models = config.get('preferred_cars', {}).get('models', [])
    
    # Get all unavailable cars
    unavailable_query = session.query(Car).filter(Car.is_available == False).order_by(
        Car.marked_unavailable_at.desc()
    )
    
    all_unavailable = unavailable_query.all()
    
    # Separate into preferred and other
    preferred_unavailable = []
    other_unavailable = []
    
    for car in all_unavailable:
        is_preferred_make = car.make in preferred_makes
        is_preferred_model = any(model.lower() in str(car.model).lower() for model in preferred_models)
        
        if is_preferred_make or is_preferred_model:
            car.is_preferred = True
            preferred_unavailable.append(car)
        else:
            car.is_preferred = False
            other_unavailable.append(car)
    
    session.close()
    
    return render_template('unavailable_cars.html',
                         preferred_unavailable=preferred_unavailable,
                         other_unavailable=other_unavailable,
                         config=config)


@app.route('/admin')
def admin():
    """Admin panel for scraper management"""
    session = db.get_session()
    
    # Get database statistics
    total_cars = session.query(func.count(Car.id)).filter(Car.is_available == True).scalar()
    perfect_matches = session.query(func.count(Car.id)).filter(
        Car.is_available == True,
        Car.has_all_required_features == True
    ).scalar()
    
    # Get last scrape time
    last_scrape_log = session.query(ScraperLog).order_by(desc(ScraperLog.started_at)).first()
    if last_scrape_log:
        last_scrape = last_scrape_log.started_at.strftime("%Y-%m-%d %H:%M")
    else:
        last_scrape = "Never"
    
    # Get last availability check stats
    last_availability_check = session.query(ScraperLog).filter(
        ScraperLog.website == 'availability_checker'
    ).order_by(desc(ScraperLog.started_at)).first()
    
    if last_availability_check:
        availability_last_check = last_availability_check.started_at.strftime("%Y-%m-%d %H:%M")
        availability_cars_checked = last_availability_check.cars_found or 0
        availability_cars_unavailable = last_availability_check.cars_updated or 0
        availability_status = last_availability_check.status or 'unknown'
    else:
        availability_last_check = "Never"
        availability_cars_checked = 0
        availability_cars_unavailable = 0
        availability_status = "not_run"
    
    session.close()
    
    # Get scheduler config
    scheduler_config = config.get('scraping', {}).get('scheduler', {})
    scheduler_enabled = scheduler_config.get('enabled', True)
    interval_minutes = scheduler_config.get('interval_minutes', 5)
    
    # Get availability checker config
    availability_config = config.get('availability_checker', {})
    availability_enabled = availability_config.get('enabled', True)
    availability_interval = availability_config.get('check_interval_hours', 6)
    
    # Get browser config
    browser_config = config.get('scraping', {}).get('browser', {})
    headless_mode = browser_config.get('headless', True)
    
    return render_template(
        'admin.html',
        scheduler_enabled=scheduler_enabled,
        scheduler_interval=interval_minutes,
        headless_mode=headless_mode,
        total_cars=total_cars,
        perfect_matches=perfect_matches,
        last_scrape=last_scrape,
        availability_enabled=availability_enabled,
        availability_interval=availability_interval,
        availability_last_check=availability_last_check,
        availability_cars_checked=availability_cars_checked,
        availability_cars_unavailable=availability_cars_unavailable,
        availability_status=availability_status
    )


@app.route('/api/trigger-scrape', methods=['POST'])
def trigger_scrape():
    """Manually trigger a scraper run"""
    try:
        # Get optional scraper parameter
        scraper_name = request.json.get('scraper', 'all') if request.is_json else 'all'
        
        logger.info(f"Manual scraper trigger requested: {scraper_name}")
        
        # Run scrapers in a separate thread to avoid blocking the request
        import threading
        
        def run_scrape():
            try:
                from scrapers.autoscout24_scraper import AutoScout24Scraper
                from scrapers.autotrack_scraper import AutotrackScraper
                from scrapers.gaspedaal_scraper import GaspedaalScraper
                
                if scraper_name == 'all':
                    scrapers = [
                        AutoScout24Scraper(),
                        AutotrackScraper(),
                        GaspedaalScraper()
                    ]
                elif scraper_name == 'autoscout24':
                    scrapers = [AutoScout24Scraper()]
                elif scraper_name == 'autotrack':
                    scrapers = [AutotrackScraper()]
                elif scraper_name == 'gaspedaal':
                    scrapers = [GaspedaalScraper()]
                else:
                    logger.error(f"Unknown scraper: {scraper_name}")
                    return
                
                for scraper in scrapers:
                    try:
                        logger.info(f"Manually running {scraper.__class__.__name__}...")
                        scraper.run()
                        logger.info(f"{scraper.__class__.__name__} completed successfully")
                    except Exception as e:
                        logger.error(f"Error running {scraper.__class__.__name__}: {e}")
            except Exception as e:
                logger.error(f"Error in manual scraper run: {e}")
        
        thread = threading.Thread(target=run_scrape)
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': f'Scraper run started: {scraper_name}',
            'note': 'Scraping is running in the background. Check logs for progress.'
        })
        
    except Exception as e:
        logger.error(f"Error triggering scrape: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/trigger-availability-check', methods=['POST'])
def trigger_availability_check():
    """Manually trigger availability check"""
    try:
        logger.info("Manual availability check requested")
        
        # Run availability check in a separate thread to avoid blocking
        import threading
        
        def run_availability_check():
            try:
                logger.info("Running manual availability check...")
                result = check_car_availability()
                logger.info(f"Availability check completed: {result}")
            except Exception as e:
                logger.error(f"Error in manual availability check: {e}")
        
        thread = threading.Thread(target=run_availability_check)
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': 'Availability check started',
            'note': 'Check is running in the background. Check logs for progress.'
        })
        
    except Exception as e:
        logger.error(f"Error triggering availability check: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/scraper-logs', methods=['GET'])
def get_scraper_logs():
    """Get recent scraper log entries"""
    try:
        import os
        log_file = '/tmp/flask_app.log'
        
        # Check if log file exists
        if not os.path.exists(log_file):
            return jsonify({
                'status': 'success',
                'logs': []
            })
        
        # Read last 100 lines from log file
        with open(log_file, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-100:] if len(lines) > 100 else lines
        
        # Filter for scraper-related logs and format them
        log_entries = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            
            # Only include scraper-related logs
            if any(keyword in line for keyword in ['Scraper', 'scraper', 'AutoTrack', 'AutoScout24', 'Gaspedaal', 'Successfully extracted', 'Found price', 'Processing listing']):
                # Parse timestamp and message
                try:
                    parts = line.split(' - ', 3)
                    if len(parts) >= 4:
                        timestamp = parts[0]
                        logger_name = parts[1]
                        level = parts[2]
                        message = parts[3]
                        
                        log_entries.append({
                            'timestamp': timestamp,
                            'logger': logger_name,
                            'level': level,
                            'message': message
                        })
                except:
                    # If parsing fails, add the whole line
                    log_entries.append({
                        'timestamp': '',
                        'logger': '',
                        'level': 'INFO',
                        'message': line
                    })
        
        return jsonify({
            'status': 'success',
            'logs': log_entries[-50:]  # Return last 50 entries
        })
        
    except Exception as e:
        logger.error(f"Error reading scraper logs: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'logs': []
        }), 500


@app.route('/api/mark-available/<int:car_id>', methods=['POST'])
def mark_car_available(car_id):
    """
    Manually mark a car as available again
    This is used when a user manually verifies a car is back on the market
    """
    from datetime import datetime
    
    try:
        session = db.get_session()
        
        # Get the car
        car = session.query(Car).filter_by(id=car_id).first()
        
        if not car:
            session.close()
            return jsonify({
                'success': False,
                'error': 'Car not found'
            }), 404
        
        # Check if car is already available
        if car.is_available:
            session.close()
            return jsonify({
                'success': False,
                'error': 'Car is already marked as available'
            }), 400
        
        # Store car info before closing session
        car_make = car.make
        car_model = car.model
        
        # Mark car as available and update last_seen
        car.is_available = True
        car.unavailable_reason = None
        car.marked_unavailable_at = None
        car.last_seen = datetime.utcnow()
        
        session.commit()
        session.close()
        
        logger.info(f"Car {car_id} ({car_make} {car_model}) manually marked as available")
        
        return jsonify({
            'success': True,
            'message': f'Car {car_make} {car_model} marked as available',
            'car_id': car_id
        })
        
    except Exception as e:
        logger.error(f"Error marking car {car_id} as available: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/exclusions', methods=['GET'])
def get_exclusions():
    """Get all excluded models from config"""
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        exclusions = config_data.get('vehicle_classification', {}).get('exclude_models', {})
        
        # Convert to list format for easier display
        exclusion_list = []
        for make, models in exclusions.items():
            if isinstance(models, list):
                if len(models) == 0:
                    # Empty list means all models excluded
                    exclusion_list.append({'make': make, 'model': 'ALL', 'id': f"{make}:ALL"})
                else:
                    for model in models:
                        exclusion_list.append({'make': make, 'model': model, 'id': f"{make}:{model}"})
        
        return jsonify({'exclusions': exclusion_list})
    except Exception as e:
        logger.error(f"Error getting exclusions: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/exclusions', methods=['POST'])
def add_exclusion():
    """Add a new exclusion to config"""
    try:
        data = request.json
        make = data.get('make', '').strip()
        model = data.get('model', '').strip()
        
        if not make:
            return jsonify({'status': 'error', 'message': 'Make is required'}), 400
        
        # Load current config
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Ensure the structure exists
        if 'vehicle_classification' not in config_data:
            config_data['vehicle_classification'] = {}
        if 'exclude_models' not in config_data['vehicle_classification']:
            config_data['vehicle_classification']['exclude_models'] = {}
        
        exclude_models = config_data['vehicle_classification']['exclude_models']
        
        # Add the exclusion
        if make not in exclude_models:
            exclude_models[make] = []
        
        if model and model != 'ALL':
            # Add specific model if not already excluded
            if model not in exclude_models[make]:
                exclude_models[make].append(model)
        else:
            # Exclude all models from this make (empty list)
            exclude_models[make] = []
        
        # Save config
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        
        # Reload config in app
        global config
        config = config_data
        
        # Clean up any existing vehicles that match the new exclusion
        deleted_count = clean_excluded_vehicles_from_db()
        
        message = f'Added exclusion: {make} {model if model else "ALL"}'
        if deleted_count > 0:
            message += f' and removed {deleted_count} matching vehicle(s) from database'
        
        return jsonify({
            'status': 'success',
            'message': message
        })
    except Exception as e:
        logger.error(f"Error adding exclusion: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/exclusions/<path:exclusion_id>', methods=['DELETE'])
def delete_exclusion(exclusion_id):
    """Delete an exclusion from config"""
    try:
        # Parse the exclusion_id (format: "Make:Model")
        parts = exclusion_id.split(':', 1)
        if len(parts) != 2:
            return jsonify({'status': 'error', 'message': 'Invalid exclusion ID'}), 400
        
        make, model = parts
        
        # Load current config
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        exclude_models = config_data.get('vehicle_classification', {}).get('exclude_models', {})
        
        if make not in exclude_models:
            return jsonify({'status': 'error', 'message': 'Make not found'}), 404
        
        if model == 'ALL':
            # Remove the entire make
            del exclude_models[make]
        else:
            # Remove specific model
            if model in exclude_models[make]:
                exclude_models[make].remove(model)
                # If no more models for this make, remove the make entry
                if len(exclude_models[make]) == 0:
                    del exclude_models[make]
        
        # Save config
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        
        # Reload config in app
        global config
        config = config_data
        
        # Note: No need to clean database when removing exclusions
        # (previously excluded vehicles should not be auto-added back)
        
        return jsonify({
            'status': 'success',
            'message': f'Removed exclusion: {make} {model}'
        })
    except Exception as e:
        logger.error(f"Error deleting exclusion: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/availability-history')
def api_availability_history():
    """API endpoint for availability check history"""
    try:
        session = db.get_session()
        
        # Query last 20 availability checks
        history_logs = session.query(ScraperLog).filter(
            ScraperLog.website == 'availability_checker'
        ).order_by(desc(ScraperLog.started_at)).limit(20).all()
        
        history_data = []
        for log in history_logs:
            # Calculate duration if completed
            duration_seconds = None
            if log.completed_at and log.started_at:
                duration = log.completed_at - log.started_at
                duration_seconds = int(duration.total_seconds())
            
            history_data.append({
                'id': log.id,
                'started_at': log.started_at.strftime("%Y-%m-%d %H:%M:%S"),
                'completed_at': log.completed_at.strftime("%Y-%m-%d %H:%M:%S") if log.completed_at else None,
                'status': log.status or 'unknown',
                'cars_checked': log.cars_found or 0,
                'cars_unavailable': log.cars_updated or 0,
                'duration_seconds': duration_seconds,
                'error_message': log.error_message
            })
        
        session.close()
        
        return jsonify({
            'status': 'success',
            'history': history_data,
            'total_entries': len(history_data)
        })
        
    except Exception as e:
        logger.error(f"Error fetching availability history: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/scraper-statistics')
def api_scraper_statistics():
    """API endpoint for scraper statistics per website"""
    try:
        session = db.get_session()
        
        # Query statistics for each scraper website (exclude availability_checker)
        all_logs = session.query(ScraperLog).filter(
            ScraperLog.website != 'availability_checker'
        ).all()
        
        # Group statistics by website
        website_stats = {}
        for log in all_logs:
            website = log.website
            if website not in website_stats:
                website_stats[website] = {
                    'total_checks': 0,
                    'successful_checks': 0,
                    'total_cars_found': 0,
                    'total_cars_updated': 0,
                    'last_check': None
                }
            
            website_stats[website]['total_checks'] += 1
            if log.status == 'success':
                website_stats[website]['successful_checks'] += 1
            if log.cars_found:
                website_stats[website]['total_cars_found'] += log.cars_found
            if log.cars_updated:
                website_stats[website]['total_cars_updated'] += log.cars_updated
            
            # Track last check
            if log.started_at:
                if website_stats[website]['last_check'] is None or log.started_at > website_stats[website]['last_check']:
                    website_stats[website]['last_check'] = log.started_at
        
        # Format response
        statistics = []
        for website, stats in website_stats.items():
            total_checks = stats['total_checks']
            successful_checks = stats['successful_checks']
            success_rate = (successful_checks / total_checks * 100) if total_checks > 0 else 0
            
            statistics.append({
                'website': website,
                'total_checks': total_checks,
                'successful_checks': successful_checks,
                'success_rate': round(success_rate, 1),
                'total_cars_found': stats['total_cars_found'],
                'total_cars_updated': stats['total_cars_updated'],
                'last_check': stats['last_check'].strftime("%Y-%m-%d %H:%M:%S") if stats['last_check'] else None
            })
        
        session.close()
        
        return jsonify({
            'status': 'success',
            'statistics': statistics
        })
        
    except Exception as e:
        logger.error(f"Error fetching scraper statistics: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/scraper-trends')
def get_scraper_trends():
    """Get scraper performance trends over the last 30 days"""
    try:
        session = db.Session()
        
        # Get data from last 30 days
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # Query scraper logs
        logs = session.query(ScraperLog).filter(
            ScraperLog.started_at >= thirty_days_ago
        ).order_by(ScraperLog.started_at).all()
        
        # Group data by date and website
        trends_by_date = {}
        for log in logs:
            date_key = log.started_at.strftime('%Y-%m-%d')
            
            if date_key not in trends_by_date:
                trends_by_date[date_key] = {}
            
            if log.website not in trends_by_date[date_key]:
                trends_by_date[date_key][log.website] = {
                    'total_runs': 0,
                    'successful_runs': 0,
                    'total_cars_found': 0,
                    'total_cars_new': 0,
                    'total_cars_updated': 0
                }
            
            trends_by_date[date_key][log.website]['total_runs'] += 1
            if log.status == 'completed':
                trends_by_date[date_key][log.website]['successful_runs'] += 1
            trends_by_date[date_key][log.website]['total_cars_found'] += log.cars_found or 0
            trends_by_date[date_key][log.website]['total_cars_new'] += log.cars_new or 0
            trends_by_date[date_key][log.website]['total_cars_updated'] += log.cars_updated or 0
        
        # Format for Chart.js
        dates = sorted(trends_by_date.keys())
        websites = set()
        for date_data in trends_by_date.values():
            websites.update(date_data.keys())
        websites = sorted(list(websites))
        
        # Build datasets
        trends_data = {
            'dates': dates,
            'websites': websites,
            'success_rate': {},
            'cars_found': {},
            'cars_new': {},
            'cars_updated': {}
        }
        
        for website in websites:
            trends_data['success_rate'][website] = []
            trends_data['cars_found'][website] = []
            trends_data['cars_new'][website] = []
            trends_data['cars_updated'][website] = []
            
            for date in dates:
                if date in trends_by_date and website in trends_by_date[date]:
                    data = trends_by_date[date][website]
                    success_rate = (data['successful_runs'] / data['total_runs'] * 100) if data['total_runs'] > 0 else 0
                    trends_data['success_rate'][website].append(round(success_rate, 1))
                    trends_data['cars_found'][website].append(data['total_cars_found'])
                    trends_data['cars_new'][website].append(data['total_cars_new'])
                    trends_data['cars_updated'][website].append(data['total_cars_updated'])
                else:
                    trends_data['success_rate'][website].append(0)
                    trends_data['cars_found'][website].append(0)
                    trends_data['cars_new'][website].append(0)
                    trends_data['cars_updated'][website].append(0)
        
        session.close()
        
        return jsonify({
            'status': 'success',
            'trends': trends_data
        })
        
    except Exception as e:
        logger.error(f"Error fetching scraper trends: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/scheduler-status')
def get_scheduler_status():
    """Get current scheduler configuration and status"""
    try:
        # Get scheduler config
        scheduler_config = config.get('scraping', {})
        scheduler_enabled = scheduler_config.get('scheduler', {}).get('enabled', False)
        interval_minutes = scheduler_config.get('scheduler', {}).get('interval_minutes', 5)
        
        # Get website configurations
        websites = []
        for website_config in scheduler_config.get('websites', []):
            website_name = website_config.get('name', '')
            website_enabled = website_config.get('enabled', False)
            
            # Get last run from database
            session = db.Session()
            last_log = session.query(ScraperLog).filter(
                ScraperLog.website == website_name
            ).order_by(ScraperLog.started_at.desc()).first()
            
            last_run = None
            last_status = None
            if last_log:
                last_run = last_log.started_at.strftime("%Y-%m-%d %H:%M:%S")
                last_status = last_log.status
            
            session.close()
            
            websites.append({
                'name': website_name,
                'enabled': website_enabled,
                'last_run': last_run,
                'last_status': last_status
            })
        
        # Calculate next run time (approximate)
        # This is a simple calculation based on the last run
        next_run = None
        if scheduler_enabled and websites:
            session = db.Session()
            most_recent_log = session.query(ScraperLog).order_by(
                ScraperLog.started_at.desc()
            ).first()
            
            if most_recent_log:
                next_run_time = most_recent_log.started_at + timedelta(minutes=interval_minutes)
                next_run = next_run_time.strftime("%Y-%m-%d %H:%M:%S")
            
            session.close()
        
        return jsonify({
            'status': 'success',
            'scheduler': {
                'enabled': scheduler_enabled,
                'interval_minutes': interval_minutes,
                'next_run': next_run
            },
            'websites': websites
        })
        
    except Exception as e:
        logger.error(f"Error fetching scheduler status: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/scheduler-update', methods=['POST'])
def update_scheduler_config():
    """Update scheduler configuration in config.yaml"""
    try:
        data = request.json
        
        # Validate input
        if 'scheduler_enabled' not in data or 'interval_minutes' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: scheduler_enabled, interval_minutes'
            }), 400
        
        scheduler_enabled = data['scheduler_enabled']
        interval_minutes = int(data['interval_minutes'])
        website_configs = data.get('websites', [])
        
        # Validate interval
        if interval_minutes < 1:
            return jsonify({
                'status': 'error',
                'message': 'Interval must be at least 1 minute'
            }), 400
        
        # Load current config
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.yaml')
        with open(config_path, 'r') as f:
            current_config = yaml.safe_load(f)
        
        # Update scheduler settings
        if 'scraping' not in current_config:
            current_config['scraping'] = {}
        
        if 'scheduler' not in current_config['scraping']:
            current_config['scraping']['scheduler'] = {}
        
        current_config['scraping']['scheduler']['enabled'] = scheduler_enabled
        current_config['scraping']['scheduler']['interval_minutes'] = interval_minutes
        
        # Update website enabled status
        if website_configs and 'websites' in current_config['scraping']:
            for website_update in website_configs:
                website_name = website_update['name']
                website_enabled = website_update['enabled']
                
                for website in current_config['scraping']['websites']:
                    if website.get('name') == website_name:
                        website['enabled'] = website_enabled
                        break
        
        # Write updated config back to file
        with open(config_path, 'w') as f:
            yaml.dump(current_config, f, default_flow_style=False, sort_keys=False)
        
        # Reload config in memory (Note: Flask app restart required for scheduler changes)
        global config
        config = current_config
        
        return jsonify({
            'status': 'success',
            'message': 'Configuration updated successfully. Please restart the Flask app for changes to take effect.',
            'restart_required': True
        })
        
    except Exception as e:
        logger.error(f"Error updating scheduler config: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/critical-features', methods=['GET'])
def get_critical_features():
    """Get list of all possible critical features with their enabled status, organized by category"""
    try:
        # Define all available features with descriptions, organized by category
        all_features_by_category = {
            'Safety Features': {
                'Adaptive Cruise Control': 'Automatically adjusts speed to maintain safe distance',
                'Lane Assist': 'Helps keep vehicle in lane',
                'Park Assist': 'Assists with parking maneuvers',
                'Achteruitrijcamera': 'Rear-view camera for safer reversing',
                '360° camera': '360-degree camera system for all-around visibility',
                'Dodehoekdetectie': 'Blind spot detection system',
                'Botswaarschuwing': 'Collision warning system',
                'Lane Departure Warning Systeem': 'Warns when drifting out of lane',
                'Verkeersbordherkenning': 'Traffic sign recognition',
                'Vermoeidheidsdetectie': 'Driver fatigue detection',
                'Parkeerhulp automatisch': 'Automatic parking assistance',
            },
            'Comfort & Convenience': {
                'Climate Control': 'Automatic climate/temperature control',
                'Stoelverwarming': 'Heated seats for added comfort',
                'Stuurwielverwarming': 'Heated steering wheel',
                'Elektrische stoelverstelling': 'Power adjustable seats',
                'Elektrische achterklep': 'Power tailgate/trunk',
                'Keyless Entry': 'Keyless entry and start system',
                'Panorama dak': 'Panoramic sunroof/moonroof',
                'Getinte ramen': 'Tinted windows',
                'Regensensor': 'Automatic rain-sensing wipers',
                'Lendensteun': 'Lumbar support for seats',
                'Voorruitverwarming': 'Heated windshield',
            },
            'Infotainment': {
                'Android Auto': 'Smartphone integration for Android devices',
                'Apple CarPlay': 'Smartphone integration for Apple devices',
                'Navigatiesysteem': 'Built-in GPS navigation system',
                'DAB+ radio': 'Digital radio with better sound quality',
                'Bluetooth': 'Bluetooth connectivity',
                'Spraakbediening': 'Voice control system',
                'Geheel digitaal combi-instrument': 'Fully digital instrument cluster',
                'Inductieladen voor smartphones': 'Wireless phone charging',
            },
            'Exterior': {
                'Trekhaak': 'Tow bar/hitch (can be installed aftermarket)',
                'LED verlichting': 'LED lighting system',
                'LED dagrijverlichting': 'LED daytime running lights',
                'Lichtmetalen velgen': 'Alloy wheels',
                'Dakrails': 'Roof rails for cargo',
                'Binnenspiegel automatisch dimmend': 'Auto-dimming rearview mirror'
            }
        }
        
        # Get currently enabled features from config
        enabled_features = config.get('critical_features', [])
        
        # Build response with enabled status, organized by category
        categories = []
        for category_name, features in all_features_by_category.items():
            features_list = []
            for feature_name, description in features.items():
                features_list.append({
                    'id': feature_name.replace(' ', '_').lower(),
                    'name': feature_name,
                    'description': description,
                    'enabled': feature_name in enabled_features
                })
            
            categories.append({
                'name': category_name,
                'id': category_name.replace(' ', '_').replace('&', 'and').lower(),
                'features': features_list
            })
        
        return jsonify({
            'status': 'success',
            'categories': categories,
            'total_enabled': len(enabled_features)
        })
    except Exception as e:
        logger.error(f"Error getting critical features: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/critical-features/<path:feature_id>', methods=['PUT'])
def update_critical_feature(feature_id):
    """Enable or disable a critical feature"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', False)
        
        # Convert feature_id back to feature name
        feature_name_map = {
            # Safety Features
            'adaptive_cruise_control': 'Adaptive Cruise Control',
            'lane_assist': 'Lane Assist',
            'park_assist': 'Park Assist',
            'achteruitrijcamera': 'Achteruitrijcamera',
            '360°_camera': '360° camera',
            'dodehoekdetectie': 'Dodehoekdetectie',
            'botswaarschuwing': 'Botswaarschuwing',
            'lane_departure_warning_systeem': 'Lane Departure Warning Systeem',
            'verkeersbordherkenning': 'Verkeersbordherkenning',
            'vermoeidheidsdetectie': 'Vermoeidheidsdetectie',
            'parkeerhulp_automatisch': 'Parkeerhulp automatisch',
            
            # Comfort & Convenience
            'climate_control': 'Climate Control',
            'stoelverwarming': 'Stoelverwarming',
            'stuurwielverwarming': 'Stuurwielverwarming',
            'elektrische_stoelverstelling': 'Elektrische stoelverstelling',
            'elektrische_achterklep': 'Elektrische achterklep',
            'keyless_entry': 'Keyless Entry',
            'panorama_dak': 'Panorama dak',
            'getinte_ramen': 'Getinte ramen',
            'regensensor': 'Regensensor',
            'lendensteun': 'Lendensteun',
            'voorruitverwarming': 'Voorruitverwarming',
            
            # Infotainment
            'android_auto': 'Android Auto',
            'apple_carplay': 'Apple CarPlay',
            'navigatiesysteem': 'Navigatiesysteem',
            'dab+_radio': 'DAB+ radio',
            'bluetooth': 'Bluetooth',
            'spraakbediening': 'Spraakbediening',
            'geheel_digitaal_combi-instrument': 'Geheel digitaal combi-instrument',
            'inductieladen_voor_smartphones': 'Inductieladen voor smartphones',
            
            # Exterior
            'trekhaak': 'Trekhaak',
            'led_verlichting': 'LED verlichting',
            'led_dagrijverlichting': 'LED dagrijverlichting',
            'lichtmetalen_velgen': 'Lichtmetalen velgen',
            'dakrails': 'Dakrails',
            'binnenspiegel_automatisch_dimmend': 'Binnenspiegel automatisch dimmend'
        }
        
        feature_name = feature_name_map.get(feature_id)
        if not feature_name:
            return jsonify({'status': 'error', 'message': 'Invalid feature ID'}), 400
        
        # Load current config
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        critical_features = config_data.get('critical_features', [])
        
        if enabled:
            # Add feature if not already present
            if feature_name not in critical_features:
                critical_features.append(feature_name)
        else:
            # Remove feature if present
            if feature_name in critical_features:
                critical_features.remove(feature_name)
        
        # Ensure at least 5 features remain enabled (for tier system to work properly)
        if len(critical_features) < 5:
            return jsonify({
                'status': 'error', 
                'message': 'At least 5 critical features must be enabled for the tier system to work'
            }), 400
        
        # Update config
        config_data['critical_features'] = critical_features
        
        # Save config
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        
        # Reload config in app
        global config
        config = config_data
        
        action = 'enabled' if enabled else 'disabled'
        return jsonify({
            'status': 'success',
            'message': f'Critical feature "{feature_name}" {action}',
            'total_enabled': len(critical_features)
        })
    except Exception as e:
        logger.error(f"Error updating critical feature: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/trade-in-value')
def trade_in_value_page():
    """Page to view and update trade-in value"""
    from models.database import CurrentCar, TradeInValue
    session = db.get_session()
    
    # Get current car info
    license_plate = config.get('current_car', {}).get('license_plate')
    current_car = None
    trade_in_history = []
    
    if license_plate:
        current_car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        if current_car:
            # Get trade-in value history (last 10 entries)
            trade_in_history = session.query(TradeInValue)\
                .filter_by(car_id=current_car.id)\
                .order_by(TradeInValue.checked_at.desc())\
                .limit(10)\
                .all()
    
    session.close()
    
    return render_template('trade_in_value.html',
                          current_car=current_car,
                          trade_in_history=trade_in_history,
                          current_trade_in_value=TRADE_IN_VALUE,
                          config=config)


@app.route('/api/trade-in-value', methods=['POST'])
def update_trade_in_value():
    """API endpoint to manually update trade-in value"""
    try:
        from models.database import CurrentCar, TradeInValue
        
        data = request.get_json()
        selling_price = data.get('selling_price')
        mileage_km = data.get('mileage_km')
        
        if not selling_price or not mileage_km:
            return jsonify({'status': 'error', 'message': 'Selling price and mileage are required'}), 400
        
        # Convert to appropriate types
        try:
            selling_price = float(selling_price)
            mileage_km = int(mileage_km)
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid price or mileage format'}), 400
        
        # Validate values
        if selling_price <= 0 or selling_price > 200000:
            return jsonify({'status': 'error', 'message': 'Selling price must be between €1 and €200,000'}), 400
        
        if mileage_km < 0 or mileage_km > 500000:
            return jsonify({'status': 'error', 'message': 'Mileage must be between 0 and 500,000 km'}), 400
        
        session = db.get_session()
        
        # Get current car
        license_plate = config.get('current_car', {}).get('license_plate')
        if not license_plate:
            session.close()
            return jsonify({'status': 'error', 'message': 'No current car configured'}), 400
        
        current_car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        if not current_car:
            session.close()
            return jsonify({'status': 'error', 'message': f'Current car not found: {license_plate}'}), 404
        
        # Create new trade-in value record
        new_value = TradeInValue(
            car_id=current_car.id,
            selling_price=selling_price,
            mileage_km=mileage_km,
            source='manual',
            checked_at=datetime.utcnow(),
            raw_data={'note': 'Manually entered value'}
        )
        
        session.add(new_value)
        session.commit()
        session.close()
        
        # Update global TRADE_IN_VALUE
        global TRADE_IN_VALUE
        TRADE_IN_VALUE = selling_price
        
        logger.info(f"Trade-in value manually updated to €{selling_price:,.0f} at {mileage_km:,} km")
        
        return jsonify({
            'status': 'success',
            'message': f'Trade-in value updated to €{selling_price:,.0f}',
            'trade_in_value': selling_price
        })
    
    except Exception as e:
        logger.error(f"Error updating trade-in value: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/update-mileage', methods=['POST'])
def update_mileage():
    """API endpoint to update only the current car's mileage"""
    try:
        from models.database import CurrentCar
        
        data = request.get_json()
        mileage_km = data.get('mileage_km')
        
        if not mileage_km:
            return jsonify({'status': 'error', 'message': 'Mileage is required'}), 400
        
        # Convert to appropriate type
        try:
            mileage_km = int(mileage_km)
        except (ValueError, TypeError):
            return jsonify({'status': 'error', 'message': 'Invalid mileage format'}), 400
        
        # Validate value
        if mileage_km < 0 or mileage_km > 500000:
            return jsonify({'status': 'error', 'message': 'Mileage must be between 0 and 500,000 km'}), 400
        
        session = db.get_session()
        
        # Get current car
        license_plate = config.get('current_car', {}).get('license_plate')
        if not license_plate:
            session.close()
            return jsonify({'status': 'error', 'message': 'No current car configured'}), 400
        
        current_car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        if not current_car:
            session.close()
            return jsonify({'status': 'error', 'message': f'Current car not found: {license_plate}'}), 404
        
        # Update mileage
        old_mileage = current_car.mileage_km
        current_car.mileage_km = mileage_km
        
        session.commit()
        session.close()
        
        logger.info(f"Mileage updated from {old_mileage:,} km to {mileage_km:,} km for {license_plate}")
        
        return jsonify({
            'status': 'success',
            'message': f'Mileage updated to {mileage_km:,} km',
            'mileage_km': mileage_km,
            'old_mileage_km': old_mileage
        })
    
    except Exception as e:
        logger.error(f"Error updating mileage: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/calculate-depreciation', methods=['GET'])
def calculate_depreciation():
    """API endpoint to calculate depreciation for current car"""
    try:
        from models.database import CurrentCar
        from utils.depreciation_calculator import calculate_depreciation_from_car_data
        
        session = db.get_session()
        
        # Get current car
        license_plate = config.get('current_car', {}).get('license_plate')
        if not license_plate:
            session.close()
            return jsonify({'status': 'error', 'message': 'No current car configured'}), 400
        
        current_car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
        if not current_car:
            session.close()
            return jsonify({'status': 'error', 'message': f'Current car not found: {license_plate}'}), 404
        
        # Check if we have required data for depreciation calculation
        if not current_car.initial_purchase_price:
            session.close()
            return jsonify({
                'status': 'error', 
                'message': 'Purchase price not set. Please update current_car.initial_purchase_price in config.yaml'
            }), 400
        
        if not current_car.purchase_date:
            session.close()
            return jsonify({
                'status': 'error',
                'message': 'Purchase date not set. Please update current_car.purchase_date in config.yaml'
            }), 400
        
        if not current_car.mileage_km:
            session.close()
            return jsonify({
                'status': 'error',
                'message': 'Mileage not available. Please update trade-in value with current mileage.'
            }), 400
        
        # Prepare data for calculator
        car_data = {
            'initial_purchase_price': current_car.initial_purchase_price,
            'purchase_date': current_car.purchase_date,
            'mileage_km': current_car.mileage_km,
            'average_km_per_year': current_car.average_km_per_year,
            'year': current_car.year,  # Add manufacture year for accurate age calculation
            'purchase_mileage_km': current_car.purchase_mileage_km,
            'estimated_new_price': current_car.estimated_new_price
        }
        
        # Calculate depreciation
        result = calculate_depreciation_from_car_data(car_data)
        
        if not result:
            session.close()
            return jsonify({'status': 'error', 'message': 'Could not calculate depreciation'}), 500
        
        session.close()
        
        return jsonify({
            'status': 'success',
            'car': {
                'make': current_car.make,
                'model': current_car.model,
                'year': current_car.year,
                'license_plate': current_car.license_plate,
                'purchase_price': current_car.initial_purchase_price,
                'estimated_new_price': current_car.estimated_new_price or current_car.initial_purchase_price,
                'purchase_date': current_car.purchase_date.isoformat() if current_car.purchase_date else None,
                'current_mileage': current_car.mileage_km
            },
            'depreciation': result
        })
    
    except Exception as e:
        logger.error(f"Error calculating depreciation: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/scraper-service/status', methods=['GET'])
def get_scraper_service_status():
    """Get the status of the scraper Docker container"""
    try:
        import subprocess
        
        # Check if the scraper container is running
        result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=nl-car-tracker-scraper', '--format', '{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            status_output = result.stdout.strip()
            
            if status_output and 'Up' in status_output:
                return jsonify({
                    'status': 'running',
                    'message': 'Scraper service is running',
                    'details': status_output
                })
            else:
                # Check if container exists but is stopped
                stopped_result = subprocess.run(
                    ['docker', 'ps', '-a', '--filter', 'name=nl-car-tracker-scraper', '--format', '{{.Status}}'],

if __name__ == '__main__':
    # Run Flask development server with threading enabled
    # Threading is required to handle concurrent requests when scrapers are running
    # Use PORT env var for Railway, fallback to config for local development
    port = int(os.environ.get('PORT', config['dashboard']['port']))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=config['dashboard']['debug'],
        threaded=True
    )
