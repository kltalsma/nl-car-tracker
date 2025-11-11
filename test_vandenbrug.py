"""
Test script for Vandenbrug scraper
"""
import sys
import logging
from scrapers.vandenbrug_scraper import VandenBrugScraper

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_vandenbrug_scraper():
    """Test the Vandenbrug scraper"""
    logger.info("=" * 80)
    logger.info("Testing Vandenbrug Scraper")
    logger.info("=" * 80)
    
    try:
        # Initialize scraper
        logger.info("Initializing Vandenbrug scraper...")
        scraper = VandenBrugScraper()
        
        # Test 1: Build search URLs
        logger.info("\n--- Test 1: Building search URLs ---")
        urls = scraper.build_search_url()
        logger.info(f"Built {len(urls)} search URL(s)")
        for i, url in enumerate(urls[:3], 1):  # Show first 3 URLs
            logger.info(f"URL {i}: {url[:100]}...")
        
        # Test 2: Parse listing page (first URL only)
        logger.info("\n--- Test 2: Parsing listing page ---")
        if urls:
            cars = scraper.parse_listing_page(urls[0])
            logger.info(f"Found {len(cars)} electric vehicles on first page")
            
            if cars:
                logger.info("\nSample car from listing:")
                sample_car = cars[0]
                logger.info(f"  Make: {sample_car.get('make')}")
                logger.info(f"  Model: {sample_car.get('model')}")
                logger.info(f"  Edition: {sample_car.get('edition')}")
                logger.info(f"  Price: €{sample_car.get('price')}")
                logger.info(f"  Year: {sample_car.get('year')}")
                logger.info(f"  Mileage: {sample_car.get('mileage')} km")
                logger.info(f"  Slug: {sample_car.get('slug')}")
                
                # Test 3: Parse car detail (first car only)
                logger.info("\n--- Test 3: Parsing car detail ---")
                car_detail = scraper.parse_car_detail(sample_car)
                
                if car_detail:
                    logger.info("Successfully parsed car detail:")
                    logger.info(f"  External ID: {car_detail.get('external_id')}")
                    logger.info(f"  Make: {car_detail.get('make')}")
                    logger.info(f"  Model: {car_detail.get('model')}")
                    logger.info(f"  Year: {car_detail.get('year')}")
                    logger.info(f"  Price: €{car_detail.get('price')}")
                    logger.info(f"  Mileage: {car_detail.get('mileage_km')} km")
                    logger.info(f"  Fuel Type: {car_detail.get('fuel_type')}")
                    logger.info(f"  Vehicle Type: {car_detail.get('vehicle_type')}")
                    logger.info(f"  Location: {car_detail.get('location_city')}, {car_detail.get('location_province')}")
                    logger.info(f"  Distance: {car_detail.get('distance_from_heerenveen_km')} km")
                    logger.info(f"  URL: {car_detail.get('listing_url')}")
                    logger.info(f"  License Plate: {car_detail.get('license_plate')}")
                    logger.info(f"  Transmission: {car_detail.get('transmission')}")
                    logger.info(f"  Color: {car_detail.get('color')}")
                    logger.info(f"  Power: {car_detail.get('power_kw')} kW")
                    logger.info(f"  Image URL: {car_detail.get('image_url')}")
                else:
                    logger.warning("Failed to parse car detail")
            else:
                logger.warning("No electric vehicles found on first page")
        
        logger.info("\n" + "=" * 80)
        logger.info("Test completed successfully!")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    test_vandenbrug_scraper()
