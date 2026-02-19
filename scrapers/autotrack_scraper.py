"""
Autotrack.nl scraper for NL Car Tracker
"""
from scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.helpers import (
    extract_number, normalize_fuel_type, normalize_vehicle_type, normalize_model_name,
    get_coordinates, calculate_distance_from_heerenveen, should_exclude_vehicle,
    get_wltp_range, extract_city_from_address
)
from typing import List, Dict
import time
import re
import json
import os


class AutotrackScraper(BaseScraper):
    """Scraper for autotrack.nl"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        super().__init__(config_path, db_path)
        self.website_name = "autotrack.nl"
        self.base_url = "https://www.autotrack.nl"
        self.cookies_file = "cookies/autotrack_cookies.json"
    
    def load_cookies(self):
        """Load cookies from file to bypass privacy gate"""
        if not os.path.exists(self.cookies_file):
            self.logger.warning(f"Cookie file not found: {self.cookies_file}")
            return False
        
        try:
            # CRITICAL: Navigate to robots.txt FIRST to avoid privacy gate redirect
            # The privacy gate redirects happen during navigation to actual pages,
            # but robots.txt doesn't trigger the redirect. This allows us to:
            # 1. Get on the correct domain (www.autotrack.nl)
            # 2. Load cookies while on that domain
            # 3. Then navigate to actual pages with cookies already loaded
            robots_url = "https://www.autotrack.nl/robots.txt"
            self.logger.info(f"Navigating to {robots_url} to load cookies...")
            try:
                self.driver.get(robots_url)
                time.sleep(2)
            except TimeoutException:
                self.logger.error(f"Page load timeout (30s) loading robots.txt - cannot proceed")
                raise
            
            # Load cookies from file
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            # Add each cookie to the browser
            successful_cookies = 0
            for cookie in cookies:
                try:
                    # Remove fields that Selenium doesn't accept
                    cookie.pop('sameSite', None)
                    cookie.pop('storeId', None)
                    cookie.pop('id', None)
                    
                    self.driver.add_cookie(cookie)
                    successful_cookies += 1
                except Exception as e:
                    self.logger.debug(f"Could not add cookie {cookie.get('name', 'unknown')}: {e}")
            
            self.logger.info(f"Successfully loaded {successful_cookies}/{len(cookies)} cookies")
            
            # Verify we're still on the correct domain
            current_url = self.driver.current_url
            if "www.autotrack.nl" in current_url:
                self.logger.info("Cookies loaded successfully on www.autotrack.nl domain")
                return True
            else:
                self.logger.warning(f"Unexpected domain after cookie loading: {current_url}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error loading cookies: {e}")
            return False
    
    def build_search_url(self) -> List[str]:
        """Build search URLs for Autotrack based on configuration"""
        urls = []
        
        for vehicle in self.config['search']['vehicle_types']:
            for fuel in self.config['search']['fuel_types']:
                # Autotrack uses data filter format for fuel type
                # Vehicle type is checkbox-based (not in URL), so we'll search all and filter later
                
                # Map our fuel types to Autotrack's filter format
                fuel_map = {
                    "Full Electric": "elektriciteit",
                    "PHEV": "hybride"
                }
                
                fuel_slug = fuel_map.get(fuel['type'], 'elektriciteit')
                
                # Build URLs for multiple pages to get more results
                # AutoTrack pagination: pageNumber starts at 1
                # We'll fetch first 2 pages (60 cars) to get better coverage while maintaining reasonable scrape times
                for page_num in range(1, 3):
                    url = f"{self.base_url}/aanbod"
                    params = []
                    params.append(f"data.brandstofsoort.filter.0.slug={fuel_slug}")
                    params.append(f"pageNumber={page_num}")
                    params.append(f"pageSize=30")
                    params.append(f"sortField=relevance")
                    params.append(f"sortOrder=asc")
                    
                    # Note: Price, year, mileage, and vehicle type filtering will be done
                    # in parse_car_detail() since they're not easily added to URL
                    
                    full_url = url + "?" + "&".join(params)
                    urls.append(full_url)
                    self.logger.info(f"Built search URL (page {page_num}): {full_url}")
        
        return urls
    
    def parse_listing_page(self, url: str) -> List[Dict]:
        """Parse Autotrack listing page to extract basic car information"""
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
            
            # Wait for cookies to take effect and JavaScript to render
            time.sleep(3)
            
            # Check if we still hit the privacy gate
            page_source = self.driver.page_source
            if 'privacy-gate' in page_source.lower() or 'privacygate' in page_source.lower():
                self.logger.error("Still stuck on privacy gate despite cookies - manual intervention needed")
                self.logger.error("Please:")
                self.logger.error("1. Visit autotrack.nl in Chrome")
                self.logger.error("2. Accept the privacy consent")
                self.logger.error("3. Export cookies using EditThisCookie extension")
                self.logger.error("4. Save cookies to cookies/autotrack_cookies.json")
                
                if self.config['scraping']['browser']['screenshot_on_error']:
                    self._take_screenshot('autotrack_privacy_gate')
                    try:
                        with open('./tmp/autotrack_privacy_gate.html', 'w', encoding='utf-8') as f:
                            f.write(page_source)
                        self.logger.info("Saved privacy gate HTML to ./tmp/autotrack_privacy_gate.html")
                    except Exception as e:
                        self.logger.error(f"Failed to save page source: {e}")
                
                return car_summaries
            
            # Wait for car listings to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # Give page time to render JavaScript content
                time.sleep(1)
            except TimeoutException:
                self.logger.warning(f"Timeout waiting for page body on {url}")
                return car_summaries
            
            # Scroll to bottom to trigger lazy-loading of all car listings
            # AutoTrack uses React/Next.js and may progressively render cards
            self.logger.info("Scrolling to trigger all listings to render...")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Wait for all car listings to be fully rendered
            # AutoTrack loads 30 items per page via React/Next.js
            self.logger.info("Waiting for all listings to load...")
            try:
                # Wait up to 30 seconds for at least 25 car links to appear
                # (using 25 as threshold to handle pages with fewer than 30 results)
                WebDriverWait(self.driver, 30).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "a[href*='/a/']")) >= 25
                )
                # Give a bit more time for any final rendering
                time.sleep(1)
                self.logger.info("Car listings fully loaded")
            except TimeoutException:
                self.logger.warning("Timeout waiting for all listings to load - proceeding with whatever is available")
            
            # Extract car listing links
            # Autotrack uses links with pattern /a/{make}-{model}-{fuel}-{year}-{id}
            car_links = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/a/']")
            
            self.logger.info(f"Found {len(car_links)} links containing '/a/' in href")
            
            if not car_links:
                # Debug: Save page source
                self.logger.warning("No car listing links found - saving page source for debugging")
                if self.config['scraping']['browser']['screenshot_on_error']:
                    self._take_screenshot('autotrack_no_listings')
                    # Save page HTML to tmp directory
                    try:
                        with open('./tmp/autotrack_page_source.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        self.logger.info("Saved page source to ./tmp/autotrack_page_source.html")
                    except Exception as e:
                        self.logger.error(f"Failed to save page source: {e}")
                return car_summaries
            
            self.logger.info(f"Found {len(car_links)} potential car links")
            
            # Filter to unique detail page URLs
            seen_urls = set()
            
            # Parse each link
            for idx, link in enumerate(car_links[:30]):  # Limit to first 30 to avoid duplicates
                try:
                    detail_url = link.get_attribute('href')
                    
                    # Skip if we've already seen this URL
                    if detail_url in seen_urls:
                        continue
                    
                    # Validate URL pattern: /a/{brand}-{model}-{fuel}-{year}-{id}
                    if not re.match(r'.*/a/[\w-]+-\d{4}-\d+', detail_url):
                        continue
                    
                    seen_urls.add(detail_url)
                    
                    if not detail_url.startswith('http'):
                        detail_url = self.base_url + detail_url
                    
                    car_summary = {}
                    car_summary['listing_url'] = detail_url
                    
                    # Extract external_id from URL (last part after /a/)
                    # URL pattern: /a/{make}-{model}-{fuel}-{year}-{id}
                    external_id = detail_url.split('/a/')[-1].split('?')[0]
                    car_summary['external_id'] = f"autotrack_{external_id}"
                    
                    # Extract basic info from link text/context
                    try:
                        # Get title from link text or parent element
                        title = link.text.strip()
                        if not title:
                            # Try to get from parent element
                            parent = link.find_element(By.XPATH, "./..")
                            title = parent.text.strip().split('\n')[0]  # Take first line
                        
                        if title:
                            # Remove pagination text pattern (e.g., "1 / 20", "2 / 44", etc.)
                            # Pattern: digit(s) + optional space + "/" + optional space + digit(s)
                            title = re.sub(r'^\d+\s*/\s*\d+\s*', '', title).strip()
                            
                            # Check if title is still valid after cleaning
                            if title:
                                car_summary['title'] = title
                                
                                # Try to parse make and model from title
                                title_parts = title.split()
                                if len(title_parts) >= 2:
                                    car_summary['make'] = title_parts[0]
                                    raw_model = ' '.join(title_parts[1:])
                                    car_summary['model'] = normalize_model_name(raw_model)
                            else:
                                car_summary['title'] = "Unknown"
                        else:
                            car_summary['title'] = "Unknown"
                    except:
                        car_summary['title'] = "Unknown"
                    
                    # Extract info from URL pattern: /a/{make}-{model}-{fuel}-{year}-{id}
                    url_parts = detail_url.split('/a/')[-1].split('-')
                    if len(url_parts) >= 4:
                        try:
                            # Last part is ID, second-to-last is year
                            year = int(url_parts[-2])
                            if 1900 < year < 2030:
                                car_summary['year'] = year
                        except (ValueError, IndexError):
                            pass
                    
                    car_summaries.append(car_summary)
                    self.logger.debug(f"Extracted summary for: {car_summary.get('title', 'Unknown')}")
                    
                except Exception as e:
                    self.logger.error(f"Error parsing link {idx}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error loading listing page {url}: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('autotrack_listing_error')
        
        return car_summaries
    
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """Parse detailed car information from Autotrack detail page"""
        car_data = car_summary.copy()
        car_data['source_website'] = self.website_name
        
        # Remove 'title' field - not in database schema
        car_data.pop('title', None)
        
        # Extract make/model/fuel from URL as fallback if not already set
        # URL pattern: /a/{make}-{model}-{fuel}-{year}-{id}
        # Example: /a/volkswagen-id-4-elektriciteit-2020-58268930
        url_path = car_summary['listing_url'].split('/a/')[-1].split('?')[0]
        url_parts = url_path.split('-')
        
        # Map Autotrack fuel types to our normalized fuel types
        # Note: 'hybride' includes both PHEV and regular hybrid
        # We'll check for electric_range_km later to distinguish them
        fuel_type_map = {
            'elektriciteit': 'Full Electric',
            'hybride': 'Hybrid',  # Will be upgraded to PHEV if electric_range_km is found
            'benzine': None,  # Rejected - not electric/PHEV
            'diesel': None    # Rejected - not electric/PHEV
        }
        
        if len(url_parts) >= 4:
            # Extract fuel type from URL (it's more reliable than page parsing)
            for part in url_parts:
                if part in fuel_type_map:
                    normalized_fuel = fuel_type_map[part]
                    
                    # Skip benzine/diesel cars immediately (fuel_type_map returns None for these)
                    if normalized_fuel is None:
                        self.logger.info(f"Skipping benzine/diesel car from URL: {car_summary['listing_url']}")
                        return None
                    
                    car_data['fuel_type'] = normalized_fuel
                    self.logger.debug(f"Extracted fuel type from URL: {normalized_fuel}")
                    break
            
            # Extract make/model if not already set
            if not car_data.get('make') or not car_data.get('model'):
                # First part is make
                make = url_parts[0].capitalize()
                car_data['make'] = make
                
                # Model is everything between make and fuel type
                # Find where fuel type starts (elektriciteit, hybride, etc.)
                fuel_markers = ['elektriciteit', 'hybride', 'benzine', 'diesel']
                model_parts = []
                
                for i, part in enumerate(url_parts[1:], 1):
                    if part in fuel_markers:
                        break
                    # Check if it's the year (4 digits)
                    if part.isdigit() and len(part) == 4:
                        break
                    model_parts.append(part)
                
                if model_parts:
                    model = ' '.join(model_parts).title()
                    car_data['model'] = model
                    self.logger.info(f"Extracted from URL: {make} {model}")
        
        try:
            # Navigate to detail page with timeout protection
            try:
                self.driver.get(car_summary['listing_url'])
                self._random_delay(2, 4)
            except TimeoutException:
                self.logger.warning(f"Page load timeout (30s) on detail page: {car_summary['listing_url']}")
                return None
            
            # Wait for page to load and JavaScript to render critical elements
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                # Give time for JavaScript to fully render the page
                time.sleep(3)
                self.logger.debug("Waited for page rendering to complete")
            except TimeoutException:
                self.logger.warning(f"Timeout waiting for page body: {car_summary['listing_url']}")
                return None
            
            # Extract price first - it's required
            # Wait for price elements to be rendered by JavaScript
            try:
                # Try waiting for common price-related elements first
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda d: '€' in d.find_element(By.TAG_NAME, "body").text
                    )
                    self.logger.debug("Price symbol detected on page")
                except TimeoutException:
                    self.logger.warning("Timeout waiting for price symbol - proceeding anyway")
                
                # Small additional delay for JavaScript to finish
                time.sleep(1)
                
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                
                # Enhanced unavailability detection (multi-signal approach)
                # Autotrack.nl shows various unavailability messages and may remove key elements
                try:
                    is_unavailable = False
                    page_text_lower = page_text.lower()
                    
                    # 1. Check for unavailability text patterns (case-insensitive)
                    # Autotrack-specific patterns (DPG Media)
                    unavailability_patterns = [
                        'niet meer beschikbaar',
                        'helaas niet meer beschikbaar',
                        'is verkocht',
                        'reeds verkocht',
                        'deze advertentie is niet meer beschikbaar',
                        'deze auto is niet meer beschikbaar',
                        'no longer available',
                        'already sold',
                        'al verkocht',
                        'deze auto is verkocht'
                    ]
                    
                    text_match_found = any(pattern in page_text_lower for pattern in unavailability_patterns)
                    
                    # 2. Check if page has very little content (indicator of unavailability page)
                    content_too_sparse = len(page_text.strip()) < 200
                    
                    # 3. Check if price is found (missing price suggests unavailability)
                    price_found_in_text = '€' in page_text
                    
                    # Determine unavailability based on multiple signals
                    if text_match_found:
                        # High confidence: explicit unavailability message
                        is_unavailable = True
                        self.logger.info(f"Car unavailable (text match): {car_summary['listing_url']}")
                    elif content_too_sparse and not price_found_in_text:
                        # Medium confidence: sparse content + no price
                        is_unavailable = True
                        self.logger.info(f"Car unavailable (sparse content + no price): {car_summary['listing_url']}")
                    
                    if is_unavailable:
                        car_data['is_available'] = False
                        # Still try to extract any available data, but mark as unavailable
                    else:
                        car_data['is_available'] = True
                        
                except Exception as e:
                    self.logger.warning(f"Error checking unavailability: {e}")
                    # Default to available if check fails
                    car_data['is_available'] = True
                
                # Look for price patterns in the page
                # Common patterns: €45.000, € 45.000, 45.000 €, €45000
                price_patterns = [
                    r'€\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)',  # €45.000 or €45.000,00
                    r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€',  # 45.000 €
                ]
                
                for pattern in price_patterns:
                    price_matches = re.findall(pattern, page_text)
                    for match in price_matches:
                        # Clean and convert price
                        price_str = match.replace('.', '').replace(',', '.')
                        try:
                            price = float(price_str)
                            # Sanity check: price should be between €1,000 and €200,000
                            if 1000 < price < 200000:
                                car_data['price'] = price
                                self.logger.info(f"Found price: €{price:,.0f}")
                                break
                        except ValueError:
                            continue
                    if car_data.get('price'):
                        break
                
                if not car_data.get('price'):
                    self.logger.warning(f"Could not extract price from {car_summary['listing_url']}")
                    # Try to find price in meta tags or specific elements
                    try:
                        price_elems = self.driver.find_elements(By.CSS_SELECTOR, 
                            "[class*='price'], [class*='Price'], h1, h2, h3")
                        for elem in price_elems:
                            elem_text = elem.text
                            for pattern in price_patterns:
                                price_match = re.search(pattern, elem_text)
                                if price_match:
                                    price_str = price_match.group(1).replace('.', '').replace(',', '.')
                                    try:
                                        price = float(price_str)
                                        if 1000 < price < 200000:
                                            car_data['price'] = price
                                            self.logger.info(f"Found price in element: €{price:,.0f}")
                                            break
                                    except ValueError:
                                        continue
                            if car_data.get('price'):
                                break
                    except Exception as e:
                        self.logger.debug(f"Error searching price in elements: {e}")
                
            except Exception as e:
                self.logger.error(f"Error extracting price: {e}")
            
            # Extract specifications from detail page
            # Autotrack uses expandable sections with paragraph pairs (label/value)
            try:
                # Look for all paragraph elements
                all_paragraphs = self.driver.find_elements(By.TAG_NAME, "p")
                
                specs = {}
                # Parse paragraph pairs (label followed by value)
                for i in range(len(all_paragraphs) - 1):
                    try:
                        label = all_paragraphs[i].text.strip()
                        value = all_paragraphs[i + 1].text.strip()
                        
                        # Skip if label or value is empty or too long
                        if not label or not value or len(label) > 100 or len(value) > 200:
                            continue
                        
                        # Store as spec if label looks like a spec name
                        if ':' not in label and len(label.split()) <= 5:
                            specs[label.lower()] = value
                    except:
                        continue
                
                self.logger.debug(f"Extracted {len(specs)} specifications")
                
                # Parse specifications
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
                    
                    # Priority 1: Actieradius praktijk (practical/real-world range - most accurate)
                    elif 'actieradius praktijk' in key.lower() or 'praktijk actieradius' in key.lower():
                        practical_range = extract_number(value)
                        if practical_range:
                            car_data['electric_range_km'] = practical_range  # Use electric_range_km for practical range
                            self.logger.debug(f"Using practical range: {practical_range} km")
                    
                    # Priority 2: Elektrisch bereik (electric range - shown prominently on page)
                    elif 'elektrisch bereik' in key.lower() and 'electric_range_km' not in car_data:
                        e_range = extract_number(value)
                        if e_range:
                            car_data['electric_range_km'] = e_range
                            self.logger.debug(f"Using elektrisch bereik: {e_range} km")
                    
                    # Priority 3: Actieradius/bereik (WLTP official range - fallback)
                    elif ('bereik' in key.lower() or 'actieradius' in key.lower()) and 'praktijk' not in key.lower() and 'elektrisch' not in key.lower():
                        range_km = extract_number(value)
                        if range_km:
                            car_data['range_km'] = range_km
                            self.logger.debug(f"Using actieradius/bereik: {range_km} km")
                    
                    elif 'carrosserie' in key or 'type auto' in key:
                        v_type = normalize_vehicle_type(value, car_data.get('model', ''))
                        if v_type:
                            car_data['vehicle_type'] = v_type
                    
                    elif 'kleur' in key:
                        car_data['color'] = value
                    
                    elif 'transmissie' in key or 'versnellingsbak' in key:
                        car_data['transmission'] = value
                    
                    elif 'vermogen' in key:
                        kw = extract_number(value.split('kW')[0] if 'kW' in value else '')
                        hp = extract_number(value.split('pk')[0] if 'pk' in value else '')
                        if kw:
                            car_data['power_kw'] = kw
                        if hp:
                            car_data['power_hp'] = hp
                    
                    elif 'inhoud kofferbak' in key or 'kofferbakinhoud' in key:
                        # Handle range format: "543 - 1.575 liter" or single value
                        # Extract first number (seats up position, smaller capacity)
                        numbers = re.findall(r'(\d+)', value)
                        if numbers:
                            storage = int(numbers[0])
                            car_data['storage_capacity_liters'] = storage
                            self.logger.info(f"Found storage capacity: {storage} liters from '{value}'")
                    
                    elif 'bagageruimte' in key or 'kofferruimte' in key:
                        # Backup field names
                        storage = extract_number(value)
                        if storage:
                            car_data['storage_capacity_liters'] = storage
                    
                    elif 'beenruimte' in key and 'achter' in key:
                        legroom = extract_number(value)
                        if legroom:
                            car_data['rear_legroom_mm'] = legroom
                    
                    elif 'aantal zitplaatsen' in key or 'zitplaatsen' in key:
                        seats = extract_number(value)
                        if seats:
                            car_data['seats'] = seats
                            self.logger.debug(f"Extracted seats: {seats}")
                    
                    elif 'aantal deuren' in key or 'deuren' in key:
                        doors = extract_number(value)
                        if doors:
                            car_data['doors'] = doors
                            self.logger.debug(f"Extracted doors: {doors}")
            
            except Exception as e:
                self.logger.error(f"Error parsing specifications: {e}")
            
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
            
            # Extract features/equipment
            try:
                features = []
                # Look for feature lists in Mantine UI components
                # Features are in: li.m_abb6bec2.mantine-List-item > div > span.mantine-List-itemLabel
                feature_selectors = [
                    "li.mantine-List-item span.mantine-List-itemLabel",  # Primary selector for Mantine UI
                    "li[class*='mantine-List-item'] span[class*='itemLabel']",  # Backup selector
                    "li[class*='feature']",  # Legacy selector
                    "div[class*='equipment'] li",
                    "ul[class*='feature'] li"
                ]
                
                for selector in feature_selectors:
                    feature_elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if feature_elems:
                        for elem in feature_elems:
                            feature_text = elem.text.strip()
                            if feature_text and len(feature_text) < 100 and len(feature_text) > 2:
                                features.append(feature_text)
                        if features:  # Only break if we found features
                            break
                
                car_data['features'] = list(set(features))  # Remove duplicates
                self.logger.info(f"Extracted {len(car_data['features'])} unique features")
            
            except Exception as e:
                self.logger.error(f"Error parsing features: {e}")
                car_data['features'] = []
            
            # Extract location
            try:
                location_text = None
                
                # Look for dealer location
                location_selectors = [
                    "[class*='dealer-location']",
                    "[class*='location']",
                    ".address"
                ]
                
                for selector in location_selectors:
                    try:
                        location_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        location_text = location_elem.text.strip()
                        if location_text:
                            break
                    except:
                        continue
                
                # Fallback: search for Dutch postal code pattern
                if not location_text:
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    # Dutch postal codes: 1000-9999 followed by 2 capital letters
                    # Require space after postal code and city must start with letter
                    postal_match = re.search(r'([1-9]\d{3}\s*[A-Z]{2})\s+([A-Za-z][A-Za-z\s-]+)', page_text)
                    if postal_match:
                        postal_code = postal_match.group(1).replace(' ', '')
                        city = postal_match.group(2)[:50].strip()
                        
                        # Validate: exclude if it looks like a year (1900-2199)
                        first_four = postal_code[:4]
                        if first_four.isdigit():
                            year_num = int(first_four)
                            if not (1900 <= year_num <= 2199):
                                location_text = f"{postal_code} {city}".strip()
                                self.logger.debug(f"Extracted location from page text: {location_text}")
                            else:
                                self.logger.debug(f"Rejected postal code {postal_code} (looks like year {year_num})")
                
                if location_text:
                    car_data['dealer_location'] = location_text
                    # Extract just the city name from the full address
                    city = extract_city_from_address(location_text)
                    if city:
                        car_data['location_city'] = city
                    
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
                dealer_selectors = ["[class*='dealer-name']", "h2", "h3"]
                for selector in dealer_selectors:
                    try:
                        dealer_elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                        dealer_text = dealer_elem.text.strip()
                        if dealer_text and len(dealer_text) < 100:
                            car_data['dealer_name'] = dealer_text
                            break
                    except:
                        continue
            except Exception as e:
                self.logger.debug(f"Could not extract dealer name: {e}")
            
            # Extract images
            try:
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='autotrack'], img[class*='car']")
                image_urls = []
                for img in image_elements:
                    src = img.get_attribute('src')
                    if src and 'logo' not in src.lower():
                        image_urls.append(src)
                
                car_data['image_urls'] = image_urls[:10]  # Limit to 10 images
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
            # Regular hybrids don't have electric_range_km, only PHEVs do
            if car_data.get('fuel_type') == 'Hybrid' and car_data.get('electric_range_km'):
                car_data['fuel_type'] = 'PHEV'
                self.logger.info(f"Upgraded Hybrid to PHEV (electric range: {car_data['electric_range_km']} km)")
            
            # Validate required fields before returning
            required_fields = {
                'make': car_data.get('make'),
                'model': car_data.get('model'),
                'year': car_data.get('year'),
                'price': car_data.get('price'),
                'mileage_km': car_data.get('mileage_km'),
                'fuel_type': car_data.get('fuel_type')
            }
            
            missing_fields = [field for field, value in required_fields.items() if value is None]
            
            if missing_fields:
                self.logger.error(f"Missing required fields: {', '.join(missing_fields)}")
                self.logger.error(f"Extracted data: make={car_data.get('make')}, model={car_data.get('model')}, "
                                f"year={car_data.get('year')}, price={car_data.get('price')}, "
                                f"mileage={car_data.get('mileage_km')}, fuel={car_data.get('fuel_type')}")
                self.logger.error(f"URL: {car_summary['listing_url']}")
                
                # If we're missing critical fields, try to save HTML for debugging
                if self.config['scraping']['browser']['screenshot_on_error']:
                    self._take_screenshot('autotrack_missing_fields')
                    try:
                        with open('./tmp/autotrack_missing_fields.html', 'w', encoding='utf-8') as f:
                            f.write(self.driver.page_source)
                        self.logger.info("Saved page HTML to ./tmp/autotrack_missing_fields.html")
                    except Exception as e:
                        self.logger.debug(f"Could not save HTML: {e}")
                
                return None
            
            self.logger.info(f"Successfully extracted: {car_data.get('make')} {car_data.get('model')} "
                           f"({car_data.get('year')}) - €{car_data.get('price'):,.0f} - "
                           f"{car_data.get('mileage_km'):,} km")
            
            # Check if vehicle should be excluded (too small for family use)
            if should_exclude_vehicle(car_data.get('make', ''), car_data.get('model', '')):
                self.logger.info(f"Excluding small car: {car_data.get('make')} {car_data.get('model')}")
                return None
            
            return car_data
        
        except Exception as e:
            self.logger.error(f"Error parsing detail page: {e}")
            if self.config['scraping']['browser']['screenshot_on_error']:
                self._take_screenshot('autotrack_detail_error')
            return None


if __name__ == "__main__":
    # Test scraper
    scraper = AutotrackScraper()
    scraper.run()
