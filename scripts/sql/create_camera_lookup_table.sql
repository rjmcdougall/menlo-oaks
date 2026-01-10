-- Camera lookup table creation DDL for BigQuery
-- This table stores normalized camera/device information that can be joined with license plate detections

CREATE TABLE IF NOT EXISTS `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup` (
  device_id STRING NOT NULL
    OPTIONS(description="UniFi Protect device ID (primary key)"),
  
  camera_id STRING
    OPTIONS(description="UniFi Protect camera ID (may be same as device_id)"),
  
  camera_name STRING NOT NULL
    OPTIONS(description="Human-readable camera name"),
  
  camera_location STRING
    OPTIONS(description="Camera location description"),
  
  latitude FLOAT64
    OPTIONS(description="Camera latitude coordinate"),
  
  longitude FLOAT64
    OPTIONS(description="Camera longitude coordinate"),
  
  camera_model STRING
    OPTIONS(description="Camera model/type"),
  
  installation_date DATE
    OPTIONS(description="When the camera was installed"),
  
  is_active BOOL NOT NULL
    OPTIONS(description="Whether the camera is currently active"),
  
  notes STRING
    OPTIONS(description="Additional notes about the camera"),
  
  created_at DATETIME NOT NULL
    OPTIONS(description="When this record was created"),
  
  updated_at DATETIME NOT NULL
    OPTIONS(description="When this record was last updated")
)
OPTIONS(
  description="Camera/device lookup table for UniFi Protect license plate detection system"
);

-- Create a view that joins detections with camera information
CREATE OR REPLACE VIEW `{{ PROJECT_ID }}.{{ DATASET_ID }}.detections_with_camera_info` AS
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
  
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.{{ TABLE_ID }}` d
LEFT JOIN `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup` c
  ON d.device_id = c.device_id;

-- Sample queries for using the camera lookup table

-- 1. View all cameras
/*
SELECT device_id, camera_name, camera_location, latitude, longitude
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup`
WHERE is_active = true
ORDER BY camera_name;
*/

-- 2. Join detections with camera info  
/*
SELECT d.plate_number, d.detection_timestamp, c.camera_name, c.camera_location
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.{{ TABLE_ID }}` d
LEFT JOIN `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup` c
  ON d.device_id = c.device_id
ORDER BY d.detection_timestamp DESC
LIMIT 10;
*/

-- 3. Use the pre-built view
/*
SELECT plate_number, detection_timestamp, camera_name, camera_location, latitude, longitude
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.detections_with_camera_info`
WHERE camera_active = true
ORDER BY detection_timestamp DESC
LIMIT 10;
*/

-- 4. Count detections by camera
/*
SELECT c.camera_name, c.camera_location, COUNT(*) as detection_count
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.{{ TABLE_ID }}` d
LEFT JOIN `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup` c
  ON d.device_id = c.device_id
GROUP BY c.camera_name, c.camera_location
ORDER BY detection_count DESC;
*/

-- 5. Get recent detections with location info
/*
SELECT 
  d.plate_number,
  d.detection_timestamp,
  d.confidence,
  c.camera_name,
  c.camera_location,
  c.latitude,
  c.longitude
FROM `{{ PROJECT_ID }}.{{ DATASET_ID }}.{{ TABLE_ID }}` d
LEFT JOIN `{{ PROJECT_ID }}.{{ DATASET_ID }}.camera_lookup` c
  ON d.device_id = c.device_id
WHERE d.detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR)
  AND c.is_active = true
ORDER BY d.detection_timestamp DESC;
*/
