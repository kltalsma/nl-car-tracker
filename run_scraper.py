"""
Continuous scraper runner for NL Car Tracker
Runs all scrapers in a loop with configured delays
"""
import time
import random
import yaml
import logging
import signal
import sys
import atexit
import subprocess
from datetime import datetime
from scrapers.autoscout24_scraper import AutoScout24Scraper
from scrapers.autotrack_scraper import AutotrackScraper
from scrapers.gaspedaal_scraper import GaspedaalScraper
from scrapers.vandenbrug_scraper import VandenBrugScraper
from check_availability import AvailabilityChecker

# Global shutdown flag and scraper references
shutdown_requested = False
_scrapers_ref = []
_availability_checker_ref = None
_cleanup_done = False

# Force immediate flushing to file
class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

# Set up logging with unbuffered file output
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = FlushFileHandler('logs/scraper.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

# Configure root logger to capture all logs
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
    force=True  # Override any existing logging configuration
)

logger = logging.getLogger(__name__)


def get_shutdown_requested():
    """Allow scrapers to check shutdown status"""
    global shutdown_requested
    return shutdown_requested


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_requested
    signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
    logger.info(f"*** SHUTDOWN: Received {signal_name} signal - initiating graceful shutdown... ***")
    sys.stdout.flush()  # Ensure log message is written immediately
    shutdown_requested = True


def cleanup_resources(scrapers, availability_checker):
    """Clean up all resources before shutdown with timeout protection"""
    logger.info("*** SHUTDOWN: Cleaning up resources... ***")
    sys.stdout.flush()
    
    import concurrent.futures
    
    # Kill orphaned Chrome/ChromeDriver processes first
    try:
        logger.info("Killing orphaned Chrome processes...")
        subprocess.run(['pkill', '-9', 'chrome'], stderr=subprocess.DEVNULL)
        subprocess.run(['pkill', '-9', 'chromedriver'], stderr=subprocess.DEVNULL)
        logger.info("Orphaned Chrome processes killed")
    except Exception as e:
        logger.warning(f"Error killing Chrome processes: {e}")
    
    # Close all scraper WebDrivers with timeout
    def close_scraper_driver(scraper):
        try:
            if hasattr(scraper, '_close_driver'):
                scraper._close_driver()
                logger.info(f"Closed WebDriver for {scraper.website_name}")
                return True
        except Exception as e:
            logger.error(f"Error closing WebDriver for {scraper.website_name}: {e}")
            return False
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        futures = {executor.submit(close_scraper_driver, s): s for s in scrapers}
        
        # Wait up to 10 seconds for all drivers to close
        try:
            for future in concurrent.futures.as_completed(futures, timeout=10):
                future.result()
        except concurrent.futures.TimeoutError:
            logger.warning("Timeout waiting for scrapers to close - forcing shutdown")
    
    # Close availability checker WebDriver with timeout
    if availability_checker:
        try:
            def close_checker():
                if hasattr(availability_checker, 'driver') and availability_checker.driver:
                    availability_checker.driver.quit()
                    logger.info("Closed availability checker WebDriver")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(close_checker)
                future.result(timeout=5)
        except concurrent.futures.TimeoutError:
            logger.warning("Timeout closing availability checker - forcing shutdown")
        except Exception as e:
            logger.error(f"Error closing availability checker WebDriver: {e}")
    
    logger.info("*** SHUTDOWN: Resource cleanup completed ***")
    sys.stdout.flush()


def atexit_handler():
    """Backup cleanup handler called on exit"""
    global _scrapers_ref, _availability_checker_ref, _cleanup_done
    
    # Skip if cleanup already done
    if _cleanup_done:
        return
    
    logger.info("*** SHUTDOWN: atexit handler called - performing emergency cleanup ***")
    sys.stdout.flush()
    
    if _scrapers_ref or _availability_checker_ref:
        cleanup_resources(_scrapers_ref, _availability_checker_ref)
        _cleanup_done = True


