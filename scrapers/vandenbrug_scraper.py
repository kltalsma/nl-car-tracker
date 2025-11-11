"""
Van den Brug dealer scraper for NL Car Tracker
Hybrid scraper: API for listing, HTML parsing for details
"""
from scrapers.base_scraper import BaseScraper
from typing import List, Dict
from utils.helpers import (
    normalize_fuel_type,
    normalize_vehicle_type,
    normalize_model_name,
    extract_number,
    extract_price,
    calculate_distance_from_heerenveen,
    get_coordinates,
    should_exclude_vehicle
)
import requests
import time
from bs4 import BeautifulSoup
import re


class VandenBrugScraper(BaseScraper):
    """Scraper for Van den Brug dealer website (vandenbrug.nl) using Datamotive API"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        super().__init__(config_path, db_path)
        self.website_name = "vandenbrug.nl"
        self.base_url = "https://api.datamotive.nl/api/v1/content/vehicle-list/627"
        
        # API configuration
        self.page_size = 50  # Fetch 50 vehicles per page for efficiency
        self.rate_limit_delay = 2.5  # 2.5 seconds between requests
        
        # Dealer location (Heerenveen headquarters)
        self.dealer_city = "Heerenveen"
        self.dealer_province = "Friesland"
        
        # Load search criteria from config for early filtering
        self.min_price = self.config.get('search_criteria', {}).get('min_price', 0)
        self.max_price = self.config.get('search_criteria', {}).get('max_price', float('inf'))
        self.min_year = self.config.get('search_criteria', {}).get('min_year', 0)
        self.max_mileage = self.config.get('search_criteria', {}).get('max_mileage_km', float('inf'))
        self.min_seats = self.config.get('search_criteria', {}).get('min_seats', 0)
    
    def _extract_power_from_edition(self, edition: str):
        """
        Extract power in PK (horsepower) from edition string
        
        Args:
            edition: Edition string, e.g., "82 kWh 286 PK Launch Edition"
            
        Returns:
            Power in PK, or None if not found
        """
        if not edition:
            return None
        
        # Look for pattern like "286 PK" or "286PK"
        pk_match = re.search(r'(\d+)\s*pk', edition.lower())
        if pk_match:
            return int(pk_match.group(1))
        
        return None
    
    def build_search_url(self) -> List[str]:
        """
        Build API URLs for Van den Brug
        
        Since this is an API endpoint, we'll construct pagination URLs.
        We'll start by fetching the first page to get the total count.
        
        Returns:
            List of API URLs to fetch
        """
        urls = []
        
        try:
            # First, make a request to get the total number of pages
            initial_params = {
                'page': 1,
                'pageSize': self.page_size,
                'sort': 'created_at_desc',
                'filterId': 50,  # Filter ID from the API
                'attributes[]': [
                    'addition', 'fuel', 'make', 'model', 'price', 
                    'edition', 'yearOfConstruction', 'odometerReading',
                    'licensePlate', 'slug', 'bodyType', 'transmission',
                    'color', 'doors', 'seats', 'power', 'images'
                ]
            }
            
            response = requests.get(self.base_url, params=initial_params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            total_pages = data.get('pages', {}).get('total', 1)
            total_count = data.get('count', 0)
            
            self.logger.info(f"Van den Brug API: {total_count} total vehicles across {total_pages} pages")
            
            # Build URLs for all pages
            for page_num in range(1, total_pages + 1):
                params = {
                    'page': page_num,
                    'pageSize': self.page_size,
                    'sort': 'created_at_desc',
                    'filterId': 50,
                    'attributes[]': [
                        'addition', 'fuel', 'make', 'model', 'price', 
                        'edition', 'yearOfConstruction', 'odometerReading',
                        'licensePlate', 'slug', 'bodyType', 'transmission',
                        'color', 'doors', 'seats', 'power', 'images'
                    ]
                }
                
                # Construct URL with parameters
                param_parts = []
                for k, v in params.items():
                    if isinstance(v, list):
                        # For list parameters, add each value separately
                        for item in v:
                            param_parts.append(f"{k}={item}")
                    else:
                        # For regular parameters, add normally
                        param_parts.append(f"{k}={v}")
                
                param_str = '&'.join(param_parts)
                url = f"{self.base_url}?{param_str}"
                urls.append(url)
            
            # Small delay to respect rate limits
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            self.logger.error(f"Error building search URLs: {e}")
            # Fallback: return at least one URL for page 1
            urls = [f"{self.base_url}?page=1&pageSize={self.page_size}"]
        
        return urls
    
    def parse_listing_page(self, url: str) -> List[Dict]:
        """
        Parse Van den Brug API response
        
        Args:
            url: API URL to fetch
            
        Returns:
            List of dictionaries containing car summary data
        """
        cars = []
        
        try:
            self.logger.debug(f"Fetching API: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            items = data.get('items', [])
            self.logger.info(f"Found {len(items)} vehicles on this page")
            
            for item in items:
                # Extract data directly from item (API does NOT provide 'attributes' object)
                media = item.get('media', [])
                
                # Extract basic info for each vehicle
                # Note: API only provides: id, brand, model, edition, slug, prices, media
                # Fuel, year, mileage, specs etc. must be fetched from detail page
                car_summary = {
                    'id': item.get('id'),
                    'make': item.get('brand'),
                    'model': item.get('model'),
                    'edition': item.get('edition'),
                    'slug': item.get('slug'),
                    'price': item.get('prices', {}).get('purchase', {}).get('value'),
                    'images': [m.get('url') for m in media if m.get('type') == 'image']
                }
                
                # Early filtering: Check price requirements (only filter we can apply at API level)
                price = car_summary.get('price')
                if price is not None:
                    if price < self.min_price or price > self.max_price:
                        self.logger.debug(f"Skipping {car_summary.get('make')} {car_summary.get('model')} - price €{price:,} outside range €{self.min_price:,}-€{self.max_price:,}")
                        continue
                
                # Note: Cannot filter by year/mileage/fuel/seats at API level since those fields
                # are not in the API response. They will be fetched from detail pages and filtered
                # in parse_car_detail() method.
                
                # Add all cars that pass price filter
                # Electric filtering will happen after detail page fetch (which has fuel type)
                cars.append(car_summary)
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching API: {e}")
        except Exception as e:
            self.logger.error(f"Error parsing API response: {e}")
        
        return cars
    
    def fetch_detail_page(self, url: str) -> Dict:
        """
        Fetch and parse detail page to get accurate specifications and features
        
        Args:
            url: Vehicle detail page URL
            
        Returns:
            Dictionary with scraped specifications and features list
        """
        specs = {}
        
        try:
            self.logger.debug(f"Fetching detail page: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract features from title meta tag (pipe-separated)
            features = []
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text(strip=True)
                # Title format: "Make Model Edition | Feature1 | Feature2 | Feature3 | Dealer Name"
                # Split by pipe and skip first (car name) and last (dealer name) parts
                title_parts = [part.strip() for part in title_text.split('|')]
                if len(title_parts) > 2:
                    # Skip first part (car name) and last part (dealer name)
                    title_features = title_parts[1:-1]
                    features.extend([f for f in title_features if f])
                    self.logger.debug(f"Extracted {len(title_features)} features from title")
            
            # Extract features from description meta tag
            description_tag = soup.find('meta', {'name': 'description'})
            if description_tag:
                description = description_tag.get('content', '')
                # Look for pattern: "Verder is de [brand] uitgerust met: [features]"
                uitgerust_match = re.search(r'uitgerust met:([^.]+)', description, re.IGNORECASE)
                if uitgerust_match:
                    features_text = uitgerust_match.group(1).strip()
                    # Split by comma and clean up
                    desc_features = [f.strip() for f in features_text.split(',')]
                    # Also split "en" at the end (Dutch for "and")
                    final_features = []
                    for feature in desc_features:
                        if ' en ' in feature:
                            # Split on "en" to get the last feature
                            parts = [p.strip() for p in feature.split(' en ')]
                            final_features.extend([p for p in parts if p])
                        else:
                            final_features.append(feature)
                    features.extend([f for f in final_features if f])
                    self.logger.debug(f"Extracted {len(final_features)} features from description")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_features = []
            for feature in features:
                feature_lower = feature.lower()
                if feature_lower not in seen and feature:
                    seen.add(feature_lower)
                    unique_features.append(feature)
            
            specs['features'] = unique_features
            self.logger.debug(f"Total unique features extracted: {len(unique_features)}")
            
            # Find specifications section
            spec_items = soup.find_all('div', class_='BlockVehicleSpecs_spec__Gz_Qg')
            
            for spec_div in spec_items:
                spans = spec_div.find_all('span')
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    value = spans[1].get_text(strip=True)
                    
                    # Map Dutch labels to our keys
                    if label == 'Brandstof':
                        specs['fuel'] = value
                    elif label == 'Kilometerstand':
                        # Extract just the number
                        km_match = re.search(r'([\d.]+)', value.replace('.', ''))
                        if km_match:
                            specs['mileage_km'] = int(km_match.group(1))
                    elif label == 'Bouwjaar':
                        specs['year'] = int(value)
                    elif label == 'Transmissie':
                        specs['transmission'] = value
                    elif label == 'Vermogen (pk)':
                        pk_match = re.search(r'(\d+)', value)
                        if pk_match:
                            specs['power_pk'] = int(pk_match.group(1))
                    elif label == 'Kenteken':
                        specs['license_plate'] = value
                        
            time.sleep(self.rate_limit_delay)
            
        except Exception as e:
            self.logger.warning(f"Error fetching detail page {url}: {e}")
        
        return specs
    
    def parse_car_detail(self, car_summary: Dict) -> Dict:
        """
        Parse detailed car information from API data
        
        For Van den Brug, all data is available from the API, so we don't
        need to scrape detail pages.
        
        Args:
            car_summary: Basic car info from API response
            
        Returns:
            Complete car data dictionary
        """
        try:
            # Construct listing URL from slug
            slug = car_summary.get('slug', '')
            listing_url = f"https://vandenbrug.nl/p/{slug}" if slug else None
            
            if not listing_url:
                self.logger.warning(f"Missing slug/URL, skipping car: {car_summary}")
                return {}
            
            # Map API fields to our database schema
            make = car_summary.get('make', '') or ''
            model = car_summary.get('model', '') or ''
            edition = car_summary.get('edition', '') or ''
            
            make = make.strip()
            model = model.strip()
            edition = edition.strip()
            
            # Skip if missing required fields
            if not make or not model:
                self.logger.warning(f"Missing make or model, skipping car: {car_summary}")
                return {}
            
            # Normalize model name
            normalized_model = normalize_model_name(model)
            
            # Construct full model name with edition if available
            full_model = f"{normalized_model} {edition}".strip() if edition else normalized_model
            
            # PRE-FILTER: Check for electric/PHEV keywords BEFORE fetching detail page
            # This saves us from fetching 1000+ detail pages
            edition_lower = edition.lower()
            model_lower = model.lower()
            make_lower = make.lower()
            
            is_likely_electric = False
            fuel_type = None
            
            # Check for PHEV indicators in edition/model (most reliable)
            if 'phev' in edition_lower or 'plug-in' in edition_lower or 'ehybrid' in edition_lower or ' gte ' in edition_lower or edition_lower.endswith(' gte') or ' iv ' in edition_lower:
                is_likely_electric = True
                fuel_type = 'PHEV'
            # Check for full electric indicators
            elif any(kw in edition_lower or kw in model_lower for kw in ['kwh', 'electric', 'e-tron', ' ev ', 'id.', 'enyaq', 'elroq', 'e-up', 'e-golf', 'ioniq', 'kona electric', 'leaf', 'zoe', 'twingo ze']):
                is_likely_electric = True
                fuel_type = 'Full Electric'
            # Known electric brands
            elif make_lower == 'tesla' or (make_lower == 'polestar'):
                is_likely_electric = True
                fuel_type = 'Full Electric'
            
            # Skip non-electric vehicles early to avoid fetching detail page
            if not is_likely_electric:
                self.logger.debug(f"Not electric/PHEV based on make/model/edition, skipping: {make} {model} {edition}")
                return {}
            
            # NOW fetch detail page for vehicles that passed electric pre-filter
            detail_specs = {}
            features = []
            if listing_url:
                detail_specs = self.fetch_detail_page(listing_url)
                features = detail_specs.get('features', [])
                self.logger.debug(f"Fetched detail specs for {make} {model}: {detail_specs}")
            
            # Double-check fuel type from detail page if we didn't detect it from edition
            if not fuel_type:
                fuel_raw = detail_specs.get('fuel', '')
                if fuel_raw:
                    fuel_type = normalize_fuel_type(fuel_raw)
                    # Verify it's actually electric/PHEV
                    if fuel_type not in ['Full Electric', 'PHEV']:
                        self.logger.debug(f"Pre-filter was wrong - not electric/PHEV (fuel: {fuel_raw}), skipping: {make} {model}")
                        return {}
            
            # Check if vehicle should be excluded based on config
            if should_exclude_vehicle(make, model):
                self.logger.info(f"Excluding vehicle based on config: {make} {model}")
                return {}
            
            # Normalize vehicle type (body style)
            body_type_raw = car_summary.get('body_type', '')
            vehicle_type = normalize_vehicle_type(body_type_raw, normalized_model, make)
            
            # Extract price
            price = car_summary.get('price')
            if price and isinstance(price, (int, float)):
                price = int(price)
            else:
                self.logger.warning(f"No valid price for {make} {model}, skipping")
                return {}
            
            # Extract year from detail page (API doesn't provide it)
            year = detail_specs.get('year')
            if year and isinstance(year, (int, str)):
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None
            
            # Apply year filter if configured
            if year and self.min_year and year < self.min_year:
                self.logger.debug(f"Year {year} below minimum {self.min_year}, skipping: {make} {model}")
                return {}
            
            # Extract mileage from detail page (API doesn't provide it)
            mileage_km = detail_specs.get('mileage_km')
            if mileage_km and isinstance(mileage_km, (int, float)):
                mileage_km = int(mileage_km)
            else:
                mileage_km = None
            
            # Apply mileage filter if configured
            if mileage_km and self.max_mileage and mileage_km > self.max_mileage:
                self.logger.debug(f"Mileage {mileage_km} above maximum {self.max_mileage}, skipping: {make} {model}")
                return {}
            
            # Extract license plate from API
            license_plate = (car_summary.get('license_plate') or '').strip()
            
            # Extract power from API or edition string
            power_pk = car_summary.get('power')
            if not power_pk:
                # Try extracting from edition string (e.g., "286 PK")
                power_pk = self._extract_power_from_edition(edition)
            
            power_kw = None
            if power_pk and isinstance(power_pk, (int, float)):
                # Convert HP to kW (1 HP ≈ 0.7355 kW)
                power_kw = int(power_pk * 0.7355)
            
            # Extract doors and seats
            doors = car_summary.get('doors')
            seats = car_summary.get('seats')
            
            # Apply seats filter if configured
            if seats and self.min_seats and seats < self.min_seats:
                self.logger.debug(f"Seats {seats} below minimum {self.min_seats}, skipping: {make} {model}")
                return {}
            
            # Extract transmission from API
            transmission = (car_summary.get('transmission') or '').strip()
            
            # Extract color
            color = (car_summary.get('color') or '').strip()
            
            # Get first image URL if available
            images = car_summary.get('images', [])
            image_url = images[0] if images and len(images) > 0 else None
            
            # Calculate distance from Heerenveen (dealer is in Heerenveen)
            distance_km = 0  # Dealer is in Heerenveen, so distance is 0
            
            # Build car data
            car_data = {
                'external_id': f"vandenbrug_{car_summary.get('id')}",
                'source_website': self.website_name,
                'make': make,
                'model': full_model,
                'year': year,
                'price': price,
                'mileage_km': mileage_km,
                'fuel_type': fuel_type,
                'vehicle_type': vehicle_type,
                'listing_url': listing_url,
                'location_city': self.dealer_city,
                'location_province': self.dealer_province,
                'distance_from_heerenveen_km': distance_km,
                'license_plate': license_plate,
                'transmission': transmission,
                'color': color,
                'doors': doors,
                'seats': seats,
                'power_kw': power_kw,
                'image_url': image_url,
                'features': features
            }
            
            self.logger.debug(f"Parsed car: {make} {full_model} - €{price}")
            return car_data
            
        except Exception as e:
            self.logger.error(f"Error parsing car detail: {e}")
            return {}
    
    def _init_driver(self):
        """
        Override driver initialization - not needed for API-based scraper
        """
        self.logger.info("Skipping WebDriver initialization (API-based scraper)")
        pass
    
    def _close_driver(self):
        """
        Override driver closing - not needed for API-based scraper
        """
        self.logger.debug("Skipping WebDriver cleanup (API-based scraper)")
        pass
    
    def _random_delay(self, min_seconds=None, max_seconds=None):
        """
        Add fixed delay for API rate limiting
        """
        time.sleep(self.rate_limit_delay)
