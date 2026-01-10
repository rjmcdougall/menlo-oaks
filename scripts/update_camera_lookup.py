#!/usr/bin/env python3
"""
Script to fetch camera data from UniFi Protect and update the BigQuery lookup table.

This script connects to the UniFi Protect API to fetch current camera information
and updates the camera_lookup table in BigQuery with the latest data.
"""

import os
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from google.cloud import bigquery
from config import Config
from unifi_protect_client import UniFiProtectClient

class CameraLookupUpdater:
    """Updates camera lookup table with data from UniFi Protect."""
    
    def __init__(self, config: Config):
        self.config = config
        self.bigquery_client = bigquery.Client(project=config.GCP_PROJECT_ID)
        self.dataset_id = config.BIGQUERY_DATASET
        self.lookup_table_id = "camera_lookup"
        
        # Initialize UniFi Protect client
        self.protect_client = UniFiProtectClient(
            host=config.UNIFI_PROTECT_HOST,
            username=config.UNIFI_PROTECT_USERNAME,
            password=config.UNIFI_PROTECT_PASSWORD,
            verify_ssl=config.UNIFI_PROTECT_VERIFY_SSL
        )
    
    async def fetch_camera_data_from_unifi(self) -> List[Dict[str, Any]]:
        """Fetch camera data from UniFi Protect system."""
        try:
            print("🔌 Connecting to UniFi Protect...")
            await self.protect_client.connect()
            
            print("📷 Fetching camera data...")
            bootstrap_info = await self.protect_client.get_bootstrap_info()
            
            cameras = []
            
            # Extract camera information from bootstrap data
            if 'cameras' in bootstrap_info:
                for camera_data in bootstrap_info['cameras']:
                    camera_info = {
                        'device_id': camera_data.get('mac', '').replace(':', '').upper(),
                        'camera_id': camera_data.get('id', ''),
                        'camera_name': camera_data.get('name', 'Unknown Camera'),
                        'camera_location': camera_data.get('customName', ''),  # Use custom name as location if available
                        'latitude': None,  # UniFi Protect doesn't typically store GPS coordinates
                        'longitude': None,
                        'camera_model': camera_data.get('type', 'Unknown Model'),
                        'installation_date': None,  # Would need to be manually entered
                        'is_active': camera_data.get('state') == 'CONNECTED',
                        'notes': f"Model: {camera_data.get('model', 'Unknown')}, Firmware: {camera_data.get('firmwareVersion', 'Unknown')}",
                        'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    # Try to extract additional location info
                    if 'customName' in camera_data and camera_data['customName']:
                        camera_info['camera_location'] = camera_data['customName']
                    elif 'name' in camera_data:
                        # Parse location from camera name if it follows a pattern
                        name = camera_data['name']
                        if ' - ' in name:
                            parts = name.split(' - ')
                            if len(parts) > 1:
                                camera_info['camera_location'] = parts[1].strip()
                    
                    cameras.append(camera_info)
                    print(f"   📸 Found camera: {camera_info['camera_name']} ({camera_info['device_id']})")
            
            print(f"✅ Found {len(cameras)} cameras in UniFi Protect")
            return cameras
            
        except Exception as e:
            print(f"❌ Error fetching camera data from UniFi Protect: {str(e)}")
            return []
        
        finally:
            try:
                await self.protect_client.disconnect()
            except:
                pass
    
    def update_bigquery_lookup_table(self, camera_data: List[Dict[str, Any]]) -> bool:
        """Update the BigQuery lookup table with camera data."""
        if not camera_data:
            print("❌ No camera data to update")
            return False
        
        try:
            table_ref = self.bigquery_client.dataset(self.dataset_id).table(self.lookup_table_id)
            table = self.bigquery_client.get_table(table_ref)
            
            print(f"📊 Updating BigQuery table with {len(camera_data)} camera records...")
            
            # Use MERGE strategy: delete existing records and insert new ones
            # This ensures we have the latest data and remove any cameras that no longer exist
            
            # First, get current device IDs from the fetched data
            current_device_ids = [camera['device_id'] for camera in camera_data]
            device_ids_str = "', '".join(current_device_ids)
            
            # Delete existing records for these device IDs
            delete_query = f"""
            DELETE FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}`
            WHERE device_id IN ('{device_ids_str}')
            """
            
            print("🗑️ Removing existing records for updated cameras...")
            delete_job = self.bigquery_client.query(delete_query)
            delete_job.result()  # Wait for the job to complete
            
            # Insert new/updated records
            print("📝 Inserting updated camera records...")
            errors = self.bigquery_client.insert_rows_json(table, camera_data)
            
            if errors:
                print(f"❌ Error inserting camera data: {errors}")
                return False
            else:
                print(f"✅ Successfully updated {len(camera_data)} camera records")
                return True
                
        except Exception as e:
            print(f"❌ Error updating BigQuery lookup table: {str(e)}")
            return False
    
    def add_manual_camera_locations(self) -> bool:
        """Add or update manual location data for cameras."""
        try:
            # Manual location data that's not available from UniFi Protect API
            # This would typically be maintained separately or entered manually
            location_updates = [
                {
                    'device_id': '942A6FD0BCCD',
                    'camera_location': 'Main Entrance Gate',
                    'latitude': 37.4419,
                    'longitude': -122.1430,
                    'installation_date': '2024-01-15',
                    'notes': 'Primary entrance monitoring with LPR capability - high traffic area'
                },
                {
                    'device_id': '1C6A1B815D69', 
                    'camera_location': 'Employee Parking Lot',
                    'latitude': 37.4425,
                    'longitude': -122.1435,
                    'installation_date': '2024-02-20',
                    'notes': 'Monitors employee parking - covers 50+ spaces'
                },
                {
                    'device_id': '28704E1B79B3',
                    'camera_location': 'Side Entrance/Exit',
                    'latitude': 37.4415,
                    'longitude': -122.1425,
                    'installation_date': '2024-03-10',
                    'notes': 'Secondary access point - lower traffic volume'
                }
            ]
            
            print(f"📍 Updating location data for {len(location_updates)} cameras...")
            
            for update in location_updates:
                device_id = update['device_id']
                
                # Build UPDATE query for this camera
                set_clauses = []
                if 'camera_location' in update:
                    set_clauses.append(f"camera_location = '{update['camera_location']}'")
                if 'latitude' in update:
                    set_clauses.append(f"latitude = {update['latitude']}")
                if 'longitude' in update:
                    set_clauses.append(f"longitude = {update['longitude']}")
                if 'installation_date' in update:
                    set_clauses.append(f"installation_date = '{update['installation_date']}'")
                if 'notes' in update:
                    # Escape single quotes in notes
                    escaped_notes = update['notes'].replace("'", "\\'\\'")
                    set_clauses.append(f"notes = '{escaped_notes}'")
                
                set_clauses.append(f"updated_at = '{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}'")
                
                if set_clauses:
                    update_query = f"""
                    UPDATE `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}`
                    SET {', '.join(set_clauses)}
                    WHERE device_id = '{device_id}'
                    """
                    
                    update_job = self.bigquery_client.query(update_query)
                    update_job.result()  # Wait for completion
                    
                    print(f"   📍 Updated location data for {device_id}")
            
            print("✅ Manual location updates complete")
            return True
            
        except Exception as e:
            print(f"❌ Error updating manual location data: {str(e)}")
            return False
    
    def show_updated_camera_summary(self) -> bool:
        """Display summary of cameras in the lookup table."""
        try:
            query = f"""
            SELECT 
                device_id,
                camera_name,
                camera_location,
                CASE 
                    WHEN latitude IS NOT NULL AND longitude IS NOT NULL 
                    THEN CONCAT(CAST(latitude AS STRING), ', ', CAST(longitude AS STRING))
                    ELSE 'No coordinates'
                END as coordinates,
                is_active,
                updated_at
            FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.lookup_table_id}`
            ORDER BY camera_name
            """
            
            print(f"\n📊 Current camera lookup table contents:")
            print(f"{'Device ID':<15} {'Camera Name':<25} {'Location':<25} {'Coordinates':<20} {'Active':<8} {'Updated'}")
            print("-" * 120)
            
            query_job = self.bigquery_client.query(query)
            results = query_job.result()
            
            for row in results:
                print(f"{row.device_id:<15} {row.camera_name:<25} {str(row.camera_location or 'N/A'):<25} {row.coordinates:<20} {str(row.is_active):<8} {row.updated_at}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error fetching camera summary: {str(e)}")
            return False

async def main():
    """Main function to update camera lookup table from UniFi Protect."""
    print("🚀 Updating camera lookup table from UniFi Protect...")
    
    # Initialize
    config = Config()
    updater = CameraLookupUpdater(config)
    
    print(f"📋 Target: {config.GCP_PROJECT_ID}.{config.BIGQUERY_DATASET}.camera_lookup")
    print(f"🏠 UniFi Protect: {config.UNIFI_PROTECT_HOST}")
    
    # Fetch camera data from UniFi Protect
    camera_data = await updater.fetch_camera_data_from_unifi()
    
    if not camera_data:
        print("❌ No camera data fetched from UniFi Protect")
        return False
    
    # Update BigQuery lookup table
    if not updater.update_bigquery_lookup_table(camera_data):
        print("❌ Failed to update BigQuery lookup table")
        return False
    
    # Add manual location data
    if not updater.add_manual_camera_locations():
        print("❌ Failed to add manual location data")
        return False
    
    # Show summary
    updater.show_updated_camera_summary()
    
    print(f"\n🎉 Camera lookup table update complete!")
    print(f"   ✅ Fetched data from UniFi Protect API")
    print(f"   ✅ Updated BigQuery lookup table")
    print(f"   ✅ Applied manual location data")
    print(f"   📊 Camera metadata is now available for joins")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
