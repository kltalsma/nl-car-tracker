"""
Das-import.nl scraper for NL Car Tracker
"""
from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.helpers import (
    extract_number, normalize_fuel_type, normalize_vehicle_type, normalize_model_name,
    get_coordinates, calculate_distance_from_heerenveen, should_exclude_vehicle,
    get_wltp_range
)
from typing import List, Dict
import time
import re
import json
import os


class DasImportScraper(BaseScraper):
    """Scraper for das-import.nl"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        super().__init__(config_path, db_path)
        self.website_name = "das-import.nl"
        self.base_url = "https://www.das-import.nl"
        self.cookies_file = "cookies/dasimport_cookies.json"
    
    def load_cookies(self):
        """Load cookies from file to bypass privacy gate"""
        if not os.path.exists(self.cookies_file):
            self.logger.warning(f"Cookie file not found: {self.cookies_file}")
            return False
        
        try:
            # First navigate to base domain to set cookies
            self.driver.get(self.base_url)
            time.sleep(2)
            
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
    
    def build_search_url(self) -> List[str]:
        """Build search URLs for Das-import based on configuration"""
        urls = []
        
        # Das-import.nl typically has a simpler URL structure
        # We'll need to explore the actual site structure, but let's start with common patterns
        
        for vehicle in self.config['search']['vehicle_types']:
            for fuel in self.config['search']['fuel_types']:
                # Map fuel types - will need to adjust based on actual site
                fuel_map = {
                    "Full Electric": "elektrisch",
                    "PHEV": "hybride"
                }
                
                # Map vehicle types
                vehicle_map = {
                    "SUV": "suv",
                    "Stationwagon": "station"
                }
                
                fuel_param = fuel_map.get(fuel['type'], 'elektrisch')
                vehicle_param = vehicle_map.get(vehicle['type'], 'suv')
                
                # Build URL - trying common Dutch car site patterns
                # Pattern 1: /occasions with query params
                url = f"{self.base_url}/occasions"
                params = []
                params.append(f"fuel={fuel_param}")
                params.append(f"type={vehicle_param}")
                params.append(f"price_max={vehicle['max_price']}")
                params.append(f"year_min={self.config['search']['min_year']}")
                params.append(f"mileage_max={self.config['search']['max_mileage_km']}")
                
                full_url = url + "?" + "&".join(params)
                urls.append(full_url)
                self.logger.info(f"Built search URL: {full_url}")
        
        # Also add a generic search URL without filters to explore
        urls.append(f"{self.base_url}/occasions")
        urls.append(f"{self.base_url}/aanbod")  # Alternative path
        
        return urls
    
    def parse_listing_page(self, url: str) -> List[Dict]:
        """Parse Das-import listing page to extract basic car information"""
        car_summaries = []
        
        try:
            # Load cookies before first request if available
            if not hasattr(self, '_cookies_loaded'):
                self.load_cookies()
                self._cookies_loaded = True
            
            self.logger.info(f"Loading listing page: {url}")
            self.driver.get(url)
            self._random_delay(3, 5)
            
            # Wait for page to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(3)  # Additional time for JavaScript
            except TimeoutException:
                self.logger.warning(f"Timeout waiting for page on {url}")
                return car_summaries
            
            # Try multiple selectors for car listings
            listing_selectors = [
                "article.car-listing",
                "article[data-car-id]",
                "div.car-item",
                "div.vehicle-item",
                "article.vehicle",
                "div[class*='listing']",
                "div[class*='car']",
                "a[href*='/auto/']",
                "a[href*='/occasions/']",
                "a[href*='/vehicle/']"
            ]
            
            listings = []
            for selector in listing_selectors:
                try:
                    listings = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if listings and len(listings) > 2:  # Need at least a few to be valid
                        self.logger.info(f"Found {len(listings)} listings using selector: {selector}")
                        break
                except:
                    continue
            
            if not listings:
                self.logger.warning("No car listings found - saving debug info")
                if self.config['scraping']['browser']['screenshot_on_error']:
                    self._take_screenshot('dasimport_no_listings')
                    try:
                        with open('./tmp/dasimport_page_source.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        self.logger.info("Saved page source to ./tmp/dasimport_page_source.html")
                    except Exception as e:
                        self.logger.error(f"Failed to save page source: {e}")
                
                return car_summaries
            
            # Parse each listing
            seen_urls = set()
            for idx, listing in enumerate(listings[:30]):  # Limit to first 30
                try:
                    car_summary = {}
                    
                    # Extract detail page URL
                    link_selectors = ["a[href*='/auto/']", "a[href*='/occasions/']", "a[href*='/vehicle/']", "a"]
                    detail_url = None
                    
                    for link_sel in link_selectors:
                        try:
                            if listing.tag_name == 'a':
                                link_elem = listing
                            else:
                                link_elem = listing.find_element(By.CSS_SELECTOR, link_sel)
                            detail_url = link_elem.get_attribute('href')
                            if detail_url:
                                break
                        except:
                            continue
                    
                    if not detail_url or detail_url in seen_urls:
                        continue
                    
                    seen_urls.add(detail_url)
                    
                    if not detail_url.startswith('http'):
                        detail_url = self.base_url + detail_url
                    
                    car_summary['listing_url'] = detail_url
                    
                    # Extract external_id from URL
                    external_id = detail_url.split('/')[-1].split('?')[0]
                    car_summary['external_id'] = f"dasimport_{external_id}"
                    
                    # Extract basic info from listing card
                    try:
                        # Try to find title
                        title_selectors = ["h2", "h3", ".car-title", "[class*='title']", ".vehicle-name"]
                        for title_sel in title_selectors:
                            try:
                                title_elem = listing.find_element(By.CSS_SELECTOR, title_sel)
                                title = title_elem.text.strip()
                                if title and len(title) > 3:
                                    car_summary['title'] = title
                                    
                                    # Parse make and model from title
                                    title_parts = title.split()
                                    if len(title_parts) >= 2:
                                        car_summary['make'] = title_parts[0]
                                        raw_model = ' '.join(title_parts[1:])
                                        car_summary['model'] = normalize_model_name(raw_model)
                                    break
                            except:
                                continue
                    except:
                        pass
                    
                    # Extract price
                    try:
                        price_selectors = ["[class*='price']", ".price", "[data-price]", "span:contains('€')"]
                        for price_sel in price_selectors:
                            try:
                                price_elem = listing.find_element(By.CSS_SELECTOR, price_sel)
                                price_text = price_elem.text.strip()
                                if '€' in price_text:
                                    price = extract_number(price_text)
                                    if price:
                                        car_summary['price'] = price
                                        break
                            except:
                                continue
                    except:
                        pass
                    
                    # Extract primary image
                    try:
                        img_elem = listing.find_element(By.CSS_SELECTOR, "img")
                        img_url = img_elem.get_attribute('src')
                        if img_url and 'logo' not in img_url.lower():
                            car_summary['primary_image_url'] = img_url
                    except:
                        pass
                    
                    car_summaries.append(car_summary)
                    self.logger.debug(f"Extracted summary for: {car_summary.get('title', 'Unknown')}")
                    
                except Exception as e:
                    self.logger.error(f"Error parsing listing {idx}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error loading listing page {url}: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('dasimport_listing_error')
        
        return car_summaries
    
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """Parse detailed car information from Das-import detail page"""
        car_data = car_summary.copy()
        car_data['source_website'] = self.website_name
        
        try:
            # Navigate to detail page
            self.driver.get(car_summary['listing_url'])
            self._random_delay(2, 4)
            
            # Wait for page to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                time.sleep(3)
            except TimeoutException:
                self.logger.warning(f"Timeout on detail page: {car_summary['listing_url']}")
                return None
            
            # Extract specifications
            try:
                # Try common spec table structures
                spec_elements = self.driver.find_elements(By.CSS_SELECTOR, "dt, .spec-label, [class*='spec']")
                spec_values = self.driver.find_elements(By.CSS_SELECTOR, "dd, .spec-value")
                
                specs = {}
                for i, elem in enumerate(spec_elements):
                    if i < len(spec_values):
                        key = elem.text.strip().lower()
                        value = spec_values[i].text.strip()
                        specs[key] = value
                
                # If no specs found with dt/dd, try paragraph pairs
                if not specs:
                    all_paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                    for i in range(len(all_paragraphs) - 1):
                        try:
                            label = all_paragraphs[i].text.strip()
                            value = all_paragraphs[i + 1].text.strip()
                            
                            if not label or not value or len(label) > 100 or len(value) > 200:
                                continue
                            
                            if ':' not in label and len(label.split()) <= 5:
                                specs[label.lower()] = value
                        except:
                            continue
                
                self.logger.debug(f"Extracted {len(specs)} specifications")
                
                # Parse specifications (same logic as other scrapers)
                for key, value in specs.items():
                    if 'jaar' in key or 'bouwjaar' in key:
                        year_match = re.search(r'(\d{4})', value)
                        if year_match:
                            year = int(year_match.group(1))
                            if year > 1900:
                                car_data['year'] = year
                    
                    elif 'kilometerstand' in key or 'km-stand' in key or 'km stand' in key:
                        mileage = extract_number(value)
                        if mileage:
                            car_data['mileage_km'] = mileage
                    
                    elif 'brandstof' in key:
                        fuel = normalize_fuel_type(value, model_str=car_data.get('model'))
                        if fuel:
                            car_data['fuel_type'] = fuel
                    
                    elif 'bereik' in key or 'actieradius' in key:
                        range_km = extract_number(value)
                        if range_km:
                            car_data['range_km'] = range_km
                    
                    elif 'elektrisch bereik' in key:
                        e_range = extract_number(value)
                        if e_range:
                            car_data['electric_range_km'] = e_range
                    
                    elif 'carrosserie' in key or 'type' in key or 'body' in key:
                        v_type = normalize_vehicle_type(value, car_data.get('model', ''))
                        if v_type:
                            car_data['vehicle_type'] = v_type
                    
                    elif 'kleur' in key or 'color' in key:
                        car_data['color'] = value
                    
                    elif 'transmissie' in key or 'versnellingsbak' in key:
                        car_data['transmission'] = value
                    
                    elif 'vermogen' in key or 'power' in key:
                        kw = extract_number(value.split('kW')[0] if 'kW' in value else '')
                        hp = extract_number(value.split('pk')[0] if 'pk' in value else '')
                        if kw:
                            car_data['power_kw'] = kw
                        if hp:
                            car_data['power_hp'] = hp
                    
                    elif 'bagageruimte' in key or 'kofferruimte' in key:
                        storage = extract_number(value)
                        if storage:
                            car_data['storage_capacity_liters'] = storage
                    
                    elif 'beenruimte' in key and 'achter' in key:
                        legroom = extract_number(value)
                        if legroom:
                            car_data['rear_legroom_mm'] = legroom
                    
                    elif 'aantal zitplaatsen' in key or 'zitplaatsen' in key or 'seats' in key:
                        seats = extract_number(value)
                        if seats:
                            car_data['seats'] = seats
                    
                    elif 'aantal deuren' in key or 'deuren' in key or 'doors' in key:
                        doors = extract_number(value)
                        if doors:
                            car_data['doors'] = doors
                    
                    # Extract price if not already set
                    elif 'prijs' in key or 'price' in key:
                        if not car_data.get('price'):
                            price = extract_number(value)
                            if price:
                                car_data['price'] = price
            
            except Exception as e:
                self.logger.error(f"Error parsing specifications: {e}")
            
            # WLTP range fallback
            fuel = car_data.get('fuel_type', '')
            if fuel in ['Full Electric', 'PHEV', 'Hybrid']:
                if fuel == 'Full Electric' and not car_data.get('range_km'):
                    wltp_range = get_wltp_range(car_data.get('make', ''), car_data.get('model', ''), fuel)
                    if wltp_range:
                        car_data['range_km'] = wltp_range
                        car_data['range_source'] = 'wltp_estimate'
                        self.logger.info(f"  - Using WLTP range estimate: {wltp_range} km")
                
                if fuel in ['PHEV', 'Hybrid'] and not car_data.get('electric_range_km'):
                    wltp_range = get_wltp_range(car_data.get('make', ''), car_data.get('model', ''), fuel)
                    if wltp_range:
                        car_data['electric_range_km'] = wltp_range
                        car_data['range_source'] = 'wltp_estimate'
                        self.logger.info(f"  - Using WLTP electric range estimate: {wltp_range} km")
            
            # Extract features/equipment
            try:
                features = []
                feature_selectors = [
                    "li[class*='feature']",
                    "div[class*='equipment'] li",
                    "ul[class*='feature'] li",
                    ".features li",
                    "ul li"
                ]
                
                for selector in feature_selectors:
                    feature_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if feature_elems:
                        for elem in feature_elems:
                            feature_text = elem.text.strip()
                            if feature_text and len(feature_text) < 100 and len(feature_text) > 2:
                                features.append(feature_text)
                        if len(features) > 5:  # Found meaningful features
                            break
                
                car_data['features'] = list(set(features))
                self.logger.debug(f"Extracted {len(features)} features")
            
            except Exception as e:
                self.logger.error(f"Error parsing features: {e}")
                car_data['features'] = []
            
            # Extract location
            try:
                location_text = None
                
                location_selectors = [
                    "[class*='dealer-location']",
                    "[class*='location']",
                    ".address",
                    "[class*='address']"
                ]
                
                for selector in location_selectors:
                    try:
                        location_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        location_text = location_elem.text.strip()
                        if location_text:
                            break
                    except:
                        continue
                
                # Fallback: search for Dutch postal code
                if not location_text:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    postal_match = re.search(r'([1-9]\d{3}\s*[A-Z]{2})\s+([A-Za-z][A-Za-z\s-]+)', page_text)
                    if postal_match:
                        postal_code = postal_match.group(1).replace(' ', '')
                        city = postal_match.group(2)[:50].strip()
                        
                        # Validate: exclude if it looks like a year
                        first_four = postal_code[:4]
                        if first_four.isdigit():
                            year_num = int(first_four)
                            if not (1900 <= year_num <= 2199):
                                location_text = f"{postal_code} {city}".strip()
                
                if location_text:
                    car_data['dealer_location'] = location_text
                    car_data['location_city'] = location_text
                    
                    # Geocode and calculate distance
                    coords = get_coordinates(location_text)
                    if coords:
                        car_data['latitude'] = coords[0]
                        car_data['longitude'] = coords[1]
                        distance = calculate_distance_from_heerenveen(coords=coords)
                        if distance and distance < 500:
                            car_data['distance_from_heerenveen_km'] = distance
                            self.logger.debug(f"Distance: {distance:.2f} km")
            
            except Exception as e:
                self.logger.error(f"Error parsing location: {e}")
            
            # Extract dealer name
            try:
                dealer_selectors = ["[class*='dealer-name']", "h1", "h2", "h3"]
                for selector in dealer_selectors:
                    try:
                        dealer_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        dealer_text = dealer_elem.text.strip()
                        if dealer_text and len(dealer_text) < 100 and 'das' in dealer_text.lower():
                            car_data['dealer_name'] = dealer_text
                            break
                    except:
                        continue
            except Exception as e:
                self.logger.debug(f"Could not extract dealer name: {e}")
            
            # Extract images
            try:
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='das'], img[class*='car'], img[class*='vehicle']")
                image_urls = []
                for img in image_elements:
                    src = img.get_attribute('src')
                    if src and 'logo' not in src.lower():
                        image_urls.append(src)
                
                car_data['image_urls'] = image_urls[:10]
                if not car_data.get('primary_image_url') and image_urls:
                    car_data['primary_image_url'] = image_urls[0]
            except Exception as e:
                self.logger.error(f"Error parsing images: {e}")
            
            # Fallback: if still no vehicle_type, check the model name
            if 'vehicle_type' not in car_data or not car_data['vehicle_type']:
                v_type = normalize_vehicle_type('', car_data.get('model', ''), car_data.get('make', ''))
                if v_type:
                    car_data['vehicle_type'] = v_type
            
            # Upgrade Hybrid to PHEV if electric range is found
            if car_data.get('fuel_type') == 'Hybrid' and car_data.get('electric_range_km'):
                car_data['fuel_type'] = 'PHEV'
                self.logger.info(f"Upgraded Hybrid to PHEV (electric range: {car_data['electric_range_km']} km)")
            
            # Check if vehicle should be excluded (too small for family use)
            if should_exclude_vehicle(car_data.get('make', ''), car_data.get('model', '')):
                self.logger.info(f"Excluding small car: {car_data.get('make')} {car_data.get('model')}")
                return None
            
            return car_data
        
        except Exception as e:
            self.logger.error(f"Error parsing detail page: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('dasimport_detail_error')
            return None


if __name__ == "__main__":
    # Test scraper
    scraper = DasImportScraper()
    scraper.run()
