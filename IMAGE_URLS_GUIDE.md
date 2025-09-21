# License Plate Detection Image URLs Guide

Your UniFi Protect license plate detection system already stores image URLs in the BigQuery database! Here's how to access them.

## Database Schema for Image URLs

The BigQuery `license_plate_detections` table includes the following image-related fields:

### Full Scene Images (Alarm Thumbnails)
- `thumbnail_public_url` - Direct HTTP URL to the full scene image in Google Cloud Storage
- `thumbnail_gcs_path` - GCS path (gs://bucket-name/path/to/file.jpg)
- `thumbnail_filename` - Original filename of the stored image
- `thumbnail_size_bytes` - Size of the image file in bytes
- `thumbnail_content_type` - MIME type (e.g., "image/jpeg")
- `thumbnail_upload_timestamp` - When the image was uploaded to GCS

### Cropped License Plate Images
- `cropped_thumbnail_public_url` - Direct HTTP URL to the cropped license plate image
- `cropped_thumbnail_gcs_path` - GCS path to the cropped image
- `cropped_thumbnail_filename` - Filename of the cropped image
- `cropped_thumbnail_size_bytes` - Size of the cropped image in bytes

## Query Examples

### 1. Recent Detections with Images

```sql
SELECT 
    plate_number,
    detection_timestamp,
    camera_name,
    thumbnail_public_url,
    cropped_thumbnail_public_url,
    thumbnail_size_bytes
FROM `menlo-oaks.license_plate_data.license_plate_detections`
WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR)
  AND (thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL)
ORDER BY detection_timestamp DESC
LIMIT 50;
```

### 2. Detections for Specific License Plate

```sql
SELECT 
    record_id,
    plate_number,
    detection_timestamp,
    camera_name,
    thumbnail_public_url,
    cropped_thumbnail_public_url,
    confidence
FROM `menlo-oaks.license_plate_data.license_plate_detections`
WHERE plate_number = 'ABC123'
  AND (thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL)
ORDER BY detection_timestamp DESC;
```

### 3. Image Storage Statistics

```sql
SELECT 
    COUNT(*) as total_detections,
    COUNT(thumbnail_public_url) as detections_with_full_images,
    COUNT(cropped_thumbnail_public_url) as detections_with_crop_images,
    COUNT(CASE WHEN thumbnail_public_url IS NOT NULL OR cropped_thumbnail_public_url IS NOT NULL THEN 1 END) as detections_with_any_image,
    ROUND(AVG(thumbnail_size_bytes) / 1024, 2) as avg_image_size_kb,
    ROUND(SUM(thumbnail_size_bytes) / 1024 / 1024, 2) as total_storage_mb
FROM `menlo-oaks.license_plate_data.license_plate_detections`;
```

## Image URL Types

### Public URLs (Recommended)
The `thumbnail_public_url` and `cropped_thumbnail_public_url` fields contain direct HTTP URLs that can be accessed from any web browser or application:

```
https://storage.googleapis.com/menlo-oaks-thumbnails/license_plates/2025/09/21/ABC123_20250921_050925_alarm_thumbnail.jpg
```

### GCS Paths
The GCS path fields contain the full Google Cloud Storage path:

```
gs://menlo-oaks-thumbnails/license_plates/2025/09/21/ABC123_20250921_050925_alarm_thumbnail.jpg
```

## How Images are Stored

When a license plate detection occurs, the system:

1. **Extracts the base64-encoded thumbnail** from the UniFi Protect webhook (`alarm.thumbnail` field)
2. **Decodes the image** and determines the content type (usually JPEG)
3. **Uploads to Google Cloud Storage** with a structured filename:
   - Format: `{plate_number}_{timestamp}_{image_type}.{extension}`
   - Example: `ABC123_20250921_050925_alarm_thumbnail.jpg`
4. **Stores the public URL** in BigQuery for easy access

## Accessing Images Programmatically

### Using the Query Script
```bash
# Show recent detections with images
python query_images.py recent 24

# Show detections for specific plate
python query_images.py plate ABC123

# Show storage statistics  
python query_images.py stats
```

### Using Python
```python
from bigquery_client import BigQueryClient
from config import Config

config = Config()
bq_client = BigQueryClient(config)

# Get recent detections with images
recent_with_images = bq_client.client.query("""
    SELECT plate_number, thumbnail_public_url, cropped_thumbnail_public_url
    FROM `menlo-oaks.license_plate_data.license_plate_detections`
    WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR)
      AND thumbnail_public_url IS NOT NULL
    ORDER BY detection_timestamp DESC
    LIMIT 10
""")

for row in recent_with_images:
    print(f"Plate: {row.plate_number}")
    print(f"Image: {row.thumbnail_public_url}")
```

### Using curl or wget
```bash
# Download an image using the public URL
wget "https://storage.googleapis.com/menlo-oaks-thumbnails/license_plates/2025/09/21/ABC123_20250921_050925_alarm_thumbnail.jpg"
```

## Image Access Permissions

The images are stored in the `menlo-oaks-thumbnails` GCS bucket with public URLs for easy access. The Cloud Function service account has been granted the necessary permissions to upload images.

## Viewing Images in a Web Browser

Since the `thumbnail_public_url` and `cropped_thumbnail_public_url` fields contain direct HTTP URLs, you can:

1. **Copy the URL from BigQuery results** and paste it into any web browser
2. **Use in HTML img tags**: `<img src="{thumbnail_public_url}" alt="License plate detection" />`
3. **Embed in applications** or dashboards directly

## Next Steps

To build a web interface for viewing images:

1. Query BigQuery for recent detections with images
2. Display the results in an HTML table
3. Use the `thumbnail_public_url` fields as image sources
4. Add filtering by date range, camera, or license plate number

The infrastructure is already in place - you just need to query the database and use the stored URLs!
