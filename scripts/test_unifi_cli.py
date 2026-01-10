#!/usr/bin/env python3
"""
CLI tool for testing UniFi Protect API connection and retrieving events
Usage: python test_unifi_cli.py [command] [options]
"""

import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from uiprotect import ProtectApiClient
    from uiprotect.exceptions import ClientError, NotAuthorized
    UIPROTECT_AVAILABLE = True
except ImportError:
    print("⚠️  uiprotect not installed. Install with: pip install uiprotect")
    UIPROTECT_AVAILABLE = False
    ProtectApiClient = None
    ClientError = Exception
    NotAuthorized = Exception

from config import Config


class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 60}{Colors.END}")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")


class UniFiProtectCLI:
    """CLI tool for testing UniFi Protect API"""
    
    def __init__(self):
        self.client: Optional[ProtectApiClient] = None
        self.config = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration from environment"""
        try:
            self.config = Config()
            if not self.config.is_unifi_protect_configured():
                print_warning("UniFi Protect not fully configured. Set environment variables:")
                print("  - UNIFI_PROTECT_HOST")
                print("  - UNIFI_PROTECT_USERNAME") 
                print("  - UNIFI_PROTECT_PASSWORD")
        except Exception as e:
            print_error(f"Failed to load configuration: {e}")
            sys.exit(1)
    
    async def connect(self) -> bool:
        """Connect to UniFi Protect"""
        if not UIPROTECT_AVAILABLE:
            print_error("uiprotect is not available")
            return False
        
        if not self.config.is_unifi_protect_configured():
            print_error("UniFi Protect configuration is incomplete")
            return False
        
        try:
            print_info(f"Connecting to {self.config.UNIFI_PROTECT_HOST}:{self.config.UNIFI_PROTECT_PORT}")
            
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
            print_success("Connected to UniFi Protect successfully!")
            return True
            
        except NotAuthorized:
            print_error("Authentication failed - check username/password")
            return False
        except ClientError as e:
            print_error(f"Client error: {e}")
            return False
        except Exception as e:
            print_error(f"Connection failed: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from UniFi Protect"""
        if self.client:
            try:
                if hasattr(self.client, 'close'):
                    await self.client.close()
                elif hasattr(self.client, 'close_session'):
                    await self.client.close_session()
            except Exception as e:
                print_warning(f"Error during disconnect: {e}")
            finally:
                print_info("Disconnected from UniFi Protect")
    
    async def test_connection(self):
        """Test connection to UniFi Protect"""
        print_header("Testing UniFi Protect Connection")
        
        if not await self.connect():
            return False
        
        try:
            # Get basic system info
            bootstrap = await self.client.get_bootstrap()
            nvr = bootstrap.nvr
            
            print_success("Connection test successful!")
            print(f"  NVR Name: {nvr.name}")
            print(f"  NVR Version: {nvr.version}")
            print(f"  Cameras: {len(bootstrap.cameras)}")
            print(f"  Events Available: {len(bootstrap.events)}")
            
            await self.disconnect()
            return True
            
        except Exception as e:
            print_error(f"Connection test failed: {e}")
            await self.disconnect()
            return False
    
    async def list_cameras(self):
        """List all cameras and their smart detection settings"""
        print_header("UniFi Protect Cameras")
        
        if not await self.connect():
            return
        
        try:
            bootstrap = await self.client.get_bootstrap()
            cameras = bootstrap.cameras.values()
            
            if not cameras:
                print_warning("No cameras found")
                return
            
            for i, camera in enumerate(cameras, 1):
                print(f"\n{Colors.BOLD}Camera {i}: {camera.name}{Colors.END}")
                print(f"  ID: {camera.id}")
                print(f"  Model: {camera.model}")
                print(f"  Connected: {'✓' if camera.is_connected else '✗'}")
                print(f"  Recording: {'✓' if camera.is_recording else '✗'}")
                
                # Smart detection settings
                if hasattr(camera, 'smart_detect_settings') and camera.smart_detect_settings:
                    settings = camera.smart_detect_settings
                    object_types = getattr(settings, 'object_types', [])
                    audio_types = getattr(settings, 'audio_types', [])
                    
                    # Convert to strings for checking
                    enabled_objects = [str(obj_type).lower() for obj_type in object_types]
                    
                    print(f"  Smart Detection:")
                    print(f"    License Plate: {'✓' if any('license' in obj and 'plate' in obj for obj in enabled_objects) else '✗'}")
                    print(f"    Person: {'✓' if any('person' in obj for obj in enabled_objects) else '✗'}")
                    print(f"    Vehicle: {'✓' if any('vehicle' in obj for obj in enabled_objects) else '✗'}")
                    print(f"    Animal: {'✓' if any('animal' in obj for obj in enabled_objects) else '✗'}")
                    print(f"    Face: {'✓' if any('face' in obj for obj in enabled_objects) else '✗'}")
                    if len(audio_types) > 0:
                        print(f"    Audio Detections: ✓ ({len(audio_types)} types)")
                else:
                    print(f"  Smart Detection: Not configured")
                
                if hasattr(camera, 'location_name') and camera.location_name:
                    print(f"  Location: {camera.location_name}")
            
            await self.disconnect()
            
        except Exception as e:
            print_error(f"Failed to list cameras: {e}")
            await self.disconnect()
    
    async def get_recent_events(self, hours: int = 24, event_filter: str = None):
        """Get recent events from UniFi Protect"""
        print_header(f"Recent Events (Last {hours} hours)")
        
        if not await self.connect():
            return
        
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            print_info(f"Searching for events from {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get events
            events = await self.client.get_events(
                start=start_time,
                end=end_time
            )
            
            if not events:
                print_warning("No events found in the specified time range")
                await self.disconnect()
                return
            
            # Filter events if requested
            filtered_events = []
            for event in events:
                if event_filter:
                    if event_filter.lower() in event.type.lower():
                        filtered_events.append(event)
                else:
                    filtered_events.append(event)
            
            if event_filter and not filtered_events:
                print_warning(f"No events found matching filter: {event_filter}")
                await self.disconnect()
                return
            
            events_to_show = filtered_events if event_filter else events
            print_success(f"Found {len(events_to_show)} events")
            
            # Display events
            for i, event in enumerate(events_to_show[:20], 1):  # Limit to 20 events
                self._display_event(event, i)
            
            if len(events_to_show) > 20:
                print_info(f"... and {len(events_to_show) - 20} more events")
            
            await self.disconnect()
            
        except Exception as e:
            print_error(f"Failed to get events: {e}")
            await self.disconnect()
    
    async def get_license_plate_events(self, hours: int = 24):
        """Get license plate detection events specifically"""
        print_header(f"License Plate Detection Events (Last {hours} hours)")
        
        if not await self.connect():
            return
        
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            print_info(f"Searching for license plate events from {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get all events
            events = await self.client.get_events(
                start=start_time,
                end=end_time
            )
            
            license_plate_events = []
            for event in events:
                # Look for license plates in detected_thumbnails metadata
                has_plates = False
                if hasattr(event, 'metadata') and event.metadata:
                    metadata = event.metadata
                    detected_thumbnails = getattr(metadata, 'detected_thumbnails', [])
                    
                    for thumbnail in detected_thumbnails:
                        if (getattr(thumbnail, 'type', '') == 'vehicle' and 
                            hasattr(thumbnail, 'name') and thumbnail.name):
                            has_plates = True
                            break
                
                # Also check legacy smart detection events
                if hasattr(event, 'smart_detect_events') and event.smart_detect_events:
                    for smart_event in event.smart_detect_events:
                        if getattr(smart_event, 'smart_detect_type', '') == 'license_plate':
                            has_plates = True
                            break
                
                if has_plates:
                    license_plate_events.append(event)
            
            if not license_plate_events:
                print_warning("No license plate detection events found")
                print_info("Make sure license plate detection is enabled on your cameras")
                await self.disconnect()
                return
            
            print_success(f"Found {len(license_plate_events)} events with license plates")
            
            # Display license plate events using the extraction method
            for i, event in enumerate(license_plate_events, 1):
                event_info = self._extract_event_info(event)
                if event_info and event_info.get('license_plates'):
                    print(f"\n{Colors.BOLD}{Colors.GREEN}License Plate Event {i}:{Colors.END}")
                    print(f"  Event ID: {event_info['id']}")
                    print(f"  Camera: {event_info['camera_id']}")
                    print(f"  Time: {event_info['start']}")
                    print(f"  Type: {event_info['type']}")
                    
                    print(f"  {Colors.BOLD}License Plates ({len(event_info['license_plates'])}){Colors.END}:")
                    for j, plate_info in enumerate(event_info['license_plates'], 1):
                        print(f"    {j}. {Colors.BOLD}{plate_info['plate_number']}{Colors.END}")
                        if plate_info.get('timestamp'):
                            print(f"       Detected at: {plate_info['timestamp']}")
                        if plate_info.get('vehicle_type'):
                            vtype = plate_info['vehicle_type']
                            print(f"       Vehicle: {vtype['type']} (confidence: {vtype['confidence']:.2f})")
                        if plate_info.get('vehicle_color'):
                            vcolor = plate_info['vehicle_color']
                            print(f"       Color: {vcolor['color']} (confidence: {vcolor['confidence']:.2f})")
                        if plate_info.get('cropped_id'):
                            print(f"       Crop ID: {plate_info['cropped_id']}")
            
            await self.disconnect()
            
        except Exception as e:
            print_error(f"Failed to get license plate events: {e}")
            await self.disconnect()
    
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
            print_error(f"Error extracting event info: {str(e)}")
            return None
    
    def _display_event(self, event, index: int):
        """Display a single event in formatted output"""
        print(f"\n{Colors.BOLD}Event {index}:{Colors.END}")
        print(f"  ID: {event.id}")
        print(f"  Type: {event.type}")
        print(f"  Start: {event.start.strftime('%Y-%m-%d %H:%M:%S') if event.start else 'Unknown'}")
        if event.end:
            print(f"  End: {event.end.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Camera ID: {getattr(event, 'camera_id', 'Unknown')}")
        
        if hasattr(event, 'score') and event.score:
            print(f"  Score: {event.score}")
        
        # Extract and show license plate data using new method
        event_info = self._extract_event_info(event)
        if event_info and event_info.get('license_plates'):
            print(f"  {Colors.BOLD}License Plates ({len(event_info['license_plates'])}){Colors.END}:")
            for j, plate_info in enumerate(event_info['license_plates'], 1):
                print(f"    {j}. {Colors.BOLD}{plate_info['plate_number']}{Colors.END}")
                if plate_info.get('timestamp'):
                    print(f"       Detected at: {plate_info['timestamp']}")
                if plate_info.get('vehicle_type'):
                    vtype = plate_info['vehicle_type']
                    print(f"       Vehicle: {vtype['type']} (confidence: {vtype['confidence']:.2f})")
                if plate_info.get('vehicle_color'):
                    vcolor = plate_info['vehicle_color']
                    print(f"       Color: {vcolor['color']} (confidence: {vcolor['confidence']:.2f})")
        
        # Show legacy smart detection info if available
        if hasattr(event, 'smart_detect_events') and event.smart_detect_events:
            print(f"  Smart Detections:")
            for smart_event in event.smart_detect_events:
                detect_type = getattr(smart_event, 'smart_detect_type', 'Unknown')
                print(f"    - {detect_type}")
                if detect_type == 'license_plate':
                    plate_number = getattr(smart_event, 'license_plate_number', 'Unknown')
                    confidence = getattr(smart_event, 'confidence', 0.0)
                    print(f"      Plate: {plate_number} (Confidence: {confidence:.2f})")
    
    async def export_events_json(self, hours: int = 24, output_file: str = "events.json"):
        """Export events to JSON file"""
        print_header(f"Exporting Events to {output_file}")
        
        if not await self.connect():
            return
        
        try:
            # Calculate time range
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            # Get events
            events = await self.client.get_events(
                start=start_time,
                end=end_time
            )
            
            # Convert events to JSON-serializable format
            events_data = []
            for event in events:
                event_data = {
                    "id": event.id,
                    "type": event.type,
                    "start": event.start.isoformat() if event.start else None,
                    "end": event.end.isoformat() if event.end else None,
                    "camera_id": getattr(event, 'camera_id', None),
                    "score": getattr(event, 'score', None),
                    "thumbnail_id": getattr(event, 'thumbnail_id', None)
                }
                
                # Add smart detection data
                if hasattr(event, 'smart_detect_events') and event.smart_detect_events:
                    smart_detections = []
                    for smart_event in event.smart_detect_events:
                        smart_data = {
                            "type": getattr(smart_event, 'smart_detect_type', None),
                            "confidence": getattr(smart_event, 'confidence', None)
                        }
                        
                        if smart_data["type"] == "license_plate":
                            smart_data["license_plate_number"] = getattr(smart_event, 'license_plate_number', None)
                            smart_data["region"] = getattr(smart_event, 'region', None)
                        
                        smart_detections.append(smart_data)
                    
                    event_data["smart_detections"] = smart_detections
                
                events_data.append(event_data)
            
            # Write to file
            with open(output_file, 'w') as f:
                json.dump({
                    "export_time": datetime.now().isoformat(),
                    "time_range": {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "hours": hours
                    },
                    "total_events": len(events_data),
                    "events": events_data
                }, f, indent=2)
            
            print_success(f"Exported {len(events_data)} events to {output_file}")
            await self.disconnect()
            
        except Exception as e:
            print_error(f"Failed to export events: {e}")
            await self.disconnect()


async def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="UniFi Protect API Testing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_unifi_cli.py test                    # Test connection
  python test_unifi_cli.py cameras                 # List cameras
  python test_unifi_cli.py events                  # Get recent events (24h)
  python test_unifi_cli.py events --hours 48       # Get events from last 48 hours  
  python test_unifi_cli.py events --filter smart   # Filter events by type
  python test_unifi_cli.py plates                  # Get license plate events
  python test_unifi_cli.py export --hours 168      # Export week of events to JSON

Environment Variables:
  UNIFI_PROTECT_HOST     - UniFi Protect hostname/IP
  UNIFI_PROTECT_USERNAME - Username
  UNIFI_PROTECT_PASSWORD - Password
  UNIFI_PROTECT_PORT     - Port (default: 443)
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Test connection command
    subparsers.add_parser('test', help='Test connection to UniFi Protect')
    
    # List cameras command
    subparsers.add_parser('cameras', help='List cameras and smart detection settings')
    
    # Get events command
    events_parser = subparsers.add_parser('events', help='Get recent events')
    events_parser.add_argument('--hours', type=int, default=24, help='Hours to look back (default: 24)')
    events_parser.add_argument('--filter', type=str, help='Filter events by type')
    
    # Get license plate events command
    plates_parser = subparsers.add_parser('plates', help='Get license plate detection events')
    plates_parser.add_argument('--hours', type=int, default=24, help='Hours to look back (default: 24)')
    
    # Export events command
    export_parser = subparsers.add_parser('export', help='Export events to JSON file')
    export_parser.add_argument('--hours', type=int, default=24, help='Hours to look back (default: 24)')
    export_parser.add_argument('--output', type=str, default='events.json', help='Output file (default: events.json)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = UniFiProtectCLI()
    
    if args.command == 'test':
        await cli.test_connection()
    elif args.command == 'cameras':
        await cli.list_cameras()
    elif args.command == 'events':
        await cli.get_recent_events(args.hours, args.filter)
    elif args.command == 'plates':
        await cli.get_license_plate_events(args.hours)
    elif args.command == 'export':
        await cli.export_events_json(args.hours, args.output)


if __name__ == "__main__":
    if not UIPROTECT_AVAILABLE:
        print_error("uiprotect is required. Install with:")
        print("pip install uiprotect")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_info("\nOperation cancelled by user")
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)
