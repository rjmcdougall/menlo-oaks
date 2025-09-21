#!/usr/bin/env python3
"""
Query script to retrieve license plate detection records with their associated image URLs.
This demonstrates how to access the thumbnail and cropped image URLs stored in BigQuery.
"""

import sys
from typing import List, Dict, Any, Optional
from bigquery_client import BigQueryClient
from config import Config

def main():
    """Main function to demonstrate image URL queries."""
    config = Config()
    bq_client = BigQueryClient(config)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "recent":
            # Show recent detections with images
            hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
            print(f"\n🔍 Recent detections with images (last {hours} hours):")
            results = get_recent_detections_with_images(bq_client, hours)
        elif sys.argv[1] == "plate":
            # Show detections for specific plate
            if len(sys.argv) < 3:
                print("Usage: python query_images.py plate <PLATE_NUMBER>")
                sys.exit(1)
            plate_number = sys.argv[2].upper()
            print(f"\n🔍 Detections for plate {plate_number} with images:")
            results = get_detections_by_plate_with_images(bq_client, plate_number)
        elif sys.argv[1] == "stats":
            # Show image storage statistics
            print("\n📊 Image storage statistics:")
            show_image_storage_stats(bq_client)
            return
        else:
            print_usage()
            return
    else:
        print_usage()
        return
    
    # Display results
    if results:
        for i, record in enumerate(results):
            print(f"\n📋 Record {i + 1}:")
            print(f"  Plate: {record['plate_number']}")
            print(f"  Camera: {record['camera_name']} ({record['camera_id']})")
            print(f"  Detection Time: {record['detection_timestamp']}")
            print(f"  Confidence: {record['confidence']:.2f}")
            
            # Show image URLs
            if record.get('thumbnail_public_url'):
                print(f"  🖼️  Full Scene Image: {record['thumbnail_public_url']}")
            
            if record.get('cropped_thumbnail_public_url'):
                print(f"  🔍 License Plate Crop: {record['cropped_thumbnail_public_url']}")
            
            if not record.get('thumbnail_public_url') and not record.get('cropped_thumbnail_public_url'):
                print(f"  ❌ No images stored for this detection")
                
            # Show GCS paths (useful for direct access)
            if record.get('thumbnail_gcs_path'):
                print(f"  📁 GCS Path: {record['thumbnail_gcs_path']}")
    else:
        print("  No records found with the specified criteria.")

def print_usage():
    """Print usage information."""
    print("Usage:")
    print("  python query_images.py recent [hours]     - Show recent detections with images")
    print("  python query_images.py plate <PLATE>      - Show detections for specific plate") 
    print("  python query_images.py stats              - Show image storage statistics")
    print("")
    print("Examples:")
    print("  python query_images.py recent 48")
    print("  python query_images.py plate ABC123")
    print("  python query_images.py stats")

