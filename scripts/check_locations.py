#!/usr/bin/env python3

from create_camera_lookup import CameraLookupManager
from config import Config
from google.cloud import bigquery

config = Config()
client = bigquery.Client(project=config.GCP_PROJECT_ID)

# Check what's currently in the camera lookup table
query = f"""
SELECT device_id, camera_name, camera_location, latitude, longitude 
FROM `{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.camera_lookup`
WHERE camera_location IN ('1000 Colby Ave', '151 Arlington')
ORDER BY camera_location, camera_name
"""

try:
    results = client.query(query).result()
    
    print('Current records for these locations:')
    records = list(results)
    for row in records:
        coords = f'({row.latitude}, {row.longitude})' if (row.latitude and row.longitude) else 'NO COORDS'
        print(f'  {row.camera_name} at {row.camera_location} - {coords}')
        
    if len(records) == 0:
        print('❌ No records found for these locations')
    else:
        print(f'Found {len(records)} records')
        
except Exception as e:
    print(f'Error querying table: {e}')
