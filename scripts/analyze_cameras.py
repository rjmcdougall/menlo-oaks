#!/usr/bin/env python3

from create_camera_lookup import CameraLookupManager
from config import Config
from google.cloud import bigquery

config = Config()
client = bigquery.Client(project=config.GCP_PROJECT_ID)

# Get all records grouped by location
query = f"""
SELECT 
    camera_location,
    COUNT(*) as total_records,
    COUNT(latitude) as records_with_coords,
    COUNT(*) - COUNT(latitude) as records_without_coords,
    MAX(latitude) as sample_lat,
    MAX(longitude) as sample_lng
FROM `{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.camera_lookup`
GROUP BY camera_location
ORDER BY records_without_coords DESC, camera_location
"""

try:
    results = client.query(query).result()
    
    print('Camera Location Analysis:')
    print('=' * 80)
    total_missing = 0
    
    for row in results:
        status = "✅ ALL GEOCODED" if row.records_without_coords == 0 else f"❌ {row.records_without_coords} MISSING COORDS"
        coords = f"({row.sample_lat}, {row.sample_lng})" if row.sample_lat else "NO COORDS"
        print(f'{row.camera_location:20} | {row.total_records:2} records | {status} | {coords}')
        total_missing += row.records_without_coords
    
    print('=' * 80)
    print(f'Total records missing coordinates: {total_missing}')
        
except Exception as e:
    print(f'Error querying table: {e}')
