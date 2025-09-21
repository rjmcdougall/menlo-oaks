"""
Google Cloud Function for UniFi Protect License Plate Detection
Receives callbacks from UniFi Protect and stores license plate data in BigQuery
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import functions_framework
from flask import Request, jsonify

from bigquery_client import BigQueryClient
from unifi_protect_client import UniFiProtectClient
from gcs_client import GCSClient
from config import Config

# Configure logging for Google Cloud Functions
import google.cloud.logging

# Set up Cloud Logging only if running in GCP
if os.getenv('FUNCTION_NAME'):
    # Running in Google Cloud Functions
    client = google.cloud.logging.Client()
    client.setup_logging()
    
# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # This ensures logs go to stdout/stderr for GCP
    ]
)

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Ensure BigQuery client logger is also configured properly
bq_logger = logging.getLogger('bigquery_client')
bq_logger.setLevel(logging.DEBUG)

# Initialize clients
config = Config()
bq_client = BigQueryClient(config)
unifi_client = UniFiProtectClient(config)
gcs_client = GCSClient(config) if config.STORE_IMAGES else None


@functions_framework.http
def main(request: Request) -> Dict[str, Any]:
    """
    Main Cloud Function entry point with routing support.
    Handles both license plate webhooks and health checks.
    
    Args:
        request: HTTP request
        
    Returns:
        JSON response
    """
    try:
        # Route based on path and method
        path = request.path.lower().rstrip('/')
        method = request.method.upper()
        
        logger.debug(f"Received {method} request to {path}")
        
        # Health check endpoint
        # Cloud Functions include the function name in the path, so we check for both formats
        if (path.endswith('/health') or path == '/health' or (path == '' and method == 'GET')):
            return health_check(request)
        
        # License plate webhook endpoint (default)
        if method == 'POST':
            return license_plate_webhook(request)
        
        # Invalid route/method combination
        logger.warning(f"Invalid request: {method} {path}")
        return jsonify({
            "error": "Invalid endpoint",
            "message": "Use POST for webhooks or GET /health for health checks",
            "received": {"method": method, "path": path}
        }), 404
        
    except Exception as e:
        logger.error(f"Error in main router: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Internal server error in request router"
        }), 500


def license_plate_webhook(request: Request) -> Dict[str, Any]:
    """
    Process UniFi Protect license plate detection callbacks.
    
    Args:
        request: HTTP request from UniFi Protect
        
    Returns:
        JSON response indicating success or failure
    """
    try:
        # Validate request method
        if request.method != 'POST':
            logger.warning(f"Invalid request method for webhook: {request.method}")
            return jsonify({"error": "Only POST requests are allowed for webhooks"}), 405
        
        # Validate content type
        if not request.is_json:
            logger.warning("Request is not JSON")
            return jsonify({"error": "Request must be JSON"}), 400
        
        # Parse request data
        webhook_data = request.get_json()
        if not webhook_data:
            logger.warning("Empty request body")
            return jsonify({"error": "Empty request body"}), 400
        
        logger.info(f"Received webhook data: {json.dumps(webhook_data, indent=2)}")
        
        # Validate webhook signature if configured
        if config.WEBHOOK_SECRET:
            if not validate_webhook_signature(request, config.WEBHOOK_SECRET):
                logger.warning("Invalid webhook signature")
                return jsonify({"error": "Invalid signature"}), 401
        
        # Process the license plate detection
        result = process_license_plate_detection(webhook_data)
        
        if result["success"]:
            logger.info(f"Successfully processed license plate detection: {result['plate_number']}")
            return jsonify({
                "status": "success",
                "message": "License plate data stored successfully",
                "plate_number": result["plate_number"],
                "record_id": result["record_id"]
            }), 200
        else:
            logger.error(f"Failed to process license plate detection: {result['error']}")
            return jsonify({
                "status": "error",
                "message": result["error"]
            }), 500
            
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {str(e)}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500


def process_license_plate_detection(webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process license plate detection data from UniFi Protect webhook.
    Now handles multiple license plates per event.
    
    Args:
        webhook_data: Raw webhook data from UniFi Protect
        
    Returns:
        Dictionary containing success status and relevant data
    """
    try:
        # Extract license plate information from webhook
        logger.info(f"raw webhook: {webhook_data}")
        plate_data = extract_plate_data(webhook_data)
        
        if not plate_data:
            return {"success": False, "error": "No valid license plate data found"}
        
        # Process each license plate found in the event
        record_ids = []
        plate_numbers = []
        
        for plate_info in plate_data["license_plates"]:
            # Enrich each plate with additional information
            enriched_plate = enrich_individual_plate_data(plate_info, webhook_data)
            #enriched_plate = plate_info
            
            # Extract and store thumbnails if image storage is enabled
            plate_number = plate_info["plate_number"]
            event_id = plate_info.get("event_id", "N/A")
            
            # Initialize thumbnail_result for logging purposes
            thumbnail_result = None
            
            if config.STORE_IMAGES and gcs_client:
                logger.info(f"💾 Image storage enabled - processing thumbnails for plate {plate_number}")
                thumbnail_result = process_thumbnails_for_plate(enriched_plate, webhook_data)
                if thumbnail_result:
                    # Add thumbnail information to the enriched plate data
                    logger.info(f"thumbnail result : {thumbnail_result}")
                    enriched_plate.update(thumbnail_result)
                    logger.info(f"enriched plate : {enriched_plate}")
                    
                    # Log thumbnail URLs for tracking
                    if thumbnail_result.get("thumbnail_public_url"):
                        logger.info(f"📸 THUMBNAIL STORED - Plate: {plate_number}, Event: {event_id}, URL: {thumbnail_result['thumbnail_public_url']}")
                    if enriched_plate.get("thumbnail_public_url"):
                        logger.info(f"📸 THUMBNAIL in enriched - Plate: {plate_number}, Event: {event_id}, URL: {enriched_plate['thumbnail_public_url']}")
                    
                    if thumbnail_result.get("cropped_thumbnail_public_url"):
                        logger.info(f"🔍 CROPPED THUMBNAIL STORED - Plate: {plate_number}, Event: {event_id}, URL: {thumbnail_result['cropped_thumbnail_public_url']}")
                    
                    # Log additional thumbnail metadata
                    thumbnail_size = thumbnail_result.get("thumbnail_size_bytes", "unknown")
                    thumbnail_type = thumbnail_result.get("thumbnail_content_type", "unknown")
                    logger.info(f"📊 Thumbnail metadata - Plate: {plate_number}, Size: {thumbnail_size} bytes, Type: {thumbnail_type}")
                else:
                    logger.warning(f"⚠️  No thumbnails processed for plate {plate_number} (Event: {event_id}) - thumbnail processing failed")
            else:
                # Log why thumbnails are not being processed
                if not config.STORE_IMAGES:
                    logger.info(f"🚫 Image storage disabled (STORE_IMAGES=false) - skipping thumbnails for plate {plate_number} (Event: {event_id})")
                elif not gcs_client:
                    logger.warning(f"⚠️  GCS client not initialized - skipping thumbnails for plate {plate_number} (Event: {event_id})")
                else:
                    logger.warning(f"⚠️  Unknown reason - skipping thumbnails for plate {plate_number} (Event: {event_id})")
            
            # Store in BigQuery (now with thumbnail URLs if processed)
            logger.info(f"Calling bq insert - Plate: {plate_number} {enriched_plate}")
            if enriched_plate.get("thumbnail_public_url"):
                 logger.info(f"📸 THUMBNAIL in enriched - Plate: {plate_number}, Event: {event_id}, URL: {enriched_plate['thumbnail_public_url']}")
            record_id = bq_client.insert_license_plate_record(enriched_plate)
            logger.info(f"Called bq insert, record_id: {record_id}")
            record_ids.append(record_id)
            plate_numbers.append(plate_info["plate_number"])
        
        return {
            "success": True,
            "plate_number": ", ".join(plate_numbers),  # Join multiple plates for response
            "record_id": record_ids[0] if record_ids else None,  # Return first record ID
            "total_plates": len(plate_numbers),
            "all_record_ids": record_ids
        }
        
    except Exception as e:
        logger.error(f"Error processing license plate detection: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}


def extract_plate_data(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from UniFi Protect webhook payload.
    Handles both alarm-based format (triggers) and smart detection format (metadata.detected_thumbnails).
    
    Args:
        webhook_data: Raw webhook data
        
    Returns:
        Extracted plate data with multiple plates or None if not found
    """
    try:
        # Check for UniFi Protect alarm format first (triggers-based)
        if "alarm" in webhook_data and "triggers" in webhook_data["alarm"]:
            logger.info("Processing UniFi Protect alarm-based webhook")
            return _extract_plate_data_from_alarm(webhook_data)
        
        # Check for smart detection events (metadata.detected_thumbnails format)
        event_type = webhook_data.get("type", "")
        if event_type == "smart_detection":
            logger.info("Processing smart detection webhook")
            return _extract_plate_data_from_smart_detection(webhook_data)
        
        logger.info(f"Unsupported webhook format - no alarm or smart_detection data found")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting plate data: {str(e)}")
        return None


def _extract_plate_data_from_alarm(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from UniFi Protect alarm format.
    License plate data is in alarm.triggers[].value field.
    
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
                    plate_info = {
                        "plate_number": plate_number.upper().strip(),
                        "timestamp": trigger.get("timestamp"),
                        "device_id": trigger.get("device", ""),
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
                    embedded_plates = _extract_embedded_plate_data_from_webhook(webhook_data, trigger)
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


def _extract_embedded_plate_data_from_webhook(webhook_data: Dict[str, Any], trigger: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract license plate data from embedded webhook data when we have a vehicle trigger
    but no direct plate value. This handles cases where the license plate info is stored
    in the webhook thumbnail data or other embedded fields.
    
    Args:
        webhook_data: Full webhook payload
        trigger: The vehicle trigger that doesn't have a direct plate value
        
    Returns:
        List of plate info dictionaries, empty if none found
    """
    try:
        license_plates = []
        
        # Check if the webhook has a thumbnail field with base64 encoded image
        # In some cases, UniFi Protect includes a thumbnail that might be processed
        # to extract license plate info, but for now we'll focus on explicit data
        
        # Method 1: Check alarm.thumbnail field for any additional metadata
        alarm = webhook_data.get("alarm", {})
        if alarm.get("thumbnail"):
            logger.info("Found alarm thumbnail - this might contain license plate detection data")
            # The thumbnail is base64 encoded but we don't have OCR capabilities here
            # We would need additional processing to extract plate numbers from images
        
        # Method 2: Check if there are any other triggers with license plate data
        # that might be related to this vehicle trigger
        triggers = alarm.get("triggers", [])
        for other_trigger in triggers:
            if other_trigger != trigger:  # Don't check the same trigger
                key = other_trigger.get("key", "")
                if "license_plate" in key and other_trigger.get("value"):
                    # Found a related license plate trigger
                    plate_info = {
                        "plate_number": other_trigger["value"].upper().strip(),
                        "timestamp": other_trigger.get("timestamp"),
                        "device_id": other_trigger.get("device", trigger.get("device", "")),
                        "event_id": other_trigger.get("eventId", trigger.get("eventId", "")),
                        "detection_type": key,
                        "zones": other_trigger.get("zones", trigger.get("zones", {})),
                        "confidence": 0.95
                    }
                    license_plates.append(plate_info)
        
        # Method 3: For now, if we have a vehicle trigger but no license plate data,
        # we'll create a placeholder record to indicate a vehicle was detected
        # This can help with debugging and understanding what events are being sent
        if not license_plates:
            logger.info(f"Creating placeholder record for vehicle trigger {trigger.get('eventId', 'unknown')}")
            
            # Check if we should create a placeholder or skip entirely
            # For now, let's skip and focus on actual license plate detections
            logger.warning(f"Vehicle detected but no license plate data found in webhook for event {trigger.get('eventId', 'unknown')}")
        
        return license_plates
        
    except Exception as e:
        logger.error(f"Error extracting embedded plate data: {str(e)}")
        return []


def _extract_plate_data_from_smart_detection(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate data from smart detection format (metadata.detected_thumbnails).
    This is the legacy format we originally implemented.
    
    Args:
        webhook_data: Raw webhook data with smart detection format
        
    Returns:
        Extracted plate data with multiple plates or None if not found
    """
    try:
        # Extract license plates from metadata.detected_thumbnails
        metadata = webhook_data.get("metadata", {})
        if not metadata:
            logger.warning("No metadata found in webhook data")
            return None
            
        detected_thumbnails = metadata.get("detected_thumbnails", [])
        if not detected_thumbnails:
            logger.warning("No detected thumbnails found in metadata")
            return None
        
        license_plates = []
        for thumbnail in detected_thumbnails:
            # Check if this thumbnail has a vehicle with a license plate name
            if (thumbnail.get("type") == "vehicle" and 
                thumbnail.get("name")):
                
                plate_info = {
                    "plate_number": thumbnail["name"].upper().strip(),
                    "timestamp": thumbnail.get("clock_best_wall"),
                    "cropped_id": thumbnail.get("cropped_id", ""),
                    "confidence": None  # Vehicle detection confidence, not plate confidence
                }
                
                # Extract vehicle attributes if available
                if thumbnail.get("attributes"):
                    attributes = thumbnail["attributes"]
                    if attributes.get("vehicle_type"):
                        vtype = attributes["vehicle_type"]
                        plate_info["vehicle_type"] = {
                            "type": vtype.get("val", ""),
                            "confidence": vtype.get("confidence", 0)
                        }
                    if attributes.get("color"):
                        color = attributes["color"]
                        plate_info["vehicle_color"] = {
                            "color": color.get("val", ""),
                            "confidence": color.get("confidence", 0)
                        }
                
                license_plates.append(plate_info)
        
        if license_plates:
            return {
                "license_plates": license_plates,
                "total_plates": len(license_plates)
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting plate data from smart detection: {str(e)}")
        return None


def enrich_individual_plate_data(plate_info: Dict[str, Any], webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich individual license plate data with additional context from webhook.
    
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
    
    # Add device information (from alarm triggers)
    enriched["device_id"] = plate_info.get("device_id", "")
    
    # Add detection type information (license_plate_unknown, etc.)
    if "detection_type" in plate_info:
        enriched["detection_type"] = plate_info["detection_type"]
    
    # Add timestamp
    enriched["detection_timestamp"] = datetime.utcnow().isoformat()
    
    # Add camera information - try multiple sources
    camera_info = webhook_data.get("camera", {})
    enriched["camera_id"] = camera_info.get("id", "")
    enriched["camera_name"] = camera_info.get("name", "")
    enriched["camera_location"] = camera_info.get("location", "")
    
    # If camera_id is empty, try to use device_id from plate_info (from alarm triggers)
    if not enriched["camera_id"] and plate_info.get("device_id"):
        enriched["camera_id"] = plate_info["device_id"]
        logger.debug(f"Using device_id as camera_id: {plate_info['device_id']}")
    
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
    enriched["raw_detection_data"] = json.dumps(webhook_data) if webhook_data else "{}"
    
    return enriched


def enrich_plate_data(plate_data: Dict[str, Any], webhook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy function - kept for backward compatibility.
    Enrich license plate data with additional context from webhook.
    
    Args:
        plate_data: Extracted plate data
        webhook_data: Full webhook payload
        
    Returns:
        Enriched data dictionary
    """
    enriched = plate_data.copy()
    
    # Add timestamp
    enriched["detection_timestamp"] = datetime.utcnow().isoformat()
    
    # Add camera information
    camera_info = webhook_data.get("camera", {})
    enriched["camera_id"] = camera_info.get("id", "")
    enriched["camera_name"] = camera_info.get("name", "")
    enriched["camera_location"] = camera_info.get("location", "")
    
    # Add event information
    event_info = webhook_data.get("event", {})
    enriched["event_id"] = event_info.get("id", "")
    enriched["event_timestamp"] = event_info.get("start", "")
    
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
    
    return enriched


def process_thumbnails_for_plate(plate_data: Dict[str, Any], webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and store thumbnails for a license plate detection.
    Downloads thumbnails from UniFi Protect and uploads them to Google Cloud Storage.
    
    Args:
        plate_data: License plate data including URLs and IDs
        webhook_data: Full webhook payload for context
        
    Returns:
        Dictionary with thumbnail URLs and metadata, or None if processing fails
    """
    if not gcs_client:
        logger.warning("GCS client not initialized - skipping thumbnail processing")
        return None
    
    try:
        plate_number = plate_data.get("plate_number", "UNKNOWN")
        detection_timestamp = plate_data.get("detection_timestamp", datetime.utcnow().isoformat())
        event_id = plate_data.get("event_id", "")
        camera_id = plate_data.get("camera_id", "")
        cropped_id = plate_data.get("cropped_id", "")
        
        logger.info(f"Processing thumbnails for plate {plate_number}")
        
        thumbnail_results = {}
        
        # 1. Process base64-encoded thumbnail from alarm webhook (most common case)
        if "alarm" in webhook_data and webhook_data["alarm"].get("thumbnail"):
            logger.info(f"Processing base64-encoded alarm thumbnail for plate {plate_number}")
            
            try:
                # Extract base64 thumbnail from alarm
                thumbnail_data = webhook_data["alarm"]["thumbnail"]
                
                # Handle data URL format: "data:image/jpeg;base64,<data>"
                if thumbnail_data.startswith("data:image/"):
                    # Extract the base64 data after the comma
                    header, base64_data = thumbnail_data.split(",", 1)
                    content_type = header.split(":")[1].split(";")[0]  # Extract "image/jpeg"
                    
                    # Decode base64 to bytes
                    import base64
                    image_bytes = base64.b64decode(base64_data)
                    
                    # Upload to GCS using the base64 data
                    upload_result = gcs_client.upload_thumbnail(
                        image_data=image_bytes,
                        plate_number=plate_number,
                        detection_timestamp=detection_timestamp,
                        event_id=event_id,
                        image_type="alarm_thumbnail"
                    )
                    
                    if upload_result.get("success"):
                        thumbnail_results.update({
                            "thumbnail_gcs_path": upload_result["gcs_path"],
                            "thumbnail_public_url": upload_result["public_url"],
                            "thumbnail_filename": upload_result["filename"],
                            "thumbnail_size_bytes": upload_result["size_bytes"],
                            "thumbnail_content_type": upload_result["content_type"],
                            "thumbnail_upload_timestamp": upload_result["upload_timestamp"]
                        })
                        logger.info(f"Successfully stored base64 alarm thumbnail for {plate_number}")
                    else:
                        logger.warning(f"Failed to store base64 alarm thumbnail for {plate_number}: {upload_result.get('error')}")
                else:
                    logger.warning(f"Unexpected thumbnail format for plate {plate_number}: {thumbnail_data[:100]}...")
                    
            except Exception as e:
                logger.error(f"Error processing base64 thumbnail for plate {plate_number}: {str(e)}")
        
        # 2. Process event snapshot (full scene image) from URL
        if config.STORE_EVENT_SNAPSHOTS:
            snapshot_url = plate_data.get("snapshot_url", "")
            if snapshot_url:
                logger.info(f"Processing event snapshot from URL: {snapshot_url}")
                
                # Download and upload event snapshot
                upload_result = gcs_client.download_and_upload_from_url(
                    image_url=snapshot_url,
                    plate_number=plate_number,
                    detection_timestamp=detection_timestamp,
                    event_id=event_id,
                    image_type="event_snapshot"
                )
                
                if upload_result.get("success"):
                    thumbnail_results.update({
                        "thumbnail_gcs_path": upload_result["gcs_path"],
                        "thumbnail_public_url": upload_result["public_url"],
                        "thumbnail_filename": upload_result["filename"],
                        "thumbnail_size_bytes": upload_result["size_bytes"],
                        "thumbnail_content_type": upload_result["content_type"],
                        "thumbnail_upload_timestamp": upload_result["upload_timestamp"]
                    })
                    logger.info(f"Successfully stored event snapshot for {plate_number}")
                else:
                    logger.warning(f"Failed to store event snapshot for {plate_number}: {upload_result.get('error')}")
        
        # 2. Process cropped license plate thumbnail
        if config.STORE_CROPPED_THUMBNAILS and cropped_id and camera_id:
            # Generate URL for cropped thumbnail
            cropped_url = f"https://{config.UNIFI_PROTECT_HOST}:{config.UNIFI_PROTECT_PORT}/proxy/protect/api/cameras/{camera_id}/detections/{cropped_id}/thumbnail"
            
            logger.info(f"Processing cropped thumbnail from URL: {cropped_url}")
            
            # Download and upload cropped thumbnail
            upload_result = gcs_client.download_and_upload_from_url(
                image_url=cropped_url,
                plate_number=plate_number,
                detection_timestamp=detection_timestamp,
                event_id=event_id,
                image_type="license_plate_crop"
            )
            
            if upload_result.get("success"):
                thumbnail_results.update({
                    "cropped_thumbnail_gcs_path": upload_result["gcs_path"],
                    "cropped_thumbnail_public_url": upload_result["public_url"],
                    "cropped_thumbnail_filename": upload_result["filename"],
                    "cropped_thumbnail_size_bytes": upload_result["size_bytes"]
                })
                logger.info(f"Successfully stored cropped thumbnail for {plate_number}")
            else:
                logger.warning(f"Failed to store cropped thumbnail for {plate_number}: {upload_result.get('error')}")
        
        # 3. Alternative: Use UniFi Protect client for authenticated thumbnail extraction
        # This would be used if the webhook doesn't contain direct URLs or if authentication is needed
        if not thumbnail_results and config.is_unifi_protect_configured():
            logger.info("Attempting to extract thumbnails using UniFi Protect client")
            
            import asyncio
            
            async def extract_thumbnails_async():
                try:
                    # Connect to UniFi Protect
                    if await unifi_client.connect():
                        # Extract thumbnails from the detection event
                        thumbnails = await unifi_client.extract_thumbnails_from_detection(webhook_data)
                        
                        for thumbnail_info in thumbnails:
                            if thumbnail_info.get("url"):
                                thumbnail_url = thumbnail_info["url"]
                                thumbnail_type = thumbnail_info.get("type", "snapshot")
                                
                                # Download thumbnail data directly
                                image_data = await unifi_client.download_thumbnail(thumbnail_url)
                                
                                if image_data:
                                    # Upload to GCS
                                    upload_result = gcs_client.upload_thumbnail(
                                        image_data=image_data,
                                        plate_number=plate_number,
                                        detection_timestamp=detection_timestamp,
                                        event_id=event_id,
                                        image_type=thumbnail_type
                                    )
                                    
                                    if upload_result.get("success"):
                                        # Map thumbnail type to result fields
                                        if thumbnail_type == "license_plate_crop":
                                            thumbnail_results.update({
                                                "cropped_thumbnail_gcs_path": upload_result["gcs_path"],
                                                "cropped_thumbnail_public_url": upload_result["public_url"],
                                                "cropped_thumbnail_filename": upload_result["filename"],
                                                "cropped_thumbnail_size_bytes": upload_result["size_bytes"]
                                            })
                                        else:
                                            thumbnail_results.update({
                                                "thumbnail_gcs_path": upload_result["gcs_path"],
                                                "thumbnail_public_url": upload_result["public_url"],
                                                "thumbnail_filename": upload_result["filename"],
                                                "thumbnail_size_bytes": upload_result["size_bytes"],
                                                "thumbnail_content_type": upload_result["content_type"],
                                                "thumbnail_upload_timestamp": upload_result["upload_timestamp"]
                                            })
                        
                        await unifi_client.disconnect()
                        return thumbnail_results
                    
                except Exception as e:
                    logger.error(f"Error in async thumbnail extraction: {str(e)}")
                    return thumbnail_results
            
            # Run async thumbnail extraction
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                thumbnail_results = loop.run_until_complete(extract_thumbnails_async())
                loop.close()
            except Exception as e:
                logger.error(f"Error running async thumbnail extraction: {str(e)}")
        
        if thumbnail_results:
            logger.info(f"Successfully processed {len(thumbnail_results)} thumbnail fields for plate {plate_number}")
            return thumbnail_results
        else:
            logger.warning(f"No thumbnails were processed for plate {plate_number}")
            return None
            
    except Exception as e:
        logger.error(f"Error processing thumbnails for plate {plate_data.get('plate_number', 'unknown')}: {str(e)}", exc_info=True)
        return None


def validate_webhook_signature(request: Request, secret: str) -> bool:
    """
    Validate webhook signature if configured.
    
    Args:
        request: Flask request object
        secret: Webhook secret for validation
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Implementation depends on how UniFi Protect signs webhooks
        # This is a placeholder - adjust based on actual signature method
        signature_header = request.headers.get("X-UniFi-Signature", "")
        
        if not signature_header:
            return False
        
        # Add actual signature validation logic here
        # For now, just check if secret is in the signature
        return secret in signature_header
        
    except Exception as e:
        logger.error(f"Error validating webhook signature: {str(e)}")
        return False


def store_license_plate_image(plate_data: Dict[str, Any]) -> Optional[str]:
    """
    Store license plate image to Google Cloud Storage (optional feature).
    
    Args:
        plate_data: License plate data including image URL
        
    Returns:
        Cloud Storage URL if successful, None otherwise
    """
    try:
        # Placeholder for image storage logic
        # You could download the image from snapshot_url and store in GCS
        logger.info(f"Image storage not implemented for plate: {plate_data['plate_number']}")
        return None
        
    except Exception as e:
        logger.error(f"Error storing image: {str(e)}")
        return None


@functions_framework.http
def health_check(request: Request) -> Dict[str, Any]:
    """
    Health check endpoint for the Cloud Function.
    Provides comprehensive health status including connectivity to dependencies.
    
    Args:
        request: HTTP request from health check probe
        
    Returns:
        JSON response with health status
    """
    try:
        # Only respond to GET requests for health checks
        if request.method != 'GET':
            logger.warning(f"Health check called with invalid method: {request.method}")
            return jsonify({
                "status": "error",
                "message": "Health check only supports GET method",
                "timestamp": datetime.utcnow().isoformat()
            }), 405
        
        logger.debug("Health check requested")
        
        # Basic health response
        health_data = {
            "status": "healthy",
            "service": "unifi-protect-license-plate-detector",
            "version": "2.0.0",
            "timestamp": datetime.utcnow().isoformat(),
            "environment": {
                "function_name": os.getenv("FUNCTION_NAME", "local"),
                "gcp_project": os.getenv("GCP_PROJECT", "unknown"),
                "region": os.getenv("FUNCTION_REGION", "unknown")
            }
        }
        
        # Check configuration
        config_status = check_configuration_health()
        health_data["configuration"] = config_status
        
        # Check BigQuery connectivity (optional, non-blocking)
        try:
            bq_status = check_bigquery_health()
            health_data["bigquery"] = bq_status
        except Exception as e:
            logger.warning(f"BigQuery health check failed: {str(e)}")
            health_data["bigquery"] = {
                "status": "warning",
                "message": "Could not verify BigQuery connectivity",
                "error": str(e)
            }
        
        # Determine overall status
        if config_status["status"] != "healthy":
            health_data["status"] = "unhealthy"
            return jsonify(health_data), 503
        elif health_data.get("bigquery", {}).get("status") == "error":
            health_data["status"] = "degraded"
            return jsonify(health_data), 200
        
        logger.debug("Health check completed successfully")
        return jsonify(health_data), 200
        
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "service": "unifi-protect-license-plate-detector",
            "timestamp": datetime.utcnow().isoformat(),
            "error": "Internal health check error",
            "message": str(e)
        }), 500


def check_configuration_health() -> Dict[str, Any]:
    """
    Check if the application configuration is valid.
    
    Returns:
        Dictionary with configuration health status
    """
    try:
        issues = []
        
        # Check required environment variables
        if not config.GCP_PROJECT_ID:
            issues.append("Missing GCP_PROJECT_ID")
        
        if not config.BIGQUERY_DATASET:
            issues.append("Missing BIGQUERY_DATASET")
            
        if not config.BIGQUERY_TABLE:
            issues.append("Missing BIGQUERY_TABLE")
        
        # Check optional but recommended settings
        warnings = []
        if not config.WEBHOOK_SECRET:
            warnings.append("WEBHOOK_SECRET not configured - webhooks are not authenticated")
            
        if not config.is_unifi_protect_configured():
            warnings.append("UniFi Protect connection not configured - operating in webhook-only mode")
        
        if issues:
            return {
                "status": "unhealthy",
                "issues": issues,
                "warnings": warnings
            }
        
        return {
            "status": "healthy",
            "warnings": warnings,
            "bigquery_dataset": config.BIGQUERY_DATASET,
            "bigquery_table": config.BIGQUERY_TABLE,
            "webhook_auth": bool(config.WEBHOOK_SECRET),
            "unifi_protect_configured": config.is_unifi_protect_configured()
        }
        
    except Exception as e:
        logger.error(f"Configuration health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


def check_bigquery_health() -> Dict[str, Any]:
    """
    Check BigQuery connectivity and table accessibility.
    
    Returns:
        Dictionary with BigQuery health status
    """
    try:
        # Simple test to verify BigQuery client can connect
        from google.cloud import bigquery
        client = bigquery.Client(project=config.GCP_PROJECT_ID)
        
        # Try to get dataset info
        dataset_ref = client.dataset(config.BIGQUERY_DATASET)
        dataset = client.get_dataset(dataset_ref)
        
        # Try to get table info
        table_ref = dataset_ref.table(config.BIGQUERY_TABLE)
        table = client.get_table(table_ref)
        
        return {
            "status": "healthy",
            "dataset_location": dataset.location,
            "table_created": table.created.isoformat() if table.created else None,
            "table_rows": table.num_rows,
            "last_check": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.warning(f"BigQuery health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "last_check": datetime.utcnow().isoformat()
        }


if __name__ == "__main__":
    # For local development
    from flask import Flask
    
    app = Flask(__name__)
    
    # Use the main router for all requests
    app.add_url_rule("/", "main", main, methods=["GET", "POST"])
    app.add_url_rule("/health", "main_health", main, methods=["GET"])
    app.add_url_rule("/<path:path>", "main_catch_all", main, methods=["GET", "POST"])
    
    port = int(os.environ.get("PORT", 8080))
    print(f"\n🚀 Starting UniFi Protect License Plate Detector")
    print(f"📡 Listening on http://0.0.0.0:{port}")
    print(f"💚 Health check: GET /health")
    print(f"📥 Webhooks: POST /")
    print("\n" + "="*50)
    app.run(host="0.0.0.0", port=port, debug=True)
