"""
Database models for NL Car Tracker
Defines the schema for storing car listings and price history
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, JSON, text, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()


class Car(Base):
    """Main car listing table"""
    __tablename__ = 'cars'
    
    id = Column(Integer, primary_key=True)
    
    # Unique identifier from the source website
    external_id = Column(String(255), unique=True, nullable=False, index=True)
    source_website = Column(String(50), nullable=False, index=True)
    
    # Basic Information
    make = Column(String(100), nullable=False, index=True)
    model = Column(String(100), nullable=False, index=True)
    year = Column(Integer, nullable=False, index=True)
    vehicle_type = Column(String(50), index=True)  # SUV, Stationwagon
    
    # Price and Mileage
    price = Column(Float, nullable=False, index=True)
    mileage_km = Column(Integer, nullable=False, index=True)
    
    # Fuel and Range
    fuel_type = Column(String(50), nullable=False, index=True)  # Full Electric, PHEV
    range_km = Column(Integer)  # DEPRECATED: Legacy field, use ad_listed_range_km instead
    electric_range_km = Column(Integer)  # DEPRECATED: Legacy field, use ad_listed_range_km for PHEV
    
    # Three-source range tracking
    ad_listed_range_km = Column(Integer, index=True)  # Range value from the actual car listing
    wltp_reference_range_km = Column(Integer)  # Official WLTP manufacturer range from yaml
    evdb_real_range_km = Column(Integer)  # EV-Database real-world range from yaml
    
    # Location
    location_city = Column(String(100))
    location_province = Column(String(100))
    distance_from_heerenveen_km = Column(Float, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    
    # Features (stored as JSON array)
    features = Column(JSON)  # List of feature strings
    features_count = Column(Integer, default=0, index=True)  # Count of required features present
    has_all_required_features = Column(Boolean, default=False, index=True)
    
    # Additional Details
    color = Column(String(50))
    transmission = Column(String(50))
    body_type = Column(String(50))
    doors = Column(Integer)
    seats = Column(Integer)
    power_kw = Column(Integer)
    power_hp = Column(Integer)
    
    # Storage and Interior Space
    storage_capacity_liters = Column(Integer)  # Boot/trunk capacity in liters
    storage_capacity_seats_down_liters = Column(Integer)  # With rear seats folded
    rear_legroom_mm = Column(Integer)  # Rear passenger legroom
    towing_capacity_kg = Column(Integer)  # Maximum braked towing capacity in kilograms
    
    # URLs and Images
    listing_url = Column(Text, nullable=False)
    image_urls = Column(JSON)  # List of image URLs
    primary_image_url = Column(Text)
    
    # Dealer Information
    dealer_name = Column(String(200))
    dealer_location = Column(String(200))
    dealer_phone = Column(String(50))
    
    # Metadata
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, index=True)
    is_available = Column(Boolean, default=True, index=True)
    unavailable_reason = Column(String(100), index=True)  # not_found_in_scrape, website_shows_unavailable, http_error, manual
    marked_unavailable_at = Column(DateTime, index=True)  # When car became unavailable
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional info as JSON for flexibility
    raw_data = Column(JSON)  # Store raw scraped data
    
    # Relationships
    price_history = relationship("PriceHistory", back_populates="car", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Car {self.make} {self.model} ({self.year}) - €{self.price:,.0f}>"
    
    def mark_unavailable(self, reason):
        """Mark car as unavailable with a reason"""
        self.is_available = False
        self.unavailable_reason = reason
        self.marked_unavailable_at = datetime.utcnow()
    
    def mark_available(self):
        """Mark car as available (e.g., if it reappears)"""
        self.is_available = True
        self.unavailable_reason = None
        self.marked_unavailable_at = None
    
    def to_dict(self):
        """Convert car object to dictionary"""
        return {
            'id': self.id,
            'external_id': self.external_id,
            'source_website': self.source_website,
            'make': self.make,
            'model': self.model,
            'year': self.year,
            'vehicle_type': self.vehicle_type,
            'price': self.price,
            'mileage_km': self.mileage_km,
            'fuel_type': self.fuel_type,
            'range_km': self.range_km,  # Legacy
            'electric_range_km': self.electric_range_km,  # Legacy
            'ad_listed_range_km': self.ad_listed_range_km,
            'wltp_reference_range_km': self.wltp_reference_range_km,
            'evdb_real_range_km': self.evdb_real_range_km,
            'location_city': self.location_city,
            'distance_from_heerenveen_km': self.distance_from_heerenveen_km,
            'features': self.features,
            'features_count': self.features_count,
            'has_all_required_features': self.has_all_required_features,
            'storage_capacity_liters': self.storage_capacity_liters,
            'storage_capacity_seats_down_liters': self.storage_capacity_seats_down_liters,
            'listing_url': self.listing_url,
            'primary_image_url': self.primary_image_url,
            'dealer_name': self.dealer_name,
            'first_seen': self.first_seen.isoformat() if self.first_seen is not None else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen is not None else None,
            'is_available': self.is_available,
            'unavailable_reason': self.unavailable_reason,
            'marked_unavailable_at': self.marked_unavailable_at.isoformat() if self.marked_unavailable_at is not None else None
        }


class PriceHistory(Base):
    """Track price changes over time"""
    __tablename__ = 'price_history'
    
    id = Column(Integer, primary_key=True)
    car_id = Column(Integer, ForeignKey('cars.id'), nullable=False, index=True)
    price = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationships
    car = relationship("Car", back_populates="price_history")
    
    def __repr__(self):
        return f"<PriceHistory car_id={self.car_id} price=€{self.price:,.0f} at {self.recorded_at}>"


class ScraperLog(Base):
    """Log scraping activities"""
    __tablename__ = 'scraper_logs'
    
    id = Column(Integer, primary_key=True)
    website = Column(String(50), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime)
    status = Column(String(20), index=True)  # success, error, in_progress
    cars_found = Column(Integer, default=0)
    cars_new = Column(Integer, default=0)
    cars_updated = Column(Integer, default=0)
    error_message = Column(Text)
    
    def __repr__(self):
        return f"<ScraperLog {self.website} at {self.started_at} - {self.status}>"


class CurrentCar(Base):
    """Track the user's current car details"""
    __tablename__ = 'current_car'
    
    id = Column(Integer, primary_key=True)
    license_plate = Column(String(20), nullable=False, unique=True, index=True)
    make = Column(String(100))
    model = Column(String(100))
    year = Column(Integer)
    mileage_km = Column(Integer)
    fuel_type = Column(String(50))
    body_type = Column(String(50))
    color = Column(String(50))
    
    # Purchase information for depreciation calculation
    initial_purchase_price = Column(Float)  # Original purchase price
    purchase_date = Column(DateTime)  # Date of purchase
    average_km_per_year = Column(Integer)  # Expected annual mileage
    
    # RDW data
    rdw_data = Column(JSON)  # Full RDW response
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    trade_in_values = relationship("TradeInValue", back_populates="car", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<CurrentCar {self.make} {self.model} ({self.license_plate})>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'license_plate': self.license_plate,
            'make': self.make,
            'model': self.model,
            'year': self.year,
            'mileage_km': self.mileage_km,
            'fuel_type': self.fuel_type,
            'body_type': self.body_type,
            'color': self.color,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }


