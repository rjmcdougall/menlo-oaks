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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class DetectionBackfiller:
    """Handles backfilling of license plate detection data."""
    
    def __init__(self):
        """Initialize the backfiller with configuration and clients."""
        self.config = Config()
        self.bq_client = BigQueryClient(self.config)
        self.unifi_client = UniFiProtectClient(self.config)
        self.processed_events = set()  # Track processed event IDs to avoid duplicates
    
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
        
        # Parse timestamp
        detection_time = None
        if plate_info.get("timestamp"):
            detection_time = datetime.fromisoformat(plate_info["timestamp"].replace('Z', '+00:00'))
        elif event.get("start"):
            detection_time = datetime.fromisoformat(event["start"].replace('Z', '+00:00'))
        else:
            detection_time = datetime.utcnow()
        
        # Build enriched record
        enriched_plate = {
            "plate_number": plate_info.get("plate_number", ""),
            "confidence": 0.95,  # Default confidence since UniFi doesn't provide plate confidence
            "detection_timestamp": detection_time,
            "plate_detection_timestamp": detection_time,
            "processing_timestamp": datetime.utcnow(),
            "event_timestamp": datetime.fromisoformat(event["start"].replace('Z', '+00:00')) if event.get("start") else detection_time,
            
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
        
        return enriched_plate


async def main():
    """Main entry point for the backfill script."""
    parser = argparse.ArgumentParser(description="Backfill license plate detections to BigQuery")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back (default: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed without inserting data")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    backfiller = DetectionBackfiller()
    
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
