"""
Car Depreciation Calculator
Implements a hybrid time + mileage-based depreciation model
"""
from datetime import datetime, date
from typing import Dict, Optional, Tuple


class DepreciationCalculator:
    """
    Calculates car depreciation using a hybrid model:
    - Time-based depreciation (age of vehicle)
    - Mileage-based penalties (above-average usage)
    
    Based on real-world Dutch market depreciation patterns.
    """
    
    # Dutch average km per year
    DEFAULT_AVERAGE_KM_PER_YEAR = 14000
    
    # Time-based depreciation rates
    FIRST_YEAR_RATE = 0.20      # 20% first year
    YEARS_2_TO_5_RATE = 0.12    # 12% per year for years 2-5
    AFTER_5_YEARS_RATE = 0.07   # 7% per year after 5 years
    
    # Mileage penalty coefficient
    MILEAGE_PENALTY_COEFFICIENT = 0.000005  # €0.05-0.10 per excess km per year
    
    def __init__(self, 
                 initial_price: float, 
                 purchase_date: date,
                 current_mileage_km: int,
                 average_km_per_year: Optional[int] = None,
                 manufacture_year: Optional[int] = None):
        """
        Initialize depreciation calculator
        
        Args:
            initial_price: Original purchase price
            purchase_date: Date of purchase
            current_mileage_km: Current odometer reading in km
            average_km_per_year: Expected average km/year (defaults to Dutch average: 14,000)
            manufacture_year: Year the vehicle was manufactured (if different from purchase year)
        """
        self.initial_price = initial_price
        self.purchase_date = purchase_date
        self.current_mileage_km = current_mileage_km
        self.average_km_per_year = average_km_per_year or self.DEFAULT_AVERAGE_KM_PER_YEAR
        self.manufacture_year = manufacture_year
        
    def calculate_age_years(self, as_of_date: Optional[date] = None) -> float:
        """
        Calculate age of vehicle in years
        
        Args:
            as_of_date: Date to calculate age as of (defaults to today)
            
        Returns:
            Age in years (decimal)
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        # If manufacture_year is provided, use it to calculate vehicle age
        # Otherwise, fall back to purchase_date (for backwards compatibility)
        if self.manufacture_year:
            # Calculate from January 1st of manufacture year
            manufacture_date = date(self.manufacture_year, 1, 1)
            delta = as_of_date - manufacture_date
            return delta.days / 365.25  # Account for leap years
        else:
            # Fall back to purchase date
            delta = as_of_date - self.purchase_date
            return delta.days / 365.25  # Account for leap years
    
    def calculate_actual_km_per_year(self) -> float:
        """
        Calculate actual km driven per year
        
        Returns:
            Actual km/year
        """
        age_years = self.calculate_age_years()
        if age_years == 0:
            return 0
        return self.current_mileage_km / age_years
    
    def calculate_time_depreciation_rate(self, age_years: float) -> float:
        """
        Calculate time-based depreciation rate based on age
        
        Args:
            age_years: Age of vehicle in years
            
        Returns:
            Annual depreciation rate (0.0 to 1.0)
        """
        if age_years <= 1:
            return self.FIRST_YEAR_RATE
        elif age_years <= 5:
            return self.YEARS_2_TO_5_RATE
        else:
            return self.AFTER_5_YEARS_RATE
    
    def calculate_mileage_penalty_rate(self, actual_km_per_year: float) -> float:
        """
        Calculate mileage-based depreciation penalty
        
        Args:
            actual_km_per_year: Actual km driven per year
            
        Returns:
            Additional annual depreciation rate due to high mileage
        """
        excess_km = max(0, actual_km_per_year - self.average_km_per_year)
        return excess_km * self.MILEAGE_PENALTY_COEFFICIENT
    
    def calculate_current_value(self, as_of_date: Optional[date] = None) -> Dict:
        """
        Calculate current estimated value with detailed breakdown
        
        Args:
            as_of_date: Date to calculate value as of (defaults to today)
            
        Returns:
            Dictionary with:
                - estimated_value: Current estimated value
                - age_years: Age in years
                - actual_km_per_year: Actual km/year
                - time_depreciation_rate: Time-based depreciation rate
                - mileage_penalty_rate: Mileage penalty rate
                - total_depreciation_rate: Combined depreciation rate
                - total_depreciation_amount: Total amount depreciated
                - depreciation_percentage: Total depreciation as percentage
        """
        age_years = self.calculate_age_years(as_of_date)
        actual_km_per_year = self.calculate_actual_km_per_year()
        
        # Calculate depreciation rates
        time_rate = self.calculate_time_depreciation_rate(age_years)
        mileage_penalty = self.calculate_mileage_penalty_rate(actual_km_per_year)
        total_rate = time_rate + mileage_penalty
        
        # Calculate value using compound depreciation
        # estimated_value = initial_value * (1 - total_rate)^age_years
        estimated_value = self.initial_price * ((1 - total_rate) ** age_years)
        
        # Ensure value doesn't go negative
        estimated_value = max(0, estimated_value)
        
        total_depreciation = self.initial_price - estimated_value
        depreciation_percentage = (total_depreciation / self.initial_price) * 100 if self.initial_price > 0 else 0
        
        return {
            'estimated_value': round(estimated_value, 2),
            'age_years': round(age_years, 2),
            'actual_km_per_year': round(actual_km_per_year, 0),
            'time_depreciation_rate': round(time_rate, 4),
            'mileage_penalty_rate': round(mileage_penalty, 4),
            'total_depreciation_rate': round(total_rate, 4),
            'total_depreciation_amount': round(total_depreciation, 2),
            'depreciation_percentage': round(depreciation_percentage, 2),
            'is_high_mileage': actual_km_per_year > self.average_km_per_year + 5000,
            'is_low_mileage': actual_km_per_year < self.average_km_per_year - 3000
        }
    
    def calculate_projected_value(self, years_forward: int) -> float:
        """
        Project future value after N years
        
        Args:
            years_forward: Number of years to project forward
            
        Returns:
            Estimated value in N years
        """
        # Calculate future mileage
        actual_km_per_year = self.calculate_actual_km_per_year()
        future_mileage = self.current_mileage_km + (actual_km_per_year * years_forward)
        
        # Create future calculator with projected mileage
        future_date = date.today().replace(year=date.today().year + years_forward)
        
        # Use same rates but with future age
        future_age = self.calculate_age_years() + years_forward
        time_rate = self.calculate_time_depreciation_rate(future_age)
        
        # Calculate future km/year
        future_km_per_year = future_mileage / future_age if future_age > 0 else 0
        mileage_penalty = self.calculate_mileage_penalty_rate(future_km_per_year)
        
        total_rate = time_rate + mileage_penalty
        estimated_value = self.initial_price * ((1 - total_rate) ** future_age)
        
        return max(0, round(estimated_value, 2))
    
    def generate_depreciation_curve(self, years_ahead: int = 5) -> list:
        """
        Generate depreciation curve data points for visualization
        
        Args:
            years_ahead: Number of years to project into future
            
        Returns:
            List of dicts with year, age, mileage, value
        """
        curve_data = []
        
        # Start from purchase date (or manufacture year if provided)
        current_age = self.calculate_age_years()
        
        # Determine the base date for the curve
        if self.manufacture_year:
            base_date = date(self.manufacture_year, 1, 1)
        else:
            base_date = self.purchase_date
        
        # Generate historical points (from base date to now)
        for year_offset in range(0, int(current_age) + 1):
            offset_date = base_date.replace(year=base_date.year + year_offset)
            if offset_date > date.today():
                offset_date = date.today()
                
            age = self.calculate_age_years(offset_date)
            mileage = int(self.current_mileage_km * (age / current_age)) if current_age > 0 else 0
            
            # Recalculate for this point in time
            temp_calc = DepreciationCalculator(
                self.initial_price,
                self.purchase_date,
                mileage,
                self.average_km_per_year,
                self.manufacture_year
            )
            result = temp_calc.calculate_current_value(offset_date)
            
            curve_data.append({
                'year': offset_date.year,
                'age_years': round(age, 1),
                'mileage_km': mileage,
                'estimated_value': result['estimated_value'],
                'is_current': offset_date >= date.today()
            })
        
        # Generate future projections
        for year_offset in range(1, years_ahead + 1):
            future_year = date.today().year + year_offset
            future_age = current_age + year_offset
            future_mileage = self.current_mileage_km + int(self.calculate_actual_km_per_year() * year_offset)
            
            temp_calc = DepreciationCalculator(
                self.initial_price,
                self.purchase_date,
                future_mileage,
                self.average_km_per_year,
                self.manufacture_year
            )
            
            future_date = date.today().replace(year=future_year)
            result = temp_calc.calculate_current_value(future_date)
            
            curve_data.append({
                'year': future_year,
                'age_years': round(future_age, 1),
                'mileage_km': future_mileage,
                'estimated_value': result['estimated_value'],
                'is_future': True
            })
        
        return curve_data


def calculate_depreciation_from_car_data(car_data: Dict) -> Optional[Dict]:
    """
    Convenience function to calculate depreciation from car data dict
    
    Args:
        car_data: Dictionary with keys:
            - initial_purchase_price
            - purchase_date (datetime or date)
            - mileage_km
            - average_km_per_year (optional)
            - year (optional) - manufacture year for more accurate age calculation
            
    Returns:
        Depreciation calculation result dict, or None if data incomplete
    """
    # Validate required fields
    if not all(k in car_data for k in ['initial_purchase_price', 'purchase_date', 'mileage_km']):
        return None
    
    if not car_data['initial_purchase_price'] or not car_data['purchase_date']:
        return None
    
    # Convert datetime to date if needed
    purchase_date = car_data['purchase_date']
    if isinstance(purchase_date, datetime):
        purchase_date = purchase_date.date()
    
    # Create calculator
    calc = DepreciationCalculator(
        initial_price=float(car_data['initial_purchase_price']),
        purchase_date=purchase_date,
        current_mileage_km=int(car_data['mileage_km']),
        average_km_per_year=car_data.get('average_km_per_year'),
        manufacture_year=car_data.get('year')  # Pass manufacture year if available
    )
    
    # Calculate and return
    result = calc.calculate_current_value()
    
    # Add curve data
    result['depreciation_curve'] = calc.generate_depreciation_curve(years_ahead=5)
    
    return result
