"""
Gaspedaal.nl scraper for NL Car Tracker
"""
from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.helpers import (
    extract_number, normalize_fuel_type, normalize_vehicle_type, normalize_model_name,
    get_coordinates, calculate_distance_from_heerenveen, should_exclude_vehicle,
    extract_city_from_address
)
from typing import List, Dict
import time
import re
import json
import os


class GaspedaalScraper(BaseScraper):
    """Scraper for gaspedaal.nl"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        super().__init__(config_path, db_path)
        self.website_name = "gaspedaal.nl"
        self.base_url = "https://www.gaspedaal.nl"
        self.cookies_file = "cookies/gaspedaal_cookies.json"
    
    def load_cookies(self):
        """Load cookies from file to bypass privacy gate"""
        if not os.path.exists(self.cookies_file):
            self.logger.warning(f"Cookie file not found: {self.cookies_file}")
            return False
        
        try:
            # First navigate to base domain to set cookies
            try:
                self.driver.get(self.base_url)
                time.sleep(2)
            except TimeoutException:
                self.logger.error(f"Page load timeout (30s) loading base URL - cannot proceed")
                raise
            
            # Load cookies from file
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            # Add each cookie to the browser
            for cookie in cookies:
                try:
                    # Remove fields that Selenium doesn't accept
                    cookie.pop('sameSite', None)
                    cookie.pop('storeId', None)
                    cookie.pop('id', None)
                    
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    self.logger.debug(f"Could not add cookie {cookie.get('name', 'unknown')}: {e}")
            
            self.logger.info(f"Loaded {len(cookies)} cookies from {self.cookies_file}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading cookies: {e}")
            return False
    
    def _extract_external_urls(self, page_source: str) -> Dict[str, str]:
        """
        Extract mapping of occasion IDs to external portal URLs from page source.
        
        Gaspedaal is an aggregator - it embeds external URLs in escaped JSON.
        Pattern: "advertentieId":125213917,...,"url":"https://www.autotrack.nl/..."
        
        Returns:
            Dict mapping occasion IDs (as strings) to external URLs
        """
        # Pattern to extract advertentieId and url pairs from escaped JSON
        pattern = r'\\"advertentieId\\":(\d+).*?\\"url\\":\\"(https://[^\\"]+)\\"'
        
        matches = re.findall(pattern, page_source, re.DOTALL)
        
        # Create mapping, filtering out gaspedaal.nl URLs (keep only external portals)
        id_to_url = {}
        for adv_id, url in matches:
            if 'gaspedaal.nl' not in url:
                id_to_url[adv_id] = url
        
        return id_to_url
    
    def build_search_url(self) -> List[str]:
        """Build search URLs for Gaspedaal based on configuration"""
        urls = []
        
        for vehicle in self.config['search']['vehicle_types']:
            for fuel in self.config['search']['fuel_types']:
                # Gaspedaal URL structure (similar to Autotrack - both DPG Media)
                
                # Map our fuel types to Gaspedaal's URL format
                fuel_map = {
                    "Full Electric": "elektrisch",
                    "PHEV": "hybride"
                }
                
                # Map vehicle types
                vehicle_map = {
                    "SUV": "suv",
                    "Stationwagon": "stationwagen"
                }
                
                fuel_param = fuel_map.get(fuel['type'], 'elektrisch')
                vehicle_param = vehicle_map.get(vehicle['type'], 'suv')
                
                # Build URL with filters
                url = f"{self.base_url}/occasions"
                params = []
                params.append(f"brandstof={fuel_param}")
                params.append(f"type={vehicle_param}")
                params.append(f"prijs_tot={vehicle['max_price']}")
                params.append(f"bouwjaar_vanaf={self.config['search']['min_year']}")
                params.append(f"km_tot={self.config['search']['max_mileage_km']}")
                
                full_url = url + "?" + "&".join(params)
                urls.append(full_url)
                self.logger.info(f"Built search URL: {full_url}")
        
        return urls
    
    def parse_listing_page(self, url: str) -> List[Dict]:
        """Parse Gaspedaal listing page to extract basic car information"""
        car_summaries = []
        
        try:
            # Load cookies before first request if available
            if not hasattr(self, '_cookies_loaded'):
                self.load_cookies()
                self._cookies_loaded = True
            
            self.logger.info(f"Loading listing page: {url}")
            # Navigate to listing page with timeout protection
            try:
                self.driver.get(url)
                self._random_delay(2, 4)
            except TimeoutException:
                self.logger.warning(f"Page load timeout (30s) on listing page: {url}")
                return car_summaries
            
            # Wait a bit for cookies to take effect
            time.sleep(3)
            
            # Wait for car listings to load - looking for data-testid="occasion-item"
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="occasion-item"]'))
                )
            except TimeoutException:
                self.logger.warning(f"Timeout waiting for listings on {url}")
                return car_summaries
            
            # Extract external URLs from page source
            # Gaspedaal is an aggregator - real listing URLs are in escaped JSON in the page source
            page_source = self.driver.page_source
            external_url_map = self._extract_external_urls(page_source)
            self.logger.info(f"Extracted {len(external_url_map)} external URL mappings")
            
            # Extract external URLs from page source
            # Gaspedaal is an aggregator - real listing URLs are in escaped JSON in the page source
            page_source = self.driver.page_source
            external_url_map = self._extract_external_urls(page_source)
            self.logger.info(f"Extracted {len(external_url_map)} external URL mappings")
            
            # Extract car listing elements using data-testid attribute
            listings = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="occasion-item"]')
            
            if not listings:
                self.logger.warning("No car listings found on page")
                return car_summaries
            
            self.logger.info(f"Found {len(listings)} listings")
            
            # Parse each listing
            for idx, listing in enumerate(listings[:20]):  # Limit to first 20
                try:
                    car_summary = {}
                    
                    # Extract listing ID from the element's id attribute (e.g., "o125213917")
                    listing_id = listing.get_attribute('id')
                    if not listing_id or not listing_id.startswith('o'):
                        self.logger.warning(f"Could not extract listing ID from element {idx}")
                        continue
                    
                    # Remove the 'o' prefix from the ID to get the numerical part
                    numerical_id = listing_id[1:]  # Remove 'o' prefix
                    
                    # Try to get the external URL from our mapping
                    # Gaspedaal is an aggregator, so we use the real portal URL
                    external_url = external_url_map.get(numerical_id)
                    if external_url:
                        car_summary['listing_url'] = external_url
                        self.logger.debug(f"Found external URL for {numerical_id}: {external_url}")
                    else:
                        # Fallback to gaspedaal URL (though these don't work as detail pages)
                        detail_url = f"{self.base_url}/occasion/{numerical_id}"
                        car_summary['listing_url'] = detail_url
                        self.logger.debug(f"No external URL found for {numerical_id}, using placeholder")
                    
                    car_summary['external_id'] = f"gaspedaal_{numerical_id}"
                    
                    # Extract all text from the listing for parsing
                    listing_text = listing.text
                    
                    # Check for unavailability messages in listing text
                    # Gaspedaal shows unavailability status on listing cards
                    unavailability_patterns = [
                        'niet meer beschikbaar',
                        'helaas niet meer beschikbaar',
                        'is verkocht',
                        'reeds verkocht',
                        'al verkocht',
                        'no longer available',
                        'already sold',
                        'verkocht',
                        'gereserveerd',
                        'deze advertentie is niet meer beschikbaar'
                    ]
                    
                    listing_text_lower = listing_text.lower()
                    is_unavailable = any(pattern in listing_text_lower for pattern in unavailability_patterns)
                    
                    if is_unavailable:
                        self.logger.debug(f"Skipping unavailable car in listing {idx}: {listing_text[:50]}...")
                        continue  # Skip this listing entirely
                    
                    # Extract title (make + model) from h2
                    try:
                        title_elem = listing.find_element(By.CSS_SELECTOR, "h2")
                        title = title_elem.text.strip() if title_elem else None
                        
                        if title:
                            car_summary['title'] = title
                            
                            # Parse make and model from title
                            title_parts = title.split()
                            if len(title_parts) >= 2:
                                car_summary['make'] = title_parts[0]
                                raw_model = ' '.join(title_parts[1:])
                                car_summary['model'] = normalize_model_name(raw_model)
                        else:
                            car_summary['title'] = "Unknown"
                    except Exception as e:
                        self.logger.debug(f"Could not extract title: {e}")
                        car_summary['title'] = "Unknown"
                    
                    # Extract price
                    try:
                        # Price appears at the start of listing text (just a number like "20.425")
                        # or with Euro sign like "€ 24.950" or "€24950"
                        price_match = re.search(r'€\s*[\d.]+|^[\d.]+', listing_text, re.MULTILINE)
                        if price_match:
                            price_text = price_match.group(0)
                            price = extract_number(price_text)
                            if price:
                                car_summary['price'] = price
                    except Exception as e:
                        self.logger.debug(f"Could not extract price: {e}")
                    
                    # Extract year, mileage, and other specs from the listing text
                    # New format: "Bouwjaar:\n2024\nKm.stand:\n8.823 km"
                    # Old format: "2019 • 89.000 km • Elektrisch"
                    try:
                        # Year - try labeled format first, then fallback to simple digits
                        year_match = re.search(r'Bouwjaar:\s*(\d{4})', listing_text) or re.search(r'\b(20\d{2})\b', listing_text)
                        if year_match:
                            year = int(year_match.group(1))
                            if 2010 <= year <= 2025:
                                car_summary['year'] = year
                        
                        # Mileage - try labeled format first (Km.stand: or Km-stand:), then fallback to simple pattern
                        # But avoid matching the year (2024) by requiring it to have "km" nearby
                        km_match = re.search(r'Km[.\-]stand:\s*([\d.]+)\s*km', listing_text, re.IGNORECASE)
                        if not km_match:
                            # Fallback: find number with "km" but exclude if it's just the year
                            km_match = re.search(r'([\d.]+)\s*km', listing_text, re.IGNORECASE)
                            if km_match:
                                mileage_text = km_match.group(1)
                                # Skip if it's the year (e.g., 2024)
                                if len(mileage_text.replace('.', '')) == 4 and mileage_text.replace('.', '').startswith('20'):
                                    km_match = None
                        
                        if km_match:
                            mileage = extract_number(km_match.group(1))
                            if mileage and mileage > 50:  # Exclude values < 50 (likely not mileage)
                                car_summary['mileage_km'] = mileage
                        
                        # Fuel type - skip benzine/diesel immediately
                        fuel_keywords = ['elektrisch', 'hybride', 'plug-in', 'phev', 'benzine', 'diesel']
                        skip_gasoline = False
                        for keyword in fuel_keywords:
                            if keyword in listing_text.lower():
                                # Skip benzine/diesel cars immediately
                                if keyword in ['benzine', 'diesel']:
                                    self.logger.debug(f"Skipping benzine/diesel car: {car_summary.get('title', 'Unknown')}")
                                    skip_gasoline = True
                                    break
                                fuel = normalize_fuel_type(keyword, model_str=car_summary.get('model', ''))
                                if fuel:
                                    car_summary['fuel_type'] = fuel
                                    break
                        
                        # Skip this listing if it's benzine/diesel
                        if skip_gasoline:
                            continue
                        
                        # Power (kW) - extract from listing text, but avoid battery capacity (kWh)
                        # Look for standalone kW (not kWh) - typically appears as a separate line
                        power_match = re.search(r'(?<!\d)\n(\d+)kW\n', listing_text, re.IGNORECASE)
                        if not power_match:
                            # Fallback: look for "XXX kW" pattern that's not "XX kWh"
                            power_match = re.search(r'\n(\d+)\s*kW(?!h)\n', listing_text, re.IGNORECASE)
                        if power_match:
                            power_kw = int(power_match.group(1))
                            car_summary['power_kw'] = power_kw
                            # Convert to HP (1 kW ≈ 1.34102 HP)
                            car_summary['power_hp'] = int(power_kw * 1.34102)
                        
                        # Vehicle type - look for patterns like "SUV / Terreinwagen", "Hatchback", etc.
                        vehicle_type_match = re.search(r'(SUV / Terreinwagen|Hatchback|Sedan|Coupe|Stationwagen|MPV|Cabrio)', listing_text, re.IGNORECASE)
                        if vehicle_type_match:
                            v_type = vehicle_type_match.group(1)
                            # Normalize to standard format
                            v_type_normalized = normalize_vehicle_type(v_type, car_summary.get('model', ''), car_summary.get('make', ''))
                            if v_type_normalized:
                                car_summary['vehicle_type'] = v_type_normalized
                        
                        # Location - look at the end of the listing text for city names
                        # Format is usually: "City (Province)" or "DealerName\nCity"
                        lines = listing_text.strip().split('\n')
                        if lines:
                            # Skip common button/UI text and car attributes
                            skip_words = ['Vergelijk', 'Favoriet', 'Automaat', 'Grijs', 'Wit', 
                                        'Zwart', 'Elektrisch', 'Benzine', 'Diesel', 'Handgeschakeld', 
                                        'Hatchback', 'SUV', 'Terreinwagen', 'Sedan', 'Coupe', 'Blauw',
                                        'Rood', 'Zilver', 'Geel', 'Oranje', 'Beige', 'Bruin']
                            
                            location_found = False
                            for i, line in enumerate(reversed(lines)):
                                line = line.strip()
                                if not line or line in skip_words:
                                    continue
                                
                                # Skip "Bekijk deze auto op:" line
                                if line.startswith('Bekijk deze auto op:'):
                                    continue
                                
                                # Skip lines that look like numbers or specs
                                if re.match(r'^\d+[\d.\-]*$', line) or 'kW' in line or 'cc' in line or '-deurs' in line:
                                    continue
                                
                                # Look for city name pattern: "City (Province)" or just "City"
                                # Match format like "Bergschenhoek (ZH)" or "Venray (LI)"
                                loc_match = re.match(r'^([A-Z][a-zë]+(?:\s+[A-Z][a-zë]+)?)\s*(?:\([A-Z]{2}\))?', line)
                                if loc_match and not location_found:
                                    location = loc_match.group(1).strip()
                                    # Additional check: location should be at least 3 chars and not be a common car spec word
                                    if len(location) >= 3:
                                        car_summary['dealer_location'] = location
                                        # Extract just the city name in case location contains more info
                                        city = extract_city_from_address(location)
                                        if city:
                                            car_summary['location_city'] = city
                                        else:
                                            car_summary['location_city'] = location
                                        location_found = True
                                        
                                        # Try to geocode and calculate distance
                                        coords = get_coordinates(location)
                                        if coords:
                                            car_summary['latitude'] = coords[0]
                                            car_summary['longitude'] = coords[1]
                                            distance = calculate_distance_from_heerenveen(coords=coords)
                                            if distance and distance < 500:
                                                car_summary['distance_from_heerenveen_km'] = distance
                                        
                                        # The line before the location might be the dealer name
                                        # Get the next line in reversed iteration (which is previous in original)
                                        if i + 1 < len(lines):
                                            reversed_lines = list(reversed(lines))
                                            dealer_line = reversed_lines[i + 1].strip()
                                            # Check if it looks like a dealer name (not a spec or UI text)
                                            if (dealer_line and 
                                                dealer_line not in skip_words and
                                                not re.match(r'^\d+[\d.\-]*$', dealer_line) and
                                                'kW' not in dealer_line and 
                                                'cc' not in dealer_line and 
                                                '-deurs' not in dealer_line and
                                                not dealer_line.startswith('Bekijk deze auto op:')):
                                                car_summary['dealer_name'] = dealer_line
                                        break
                    
                    except Exception as e:
                        self.logger.debug(f"Could not extract specs: {e}")
                    
                    # Extract primary image
                    try:
                        img_elem = listing.find_element(By.CSS_SELECTOR, "img")
                        img_url = img_elem.get_attribute('src')
                        if img_url:
                            car_summary['primary_image_url'] = img_url
                    except Exception as e:
                        self.logger.debug(f"Could not extract image: {e}")
                    
                    # Infer vehicle type from model name if not already set
                    if 'vehicle_type' not in car_summary:
                        v_type = normalize_vehicle_type('', car_summary.get('model', ''), car_summary.get('make', ''))
                        if v_type:
                            car_summary['vehicle_type'] = v_type
                    
                    # Set source website
                    car_summary['source_website'] = self.website_name
                    
                    car_summaries.append(car_summary)
                    self.logger.debug(f"Extracted summary for: {car_summary.get('title', 'Unknown')} - {car_summary.get('year', 'N/A')} - €{car_summary.get('price', 'N/A')}")
                    
                except Exception as e:
                    self.logger.error(f"Error parsing listing {idx}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error loading listing page {url}: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('gaspedaal_listing_error')
        
        return car_summaries
    
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """
        Parse detailed car information from Gaspedaal.
        
        NOTE: Gaspedaal.nl is an aggregator that doesn't host detail pages.
        Clicking listings opens modals with redirect links to external dealer sites.
        Therefore, all data is extracted from the listing cards in parse_listing_page().
        This method just validates and returns the data without navigation.
        """
        car_data = car_summary.copy()
        
        # Ensure source website is set
        if 'source_website' not in car_data:
            car_data['source_website'] = self.website_name
        
        # Check if we have minimum required data
        if not car_data.get('title') or not car_data.get('price'):
            self.logger.warning(f"Listing missing required data (title or price): {car_data.get('external_id')}")
            return None
        
        # Upgrade Hybrid to PHEV if electric range is found
        # Regular hybrids don't have electric_range_km, only PHEVs do
        if car_data.get('fuel_type') == 'Hybrid' and car_data.get('electric_range_km'):
            car_data['fuel_type'] = 'PHEV'
            self.logger.info(f"Upgraded Hybrid to PHEV (electric range: {car_data['electric_range_km']} km)")
        
        # Check if vehicle should be excluded (too small for family use)
        if should_exclude_vehicle(car_data.get('make', ''), car_data.get('model', '')):
            self.logger.info(f"Excluding small car: {car_data.get('make')} {car_data.get('model')}")
            return None
        
        # Log what we have
        self.logger.info(f"Parsed: {car_data.get('year', 'N/A')} {car_data.get('make')} {car_data.get('model')} - €{car_data.get('price', 'N/A')} - {car_data.get('mileage_km', 'N/A')}km")
        
        return car_data


if __name__ == "__main__":
    # Test scraper
    scraper = GaspedaalScraper()
    scraper.run()
