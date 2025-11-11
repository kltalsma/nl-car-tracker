"""
Trade-In Value Checker for NL Car Tracker
Manages trade-in/market value tracking for the user's current car.

Since most Dutch valuation services (AutoScout24, ANWB, etc.) require email submission
or payment, this tool focuses on manual value entry and historical tracking.

Sources for valuations:
- AutoScout24.nl (https://www.autoscout24.nl/waardebepaling/)
- ANWB Koerslijst
- Spoticar
- Local dealers
- Online estimates (e.g., Claude.ai, ChatGPT with current market data)
"""
import os
from datetime import datetime
import yaml
import logging
import requests
from typing import Dict, Optional, List
from models.database import CurrentCar, TradeInValue, Database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class TradeInChecker:
    """Check and track trade-in values for the user's current car"""
    
    def __init__(self, config_path='config.yaml', db_path='data/cars.db'):
        """
        Initialize the trade-in checker
        
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
        
        # RDW API endpoint
        self.rdw_api_base = "https://opendata.rdw.nl/resource"
        
    def get_rdw_data(self, license_plate: str) -> Optional[Dict]:
        """
        Fetch car details from RDW (Dutch vehicle registration) API
        
        Args:
            license_plate: Dutch license plate (e.g., 'SX-515-N')
            
        Returns:
            Dictionary with car details or None if not found
        """
        # Clean license plate (remove dashes and spaces, uppercase)
        clean_plate = license_plate.replace('-', '').replace(' ', '').upper()
        
        self.logger.info(f"Fetching RDW data for license plate: {license_plate}")
        
        try:
            # RDW Gekentekende voertuigen (registered vehicles) endpoint
            url = f"{self.rdw_api_base}/m9d7-ebf2.json"
            params = {
                'kenteken': clean_plate,
                '$limit': 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if not data or len(data) == 0:
                self.logger.warning(f"No RDW data found for license plate: {license_plate}")
                return None
            
            vehicle = data[0]
            
            # Extract relevant fields
            rdw_info = {
                'license_plate': license_plate,
                'make': vehicle.get('merk', 'Unknown'),
                'model': vehicle.get('handelsbenaming', 'Unknown'),
                'year': int(vehicle.get('datum_eerste_toelating', '0000')[:4]) if vehicle.get('datum_eerste_toelating') else None,
                'fuel_type': vehicle.get('brandstof_omschrijving', 'Unknown'),
                'body_type': vehicle.get('voertuigsoort', 'Unknown'),
                'color': vehicle.get('eerste_kleur', 'Unknown'),
                'raw_data': vehicle
            }
            
            self.logger.info(f"RDW data found: {rdw_info['make']} {rdw_info['model']} ({rdw_info['year']})")
            return rdw_info
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to fetch RDW data: {e}")
            return None
    
    def get_or_create_current_car(self, license_plate: str, mileage_km: Optional[int] = None) -> Optional[CurrentCar]:
        """
        Get or create the current car record in the database
        
        Args:
            license_plate: License plate of the car
            mileage_km: Current mileage (optional, will use config if not provided)
            
        Returns:
            CurrentCar object or None if failed
        """
        session = self.db.get_session()
        
        try:
            # Check if car already exists
            car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
            
            if car:
                # Update mileage if provided
                if mileage_km is not None:
                    car.mileage_km = mileage_km
                    car.last_updated = datetime.utcnow()
                    session.commit()
                    self.logger.info(f"Updated mileage for {car.license_plate}: {mileage_km} km")
                return car
            
            # Create new car record
            self.logger.info(f"Creating new current car record for {license_plate}")
            
            # Fetch RDW data
            rdw_data = self.get_rdw_data(license_plate)
            
            if not rdw_data:
                self.logger.error(f"Cannot create car record without RDW data")
                return None
            
            # Use mileage from parameter or config
            if mileage_km is None:
                mileage_km = self.config.get('current_car', {}).get('mileage_km', 0)
            
            car = CurrentCar(
                license_plate=license_plate,
                make=rdw_data['make'],
                model=rdw_data['model'],
                year=rdw_data['year'],
                fuel_type=rdw_data['fuel_type'],
                body_type=rdw_data['body_type'],
                color=rdw_data['color'],
                mileage_km=mileage_km,
                rdw_data=rdw_data['raw_data']
            )
            
            session.add(car)
            session.commit()
            
            self.logger.info(f"Created current car: {car.make} {car.model} ({car.year})")
            return car
            
        except Exception as e:
            self.logger.error(f"Failed to get/create current car: {e}")
            session.rollback()
            return None
        finally:
            session.close()
    
    def add_manual_value(
        self,
        license_plate: str,
        value: float,
        source: str,
        mileage_km: Optional[int] = None,
        value_type: str = "market_value",
        notes: Optional[str] = None
    ) -> Optional[TradeInValue]:
        """
        Manually add a trade-in valuation
        
        Args:
            license_plate: License plate of the car
            value: The valuation amount in euros
            source: Source of the valuation (e.g., "AutoScout24", "ANWB", "Dealer", "Claude.ai")
            mileage_km: Mileage at time of valuation (optional, uses config if not provided)
            value_type: Type of value - "market_value", "asking_price", or "selling_price"
            notes: Optional notes about the valuation
            
        Returns:
            TradeInValue object or None if failed
        """
        session = self.db.get_session()
        
        try:
            # Get or create car record
            car = self.get_or_create_current_car(license_plate, mileage_km)
            if not car:
                self.logger.error("Failed to get/create car record")
                return None
            
            # Use car's current mileage if not specified
            if mileage_km is None:
                mileage_km = car.mileage_km
            
            # Prepare valuation data
            valuation_data = {
                'source': source,
                'value_type': value_type,
                'notes': notes,
                'entered_at': datetime.utcnow().isoformat()
            }
            
            # Create trade-in value record
            trade_in = TradeInValue(
                car_id=car.id,
                asking_price=value if value_type == "asking_price" else None,
                market_value=value if value_type == "market_value" else None,
                selling_price=value if value_type == "selling_price" else None,
                mileage_km=mileage_km,
                source=source,
                source_url=None,
                checked_at=datetime.utcnow(),
                raw_data=valuation_data
            )
            
            session.add(trade_in)
            session.commit()
            
            self.logger.info(f"Added {value_type} of €{value:,.0f} from {source}")
            return trade_in
            
        except Exception as e:
            self.logger.error(f"Failed to add manual value: {e}")
            session.rollback()
            return None
        finally:
            session.close()
    
    def get_value_history(self, license_plate: str, limit: int = 10) -> List[TradeInValue]:
        """
        Get historical trade-in values for a car
        
        Args:
            license_plate: License plate of the car
            limit: Maximum number of records to return
            
        Returns:
            List of TradeInValue objects, most recent first
        """
        session = self.db.get_session()
        
        try:
            car = session.query(CurrentCar).filter_by(license_plate=license_plate).first()
            if not car:
                self.logger.warning(f"No car found with license plate: {license_plate}")
                return []
            
            values = session.query(TradeInValue)\
                .filter_by(car_id=car.id)\
                .order_by(TradeInValue.checked_at.desc())\
                .limit(limit)\
                .all()
            
            return values
            
        except Exception as e:
            self.logger.error(f"Failed to get value history: {e}")
            return []
        finally:
            session.close()
    
    def print_value_history(self, license_plate: str, limit: int = 10):
        """
        Print value history in a readable format
        
        Args:
            license_plate: License plate of the car
            limit: Maximum number of records to show
        """
        values = self.get_value_history(license_plate, limit)
        
        if not values:
            print(f"\nNo valuation history found for {license_plate}")
            return
        
        print(f"\n{'='*80}")
        print(f"Trade-In Value History for {license_plate}")
        print(f"{'='*80}\n")
        
        for val in values:
            print(f"Date: {val.checked_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"Source: {val.source}")
            print(f"Mileage: {val.mileage_km:,} km")
            
            if val.market_value:
                print(f"Market Value: €{val.market_value:,.0f}")
            if val.asking_price:
                print(f"Asking Price: €{val.asking_price:,.0f}")
            if val.selling_price:
                print(f"Selling Price: €{val.selling_price:,.0f}")
            
            if val.raw_data and isinstance(val.raw_data, dict):
                notes = val.raw_data.get('notes')
                if notes:
                    print(f"Notes: {notes}")
            
            print(f"{'-'*80}\n")
    
    def get_latest_value(self, license_plate: str) -> Optional[TradeInValue]:
        """
        Get the most recent trade-in value
        
        Args:
            license_plate: License plate of the car
            
        Returns:
            Most recent TradeInValue or None
        """
        values = self.get_value_history(license_plate, limit=1)
        return values[0] if values else None


def main():
    """Main function for CLI usage"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description='NL Car Tracker - Trade-In Value Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a manual valuation
  python utils/trade_in_checker.py add --value 10500 --source "AutoScout24" --notes "Online estimate"
  
  # Add with specific mileage
  python utils/trade_in_checker.py add --value 11000 --source "Local Dealer" --mileage 151000
  
  # View value history
  python utils/trade_in_checker.py history
  
  # Show latest value
  python utils/trade_in_checker.py latest
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Add value command
    add_parser = subparsers.add_parser('add', help='Add a manual valuation')
    add_parser.add_argument('--value', type=float, required=True, help='Valuation amount in euros')
    add_parser.add_argument('--source', type=str, required=True, help='Source of valuation (e.g., AutoScout24, ANWB, Dealer)')
    add_parser.add_argument('--license-plate', type=str, help='License plate (uses config if not provided)')
    add_parser.add_argument('--mileage', type=int, help='Mileage in km (uses config if not provided)')
    add_parser.add_argument('--type', type=str, choices=['market_value', 'asking_price', 'selling_price'], 
                          default='market_value', help='Type of value')
    add_parser.add_argument('--notes', type=str, help='Optional notes about this valuation')
    
    # History command
    history_parser = subparsers.add_parser('history', help='Show valuation history')
    history_parser.add_argument('--license-plate', type=str, help='License plate (uses config if not provided)')
    history_parser.add_argument('--limit', type=int, default=10, help='Number of records to show')
    
    # Latest command
    latest_parser = subparsers.add_parser('latest', help='Show latest valuation')
    latest_parser.add_argument('--license-plate', type=str, help='License plate (uses config if not provided)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    checker = TradeInChecker()
    
    # Get license plate from args or config
    license_plate = args.license_plate if hasattr(args, 'license_plate') and args.license_plate else None
    if not license_plate:
        license_plate = checker.config.get('current_car', {}).get('license_plate')
        if not license_plate:
            print("Error: No license plate provided. Use --license-plate or set in config.yaml")
            sys.exit(1)
    
    # Execute command
    if args.command == 'add':
        mileage = args.mileage if args.mileage else None
        actual_mileage = mileage if mileage else checker.config.get('current_car', {}).get('mileage_km', 0)
        
        result = checker.add_manual_value(
            license_plate=license_plate,
            value=args.value,
            source=args.source,
            mileage_km=mileage,
            value_type=args.type,
            notes=args.notes
        )
        
        if result:
            print(f"\n✓ Successfully added {args.type} of €{args.value:,.0f} from {args.source}")
            print(f"  License Plate: {license_plate}")
            print(f"  Mileage: {actual_mileage:,} km")
            if args.notes:
                print(f"  Notes: {args.notes}")
            sys.exit(0)
        else:
            print("\n✗ Failed to add valuation")
            sys.exit(1)
    
    elif args.command == 'history':
        checker.print_value_history(license_plate, args.limit)
    
    elif args.command == 'latest':
        latest = checker.get_latest_value(license_plate)
        if latest:
            print(f"\nLatest valuation for {license_plate}:")
            print(f"  Date: {latest.checked_at.strftime('%Y-%m-%d %H:%M')}")
            print(f"  Source: {latest.source}")
            print(f"  Mileage: {latest.mileage_km:,} km")
            if latest.market_value:
                print(f"  Market Value: €{latest.market_value:,.0f}")
            if latest.asking_price:
                print(f"  Asking Price: €{latest.asking_price:,.0f}")
            if latest.selling_price:
                print(f"  Selling Price: €{latest.selling_price:,.0f}")
        else:
            print(f"\nNo valuations found for {license_plate}")


if __name__ == "__main__":
    main()
