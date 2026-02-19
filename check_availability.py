#!/usr/bin/env python3
"""
Proactive Car Availability Checker

This script checks if cars in the database are still available on their source websites.
It detects unavailable cars by looking for specific indicators on each website.
When a car is found unavailable on AutoScout24, it scrapes alternative cars suggested by the site.

Usage:
    python check_availability.py [--all] [--older-than DAYS] [--website WEBSITE]
    
Examples:
    python check_availability.py --older-than 7    # Check cars not seen in 7 days
    python check_availability.py --website autoscout24.nl
    python check_availability.py --all             # Check all available cars
"""

import argparse
import sys
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import time
import logging

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from models.database import Database, Car
from scrapers.autoscout24_scraper import AutoScout24Scraper
from sqlalchemy import or_
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import yaml
from bs4 import BeautifulSoup
from PIL import Image
import pytesseract
import io
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)



def is_legitimate_autoscout24_redirect(original_url, current_url):
    """Check if redirect is legitimate URL canonicalization vs unavailability"""
    from urllib.parse import urlparse
    import re
    
    # Parse URLs
    original_parsed = urlparse(original_url)
    current_parsed = urlparse(current_url)
    
    # Must be same domain
    if original_parsed.netloc != current_parsed.netloc:
        return False
    
    # Extract UUID pattern (8-4-4-4-12 format)
    uuid_pattern = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    original_uuid_match = re.search(uuid_pattern, original_url, re.IGNORECASE)
    current_uuid_match = re.search(uuid_pattern, current_url, re.IGNORECASE)
    
    # Both URLs should have matching UUIDs
    if not original_uuid_match or not current_uuid_match:
        return False
    if original_uuid_match.group(1).lower() != current_uuid_match.group(1).lower():
        return False
    
    # Check if current URL looks like search page (indicates unavailability)
    if "/lst/" in current_url or "/zoeken/" in current_url:
        return False
    
    return True


