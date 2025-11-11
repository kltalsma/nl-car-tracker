#!/usr/bin/env python3
"""
RDW WLTP Range Enrichment Script

This script verifies and enriches the WLTP range YAML data using official RDW Open Data.
It performs the following operations:

1. Cross-validates existing YAML entries against RDW official data
2. Identifies discrepancies (>5% difference) between YAML and RDW values
3. Discovers new popular EV models not yet in the YAML
4. Generates enriched YAML content and a detailed report

Usage:
    python scripts/enrich_wltp_from_rdw.py [--auto-update] [--discover-new] [--output FILE]

Options:
    --auto-update     Automatically update YAML file with verified RDW data
    --discover-new    Query RDW for popular models not in YAML
    --output FILE     Write enriched YAML to specified file (default: print to console)
    --verbose         Enable detailed logging
    --limit N         Limit number of makes to process (for testing)
"""

import sys
import os
import argparse
import yaml
import requests
import time
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Add parent directory to path to import helpers
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Simple logging setup
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RDWRangeVerifier:
    """Verifies and enriches WLTP range data using RDW Open Data API"""
    
    VEHICLE_API_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
    FUEL_API_URL = "https://opendata.rdw.nl/resource/8ys7-d773.json"
    REQUEST_DELAY = 0.5  # Seconds between API calls to avoid rate limiting
    DISCREPANCY_THRESHOLD = 0.05  # 5% difference threshold
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.stats = {
            'verified': 0,
            'discrepancies': 0,
            'not_found': 0,
            'errors': 0,
            'new_discoveries': 0
        }
        self.discrepancies = []
        self.not_found = []
        self.errors = []
        
    def query_rdw_range(self, make: str, model: str, battery_kwh: Optional[str] = None, 
                        is_phev: bool = False) -> Optional[int]:
        """
        Query RDW API for WLTP range of a specific vehicle
        
        Args:
            make: Vehicle make (e.g., "Tesla")
            model: Vehicle model (e.g., "Model 3")
            battery_kwh: Battery capacity for more specific matching
            is_phev: Whether this is a PHEV (affects which range field to use)
            
        Returns:
            WLTP range in km or None if not found
        """
        if not make or not model:
            return None
        
        try:
            # Extract first word of model for broader matching
            model_search = model.split()[0]
            
            # Query main vehicle dataset
            params = {
                "$where": f"merk='{make.upper()}' AND handelsbenaming LIKE '%{model_search.upper()}%'",
                "$select": "kenteken,handelsbenaming,datum_eerste_toelating",
                "$limit": 20,
                "$order": "datum_eerste_toelating DESC"
            }
            
            if self.verbose:
                logger.debug(f"Querying RDW for {make} {model} ({battery_kwh} kWh)...")
            
            response = requests.get(self.VEHICLE_API_URL, params=params, timeout=15)
            time.sleep(self.REQUEST_DELAY)  # Rate limiting
            
            if response.status_code != 200:
                if self.verbose:
                    logger.warning(f"RDW query failed: {response.status_code}")
                return None
            
            vehicles = response.json()
            if not vehicles:
                return None
            
            # Query fuel/range data for matching vehicles
            ranges = []
            
            for vehicle in vehicles[:10]:  # Check first 10 matches
                kenteken = vehicle.get('kenteken')
                if not kenteken:
                    continue
                
                fuel_params = {"kenteken": kenteken}
                fuel_response = requests.get(self.FUEL_API_URL, params=fuel_params, timeout=15)
                time.sleep(self.REQUEST_DELAY)
                
                if fuel_response.status_code == 200:
                    fuel_data = fuel_response.json()
                    
                    for record in fuel_data:
                        if record.get('brandstof_omschrijving') != 'Elektriciteit':
                            continue
                        
                        # Determine which range field to use
                        if is_phev:
                            range_val = record.get('actie_radius_extern_opladen_wltp')
                        else:
                            range_val = record.get('actie_radius_enkel_elektrisch_wltp')
                        
                        # Try to match battery capacity if provided
                        battery_match = True
                        if battery_kwh is not None:
                            rdw_battery = record.get('nettomaximumvermogen')
                            if rdw_battery:
                                try:
                                    # RDW lists battery in kW, convert for rough comparison
                                    rdw_kwh = int(float(rdw_battery))
                                    yaml_kwh = int(battery_kwh)
                                    # Allow 20% tolerance for battery capacity matching
                                    battery_match = abs(rdw_kwh - yaml_kwh) < (yaml_kwh * 0.2)
                                except (ValueError, TypeError):
                                    pass
                        
                        if range_val and battery_match:
                            try:
                                range_km = int(range_val)
                                if 30 < range_km < 1000:  # Sanity check
                                    ranges.append(range_km)
                                    if self.verbose:
                                        logger.debug(f"  Found: {range_km} km (kenteken: {kenteken})")
                            except (ValueError, TypeError):
                                continue
            
            if ranges:
                # Return the most common range (mode)
                range_counts = Counter(ranges)
                most_common = range_counts.most_common(1)[0][0]
                return most_common
                
        except requests.exceptions.Timeout:
            if self.verbose:
                logger.warning(f"RDW API timeout for {make} {model}")
        except Exception as e:
            if self.verbose:
                logger.error(f"RDW API error for {make} {model}: {e}")
        
        return None
    
    def verify_yaml_entry(self, make: str, model: str, battery_kwh: Optional[str], 
                         yaml_range: int, is_phev: bool = False) -> Dict:
        """
        Verify a single YAML entry against RDW data
        
        Returns:
            Dictionary with verification results
        """
        rdw_range = self.query_rdw_range(make, model, battery_kwh, is_phev)
        
        result = {
            'make': make,
            'model': model,
            'battery_kwh': battery_kwh,
            'yaml_range': yaml_range,
            'rdw_range': rdw_range,
            'is_phev': is_phev,
            'status': 'unknown'
        }
        
        if rdw_range is None:
            result['status'] = 'not_found'
            self.stats['not_found'] += 1
            self.not_found.append(result)
        else:
            # Calculate discrepancy percentage
            diff_pct = abs(rdw_range - yaml_range) / yaml_range
            result['diff_percentage'] = diff_pct * 100
            
            if diff_pct > self.DISCREPANCY_THRESHOLD:
                result['status'] = 'discrepancy'
                self.stats['discrepancies'] += 1
                self.discrepancies.append(result)
            else:
                result['status'] = 'verified'
                self.stats['verified'] += 1
        
        return result
    
    def load_yaml_data(self, yaml_path: str) -> Dict:
        """Load and parse WLTP ranges YAML file"""
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load YAML: {e}")
            sys.exit(1)
    
    def verify_all_entries(self, yaml_data: Dict, limit: Optional[int] = None) -> List[Dict]:
        """Verify all entries in YAML data against RDW"""
        results = []
        processed = 0
        
        # Process main EV entries
        for make, models in yaml_data.items():
            if make == 'PHEV':  # Handle PHEV separately
                continue
            
            if limit and processed >= limit:
                break
            
            logger.info(f"Processing {make}...")
            
            if not isinstance(models, dict):
                continue
            
            for model, batteries in models.items():
                if not isinstance(batteries, dict):
                    continue
                
                for battery_kwh, wltp_range in batteries.items():
                    if not isinstance(wltp_range, int):
                        continue
                    
                    print(f"  {make} {model} ({battery_kwh} kWh): {wltp_range} km", end=" -> ")
                    result = self.verify_yaml_entry(make, model, battery_kwh, wltp_range, is_phev=False)
                    results.append(result)
                    
                    if result['status'] == 'verified':
                        print(f"✓ Verified ({result['rdw_range']} km)")
                    elif result['status'] == 'discrepancy':
                        print(f"⚠️  Discrepancy: RDW says {result['rdw_range']} km ({result['diff_percentage']:.1f}% diff)")
                    else:
                        print("❌ Not found in RDW")
                
                processed += 1
                if limit and processed >= limit:
                    break
        
        # Process PHEV entries
        if 'PHEV' in yaml_data and (not limit or processed < limit):
            logger.info("Processing PHEV entries...")
            phev_data = yaml_data['PHEV']
            
            for make, models in phev_data.items():
                if not isinstance(models, dict):
                    continue
                
                for model, phev_range in models.items():
                    if not isinstance(phev_range, int):
                        continue
                    
                    print(f"  {make} {model} (PHEV): {phev_range} km", end=" -> ")
                    result = self.verify_yaml_entry(make, model, None, phev_range, is_phev=True)
                    results.append(result)
                    
                    if result['status'] == 'verified':
                        print(f"✓ Verified ({result['rdw_range']} km)")
                    elif result['status'] == 'discrepancy':
                        print(f"⚠️  Discrepancy: RDW says {result['rdw_range']} km ({result['diff_percentage']:.1f}% diff)")
                    else:
                        print("❌ Not found in RDW")
        
        return results
    
    def discover_popular_models(self, yaml_data: Dict, top_n: int = 50) -> List[Dict]:
        """
        Query RDW to discover popular EV models not yet in YAML
        
        This queries the most recently registered EVs to identify popular models
        """
        logger.info(f"Discovering top {top_n} popular EV models from RDW...")
        
        try:
            # Query recent EV registrations
            params = {
                "$where": "brandstof_omschrijving='Elektriciteit'",
                "$select": "merk,handelsbenaming,COUNT(*) as count",
                "$group": "merk,handelsbenaming",
                "$order": "count DESC",
                "$limit": top_n
            }
            
            # Note: RDW API might not support GROUP BY, so we'll do client-side aggregation
            # Query recent EVs instead
            params = {
                "$select": "merk,handelsbenaming,datum_eerste_toelating",
                "$where": "datum_eerste_toelating > '20200101'",
                "$order": "datum_eerste_toelating DESC",
                "$limit": 1000
            }
            
            response = requests.get(self.VEHICLE_API_URL, params=params, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to discover models: {response.status_code}")
                return []
            
            vehicles = response.json()
            
            # Count make/model combinations
            model_counts = Counter()
            for v in vehicles:
                make = v.get('merk', '').title()
                model = v.get('handelsbenaming', '').split()[0] if v.get('handelsbenaming') else ''
                if make and model:
                    model_counts[(make, model)] += 1
            
            # Find models not in YAML
            discoveries = []
            for (make, model), count in model_counts.most_common(top_n):
                # Check if make/model exists in YAML
                found = False
                if make in yaml_data:
                    if isinstance(yaml_data[make], dict):
                        if any(model.lower() in yaml_model.lower() for yaml_model in yaml_data[make].keys()):
                            found = True
                
                if not found:
                    discoveries.append({
                        'make': make,
                        'model': model,
                        'registrations': count
                    })
            
            logger.info(f"Found {len(discoveries)} new models to add")
            return discoveries[:20]  # Return top 20 new models
            
        except Exception as e:
            logger.error(f"Error discovering models: {e}")
            return []
    
    def generate_report(self) -> str:
        """Generate a detailed verification report"""
        lines = []
        lines.append("=" * 80)
        lines.append(f"RDW WLTP Range Verification Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 80)
        lines.append("")
        
        # Summary statistics
        total = sum(self.stats.values())
        lines.append("SUMMARY STATISTICS")
        lines.append("-" * 40)
        lines.append(f"Total entries checked:    {total}")
        lines.append(f"✓ Verified:              {self.stats['verified']} ({self.stats['verified']/total*100:.1f}%)")
        lines.append(f"⚠️  Discrepancies found:   {self.stats['discrepancies']} ({self.stats['discrepancies']/total*100:.1f}%)")
        lines.append(f"❌ Not found in RDW:     {self.stats['not_found']} ({self.stats['not_found']/total*100:.1f}%)")
        lines.append("")
        
        # Discrepancies detail
        if self.discrepancies:
            lines.append("DISCREPANCIES (>5% difference)")
            lines.append("-" * 40)
            for d in sorted(self.discrepancies, key=lambda x: x['diff_percentage'], reverse=True):
                phev_tag = " (PHEV)" if d['is_phev'] else ""
                battery_info = f" {d['battery_kwh']} kWh" if d['battery_kwh'] else ""
                lines.append(f"{d['make']} {d['model']}{battery_info}{phev_tag}")
                lines.append(f"  YAML: {d['yaml_range']} km  |  RDW: {d['rdw_range']} km  |  Diff: {d['diff_percentage']:.1f}%")
                lines.append(f"  Suggested: Update YAML to {d['rdw_range']} km")
                lines.append("")
        
        # Not found entries
        if self.not_found:
            lines.append("NOT FOUND IN RDW")
            lines.append("-" * 40)
            lines.append("These entries could not be verified (may be discontinued models or naming mismatch)")
            for nf in self.not_found[:10]:  # Show first 10
                phev_tag = " (PHEV)" if nf['is_phev'] else ""
                battery_info = f" {nf['battery_kwh']} kWh" if nf['battery_kwh'] else ""
                lines.append(f"  {nf['make']} {nf['model']}{battery_info}{phev_tag}: {nf['yaml_range']} km")
            if len(self.not_found) > 10:
                lines.append(f"  ... and {len(self.not_found) - 10} more")
            lines.append("")
        
        lines.append("=" * 80)
        return "\n".join(lines)
    
    def generate_updated_yaml(self, yaml_data: Dict, results: List[Dict]) -> str:
        """Generate updated YAML content with RDW-verified values"""
        # Create a copy and update discrepancies
        updated_data = yaml.safe_load(yaml.dump(yaml_data))  # Deep copy
        
        updates_made = 0
        for result in results:
            if result['status'] == 'discrepancy':
                make = result['make']
                model = result['model']
                battery = result['battery_kwh']
                new_range = result['rdw_range']
                is_phev = result['is_phev']
                
                # Update the value
                if is_phev:
                    if 'PHEV' in updated_data and make in updated_data['PHEV']:
                        if model in updated_data['PHEV'][make]:
                            updated_data['PHEV'][make][model] = new_range
                            updates_made += 1
                else:
                    if make in updated_data and isinstance(updated_data[make], dict):
                        if model in updated_data[make] and isinstance(updated_data[make][model], dict):
                            if battery in updated_data[make][model]:
                                updated_data[make][model][battery] = new_range
                                updates_made += 1
        
        logger.info(f"Updated {updates_made} entries with RDW-verified values")
        
        # Generate YAML with comments preserved (header)
        yaml_str = "# WLTP Range Reference Database\n"
        yaml_str += "# Last updated: " + datetime.now().strftime('%Y-%m-%d') + "\n"
        yaml_str += f"# Updated with RDW Open Data verification - {updates_made} values corrected\n"
        yaml_str += "# Format: Make -> Model Pattern -> Battery Size -> WLTP Range (km)\n\n"
        yaml_str += yaml.dump(updated_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return yaml_str


def main():
    parser = argparse.ArgumentParser(
        description="Verify and enrich WLTP range data using RDW Open Data",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--auto-update', action='store_true',
                      help='Automatically update YAML file with verified RDW data')
    parser.add_argument('--discover-new', action='store_true',
                      help='Query RDW for popular models not in YAML')
    parser.add_argument('--output', type=str,
                      help='Write enriched YAML to specified file')
    parser.add_argument('--verbose', action='store_true',
                      help='Enable detailed logging')
    parser.add_argument('--limit', type=int,
                      help='Limit number of makes to process (for testing)')
    
    args = parser.parse_args()
    
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    yaml_path = os.path.join(project_root, 'data', 'wltp_ranges.yaml')
    
    if not os.path.exists(yaml_path):
        logger.error(f"YAML file not found: {yaml_path}")
        sys.exit(1)
    
    # Initialize verifier
    verifier = RDWRangeVerifier(verbose=args.verbose)
    
    # Load YAML data
    logger.info(f"Loading YAML data from {yaml_path}...")
    yaml_data = verifier.load_yaml_data(yaml_path)
    
    # Verify all entries
    logger.info("Starting verification process (this may take several minutes)...")
    results = verifier.verify_all_entries(yaml_data, limit=args.limit)
    
    # Generate report
    print("\n")
    report = verifier.generate_report()
    print(report)
    
    # Discover new models
    if args.discover_new:
        discoveries = verifier.discover_popular_models(yaml_data)
        if discoveries:
            print("\nNEW MODELS TO CONSIDER ADDING")
            print("-" * 40)
            for d in discoveries:
                print(f"  {d['make']} {d['model']} ({d['registrations']} recent registrations)")
    
    # Auto-update YAML
    if args.auto_update and verifier.stats['discrepancies'] > 0:
        logger.info("\nGenerating updated YAML with RDW-verified values...")
        updated_yaml = verifier.generate_updated_yaml(yaml_data, results)
        
        output_path = args.output or yaml_path
        backup_path = yaml_path + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create backup
        import shutil
        shutil.copy2(yaml_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        
        # Write updated YAML
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(updated_yaml)
        
        logger.info(f"✓ Updated YAML written to: {output_path}")
    
    elif args.output:
        # Write to output file without updating original
        updated_yaml = verifier.generate_updated_yaml(yaml_data, results)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(updated_yaml)
        logger.info(f"✓ Enriched YAML written to: {args.output}")
    
    # Save report
    report_path = os.path.join(project_root, 'tmp', f'rdw_verification_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info(f"\n✓ Full report saved to: {report_path}")


if __name__ == '__main__':
    main()
