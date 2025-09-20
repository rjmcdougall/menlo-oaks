"""
Google Cloud Function for UniFi Protect License Plate Detection
Receives callbacks from UniFi Protect and stores license plate data in BigQuery
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

import functions_framework
from flask import Request, jsonify

from bigquery_client import BigQueryClient
from unifi_protect_client import UniFiProtectClient
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
config = Config()
bq_client = BigQueryClient(config)
unifi_client = UniFiProtectClient(config)


@functions_framework.http
def license_plate_webhook(request: Request) -> Dict[str, Any]:
    """
    Main Cloud Function entry point for UniFi Protect license plate detection callbacks.
    
    Args:
        request: HTTP request from UniFi Protect
        
    Returns:
        JSON response indicating success or failure
    """
    try:
        # Validate request method
        if request.method != 'POST':
            logger.warning(f"Invalid request method: {request.method}")
            return jsonify({"error": "Only POST requests are allowed"}), 405
        
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
        plate_data = extract_plate_data(webhook_data)
        
        if not plate_data:
            return {"success": False, "error": "No valid license plate data found"}
        
        # Process each license plate found in the event
        record_ids = []
        plate_numbers = []
        
        for plate_info in plate_data["license_plates"]:
            # Enrich each plate with additional information
            enriched_plate = enrich_individual_plate_data(plate_info, webhook_data)
            
            # Store in BigQuery
            record_id = bq_client.insert_license_plate_record(enriched_plate)
            record_ids.append(record_id)
            plate_numbers.append(plate_info["plate_number"])
            
            # Optional: Store image or additional processing
            if config.STORE_IMAGES and enriched_plate.get("snapshot_url"):
                store_license_plate_image(enriched_plate)
        
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
    Uses the new metadata.detected_thumbnails structure for license plate detection.
    
    Args:
        webhook_data: Raw webhook data
        
    Returns:
        Extracted plate data with multiple plates or None if not found
    """
    try:
        # Check for smart detection events
        event_type = webhook_data.get("type", "")
        if event_type != "smart_detection":
            logger.info(f"Ignoring non-smart-detection event: {event_type}")
            return None
        
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
        logger.error(f"Error extracting plate data: {str(e)}")
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
        "confidence": 0.95,  # Default confidence since we don't get plate-specific confidence
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
    """
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }), 200


if __name__ == "__main__":
    # For local development
    from flask import Flask
    
    app = Flask(__name__)
    app.add_url_rule("/", "license_plate_webhook", license_plate_webhook, methods=["POST"])
    app.add_url_rule("/health", "health_check", health_check, methods=["GET"])
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
