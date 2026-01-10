#!/usr/bin/env python3
"""
Simple debug script to test H2F55U processing with extracted functions
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from config import Config
from bigquery_client import BigQueryClient

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def extract_plate_data_from_alarm(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from UniFi Protect alarm format.
    (Copied from main.py to avoid import issues)
    """
    try:
        alarm = webhook_data.get("alarm", {})
        triggers = alarm.get("triggers", [])
        
        if not triggers:
            logger.warning("No triggers found in alarm data")
            return None
        
        license_plates = []
        for trigger in triggers:
            key = trigger.get("key", "")
            
            if key and ("license_plate" in key or key == "vehicle"):
                plate_number = trigger.get("value", "")
                event_id = trigger.get("eventId", "")
                
                if plate_number:
                    plate_info = {
                        "plate_number": plate_number.upper().strip(),
                        "timestamp": trigger.get("timestamp"),
                        "device_id": trigger.get("device", ""),
                        "event_id": event_id,
                        "detection_type": key,
                        "zones": trigger.get("zones", {}),
                        "confidence": 0.95  # Default confidence for alarm format
                    }
                    
                    if trigger.get("group", {}).get("name"):
                        plate_info["group_name"] = trigger["group"]["name"]
                    
                    license_plates.append(plate_info)
        
        if license_plates:
            logger.info(f"Extracted {len(license_plates)} license plates from alarm triggers")
            return {
                "license_plates": license_plates,
                "total_plates": len(license_plates)
            }
        
        logger.warning("No license plate triggers found in alarm data")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting plate data from alarm: {str(e)}")
        return None

def extract_plate_data(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from webhook payload.
    (Copied from main.py to avoid import issues)
    """
    try:
        # Check for alarm format first
        if "alarm" in webhook_data and "triggers" in webhook_data["alarm"]:
            logger.info("Processing UniFi Protect alarm-based webhook")
            return extract_plate_data_from_alarm(webhook_data)
        
        logger.info("Unsupported webhook format - no alarm data found")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting plate data: {str(e)}")
        return None

def enrich_individual_plate_data(plate_info: Dict[str, Any], webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich individual license plate data.
    (Copied from main.py to avoid import issues)
    """
    enriched = {
        "plate_number": plate_info["plate_number"],
        "confidence": plate_info.get("confidence", 0.95),
        "cropped_id": plate_info.get("cropped_id", ""),
        "plate_detection_timestamp": plate_info.get("timestamp")
    }
    
    # Add device information
    enriched["device_id"] = plate_info.get("device_id", "")
    
    # Add detection type information
    if "detection_type" in plate_info:
        enriched["detection_type"] = plate_info["detection_type"]
    
    # Add timestamp
    enriched["detection_timestamp"] = datetime.utcnow()
    
    # Add camera information
    camera_info = webhook_data.get("camera", {})
    enriched["camera_id"] = camera_info.get("id", "")
    enriched["camera_name"] = camera_info.get("name", "")
    enriched["camera_location"] = camera_info.get("location", "")
    
    # If camera_id is empty, use device_id
    if not enriched["camera_id"] and plate_info.get("device_id"):
        enriched["camera_id"] = plate_info["device_id"]
        logger.debug(f"Using device_id as camera_id: {plate_info['device_id']}")
    
    # Add event information
    event_info = webhook_data.get("event", {})
    enriched["event_id"] = event_info.get("id", "")
    enriched["event_timestamp"] = event_info.get("start", "")
    
    # If event_id is empty, use event_id from plate_info
    if not enriched["event_id"] and plate_info.get("event_id"):
        enriched["event_id"] = plate_info["event_id"]
        logger.debug(f"Using trigger event_id: {plate_info['event_id']}")
    
    # Add processing metadata
    enriched["processed_by"] = "debug-script-simulation"
    enriched["processing_timestamp"] = datetime.utcnow()
    
    return enriched

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
                "thumbnail": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/..."
            }
        }
        
        print("🔍 Simulating webhook processing for H2F55U...")
        print(f"Webhook data structure: alarm with {len(webhook_data['alarm']['triggers'])} triggers")
        
        # Initialize clients
        config = Config()
        bq_client = BigQueryClient(config)
        
        # Step 1: Extract plate data
        print("\n📋 Step 1: Extracting plate data...")
        plate_data = extract_plate_data(webhook_data)
        
        if not plate_data:
            print("❌ No plate data extracted!")
            return
        
        print(f"✅ Extracted plate data:")
        print(f"   License plates: {len(plate_data['license_plates'])}")
        for i, plate in enumerate(plate_data['license_plates']):
            print(f"     {i+1}. {plate['plate_number']} (confidence: {plate.get('confidence', 'N/A')})")
        
        # Step 2: Process each plate
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
            
            if confidence < min_confidence:
                print(f"  ❌ Plate {plate_number} filtered out due to low confidence!")
                continue
            
            # Step 2c: BigQuery insertion
            print("  💾 Attempting BigQuery insertion...")
            try:
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
                    print(f"     Record ID: {record.get('record_id', 'N/A')[:8]}...")
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