class TradeInValue(Base):
    """Track trade-in value history for the current car"""
    __tablename__ = 'trade_in_values'
    
    id = Column(Integer, primary_key=True)
    car_id = Column(Integer, ForeignKey('current_car.id'), nullable=False, index=True)
    
    # Valuation data from AutoScout24
    asking_price = Column(Float)  # Vraagprijs
    market_value = Column(Float)  # Dagwaarde
    selling_price = Column(Float)  # Verkoopprijs (estimated)
    
    # Car state at time of valuation
    mileage_km = Column(Integer, nullable=False)
    
    # Source info
    source = Column(String(50), default='autoscout24.nl')
    source_url = Column(Text)
    
    # Metadata
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    raw_data = Column(JSON)  # Store full response
    
    # Relationships
    car = relationship("CurrentCar", back_populates="trade_in_values")
    
    def __repr__(self):
        return f"<TradeInValue €{self.market_value:,.0f} at {self.checked_at}>"
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'car_id': self.car_id,
            'asking_price': self.asking_price,
            'market_value': self.market_value,
            'selling_price': self.selling_price,
            'mileage_km': self.mileage_km,
            'source': self.source,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None
        }


class User(Base):
    """User authentication table"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime)
    is_active = Column(Boolean, default=True, nullable=False)
    
    def __repr__(self):
        return f"<User {self.username} (admin={self.is_admin})>"


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Set SQLite pragmas on every connection.
    This ensures WAL mode is enabled even if the database was opened
    in a different mode by another process.
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")  # Faster than FULL, safe with WAL
    cursor.execute("PRAGMA cache_size=-64000;")  # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY;")  # Store temp tables in memory
    cursor.execute("PRAGMA busy_timeout=30000;")  # 30 second busy timeout
    cursor.close()


class Database:
    """Database connection and session management"""
    
    def __init__(self, db_path='data/cars.db'):
        """Initialize database connection"""
        # Convert relative paths to absolute, using project root as base
        if not os.path.isabs(db_path):
            # Find project root (where config.yaml is located)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)  # Go up from models/ to project root
            db_path = os.path.join(project_root, db_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Store db_path for later use
        self.db_path = db_path
        
        # Configure SQLite for concurrent access and corruption resistance
        # WAL mode allows multiple readers and one writer simultaneously
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,
            connect_args={
                'timeout': 30,  # Wait up to 30 seconds for lock
                'check_same_thread': False  # Allow multi-threaded access
            },
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600  # Recycle connections every hour
        )
        
        # Register event listener to set PRAGMA on every connection
        # This ensures WAL mode is enabled even if database was accessed
        # by another process in a different mode
        event.listen(self.engine, "connect", _set_sqlite_pragma)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
    
    def get_session(self):
        """Get a new database session"""
        return self.Session()
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()
    
    def get_available_cars(self, session=None):
        """
        Get all available cars
        
        Args:
            session: Optional existing session, creates new one if not provided
            
        Returns:
            Query object of available cars
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True
        
        try:
            query = session.query(Car).filter(Car.is_available == True)
            return query
        finally:
            if close_session:
                session.close()
    
    def get_unavailable_cars(self, session=None, reason=None):
        """
        Get unavailable cars, optionally filtered by reason
        
        Args:
            session: Optional existing session
            reason: Optional filter by unavailable_reason
            
        Returns:
            Query object of unavailable cars
        """
        close_session = False
        if session is None:
            session = self.get_session()
            close_session = True
        
        try:
            query = session.query(Car).filter(Car.is_available == False)
            
            if reason:
                query = query.filter(Car.unavailable_reason == reason)
            
            return query
        finally:
            if close_session:
                session.close()


def init_db(db_path='data/cars.db'):
    """Initialize the database and create all tables"""
    db = Database(db_path)
    print(f"Database initialized at {db_path}")
    return db


if __name__ == "__main__":
    # Initialize database when run directly
    db = init_db()
    print("Database tables created successfully!")
