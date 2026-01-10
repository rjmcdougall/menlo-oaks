# License Plate Detection Backfill Script

This script allows you to backfill historical license plate detection data from your UniFi Protect system into BigQuery.

## Prerequisites

1. **Environment Setup**: Make sure you have the same environment variables configured as your webhook function:
   ```bash
   export UNIFI_PROTECT_HOST="your-protect-host"
   export UNIFI_PROTECT_USERNAME="your-username" 
   export UNIFI_PROTECT_PASSWORD="your-password"
   export GOOGLE_CLOUD_PROJECT="menlo-oaks"
   export BIGQUERY_DATASET="license_plates_dev"
   export BIGQUERY_TABLE="detections"
   ```

2. **Dependencies**: The script uses the same dependencies as the webhook function. Make sure you have them installed:
   ```bash
   pip install uiprotect google-cloud-bigquery
   ```

3. **Authentication**: Ensure you're authenticated with Google Cloud:
   ```bash
   gcloud auth application-default login
   ```

## Usage

### Basic Usage

Run a dry-run first to see what data would be processed:

```bash
python3 backfill_detections.py --dry-run
```

This will:
- Connect to your UniFi Protect system
- Fetch the last 30 days of license plate detection events
- Show you what would be inserted without actually inserting anything

### Actually Insert Data

Once you're satisfied with the dry-run results, run it for real:

```bash
python3 backfill_detections.py
```

### With Thumbnail Extraction (New!)

The backfill script now automatically extracts and stores thumbnail images alongside the detection data:

```bash
# Standard backfill with thumbnails (default behavior)
python3 backfill_detections.py --days 30

# Skip thumbnail processing for faster execution
python3 backfill_detections.py --no-thumbnails --days 30
```

### Advanced Options

**Specify number of days to look back:**
```bash
python3 backfill_detections.py --days 90  # Look back 90 days
```

**Enable verbose logging:**
```bash
python3 backfill_detections.py --verbose
```

**Combine options:**
```bash
python3 backfill_detections.py --days 7 --dry-run --verbose
```

## What the Script Does

1. **Connects** to your UniFi Protect system using the API
2. **Fetches** historical smart detection events in chunks (7 days at a time to avoid API limits)
3. **Filters** for events that contain license plate detections
4. **Enriches** the data with additional camera and event information
5. **Extracts and stores thumbnails** (both event snapshots and cropped license plates) to Google Cloud Storage
6. **Inserts** records into BigQuery using the same format as the webhook, including thumbnail URLs

## Thumbnail Processing

The backfill script now includes comprehensive thumbnail extraction capabilities:

### What Gets Stored
- **Event Snapshots**: Full scene images showing the entire detection context
- **Cropped License Plates**: Close-up crops of just the license plate area
- **Organized Structure**: Images stored in `YYYY/MM/DD/` folders in the `menlo_oaks_thumbnails` bucket
- **Complete Metadata**: File sizes, content types, upload timestamps stored in BigQuery

### Thumbnail Options

```bash
# Default: Extract and store all thumbnails
python3 backfill_detections.py --days 30

# Skip thumbnails for faster processing
python3 backfill_detections.py --no-thumbnails --days 30

# Dry run with thumbnail processing preview
python3 backfill_detections.py --dry-run --verbose
```

### Environment Variables for Thumbnails

Make sure these are configured for thumbnail processing:

```bash
# Core GCS Settings
export GCS_THUMBNAIL_BUCKET="menlo_oaks_thumbnails"
export GCS_BUCKET_LOCATION="US"
export GCS_MAKE_PUBLIC="true"

# Thumbnail Types
export STORE_EVENT_SNAPSHOTS="true"    # Full scene images
export STORE_CROPPED_THUMBNAILS="true" # License plate crops

# File Processing
export GCS_MAX_FILE_SIZE="10485760"    # 10MB default
export GCS_DOWNLOAD_TIMEOUT="30"       # 30 seconds
export GCS_RETENTION_DAYS="90"         # 90 days auto-cleanup
```

### Thumbnail Processing Flow

1. **Event Snapshots**: Downloads full scene images from event snapshot URLs
2. **Cropped Plates**: Generates authenticated URLs for license plate crops
3. **Fallback Method**: Uses direct API calls if URLs are expired (for older events)
4. **Storage**: Uploads to organized GCS structure with unique filenames
5. **Metadata**: Stores all URLs and metadata in BigQuery alongside detection data

