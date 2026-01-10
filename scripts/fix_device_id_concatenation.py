#!/usr/bin/env python3
"""
Fix for device_id concatenation issues in webhook processing.
This script adds validation and fixes to prevent device_id values from being concatenated.
"""

import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def validate_device_id(device_id: str) -> bool:
    """
    Validate that a device_id is properly formatted.
    
    Args:
        device_id: The device ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not device_id:
        return False
    
    # Device IDs should be either 12 or 24 hexadecimal characters
    # 12 characters: MAC address format (e.g., 942A6FD0AD1A)
    # 24 characters: Extended format (e.g., 67cdebed0116cb03e40192f1)
    if len(device_id) not in [12, 24]:
        logger.warning(f"Invalid device_id length: {device_id} (length: {len(device_id)})")
        return False
    
    # Should only contain hexadecimal characters
    if not re.match(r'^[a-fA-F0-9]+$', device_id):
        logger.warning(f"Invalid device_id format (non-hex characters): {device_id}")
        return False
    
    return True

def clean_device_id(device_id: str) -> str:
    """
    Clean and validate a device_id, preventing concatenation issues.
    
    Args:
        device_id: Raw device ID from webhook
        
    Returns:
        Cleaned device ID
    """
    if not device_id:
        return ""
    
    # Strip whitespace and convert to uppercase for consistency
    cleaned_id = device_id.strip().upper()
    
    # Check if it looks like a concatenated ID (48 characters = 24+24)
    if len(cleaned_id) == 48:
        logger.warning(f"Potential concatenated device_id detected: {cleaned_id}")
        
        # Try to split it in half and use the first half
        first_half = cleaned_id[:24]
        second_half = cleaned_id[24:]
        
        logger.warning(f"  First half: {first_half}")
        logger.warning(f"  Second half: {second_half}")
        
        # Use the first half if it's valid
        if validate_device_id(first_half):
            logger.info(f"Using first half of concatenated device_id: {first_half}")
            return first_half
        elif validate_device_id(second_half):
            logger.info(f"Using second half of concatenated device_id: {second_half}")
            return second_half
        else:
            logger.error(f"Both halves of concatenated device_id are invalid")
            return ""
    
    # Validate the cleaned ID
    if validate_device_id(cleaned_id):
        return cleaned_id
    else:
        logger.error(f"Invalid device_id after cleaning: {cleaned_id}")
        return ""

def extract_device_id_from_trigger(trigger: Dict[str, Any]) -> str:
    """
    Safely extract device_id from a webhook trigger.
    
    Args:
        trigger: Trigger data from webhook
        
    Returns:
        Cleaned device_id
    """
    raw_device_id = trigger.get("device", "")
    cleaned_device_id = clean_device_id(raw_device_id)
    
    if raw_device_id and not cleaned_device_id:
        logger.error(f"Failed to clean device_id from trigger: {raw_device_id}")
    
    return cleaned_device_id

def fixed_extract_plate_data_from_alarm(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fixed version of _extract_plate_data_from_alarm with proper device_id handling.
    
    Args:
        webhook_data: Raw webhook data with alarm format
        
    Returns:
        Extracted plate data with multiple plates or None if not found
    """
    try:
        alarm = webhook_data.get("alarm", {})
        triggers = alarm.get("triggers", [])
        
        if not triggers:
            logger.warning("No triggers found in alarm data")
            return None
        
        license_plates = []
        for trigger in triggers:
            # Check if this trigger contains license plate data
            key = trigger.get("key", "")
            
            # Handle different trigger key formats:
            # 1. Direct license plate triggers: "license_plate", "license_plate_unknown", etc.
            # 2. Vehicle triggers that might contain license plate info
            if key and ("license_plate" in key or key == "vehicle"):
                # For direct license plate triggers, get the plate from 'value'
                plate_number = trigger.get("value", "")
                
                # If no plate number but we have an eventId, we need to fetch the actual event details
                # This commonly happens with "vehicle" triggers where the license plate is detected
                # but stored in the actual event data rather than the trigger
                event_id = trigger.get("eventId", "")
                
                if plate_number:
                    # Direct license plate trigger with value
                    # FIXED: Use the new safe device_id extraction
                    device_id = extract_device_id_from_trigger(trigger)
                    
                    plate_info = {
                        "plate_number": plate_number.upper().strip(),
                        "timestamp": trigger.get("timestamp"),
                        "device_id": device_id,  # Now properly validated
                        "event_id": event_id,
                        "detection_type": key,  # license_plate_unknown, license_plate_known, etc.
                        "zones": trigger.get("zones", {}),
                        "confidence": 0.95  # Default confidence since not provided in alarm format
                    }
                    
                    # Extract group information if available
                    if trigger.get("group", {}).get("name"):
                        plate_info["group_name"] = trigger["group"]["name"]
                    
                    license_plates.append(plate_info)
                    
                elif event_id and key == "vehicle":
                    # Vehicle trigger without direct plate number - need to check if webhook has embedded plate data
                    logger.info(f"Found vehicle trigger with eventId {event_id}, checking for embedded license plate data")
                    
                    # Check if the webhook contains thumbnail data with license plate info
                    embedded_plates = fixed_extract_embedded_plate_data_from_webhook(webhook_data, trigger)
                    if embedded_plates:
                        license_plates.extend(embedded_plates)
                    else:
                        logger.warning(f"Vehicle trigger {event_id} found but no license plate data available in webhook")
        
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

