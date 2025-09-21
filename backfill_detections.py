#!/usr/bin/env python3
"""
Backfill script to populate BigQuery with historical license plate detections from UniFi Protect.

This script connects to your UniFi Protect system, retrieves all historical license plate
detection events, and inserts them into the BigQuery table.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import argparse

from config import Config
from bigquery_client import BigQueryClient
from unifi_protect_client import UniFiProtectClient
from gcs_client import GCSClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class DetectionBackfiller:
    """Handles backfilling of license plate detection data."""
    
    def __init__(self, store_thumbnails: bool = True):
        """Initialize the backfiller with configuration and clients."""
        self.config = Config()
        self.bq_client = BigQueryClient(self.config)
        self.unifi_client = UniFiProtectClient(self.config)
        self.gcs_client = GCSClient(self.config) if store_thumbnails else None
        self.store_thumbnails = store_thumbnails
        self.processed_events = set()  # Track processed event IDs to avoid duplicates
        
        if store_thumbnails and self.gcs_client:
            logger.info(f"Thumbnail storage enabled - using bucket: {self.config.GCS_THUMBNAIL_BUCKET}")
        elif store_thumbnails:
            logger.warning("Thumbnail storage requested but GCS client initialization failed")
        else:
            logger.info("Thumbnail storage disabled")
    
    async def run_backfill(self, days: int = 30, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run the backfill process for the specified number of days.
        
        Args:
            days: Number of days to look back
            dry_run: If True, don't actually insert data, just show what would be processed
            
        Returns:
            Summary of the backfill process
        """
        logger.info(f"Starting backfill for last {days} days (dry_run={dry_run})")
        
        try:
            # Connect to UniFi Protect
            if not await self.unifi_client.connect():
                raise Exception("Failed to connect to UniFi Protect")
            
            # Get all events with license plate detections
            events = await self._get_license_plate_events(days)
            logger.info(f"Found {len(events)} license plate detection events")
            
            if not events:
                return {
                    "success": True,
                    "message": "No license plate events found",
                    "events_processed": 0,
                    "records_inserted": 0
                }
            
            # Process each event
            records_inserted = 0
            errors = []
            
            for event in events:
                try:
                    result = await self._process_event(event, dry_run)
                    if result["success"]:
                        records_inserted += result.get("records_inserted", 0)
                    else:
                        errors.append(f"Event {event['id']}: {result['error']}")
                        
                except Exception as e:
                    error_msg = f"Error processing event {event.get('id', 'unknown')}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            summary = {
                "success": True,
                "events_found": len(events),
                "events_processed": len(events) - len(errors),
                "records_inserted": records_inserted,
                "errors": errors,
                "dry_run": dry_run
            }
            
            logger.info(f"Backfill completed: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"Backfill failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "events_processed": 0,
                "records_inserted": 0
            }
        finally:
            await self.unifi_client.disconnect()
    
    async def _get_license_plate_events(self, days: int) -> List[Dict[str, Any]]:
        """
        Get all license plate detection events from the specified time period.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of events with license plate detections
        """
        # UniFi Protect API might have limits on how much history we can fetch at once
        # So we'll fetch in chunks of 7 days to be safe
        all_events = []
        chunk_size = 7  # days per chunk
        
        for start_day in range(0, days, chunk_size):
            end_day = min(start_day + chunk_size, days)
            
            logger.info(f"Fetching events for days {start_day} to {end_day} ago")
            
            try:
                # Get events for this time chunk
                events = await self.unifi_client.get_recent_events(
                    hours=end_day * 24,  # Convert days to hours
                    event_types=["smart_detect"]  # Focus on smart detection events
                )
                
                # Filter for license plate events and deduplicate
                plate_events = []
                for event in events:
                    if (event.get("license_plates") and 
                        event["id"] not in self.processed_events):
                        plate_events.append(event)
                        self.processed_events.add(event["id"])
                
                all_events.extend(plate_events)
                logger.info(f"Found {len(plate_events)} new license plate events in this chunk")
                
            except Exception as e:
                logger.warning(f"Error fetching events for days {start_day}-{end_day}: {str(e)}")
                continue
        
        return all_events
    
    async def _process_event(self, event: Dict[str, Any], dry_run: bool) -> Dict[str, Any]:
        """
        Process a single event and insert license plate records.
        
        Args:
            event: Event data from UniFi Protect
            dry_run: If True, don't actually insert data
            
        Returns:
            Processing result
        """
        try:
            records_inserted = 0
            
            # Process each license plate in the event
            for plate_info in event.get("license_plates", []):
                enriched_plate = await self._enrich_plate_data(plate_info, event)
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would insert: {enriched_plate['plate_number']} at {enriched_plate['detection_timestamp']}")
                    logger.info(f"[DRY RUN] Would insert: {enriched_plate}")
                    records_inserted += 1
                else:
                    # Insert into BigQuery
                    record_id = self.bq_client.insert_license_plate_record(enriched_plate)
                    logger.info(f"Inserted record {record_id} for plate {enriched_plate['plate_number']}")
                    records_inserted += 1
            
            return {
                "success": True,
                "records_inserted": records_inserted
            }
            
        except Exception as e:
            logger.error(f"Error processing event: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _enrich_plate_data(self, plate_info: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich plate data with additional information from the event and camera.
        
        Args:
            plate_info: License plate information
            event: Full event data
            
        Returns:
            Enriched plate data ready for BigQuery
        """
        # Get camera information
        camera_info = await self.unifi_client.get_camera_by_id(event["camera_id"])
        
        # Parse timestamp with better fallback handling
        detection_time = None
        try:
            if plate_info.get("timestamp"):
                detection_time = datetime.fromisoformat(plate_info["timestamp"].replace('Z', '+00:00'))
            elif event.get("start"):
                detection_time = datetime.fromisoformat(event["start"].replace('Z', '+00:00'))
            else:
                # Use current time as fallback if no timestamp is available
                detection_time = datetime.utcnow()
                logger.warning(f"No timestamp found for event {event.get('id', 'unknown')}, using current time")
        except Exception as e:
            # If timestamp parsing fails, use current time
            detection_time = datetime.utcnow()
            logger.warning(f"Failed to parse timestamp for event {event.get('id', 'unknown')}: {str(e)}, using current time")
        
        # Build enriched record
        enriched_plate = {
            "plate_number": plate_info.get("plate_number", ""),
            "confidence": 0.95,  # Default confidence since UniFi doesn't provide plate confidence
            "detection_timestamp": detection_time,
            "plate_detection_timestamp": detection_time,
            "processing_timestamp": datetime.utcnow(),
            "event_timestamp": self._parse_event_timestamp(event.get("start"), detection_time),
            
            # Vehicle information
            "vehicle_type": plate_info.get("vehicle_type", {}).get("type", ""),
            "vehicle_type_confidence": plate_info.get("vehicle_type", {}).get("confidence", 0),
            "vehicle_color": plate_info.get("vehicle_color", {}).get("color", ""),
            "vehicle_color_confidence": plate_info.get("vehicle_color", {}).get("confidence", 0),
            
            # Camera information
            "camera_id": event["camera_id"],
            "camera_name": camera_info.get("name", "") if camera_info else "",
            "camera_location": camera_info.get("location_name", "") if camera_info else "",
            
            # Event information
            "event_id": event["id"],
            "device_id": event["camera_id"],  # Use camera_id as device_id for consistency
            "cropped_id": plate_info.get("cropped_id", ""),
            
            # Metadata
            "processed_by": "backfill_script",
            "raw_detection_data": str(event)  # Store original event data for reference
        }
        
        # Add snapshot URL if available
        snapshot_url = await self.unifi_client.get_snapshot_url(
            event["camera_id"], 
            event["id"]
        )
        if snapshot_url:
            enriched_plate["snapshot_url"] = snapshot_url
        
        # Process thumbnails if enabled
        if self.store_thumbnails and self.gcs_client:
            thumbnail_result = await self._process_thumbnails_for_plate(enriched_plate, event)
            if thumbnail_result:
                enriched_plate.update(thumbnail_result)
        
        return enriched_plate
    
    def _parse_event_timestamp(self, start_timestamp: Optional[str], fallback_time: datetime) -> datetime:
        """
        Parse event timestamp with fallback handling.
        
        Args:
            start_timestamp: ISO format timestamp string from event
            fallback_time: Fallback datetime to use if parsing fails
            
        Returns:
            Parsed datetime or fallback time
        """
        if not start_timestamp:
            return fallback_time
            
        try:
            return datetime.fromisoformat(start_timestamp.replace('Z', '+00:00'))
        except Exception as e:
            logger.warning(f"Failed to parse event start timestamp '{start_timestamp}': {str(e)}, using fallback")
            return fallback_time
    
    async def _process_thumbnails_for_plate(self, plate_data: Dict[str, Any], event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract and store thumbnails for a license plate detection during backfill.
        
        Args:
            plate_data: License plate data including URLs and IDs
            event: Full event data for context
            
        Returns:
            Dictionary with thumbnail URLs and metadata, or None if processing fails
        """
        try:
            plate_number = plate_data.get("plate_number", "UNKNOWN")
            detection_timestamp = plate_data.get("detection_timestamp", datetime.utcnow()).isoformat()
            event_id = plate_data.get("event_id", "")
            camera_id = plate_data.get("camera_id", "")
            cropped_id = plate_data.get("cropped_id", "")
            
            logger.info(f"Processing thumbnails for historical plate {plate_number}")
            
            thumbnail_results = {}
            
            # 1. Process event snapshot (full scene image) using authenticated download
            if self.config.STORE_EVENT_SNAPSHOTS:
                snapshot_url = plate_data.get("snapshot_url", "")
                if snapshot_url:
                    logger.debug(f"Processing historical event snapshot from URL: {snapshot_url}")
                    
                    # Download snapshot using authenticated UniFi client
                    image_data = await self.unifi_client.download_thumbnail(snapshot_url)
                    
                    if image_data:
                        # Upload to GCS using the downloaded image data
                        upload_result = self.gcs_client.upload_thumbnail(
                            image_data=image_data,
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
                            logger.info(f"Successfully stored historical event snapshot for {plate_number}")
                        else:
                            logger.warning(f"Failed to upload historical event snapshot for {plate_number}: {upload_result.get('error')}")
                    else:
                        logger.warning(f"Failed to download historical event snapshot for {plate_number} from {snapshot_url}")
            
            # 2. Process cropped license plate thumbnail using authenticated download
            if self.config.STORE_CROPPED_THUMBNAILS and cropped_id and camera_id:
                # Generate URL for cropped thumbnail
                cropped_url = f"https://{self.config.UNIFI_PROTECT_HOST}:{self.config.UNIFI_PROTECT_PORT}/proxy/protect/api/cameras/{camera_id}/detections/{cropped_id}/thumbnail"
                
                logger.debug(f"Processing historical cropped thumbnail from URL: {cropped_url}")
                
                # Download thumbnail using authenticated UniFi client
                image_data = await self.unifi_client.download_thumbnail(cropped_url)
                
                if image_data:
                    # Upload to GCS using the downloaded image data
                    upload_result = self.gcs_client.upload_thumbnail(
                        image_data=image_data,
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
                        logger.info(f"Successfully stored historical cropped thumbnail for {plate_number}")
                    else:
                        logger.warning(f"Failed to upload historical cropped thumbnail for {plate_number}: {upload_result.get('error')}")
                else:
                    logger.warning(f"Failed to download historical cropped thumbnail for {plate_number} from {cropped_url}")
            
            # 3. Alternative: Use direct UniFi Protect API calls for authenticated thumbnail extraction
            # This handles cases where the webhook URLs might be expired for historical events
            if not thumbnail_results:
                logger.info(f"Attempting direct thumbnail extraction for historical plate {plate_number}")
                
                # Extract thumbnails from the detection event using authenticated API calls
                thumbnails = await self.unifi_client.extract_thumbnails_from_detection({
                    "camera": {"id": camera_id},
                    "event": {"id": event_id},
                    "metadata": event  # Pass full event as metadata context
                })
                
                for thumbnail_info in thumbnails:
                    if thumbnail_info.get("url"):
                        thumbnail_url = thumbnail_info["url"]
                        thumbnail_type = thumbnail_info.get("type", "snapshot")
                        
                        # Download thumbnail data directly
                        image_data = await self.unifi_client.download_thumbnail(thumbnail_url)
                        
                        if image_data:
                            # Upload to GCS
                            upload_result = self.gcs_client.upload_thumbnail(
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
                                logger.info(f"Successfully stored {thumbnail_type} for historical plate {plate_number}")
            
            if thumbnail_results:
                logger.info(f"Successfully processed {len(thumbnail_results)} thumbnail fields for historical plate {plate_number}")
                return thumbnail_results
            else:
                logger.warning(f"No thumbnails were processed for historical plate {plate_number}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing thumbnails for historical plate {plate_data.get('plate_number', 'unknown')}: {str(e)}", exc_info=True)
            return None


async def main():
    """Main entry point for the backfill script."""
    parser = argparse.ArgumentParser(description="Backfill license plate detections to BigQuery")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without inserting data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--no-thumbnails", action="store_true", help="Skip thumbnail extraction and storage")
    parser.add_argument("--thumbnails-only", action="store_true", help="Only process thumbnails, skip BigQuery insertion (requires existing data)")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Determine thumbnail processing based on command line options
    store_thumbnails = not args.no_thumbnails
    if args.thumbnails_only and args.no_thumbnails:
        print("❌ Error: --thumbnails-only and --no-thumbnails are mutually exclusive")
        sys.exit(1)
    
    backfiller = DetectionBackfiller(store_thumbnails=store_thumbnails)
    
    try:
        result = await backfiller.run_backfill(days=args.days, dry_run=args.dry_run)
        
        if result["success"]:
            print(f"\n✅ Backfill completed successfully!")
            print(f"   Events found: {result.get('events_found', 0)}")
            print(f"   Events processed: {result.get('events_processed', 0)}")
            print(f"   Records inserted: {result.get('records_inserted', 0)}")
            
            if result.get("errors"):
                print(f"   Errors encountered: {len(result['errors'])}")
                for error in result["errors"]:
                    print(f"     - {error}")
            
            if args.dry_run:
                print(f"\n💡 This was a dry run. Use --dry-run=false to actually insert data.")
        else:
            print(f"\n❌ Backfill failed: {result.get('error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print(f"\n⏹️  Backfill interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Unexpected error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
