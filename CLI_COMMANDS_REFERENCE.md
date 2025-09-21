# ProtectMenlo CLI Commands Reference

This document contains all the CLI commands used for managing the license plate detection system, including BigQuery operations, testing, deployment, and debugging.

## Table of Contents
- [BigQuery Commands](#bigquery-commands)
- [Cloud Functions Deployment](#cloud-functions-deployment)
- [Cloud Logging & Debugging](#cloud-logging--debugging)
- [Testing Commands](#testing-commands)
- [File Operations](#file-operations)
- [Project Setup & Configuration](#project-setup--configuration)

---

## BigQuery Commands

### Query Recent License Plate Detections
```bash
# Query all records from the last 24 hours
bq query --use_legacy_sql=false \
"SELECT * FROM \`menlo-oaks.license_plates.detections\` 
WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 24 HOUR) 
ORDER BY detection_timestamp DESC 
LIMIT 10"

# Query specific plate number
bq query --use_legacy_sql=false \
"SELECT * FROM \`menlo-oaks.license_plates.detections\` 
WHERE plate_number = 'H2F55U' 
ORDER BY detection_timestamp DESC"

# Count total records
bq query --use_legacy_sql=false \
"SELECT COUNT(*) as total_records FROM \`menlo-oaks.license_plates.detections\`"
```

### BigQuery Table Schema Operations
```bash
# Show table schema
bq show menlo-oaks:license_plates.detections

# Show table info with details
bq show --format=prettyjson menlo-oaks:license_plates.detections

# List all tables in dataset
bq ls menlo-oaks:license_plates
```

### BigQuery Dataset Operations
```bash
# List all datasets in project
bq ls --project_id=menlo-oaks

# Create dataset (if needed)
bq mk --dataset --location=US menlo-oaks:license_plates
```

---

## Cloud Functions Deployment

### Deploy Cloud Function
```bash
# Deploy with Python 3.11 (current/recommended)
gcloud functions deploy license-plate-webhook \
  --runtime python311 \
  --trigger-http \
  --allow-unauthenticated \
  --project menlo-oaks \
  --region us-central1 \
  --source . \
  --entry-point main \
  --memory 512MB \
  --timeout 540s

# Deploy with Python 3.9 (legacy - not recommended)
gcloud functions deploy license-plate-webhook \
  --runtime python39 \
  --trigger-http \
  --allow-unauthenticated \
  --project menlo-oaks \
  --region us-central1 \
  --source . \
  --entry-point main \
  --memory 512MB \
  --timeout 540s
```

### Cloud Function Management
```bash
# List all functions
gcloud functions list --project menlo-oaks

# Get function details
gcloud functions describe license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks

# View function logs
gcloud functions logs read license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks \
  --limit 50

# Delete function (if needed)
gcloud functions delete license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks
```

---

## Cloud Logging & Debugging

### Query Cloud Run Logs (License Plate Webhook)
```bash
# Search for specific plate number in logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook AND timestamp>=\"2025-09-21T15:20:00Z\" AND timestamp<=\"2025-09-21T15:30:00Z\"" \
  --limit=200 \
  --project=menlo-oaks \
  --format=json | \
  jq -r '.[] | select(.textPayload // .jsonPayload.message // "" | contains("H2F55U")) | "\(.timestamp) \(.severity) \(.textPayload // .jsonPayload.message // "")"' | \
  head -10

# Get all recent webhook logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook" \
  --limit=100 \
  --project=menlo-oaks \
  --format="table(timestamp,severity,textPayload)"

# Search for BigQuery-related logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook AND (textPayload:\"BigQuery\" OR jsonPayload.message:\"BigQuery\")" \
  --limit=50 \
  --project=menlo-oaks

# Search for error logs
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook AND severity>=ERROR" \
  --limit=50 \
  --project=menlo-oaks
```

### Real-time Log Streaming
```bash
# Stream logs in real-time
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook" \
  --project=menlo-oaks

# Stream only error logs
gcloud logging tail \
  "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook AND severity>=ERROR" \
  --project=menlo-oaks
```

---

## Testing Commands

### Python Script Execution
```bash
# Run test extraction script
python test_extraction.py

# Run with verbose output
python -v test_extraction.py

# Run specific test functions (if using pytest)
pytest test_extraction.py::test_specific_function -v
```

### Test HTTP Webhook Locally
```bash
# Test webhook with curl (example payload)
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{
    "plate_number": "TEST123",
    "confidence": 0.95,
    "detection_timestamp": "2025-01-21T15:30:00Z",
    "camera_name": "Front Gate"
  }'

# Test deployed webhook
curl -X POST https://us-central1-menlo-oaks.cloudfunctions.net/license-plate-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "plate_number": "TEST456",
    "confidence": 0.87,
    "detection_timestamp": "2025-01-21T15:30:00Z"
  }'
```

---

## File Operations

### Search and Find Commands
```bash
# Find Python files in current directory
find . -name "*.py" -type f

# Search for specific text in files
grep -r "BigQuery" . --include="*.py"

# Search for function definitions
grep -r "def.*insert" . --include="*.py"

# Find configuration files
find . -name "*.json" -o -name "*.yaml" -o -name "*.yml"
```

### File Content Operations
```bash
# View file with line numbers
cat -n bigquery_client.py

# View specific lines of a file
sed -n '50,100p' bigquery_client.py

# Search for imports in Python files
grep -n "^import\|^from" *.py
```

---

## Project Setup & Configuration

### Google Cloud Project Setup
```bash
# Set default project
gcloud config set project menlo-oaks

# List current configuration
gcloud config list

# Authenticate (if needed)
gcloud auth login
gcloud auth application-default login

# Set default region
gcloud config set functions/region us-central1
```

### Environment Variables
```bash
# Set environment variables for local testing
export GCP_PROJECT_ID=menlo-oaks
export BIGQUERY_DATASET=license_plates
export BIGQUERY_TABLE=detections
export STORE_IMAGES=true
export LOG_EXECUTION_ID=true

# View current environment variables
env | grep -E "(GCP|BIGQUERY|STORE|LOG)"
```

### Python Environment Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Update pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt --upgrade

# List installed packages
pip list

# Generate requirements file
pip freeze > requirements.txt
```

---

## Useful Debugging Commands

### Check Function Status
```bash
# Check if function is active
gcloud functions describe license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks \
  --format="value(state)"

# Get function URL
gcloud functions describe license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks \
  --format="value(httpsTrigger.url)"
```

### Monitor Resource Usage
```bash
# Check Cloud Function metrics
gcloud logging metrics list --project menlo-oaks

# View Cloud Function execution metrics
gcloud functions logs read license-plate-webhook \
  --region us-central1 \
  --project menlo-oaks \
  --limit 10 \
  --format="table(timestamp,executionId)"
```

### BigQuery Job Management
```bash
# List recent BigQuery jobs
bq ls -j --max_results=10 menlo-oaks

# Show details of a specific job
bq show -j <job_id>

# Cancel a running job (if needed)
bq cancel <job_id>
```

---

## Quick Reference Commands

### Most Frequently Used
```bash
# Deploy function
gcloud functions deploy license-plate-webhook --runtime python311 --trigger-http --allow-unauthenticated --project menlo-oaks --region us-central1 --source . --entry-point main --memory 512MB --timeout 540s

# Query recent detections
bq query --use_legacy_sql=false "SELECT * FROM \`menlo-oaks.license_plates.detections\` WHERE detection_timestamp >= DATETIME_SUB(CURRENT_DATETIME(), INTERVAL 1 HOUR) ORDER BY detection_timestamp DESC"

# View recent logs
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=license-plate-webhook" --limit=20 --project=menlo-oaks

# Test Python script
python test_extraction.py
```

---

## Notes

1. **Project ID**: All commands use `menlo-oaks` as the project ID
2. **Region**: Functions are deployed to `us-central1`
3. **Python Runtime**: Upgraded from python39 to python311 for better compatibility
4. **BigQuery Dataset**: `license_plates` with table `detections`
5. **Function URL**: https://us-central1-menlo-oaks.cloudfunctions.net/license-plate-webhook

## Troubleshooting Tips

- If deployment fails, check `requirements.txt` for incompatible dependencies
- Use `gcloud functions logs read` to debug runtime issues
- Use BigQuery web console for complex queries and schema inspection
- Check Cloud Function memory and timeout settings if experiencing performance issues
- Use `--format=json` with gcloud commands for programmatic parsing
