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
    

