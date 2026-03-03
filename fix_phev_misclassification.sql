-- Fix PHEV misclassification bug
-- Cars marked as "Full Electric" with 50-100km range are actually PHEVs
-- Real EVs have 300+ km range

-- Step 1: Check how many cars will be affected
SELECT 
    COUNT(*) as total_affected,
    make,
    model
FROM cars
WHERE fuel_type = 'Full Electric'
  AND (
      (electric_range_km BETWEEN 50 AND 100)
      OR (wltp_reference_range_km BETWEEN 50 AND 100 AND electric_range_km IS NULL)
  )
GROUP BY make, model
ORDER BY total_affected DESC;

-- Step 2: Update the fuel_type to PHEV for misclassified cars
UPDATE cars
SET 
    fuel_type = 'PHEV',
    last_updated = CURRENT_TIMESTAMP
WHERE fuel_type = 'Full Electric'
  AND (
      (electric_range_km BETWEEN 50 AND 100)
      OR (wltp_reference_range_km BETWEEN 50 AND 100 AND electric_range_km IS NULL)
  );

-- Step 3: Also upgrade "Hybrid" to "PHEV" if electric range is present
UPDATE cars
SET 
    fuel_type = 'PHEV',
    last_updated = CURRENT_TIMESTAMP
WHERE fuel_type = 'Hybrid'
  AND (electric_range_km IS NOT NULL OR wltp_reference_range_km IS NOT NULL);

-- Step 4: Verify the changes
SELECT 
    COUNT(*) as count,
    fuel_type,
    make,
    model
FROM cars
WHERE (make = 'Lynk' AND model LIKE '%Co%')
   OR (make = 'Kia' AND model LIKE '%Sportage%')
   OR (make = 'Hyundai' AND model LIKE '%TUCSON%')
GROUP BY fuel_type, make, model
ORDER BY make, model, fuel_type;
