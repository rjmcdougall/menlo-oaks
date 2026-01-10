#!/usr/bin/env python3
"""
Simple test script to verify license plate extraction logic without Cloud Functions dependencies
"""

import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Sample webhook data from your actual UniFi Protect system
SAMPLE_WEBHOOK_DATA = {
    'alarm': {
        'name': 'LPR Webhook',
        'sources': [
            {'device': '28704E169362', 'type': 'include'},
            {'device': '942A6FD0AD1A', 'type': 'include'}
        ],
        'conditions': [
            {'condition': {'type': 'is', 'source': 'license_plate_unknown'}},
            {'condition': {'type': 'is', 'source': 'license_plate_known'}},
            {'condition': {'type': 'is', 'source': 'license_plate_of_interest'}}
        ],
        # Base64-encoded sample thumbnail (1x1 pixel PNG)
        'thumbnail': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
        'triggers': [
            {
                'device': '942A6FD0AD1A',
                'value': '7ERF019',
                'key': 'license_plate_unknown',
                'group': {'name': '7ERF019'},
                'zones': {'loiter': [], 'line': [], 'zone': [1]},
                'eventId': '68ce4d9c0202bb03e40cbdbc',
                'timestamp': 1758350753085
            }
        ]
    },
    'timestamp': 1758350754119
}

