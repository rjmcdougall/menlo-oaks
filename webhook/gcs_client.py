"""
Google Cloud Storage client for storing license plate detection thumbnails
"""

import logging
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from io import BytesIO

from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
import requests

# Use root logger for consistent logging in GCP
logger = logging.getLogger()


class GCSClient:
    """Client for interacting with Google Cloud Storage to store thumbnails."""
    
    def __init__(self, config):
        """
        Initialize GCS client.
        
        Args:
            config: Configuration object containing GCS settings
        """
        self.config = config
        self.client = storage.Client(project=config.GCP_PROJECT_ID)
        self.bucket_name = config.GCS_THUMBNAIL_BUCKET or "menlo_oaks_thumbnails"
        
        # Initialize bucket (create if needed)
        self._ensure_bucket_exists()
    
    def upload_thumbnail(self, image_data: bytes, plate_number: str, 
                        detection_timestamp: str, event_id: str = "",
                        image_type: str = "snapshot") -> Dict[str, Any]:
        """
        Upload a thumbnail image to Google Cloud Storage.
        
        Args:
            image_data: Raw image data as bytes
            plate_number: License plate number for filename generation
            detection_timestamp: Timestamp of detection for organization
            event_id: UniFi Protect event ID
            image_type: Type of image ('snapshot', 'cropped', 'full')
            
        Returns:
            Dictionary containing upload results and metadata
            
        Raises:
            GoogleCloudError: If upload fails
        """
        try:
            # Generate unique filename
            filename = self._generate_filename(
                plate_number, detection_timestamp, event_id, image_type
            )
            
            # Get bucket reference
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(filename)
            
            # Set metadata
            blob.metadata = {
                'plate_number': plate_number,
                'detection_timestamp': detection_timestamp,
                'event_id': event_id,
                'image_type': image_type,
                'uploaded_by': 'unifi-protect-webhook',
                'upload_timestamp': datetime.utcnow().isoformat()
            }
            
            # Set content type based on image format
            content_type = self._detect_image_content_type(image_data)
            blob.content_type = content_type
            
            # Upload the image
            blob.upload_from_string(image_data, content_type=content_type)
            
            # For uniform bucket-level access, we cannot use blob.make_public()
            # Instead, we generate the public URL directly if bucket allows public access
            if self.config.GCS_MAKE_PUBLIC:
                # Generate direct public URL (works with uniform bucket-level access)
                public_url = f"https://storage.googleapis.com/{self.bucket_name}/{filename}"
            else:
                # Generate signed URL valid for configured time
                try:
                    public_url = blob.generate_signed_url(
                        expiration=datetime.utcnow() + self.config.GCS_SIGNED_URL_EXPIRY
                    )
                except Exception as e:
                    logger.warning(f"Could not generate signed URL, using public URL: {str(e)}")
                    public_url = f"https://storage.googleapis.com/{self.bucket_name}/{filename}"
            
            logger.info(f"Successfully uploaded thumbnail {filename} for plate {plate_number}")
            
            return {
                'success': True,
                'filename': filename,
                'gcs_path': f"gs://{self.bucket_name}/{filename}",
                'public_url': public_url,
                'blob_name': blob.name,
                'bucket_name': self.bucket_name,
                'content_type': content_type,
                'size_bytes': len(image_data),
                'upload_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error uploading thumbnail for plate {plate_number}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'filename': filename if 'filename' in locals() else 'unknown'
            }
    
    def download_and_upload_from_url(self, image_url: str, plate_number: str,
                                   detection_timestamp: str, event_id: str = "",
                                   image_type: str = "snapshot",
                                   auth_headers: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Download an image from URL and upload to GCS.
        
        Args:
            image_url: URL to download image from
            plate_number: License plate number
            detection_timestamp: Timestamp of detection
            event_id: UniFi Protect event ID
            image_type: Type of image
            auth_headers: Authentication headers for downloading
            
        Returns:
            Dictionary containing upload results
        """
        try:
            logger.info(f"Downloading image from URL: {image_url}")
            
            # Download image with timeout and size limits
            headers = auth_headers or {}
            response = requests.get(
                image_url, 
                headers=headers,
                timeout=self.config.GCS_DOWNLOAD_TIMEOUT,
                stream=True,
                verify=self.config.GCS_DOWNLOAD_VERIFY_SSL  # Use dedicated GCS download SSL verification setting
            )
            response.raise_for_status()
            
            # Check content length if available
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.config.GCS_MAX_FILE_SIZE:
                raise ValueError(f"Image too large: {content_length} bytes")
            
            # Read image data with size limit
            image_data = b""
            total_size = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    total_size += len(chunk)
                    if total_size > self.config.GCS_MAX_FILE_SIZE:
                        raise ValueError(f"Image too large: {total_size} bytes")
                    image_data += chunk
            
            logger.info(f"Downloaded {total_size} bytes for plate {plate_number}")
            
            # Upload to GCS
            return self.upload_thumbnail(
                image_data, plate_number, detection_timestamp, event_id, image_type
            )
            
        except requests.RequestException as e:
            logger.error(f"Error downloading image from {image_url}: {str(e)}")
            return {'success': False, 'error': f"Download failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Error processing image from URL: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _generate_filename(self, plate_number: str, detection_timestamp: str,
                          event_id: str = "", image_type: str = "snapshot") -> str:
        """
        Generate a unique filename for the thumbnail.
        
        Args:
            plate_number: License plate number
            detection_timestamp: Detection timestamp
            event_id: UniFi Protect event ID
            image_type: Type of image
            
        Returns:
            Unique filename for GCS storage
        """
        try:
            # Parse timestamp for folder organization
            dt = datetime.fromisoformat(detection_timestamp.replace('Z', '+00:00'))
            date_path = dt.strftime('%Y/%m/%d')
            time_str = dt.strftime('%H%M%S')
            
            # Clean plate number for filename
            clean_plate = ''.join(c for c in plate_number if c.isalnum()).upper()
            
            # Generate hash for uniqueness
            unique_data = f"{plate_number}_{detection_timestamp}_{event_id}_{image_type}"
            hash_suffix = hashlib.md5(unique_data.encode()).hexdigest()[:8]
            
            # Generate filename with extension
            filename = f"{date_path}/{clean_plate}_{time_str}_{hash_suffix}_{image_type}.jpg"
            
            return filename
            
        except Exception as e:
            # Fallback to UUID-based filename
            logger.warning(f"Error generating structured filename: {str(e)}")
            fallback_id = str(uuid.uuid4())
            return f"fallback/{fallback_id}_{image_type}.jpg"
    
    def _detect_image_content_type(self, image_data: bytes) -> str:
        """
        Detect image content type from image data.
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            MIME content type string
        """
        # Check magic bytes for common image formats
        if image_data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            return 'image/gif'
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return 'image/webp'
        else:
            # Default to JPEG for unknown formats
            return 'image/jpeg'
    
    def _ensure_bucket_exists(self):
        """Ensure the GCS bucket exists, create if it doesn't."""
        try:
            bucket = self.client.bucket(self.bucket_name)
            bucket.reload()
            logger.info(f"GCS bucket {self.bucket_name} exists")
        except Exception:
            # Bucket doesn't exist, create it
            logger.info(f"Creating GCS bucket {self.bucket_name}")
            bucket = self.client.bucket(self.bucket_name)
            
            # Set bucket location
            bucket.location = self.config.GCS_BUCKET_LOCATION
            
            # Configure bucket settings
            bucket.versioning_enabled = False
            bucket.default_kms_key_name = None  # Use default encryption
            
            # Set lifecycle rules to automatically delete old thumbnails
            if self.config.GCS_RETENTION_DAYS > 0:
                rule = {
                    "action": {"type": "Delete"},
                    "condition": {"age": self.config.GCS_RETENTION_DAYS}
                }
                bucket.lifecycle_rules = [rule]
            
            # Create the bucket
            self.client.create_bucket(bucket)
            logger.info(f"Created GCS bucket {self.bucket_name}")
    
    def delete_thumbnail(self, filename: str) -> bool:
        """
        Delete a thumbnail from GCS.
        
        Args:
            filename: Name of the file to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(filename)
            blob.delete()
            
            logger.info(f"Successfully deleted thumbnail {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting thumbnail {filename}: {str(e)}")
            return False
    
    def get_thumbnail_info(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a stored thumbnail.
        
        Args:
            filename: Name of the file
            
        Returns:
            Dictionary with file information or None if not found
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blob = bucket.blob(filename)
            blob.reload()
            
            return {
                'filename': filename,
                'size_bytes': blob.size,
                'content_type': blob.content_type,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'updated': blob.updated.isoformat() if blob.updated else None,
                'metadata': blob.metadata or {},
                'public_url': blob.public_url if blob.public_access_prevention != 'enforced' else None,
                'gcs_path': f"gs://{self.bucket_name}/{filename}"
            }
            
        except Exception as e:
            logger.error(f"Error getting thumbnail info for {filename}: {str(e)}")
            return None
    
    def list_thumbnails(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """
        List thumbnails in the bucket.
        
        Args:
            prefix: Filter by filename prefix
            limit: Maximum number of results
            
        Returns:
            List of thumbnail information dictionaries
        """
        try:
            bucket = self.client.bucket(self.bucket_name)
            blobs = bucket.list_blobs(prefix=prefix, max_results=limit)
            
            thumbnails = []
            for blob in blobs:
                info = {
                    'filename': blob.name,
                    'size_bytes': blob.size,
                    'content_type': blob.content_type,
                    'created': blob.time_created.isoformat() if blob.time_created else None,
                    'metadata': blob.metadata or {}
                }
                thumbnails.append(info)
            
            return thumbnails
            
        except Exception as e:
            logger.error(f"Error listing thumbnails: {str(e)}")
            return []