def get_recent_detections_with_images(bq_client: BigQueryClient, hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get recent license plate detections that have stored images.
    
    Args:
        bq_client: BigQuery client instance
        hours: Number of hours to look back
        limit: Maximum number of results
        
    Returns:
        List of detection records with image information
    """
    query = f"""
    SELECT 
        record_id,
        plate_number,
        confidence,
        detection_timestamp,
        camera_id,
        camera_name,
        camera_location,
        event_id,
        thumbnail_public_url,
        thumbnail_gcs_path,
        thumbnail_filename,
        thumbnail_size_bytes,
        thumbnail_content_type,
        cropped_thumbnail_public_url,
        cropped_thumbnail_gcs_path,
        cropped_thumbnail_filename,
        cropped_thumbnail_size_bytes,
        vehicle_type,
        vehicle_color
    FROM `{bq_client.config.GCP_PROJECT_ID}.{bq_client.dataset_id}.{bq_client.table_id}`
    WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {hours} HOUR)
      AND (thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL)
    ORDER BY detection_timestamp DESC
    LIMIT {limit}
    """
    
    results = bq_client.client.query(query)
    return [dict(row) for row in results]

def get_detections_by_plate_with_images(bq_client: BigQueryClient, plate_number: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get detections for a specific license plate that have stored images.
    
    Args:
        bq_client: BigQuery client instance
        plate_number: License plate number to search for
        limit: Maximum number of results
        
    Returns:
        List of detection records with image information
    """
    from google.cloud import bigquery
    
    query = f"""
    SELECT 
        record_id,
        plate_number,
        confidence,
        detection_timestamp,
        camera_id,
        camera_name,
        camera_location,
        event_id,
        thumbnail_public_url,
        thumbnail_gcs_path,
        thumbnail_filename,
        thumbnail_size_bytes,
        thumbnail_content_type,
        cropped_thumbnail_public_url,
        cropped_thumbnail_gcs_path,
        cropped_thumbnail_filename,
        cropped_thumbnail_size_bytes,
        vehicle_type,
        vehicle_color
    FROM `{bq_client.config.GCP_PROJECT_ID}.{bq_client.dataset_id}.{bq_client.table_id}`
    WHERE plate_number = @plate_number
      AND (thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL)
    ORDER BY detection_timestamp DESC
    LIMIT {limit}
    """
    
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("plate_number", "STRING", plate_number.upper())
        ]
    )
    
    results = bq_client.client.query(query, job_config=job_config)
    return [dict(row) for row in results]

def show_image_storage_stats(bq_client: BigQueryClient):
    """
    Show statistics about image storage.
    
    Args:
        bq_client: BigQuery client instance
    """
    query = f"""
    SELECT 
        COUNT(*) as total_detections,
        COUNT(thumbnail_public_url) as detections_with_full_images,
        COUNT(cropped_thumbnail_public_url) as detections_with_crop_images,
        COUNT(CASE WHEN thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL THEN 1 END) as detections_with_any_image,
        ROUND(AVG(thumbnail_size_bytes) / 1024, 2) as avg_image_size_kb,
        ROUND(SUM(thumbnail_size_bytes) / 1024 / 1024, 2) as total_storage_mb,
        MIN(detection_timestamp) as earliest_detection,
        MAX(detection_timestamp) as latest_detection
    FROM `{bq_client.config.GCP_PROJECT_ID}.{bq_client.dataset_id}.{bq_client.table_id}`
    """
    
    results = bq_client.client.query(query)
    stats = list(results)[0]
    
    print(f"  📊 Total Detections: {stats['total_detections']}")
    print(f"  🖼️  With Full Scene Images: {stats['detections_with_full_images']}")
    print(f"  🔍 With License Plate Crops: {stats['detections_with_crop_images']}")
    print(f"  📷 With Any Images: {stats['detections_with_any_image']}")
    
    if stats['total_detections'] > 0:
        image_percentage = (stats['detections_with_any_image'] / stats['total_detections']) * 100
        print(f"  📈 Image Coverage: {image_percentage:.1f}%")
    
    if stats['avg_image_size_kb']:
        print(f"  📏 Average Image Size: {stats['avg_image_size_kb']} KB")
    
    if stats['total_storage_mb']:
        print(f"  💾 Total Storage Used: {stats['total_storage_mb']} MB")
    
    if stats['earliest_detection']:
        print(f"  📅 Detection Range: {stats['earliest_detection']} to {stats['latest_detection']}")

def generate_direct_gcs_url(gcs_path: str, bucket_name: str) -> str:
    """
    Generate a direct Google Cloud Storage URL from a GCS path.
    
    Args:
        gcs_path: GCS path like "gs://bucket-name/path/to/file.jpg"
        bucket_name: GCS bucket name
        
    Returns:
        Direct HTTP URL to the GCS object
    """
    if not gcs_path or not gcs_path.startswith("gs://"):
        return ""
    
    # Remove the gs:// prefix and bucket name to get the object path
    path_parts = gcs_path.replace("gs://", "").split("/", 1)
    if len(path_parts) > 1:
        object_path = path_parts[1]
        return f"https://storage.googleapis.com/{bucket_name}/{object_path}"
    
    return ""

if __name__ == "__main__":
    main()
