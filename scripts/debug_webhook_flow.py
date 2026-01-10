#!/usr/bin/env python3
"""
Debug script to simulate the webhook processing flow that should have created H2F55U record
"""

import logging
import json
from datetime import datetime
from config import Config
from bigquery_client import BigQueryClient

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    """Simulate the webhook processing that should have created H2F55U"""
    try:
        # Recreate the webhook data that was processed (based on the logs)
        webhook_data = {
            "alarm": {
                "name": "Menlo Oaks LPR Cloud Webhook",
                "sources": [
                    {"device": "942A6FD0BCCD", "type": "include"},
                    {"device": "1C6A1B815D69", "type": "include"}
                ],
                "conditions": [
                    {"condition": {"type": "is", "source": "license_plate_unknown"}},
                    {"condition": {"type": "is", "source": "license_plate_known"}},
                    {"condition": {"type": "is", "source": "license_plate_of_interest"}}
                ],
                "triggers": [
                    {
                        "device": "1C6A1B815D69",
                        "value": "H2F55U",
                        "key": "license_plate_unknown", 
                        "group": {"name": "H2F55U"},
                        "zones": {"loiter": [], "line": [], "zone": [1]},
                        "eventId": "68d0186b0116a803e49b76c1",
                        "timestamp": 1758468216321
                    }
                ],
                "thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/..."  # truncated
            }
        }
        
        print("🔍 Simulating webhook processing for H2F55U...")
        print(f"Webhook data structure: alarm with {len(webhook_data['alarm']['triggers'])} triggers")
        
        # Initialize the same clients that main.py uses
        config = Config()
        bq_client = BigQueryClient(config)
        
        # Import the exact functions from main.py to test them
        import sys
        sys.path.append('/Users/rmc/src/protectmenlo')
        
        from main import extract_plate_data, enrich_individual_plate_data
        
        # Step 1: Extract plate data (this should work based on logs)
        print("📋 Step 1: Extracting plate data...")
        plate_data = extract_plate_data(webhook_data)
        
        if not plate_data:
            print("❌ No plate data extracted!")
            return
        
        print(f"✅ Extracted plate data:")
        print(f"   License plates: {len(plate_data['license_plates'])}")
        for i, plate in enumerate(plate_data['license_plates']):
            print(f"     {i+1}. {plate['plate_number']} (confidence: {plate.get('confidence', 'N/A')})")
        
        # Step 2: Process each plate (simulate the main processing loop)
        for plate_info in plate_data["license_plates"]:
            plate_number = plate_info["plate_number"]
            print(f"\n🔧 Step 2: Processing plate {plate_number}...")
            
            # Step 2a: Enrich plate data
            print("  📝 Enriching plate data...")
            enriched_plate = enrich_individual_plate_data(plate_info, webhook_data)
            
            print("  ✅ Enriched plate data:")
            for key, value in enriched_plate.items():
                if key in ['detection_timestamp', 'plate_number', 'confidence', 'device_id', 'event_id']:
                    print(f"     {key}: {value}")
            
            # Step 2b: Check confidence filtering
            confidence = enriched_plate.get('confidence', 0.0)
            min_confidence = config.MIN_CONFIDENCE_THRESHOLD
            print(f"  🎯 Confidence check: {confidence} >= {min_confidence} = {confidence >= min_confidence}")
            
            # Step 2c: Simulate BigQuery insertion
            print("  💾 Attempting BigQuery insertion...")
            try:
                # Add some debug info to the enriched plate data
                enriched_plate['processed_by'] = 'debug_script_simulation'
                enriched_plate['debug_note'] = f'Simulating H2F55U processing at {datetime.now()}'
                
                record_id = bq_client.insert_license_plate_record(enriched_plate)
                print(f"  ✅ BigQuery insertion successful!")
                print(f"     Record ID: {record_id}")
                
                # Verify the record was inserted
                print("  🔍 Verifying insertion...")
                recent_records = bq_client.query_plates_by_number(plate_number, limit=1)
                if recent_records:
                    print(f"  ✅ Verification successful - record found in BigQuery")
                    record = recent_records[0]
                    print(f"     Stored at: {record.get('detection_timestamp', 'N/A')}")
                    print(f"     Record ID: {record.get('record_id', 'N/A')}")
                else:
                    print(f"  ⚠️  Record not immediately visible (BigQuery eventual consistency)")
                
            except Exception as e:
                print(f"  ❌ BigQuery insertion failed: {str(e)}")
                logger.error("Full BigQuery insertion error:", exc_info=True)
                
        print(f"\n✅ Debug simulation completed!")
        
    except Exception as e:
        print(f"❌ Fatal error in simulation: {str(e)}")
        logger.error("Fatal error details:", exc_info=True)

if __name__ == "__main__":
    main()
