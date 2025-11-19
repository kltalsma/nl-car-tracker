#!/usr/bin/env python3
import re

# Read the current base_scraper.py
with open('scrapers/base_scraper.py', 'r') as f:
    content = f.read()

# Find the exact location - let's be more specific
# Looking for the lines around features_count assignment
lines = content.split('\n')

# Find the line with "Check required features"
target_idx = None
for i, line in enumerate(lines):
    if '# Check required features' in line and i > 800:
        target_idx = i
        break

if target_idx is None:
    print("ERROR: Could not find target location")
    for i in range(830, 845):
        if i < len(lines):
            print(f"{i}: {lines[i]}")
    exit(1)

print(f"Found target at line {target_idx}")

# Insert the feature inference code before the comment
inference_code = """                                # Apply feature inference to enrich incomplete data
                                from utils.feature_inference import infer_features
                                
                                original_features = car_data.get('features', [])
                                original_count = len([f for f in original_features if f])
                                
                                # Infer additional features
                                enriched_features, inferred_count = infer_features(car_data, original_features)
                                car_data['features'] = enriched_features
                                
                                # Log inference results
                                if inferred_count > 0:
                                    make = car_data.get('make', 'Unknown')
                                    model = car_data.get('model', 'Unknown')
                                    self.logger.info(
                                        f"Feature inference: {make} {model} - "
                                        f"{original_count} scraped + {inferred_count} inferred = {len(enriched_features)} total"
                                    )
                                
"""

# Insert the code
lines.insert(target_idx, inference_code)

# Write back
with open('scrapers/base_scraper.py', 'w') as f:
    f.write('\n'.join(lines))

print(f"✓ Successfully inserted feature inference at line {target_idx}")
