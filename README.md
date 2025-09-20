# UniFi Protect License Plate Detection Cloud Function

A Google Cloud Function that receives webhooks from UniFi Protect cameras when license plates are detected and stores the data in BigQuery for analysis and tracking.

## Features

- **Real-time Processing**: Receives webhooks from UniFi Protect immediately when license plates are detected
- **BigQuery Integration**: Stores detection data with full schema in BigQuery for analysis
- **Flexible Configuration**: Environment-based configuration for different deployment scenarios
- **Error Handling**: Comprehensive error handling and logging
- **Scalable**: Designed to handle multiple camera feeds and high detection volumes
- **Security**: Optional webhook signature validation

## Architecture

```
UniFi Protect Camera → License Plate Detection → Webhook → Cloud Function → BigQuery
```

## Project Structure

```
protectmenlo/
├── main.py                    # Main Cloud Function entry point
├── bigquery_client.py         # BigQuery integration and schema management  
├── unifi_protect_client.py    # UniFi Protect API client and webhook processing
├── config.py                  # Configuration management
├── requirements.txt           # Python dependencies
├── deploy.sh                  # Deployment script
├── .env.template             # Environment configuration template
└── README.md                 # This file
```

## Setup

### Prerequisites

1. **Google Cloud Project** with billing enabled
2. **UniFi Protect** system with cameras that support license plate detection
3. **gcloud CLI** installed and authenticated
4. **Python 3.11+** for local development

> **⚠️ Important Library Change**: This project now uses the `uiprotect` library instead of the deprecated `pyunifiprotect`. If you have an existing installation, please update your dependencies.

### Installation

1. Clone or download the project files
2. Copy the environment template:
   ```bash
   cp .env.template .env.development
   ```

3. Edit `.env.development` with your configuration:
   ```bash
   # Required
   GCP_PROJECT_ID=your-gcp-project-id
   
   # UniFi Protect connection
   UNIFI_PROTECT_HOST=your.unifi.protect.host
   UNIFI_PROTECT_USERNAME=your-username
   UNIFI_PROTECT_PASSWORD=your-password
   
   # Optional security
   WEBHOOK_SECRET=your-secret-key
   ```

### Deployment

1. Make the deploy script executable:
   ```bash
   chmod +x deploy.sh
   ```

2. Deploy to development:
   ```bash
   ./deploy.sh development your-gcp-project-id
   ```

3. Deploy to production:
   ```bash
   ./deploy.sh production your-gcp-project-id
   ```

The deployment script will:
- Enable required Google Cloud APIs
- Create BigQuery datasets and tables
- Deploy the Cloud Function
- Provide the webhook URL for UniFi Protect configuration

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | ✅ | - | Google Cloud Project ID |
| `BIGQUERY_DATASET` | ❌ | `license_plates` | BigQuery dataset name |
| `BIGQUERY_TABLE` | ❌ | `detections` | BigQuery table name |
| `UNIFI_PROTECT_HOST` | ❌ | - | UniFi Protect hostname/IP |
| `UNIFI_PROTECT_USERNAME` | ❌ | - | UniFi Protect username |
| `UNIFI_PROTECT_PASSWORD` | ❌ | - | UniFi Protect password |
| `WEBHOOK_SECRET` | ❌ | - | Webhook validation secret |
| `MIN_CONFIDENCE_THRESHOLD` | ❌ | `0.7` | Minimum detection confidence |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level |

### UniFi Protect Setup

1. **Enable License Plate Detection** on your cameras:
   - Go to UniFi Protect → Cameras
   - Select camera → Settings → Smart Detections
   - Enable "License Plate Detection"

2. **Configure Webhooks**:
   - Go to UniFi Protect → Settings → System
   - Add webhook URL: `https://your-cloud-function-url`
   - Set events to include "Smart Detection"

## BigQuery Schema

The function creates a table with the following schema:

| Field | Type | Description |
|-------|------|-------------|
| `record_id` | STRING | Unique record identifier |
| `plate_number` | STRING | Detected license plate number |
| `confidence` | FLOAT | Detection confidence (0-1) |
| `detection_timestamp` | DATETIME | When the plate was detected |
| `camera_id` | STRING | UniFi Protect camera ID |
| `camera_name` | STRING | Camera display name |
| `camera_location` | STRING | Camera location |
| `event_id` | STRING | UniFi Protect event ID |
| `snapshot_url` | STRING | URL to detection image |
| `latitude` | FLOAT | Camera GPS latitude |
| `longitude` | FLOAT | Camera GPS longitude |
| `detection_box_*` | FLOAT | License plate bounding box coordinates |
| `processed_by` | STRING | Processing system identifier |

## Usage Examples

### Query Recent Detections

```sql
SELECT 
    plate_number,
    camera_name,
    detection_timestamp,
    confidence
FROM `your-project.license_plates.detections`
WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR)
ORDER BY detection_timestamp DESC
```

### Find Specific License Plate

```sql
SELECT *
FROM `your-project.license_plates.detections`
WHERE plate_number = 'ABC123'
ORDER BY detection_timestamp DESC
```

### Detection Statistics

```sql
SELECT 
    COUNT(*) as total_detections,
    COUNT(DISTINCT plate_number) as unique_plates,
    DATE(detection_timestamp) as detection_date
FROM `your-project.license_plates.detections`
WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 7 DAY)
GROUP BY detection_date
ORDER BY detection_date DESC
```

## Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
   > **Note**: The project now uses `uiprotect>=5.0.0` instead of the deprecated `pyunifiprotect`

2. Set environment variables:
   ```bash
   export GCP_PROJECT_ID=your-project-id
   # ... other variables
   ```

3. Run locally:
   ```bash
   python main.py
   ```

4. Test webhook endpoint:
   ```bash
   curl -X POST http://localhost:8080/ \
     -H "Content-Type: application/json" \
     -d '{"type": "smart_detection", "smart_detect_data": {"detections": []}}'
   ```

## Monitoring and Troubleshooting

### View Logs

```bash
# View function logs
gcloud functions logs read license-plate-webhook --region=us-central1

# Tail logs in real-time
gcloud functions logs tail license-plate-webhook --region=us-central1
```

### Common Issues

1. **Function timeout**: Increase timeout in `deploy.sh`
2. **BigQuery permissions**: Ensure the function's service account has BigQuery Data Editor role
3. **Webhook not receiving data**: Check UniFi Protect webhook configuration
4. **Low detection confidence**: Adjust `MIN_CONFIDENCE_THRESHOLD`

### Health Check

The function provides a health check endpoint:
```bash
curl https://your-function-url/health
```

## Security Considerations

1. **Webhook Secrets**: Always use `WEBHOOK_SECRET` in production
2. **SSL Verification**: Keep `UNIFI_PROTECT_VERIFY_SSL=true` unless necessary
3. **IAM Permissions**: Use principle of least privilege for service accounts
4. **Network Security**: Consider VPC connector for internal UniFi Protect access

## Cost Optimization

1. **Function Configuration**:
   - Set appropriate memory allocation (512MB default)
   - Configure max instances based on expected load
   - Use min instances = 0 to reduce idle costs

2. **BigQuery**:
   - Partition tables by date for better performance
   - Set up table expiration if long-term storage isn't needed
   - Consider clustering on frequently queried columns

## License

This project is provided as-is for educational and personal use.

## Support

For issues with:
- **UniFi Protect**: Consult Ubiquiti documentation
- **Google Cloud**: Check GCP documentation and support
- **This integration**: Review logs and configuration
# menlo-oaks
