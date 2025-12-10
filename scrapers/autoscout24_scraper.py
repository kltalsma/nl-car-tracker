"""
AutoScout24.nl scraper for NL Car Tracker
"""
from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from typing import List, Dict
from utils.helpers import (
    normalize_fuel_type,
    normalize_vehicle_type,
    normalize_model_name,
    extract_number,
    extract_price,
    calculate_distance_from_heerenveen,
    get_coordinates,
    should_exclude_vehicle,
    get_wltp_range,
    extract_city_from_address
)
import time
import re


class AutoScout24Scraper(BaseScraper):
    """Scraper for autoscout24.nl"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        super().__init__(config_path, db_path)
        self.website_name = "autoscout24.nl"
        self.base_url = "https://www.autoscout24.nl"
    
    def build_search_url(self) -> List[str]:
        """
        Build search URLs for AutoScout24
        
        Returns:
            List of search URLs
        """
        urls = []
        
        # Number of pages to scrape (20 results per page)
        # 5 pages = 100 results total
        num_pages = 5
        
        # Build URL for each vehicle type and fuel type combination
        for vehicle_config in self.config['search']['vehicle_types']:
            vehicle_type = vehicle_config['type']
            max_price = vehicle_config['max_price']
            
            for fuel_config in self.config['search']['fuel_types']:
                fuel_type = fuel_config['type']
                
                # Build URLs for multiple pages
                for page_num in range(1, num_pages + 1):
                    # Map to AutoScout24 parameters
                    params = {
                        'sort': 'age',
                        'desc': 1,
                        'ustate': 'U',  # Used cars
                        'size': 20,
                        'page': page_num,
                        'priceto': max_price,
                        'kmto': self.config['search']['max_mileage_km'],
                        'fregfrom': self.config['search']['min_year'],
                        # Location filtering - 80km radius from Heerenveen
                        'zipc': '8448',  # Heerenveen postal code
                        'dist': 80,      # 80km radius
                        'country': 'NL', # Netherlands only
                        'custtype': 'D', # Dealers only (exclude private sellers/particulier)
                        # Note: Not using body filter as codes may vary - relying on keyword filtering instead
                    }
                    
                    # Add fuel type filter
                    # AutoScout24 fuel codes: E=Electric, H=Hybrid (includes PHEV)
                    # We want to exclude gasoline (B=Benzine) and diesel (D=Diesel)
                    if fuel_type == "Full Electric":
                        params['fuel'] = 'E'  # Electric only
                    elif fuel_type == "PHEV":
                        # PHEV falls under Hybrid category in AutoScout24
                        params['fuel'] = 'H'  # Hybrid (includes PHEV)
                    elif fuel_type == "Hybrid":
                        params['fuel'] = 'H'  # Hybrid
                    else:
                        # For any other fuel type, still filter to electric/hybrid only
                        # Use multiple fuel types: E (Electric) and H (Hybrid)
                        # Note: AutoScout24 may not support multiple fuel params in one URL
                        # So we'll rely on post-scraping filtering and set to Electric/Hybrid
                        params['fuel'] = 'E,H'  # Electric and Hybrid
                    
                    # Build URL string
                    param_str = '&'.join([f"{k}={v}" for k, v in params.items()])
                    url = f"{self.base_url}/lst?{param_str}"
                    urls.append(url)
                    
                    self.logger.debug(f"Built URL for {vehicle_type} {fuel_type} page {page_num}: {url}")
        
        # Return only unique URLs (since we're using same fuel filter for both)
        return list(set(urls))
    
    def parse_listing_page(self, url: str) -> List[Dict]:
        """
        Parse AutoScout24 listing page
        
        Args:
            url: Search results URL
            
        Returns:
            List of car summary dictionaries
        """
        car_summaries = []
        
        try:
            # Navigate to listing page with timeout protection
            try:
                self.driver.get(url)
                self._random_delay(2, 4)
            except TimeoutException:
                self.logger.warning(f"Page load timeout (30s) on listing page: {url}")
                return car_summaries
            
            # Accept cookie consent if present
            try:
                cookie_button = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Alles accepteren')]"))
                )
                cookie_button.click()
                self.logger.info("Accepted cookie consent")
                time.sleep(3)  # Increased wait time for page to settle after cookie acceptance
            except TimeoutException:
                self.logger.debug("No cookie consent found or already accepted")
            
            # Wait for listings to load (article elements)
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article"))
                )
            except TimeoutException:
                self.logger.warning(f"Timeout waiting for listings on {url}")
                return car_summaries
            
            # Find all car listing cards (article elements)
            listings = self.driver.find_elements(By.CSS_SELECTOR, "article")
            
            self.logger.info(f"Found {len(listings)} listings on page")
            
            for idx, listing in enumerate(listings, 1):
                try:
                    self.logger.info(f"Processing listing {idx}/{len(listings)}")
                    # Extract basic information from listing card
                    car_summary = {}
                    
                    # Get listing URL from data-guid attribute
                    # AutoScout24 uses JavaScript-populated hrefs, so we build the URL from the GUID
                    guid = listing.get_attribute('data-guid')
                    if guid:
                        car_summary['listing_url'] = f"{self.base_url}/aanbod/{guid}"
                    else:
                        # Fallback: try to get href from anchor tag
                        try:
                            link_elem = listing.find_element(By.CSS_SELECTOR, "a")
                            car_summary['listing_url'] = link_elem.get_attribute('href')
                        except NoSuchElementException:
                            car_summary['listing_url'] = None
                    
                    # Skip listings without valid URLs
                    if not car_summary['listing_url']:
                        self.logger.warning(f"Skipping listing {idx} - no valid URL found (no data-guid or href)")
                        continue
                    
                    # Skip "suggested results" that don't match our search filters
                    # AutoScout24 pads results with similar cars that may not be electric/PHEV
                    if 'suggested-results' in car_summary['listing_url']:
                        self.logger.debug(f"Skipping suggested result: {car_summary['listing_url']}")
                        continue
                    
                    # Get external ID from URL
                    external_id = car_summary['listing_url'].split('/')[-1].split('?')[0]
                    car_summary['external_id'] = f"autoscout24_{external_id}"
                    
                    # Get title from h2 element
                    try:
                        title_elem = listing.find_element(By.CSS_SELECTOR, "h2")
                        title_text = title_elem.text.strip()
                        # Parse title (usually "Make Model Version")
                        title_parts = title_text.split()
                        car_summary['make'] = title_parts[0] if len(title_parts) > 0 else "Unknown"
                        # Use normalize_model_name to extract clean model name
                        raw_model = ' '.join(title_parts[1:]) if len(title_parts) > 1 else "Unknown"
                        car_summary['model'] = normalize_model_name(raw_model) or "Unknown"
                        
                        # Filter out vans and commercial vehicles
                        van_keywords = ['vito', 'sprinter', 'transit', 'combo', 'partner', 'berlingo', 
                                       'caddy', 'transporter', 'crafter', 'ducato', 'boxer', 'jumper',
                                       'proace', 'vivaro', 'movano', 'expert', 'dispatch']
                        model_lower = car_summary.get('model', '').lower()
                        title_lower = title_text.lower()
                        if any(van in model_lower for van in van_keywords):
                            self.logger.info(f"  - Skipping van: {car_summary['make']} {car_summary['model']}")
                            continue
                        
                        # Filter out hydrogen fuel cell vehicles early (before detail page scrape)
                        # Hydrogen cars: Toyota Mirai, Hyundai NEXO
                        if ('mirai' in model_lower or 'nexo' in model_lower or 
                            'waterstof' in title_lower or 'hydrogen' in title_lower or 'fcev' in title_lower):
                            self.logger.debug(f"  - Skipping hydrogen vehicle (early filter): {car_summary['make']} {car_summary['model']}")
                            continue
                        
                        # Check for gasoline engine patterns in model name
                        # Patterns like "1.2", "2.0", "1.5 TSI", etc. indicate combustion engines
                        # IMPORTANT: Exclude battery sizes (e.g., "64.8 kWh")
                        gasoline_patterns = [
                            r'\d+\.\d+\s*(TSI|TFSI|TDI|HDi|BlueHDi|PureTech|EcoBoost|Skyactiv)',  # e.g., "1.2 TSI", "1.5 HDi"
                            r'\b\d+\.\d+\s*[lL]\b',  # e.g., "2.0L" - must have L suffix to avoid false positives
                        ]
                        model_and_title = f"{car_summary.get('model', '')} {title_text}"
                        
                        # Skip gasoline pattern check if this looks like an EV (has kWh battery size)
                        is_likely_ev = re.search(r'\d+\.?\d*\s*k?wh', model_and_title, re.IGNORECASE)
                        
                        if not is_likely_ev:
                            for pattern in gasoline_patterns:
                                if re.search(pattern, model_and_title):
                                    self.logger.info(f"  - Skipping: Gasoline engine pattern detected in '{model_and_title}'")
                                    # Use a flag to skip this listing
                                    car_summary['skip_gasoline'] = True
                                    break
                        
                        if car_summary.get('skip_gasoline'):
                            continue
                        
                        self.logger.debug(f"  - {car_summary['make']} {car_summary['model']}")
                    except NoSuchElementException:
                        self.logger.warning(f"  - No title found, skipping")
                        continue
                    
                    # Get price from paragraph containing "€"
                    try:
                        price_elem = listing.find_element(By.XPATH, ".//p[contains(text(), '€')]")
                        car_summary['price'] = extract_price(price_elem.text)
                    except NoSuchElementException:
                        car_summary['price'] = None
                    
                    # Extract specs from spans, divs, and text elements
                    try:
                        # Get all text from the listing card
                        listing_text = listing.text or ""
                        
                        # Mileage detection - look for pattern like "12.345 km"
                        km_match = re.search(r'(\d{1,3}(?:\.\d{3})*)\s*km', listing_text)
                        if km_match:
                            car_summary['mileage_km'] = extract_number(km_match.group(0))
                        
                        # Year detection (MM/YYYY format)
                        year_match = re.search(r'\d{2}/(\d{4})', listing_text)
                        if year_match:
                            car_summary['year'] = int(year_match.group(1))
                        
                        # Fuel type detection
                        if 'Waterstof' in listing_text:
                            car_summary['fuel_type'] = 'Hydrogen'
                        elif 'Elektrisch' in listing_text:
                            car_summary['fuel_type'] = 'Full Electric'
                        elif 'Plug-in hybride' in listing_text or 'Plug-in Hybride' in listing_text:
                            car_summary['fuel_type'] = 'PHEV'
                        elif 'Hybride' in listing_text:
                            car_summary['fuel_type'] = 'Hybrid'
                        elif 'Benzine' in listing_text:
                            # Skip benzine cars immediately
                            self.logger.info(f"  - Skipping benzine car: {car_summary['make']} {car_summary['model']}")
                            car_summary['skip_gasoline'] = True
                        elif 'Diesel' in listing_text:
                            # Skip diesel cars immediately
                            self.logger.info(f"  - Skipping diesel car: {car_summary['make']} {car_summary['model']}")
                            car_summary['skip_gasoline'] = True
                    except Exception as e:
                        self.logger.debug(f"Error extracting specs: {e}")
                    
                    # Skip if marked as gasoline/diesel
                    if car_summary.get('skip_gasoline'):
                        continue
                    
                    # Get image
                    try:
                        img_elem = listing.find_element(By.CSS_SELECTOR, "img")
                        car_summary['primary_image_url'] = img_elem.get_attribute('src')
                    except NoSuchElementException:
                        car_summary['primary_image_url'] = None
                    
                    car_summaries.append(car_summary)
                
                except Exception as e:
                    import traceback
                    self.logger.error(f"Error parsing listing: {e}")
                    self.logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
        
        except Exception as e:
            import traceback
            self.logger.error(f"Error loading listing page {url}: {e}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('listing_page_error')
        
        return car_summaries
    
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """
        Parse detailed car information from AutoScout24 detail page
        
        Args:
            car_summary: Basic car info from listing page
            
        Returns:
            Complete car data dictionary
        """
        car_data = car_summary.copy()
        car_data['source_website'] = self.website_name
        
        try:
            # Navigate to detail page with timeout protection
            try:
                self.driver.get(car_summary['listing_url'])
                self._random_delay(2, 4)
            except TimeoutException:
                self.logger.warning(f"Page load timeout (30s) on detail page: {car_summary['listing_url']}")
                return None
            
            # Enhanced unavailability detection
            # AutoScout24 shows various unavailability messages and removes key page elements
            try:
                is_unavailable = False
                page_source = self.driver.page_source.lower()
                
                # Skip unavailability check for hydrogen vehicles (they'll be filtered later)
                # This prevents false positives from "waterstof" URLs or page content
                if 'waterstof' in page_source or 'hydrogen' in page_source:
                    # Don't check unavailability - hydrogen vehicles will be skipped anyway
                    text_match_found = False
                    price_missing = False
                    sparse_specs = False
                else:
                    # 1. Check for unavailability text patterns (case-insensitive)
                    # Look for actual visible unavailability messages, not i18n JSON strings
                    # We need to check both presence of text AND absence of key page elements
                    
                    # First check page structure indicators
                    # 2. Check if price element is missing (strong indicator of unavailability)
                    price_elements = self.driver.find_elements(By.CSS_SELECTOR, 
                        "div[class*='price'], span[class*='price'], strong[class*='price'], [data-testid*='price']")
                    price_missing = len(price_elements) == 0
                    
                    # 3. Check if spec elements are sparse (< 3 indicates incomplete page)
                    spec_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt, term")
                    sparse_specs = len(spec_elements) < 3
                    
                    # 4. Check for visible body text (excludes script/style tags)
                    try:
                        body_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
                    except:
                        body_text = ""
                    
                    # AutoScout24-specific unavailability patterns
                    # These should appear in visible text, not just in i18n JSON
                    unavailability_patterns = [
                        'dit voertuig is helaas niet meer beschikbaar',  # Most common actual message
                        'deze auto is niet meer beschikbaar',
                        'deze auto is verkocht',
                        'helaas niet meer beschikbaar',
                    ]
                    
                    # Check if patterns appear in VISIBLE body text
                    text_match_found = any(pattern in body_text for pattern in unavailability_patterns)
                    
                    # Determine unavailability based on COMBINED signals
                    # CHANGED: Don't trust text alone - require missing price OR sparse specs
                    if text_match_found and (price_missing or sparse_specs):
                        # High confidence: unavailability text + missing page elements
                        is_unavailable = True
                        self.logger.info(f"Car unavailable (text match + missing elements): {car_summary['listing_url']}")
                    elif price_missing and sparse_specs:
                        # Fallback: both missing indicates unavailable page
                        is_unavailable = True
                        self.logger.info(f"Car unavailable (missing price + sparse specs): {car_summary['listing_url']}")
                
                if is_unavailable:
                    car_data['is_unavailable'] = True
                    return car_data
                    
            except Exception as e:
                self.logger.warning(f"Error checking unavailability: {e}")
                pass  # Continue if check fails
            
            # Wait for page to load - look for term/definition elements
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "dt, term"))
                )
            except TimeoutException:
                self.logger.warning(f"Timeout on detail page: {car_summary['listing_url']}")
                return None
            
            # Extract detailed information from actual HTML structure
            
            # Year, mileage, fuel type, etc. from specification term/definition lists
            try:
                # Try both dt/dd and term/definition element types
                spec_rows = self.driver.find_elements(By.CSS_SELECTOR, "dt, term")
                spec_values = self.driver.find_elements(By.CSS_SELECTOR, "dd, definition")
                
                specs = {}
                for i, row in enumerate(spec_rows):
                    if i < len(spec_values):
                        key = row.text.strip().lower()
                        value = spec_values[i].text.strip()
                        specs[key] = value
                
                # Debug: log all spec keys found
                self.logger.debug(f"Found spec keys: {list(specs.keys())}")
                
                # Parse specifications - only update if we get valid data
                if 'jaar' in specs or 'bouwjaar' in specs:
                    year_text = specs.get('jaar', specs.get('bouwjaar', ''))
                    # Extract 4-digit year (not first number which might be month)
                    import re
                    year_match = re.search(r'(\d{4})', year_text)
                    if year_match:
                        year = int(year_match.group(1))
                        if year > 1900:  # Sanity check
                            car_data['year'] = year
                
                if 'kilometerstand' in specs or 'km-stand' in specs:
                    mileage = extract_number(specs.get('kilometerstand', specs.get('km-stand', '')))
                    if mileage:
                        car_data['mileage_km'] = mileage
                
                if 'brandstof' in specs or 'fuel type' in specs:
                    fuel = normalize_fuel_type(
                        specs.get('brandstof', specs.get('fuel type', '')),
                        model_str=car_data.get('model')
                    )
                    if fuel:
                        car_data['fuel_type'] = fuel
                
                # Priority 1: Actieradius praktijk (practical/real-world range - most accurate)
                if 'actieradius praktijk' in specs:
                    practical_range = extract_number(specs.get('actieradius praktijk', ''))
                    if practical_range:
                        car_data['electric_range_km'] = practical_range  # Use electric_range_km for practical range
                        self.logger.debug(f"Using practical range: {practical_range} km")
                
                # Priority 2: Elektrisch bereik (electric range - shown prominently on page)
                if 'elektrisch bereik' in specs and 'electric_range_km' not in car_data:
                    e_range = extract_number(specs.get('elektrisch bereik', ''))
                    if e_range:
                        car_data['electric_range_km'] = e_range
                        self.logger.debug(f"Using elektrisch bereik: {e_range} km")
                
                # Priority 3: Actieradius (WLTP official range - fallback)
                if 'actieradius' in specs or 'range' in specs:
                    range_km = extract_number(specs.get('actieradius', specs.get('range', '')))
                    if range_km:
                        car_data['range_km'] = range_km
                        self.logger.debug(f"Using actieradius: {range_km} km")
                
                # WLTP range fallback: If range not found on listing, try WLTP database
                fuel = car_data.get('fuel_type', '')
                if fuel in ['Full Electric', 'PHEV', 'Hybrid']:
                    # For Full Electric: fallback for range_km
                    if fuel == 'Full Electric' and not car_data.get('range_km'):
                        wltp_range = get_wltp_range(car_data.get('make', ''), car_data.get('model', ''), fuel)
                        if wltp_range:
                            car_data['range_km'] = wltp_range
                            car_data['range_source'] = 'wltp_estimate'
                            self.logger.info(f"  - Using WLTP range estimate: {wltp_range} km")
                    
                    # For PHEV/Hybrid: fallback for electric_range_km
                    if fuel in ['PHEV', 'Hybrid'] and not car_data.get('electric_range_km'):
                        wltp_range = get_wltp_range(car_data.get('make', ''), car_data.get('model', ''), fuel)
                        if wltp_range:
                            car_data['electric_range_km'] = wltp_range
                            car_data['range_source'] = 'wltp_estimate'
                            self.logger.info(f"  - Using WLTP electric range estimate: {wltp_range} km")
                
                if 'carrosserie' in specs or 'body type' in specs:
                    v_type = normalize_vehicle_type(specs.get('carrosserie', specs.get('body type', '')), car_data.get('model', ''), car_data.get('make', ''))
                    if v_type:
                        car_data['vehicle_type'] = v_type
                
                # Fallback: if still no vehicle_type, check the model name
                if 'vehicle_type' not in car_data or not car_data['vehicle_type']:
                    v_type = normalize_vehicle_type('', car_data.get('model', ''), car_data.get('make', ''))
                    if v_type:
                        car_data['vehicle_type'] = v_type
                
                if 'kleur' in specs or 'color' in specs:
                    color = specs.get('kleur', specs.get('color', ''))
                    if color:
                        car_data['color'] = color
                
                if 'transmissie' in specs or 'transmission' in specs:
                    trans = specs.get('transmissie', specs.get('transmission', ''))
                    if trans:
                        car_data['transmission'] = trans
                
                if 'vermogen' in specs or 'power' in specs:
                    power_text = specs.get('vermogen', specs.get('power', ''))
                    if power_text:
                        kw = extract_number(power_text.split('kW')[0] if 'kW' in power_text else '')
                        hp = extract_number(power_text.split('pk')[0] if 'pk' in power_text else '')
                        if kw:
                            car_data['power_kw'] = kw
                        if hp:
                            car_data['power_hp'] = hp
                
                # Extract storage capacity (boot/trunk space)
                if 'bagageruimte' in specs or 'kofferruimte' in specs or 'laadruimte' in specs:
                    storage_text = specs.get('bagageruimte', specs.get('kofferruimte', specs.get('laadruimte', '')))
                    storage = extract_number(storage_text)
                    if storage:
                        car_data['storage_capacity_liters'] = storage
                        self.logger.debug(f"Extracted storage capacity: {storage}L")
                
                # Extract rear legroom if available
                if 'achterbank beenruimte' in specs or 'legroom rear' in specs:
                    legroom_text = specs.get('achterbank beenruimte', specs.get('legroom rear', ''))
                    legroom = extract_number(legroom_text)
                    if legroom:
                        car_data['rear_legroom_mm'] = legroom
                
                # Extract number of seats
                if 'aantal zitplaatsen' in specs or 'zitplaatsen' in specs or 'seats' in specs:
                    seats_text = specs.get('aantal zitplaatsen', specs.get('zitplaatsen', specs.get('seats', '')))
                    seats = extract_number(seats_text)
                    if seats:
                        car_data['seats'] = seats
                        self.logger.debug(f"Extracted seats: {seats}")
                
                # Extract number of doors
                if 'aantal deuren' in specs or 'deuren' in specs or 'doors' in specs:
                    doors_text = specs.get('aantal deuren', specs.get('deuren', specs.get('doors', '')))
                    doors = extract_number(doors_text)
                    if doors:
                        car_data['doors'] = doors
                        self.logger.debug(f"Extracted doors: {doors}")
            
            except Exception as e:
                self.logger.error(f"Error parsing specifications: {e}")
            
            # Extract features from Next.js JSON data
            try:
                import json
                features = []
                
                # Find the __NEXT_DATA__ script tag containing structured JSON data
                page_source = self.driver.page_source
                json_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_source, re.DOTALL)
                
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        # Navigate to equipment data in the JSON structure
                        equipment = data.get('props', {}).get('pageProps', {}).get('listingDetails', {}).get('vehicle', {}).get('equipment', {})
                        
                        # Extract features from all equipment categories
                        for category, items in equipment.items():
                            if isinstance(items, list):
                                for item in items:
                                    if isinstance(item, dict) and 'id' in item:
                                        feature_name = item['id'].strip()
                                        if feature_name:
                                            features.append(feature_name)
                        
                        self.logger.debug(f"Extracted {len(features)} features from JSON data")
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        self.logger.warning(f"Error parsing JSON equipment data: {e}")
                else:
                    self.logger.warning("Could not find __NEXT_DATA__ script tag")
                
                car_data['features'] = features
            except Exception as e:
                self.logger.error(f"Error parsing features: {e}")
                car_data['features'] = []
            
            # Extract price from JSON-LD structured data (most reliable)
            try:
                import json
                page_source = self.driver.page_source
                
                # Look for JSON-LD structured data which contains price and dealer info
                jsonld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page_source, re.DOTALL)
                
                if jsonld_match:
                    try:
                        jsonld_data = json.loads(jsonld_match.group(1))
                        
                        # Extract price from offers section
                        if isinstance(jsonld_data, dict) and 'offers' in jsonld_data:
                            offers = jsonld_data['offers']
                            if isinstance(offers, dict) and 'price' in offers:
                                price = offers['price']
                                if price and isinstance(price, (int, float)):
                                    car_data['price'] = float(price)
                                    self.logger.debug(f"Extracted price from JSON-LD: €{price}")
                        
                        # Extract dealer address from offers.offeredBy.address
                        if isinstance(jsonld_data, dict) and 'offers' in jsonld_data:
                            offers = jsonld_data['offers']
                            if isinstance(offers, dict) and 'offeredBy' in offers:
                                offered_by = offers['offeredBy']
                                if isinstance(offered_by, dict) and 'address' in offered_by:
                                    address = offered_by['address']
                                    
                                    # Build location string from address components
                                    location_parts = []
                                    if address.get('streetAddress'):
                                        location_parts.append(address['streetAddress'])
                                    if address.get('postalCode'):
                                        location_parts.append(address['postalCode'])
                                    if address.get('addressLocality'):
                                        location_parts.append(address['addressLocality'])
                                    
                                    if location_parts:
                                        location_text = ', '.join(location_parts)
                                        car_data['dealer_location'] = location_text
                                        
                                        # Extract just the city name
                                        city = extract_city_from_address(location_text)
                                        if city:
                                            car_data['location_city'] = city
                                        else:
                                            # Fallback: use addressLocality if available
                                            car_data['location_city'] = address.get('addressLocality', location_text)
                                        
                                        # Calculate distance from Heerenveen
                                        coords = get_coordinates(location_text)
                                        if coords:
                                            car_data['latitude'] = coords[0]
                                            car_data['longitude'] = coords[1]
                                            distance = calculate_distance_from_heerenveen(coords=coords)
                                            if distance and distance < 500:  # Sanity check
                                                car_data['distance_from_heerenveen_km'] = distance
                                                self.logger.debug(f"Distance from Heerenveen: {distance:.2f} km")
                                            else:
                                                self.logger.warning(f"Suspicious distance: {distance} km for location: {location_text}")
                                        else:
                                            self.logger.warning(f"Could not geocode location: {location_text}")
                                        
                                        self.logger.debug(f"Extracted location from JSON-LD: {location_text}")
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        self.logger.warning(f"Error parsing JSON-LD data: {e}")
            except Exception as e:
                self.logger.error(f"Error extracting JSON-LD data: {e}")
            
            # Fallback: Extract location from dealer info section
            try:
                # Only do this if we didn't get location from JSON-LD
                if 'dealer_location' not in car_data or not car_data['dealer_location']:
                    location_text = None
                    
                    # Try to extract from __NEXT_DATA__ JSON
                    try:
                        import json
                        page_source = self.driver.page_source
                        json_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_source, re.DOTALL)
                        
                        if json_match:
                            data = json.loads(json_match.group(1))
                            seller = data.get('props', {}).get('pageProps', {}).get('listingDetails', {}).get('seller', {})
                            address = seller.get('address', {})
                            
                            # Build location string from address components
                            location_parts = []
                            if address.get('street'):
                                location_parts.append(address['street'])
                            if address.get('zipcode'):
                                location_parts.append(address['zipcode'])
                            if address.get('city'):
                                location_parts.append(address['city'])
                            
                            if location_parts:
                                location_text = ', '.join(location_parts)
                                self.logger.debug(f"Extracted location from __NEXT_DATA__: {location_text}")
                    except Exception as e:
                        self.logger.debug(f"Could not extract location from __NEXT_DATA__: {e}")
                
                # Fallback: Look for location using Dutch postal code pattern in page text
                if not location_text:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    # Dutch postal codes: start with 1-9, followed by 3 digits, then 2 capital letters
                    # Require space after postal code and city must start with letter to avoid junk
                    postal_match = re.search(r'([1-9]\d{3}\s*[A-Z]{2})\s+([A-Za-z][A-Za-z\s-]+)', page_text)
                    if postal_match:
                        postal_code = postal_match.group(1).replace(' ', '')  # Normalize spacing
                        city = postal_match.group(2)[:50].strip()
                        
                        # Validate: exclude if it looks like a year (1900-2199)
                        first_four = postal_code[:4]
                        if first_four.isdigit():
                            year_num = int(first_four)
                            # Valid Dutch postal codes: 1000-9999, but exclude year range 1900-2199
                            if not (1900 <= year_num <= 2199):
                                location_text = f"{postal_code} {city}".strip()
                                self.logger.debug(f"Extracted location from page text: {location_text}")
                            else:
                                self.logger.debug(f"Rejected postal code {postal_code} (looks like year {year_num})")
                
                # Save location and calculate distance
                if location_text:
                    car_data['dealer_location'] = location_text
                    
                    # Extract just the city name
                    city_name = extract_city_from_address(location_text)
                    if city_name:
                        car_data['location_city'] = city_name
                    else:
                        car_data['location_city'] = location_text  # Fallback
                    
                    # Calculate distance from Heerenveen
                    coords = get_coordinates(location_text)
                    if coords:
                        car_data['latitude'] = coords[0]
                        car_data['longitude'] = coords[1]
                        distance = calculate_distance_from_heerenveen(coords=coords)
                        if distance and distance < 500:  # Sanity check - should be within Netherlands
                            car_data['distance_from_heerenveen_km'] = distance
                            self.logger.debug(f"Distance from Heerenveen: {distance:.2f} km")
                        else:
                            self.logger.warning(f"Suspicious distance: {distance} km for location: {location_text}")
                    else:
                        self.logger.warning(f"Could not geocode location: {location_text}")
                else:
                    self.logger.warning("No location found for this listing")
                    
            except Exception as e:
                self.logger.error(f"Error parsing location: {e}")
            
            # Extract dealer info
            try:
                # Look for h2 or heading elements in dealer section
                dealer_elem = self.driver.find_element(By.XPATH, "//h2 | //h3")
                dealer_text = dealer_elem.text.strip()
                if dealer_text and len(dealer_text) < 100:
                    car_data['dealer_name'] = dealer_text
            except Exception as e:
                car_data['dealer_name'] = None
            
            # Extract all images
            try:
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, "img")
                image_urls = []
                for img in image_elements:
                    src = img.get_attribute('src')
                    # Filter out icons, logos, etc.
                    if src and ('autoscout24' in src or 'cloudfront' in src) and 'logo' not in src.lower():
                        image_urls.append(src)
                
                car_data['image_urls'] = image_urls
                if not car_data.get('primary_image_url') and image_urls:
                    car_data['primary_image_url'] = image_urls[0]
            except Exception as e:
                self.logger.error(f"Error parsing images: {e}")
            
            # Upgrade Hybrid to PHEV if electric range is found
            # Regular hybrids don't have electric_range_km, only PHEVs do
            if car_data.get('fuel_type') == 'Hybrid' and car_data.get('electric_range_km'):
                car_data['fuel_type'] = 'PHEV'
                self.logger.info(f"Upgraded Hybrid to PHEV (electric range: {car_data['electric_range_km']} km)")
            
            # Check if vehicle should be excluded (too small for family use)
            if should_exclude_vehicle(car_data.get('make', ''), car_data.get('model', '')):
                self.logger.info(f"Excluding small car: {car_data.get('make')} {car_data.get('model')}")
                return None
            
            return car_data
        
        except Exception as e:
            import traceback
            self.logger.error(f"Error parsing detail page: {e}")
            self.logger.error(traceback.format_exc())
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('detail_page_error')
            return None


    def scrape_alternatives(self, unavailable_car_url: str) -> List[Dict]:
        """
        Scrape alternative cars from AutoScout24's "show alternatives" page
        
        Args:
            unavailable_car_url: URL of the unavailable car listing
            
        Returns:
            List of alternative car summaries
        """
        self.logger.info(f"Scraping alternatives from: {unavailable_car_url}")
        
        try:
            # Navigate to the unavailable car page with timeout protection
            try:
                self.driver.get(unavailable_car_url)
                self._random_delay(2, 4)
            except TimeoutException:
                self.logger.warning(f"Page load timeout (30s) on alternatives page: {unavailable_car_url}")
                return []
            
            # Check if we're on an alternatives page
            page_text = self.driver.page_source.lower()
            if 'toon alternatieven' not in page_text and 'niet meer beschikbaar' not in page_text:
                self.logger.warning("Car appears to still be available - no alternatives page found")
                return []
            
            # Look for alternative car listings on the page
            # AutoScout24 shows alternatives as regular article elements
            alternatives = []
            
            try:
                # Wait for recommendation items to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".VehicleRecommendationItem_container___TuzC"))
                )
                
                # Find all recommendation items (different structure from regular listings)
                listings = self.driver.find_elements(By.CSS_SELECTOR, ".VehicleRecommendationItem_container___TuzC")
                
                self.logger.info(f"Found {len(listings)} alternative cars")
                
                for idx, listing in enumerate(listings, 1):
                    try:
                        self.logger.info(f"Processing alternative {idx}/{len(listings)}")
                        
                        car_summary = {}
                        
                        # Get listing URL
                        link_elem = listing.find_element(By.CSS_SELECTOR, "a")
                        car_summary['listing_url'] = link_elem.get_attribute('href')
                        
                        # Get external ID from URL
                        external_id = car_summary['listing_url'].split('/')[-1].split('?')[0]
                        car_summary['external_id'] = f"autoscout24_{external_id}"
                        
                        # Get title (VehicleCard uses span with VehicleCard_headline class)
                        try:
                            title_elem = listing.find_element(By.CSS_SELECTOR, ".VehicleCard_headline__l7hWc")
                            title_text = title_elem.text.strip()
                            title_parts = title_text.split()
                            car_summary['make'] = title_parts[0] if len(title_parts) > 0 else "Unknown"
                            raw_model = ' '.join(title_parts[1:]) if len(title_parts) > 1 else "Unknown"
                            car_summary['model'] = normalize_model_name(raw_model)
                            
                            self.logger.debug(f"  - {car_summary['make']} {car_summary['model']}")
                        except NoSuchElementException:
                            self.logger.warning(f"  - No title found, skipping")
                            continue
                        
                        # Get price (VehicleCard uses div with VehicleCard_priceStyle class)
                        try:
                            price_elem = listing.find_element(By.CSS_SELECTOR, ".VehicleCard_priceStyle__dG2ls")
                            car_summary['price'] = extract_price(price_elem.text)
                        except NoSuchElementException:
                            car_summary['price'] = None
                        
                        # Extract specs from listing text
                        try:
                            listing_text = listing.text
                            
                            # Mileage
                            km_match = re.search(r'(\d{1,3}(?:\.\d{3})*)\s*km', listing_text)
                            if km_match:
                                car_summary['mileage_km'] = extract_number(km_match.group(0))
                            
                            # Year
                            year_match = re.search(r'\d{2}/(\d{4})', listing_text)
                            if year_match:
                                car_summary['year'] = int(year_match.group(1))
                            
                            # Fuel type
                            if 'Elektrisch' in listing_text:
                                car_summary['fuel_type'] = 'Full Electric'
                            elif 'Plug-in hybride' in listing_text or 'Plug-in Hybride' in listing_text:
                                car_summary['fuel_type'] = 'PHEV'
                            elif 'Hybride' in listing_text:
                                car_summary['fuel_type'] = 'Hybrid'
                            elif 'Benzine' in listing_text or 'Diesel' in listing_text:
                                # Skip non-electric alternatives
                                self.logger.info(f"  - Skipping non-electric alternative: {car_summary['make']} {car_summary['model']}")
                                continue
                        except Exception as e:
                            self.logger.debug(f"Error extracting specs: {e}")
                        
                        # Get image (VehicleCard uses VehicleCard_image class)
                        try:
                            img_elem = listing.find_element(By.CSS_SELECTOR, ".VehicleCard_image__pL55V")
                            car_summary['primary_image_url'] = img_elem.get_attribute('src')
                        except NoSuchElementException:
                            car_summary['primary_image_url'] = None
                        
                        # Mark as alternative
                        car_summary['is_alternative'] = True
                        car_summary['alternative_for_url'] = unavailable_car_url
                        
                        alternatives.append(car_summary)
                    
                    except Exception as e:
                        self.logger.error(f"Error parsing alternative listing: {e}")
                        continue
                
            except TimeoutException:
                self.logger.warning("Timeout waiting for alternative listings")
                return alternatives
            
            self.logger.info(f"Successfully scraped {len(alternatives)} alternatives")
            return alternatives
        
        except Exception as e:
            self.logger.error(f"Error scraping alternatives: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('alternatives_page_error')
            return []


if __name__ == "__main__":
    # Test scraper
    scraper = AutoScout24Scraper()
    scraper.run()