class AvailabilityChecker:
    """Check car availability across different websites"""
    
    def __init__(self, db_path='data/cars.db', config_path='config.yaml', headless=True, scrape_alternatives=True):
        self.db = Database(db_path)
        self.db_path = db_path
        self.config_path = config_path
        self.headless = headless
        self.driver = None
        self.scrape_alternatives = scrape_alternatives
        self.autoscout24_scraper = None
        
        # Load config to check preferred cars
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Unavailability indicators for each website
        self.unavailable_indicators = {
            'autoscout24.nl': [
                'niet meer beschikbaar',
                'toon alternatieven',
                'no longer available',
                'bestaat helaas niet meer',
                'show alternatives'
            ],
            'autotrack.nl': [
                'deze auto is niet meer beschikbaar',
                'advertentie is verwijderd',
                'niet gevonden',
                'page not found'
            ],
            'gaspedaal.nl': [
                'niet meer beschikbaar',
                'advertentie is verwijderd',
                'niet gevonden'
            ],
            'vandenbrug.nl': [
                'pagina kan niet worden gevonden',
                'deze pagina kan niet worden gevonden',
                'bestaat helaas niet meer',
                'de auto is verkocht',
                'oeps, deze pagina kan niet worden gevonden'
            ]
        }
        
        # Banner text patterns to detect (case-insensitive)
        self.banner_patterns = [
            'verkocht',      # Dutch: sold
            'sold',          # English
            'verkauft',      # German
            'vendu',         # French
            'venduto',       # Italian
            'reserved',      # Reserved
            'gereserveerd',  # Dutch: reserved
        ]
        
        # Cookie files for each website
        self.cookies_files = {
            'autotrack.nl': 'cookies/autotrack_cookies.json'
        }
        
        # Track which websites have had cookies loaded
        self.cookies_loaded = set()
    
    def _init_driver(self):
        """Initialize Selenium WebDriver"""
        if self.driver:
            return
        
        options = Options()
        if self.headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
        
        self.driver = webdriver.Chrome(options=options)
        logger.info("WebDriver initialized")
    
    def _close_driver(self):
        """Close WebDriver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("WebDriver closed")
    
    def load_cookies(self, website):
        """Load cookies from file to bypass privacy gates
        
        Args:
            website: Website domain (e.g., 'autotrack.nl')
            
        Returns:
            bool: True if cookies loaded successfully, False otherwise
        """
        if website in self.cookies_loaded:
            logger.debug(f"Cookies already loaded for {website}")
            return True
            
        if website not in self.cookies_files:
            logger.debug(f"No cookie file configured for {website}")
            return False
            
        cookies_file = self.cookies_files[website]
        if not os.path.exists(cookies_file):
            logger.warning(f"Cookie file not found: {cookies_file}")
            return False
        
        try:
            # Navigate to robots.txt first to avoid privacy gate redirect
            # This gets us on the correct domain without triggering redirects
            robots_url = f"https://www.{website}/robots.txt"
            logger.info(f"Loading cookies for {website}...")
            self.driver.get(robots_url)
            time.sleep(2)
            
            # Load cookies from file
            with open(cookies_file, 'r') as f:
                cookies = json.load(f)
            
            # Add each cookie to the browser
            successful_cookies = 0
            for cookie in cookies:
                try:
                    # Remove fields that Selenium doesn't accept
                    if 'sameSite' in cookie:
                        del cookie['sameSite']
                    if 'storeId' in cookie:
                        del cookie['storeId']
                    
                    self.driver.add_cookie(cookie)
                    successful_cookies += 1
                except Exception as e:
                    logger.debug(f"Could not add cookie {cookie.get('name')}: {e}")
            
            logger.info(f"Loaded {successful_cookies}/{len(cookies)} cookies for {website}")
            self.cookies_loaded.add(website)
            return True
            
        except Exception as e:
            logger.error(f"Error loading cookies for {website}: {e}")
            return False
    
    def _detect_banner_text_in_images(self):
        """
        Detect VERKOCHT/SOLD banner text in listing images using OCR
        
        Returns:
            tuple: (has_banner: bool, detected_text: str or None)
        """
        try:
            # Find all images on the page
            images = self.driver.find_elements(By.TAG_NAME, 'img')
            
            if not images:
                logger.debug(f"    No images found on page")
                return (False, None)
            
            # Check the first few images (usually main listing photos)
            images_to_check = images[:5]  # Check first 5 images
            logger.debug(f"    Checking {len(images_to_check)} images for banners...")
            
            for idx, img_element in enumerate(images_to_check):
                try:
                    # Get image URL
                    img_url = img_element.get_attribute('src')
                    
                    if not img_url or img_url.startswith('data:'):
                        logger.debug(f"      Image {idx + 1}: Skipping (no URL or data URL)")
                        continue
                    
                    logger.debug(f"      Image {idx + 1}: Running OCR...")
                    # Take screenshot of the image element
                    screenshot = img_element.screenshot_as_png
                    image = Image.open(io.BytesIO(screenshot))
                    
                    # Convert to grayscale for better OCR
                    image = image.convert('L')
                    
                    # Perform OCR
                    text = pytesseract.image_to_string(image).lower()
                    logger.debug(f"      Image {idx + 1}: OCR completed, text length: {len(text)}")
                    if text.strip():
                        logger.debug(f"        OCR text: '{text.strip()}'")
                    
                    # Check for banner patterns
                    for pattern in self.banner_patterns:
                        if pattern in text:
                            logger.info(f"  🔍 Detected '{pattern.upper()}' banner in image {idx + 1}")
                            return (True, pattern)
                
                except Exception as e:
                    # Skip this image if there's an error
                    logger.debug(f"      Image {idx + 1}: Error checking - {e}")
                    continue
            
            logger.debug(f"    Banner check complete: No banners found")
            return (False, None)
            
        except Exception as e:
            logger.debug(f"  - Error in banner detection: {e}")
            return (False, None)
    
    def check_car_availability(self, car, recheck_mode=False):
        """
        Check if a single car is still available
        
        Args:
            car: Car object to check
            recheck_mode: If True, checking an unavailable car to see if it's available again
        
        Returns:
            True if available, False if not available, None if couldn't determine
        """
        try:
            # Validate listing_url before attempting to load
            if not car.listing_url or car.listing_url.strip() in ['', '...', 'None']:
                logger.warning(f"  ⚠️  SKIPPING: Car has invalid or missing listing_url: '{car.listing_url}'")
                return None
            
            # Initialize driver if not already done
            if not self.driver:
                self._init_driver()
            
            # Get the page
            logger.debug(f"  Loading URL: {car.listing_url}")
            self.driver.get(car.listing_url)
            time.sleep(2)  # Wait for page to load
            
            # Get page source and parse with BeautifulSoup
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Remove script and style tags to avoid false positives from:
            # - JavaScript translation strings (e.g., "detailpage.gonePage.title":"Dit voertuig is helaas niet meer beschikbaar.")
            # - Embedded JSON data
            # - CSS content
            for element in soup.find_all(['script', 'style']):
                element.decompose()
            
            # Get visible text only (lowercase for case-insensitive matching)
            visible_text = soup.get_text().lower()
            
            # Check for unavailability indicators in visible text only
            indicators = self.unavailable_indicators.get(car.source_website, [])
            logger.debug(f"  Checking text indicators for website: {car.source_website}")
            
            for indicator in indicators:
                if indicator.lower() in visible_text:
                    if recheck_mode:
                        logger.info(f"  ❌ STILL UNAVAILABLE: Found indicator '{indicator}' in visible content")
                    else:
                        logger.info(f"  ❌ UNAVAILABLE: Found indicator '{indicator}' in visible content")
                    return (False, 'website_shows_unavailable')
            
            logger.debug(f"  ✓ No text indicators found")
            
            # Check for VERKOCHT/SOLD banner in images (especially for AutoScout24)
            if car.source_website == 'autoscout24.nl':
                logger.debug(f"  🔍 Running banner detection on images...")
                has_banner, banner_text = self._detect_banner_text_in_images()
                if has_banner:
                    if recheck_mode:
                        logger.info(f"  ❌ STILL UNAVAILABLE: Found '{banner_text.upper()}' banner in listing images")
                    else:
                        logger.info(f"  ❌ UNAVAILABLE: Found '{banner_text.upper()}' banner in listing images")
                    return (False, 'banner_shows_sold')
                else:
                    logger.debug(f"  ✓ No banner detected in images")
            
            # Check HTTP status (if we got redirected or error page)
            current_url = self.driver.current_url
            if current_url != car.listing_url:
                # Check if this is a privacy gate redirect (not an unavailability indicator)
                is_privacy_gate = 'myprivacy.dpgmedia.nl' in current_url or 'privacygate' in current_url.lower()
                
                if is_privacy_gate:
                    # This is a privacy/consent page, not an unavailability indicator
                    logger.info(f"  🔒 Privacy gate detected, loading cookies and retrying...")
                    
                    # Extract website domain from original URL
                    from urllib.parse import urlparse
                    parsed_url = urlparse(car.listing_url)
                    website = parsed_url.netloc.replace('www.', '')
                    
                    # Try loading cookies and retrying
                    if self.load_cookies(website):
                        logger.info(f"  🔄 Retrying with cookies loaded...")
                        self.driver.get(car.listing_url)
                        time.sleep(3)
                        
                        # Check the new URL after retry
                        retry_url = self.driver.current_url
                        if retry_url == car.listing_url:
                            logger.info(f"  ✅ Successfully bypassed privacy gate")
                            # Continue with normal availability checks below
                            current_url = retry_url
                        else:
                            # Still redirected after loading cookies - now it's really unavailable
                            if recheck_mode:
                                logger.info(f"  ❌ STILL UNAVAILABLE: Redirected even after loading cookies to {retry_url}")
                            else:
                                logger.info(f"  ❌ UNAVAILABLE: Redirected even after loading cookies to {retry_url}")
                            return (False, 'http_error')
                    else:
                        logger.warning(f"  ⚠️  Could not load cookies, treating as unavailable")
                        return (False, 'http_error')
                
                # Check if this is legitimate AutoScout24 URL canonicalization
                if car.source_website == 'autoscout24.nl' and is_legitimate_autoscout24_redirect(car.listing_url, current_url):
                    logger.info(f"  ✅ Legitimate URL canonicalization: {car.listing_url} -> {current_url}")
                    # Update stored URL for future checks but continue availability checks
                    car.listing_url = current_url
                else:
                    # This is a real redirect indicating unavailability
                    if recheck_mode:
                        logger.info(f"  ❌ STILL UNAVAILABLE: Redirected from {car.listing_url} to {current_url}")
                    else:
                        logger.info(f"  ❌ UNAVAILABLE: Redirected from {car.listing_url} to {current_url}")
                    return (False, 'http_error')
            
            # If we got here, car appears available
            if recheck_mode:
                logger.info(f"  ✅ NOW AVAILABLE AGAIN!")
            else:
                logger.info(f"  ✅ AVAILABLE")
            return (True, None)
            
        except Exception as e:
            logger.error(f"  ⚠️  ERROR checking availability: {e}")
            return None
    
    def _is_preferred_car(self, car):
        """Check if a car matches preferred makes/models from config"""
        preferred_makes = [m.lower() for m in self.config.get('preferences', {}).get('preferred_makes', [])]
        preferred_models = [m.lower() for m in self.config.get('preferences', {}).get('preferred_models', [])]
        
        car_make = car.make.lower() if car.make else ''
        car_model = car.model.lower() if car.model else ''
        
        return car_make in preferred_makes or car_model in preferred_models
    
    def _scrape_and_save_alternatives(self, car):
        """Scrape alternative cars from AutoScout24 and save to database"""
        if car.source_website != 'autoscout24.nl':
            logger.debug("  - Skipping alternatives (not AutoScout24)")
            return 0
        
        if not self.scrape_alternatives:
            logger.debug("  - Alternatives scraping disabled")
            return 0
        
        try:
            # Initialize AutoScout24 scraper if needed
            if not self.autoscout24_scraper:
                self.autoscout24_scraper = AutoScout24Scraper(
                    config_path=self.config_path,
                    db_path=self.db_path
                )
                # Use the same driver as availability checker
                self.autoscout24_scraper.driver = self.driver
            
            logger.info(f"  🔍 Scraping alternatives for {car.year} {car.make} {car.model}")
            
            # Scrape alternatives
            alternatives = self.autoscout24_scraper.scrape_alternatives(car.listing_url)
            
            if not alternatives:
                logger.info("  - No alternatives found")
                return 0
            
            # Process and save alternatives
            saved_count = 0
            session = self.db.get_session()
            
            try:
                for alt_summary in alternatives:
                    # Parse full details for each alternative
                    logger.info(f"  📋 Processing alternative: {alt_summary.get('make')} {alt_summary.get('model')}")
                    
                    alt_data = self.autoscout24_scraper.parse_car_detail(alt_summary)
                    
                    if not alt_data:
                        continue
                    
                    # Check if car already exists
                    existing_car = session.query(Car).filter(
                        Car.external_id == alt_data['external_id']
                    ).first()
                    
                    if existing_car:
                        logger.info(f"  - Alternative already exists in database")
                        continue
                    
                    # Save new alternative car
                    new_car = Car.from_dict(alt_data)
                    session.add(new_car)
                    saved_count += 1
                    logger.info(f"  ✅ Saved alternative: {new_car.make} {new_car.model} - €{new_car.price}")
                
                session.commit()
                
                if saved_count > 0:
                    is_preferred = self._is_preferred_car(car)
                    logger.info(f"  🎉 Saved {saved_count} new alternative(s) {' (PREFERRED CAR!)' if is_preferred else ''}")
                
                return saved_count
            
            except Exception as e:
                session.rollback()
                logger.error(f"  ⚠️  Error saving alternatives: {e}")
                return 0
            finally:
                session.close()
        
        except Exception as e:
            logger.error(f"  ⚠️  Error scraping alternatives: {e}")
            return 0
    
    def check_and_update_availability(self, filters=None):
        """
        Check availability for cars matching filters and update database
        
        Args:
            filters: Dict with optional filters:
                - older_than_days: Check cars not seen in N days
                - website: Only check specific website
                - limit: Max number of cars to check
                - all: Check all available cars
        """
        session = self.db.get_session()
        
        try:
            # Build query
            query = session.query(Car).filter(Car.is_available == True)
            
            if filters:
                # Filter by website
                if filters.get('website'):
                    query = query.filter(Car.source_website == filters['website'])
                
                # Filter by age
                if filters.get('older_than_days'):
                    cutoff_date = datetime.utcnow() - timedelta(days=filters['older_than_days'])
                    query = query.filter(Car.last_seen < cutoff_date)
                
                # Limit
                if filters.get('limit'):
                    query = query.limit(filters['limit'])
            
            # Get cars to check
            cars = query.all()
            
            if not cars:
                logger.info("No cars match the filters")
                return {"cars_checked": 0, "cars_marked_unavailable": 0, "still_available": 0, "errors": 0}
                return
            
            logger.info(f"\n{'='*60}")
            logger.info(f"CHECKING AVAILABILITY FOR {len(cars)} CARS")
            logger.info(f"{'='*60}\n")
            
            # Initialize browser
            self._init_driver()
            
            # Check each car
            checked = 0
            marked_unavailable = 0
            still_available = 0
            errors = 0
            total_alternatives_found = 0
            
            for i, car in enumerate(cars, 1):
                logger.info(f"\n[{i}/{len(cars)}] Checking: {car.year} {car.make} {car.model}")
                logger.info(f"  Website: {car.source_website}")
                logger.info(f"  Last seen: {car.last_seen}")
                logger.info(f"  URL: {car.listing_url[:80]}...")
                
                result = self.check_car_availability(car)
                
                if result is None:
                    errors += 1
                else:
                    is_available, reason = result
                    
                    if is_available is False:
                        # Mark as unavailable with reason
                        car.mark_unavailable(reason)
                        marked_unavailable += 1
                        logger.info(f"  ➡️  Marked as UNAVAILABLE in database (reason: {reason})")
                        
                        # Commit immediately after marking unavailable
                        session.commit()
                        
                        # Scrape alternatives for AutoScout24 listings
                        alternatives_count = self._scrape_and_save_alternatives(car)
                        total_alternatives_found += alternatives_count
                        
                    elif is_available is True:
                        still_available += 1
                
                checked += 1
                
                # Small delay between requests
                time.sleep(1)
            
            # Final commit for any remaining changes
            session.commit()
            
            # Print summary
            logger.info(f"\n{'='*60}")
            logger.info(f"SUMMARY")
            logger.info(f"{'='*60}")
            logger.info(f"Total checked: {checked}")
            logger.info(f"Still available: {still_available}")
            logger.info(f"Marked unavailable: {marked_unavailable}")
            logger.info(f"Alternative cars found: {total_alternatives_found}")
            logger.info(f"Errors: {errors}")
            logger.info(f"{'='*60}\n")

            # Return stats for the caller
            return {
                'cars_checked': checked,
                'cars_marked_unavailable': marked_unavailable,
                'still_available': still_available,
                'errors': errors
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error during availability check: {e}")
            raise
        
        finally:
            session.close()
            self._close_driver()
    
    def check_unavailable_cars(self, filters=None):
        """
        Recheck cars marked as unavailable to see if they're available again
        
        Args:
            filters: Dict with optional filters:
                - only_verified: Only check cars with verified unavailability reasons
                  (website_shows_unavailable or http_error), not just 'not_found_in_scrape'
                - limit: Max number of cars to check
        
        Returns:
            Dict with stats: {
                'cars_checked': int,
                'cars_remarked_available': int,
                'still_unavailable': int,
                'errors': int
            }
        """
        session = self.db.get_session()
        
        try:
            # Build query for unavailable cars
            query = session.query(Car).filter(Car.is_available == False)
            
            if filters:
                # Filter by verified reasons only
                if filters.get('only_verified'):
                    query = query.filter(
                        or_(
                            Car.unavailable_reason == 'website_shows_unavailable',
                            Car.unavailable_reason == 'http_error'
                        )
                    )
                
                # Limit
                if filters.get('limit'):
                    query = query.limit(filters['limit'])
            
            # Get cars to recheck
            cars = query.all()
            
            if not cars:
                logger.info("No unavailable cars match the filters")
                return {
                    'cars_checked': 0,
                    'cars_remarked_available': 0,
                    'still_unavailable': 0,
                    'errors': 0
                }
            
            logger.info(f"\n{'='*60}")
            logger.info(f"RECHECKING UNAVAILABLE CARS: {len(cars)} CARS")
            logger.info(f"{'='*60}\n")
            
            # Initialize browser
            self._init_driver()
            
            # Check each car
            checked = 0
            remarked_available = 0
            still_unavailable = 0
            errors = 0
            
            for i, car in enumerate(cars, 1):
                logger.info(f"\n[{i}/{len(cars)}] Rechecking: {car.year} {car.make} {car.model}")
                logger.info(f"  Website: {car.source_website}")
                logger.info(f"  Marked unavailable: {car.marked_unavailable_at}")
                logger.info(f"  Reason: {car.unavailable_reason}")
                logger.info(f"  URL: {car.listing_url[:80]}...")
                
                result = self.check_car_availability(car, recheck_mode=True)
                
                if result is None:
                    errors += 1
                else:
                    is_available, reason = result
                    
                    if is_available is True:
                        # Mark as available again!
                        car.mark_available()
                        car.last_seen = datetime.utcnow()  # Update last_seen
                        remarked_available += 1
                        logger.info(f"  ➡️  Marked as AVAILABLE in database")
                        
                    elif is_available is False:
                        still_unavailable += 1
                
                checked += 1
                
                # Small delay between requests
                time.sleep(1)
            
            # Commit changes
            session.commit()
            
            # Print summary
            logger.info(f"\n{'='*60}")
            logger.info(f"RECHECK SUMMARY")
            logger.info(f"{'='*60}")
            logger.info(f"Total rechecked: {checked}")
            logger.info(f"Remarked as available: {remarked_available}")
            logger.info(f"Still unavailable: {still_unavailable}")
            logger.info(f"Errors: {errors}")
            logger.info(f"{'='*60}\n")
            
            return {
                'cars_checked': checked,
                'cars_remarked_available': remarked_available,
                'still_unavailable': still_unavailable,
                'errors': errors
            }
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error during unavailable cars recheck: {e}")
            raise
        
        finally:
            session.close()
            self._close_driver()


def main():
    parser = argparse.ArgumentParser(description='Check car availability and update database')
    parser.add_argument('--all', action='store_true', help='Check all available cars')
    parser.add_argument('--older-than', type=int, metavar='DAYS', help='Check cars not seen in N days')
    parser.add_argument('--website', type=str, help='Only check specific website')
    parser.add_argument('--limit', type=int, help='Max number of cars to check')
    parser.add_argument('--visible', action='store_true', help='Show browser (not headless)')
    parser.add_argument('--no-alternatives', action='store_true', help='Skip scraping alternatives for unavailable cars')
    
    args = parser.parse_args()
    
    # Build filters
    filters = {}
    
    if args.older_than:
        filters['older_than_days'] = args.older_than
    
    if args.website:
        filters['website'] = args.website
    
    if args.limit:
        filters['limit'] = args.limit
    
    if args.all:
        filters['all'] = True
    
    # Validate: need at least one filter
    if not filters:
        logger.error("Please specify at least one filter: --all, --older-than, --website, or --limit")
        parser.print_help()
        sys.exit(1)
    
    # Run checker
    checker = AvailabilityChecker(
        headless=not args.visible,
        scrape_alternatives=not args.no_alternatives
    )
    checker.check_and_update_availability(filters)


if __name__ == "__main__":
    main()
