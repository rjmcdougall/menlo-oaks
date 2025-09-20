"""
UniFi Protect client for handling camera and detection data
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

try:
    from uiprotect import ProtectApiClient
    from uiprotect.data import Camera, Event
    from uiprotect.exceptions import ClientError, NotAuthorized
except ImportError:
    # Fallback for environments where uiprotect is not available
    ProtectApiClient = None
    Camera = None
    Event = None
    ClientError = Exception
    NotAuthorized = Exception

logger = logging.getLogger(__name__)


class UniFiProtectClient:
    """Client for interacting with UniFi Protect system."""
    
    def __init__(self, config):
        """
        Initialize UniFi Protect client.
        
        Args:
            config: Configuration object containing UniFi Protect settings
        """
        self.config = config
        self.client: Optional[ProtectApiClient] = None
        self._authenticated = False
        
        if ProtectApiClient is None:
            logger.warning("uiprotect not available - client will operate in webhook-only mode")
    
    async def connect(self) -> bool:
        """
        Connect to UniFi Protect and authenticate.
        
        Returns:
            True if connection successful, False otherwise
        """
        if ProtectApiClient is None:
            logger.warning("Cannot connect - uiprotect not available")
            return False
        
        try:
            self.client = ProtectApiClient(
                host=self.config.UNIFI_PROTECT_HOST,
                port=self.config.UNIFI_PROTECT_PORT,
                username=self.config.UNIFI_PROTECT_USERNAME,
                password=self.config.UNIFI_PROTECT_PASSWORD,
                verify_ssl=self.config.UNIFI_PROTECT_VERIFY_SSL
            )
            
            await self.client.authenticate()
            # Bootstrap/update the client to load current data
            await self.client.update()
            self._authenticated = True
            
            logger.info("Successfully connected to UniFi Protect")
            return True
            
        except NotAuthorized:
            logger.error("Authentication failed - check credentials")
            return False
        except ClientError as e:
            logger.error(f"Client error connecting to UniFi Protect: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to UniFi Protect: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from UniFi Protect."""
        if self.client:
            try:
                if hasattr(self.client, 'close'):
                    await self.client.close()
                elif hasattr(self.client, 'close_session'):
                    await self.client.close_session()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._authenticated = False
                logger.info("Disconnected from UniFi Protect")
    
    async def get_cameras(self) -> List[Dict[str, Any]]:
        """
        Get list of cameras from UniFi Protect.
        
        Returns:
            List of camera information dictionaries
        """
        if not self._authenticated:
            logger.error("Not authenticated to UniFi Protect")
            return []
        
        try:
            cameras = []
            bootstrap = await self.client.get_bootstrap()
            
            for camera in bootstrap.cameras.values():
                camera_info = {
                    "id": camera.id,
                    "name": camera.name,
                    "model": camera.model,
                    "mac": camera.mac,
                    "host": camera.host,
                    "is_connected": camera.is_connected,
                    "is_recording": camera.is_recording,
                    "location_name": getattr(camera, 'location_name', ''),
                    "smart_detect_settings": self._extract_smart_detect_settings(camera)
                }
                cameras.append(camera_info)
            
            logger.info(f"Retrieved {len(cameras)} cameras from UniFi Protect")
            return cameras
            
        except Exception as e:
            logger.error(f"Error getting cameras: {str(e)}")
            return []
    
    def _extract_smart_detect_settings(self, camera) -> Dict[str, Any]:
        """
        Extract smart detection settings from camera.
        
        Args:
            camera: Camera object from uiprotect
            
        Returns:
            Dictionary containing smart detection settings
        """
        try:
            if hasattr(camera, 'smart_detect_settings'):
                settings = camera.smart_detect_settings
                
                # Check object_types list for enabled detections
                object_types = getattr(settings, 'object_types', [])
                audio_types = getattr(settings, 'audio_types', [])
                
                # Convert enum types to strings for comparison
                enabled_objects = [str(obj_type).lower() for obj_type in object_types]
                enabled_audio = [str(audio_type).lower() for audio_type in audio_types]
                
                return {
                    "license_plate_enabled": any('license' in obj and 'plate' in obj for obj in enabled_objects),
                    "person_enabled": any('person' in obj for obj in enabled_objects),
                    "vehicle_enabled": any('vehicle' in obj for obj in enabled_objects),
                    "animal_enabled": any('animal' in obj for obj in enabled_objects),
                    "face_enabled": any('face' in obj for obj in enabled_objects),
                    "package_enabled": any('package' in obj for obj in enabled_objects),
                    "audio_detections": len(enabled_audio) > 0,
                    "raw_object_types": [str(obj) for obj in object_types],
                    "raw_audio_types": [str(audio) for audio in audio_types]
                }
            return {}
        except Exception as e:
            logger.warning(f"Error extracting smart detect settings: {str(e)}")
            return {}
    
    async def get_camera_by_id(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific camera by ID.
        
        Args:
            camera_id: UniFi Protect camera ID
            
        Returns:
            Camera information dictionary or None if not found
        """
        if not self._authenticated:
            logger.error("Not authenticated to UniFi Protect")
            return None
        
        try:
            bootstrap = await self.client.get_bootstrap()
            camera = bootstrap.cameras.get(camera_id)
            
            if not camera:
                logger.warning(f"Camera {camera_id} not found")
                return None
            
            return {
                "id": camera.id,
                "name": camera.name,
                "model": camera.model,
                "mac": camera.mac,
                "host": camera.host,
                "is_connected": camera.is_connected,
                "is_recording": camera.is_recording,
                "location_name": getattr(camera, 'location_name', ''),
                "smart_detect_settings": self._extract_smart_detect_settings(camera)
            }
            
        except Exception as e:
            logger.error(f"Error getting camera {camera_id}: {str(e)}")
            return None
    
    async def get_recent_events(self, hours: int = 24, event_types: List[str] = None) -> List[Dict[str, Any]]:
        """
        Get recent events from UniFi Protect.
        
        Args:
            hours: Number of hours to look back
            event_types: List of event types to filter by
            
        Returns:
            List of event dictionaries
        """
        if not self._authenticated:
            logger.error("Not authenticated to UniFi Protect")
            return []
        
        try:
            end_time = datetime.now()
            start_time = datetime.now() - timedelta(hours=hours)
            
            events = await self.client.get_events(
                start=start_time,
                end=end_time,
                event_types=event_types
            )
            
            event_list = []
            for event in events:
                event_info = self._extract_event_info(event)
                if event_info:
                    event_list.append(event_info)
            
            logger.info(f"Retrieved {len(event_list)} events from UniFi Protect")
            return event_list
            
        except Exception as e:
            logger.error(f"Error getting recent events: {str(e)}")
            return []
    
    def _extract_event_info(self, event) -> Optional[Dict[str, Any]]:
        """
        Extract event information into a standardized dictionary.
        
        Args:
            event: Event object from uiprotect
            
        Returns:
            Event information dictionary
        """
        try:
            event_info = {
                "id": event.id,
                "type": event.type,
                "start": event.start.isoformat() if event.start else None,
                "end": event.end.isoformat() if event.end else None,
                "score": getattr(event, 'score', 0),
                "camera_id": event.camera_id,
                "thumbnail_id": getattr(event, 'thumbnail_id', None),
                "smart_detect_types": [str(t) for t in getattr(event, 'smart_detect_types', [])],
                "smart_detect_data": {},
                "license_plates": []
            }
            
            # Extract license plate data from detected_thumbnails in metadata
            if hasattr(event, 'metadata') and event.metadata:
                metadata = event.metadata
                detected_thumbnails = getattr(metadata, 'detected_thumbnails', [])
                
                for thumbnail in detected_thumbnails:
                    # Check if this thumbnail has a vehicle with a license plate name
                    if (getattr(thumbnail, 'type', '') == 'vehicle' and 
                        hasattr(thumbnail, 'name') and thumbnail.name):
                        
                        plate_info = {
                            "plate_number": thumbnail.name,
                            "timestamp": thumbnail.clock_best_wall.isoformat() if hasattr(thumbnail, 'clock_best_wall') and thumbnail.clock_best_wall else None,
                            "cropped_id": getattr(thumbnail, 'cropped_id', ''),
                            "confidence": None  # Vehicle detection confidence, not plate confidence
                        }
                        
                        # Extract vehicle attributes if available
                        if hasattr(thumbnail, 'attributes') and thumbnail.attributes:
                            attributes = thumbnail.attributes
                            if hasattr(attributes, 'vehicle_type') and attributes.vehicle_type:
                                plate_info["vehicle_type"] = {
                                    "type": getattr(attributes.vehicle_type, 'val', ''),
                                    "confidence": getattr(attributes.vehicle_type, 'confidence', 0)
                                }
                            if hasattr(attributes, 'color') and attributes.color:
                                plate_info["vehicle_color"] = {
                                    "color": getattr(attributes.color, 'val', ''),
                                    "confidence": getattr(attributes.color, 'confidence', 0)
                                }
                        
                        event_info["license_plates"].append(plate_info)
            
            return event_info
            
        except Exception as e:
            logger.error(f"Error extracting event info: {str(e)}")
            return None
    
    async def get_snapshot_url(self, camera_id: str, event_id: str = None) -> Optional[str]:
        """
        Get snapshot URL for a camera or specific event.
        
        Args:
            camera_id: Camera ID
            event_id: Optional event ID for event-specific snapshot
            
        Returns:
            Snapshot URL or None if not available
        """
        if not self._authenticated:
            logger.error("Not authenticated to UniFi Protect")
            return None
        
        try:
            base_url = f"https://{self.config.UNIFI_PROTECT_HOST}:{self.config.UNIFI_PROTECT_PORT}"
            
            if event_id:
                # Event-specific snapshot
                return f"{base_url}/proxy/protect/api/events/{event_id}/thumbnail"
            else:
                # Live snapshot from camera
                return f"{base_url}/proxy/protect/api/cameras/{camera_id}/snapshot"
                
        except Exception as e:
            logger.error(f"Error getting snapshot URL: {str(e)}")
            return None
    
    def validate_webhook_data(self, webhook_data: Dict[str, Any]) -> bool:
        """
        Validate incoming webhook data structure.
        
        Args:
            webhook_data: Raw webhook data
            
        Returns:
            True if data structure is valid, False otherwise
        """
        try:
            # Check for required top-level fields
            required_fields = ["type"]
            for field in required_fields:
                if field not in webhook_data:
                    logger.warning(f"Missing required field: {field}")
                    return False
            
            # Check event type
            event_type = webhook_data.get("type", "")
            if not event_type:
                logger.warning("Empty event type")
                return False
            
            # For smart detection events, validate structure
            if event_type == "smart_detection":
                if "smart_detect_data" not in webhook_data:
                    logger.warning("Missing smart_detect_data for smart detection event")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating webhook data: {str(e)}")
            return False
    
    def enrich_webhook_data(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich webhook data with additional context if available.
        
        Args:
            webhook_data: Original webhook data
            
        Returns:
            Enriched webhook data
        """
        enriched = webhook_data.copy()
        
        try:
            # Add processing metadata
            enriched["processing_metadata"] = {
                "received_at": datetime.utcnow().isoformat(),
                "processed_by": "unifi_protect_client",
                "client_authenticated": self._authenticated
            }
            
            # Add camera context if we can get it
            camera_id = webhook_data.get("camera", {}).get("id")
            if camera_id and self._authenticated:
                # In a real implementation, you might want to cache camera info
                # to avoid API calls on every webhook
                enriched["camera_context_available"] = True
            
            return enriched
            
        except Exception as e:
            logger.error(f"Error enriching webhook data: {str(e)}")
            return webhook_data
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to UniFi Protect and return status information.
        
        Returns:
            Dictionary with connection test results
        """
        result = {
            "connected": False,
            "authenticated": False,
            "cameras_count": 0,
            "error": None,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            if await self.connect():
                result["connected"] = True
                result["authenticated"] = True
                
                cameras = await self.get_cameras()
                result["cameras_count"] = len(cameras)
                
                # Test getting recent events
                events = await self.get_recent_events(hours=1)
                result["recent_events_count"] = len(events)
                
                await self.disconnect()
                
            else:
                result["error"] = "Failed to connect and authenticate"
                
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Connection test failed: {str(e)}")
        
        return result


# Utility functions for webhook processing
def extract_license_plate_from_webhook(webhook_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract license plate information from UniFi Protect webhook data.
    Updated to use the new metadata.detected_thumbnails structure.
    This is a standalone function that can work without the full client.
    
    Args:
        webhook_data: Raw webhook data from UniFi Protect
        
    Returns:
        License plate data dictionary with multiple plates or None
    """
    try:
        # Check if this is a smart detection event
        if webhook_data.get("type") != "smart_detection":
            return None
        
        # Extract license plates from metadata.detected_thumbnails
        metadata = webhook_data.get("metadata", {})
        if not metadata:
            return None
            
        detected_thumbnails = metadata.get("detected_thumbnails", [])
        if not detected_thumbnails:
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
                    "detection_box": {},  # Not available in thumbnail data
                    "raw_detection": thumbnail
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
            # Return first plate for backward compatibility, but include all plates
            primary_plate = license_plates[0]
            primary_plate["all_plates"] = license_plates
            primary_plate["total_plates"] = len(license_plates)
            return primary_plate
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting license plate from webhook: {str(e)}")
        return None