def run_continuous_scraping():
    """Run scrapers continuously with configured delays"""
    global shutdown_requested, _scrapers_ref, _availability_checker_ref, _cleanup_done
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Register atexit handler as backup
    atexit.register(atexit_handler)
    
    logger.info("*** Registered signal handlers (SIGTERM, SIGINT) and atexit handler ***")
    
    # Load configuration
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    # Initialize scrapers
    scrapers = []
    
    for website_config in config['scraping']['websites']:
        if not website_config['enabled']:
            continue
        
        website_name = website_config['name']
        
        if website_name == 'autoscout24.nl':
            scrapers.append(AutoScout24Scraper())
        elif website_name == 'autotrack.nl':
            scrapers.append(AutotrackScraper())
        elif website_name == 'gaspedaal.nl':
            scrapers.append(GaspedaalScraper())
        elif website_name == 'vandenbrug.nl':
            scrapers.append(VandenBrugScraper())
    
    # Initialize availability checker
    availability_enabled = config.get('availability_checker', {}).get('enabled', True)
    if availability_enabled:
        logger.info("Availability checking is ENABLED")
        availability_checker = AvailabilityChecker(
            db_path='data/cars.db',
            config_path='config.yaml',
            headless=True,
            scrape_alternatives=config.get('availability_checker', {}).get('scrape_alternatives', True)
        )
    else:
        logger.info("Availability checking is DISABLED")
        availability_checker = None
    
    # Store references for atexit handler
    _scrapers_ref = scrapers
    _availability_checker_ref = availability_checker
    
    logger.info(f"Initialized {len(scrapers)} scrapers")
    logger.info(f"Starting continuous scraping...")
    logger.info("Press Ctrl+C to stop gracefully")
    
    cycle = 0
    
    try:
        while not shutdown_requested:
            cycle += 1
            logger.info(f"=== Starting scraping cycle #{cycle} ===")
            start_time = datetime.now()
            
            # Run each scraper
            for scraper in scrapers:
                # Check shutdown flag before each scraper
                if shutdown_requested:
                    logger.info("*** SHUTDOWN: Shutdown requested, stopping scraper loop ***")
                    sys.stdout.flush()
                    break
                    
                try:
                    logger.info(f"Running scraper: {scraper.website_name}")
                    # Pass shutdown checker to scraper
                    scraper.shutdown_checker = get_shutdown_requested
                    scraper.run()
                except KeyboardInterrupt:
                    # Re-raise to let the outer handler catch it
                    raise
                except Exception as e:
                    logger.error(f"Error running scraper {scraper.website_name}: {e}")
                    continue
            
            # Don't continue to next steps if shutdown requested
            if shutdown_requested:
                logger.info("*** SHUTDOWN: Skipping availability check and next cycle ***")
                sys.stdout.flush()
                break
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info(f"=== Completed scraping cycle #{cycle} in {duration:.1f} seconds ===")
            
            # Run availability checker after scraping if enabled
            if availability_checker:
                # Check shutdown flag before availability check
                if shutdown_requested:
                    logger.info("*** SHUTDOWN: Shutdown requested, skipping availability check ***")
                    sys.stdout.flush()
                    break
                    
                try:
                    logger.info("=== Starting availability check ===")
                    check_start = datetime.now()
                    
                    # Check cars not seen recently (e.g., older than 1 day)
                    days_threshold = config.get('availability_checker', {}).get('check_stale_cars_days', 3)
                    max_cars = config.get('availability_checker', {}).get('max_cars_per_run', 100)
                    within_budget_only = config.get('availability_checker', {}).get('check_within_budget_only', True)
                    availability_checker.check_and_update_availability(
                        filters={
                            'older_than_days': days_threshold,
                            'limit': max_cars,
                            'within_budget': within_budget_only
                        }
                    )
                    
                    check_duration = (datetime.now() - check_start).total_seconds()
                    logger.info(f"=== Completed availability check in {check_duration:.1f} seconds ===")
                except Exception as e:
                    logger.error(f"Error during availability check: {e}")
            
            # Don't sleep if shutdown requested
            if shutdown_requested:
                logger.info("*** SHUTDOWN: Skipping delay, proceeding to cleanup ***")
                sys.stdout.flush()
                break
            
            # Calculate delay until next cycle
            min_delay = config['scraping']['rate_limit']['min_delay_seconds']
            max_delay = config['scraping']['rate_limit']['max_delay_seconds']
            delay = random.randint(min_delay, max_delay)
            
            logger.info(f"Waiting {delay} seconds until next cycle...")
            logger.info(f"Next cycle will start at: {datetime.now().replace(second=0, microsecond=0)}")
            
            # Sleep in smaller chunks to be responsive to shutdown
            for _ in range(delay):
                if shutdown_requested:
                    logger.info("*** SHUTDOWN: Shutdown requested during sleep, breaking out ***")
                    sys.stdout.flush()
                    break
                time.sleep(1)
    
    finally:
        # Always cleanup resources
        global _cleanup_done
        logger.info("*** SHUTDOWN: Entering finally block for cleanup ***")
        sys.stdout.flush()
        cleanup_resources(scrapers, availability_checker)
        _cleanup_done = True
        logger.info("*** SHUTDOWN: Scraper shutdown complete ***")
        sys.stdout.flush()

if __name__ == "__main__":
    try:
        run_continuous_scraping()
    except Exception as e:
        logger.error(f"Fatal error in scraper: {e}")
        raise