# Copy the extraction logic from main.py without the Cloud Functions imports
def _extract_plate_data_from_alarm(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from UniFi Protect alarm format.
    License plate data is in alarm.triggers[].value field.
    """
    try:
        alarm = webhook_data.get("alarm", {})
        triggers = alarm.get("triggers", [])
        
        if not triggers:
            print("⚠️  No triggers found in alarm data")
            return None
        
        license_plates = []
        for trigger in triggers:
            # Check if this trigger contains license plate data
            key = trigger.get("key", "")
            if key and "license_plate" in key:
                plate_number = trigger.get("value", "")
                if plate_number:
                    plate_info = {
                        "plate_number": plate_number.upper().strip(),
                        "timestamp": trigger.get("timestamp"),
                        "device_id": trigger.get("device", ""),
                        "event_id": trigger.get("eventId", ""),
                        "detection_type": key,  # license_plate_unknown, license_plate_known, etc.
                        "zones": trigger.get("zones", {}),
                        "confidence": 0.95  # Default confidence since not provided in alarm format
                    }
                    
                    # Extract group information if available
                    if trigger.get("group", {}).get("name"):
                        plate_info["group_name"] = trigger["group"]["name"]
                    
                    license_plates.append(plate_info)
        
        if license_plates:
            print(f"✅ Extracted {len(license_plates)} license plates from alarm triggers")
            return {
                "license_plates": license_plates,
                "total_plates": len(license_plates)
            }
        
        print("⚠️  No license plate triggers found in alarm data")
        return None
        
    except Exception as e:
        print(f"❌ Error extracting plate data from alarm: {str(e)}")
        return None


def extract_plate_data(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from UniFi Protect webhook payload.
    Handles both alarm-based format (triggers) and smart detection format.
    """
    try:
        # Check for UniFi Protect alarm format first (triggers-based)
        if "alarm" in webhook_data and "triggers" in webhook_data["alarm"]:
            print("ℹ️  Processing UniFi Protect alarm-based webhook")
            return _extract_plate_data_from_alarm(webhook_data)
        
        # Check for smart detection events (metadata.detected_thumbnails format)
        event_type = webhook_data.get("type", "")
        if event_type == "smart_detection":
            print("ℹ️  Processing smart detection webhook")
            print("⚠️  Smart detection format not implemented in this test")
            return None
        
        print("❌ Unsupported webhook format - no alarm or smart_detection data found")
        return None
        
    except Exception as e:
        print(f"❌ Error extracting plate data: {str(e)}")
        return None


def enrich_individual_plate_data(plate_info: Dict[str, Any], webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich individual license plate data with additional context from webhook.
    """
    enriched = {
        "plate_number": plate_info["plate_number"],
        "confidence": plate_info.get("confidence", 0.95),
        "detection_type": plate_info.get("detection_type", ""),
        "device_id": plate_info.get("device_id", ""),
        "event_id": plate_info.get("event_id", ""),
        "zones": plate_info.get("zones", {}),
        "plate_detection_timestamp": plate_info.get("timestamp")
    }
    
    # Add timestamps
    enriched["detection_timestamp"] = datetime.utcnow().isoformat()
    enriched["processing_timestamp"] = datetime.utcnow().isoformat()
    
    # Add processing metadata
    enriched["processed_by"] = "unifi-protect-cloud-function"
    
    return enriched


def test_extraction_and_enrichment():
    """Test the extraction and enrichment functions"""
    print("🧪 Testing UniFi Protect License Plate Extraction")
    print("=" * 60)
    
    print(f"Sample webhook data contains:")
    print(f"  - Alarm name: {SAMPLE_WEBHOOK_DATA['alarm']['name']}")
    print(f"  - Triggers: {len(SAMPLE_WEBHOOK_DATA['alarm']['triggers'])}")
    print(f"  - Expected plate: {SAMPLE_WEBHOOK_DATA['alarm']['triggers'][0]['value']}")
    print(f"  - Has thumbnail: {'Yes' if SAMPLE_WEBHOOK_DATA['alarm'].get('thumbnail') else 'No'}")
    if SAMPLE_WEBHOOK_DATA['alarm'].get('thumbnail'):
        thumbnail_data = SAMPLE_WEBHOOK_DATA['alarm']['thumbnail']
        print(f"  - Thumbnail format: {thumbnail_data[:50]}...")
    print()
    
    print("=== Testing extraction function ===")
    
    # Test extraction
    result = extract_plate_data(SAMPLE_WEBHOOK_DATA)
    
    if result:
        print("✅ Successfully extracted license plate data!")
        print(f"Total plates found: {result['total_plates']}")
        
        for i, plate in enumerate(result['license_plates']):
            print(f"\n📋 Plate {i+1}:")
            print(f"  Plate Number: {plate['plate_number']}")
            print(f"  Detection Type: {plate.get('detection_type', 'N/A')}")
            print(f"  Device ID: {plate.get('device_id', 'N/A')}")
            print(f"  Event ID: {plate.get('event_id', 'N/A')}")
            print(f"  Timestamp: {plate.get('timestamp', 'N/A')}")
            print(f"  Zones: {plate.get('zones', 'N/A')}")
            print(f"  Group Name: {plate.get('group_name', 'N/A')}")
            
        # Test enrichment with first plate
        if result['license_plates']:
            print("\n=== Testing enrichment function ===")
            first_plate = result['license_plates'][0]
            enriched = enrich_individual_plate_data(first_plate, SAMPLE_WEBHOOK_DATA)
            
            print("✅ Successfully enriched license plate data!")
            print(f"\n📋 Enriched fields:")
            for key, value in enriched.items():
                if key not in ['processing_timestamp', 'detection_timestamp']:  # Skip dynamic fields
                    print(f"  {key}: {value}")
                    
    else:
        print("❌ No license plate data extracted")
    
    print("\n" + "=" * 60)
    print("✅ Testing completed!")


def test_thumbnail_processing():
    """Test thumbnail processing functionality"""
    print("\n=== Testing thumbnail processing ===")
    
    try:
        import base64
        
        # Check if webhook has thumbnail data
        alarm = SAMPLE_WEBHOOK_DATA.get("alarm", {})
        thumbnail_data = alarm.get("thumbnail")
        
        if thumbnail_data:
            print("✅ Found thumbnail data in webhook")
            print(f"  - Thumbnail format: {thumbnail_data[:50]}...")
            
            # Test base64 decoding
            if thumbnail_data.startswith("data:image/"):
                try:
                    # Extract the base64 data after the comma
                    header, base64_data = thumbnail_data.split(",", 1)
                    content_type = header.split(":")[1].split(";")[0]  # Extract "image/png"
                    
                    # Decode base64 to bytes
                    image_bytes = base64.b64decode(base64_data)
                    
                    print(f"✅ Successfully decoded base64 thumbnail")
                    print(f"  - Content Type: {content_type}")
                    print(f"  - Image Size: {len(image_bytes)} bytes")
                    print(f"  - Base64 Data Length: {len(base64_data)} characters")
                    
                    # Check if it's a valid PNG header
                    if image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                        print(f"  - Valid PNG header detected")
                    else:
                        print(f"  - Not a PNG image or header not recognized")
                        
                except Exception as e:
                    print(f"❌ Error decoding base64 thumbnail: {str(e)}")
            else:
                print(f"⚠️  Thumbnail data is not in expected data URL format")
        else:
            print("❌ No thumbnail data found in webhook")
            
    except Exception as e:
        print(f"❌ Error testing thumbnail processing: {str(e)}")


def test_bigquery_integration():
    """Test BigQuery integration to verify records are being inserted with thumbnail URLs"""
    print("\n=== Testing BigQuery integration ===")
    
    try:
        from config import config
        from bigquery_client import BigQueryClient
        from datetime import datetime, timedelta
        
        # Initialize BigQuery client
        bq_client = BigQueryClient(config)
        print(f"✅ Connected to BigQuery: {config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.BIGQUERY_TABLE}")
        
        # Query recent detections to see if our system is working
        print("\n📊 Checking recent license plate detections...")
        recent_detections = bq_client.query_recent_detections(hours=1, limit=5)
        
        if recent_detections:
            print(f"✅ Found {len(recent_detections)} recent detection(s) in the past hour")
            
            # Check for records with thumbnail URLs
            records_with_thumbnails = [r for r in recent_detections if r.get('thumbnail_public_url')]
            
            print(f"📸 Records with thumbnail URLs: {len(records_with_thumbnails)}/{len(recent_detections)}")
            
            if records_with_thumbnails:
                print("\n🎯 Recent records with thumbnails:")
                for i, record in enumerate(records_with_thumbnails[:3]):  # Show first 3
                    print(f"  {i+1}. Plate: {record['plate_number']}")
                    print(f"     Time: {record['detection_timestamp']}")
                    print(f"     Thumbnail: {record['thumbnail_public_url'][:80]}...")
                    if record.get('thumbnail_size_bytes'):
                        print(f"     Size: {record['thumbnail_size_bytes']} bytes")
                    print()
            else:
                print("⚠️  No recent records have thumbnail URLs - this suggests STORE_IMAGES might be disabled")
                print("   or thumbnail processing is failing")
        else:
            print("⚠️  No recent detections found in the past hour")
            print("   This could mean no license plates have been detected recently")
        
        # Test inserting a mock record to verify the system works
        print("\n🧪 Testing record insertion with mock thumbnail data...")
        mock_plate_data = {
            "plate_number": "TEST123",
            "confidence": 0.95,
            "detection_timestamp": datetime.utcnow().isoformat(),
            "processing_timestamp": datetime.utcnow().isoformat(),
            "device_id": "test_device_123",
            "event_id": "test_event_456",
            "detection_type": "license_plate_test",
            "processed_by": "test_extraction_simple.py",
            "thumbnail_public_url": "https://storage.googleapis.com/menlo-oaks-thumbnails/test/TEST123_test_thumbnail.png",
            "thumbnail_gcs_path": "test/TEST123_test_thumbnail.png",
            "thumbnail_filename": "TEST123_test_thumbnail.png",
            "thumbnail_size_bytes": 1234,
            "thumbnail_content_type": "image/png",
            "thumbnail_upload_timestamp": datetime.utcnow().isoformat(),
            "vehicle_type": "car",
            "vehicle_color": "blue"
        }
        
        record_id = bq_client.insert_license_plate_record(mock_plate_data)
        print(f"✅ Successfully inserted test record: {record_id}")
        
        # Verify the record was inserted and has thumbnail URL
        print("\n🔍 Verifying inserted test record...")
        test_records = bq_client.query_plates_by_number("TEST123", limit=1)
        
        if test_records and len(test_records) > 0:
            test_record = test_records[0]
            print("✅ Test record found in BigQuery!")
            print(f"  Record ID: {test_record['record_id']}")
            print(f"  Plate: {test_record['plate_number']}")
            print(f"  Thumbnail URL: {test_record.get('thumbnail_public_url', 'NOT SET')}")
            print(f"  Thumbnail Size: {test_record.get('thumbnail_size_bytes', 'NOT SET')} bytes")
            print(f"  Processing System: {test_record.get('processed_by', 'NOT SET')}")
            
            if test_record.get('thumbnail_public_url'):
                print("🎉 SUCCESS: Test record has thumbnail_public_url populated!")
            else:
                print("⚠️  WARNING: Test record missing thumbnail_public_url")
                
            # Clean up test record
            print("\n🧹 Cleaning up test record...")
            try:
                # Delete the test record
                delete_query = f"""
                DELETE FROM `{config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.{config.BIGQUERY_TABLE}`
                WHERE plate_number = 'TEST123' AND processed_by = 'test_extraction_simple.py'
                """
                job = bq_client.client.query(delete_query)
                job.result()  # Wait for the job to complete
                print("✅ Test record cleaned up successfully")
            except Exception as cleanup_error:
                print(f"⚠️  Warning: Could not clean up test record: {str(cleanup_error)}")
                
        else:
            print("❌ Test record not found - insertion may have failed")
            
    except Exception as e:
        print(f"❌ Error testing BigQuery integration: {str(e)}")
        import traceback
        print(f"   Full error: {traceback.format_exc()}")


def test_utility_function():
    """Test the utility function from unifi_protect_client"""
    print("\n=== Testing utility function ===")
    
    try:
        # Import the utility extraction function
        from unifi_protect_client import extract_license_plate_from_webhook
        
        # Test with our sample data
        result = extract_license_plate_from_webhook(SAMPLE_WEBHOOK_DATA)
        
        if result:
            print("✅ Successfully extracted license plate data with utility function!")
            print(f"Primary Plate Number: {result['plate_number']}")
            print(f"Detection Type: {result.get('detection_type', 'N/A')}")
            print(f"Device ID: {result.get('device_id', 'N/A')}")
            print(f"Event ID: {result.get('event_id', 'N/A')}")
            print(f"Total plates found: {result.get('total_plates', 1)}")
            
            if 'all_plates' in result:
                print(f"\n📋 All plates:")
                for i, plate in enumerate(result['all_plates']):
                    print(f"  {i+1}. {plate['plate_number']} ({plate.get('detection_type', 'unknown')})")
                    
        else:
            print("❌ No license plate data extracted")
            
    except Exception as e:
        print(f"❌ Error testing utility extraction: {str(e)}")


if __name__ == "__main__":
    test_extraction_and_enrichment()
    test_thumbnail_processing()
    test_bigquery_integration()
    test_utility_function()
