"""
Base scraper class for NL Car Tracker
Provides common functionality for all website scrapers
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from abc import ABC, abstractmethod
from datetime import datetime
import time
import random
import yaml
import logging
import os
import unicodedata
from typing import List, Dict, Optional
from models.database import Car, PriceHistory, ScraperLog, Database
from utils.email_notifier import EmailNotifier

# Logging is configured in run_scraper.py - do not reconfigure here


class BaseScraper(ABC):
    """Base class for all car website scrapers"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        """
        Initialize the base scraper
        
        Args:
            config_path: Path to configuration file
            db_path: Path to database file
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize database
        self.db = Database(db_path)
        
        # Initialize email notifier
        try:
            self.email_notifier = EmailNotifier(config_path)
        except Exception as e:
            self.logger.warning(f"Failed to initialize email notifier: {e}")
            self.email_notifier = None
        
        # Browser driver (initialized when needed)
        self.driver = None
        
        # Shutdown checker function (set by run_scraper.py)
        self.shutdown_checker = None
        
        # Site-specific configuration (to be set by subclasses)
        self.website_name = None
        self.base_url = None
        
        # Track cars seen in this scrape session
        self.seen_external_ids = set()
        
    def _is_shutdown_requested(self):
        """Check if shutdown has been requested"""
        if self.shutdown_checker and callable(self.shutdown_checker):
            return self.shutdown_checker()
        return False
    
    @staticmethod
    def _normalize_make(make: str) -> str:
        """
        Normalize make values to ensure consistency across scrapers.
        - Removes diacritics (Škoda -> Skoda, Citroën -> Citroen)
        - Standardizes capitalization
        
        Args:
            make: The make string to normalize
            
        Returns:
            Normalized make string
        """
        if not make:
            return make
        
        # Remove diacritics
        nfd = unicodedata.normalize('NFD', make)
        normalized = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
        
        # Standardize capitalization for common makes
        normalized_lower = normalized.lower()
        if normalized_lower == 'bmw':
            return 'BMW'
        elif normalized_lower == 'mg':
            return 'MG'
        elif normalized_lower == 'cupra':
            return 'CUPRA'
        elif normalized_lower == 'seat':
            return 'SEAT'
        elif normalized_lower == 'mercedes-benz':
            return 'Mercedes-Benz'
        else:
            # Capitalize first letter only
            return normalized.capitalize()
    
    def _init_driver(self):
        """Initialize Selenium WebDriver with configured options"""
        if self.driver is not None:
            return
        
        self.logger.info("Initializing Chrome WebDriver...")
        
        chrome_options = Options()
        
        # Headless mode (using new headless mode for better stability)
        if self.config['scraping']['browser']['headless']:
            chrome_options.add_argument('--headless=new')
        
        # Additional options for stability and containerized environments
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--disable-software-rasterizer')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_argument('--log-level=3')
        chrome_options.add_argument('--silent')
        chrome_options.add_argument(f"user-agent={self.config['scraping']['browser']['user_agent']}")
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Initialize driver
        # Try to use system chromedriver first (for Docker/K8s environments)
        try:
            import shutil
            system_chromedriver = shutil.which('chromedriver')
            system_chromium = shutil.which('chromium') or shutil.which('chromium-browser')
            
            # Set chromium binary if found (for Debian-based containers)
            if system_chromium:
                self.logger.info(f"Using chromium binary at {system_chromium}")
                chrome_options.binary_location = system_chromium
            
            if system_chromedriver:
                self.logger.info(f"Using system chromedriver at {system_chromedriver}")
                service = Service(executable_path=system_chromedriver)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                # Fallback to Selenium's built-in driver management
                self.logger.info("System chromedriver not found, using Selenium's built-in driver management")
                self.driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            # Last resort: try webdriver_manager
            self.logger.warning(f"Standard driver initialization failed: {e}. Trying webdriver_manager...")
            try:
                from webdriver_manager.chrome import ChromeDriverManager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e2:
                self.logger.error(f"All driver initialization methods failed: {e2}")
                raise
        
        self.driver.implicitly_wait(2)  # Reduced from 10 to 2 seconds
        
        # Set page load timeout to prevent hanging on slow/unresponsive pages
        # This ensures driver.get() will timeout after 30 seconds instead of waiting indefinitely
        self.driver.set_page_load_timeout(30)
        
        self.logger.info("WebDriver initialized successfully")
    
    def _close_driver(self):
        """Close the WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.logger.info("WebDriver closed")
    
    def _random_delay(self, min_seconds=1, max_seconds=3):
        """Add random delay to appear more human-like"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    def _take_screenshot(self, name='error'):
        """Take a screenshot for debugging"""
        if not self.driver:
            return
        
        os.makedirs('logs/screenshots', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f'logs/screenshots/{self.website_name}_{name}_{timestamp}.png'
        
        try:
            self.driver.save_screenshot(filepath)
            self.logger.info(f"Screenshot saved: {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")
    
    def _save_car_to_db(self, car_data: Dict) -> Optional[Car]:
        """
        Save or update a car in the database
        
        Args:
            car_data: Dictionary containing car information
            
        Returns:
            Car object if saved/updated, None otherwise
        """
        from utils.helpers import get_wltp_range, get_ev_database_range, get_boot_space
        
        session = self.db.get_session()
        
        try:
            # Normalize make value to ensure consistency
            if 'make' in car_data and car_data['make']:
                car_data['make'] = self._normalize_make(car_data['make'])
            
            # Track this car as seen
            self.seen_external_ids.add(car_data['external_id'])
            
            # Populate the three range values if not already provided
            # 1. ad_listed_range_km - from the scraper (usually in car_data)
            # 2. wltp_reference_range_km - from WLTP data
            # 3. evdb_real_range_km - from EV-Database
            
            make = car_data.get('make')
            model = car_data.get('model')
            fuel_type = car_data.get('fuel_type')
            
            # Set ad_listed_range_km from scraped range data
            # For Full Electric: prefer electric_range_km (the prominently displayed "Elektrisch bereik")
            # For PHEV/Hybrid: use electric_range_km for electric-only range, range_km for total range
            if 'ad_listed_range_km' not in car_data:
                if fuel_type == 'Full Electric':
                    # For Full Electric: prefer electric_range_km over range_km
                    if 'electric_range_km' in car_data and car_data['electric_range_km']:
                        car_data['ad_listed_range_km'] = car_data['electric_range_km']
                    elif 'range_km' in car_data and car_data['range_km']:
                        car_data['ad_listed_range_km'] = car_data['range_km']
                else:
                    # For other fuel types: prefer range_km first
                    if 'range_km' in car_data and car_data['range_km']:
                        car_data['ad_listed_range_km'] = car_data['range_km']
                    elif 'electric_range_km' in car_data and car_data['electric_range_km']:
                        car_data['ad_listed_range_km'] = car_data['electric_range_km']
            
            # Populate WLTP range if not provided
            if 'wltp_reference_range_km' not in car_data and make and model:
                try:
                    self.logger.debug(f"Attempting to get WLTP range for {make} {model} (fuel_type={fuel_type})")
                    wltp_range = get_wltp_range(make, model, fuel_type)
                    if wltp_range:
                        car_data['wltp_reference_range_km'] = wltp_range
                        self.logger.info(f"✓ Enriched WLTP range for {make} {model}: {wltp_range} km")
                    else:
                        self.logger.debug(f"No WLTP range found for {make} {model}")
                except Exception as e:
                    self.logger.warning(f"Could not get WLTP range for {make} {model}: {e}")
            
            # Populate EV-Database real-world range if not provided
            if 'evdb_real_range_km' not in car_data and make and model:
                try:
                    self.logger.debug(f"Attempting to get EV-Database range for {make} {model}")
                    evdb_data = get_ev_database_range(make, model, fuel_type)
                    if evdb_data and 'real_range' in evdb_data:
                        car_data['evdb_real_range_km'] = evdb_data['real_range']
                        self.logger.info(f"✓ Enriched EV-Database range for {make} {model}: {evdb_data['real_range']} km")
                    else:
                        self.logger.debug(f"No EV-Database range found for {make} {model}")
                except Exception as e:
                    self.logger.warning(f"Could not get EV-Database range for {make} {model}: {e}")
            
            # Populate boot space if not provided
            if 'storage_capacity_liters' not in car_data and make and model:
                try:
                    self.logger.debug(f"Attempting to get boot space for {make} {model}")
                    boot_space = get_boot_space(make, model)
                    if boot_space:
                        if 'normal' in boot_space and boot_space['normal']:
                            car_data['storage_capacity_liters'] = boot_space['normal']
                            self.logger.info(f"✓ Enriched boot space for {make} {model}: {boot_space['normal']} liters")
                        if 'seats_down' in boot_space and boot_space['seats_down']:
                            car_data['storage_capacity_seats_down_liters'] = boot_space['seats_down']
                            self.logger.info(f"✓ Enriched boot space (seats down) for {make} {model}: {boot_space['seats_down']} liters")
                    else:
                        self.logger.debug(f"No boot space data found for {make} {model}")
                except Exception as e:
                    self.logger.warning(f"Could not get boot space for {make} {model}: {e}")
            
            # Sanitize empty strings to None for JSON and DateTime fields
            # This prevents data integrity issues where empty strings cause JSONDecodeError or ValueError
            json_fields = ['features', 'image_urls', 'raw_data']
            datetime_fields = ['first_seen', 'last_seen', 'marked_unavailable_at', 'last_updated']
            
            for field in json_fields + datetime_fields:
                if field in car_data and car_data[field] == '':
                    car_data[field] = None
                    self.logger.debug(f"Sanitized empty string to None for field: {field}")
            
            # Check if car already exists
            existing_car = session.query(Car).filter_by(
                external_id=car_data['external_id']
            ).first()
            
            if existing_car:
                # Update existing car
                old_price = existing_car.price
                
                # Update fields
                for key, value in car_data.items():
                    if hasattr(existing_car, key):
                        setattr(existing_car, key, value)
                
                existing_car.last_seen = datetime.utcnow()
                
                # Only mark as available if:
                # 1. It was marked unavailable due to 'not_found_in_scrape' (now we found it), OR
                # 2. It was never marked unavailable (is_available is already True)
                # Do NOT override unavailable status from manual verification (website_shows_unavailable, http_error)
                if existing_car.is_available or existing_car.unavailable_reason == 'not_found_in_scrape':
                    existing_car.mark_available()
                else:
                    # Log when we skip marking as available due to verified unavailable status
                    self.logger.info(f"Skipping availability update for {existing_car.make} {existing_car.model} - marked unavailable: {existing_car.unavailable_reason}")
                
                # Track price change
                if old_price != car_data['price']:
                    price_history = PriceHistory(
                        car_id=existing_car.id,
                        price=car_data['price']
                    )
                    session.add(price_history)
                    self.logger.info(f"Price changed: {existing_car.make} {existing_car.model} - €{old_price} -> €{car_data['price']}")
                
                session.commit()
                self.logger.debug(f"Updated car: {existing_car.make} {existing_car.model}")
                return existing_car, False
            
            else:
                # Create new car - filter out fields that don't exist in the model
                valid_fields = {k: v for k, v in car_data.items() if hasattr(Car, k)}
                new_car = Car(**valid_fields)
                session.add(new_car)
                session.flush()  # Get the ID
                
                # Add initial price to history
                price_history = PriceHistory(
                    car_id=new_car.id,
                    price=car_data['price']
                )
                session.add(price_history)
                
                session.commit()
                self.logger.info(f"New car added: {new_car.make} {new_car.model} - €{new_car.price}")
                
                # Check if this is a top match and send email notification
                try:
                    self._check_and_notify_top_match(new_car)
                except Exception as e:
                    self.logger.error(f"Error checking for top match notification: {e}")
                
                return new_car, True
        
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error saving car to database: {e}")
            return None, False
        
        finally:
            session.close()
    
    def _mark_unseen_cars_unavailable(self):
        """
        Mark cars from this website that were not seen in this scrape as unavailable
        
        DISABLED: This function is currently disabled due to scraper reliability issues.
        Scrapers often return incomplete results (e.g., finding only 2-4 cars when 80+ exist),
        which causes false positives where available cars are incorrectly marked as unavailable.
        
        Instead, use the dedicated check_availability.py script to proactively verify
        individual car availability by checking their listing URLs directly.
        
        Safety mechanism: If very few cars were seen (< 5), we don't mark anything unavailable
        to avoid false negatives from scraper issues.
        """
        session = self.db.get_session()
        
        try:
            # Safety check: If we saw very few or no cars, don't mark anything unavailable
            # This prevents false negatives when the scraper has issues
            cars_seen_count = len(self.seen_external_ids)
            
            # DISABLED: Return early to prevent false positives
            # The scrapers are unreliable and often return incomplete results
            # This was causing available cars to be incorrectly marked as unavailable
            self.logger.info(
                f"Availability checking disabled - saw {cars_seen_count} cars but will NOT mark unseen cars as unavailable. "
                f"Use check_availability.py for availability verification instead."
            )
            return 0
            
            # Original logic below (kept for reference but unreachable)
            if cars_seen_count < 5:
                self.logger.warning(
                    f"Only saw {cars_seen_count} cars - skipping availability update to prevent false negatives. "
                    f"This might indicate scraper issues."
                )
                return 0
            
            # Find all cars from this website that are currently marked as available
            # but were not seen in this scrape session
            available_cars = session.query(Car).filter(
                Car.source_website == self.website_name,
                Car.is_available == True
            ).all()
            
            cars_marked_unavailable = 0
            
            for car in available_cars:
                if car.external_id not in self.seen_external_ids:
                    car.mark_unavailable('not_found_in_scrape')
                    cars_marked_unavailable += 1
                    self.logger.info(f"Marked as unavailable: {car.make} {car.model} ({car.year}) - no longer listed")
            
            session.commit()
            
            if cars_marked_unavailable > 0:
                self.logger.info(f"Marked {cars_marked_unavailable} cars as unavailable (from {len(available_cars)} total available)")
            
            return cars_marked_unavailable
            
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error marking unseen cars as unavailable: {e}")
            return 0
        
        finally:
            session.close()
    
    def _log_scraping_session(self, status, cars_found=0, cars_new=0, cars_updated=0, error_message=None):
        """Log scraping session to database"""
        session = self.db.get_session()
        
        try:
            log = ScraperLog(
                website=self.website_name,
                started_at=self.scrape_start_time,
                completed_at=datetime.utcnow(),
                status=status,
                cars_found=cars_found,
                cars_new=cars_new,
                cars_updated=cars_updated,
                error_message=error_message
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Error logging scraping session: {e}")
        finally:
            session.close()
    
    def _check_required_features(self, features: List[str]) -> tuple[int, bool]:
        """
        Check how many critical features are present using fuzzy matching
        
        Args:
            features: List of feature strings from the car listing
            
        Returns:
            Tuple of (count of critical features, all critical features present)
        """
        if not features:
            return 0, False
            
        critical_features = self.config.get('critical_features', [])
        found_features = [f.lower().strip() for f in features if f]
        
        # Define keyword mappings for common variations
        # Synced with utils/helpers.py check_feature_match() for consistency
        feature_keywords = {
            # Critical features
            'adaptive cruise control': [
                'adaptive cruise control', 
                'adaptieve cruise control',
                'adaptieve cruisecontrol',
                'acc',
                'adaptive cruise',
                'adaptief cruise'
            ],
            'android auto': [
                'android auto', 
                'apple carplay', 
                'carplay',
                'smartphone integratie'
            ],
            'navigatiesysteem': [
                'navigatie', 
                'navigatiesysteem', 
                'navigation', 
                'navi', 
                'gps',
                'navigatiesystem'
            ],
            'stuurbekrachtiging': [
                'stuurbekrachtiging', 
                'power steering', 
                'servo'
            ],
            'dab+ radio': [
                'dab+', 
                'dab radio', 
                'digital radio', 
                'dab',
                'digitale radio',
                'digitale radio-ontvangst',
                'dab-radio'
            ],
            'elektrisch bedienbare ramen': [
                'elektrisch bedienbare ramen', 
                'electric windows', 
                'elektrische ramen'
            ],
            'achteruitrijcamera': [
                'achteruitrijcamera', 
                'rear camera', 
                'camera', 
                'reversing camera', 
                'parkeerhulp met camera',
                'achteruit camera',
                'achteruitrij camera',
                'rear view camera',
                'backup camera',
                'rearview camera'
            ],
            'climate control': [
                'climate control', 
                'climatronic', 
                'airco', 
                'climate',
                'airconditioning',
                'dual climate',
                'multi-zone climate'
            ],
            'hill hold': [
                'hill hold', 
                'hill-hold', 
                'hill start', 
                'heuvelstart', 
                'bergstart',
                'hill start assist',
                'heuvelstarthulp'
            ],
            'lane assist': [
                'lane assist', 
                'lane keeping', 
                'lka', 
                'lane departure',
                'lane departure warning',
                'lane keeping assist',
                'rijstrookassistent',
                'rijstrook assistent',
                'lane departure warning systeem',
                'ldws'
            ],
            'park assist': [
                'park assist', 
                'parkeerhulp', 
                'parking assist', 
                'parking sensors', 
                'parkeersensoren',
                'parkeer hulp',
                'parking aid',
                'parkeersensor',
                'inparkeer hulp',
                'inparkeerhulp'
            ],
            'trekhaak': [
                'trekhaak', 
                'tow hitch', 
                'towbar', 
                'tow bar',
                'trek haak',
                'towing hitch',
                'anhängerkupplung'
            ],
            # Nice-to-have features
            'dodehoekdetectie': [
                'dodehoekdetectie', 
                'blind spot', 
                'blis', 
                'dode hoek',
                'dode hoek detectie',
                'blind spot detection',
                'blind spot monitor'
            ],
            'led koplampen': [
                'led koplampen', 
                'led headlight', 
                'led verlichting',
                'led-koplampen',
                'led koplamp',
                'led headlights'
            ],
            'stoelverwarming': [
                'stoelverwarming', 
                'heated seat', 
                'stoel verwarming',
                'verwarmde stoelen',
                'heated seats',
                'seat heating'
            ],
            'leren bekleding': [
                'leren bekleding', 
                'leather', 
                'leer',
                'lederen bekleding',
                'leather interior',
                'leather seats'
            ],
            'stuurverwarming': [
                'stuurverwarming', 
                'heated steering', 
                'stuur verwarming',
                'stuurwielverwarming',
                'stuurwiel verwarming',
                'verwarmde stuur',
                'verwarmde stuurwiel',
                'heated steering wheel'
            ],
            'keyless entry': [
                'keyless entry', 
                'keyless go', 
                'keyless',
                'keyless start',
                'start/stop knop',
                'keyless access'
            ]
        }
        
        matching_count = 0
        for required in critical_features:
            required_lower = required.lower().strip()
            
            # Check for exact match first
            if required_lower in found_features:
                matching_count += 1
                continue
            
            # Check for partial match using keywords
            keywords = feature_keywords.get(required_lower, [required_lower])
            for feature in found_features:
                if any(keyword in feature for keyword in keywords):
                    matching_count += 1
                    break
        
        has_all = matching_count == len(critical_features)
        return matching_count, has_all
    
    def _calculate_car_score(self, car) -> float:
        """
        Calculate a score for a car based on critical features, price, odometer, range, and age.
        Lower score = better match
        
        Scoring weights:
        - Critical Features: 50% (missing features increase score)
        - Price: 20% (lower is better)
        - Odometer: 15% (lower is better)
        - Age: 10% (newer is better)
        - Range: 5% (higher is better)
        
        CONTENDER BONUSES:
        - Full Electric SUV with 500+ km range: -10 points
        - PHEV/Hybrid with 100+ km electric range: -5 points
        - Has trekhaak: -5 points
        """
        score = 0.0
        
        # CRITICAL FEATURES (50% weight)
        critical_features_list = self.config.get('critical_features', [])
        if critical_features_list:
            features_count, has_all = self._check_required_features(
                car.features if isinstance(car.features, list) else []
            )
            missing_count = len(critical_features_list) - features_count
            features_score = (missing_count / len(critical_features_list)) * 100
            score += features_score * 0.5
        else:
            score += 50 * 0.5
        
        # Check for trekhaak
        has_trekhaak = False
        if car.features:
            car_features_str = ' '.join(car.features).lower() if isinstance(car.features, list) else str(car.features).lower()
            has_trekhaak = any(keyword in car_features_str for keyword in ['trekhaak', 'tow hitch', 'towbar', 'tow bar'])
        
        # Price score (normalize to 0-100 scale, max price = 50000)
        if car.price:
            max_price = 50000
            price_score = min((car.price / max_price) * 100, 100)
            score += price_score * 0.2
        else:
            score += 100 * 0.2
        
        # Odometer score (normalize to 0-100 scale, max mileage = 150000)
        if car.mileage_km:
            max_odometer = 150000
            odometer_score = min((car.mileage_km / max_odometer) * 100, 100)
            score += odometer_score * 0.15
        else:
            score += 100 * 0.15
        
        # Age score (normalize to 0-100 scale, reference year = 2025, max age = 10 years)
        if car.year:
            current_year = 2025
            age = current_year - car.year
            max_age = 10
            age_score = min((age / max_age) * 100, 100)
            score += age_score * 0.1
        else:
            score += 100 * 0.1
        
        # Range score (normalize to 0-100 scale, higher is better, max range = 600km)
        # Use ad_listed_range_km (new field), fallback to electric_range_km (legacy)
        range_km = getattr(car, 'ad_listed_range_km', None) or car.electric_range_km
        if range_km:
            max_range = 600
            # Invert the score so higher range = lower score
            range_score = max(0, 100 - min((range_km / max_range) * 100, 100))
            score += range_score * 0.05
        else:
            score += 30 * 0.05  # Small penalty for missing range (assume decent 400km)
        
        # CONTENDER BONUSES
        vehicle_type_str = str(car.vehicle_type).upper() if car.vehicle_type else ''
        is_suv = 'SUV' in vehicle_type_str
        is_stationwagon = 'STATIONWAGON' in vehicle_type_str or 'STATION' in vehicle_type_str
        is_full_electric = car.fuel_type == 'Full Electric'
        is_phev_or_hybrid = car.fuel_type in ['PHEV', 'Hybrid']
        
        # BONUS 1: Full Electric SUV with 500+ km range
        if is_full_electric and is_suv and range_km and range_km >= 500:
            score -= 10
        
        # BONUS 2: PHEV/Hybrid with 100+ km electric range
        if is_phev_or_hybrid and range_km and range_km >= 100:
            score -= 5
        
        # BONUS 3: SUV or Station Wagon body style
        if is_suv or is_stationwagon:
            score -= 5
        
        # BONUS 4: Preferred cars
        preferred_config = self.config.get('preferred_cars', {})
        if preferred_config:
            preferred_makes = [m.lower() for m in preferred_config.get('makes', [])]
            preferred_models = [m.lower() for m in preferred_config.get('models', [])]
            
            car_make_lower = str(car.make).lower() if car.make else ''
            car_model_lower = str(car.model).lower() if car.model else ''
            
            is_preferred_make = any(pm in car_make_lower for pm in preferred_makes)
            is_preferred_model = any(pm in car_model_lower for pm in preferred_models)
            
            if is_preferred_make or is_preferred_model:
                score -= 15
            
            # Auto-prefer station wagons with 100+ km range
            auto_prefer_wagons_min_range = preferred_config.get('auto_prefer_wagons_min_range', 100)
            if is_stationwagon and range_km and range_km >= auto_prefer_wagons_min_range:
                score -= 10
        
        # Nice-to-have bonus: Trekhaak
        if has_trekhaak:
            score -= 5
        
        return score
    
    def _check_and_notify_top_match(self, car):
        """
        Check if a new car is a top match and send email notification
        
        Args:
            car: The Car object to check
        """
        # Skip if email notifier is not available
        if not self.email_notifier:
            return
        
        # Skip if email notifications are disabled
        notifications_config = self.config.get('notifications', {}).get('email', {})
        if not notifications_config.get('enabled', False):
            return
        
        if not notifications_config.get('notify_on_top_match', False):
            return
        
        # Calculate score
        score = self._calculate_car_score(car)
        
        # Get threshold from config
        min_score = notifications_config.get('min_score_for_notification', 85)
        
        # Check if score meets threshold (note: lower score = better match, so we use <=)
        # Actually, looking at the scoring logic, higher scores are worse, so we need >= for notification
        # Wait, I need to clarify: the score represents penalty points, so LOWER is better
        # But the config says "min_score_for_notification: 85", which implies >= 85 should notify
        # This is confusing. Let me check the app.py logic...
        
        # From app.py, I can see that lower score = better match
        # So "min_score_for_notification: 85" likely means "notify if score is AT MOST 85"
        # But that doesn't make semantic sense with "min_score"...
        # Let me interpret it as: notify if score is good enough (low enough) - so score <= threshold
        
        if score <= min_score:
            try:
                # Build car details dict
                car_details = {
                    'make': car.make,
                    'model': car.model,
                    'year': car.year,
                    'price': car.price,
                    'mileage_km': car.mileage_km,
                    'fuel_type': car.fuel_type,
                    'vehicle_type': car.vehicle_type,
                    'electric_range_km': car.electric_range_km,
                    'url': car.listing_url,
                    'location': f"{car.location_city}, {car.location_province}" if car.location_city and car.location_province else (car.location_city or car.location_province or 'Unknown'),
                    'distance_from_heerenveen_km': car.distance_from_heerenveen_km,
                    'source_website': car.source_website
                }
                
                self.email_notifier.send_top_match_notification(car_details, score)
                self.logger.info(f"Sent top match notification for {car.make} {car.model} (score: {score:.1f})")
            except Exception as e:
                self.logger.error(f"Failed to send top match notification: {e}")
    
    @abstractmethod
    def build_search_url(self) -> List[str]:
        """
        Build search URL(s) for the website based on config criteria
        
        Returns:
            List of URLs to scrape
        """
        pass
    
    @abstractmethod
    def parse_listing_page(self, url: str) -> List[Dict]:
        """
        Parse a listing page and extract car data
        
        Args:
            url: URL of the listing page
            
        Returns:
            List of dictionaries containing car data
        """
        pass
    
    @abstractmethod
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """
        Parse detailed car information from individual listing page
        
        Args:
            car_summary: Basic car info from listing page
            
        Returns:
            Complete car data dictionary
        """
        pass
    
    def run(self):
        """Main scraping execution method"""
        self.scrape_start_time = datetime.utcnow()
        cars_found = 0
        cars_new = 0
        cars_updated = 0
        
        try:
            self.logger.info(f"Starting scrape for {self.website_name}")
            
            # Initialize driver
            self._init_driver()
            
            # Build search URLs
            urls = self.build_search_url()
            self.logger.info(f"Built {len(urls)} search URLs")
            
            # Process each URL
            for url in urls:
                # Check shutdown before processing URL
                if self._is_shutdown_requested():
                    self.logger.info("*** SHUTDOWN: Shutdown requested, stopping URL processing ***")
                    break
                
                self.logger.info(f"Processing URL: {url}")
                
                try:
                    # Get car listings from page
                    car_summaries = self.parse_listing_page(url)
                    self.logger.info(f"Found {len(car_summaries)} cars on page")
                    
                    for car_summary in car_summaries:
                        # Check shutdown before processing each car
                        if self._is_shutdown_requested():
                            self.logger.info("*** SHUTDOWN: Shutdown requested, stopping car processing ***")
                            break
                        try:
                            # Get detailed information
                            car_data = self.parse_car_detail(car_summary)
                            
                            if car_data:
                                # Skip hydrogen fuel cell vehicles
                                fuel_type = car_data.get('fuel_type', '')
                                # DEBUG: Log fuel_type for Austral cars specifically
                                if "austral" in str(car_data.get("model", "")).lower():
                                    self.logger.info(f"DEBUG AUSTRAL: fuel_type='{fuel_type}' (len={len(fuel_type)}, repr={repr(fuel_type)}) for {car_data.get('make')} {car_data.get('model')}")

                                if fuel_type and fuel_type.lower() in ['hydrogen', 'waterstof']:
                                    self.logger.info(f"Skipping hydrogen vehicle: {car_data.get('make')} {car_data.get('model')}")
                                    continue
                                
                                # Skip benzine/diesel/gasoline vehicles (defense in depth)
                                contains_fuel_terms = fuel_type and any(term in fuel_type.lower() for term in ["benzine", "gasoline", "petrol", "diesel"])
                                is_not_hybrid_phev = fuel_type.lower() not in ["phev", "hybrid"]
                                should_skip = contains_fuel_terms and is_not_hybrid_phev
                                
                                # DEBUG: Log decision logic for Austral cars
                                if "austral" in str(car_data.get("model", "")).lower():
                                    self.logger.info(f"DEBUG AUSTRAL SKIP LOGIC: contains_fuel_terms={contains_fuel_terms}, is_not_hybrid_phev={is_not_hybrid_phev}, should_skip={should_skip}")

                                # These should already be filtered by normalize_fuel_type(), but double-check
                                if should_skip:
                                    self.logger.info(f"Skipping benzine/diesel car: {car_data.get('make')} {car_data.get('model')} (fuel_type: {fuel_type})")
                                    continue
                                
                                # Check required features
                                features_count, has_all = self._check_required_features(
                                    car_data.get('features', [])
                                )
                                car_data['features_count'] = features_count
                                car_data['has_all_required_features'] = has_all
                                
                                # Save to database
                                car, is_new = self._save_car_to_db(car_data)
                                
                                if car:
                                    cars_found += 1
                                    if is_new:
                                        cars_new += 1
                                    else:
                                        cars_updated += 1
                            
                            # Random delay between cars
                            self._random_delay(
                                self.config['scraping']['rate_limit']['request_delay_seconds'],
                                self.config['scraping']['rate_limit']['request_delay_seconds'] + 1
                            )
                        
                        except Exception as e:
                            self.logger.error(f"Error processing car: {e}")
                            if self.config['scraping']['browser']['screenshot_on_error']:
                                self._take_screenshot('car_error')
                            continue
                
                except Exception as e:
                    self.logger.error(f"Error processing URL {url}: {e}")
                    if self.config['scraping']['browser']['screenshot_on_error']:
                        self._take_screenshot('page_error')
                    continue
            
            # Mark cars that were not seen in this scrape as unavailable
            cars_unavailable = self._mark_unseen_cars_unavailable()
            
            # Log success
            self._log_scraping_session('success', cars_found, cars_new, cars_updated)
            self.logger.info(f"Scraping completed: {cars_found} cars found ({cars_new} new, {cars_updated} updated, {cars_unavailable} marked unavailable)")
        
        except Exception as e:
            self.logger.error(f"Scraping failed: {e}")
            self._log_scraping_session('error', cars_found, cars_new, cars_updated, str(e))
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('fatal_error')
        
        finally:
            self._close_driver()
