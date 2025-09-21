#!/usr/bin/env python3
"""
Script to create and populate a camera lookup table in BigQuery.

This script creates a normalized camera/device lookup table that can be joined
with the license plate detections table for better data organization.
"""

import os
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import requests
from google.cloud import bigquery
from config import Config

class CameraLookupManager:
    """Manages the camera lookup table in BigQuery."""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = bigquery.Client(project=config.GCP_PROJECT_ID)
        self.dataset_id = config.BIGQUERY_DATASET
        self.lookup_table_id = "camera_lookup"  # New lookup table
        self.google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        
    def create_camera_lookup_table(self, recreate: bool = False) -> bool:
        """Create the camera lookup table with proper schema.
        
        Args:
            recreate: If True, delete and recreate the table if it already exists
        """
        try:
            table_ref = self.client.dataset(self.dataset_id).table(self.lookup_table_id)
            
            # Check if table already exists
            table_exists = False
            try:
                _ = self.client.get_table(table_ref)
                table_exists = True
            except Exception:
                # Table doesn't exist
                pass
            
            if table_exists:
                if recreate:
                    # Delete the existing table
                    self.client.delete_table(table_ref)
                    print(f"🗑️ Deleted existing table {self.lookup_table_id}")
                else:
                    print(f"📋 Table {self.lookup_table_id} already exists")
                    return True
            
            # Define schema for camera lookup table
            schema = [
                bigquery.SchemaField("device_id", "STRING", mode="REQUIRED", description="UniFi Protect device ID (primary key)"),
                bigquery.SchemaField("camera_id", "STRING", mode="NULLABLE", description="UniFi Protect camera ID (may be same as device_id)"),
                bigquery.SchemaField("camera_name", "STRING", mode="REQUIRED", description="Human-readable camera name"),
                bigquery.SchemaField("camera_location", "STRING", mode="NULLABLE", description="Camera location description"),
                bigquery.SchemaField("latitude", "FLOAT", mode="NULLABLE", description="Camera latitude coordinate"),
                bigquery.SchemaField("longitude", "FLOAT", mode="NULLABLE", description="Camera longitude coordinate"),
                bigquery.SchemaField("camera_model", "STRING", mode="NULLABLE", description="Camera model/type"),
                bigquery.SchemaField("installation_date", "DATE", mode="NULLABLE", description="When the camera was installed"),
                bigquery.SchemaField("is_active", "BOOLEAN", mode="REQUIRED", description="Whether the camera is currently active"),
                bigquery.SchemaField("notes", "STRING", mode="NULLABLE", description="Additional notes about the camera"),
                bigquery.SchemaField("created_at", "DATETIME", mode="REQUIRED", description="When this record was created"),
                bigquery.SchemaField("updated_at", "DATETIME", mode="REQUIRED", description="When this record was last updated"),
            ]
            
            # Create table
            table = bigquery.Table(table_ref, schema=schema)
            table.description = "Camera/device lookup table for UniFi Protect license plate detection system"
            
            self.client.create_table(table)
            print(f"✅ Created camera lookup table: {self.dataset_id}.{self.lookup_table_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error creating camera lookup table: {str(e)}")
            return False

    def _geocode_with_google(self, address: str) -> Optional[Tuple[float, float]]:
        if not self.google_maps_api_key:
            return None
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": self.google_maps_api_key}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("status") != "OK" or not data.get("results"):
            return None
        loc = data["results"][0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])

    def _geocode_with_nominatim(self, address: str) -> Optional[Tuple[float, float]]:
        # Respect Nominatim usage policy with a UA and minimal rate limiting
        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "protectmenlo-camera-lookup/1.0 (contact: admin@example.com)"}
        params = {"q": address, "format": "json", "limit": 1}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results:
            return None
        first = results[0]
        return float(first["lat"]), float(first["lon"])

    def geocode_address(self, address: str, retries: int = 3, backoff: float = 0.5) -> Optional[Tuple[float, float]]:
        """Geocode an address to (lat, lon). Uses Google if API key present, else Nominatim."""
        last_err: Optional[str] = None
        for i in range(retries):
            try:
                # Prefer Google if available
                coords = self._geocode_with_google(address)
                if coords:
                    return coords
                # Fallback to Nominatim
                coords = self._geocode_with_nominatim(address)
                if coords:
                    return coords
                last_err = "No results from geocoders"
            except Exception as e:
                last_err = str(e)
            time.sleep(backoff * (2 ** i))
        print(f"⚠️ Geocoding failed for '{address}': {last_err}")
        return None
    
    def populate_sample_camera_data(self) -> bool:
        """Populate the lookup table with sample camera data.
        Addresses are geocoded to lat/lon prior to insert.
        """
        try:
            # Sample camera data specifying addresses instead of lat/lon
            sample_cameras_source = [
                {
                    "device_id": "942A6FD0AD1A",
                    "camera_id": "942A6FD0AD1A",
                    "camera_name": "AI LPR",
                    "camera_location": "825 Berkeley",
                    "address": "825 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "28704E169362",
                    "camera_id": "28704E169362",
                    "camera_name": "AI Pro",
                    "camera_location": "825 Berkeley",
                    "address": "825 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "1C6A1B816A71",
                    "camera_id": "1C6A1B816A71",
                    "camera_name": "AI Pro",
                    "camera_location": "500 Berkeley",
                    "address": "500 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BD20",
                    "camera_id": "942A6FD0BD20",
                    "camera_name": "AI LPR",
                    "camera_location": "500 Berkeley",
                    "address": "500 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BC20",
                    "camera_id": "942A6FD0BC20",
                    "camera_name": "AI LPR",
                    "camera_location": "650 Berkeley",
                    "address": "650 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "28704E1B79B3",
                    "camera_id": "28704E1B79B3",
                    "camera_name": "AI Pro",
                    "camera_location": "680 Berkeley",
                    "address": "680 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0B1CD",
                    "camera_id": "942A6FD0B1CD",
                    "camera_name": "AI LPR",
                    "camera_location": "680 Berkeley",
                    "address": "680 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "28704E1F031A",
                    "camera_id": "28704E1F031A",
                    "camera_name": "AI Pro",
                    "camera_location": "750 Berkeley",
                    "address": "750 Berkeley Ave, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "28704E1F0AEE",
                    "camera_id": "28704E1F0AEE",
                    "camera_name": "AI Pro",
                    "camera_location": "301 Menlo Oaks",
                    "address": "301 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BEDC",
                    "camera_id": "942A6FD0BEDC",
                    "camera_name": "AI LPR",
                    "camera_location": "301 Menlo Oaks",
                    "address": "301 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "1C6A1B815D69",
                    "camera_id": "1C6A1B815D69",
                    "camera_name": "AI Pro",
                    "camera_location": "510 Menlo Oaks",
                    "address": "510 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BCCD",
                    "camera_id": "942A6FD0BCCD",
                    "camera_name": "AI LPR",
                    "camera_location": "510 Menlo Oaks",
                    "address": "510 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0AE44",
                    "camera_id": "942A6FD0AE44",
                    "camera_name": "AI LPR",
                    "camera_location": "591 Menlo Oaks",
                    "address": "591 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0AE38",
                    "camera_id": "942A6FD0AE38",
                    "camera_name": "AI LPR",
                    "camera_location": "941 Menlo Oaks",
                    "address": "941 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "1C6A1B816A35",
                    "camera_id": "1C6A1B816A35",
                    "camera_name": "AI Pro",
                    "camera_location": "420 Menlo Oaks",
                    "address": "420 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BFB9",
                    "camera_id": "942A6FD0BFB9",
                    "camera_name": "AI LPR",
                    "camera_location": "420 Menlo Oaks",
                    "address": "420 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BBCC",
                    "camera_id": "942A6FD0BBCC",
                    "camera_name": "AI LPR",
                    "camera_location": "570 Menlo Oaks",
                    "address": "570 Menlo Oaks, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "28704E1B7F67",
                    "camera_id": "28704E1B7F67",
                    "camera_name": "AI Pro",
                    "camera_location": "151 Arlington",
                    "address": "151 Arlington Dr, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI Pro",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
                {
                    "device_id": "942A6FD0BC57",
                    "camera_id": "942A6FD0BC57",
                    "camera_name": "AI LPR",
                    "camera_location": "151 Arlington",
                    "address": "151 Arlington Dr, Menlo Park, CA 94025",
                    "camera_model": "UniFi Protect AI LPR",
                    "installation_date": "2024-01-15",
                    "is_active": True,
                    "notes": ""
                },
            ]

            # Build insert payload with geocoded coordinates
            current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            rows_to_insert: List[Dict[str, Any]] = []

            for cam in sample_cameras_source:
                address = cam.get("address")
                lat, lon = None, None
                if address:
                    coords = self.geocode_address(address)
                    if coords:
                        lat, lon = coords
                row = {
                    "device_id": cam["device_id"],
                    "camera_id": cam.get("camera_id"),
                    "camera_name": cam.get("camera_name", "Unknown Camera"),
                    "camera_location": cam.get("camera_location"),
                    "latitude": lat,
                    "longitude": lon,
                    "camera_model": cam.get("camera_model"),
                    "installation_date": cam.get("installation_date"),
                    "is_active": cam.get("is_active", True),
                    "notes": cam.get("notes"),
                    "created_at": current_time,
                    "updated_at": current_time,
                }
                rows_to_insert.append(row)
                where = f" @ ({lat}, {lon})" if (lat is not None and lon is not None) else " (no coords)"
                print(f"   📝 Prepared {row['camera_name']} at {cam.get('address', 'N/A')}{where}")
            
            # Insert data
            table_ref = self.client.dataset(self.dataset_id).table(self.lookup_table_id)
            table = self.client.get_table(table_ref)
            errors = self.client.insert_rows_json(table, rows_to_insert)
            
            if errors:
                # Log detailed BigQuery errors
                print("❌ Error inserting camera data:")
                for err in errors:
                    err_index = err.get('index')
                    print(f"   - Row index {err_index}:")
                    for e in err.get('errors', []):
                        print(f"     • reason={e.get('reason')}, message={e.get('message')}, location={e.get('location')}")
                return False
            else:
                print(f"✅ Successfully inserted {len(rows_to_insert)} camera records")
                return True
                
        except Exception as e:
            print(f"❌ Error populating camera data: {str(e)}")
            return False
    
    def create_sample_join_view(self) -> bool:
        """Create a sample view that joins detections with camera lookup."""
        try:
            view_id = "detections_with_camera_info"
            view_ref = self.client.dataset(self.dataset_id).table(view_id)
            
            # SQL for the joined view
            view_sql = f"""
            SELECT 
                d.record_id,
                d.plate_number,
                d.confidence,
                d.detection_timestamp,
                d.vehicle_type,
                d.vehicle_color,
                d.event_id,
                d.thumbnail_public_url,
                d.cropped_thumbnail_public_url,
                
                -- Camera information from lookup table
                c.camera_name,
                c.camera_location,
                c.latitude,
                c.longitude,
                c.camera_model,
                c.is_active as camera_active,
                c.notes as camera_notes
                
            FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.config.BIGQUERY_TABLE}` d
            LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}` c
                ON d.device_id = c.device_id
            """
            
            # Create the view
            view = bigquery.Table(view_ref)
            view.view_query = view_sql
            view.description = "License plate detections joined with camera location and metadata"
            
            try:
                # Try to create the view
                self.client.create_table(view)
                print(f"✅ Created view: {view_id}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    # Update existing view
                    self.client.update_table(view, ["view_query", "description"])
                    print(f"✅ Updated existing view: {view_id}")
                else:
                    raise e
            
            return True
            
        except Exception as e:
            print(f"❌ Error creating join view: {str(e)}")
            return False
    
    def show_sample_queries(self):
        """Show sample SQL queries for using the lookup table."""
        print(f"\n💡 Sample queries for using the camera lookup table:")
        print(f"\n1. View all cameras:")
        print(f"   SELECT device_id, camera_name, camera_location, latitude, longitude")
        print(f"   FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}`")
        print(f"   WHERE is_active = true;")
        
        print(f"\n2. Join detections with camera info:")
        print(f"   SELECT d.plate_number, d.detection_timestamp, c.camera_name, c.camera_location")
        print(f"   FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.config.BIGQUERY_TABLE}` d")
        print(f"   LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}` c")
        print(f"   ON d.device_id = c.device_id")
        print(f"   ORDER BY d.detection_timestamp DESC")
        print(f"   LIMIT 10;")
        
        print(f"\n3. Use the pre-built view:")
        print(f"   SELECT plate_number, detection_timestamp, camera_name, camera_location, latitude, longitude")
        print(f"   FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.detections_with_camera_info`")
        print(f"   WHERE camera_active = true")
        print(f"   ORDER BY detection_timestamp DESC")
        print(f"   LIMIT 10;")
        
        print(f"\n4. Count detections by camera:")
        print(f"   SELECT c.camera_name, c.camera_location, COUNT(*) as detection_count")
        print(f"   FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.config.BIGQUERY_TABLE}` d")
        print(f"   LEFT JOIN `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}` c")
        print(f"   ON d.device_id = c.device_id")
        print(f"   GROUP BY c.camera_name, c.camera_location")
        print(f"   ORDER BY detection_count DESC;")

def main():
    """Main function to create and populate camera lookup table."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Create and populate a camera lookup table in BigQuery"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the lookup table if it already exists"
    )
    args = parser.parse_args()
    
    print("🚀 Creating camera lookup table for license plate detection system...")
    
    if args.recreate:
        print("⚠️  Recreate mode: Will delete and recreate existing table")
    
    # Initialize
    config = Config()
    manager = CameraLookupManager(config)
    
    print(f"📋 Target dataset: {config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}")
    print(f"📋 Main table: {config.BIGQUERY_TABLE}")
    print(f"📋 Lookup table: camera_lookup")
    
    # Create lookup table
    if not manager.create_camera_lookup_table(recreate=args.recreate):
        print("❌ Failed to create camera lookup table")
        return False
    
    # Populate with sample data (addresses will be geocoded)
    if not manager.populate_sample_camera_data():
        print("❌ Failed to populate camera lookup table")
        return False
    
    # Create joined view
    if not manager.create_sample_join_view():
        print("❌ Failed to create joined view")
        return False
    
    # Show sample queries
    manager.show_sample_queries()
    
    print(f"\n🎉 Camera lookup table setup complete!")
    print(f"   ✅ Created table: camera_lookup")
    print(f"   ✅ Populated with sample camera data (geocoded)")  
    print(f"   ✅ Created joined view: detections_with_camera_info")
    print(f"   📊 You can now join detections with camera metadata")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
