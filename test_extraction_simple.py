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
    test_utility_function()