## Sample Output

```
2025-09-20 08:20:15,123 - __main__ - INFO - Starting backfill for last 30 days (dry_run=True)
2025-09-20 08:20:15,456 - __main__ - INFO - Successfully connected to UniFi Protect
2025-09-20 08:20:15,789 - __main__ - INFO - Fetching events for days 0 to 7 ago
2025-09-20 08:20:16,012 - __main__ - INFO - Found 12 new license plate events in this chunk
2025-09-20 08:20:16,234 - __main__ - INFO - Fetching events for days 7 to 14 ago
2025-09-20 08:20:16,567 - __main__ - INFO - Found 8 new license plate events in this chunk
...
2025-09-20 08:20:17,890 - __main__ - INFO - Found 45 license plate detection events
2025-09-20 08:20:18,123 - __main__ - INFO - [DRY RUN] Would insert: 7M15340 at 2025-09-19 14:25:30+00:00
2025-09-20 08:20:18,234 - __main__ - INFO - [DRY RUN] Would insert: ABC123 at 2025-09-19 10:15:22+00:00
...

✅ Backfill completed successfully!
   Events found: 45
   Events processed: 45
   Records inserted: 45

💡 This was a dry run. Use --dry-run=false to actually insert data.
```

## Error Handling

- The script handles API rate limits by fetching data in chunks
- Individual event processing errors are logged but don't stop the entire process
- Duplicate events are automatically filtered out
- Connection errors are retried automatically by the UniFi Protect client

## Monitoring Progress

- Use `--verbose` to see detailed processing information
- The script logs progress as it processes each chunk of data
- Final summary shows total events found, processed, and any errors encountered

## Verifying Results

After running the backfill, you can verify the data was inserted correctly:

### Detection Data Verification

```sql
SELECT 
  COUNT(*) as total_records,
  MIN(detection_timestamp) as earliest_detection,
  MAX(detection_timestamp) as latest_detection,
  COUNT(DISTINCT device_id) as unique_cameras
FROM `menlo-oaks.license_plates_dev.detections`
WHERE processed_by = 'backfill_script'
```

### Thumbnail Storage Verification

```sql
-- Check thumbnail storage success rate
SELECT 
  DATE(detection_timestamp) as backfill_date,
  COUNT(*) as total_detections,
  COUNT(thumbnail_public_url) as event_snapshots_stored,
  COUNT(cropped_thumbnail_public_url) as license_plate_crops_stored,
  ROUND(COUNT(thumbnail_public_url) / COUNT(*) * 100, 2) as snapshot_success_rate,
  ROUND(COUNT(cropped_thumbnail_public_url) / COUNT(*) * 100, 2) as crop_success_rate
FROM `menlo-oaks.license_plates_dev.detections`
WHERE processed_by = 'backfill_script'
GROUP BY backfill_date
ORDER BY backfill_date DESC;
```

### Google Cloud Storage Verification

```bash
# Check bucket contents
gsutil ls -l gs://menlo_oaks_thumbnails/ | head -20

# Get storage statistics
gsutil du -sh gs://menlo_oaks_thumbnails/

# List recent backfill images
gsutil ls gs://menlo_oaks_thumbnails/$(date +%Y/%m/%d)/ | head -10
```

### Sample Result with Thumbnails

After successful backfill with thumbnails, your BigQuery records will include:

```sql
SELECT 
  plate_number,
  detection_timestamp,
  thumbnail_public_url,
  cropped_thumbnail_public_url,
  thumbnail_size_bytes,
  camera_name
FROM `menlo-oaks.license_plates_dev.detections`
WHERE processed_by = 'backfill_script'
  AND thumbnail_public_url IS NOT NULL
ORDER BY detection_timestamp DESC
LIMIT 5;
```

**Expected Result:**

| plate_number | detection_timestamp | thumbnail_public_url | cropped_thumbnail_public_url | thumbnail_size_bytes | camera_name |
|--------------|---------------------|---------------------|----------------------------|---------------------|-------------|
| 7M15340 | 2024-01-15 14:30:22 | https://storage.googleapis.com/.../7M15340_143022_a1b2c3d4_event_snapshot.jpg | https://storage.googleapis.com/.../7M15340_143022_a1b2c3d4_license_plate_crop.jpg | 245678 | Front Gate |
