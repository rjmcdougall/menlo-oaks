"""
Configuration management for UniFi Protect License Plate Detection Cloud Function
"""

import os
import logging
from typing import Optional

# Use root logger for consistent logging in GCP
logger = logging.getLogger()


class Config:
    """Configuration class for the application."""
    
    def __init__(self):
        """Initialize configuration from environment variables."""
        
        # Google Cloud Configuration
        self.GCP_PROJECT_ID = self._get_required_env("GCP_PROJECT_ID")
        self.BIGQUERY_DATASET = self._get_env("BIGQUERY_DATASET", "license_plates")
        self.BIGQUERY_TABLE = self._get_env("BIGQUERY_TABLE", "detections")
        self.BIGQUERY_LOCATION = self._get_env("BIGQUERY_LOCATION", "US")
        
        # UniFi Protect Configuration (host/port used for thumbnail URL construction)
        self.UNIFI_PROTECT_HOST = self._get_env("UNIFI_PROTECT_HOST", "")
        self.UNIFI_PROTECT_PORT = int(self._get_env("UNIFI_PROTECT_PORT", "443"))
        
        # Webhook Configuration
        self.WEBHOOK_SECRET = self._get_env("WEBHOOK_SECRET", "")

        # Google Photos Configuration (for face detection thumbnails)
        self.GOOGLE_PHOTOS_CLIENT_ID = self._get_env("GOOGLE_PHOTOS_CLIENT_ID", "")
        self.GOOGLE_PHOTOS_CLIENT_SECRET = self._get_env("GOOGLE_PHOTOS_CLIENT_SECRET", "")
        self.GOOGLE_PHOTOS_REFRESH_TOKEN = self._get_env("GOOGLE_PHOTOS_REFRESH_TOKEN", "")
        
        # Processing Configuration
        self.MIN_CONFIDENCE_THRESHOLD = float(self._get_env("MIN_CONFIDENCE_THRESHOLD", "0.7"))
        self.MIN_VEHICLE_TYPE_CONFIDENCE = float(self._get_env("MIN_VEHICLE_TYPE_CONFIDENCE", "0.6"))
        self.MIN_VEHICLE_COLOR_CONFIDENCE = float(self._get_env("MIN_VEHICLE_COLOR_CONFIDENCE", "0.6"))
        self.STORE_IMAGES = self._get_env("STORE_IMAGES", "false").lower() == "true"
        
        # Google Cloud Storage Configuration
        self.GCS_THUMBNAIL_BUCKET = self._get_env("GCS_THUMBNAIL_BUCKET", "menlo_oaks_thumbnails")
        self.GCS_BUCKET_LOCATION = self._get_env("GCS_BUCKET_LOCATION", "US")
        self.GCS_MAKE_PUBLIC = self._get_env("GCS_MAKE_PUBLIC", "true").lower() == "true"
        self.GCS_MAX_FILE_SIZE = int(self._get_env("GCS_MAX_FILE_SIZE", "10485760"))  # 10MB default
        self.GCS_DOWNLOAD_TIMEOUT = int(self._get_env("GCS_DOWNLOAD_TIMEOUT", "30"))  # 30 seconds
        self.GCS_RETENTION_DAYS = int(self._get_env("GCS_RETENTION_DAYS", "90"))  # 90 days default
        self.GCS_DOWNLOAD_VERIFY_SSL = self._get_env("GCS_DOWNLOAD_VERIFY_SSL", "true").lower() == "true"  # SSL verification for image downloads
        
        # GCS Signed URL settings (if not making public)
        from datetime import timedelta
        signed_url_hours = int(self._get_env("GCS_SIGNED_URL_HOURS", "24"))
        self.GCS_SIGNED_URL_EXPIRY = timedelta(hours=signed_url_hours)
        
        # Thumbnail processing settings
        self.STORE_EVENT_SNAPSHOTS = self._get_env("STORE_EVENT_SNAPSHOTS", "true").lower() == "true"
        self.STORE_CROPPED_THUMBNAILS = self._get_env("STORE_CROPPED_THUMBNAILS", "true").lower() == "true"
        
        # Multiple plate handling
        self.MAX_PLATES_PER_EVENT = int(self._get_env("MAX_PLATES_PER_EVENT", "10"))
        self.STORE_ALL_PLATES = self._get_env("STORE_ALL_PLATES", "true").lower() == "true"
        
        # Vehicle attribute filtering
        self.FILTER_VEHICLE_TYPES = self._get_env("FILTER_VEHICLE_TYPES", "").split(",") if self._get_env("FILTER_VEHICLE_TYPES") else []
        self.FILTER_VEHICLE_COLORS = self._get_env("FILTER_VEHICLE_COLORS", "").split(",") if self._get_env("FILTER_VEHICLE_COLORS") else []
        
        # Logging Configuration
        self.LOG_LEVEL = self._get_env("LOG_LEVEL", "INFO").upper()
        
        # Validation
        self._validate_config()
    
    def _get_env(self, key: str, default: str = "") -> str:
        """
        Get environment variable with optional default.
        
        Args:
            key: Environment variable name
            default: Default value if not set
            
        Returns:
            Environment variable value or default
        """
        value = os.environ.get(key, default)
        if value and key.endswith("PASSWORD"):
            logger.debug(f"Config {key}: ***")
        else:
            logger.debug(f"Config {key}: {value}")
        return value
    
    def _get_required_env(self, key: str) -> str:
        """
        Get required environment variable.
        
        Args:
            key: Environment variable name
            
        Returns:
            Environment variable value
            
        Raises:
            ValueError: If environment variable is not set
        """
        value = os.environ.get(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        
        if key.endswith("PASSWORD"):
            logger.debug(f"Config {key}: ***")
        else:
            logger.debug(f"Config {key}: {value}")
        
        return value
    
    def _validate_config(self):
        """Validate configuration values."""
        
        # Validate confidence threshold
        if not 0.0 <= self.MIN_CONFIDENCE_THRESHOLD <= 1.0:
            raise ValueError(f"MIN_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0, got {self.MIN_CONFIDENCE_THRESHOLD}")
        
        # Validate BigQuery dataset and table names
        if not self._is_valid_bigquery_name(self.BIGQUERY_DATASET):
            raise ValueError(f"Invalid BigQuery dataset name: {self.BIGQUERY_DATASET}")
        
        if not self._is_valid_bigquery_name(self.BIGQUERY_TABLE):
            raise ValueError(f"Invalid BigQuery table name: {self.BIGQUERY_TABLE}")
        
        # Validate UniFi Protect port
        if not 1 <= self.UNIFI_PROTECT_PORT <= 65535:
            raise ValueError(f"UNIFI_PROTECT_PORT must be between 1 and 65535, got {self.UNIFI_PROTECT_PORT}")
        
        # Log configuration summary
        self._log_config_summary()
    
    def _is_valid_bigquery_name(self, name: str) -> bool:
        """
        Validate BigQuery dataset/table name.
        
        Args:
            name: Name to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not name:
            return False
        
        # BigQuery names must start with a letter or underscore
        if not (name[0].isalpha() or name[0] == '_'):
            return False
        
        # BigQuery names can only contain letters, numbers, and underscores
        return all(c.isalnum() or c == '_' for c in name)
    
    def _log_config_summary(self):
        """Log configuration summary."""
        logger.info("Configuration Summary:")
        logger.info(f"  GCP Project: {self.GCP_PROJECT_ID}")
        logger.info(f"  BigQuery Dataset: {self.BIGQUERY_DATASET}")
        logger.info(f"  BigQuery Table: {self.BIGQUERY_TABLE}")
        logger.info(f"  BigQuery Location: {self.BIGQUERY_LOCATION}")
        logger.info(f"  Min Confidence Threshold: {self.MIN_CONFIDENCE_THRESHOLD}")
        logger.info(f"  Min Vehicle Type Confidence: {self.MIN_VEHICLE_TYPE_CONFIDENCE}")
        logger.info(f"  Min Vehicle Color Confidence: {self.MIN_VEHICLE_COLOR_CONFIDENCE}")
        logger.info(f"  Max Plates Per Event: {self.MAX_PLATES_PER_EVENT}")
        logger.info(f"  Store All Plates: {self.STORE_ALL_PLATES}")
        logger.info(f"  Store Images: {self.STORE_IMAGES}")
        logger.info(f"  Vehicle Type Filters: {self.FILTER_VEHICLE_TYPES or 'None'}")
        logger.info(f"  Vehicle Color Filters: {self.FILTER_VEHICLE_COLORS or 'None'}")
        logger.info(f"  UniFi Protect Host: {self.UNIFI_PROTECT_HOST or 'Not configured'}")
        logger.info(f"  UniFi Protect Port: {self.UNIFI_PROTECT_PORT}")
        logger.info(f"  GCS Download Verify SSL: {self.GCS_DOWNLOAD_VERIFY_SSL}")
        logger.info(f"  Webhook Secret Configured: {'Yes' if self.WEBHOOK_SECRET else 'No'}")
        logger.info(f"  Log Level: {self.LOG_LEVEL}")
    
    def get_bigquery_table_full_name(self) -> str:
        """
        Get fully qualified BigQuery table name.
        
        Returns:
            Full table name in format project.dataset.table
        """
        return f"{self.GCP_PROJECT_ID}.{self.BIGQUERY_DATASET}.{self.BIGQUERY_TABLE}"
    
    def to_dict(self) -> dict:
        """
        Convert configuration to dictionary (excluding sensitive data).
        
        Returns:
            Configuration dictionary
        """
        return {
            "gcp_project_id": self.GCP_PROJECT_ID,
            "bigquery_dataset": self.BIGQUERY_DATASET,
            "bigquery_table": self.BIGQUERY_TABLE,
            "bigquery_location": self.BIGQUERY_LOCATION,
            "unifi_protect_host": self.UNIFI_PROTECT_HOST,
            "unifi_protect_port": self.UNIFI_PROTECT_PORT,
            "min_confidence_threshold": self.MIN_CONFIDENCE_THRESHOLD,
            "store_images": self.STORE_IMAGES,
            "gcs_thumbnail_bucket": self.GCS_THUMBNAIL_BUCKET,
            "log_level": self.LOG_LEVEL,
            "webhook_secret_configured": bool(self.WEBHOOK_SECRET),
        }


# Environment-specific configuration classes
class DevelopmentConfig(Config):
    """Development configuration."""
    
    def __init__(self):
        super().__init__()
        # Override defaults for development
        if not os.environ.get("LOG_LEVEL"):
            self.LOG_LEVEL = "DEBUG"
        
        # Development-specific settings
        self.DEBUG = True
        logger.info("Using Development Configuration")


class ProductionConfig(Config):
    """Production configuration."""
    
    def __init__(self):
        super().__init__()
        # Production-specific settings
        self.DEBUG = False
        
        # Enforce stricter validation for production
        if not self.WEBHOOK_SECRET:
            logger.warning("WEBHOOK_SECRET not set in production environment")
        
        logger.info("Using Production Configuration")


class TestConfig(Config):
    """Test configuration."""
    
    def __init__(self):
        # Set test defaults
        os.environ.setdefault("GCP_PROJECT_ID", "test-project")
        os.environ.setdefault("BIGQUERY_DATASET", "test_license_plates")
        os.environ.setdefault("BIGQUERY_TABLE", "test_detections")
        os.environ.setdefault("MIN_CONFIDENCE_THRESHOLD", "0.5")
        
        super().__init__()
        
        # Test-specific settings
        self.DEBUG = True
        self.TESTING = True
        logger.info("Using Test Configuration")


def get_config() -> Config:
    """
    Get configuration instance based on environment.

    Returns:
        Configuration instance
    """
    env = os.environ.get("ENVIRONMENT", "development").lower()

    if env == "production":
        return ProductionConfig()
    elif env == "test":
        return TestConfig()
    else:
        return DevelopmentConfig()


# Configuration validation functions
def validate_environment():
    """
    Validate the current environment configuration.
    
    Raises:
        ValueError: If configuration is invalid
    """
    try:
        config = get_config()
        logger.info("Environment configuration is valid")
        return True
    except Exception as e:
        logger.error(f"Environment configuration is invalid: {str(e)}")
        raise


def get_required_environment_vars() -> list:
    """
    Get list of required environment variables.
    
    Returns:
        List of required environment variable names
    """
    return [
        "GCP_PROJECT_ID",
        # Optional but recommended
        "UNIFI_PROTECT_HOST",
        "WEBHOOK_SECRET"
    ]


def check_missing_environment_vars() -> list:
    """
    Check for missing environment variables.
    
    Returns:
        List of missing environment variable names
    """
    required_vars = get_required_environment_vars()
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    return missing_vars
