"""
BigQuery client for storing license plate detection data from UniFi Protect
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List

from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError

logger = logging.getLogger(__name__)


class BigQueryClient:
    """Client for interacting with BigQuery to store license plate data."""
    
    def __init__(self, config):
        """
        Initialize BigQuery client.
        
        Args:
            config: Configuration object containing BigQuery settings
        """
        self.config = config
        self.client = bigquery.Client(project=config.GCP_PROJECT_ID)
        self.dataset_id = config.BIGQUERY_DATASET
        self.table_id = config.BIGQUERY_TABLE
        
        # Ensure dataset and table exist
        self._ensure_dataset_exists()
        self._ensure_table_exists()
    
    def insert_license_plate_record(self, plate_data: Dict[str, Any]) -> str:
        """
        Insert a license plate detection record into BigQuery.
        
        Args:
            plate_data: Dictionary containing license plate detection data
            
        Returns:
            Record ID of the inserted record
            
        Raises:
            GoogleCloudError: If insertion fails
        """
        try:
            # Generate unique record ID
            record_id = str(uuid.uuid4())
            
            # Prepare the row data
            row_data = self._prepare_row_data(plate_data, record_id)
            
            # Get table reference
            table_ref = self.client.dataset(self.dataset_id).table(self.table_id)
            table = self.client.get_table(table_ref)
            
            # Insert the row
            errors = self.client.insert_rows_json(table, [row_data])
            
            if errors:
                error_msg = f"BigQuery insertion errors: {errors}"
                logger.error(error_msg)
                raise GoogleCloudError(error_msg)
            
            logger.info(f"Successfully inserted record {record_id} for plate {plate_data['plate_number']}")
            return record_id
            
        except Exception as e:
            logger.error(f"Error inserting license plate record: {str(e)}")
            raise
    
    def _prepare_row_data(self, plate_data: Dict[str, Any], record_id: str) -> Dict[str, Any]:
        """
        Prepare row data for BigQuery insertion.
        Enhanced to handle vehicle attributes and new timestamp fields.
        
        Args:
            plate_data: Raw plate data
            record_id: Unique record ID
            
        Returns:
            Formatted row data for BigQuery
        """
        # Convert datetime strings to BigQuery DATETIME format
        detection_timestamp = self._parse_timestamp(plate_data.get("detection_timestamp"))
        plate_detection_timestamp = self._parse_timestamp(plate_data.get("plate_detection_timestamp"))
        processing_timestamp = self._parse_timestamp(plate_data.get("processing_timestamp"))
        event_timestamp = self._parse_timestamp(plate_data.get("event_timestamp"))
        
        row_data = {
            # Core license plate fields
            "record_id": record_id,
            "plate_number": plate_data.get("plate_number", "").upper(),
            "confidence": float(plate_data.get("confidence", 0.0)),
            "cropped_id": plate_data.get("cropped_id", ""),
            
            # Timestamps
            "detection_timestamp": detection_timestamp,
            "plate_detection_timestamp": plate_detection_timestamp,
            "processing_timestamp": processing_timestamp,
            "event_timestamp": event_timestamp,
            
            # Vehicle attributes
            "vehicle_type": plate_data.get("vehicle_type", ""),
            "vehicle_type_confidence": float(plate_data.get("vehicle_type_confidence", 0.0)) if plate_data.get("vehicle_type_confidence") is not None else None,
            "vehicle_color": plate_data.get("vehicle_color", ""),
            "vehicle_color_confidence": float(plate_data.get("vehicle_color_confidence", 0.0)) if plate_data.get("vehicle_color_confidence") is not None else None,
            
            # Camera and location info
            "camera_id": plate_data.get("camera_id", ""),
            "camera_name": plate_data.get("camera_name", ""),
            "camera_location": plate_data.get("camera_location", ""),
            "event_id": plate_data.get("event_id", ""),
            "latitude": float(plate_data.get("latitude", 0.0)),
            "longitude": float(plate_data.get("longitude", 0.0)),
            
            # Image and snapshot info
            "snapshot_url": plate_data.get("snapshot_url", ""),
            "image_width": int(plate_data.get("image_width", 0)),
            "image_height": int(plate_data.get("image_height", 0)),
            
            # Legacy bounding box fields (for backward compatibility)
            "detection_box_x": float(plate_data.get("detection_box", {}).get("x", 0.0)),
            "detection_box_y": float(plate_data.get("detection_box", {}).get("y", 0.0)),
            "detection_box_width": float(plate_data.get("detection_box", {}).get("width", 0.0)),
            "detection_box_height": float(plate_data.get("detection_box", {}).get("height", 0.0)),
            
            # Processing metadata
            "processed_by": plate_data.get("processed_by", ""),
            "raw_detection_data": str(plate_data.get("raw_detection", {}))
        }
        
        return row_data
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[str]:
        """
        Parse timestamp string to BigQuery DATETIME format.
        
        Args:
            timestamp_str: Timestamp string in ISO format
            
        Returns:
            Formatted timestamp string or None
        """
        if not timestamp_str:
            return None
        
        try:
            # Parse ISO format timestamp
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            # Return in BigQuery DATETIME format (YYYY-MM-DD HH:MM:SS)
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {timestamp_str}: {str(e)}")
            return None
    
    def _ensure_dataset_exists(self):
        """Ensure the BigQuery dataset exists, create if it doesn't."""
        try:
            dataset_ref = self.client.dataset(self.dataset_id)
            self.client.get_dataset(dataset_ref)
            logger.info(f"Dataset {self.dataset_id} exists")
        except Exception:
            # Dataset doesn't exist, create it
            logger.info(f"Creating dataset {self.dataset_id}")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = self.config.BIGQUERY_LOCATION
            dataset.description = "License plate detections from UniFi Protect"
            self.client.create_dataset(dataset)
            logger.info(f"Created dataset {self.dataset_id}")
    
    def _ensure_table_exists(self):
        """Ensure the BigQuery table exists with proper schema, create if it doesn't."""
        try:
            table_ref = self.client.dataset(self.dataset_id).table(self.table_id)
            self.client.get_table(table_ref)
            logger.info(f"Table {self.table_id} exists")
        except Exception:
            # Table doesn't exist, create it
            logger.info(f"Creating table {self.table_id}")
            schema = self._get_table_schema()
            table = bigquery.Table(table_ref, schema=schema)
            table.description = "License plate detections from UniFi Protect cameras"
            
            # Set table options
            table.time_partitioning = bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="detection_timestamp"
            )
            
            self.client.create_table(table)
            logger.info(f"Created table {self.table_id}")
    
    def _get_table_schema(self) -> List[bigquery.SchemaField]:
        """
        Define the BigQuery table schema for license plate data.
        Enhanced schema with vehicle attributes and multiple plate support.
        
        Returns:
            List of schema fields
        """
        schema = [
            # Core license plate fields
            bigquery.SchemaField("record_id", "STRING", mode="REQUIRED", description="Unique record identifier"),
            bigquery.SchemaField("plate_number", "STRING", mode="REQUIRED", description="License plate number"),
            bigquery.SchemaField("confidence", "FLOAT", mode="REQUIRED", description="Detection confidence score (0-1)"),
            bigquery.SchemaField("cropped_id", "STRING", mode="NULLABLE", description="UniFi Protect thumbnail crop ID"),
            
            # Timestamps
            bigquery.SchemaField("detection_timestamp", "DATETIME", mode="REQUIRED", description="When the plate was detected by our system"),
            bigquery.SchemaField("plate_detection_timestamp", "DATETIME", mode="NULLABLE", description="When the plate was detected by UniFi Protect"),
            bigquery.SchemaField("processing_timestamp", "DATETIME", mode="NULLABLE", description="When the record was processed"),
            bigquery.SchemaField("event_timestamp", "DATETIME", mode="NULLABLE", description="Event timestamp from UniFi Protect"),
            
            # Vehicle attributes
            bigquery.SchemaField("vehicle_type", "STRING", mode="NULLABLE", description="Vehicle type (car, truck, suv, etc.)"),
            bigquery.SchemaField("vehicle_type_confidence", "FLOAT", mode="NULLABLE", description="Vehicle type confidence score (0-1)"),
            bigquery.SchemaField("vehicle_color", "STRING", mode="NULLABLE", description="Vehicle color"),
            bigquery.SchemaField("vehicle_color_confidence", "FLOAT", mode="NULLABLE", description="Vehicle color confidence score (0-1)"),
            
            # Camera and location info
            bigquery.SchemaField("camera_id", "STRING", mode="NULLABLE", description="UniFi Protect camera ID"),
            bigquery.SchemaField("camera_name", "STRING", mode="NULLABLE", description="Camera display name"),
            bigquery.SchemaField("camera_location", "STRING", mode="NULLABLE", description="Camera location description"),
            bigquery.SchemaField("event_id", "STRING", mode="NULLABLE", description="UniFi Protect event ID"),
            bigquery.SchemaField("latitude", "FLOAT", mode="NULLABLE", description="Camera latitude"),
            bigquery.SchemaField("longitude", "FLOAT", mode="NULLABLE", description="Camera longitude"),
            
            # Image and snapshot info
            bigquery.SchemaField("snapshot_url", "STRING", mode="NULLABLE", description="URL to detection snapshot"),
            bigquery.SchemaField("image_width", "INTEGER", mode="NULLABLE", description="Snapshot image width"),
            bigquery.SchemaField("image_height", "INTEGER", mode="NULLABLE", description="Snapshot image height"),
            
            # Legacy bounding box fields (kept for backward compatibility)
            bigquery.SchemaField("detection_box_x", "FLOAT", mode="NULLABLE", description="License plate bounding box X coordinate"),
            bigquery.SchemaField("detection_box_y", "FLOAT", mode="NULLABLE", description="License plate bounding box Y coordinate"),
            bigquery.SchemaField("detection_box_width", "FLOAT", mode="NULLABLE", description="License plate bounding box width"),
            bigquery.SchemaField("detection_box_height", "FLOAT", mode="NULLABLE", description="License plate bounding box height"),
            
            # Processing metadata
            bigquery.SchemaField("processed_by", "STRING", mode="NULLABLE", description="Processing system identifier"),
            bigquery.SchemaField("raw_detection_data", "STRING", mode="NULLABLE", description="Raw detection data JSON")
        ]
        
        return schema
    
    def query_plates_by_number(self, plate_number: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query license plate detections by plate number.
        
        Args:
            plate_number: License plate number to search for
            limit: Maximum number of results to return
            
        Returns:
            List of detection records
        """
        try:
            query = f"""
            SELECT *
            FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.table_id}`
            WHERE plate_number = @plate_number
            ORDER BY detection_timestamp DESC
            LIMIT {limit}
            """
            
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("plate_number", "STRING", plate_number.upper())
                ]
            )
            
            results = self.client.query(query, job_config=job_config)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error querying plates by number: {str(e)}")
            raise
    
    def query_recent_detections(self, hours: int = 24, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query recent license plate detections.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of results to return
            
        Returns:
            List of recent detection records
        """
        try:
            query = f"""
            SELECT *
            FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.table_id}`
            WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {hours} HOUR)
            ORDER BY detection_timestamp DESC
            LIMIT {limit}
            """
            
            results = self.client.query(query)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error querying recent detections: {str(e)}")
            raise
    
    def get_detection_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get detection statistics for the specified time period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with detection statistics
        """
        try:
            query = f"""
            SELECT 
                COUNT(*) as total_detections,
                COUNT(DISTINCT plate_number) as unique_plates,
                COUNT(DISTINCT camera_id) as active_cameras,
                AVG(confidence) as avg_confidence,
                DATE(detection_timestamp) as detection_date
            FROM `{self.config.GCP_PROJECT_ID}.{self.dataset_id}.{self.table_id}`
            WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL {days} DAY)
            GROUP BY detection_date
            ORDER BY detection_date DESC
            """
            
            results = self.client.query(query)
            return [dict(row) for row in results]
            
        except Exception as e:
            logger.error(f"Error getting detection stats: {str(e)}")
            raise