def fixed_extract_embedded_plate_data_from_webhook(webhook_data: Dict[str, Any], trigger: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fixed version of _extract_embedded_plate_data_from_webhook with proper device_id handling.
    
    Args:
        webhook_data: Full webhook payload
        trigger: The vehicle trigger that doesn't have a direct plate value
        
    Returns:
        List of plate info dictionaries, empty if none found
    """
    try:
        license_plates = []
        
        # Get the device_id from the current trigger safely
        trigger_device_id = extract_device_id_from_trigger(trigger)
        
        # Check if there are any other triggers with license plate data
        # that might be related to this vehicle trigger
        alarm = webhook_data.get("alarm", {})
        triggers = alarm.get("triggers", [])
        
        for other_trigger in triggers:
            if other_trigger != trigger:  # Don't check the same trigger
                key = other_trigger.get("key", "")
                if "license_plate" in key and other_trigger.get("value"):
                    # Found a related license plate trigger
                    
                    # FIXED: Use safe device_id extraction instead of potential concatenation
                    other_device_id = extract_device_id_from_trigger(other_trigger)
                    
                    # Use the device_id from the license plate trigger if available,
                    # otherwise fall back to the vehicle trigger's device_id
                    final_device_id = other_device_id if other_device_id else trigger_device_id
                    
                    # Get event_id safely
                    other_event_id = other_trigger.get("eventId", "")
                    trigger_event_id = trigger.get("eventId", "")
                    final_event_id = other_event_id if other_event_id else trigger_event_id
                    
                    plate_info = {
                        "plate_number": other_trigger["value"].upper().strip(),
                        "timestamp": other_trigger.get("timestamp"),
                        "device_id": final_device_id,  # Now properly validated
                        "event_id": final_event_id,
                        "detection_type": key,
                        "zones": other_trigger.get("zones", trigger.get("zones", {})),
                        "confidence": 0.95
                    }
                    
                    logger.info(f"Extracted embedded plate: {plate_info['plate_number']} with device_id: {final_device_id}")
                    license_plates.append(plate_info)
        
        return license_plates
        
    except Exception as e:
        logger.error(f"Error extracting embedded plate data: {str(e)}")
        return []

def fixed_enrich_individual_plate_data(plate_info: Dict[str, Any], webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fixed version of enrich_individual_plate_data with proper device_id validation.
    
    Args:
        plate_info: Individual plate data from detected_thumbnails
        webhook_data: Full webhook payload
        
    Returns:
        Enriched data dictionary for a single license plate
    """
    enriched = {
        "plate_number": plate_info["plate_number"],
        "confidence": plate_info.get("confidence", 0.95),  # Use confidence from plate_info if available
        "cropped_id": plate_info.get("cropped_id", ""),
        "plate_detection_timestamp": plate_info.get("timestamp")
    }
    
    # Add vehicle attributes if available
    if "vehicle_type" in plate_info:
        enriched["vehicle_type"] = plate_info["vehicle_type"]["type"]
        enriched["vehicle_type_confidence"] = plate_info["vehicle_type"]["confidence"]
    
    if "vehicle_color" in plate_info:
        enriched["vehicle_color"] = plate_info["vehicle_color"]["color"]
        enriched["vehicle_color_confidence"] = plate_info["vehicle_color"]["confidence"]
    
    # FIXED: Add device information (from alarm triggers) with proper validation
    raw_device_id = plate_info.get("device_id", "")
    cleaned_device_id = clean_device_id(raw_device_id)
    enriched["device_id"] = cleaned_device_id
    
    if raw_device_id and not cleaned_device_id:
        logger.error(f"Failed to clean device_id in enrichment: {raw_device_id}")
    
    # Add detection type information (license_plate_unknown, etc.)
    if "detection_type" in plate_info:
        enriched["detection_type"] = plate_info["detection_type"]
    
    # Add timestamp
    from datetime import datetime
    enriched["detection_timestamp"] = datetime.utcnow().isoformat()
    
    # Add camera information - try multiple sources
    camera_info = webhook_data.get("camera", {})
    enriched["camera_id"] = camera_info.get("id", "")
    enriched["camera_name"] = camera_info.get("name", "")
    enriched["camera_location"] = camera_info.get("location", "")
    
    # If camera_id is empty, try to use device_id from plate_info (from alarm triggers)
    # FIXED: Make sure we're not using an invalid device_id
    if not enriched["camera_id"] and cleaned_device_id:
        enriched["camera_id"] = cleaned_device_id
        logger.debug(f"Using cleaned device_id as camera_id: {cleaned_device_id}")
    
    # Add event information - try multiple sources
    event_info = webhook_data.get("event", {})
    enriched["event_id"] = event_info.get("id", "")
    enriched["event_timestamp"] = event_info.get("start", "")
    
    # If event_id is empty, try to use event_id from plate_info (from alarm triggers)
    if not enriched["event_id"] and plate_info.get("event_id"):
        enriched["event_id"] = plate_info["event_id"]
        logger.debug(f"Using trigger event_id: {plate_info['event_id']}")
    
    # Add image information if available
    if "snapshot" in webhook_data:
        enriched["snapshot_url"] = webhook_data["snapshot"].get("url", "")
        enriched["image_width"] = webhook_data["snapshot"].get("width", 0)
        enriched["image_height"] = webhook_data["snapshot"].get("height", 0)
    
    # Add location data if available
    if "location" in webhook_data:
        enriched["latitude"] = webhook_data["location"].get("lat", 0.0)
        enriched["longitude"] = webhook_data["location"].get("lng", 0.0)
    
    # Add processing metadata
    enriched["processed_by"] = "unifi-protect-cloud-function"
    enriched["processing_timestamp"] = datetime.utcnow().isoformat()
    
    # Store raw detection data for debugging
    import json
    enriched["raw_detection_data"] = json.dumps(webhook_data) if webhook_data else "{}"
    
    return enriched

def audit_database_device_ids():
    """
    Audit the database for potentially problematic device_ids and generate a report.
    """
    try:
        from bigquery_client import BigQueryClient
        from config import Config
        
        config = Config()
        client = BigQueryClient(config)
        
        full_table_name = config.get_bigquery_table_full_name()
        
        print("🔍 Auditing database for device_id issues...")
        
        # Query for unusual device_id patterns
        query = f"""
        SELECT 
            device_id,
            LENGTH(device_id) as id_length,
            COUNT(*) as count,
            MIN(detection_timestamp) as first_seen,
            MAX(detection_timestamp) as last_seen,
            ARRAY_AGG(DISTINCT plate_number LIMIT 3) as sample_plates
        FROM `{full_table_name}`
        WHERE device_id IS NOT NULL AND device_id != ''
        GROUP BY device_id
        HAVING LENGTH(device_id) NOT IN (12, 24) OR device_id NOT REGEXP r'^[a-fA-F0-9]+$'
        ORDER BY count DESC
        """
        
        results = client.client.query(query).result()
        
        problematic_count = 0
        for row in results:
            problematic_count += 1
            device_id = row.device_id
            id_length = row.id_length
            count = row.count
            first_seen = row.first_seen
            last_seen = row.last_seen
            sample_plates = row.sample_plates
            
            print(f"\n❌ Problematic device_id: {device_id}")
            print(f"   Length: {id_length} (expected: 12 or 24)")
            print(f"   Count: {count} records")
            print(f"   First seen: {first_seen}")
            print(f"   Last seen: {last_seen}")
            print(f"   Sample plates: {sample_plates}")
            
            # Check if it looks like concatenation
            if id_length == 48:
                first_half = device_id[:24]
                second_half = device_id[24:]
                print(f"   Possible concatenation: {first_half} + {second_half}")
        
        if problematic_count == 0:
            print("✅ No problematic device_ids found in the database!")
        else:
            print(f"\n📊 Summary: Found {problematic_count} problematic device_id patterns")
            
    except Exception as e:
        print(f"❌ Error auditing database: {str(e)}")

if __name__ == "__main__":
    # Run the audit
    audit_database_device_ids()
