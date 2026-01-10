#!/usr/bin/env python3
"""
Debug script to test BigQuery functionality and check recent records
"""

import logging
from datetime import datetime, timedelta
from config import Config
from bigquery_client import BigQueryClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Test BigQuery functionality"""
    try:
        # Initialize config and client
        config = Config()
        bq_client = BigQueryClient(config)
        
        print(f"✅ BigQuery client initialized successfully")
        print(f"   Project: {config.GCP_PROJECT_ID}")
        print(f"   Dataset: {config.BIGQUERY_DATASET}")
        print(f"   Table: {config.BIGQUERY_TABLE}")
        
        # Test 1: Query recent detections
        print(f"\n🔍 Querying recent detections (last 24 hours)...")
        try:
            recent_records = bq_client.query_recent_detections(hours=24, limit=20)
            print(f"   Found {len(recent_records)} recent records")
            
            if recent_records:
                print(f"   Most recent records:")
                for i, record in enumerate(recent_records[:5]):
                    timestamp = record.get('detection_timestamp', 'Unknown')
                    plate = record.get('plate_number', 'Unknown')
                    record_id = record.get('record_id', 'Unknown')[:8] + "..."  # Show first 8 chars
                    print(f"     {i+1}. {timestamp} - {plate} (ID: {record_id})")
            else:
                print(f"   ❌ No recent records found!")
                
        except Exception as e:
            print(f"   ❌ Error querying recent detections: {str(e)}")
        
        # Test 2: Query for specific plate that should have been inserted
        print(f"\n🔍 Querying for plate 'H2F55U' (from recent logs)...")
        try:
            h2f55u_records = bq_client.query_plates_by_number("H2F55U", limit=10)
            print(f"   Found {len(h2f55u_records)} records for H2F55U")
            
            if h2f55u_records:
                print(f"   H2F55U records:")
                for i, record in enumerate(h2f55u_records):
                    timestamp = record.get('detection_timestamp', 'Unknown')
                    record_id = record.get('record_id', 'Unknown')[:8] + "..."
                    thumbnail_url = record.get('thumbnail_public_url', 'No thumbnail')
                    print(f"     {i+1}. {timestamp} - ID: {record_id}")
                    if thumbnail_url != 'No thumbnail':
                        print(f"        Thumbnail: {thumbnail_url[:50]}...")
            else:
                print(f"   ❌ No records found for H2F55U!")
                
        except Exception as e:
            print(f"   ❌ Error querying for H2F55U: {str(e)}")
        
        # Test 3: Check if we can insert a test record
        print(f"\n🧪 Testing BigQuery insertion with sample data...")
        try:
            test_plate_data = {
                "plate_number": "TEST999",
                "confidence": 0.95,
                "detection_timestamp": datetime.now(),
                "device_id": "TEST_DEVICE",
                "camera_id": "TEST_CAMERA",
                "event_id": "test_event_12345",
                "processed_by": "debug_script"
            }
            
            record_id = bq_client.insert_license_plate_record(test_plate_data)
            print(f"   ✅ Test insertion successful! Record ID: {record_id}")
            
            # Query for the test record we just inserted
            print(f"   🔍 Verifying test record insertion...")
            test_records = bq_client.query_plates_by_number("TEST999", limit=1)
            if test_records:
                print(f"   ✅ Test record verified in BigQuery!")
            else:
                print(f"   ❌ Test record not found in BigQuery (may take a moment to appear)")
                
        except Exception as e:
            print(f"   ❌ Error testing insertion: {str(e)}")
            logger.error("Full error details:", exc_info=True)
        
        # Test 4: Get detection stats
        print(f"\n📊 Getting detection statistics (last 7 days)...")
        try:
            stats = bq_client.get_detection_stats(days=7)
            print(f"   Statistics for last 7 days:")
            for stat in stats:
                date = stat.get('detection_date', 'Unknown')
                total = stat.get('total_detections', 0)
                unique = stat.get('unique_plates', 0)
                cameras = stat.get('active_cameras', 0)
                avg_conf = stat.get('avg_confidence', 0)
                print(f"     {date}: {total} detections, {unique} unique plates, {cameras} cameras, {avg_conf:.2f} avg confidence")
                
        except Exception as e:
            print(f"   ❌ Error getting stats: {str(e)}")
        
        print(f"\n✅ Debug script completed!")
        
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        logger.error("Fatal error details:", exc_info=True)

if __name__ == "__main__":
    main()
