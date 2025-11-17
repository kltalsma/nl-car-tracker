"""
Feature Inference Engine for NL Car Tracker

Intelligently infers standard features for vehicles when scraper data is incomplete.
This addresses the common issue where cars have 0-5 detected features despite having
20+ standard features in reality.

Inference is based on:
1. EU legal requirements by year (2020+, 2022+ mandates)
2. Brand segment (premium vs mainstream)
3. Fuel type and vehicle characteristics
4. Model year and known standard equipment
"""

from typing import List, Dict, Set
import logging

logger = logging.getLogger(__name__)


# EU Mandatory Features by Year
# These are legally required in the EU and can be safely inferred
EU_MANDATORY_FEATURES = {
    2022: [  # New EU regulations from 2022
        'Lane Departure Warning Systeem',
        'Botswaarschuwing',  # Forward Collision Warning
        'Vermoeidheidsdetectie',  # Driver Drowsiness Detection
        'Verkeersbordherkenning',  # Traffic Sign Recognition
        'Noodoproepsysteem',  # eCall emergency system
        'ABS',
        'Electronic Stability Program',
        'Bandenspanningscontrolesysteem',  # TPMS
    ],
    2020: [  # Earlier requirements
        'ABS',
        'Electronic Stability Program',
        'Airbag bestuurder',
        'Airbag passagier',
        'Centrale vergrendeling',
    ],
    2015: [  # Basic requirements
        'ABS',
        'Airbag bestuurder',
        'Airbag passagier',
    ]
}


# Premium Brand Standard Features
# These brands typically include these features as standard
PREMIUM_BRANDS = {
    'Audi': [
        'Lederen bekleding',
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Regensensor',
        'Lichtsensor',
        'Android Auto',
        'Apple CarPlay',
        'Digitale radio-ontvangst',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
    ],
    'BMW': [
        'Lederen bekleding',
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Regensensor',
        'Lichtsensor',
        'Android Auto',
        'Apple CarPlay',
        'Digitale radio-ontvangst',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
    ],
    'Mercedes-Benz': [
        'Lederen bekleding',
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Regensensor',
        'Lichtsensor',
        'Android Auto',
        'Apple CarPlay',
        'Digitale radio-ontvangst',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
    ],
    'Volvo': [
        'Lederen bekleding',
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Achteruitrijcamera',
        'Regensensor',
        'Lichtsensor',
        'Android Auto',
        'Apple CarPlay',
        'Digitale radio-ontvangst',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
    ],
    'Polestar': [
        'Lederen bekleding',
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Achteruitrijcamera',
        'Regensensor',
        'Lichtsensor',
        'Android Auto',
        'Apple CarPlay',
        'Digitale radio-ontvangst',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
    ],
    'Tesla': [
        'Navigatiesysteem',
        'Climate Control',
        'Cruise Control',
        'Adaptive Cruise Control',
        'LED verlichting',
        'Parkeerhulp achter',
        'Achteruitrijcamera',
        'Elektrische ramen',
        'Elektrisch verstelbare buitenspiegels',
        'Multifunctioneel stuurwiel',
        'Digitale radio-ontvangst',
        'Bluetooth',
    ]
}


# Modern EV Standard Features (2020+)
# Most EVs from 2020+ include these as standard
MODERN_EV_FEATURES = [
    'Cruise Control',
    'Climate Control',
    'Navigatiesysteem',
    'Android Auto',
    'Apple CarPlay',
    'Digitale radio-ontvangst',
    'Bluetooth',
    'Elektrische ramen',
    'Elektrisch verstelbare buitenspiegels',
    'Centrale vergrendeling',
    'Multifunctioneel stuurwiel',
    'LED verlichting',
    'Parkeerhulp achter',
    'Regensensor',
    'Lichtsensor',
]


# Mainstream Brand Features (typically included)
MAINSTREAM_FEATURES = [
    'Cruise Control',
    'Climate Control',
    'Elektrische ramen',
    'Centrale vergrendeling',
    'Elektrisch verstelbare buitenspiegels',
    'Multifunctioneel stuurwiel',
    'Android Auto',
    'Apple CarPlay',
    'Bluetooth',
    'Digitale radio-ontvangst',
]


def normalize_feature(feature: str) -> str:
    """Normalize feature string for comparison"""
    return feature.lower().strip()


def feature_in_list(feature: str, feature_list: List[str]) -> bool:
    """Check if a feature is already in the list (case-insensitive)"""
    normalized = normalize_feature(feature)
    normalized_list = [normalize_feature(f) for f in feature_list]
    return normalized in normalized_list


def infer_features(car_data: Dict, scraped_features: List[str]) -> tuple[List[str], int]:
    """
    Infer additional features based on car characteristics
    
    Args:
        car_data: Dictionary with car information (make, model, year, fuel_type, etc.)
        scraped_features: List of features extracted by scraper
    
    Returns:
        Tuple of (enriched_features_list, inferred_count)
    """
    # Start with scraped features (remove None/empty)
    enriched = [f for f in scraped_features if f]
    initial_count = len(enriched)
    inferred_count = 0
    
    # Extract car characteristics
    make = car_data.get('make', '')
    model = car_data.get('model', '')
    year = car_data.get('year', 0)
    fuel_type = car_data.get('fuel_type', '')
    
    logger.debug(f"Inferring features for {make} {model} ({year}) - {fuel_type} - Initial: {initial_count} features")
    
    # 1. Add EU mandatory features by year
    for mandate_year, mandatory_features in sorted(EU_MANDATORY_FEATURES.items()):
        if year >= mandate_year:
            for feature in mandatory_features:
                if not feature_in_list(feature, enriched):
                    enriched.append(feature)
                    inferred_count += 1
    
    # 2. Add premium brand standard features
    if make in PREMIUM_BRANDS:
        for feature in PREMIUM_BRANDS[make]:
            if not feature_in_list(feature, enriched):
                enriched.append(feature)
                inferred_count += 1
        logger.debug(f"Added premium brand features for {make}")
    
    # 3. Add modern EV features for electric vehicles 2020+
    if fuel_type == 'Full Electric' and year >= 2020:
        for feature in MODERN_EV_FEATURES:
            if not feature_in_list(feature, enriched):
                enriched.append(feature)
                inferred_count += 1
        logger.debug(f"Added modern EV features")
    
    # 4. Add mainstream features for non-premium 2020+ cars
    if make not in PREMIUM_BRANDS and year >= 2020:
        for feature in MAINSTREAM_FEATURES:
            if not feature_in_list(feature, enriched):
                enriched.append(feature)
                inferred_count += 1
        logger.debug(f"Added mainstream features")
    
    final_count = len(enriched)
    logger.info(f"Feature inference for {make} {model}: {initial_count} scraped + {inferred_count} inferred = {final_count} total")
    
    return enriched, inferred_count


def get_inference_stats(car_data: Dict, original_count: int, final_count: int, inferred_count: int) -> Dict:
    """
    Get statistics about feature inference for reporting
    
    Returns:
        Dictionary with inference statistics
    """
    return {
        'original_count': original_count,
        'inferred_count': inferred_count,
        'final_count': final_count,
        'improvement_percent': round((inferred_count / max(original_count, 1)) * 100, 1) if original_count > 0 else 0,
        'has_inference': inferred_count > 0,
    }
