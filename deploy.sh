#!/bin/bash

# Google Cloud Function Deployment Script for UniFi Protect License Plate Detection
# Usage: ./deploy.sh [environment] [project-id]

set -e  # Exit on any error

# Default values
ENVIRONMENT=${1:-"development"}
PROJECT_ID=${2:-""}
FUNCTION_NAME="license-plate-webhook"
REGION="us-central1"
MEMORY="512MB"
TIMEOUT="60s"
RUNTIME="python311"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate inputs
if [[ -z "$PROJECT_ID" ]]; then
    log_error "Project ID is required"
    echo "Usage: $0 [environment] [project-id]"
    echo "Example: $0 production my-gcp-project"
    exit 1
fi

# Validate gcloud is installed
if ! command -v gcloud &> /dev/null; then
    log_error "gcloud CLI is not installed. Please install it first."
    exit 1
fi

# Validate project access
log_info "Validating project access..."
if ! gcloud projects describe "$PROJECT_ID" &> /dev/null; then
    log_error "Cannot access project $PROJECT_ID. Please check project ID and permissions."
    exit 1
fi

# Set project
log_info "Setting active project to $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

# Enable required APIs
log_info "Enabling required Google Cloud APIs..."
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable bigquery.googleapis.com
gcloud services enable storage-api.googleapis.com
gcloud services enable logging.googleapis.com

# Create BigQuery dataset if it doesn't exist
DATASET_NAME="license_plates"
if [[ "$ENVIRONMENT" == "development" ]]; then
    DATASET_NAME="license_plates_dev"
elif [[ "$ENVIRONMENT" == "test" ]]; then
    DATASET_NAME="license_plates_test"
fi

log_info "Creating BigQuery dataset: $DATASET_NAME"
bq mk --dataset --location=US "$PROJECT_ID:$DATASET_NAME" || log_warn "Dataset $DATASET_NAME already exists"

# Environment-specific configurations
if [[ "$ENVIRONMENT" == "production" ]]; then
    log_info "Deploying to PRODUCTION environment"
    MEMORY="1GB"
    TIMEOUT="120s"
    ENV_VARS="ENVIRONMENT=production,LOG_LEVEL=INFO,BIGQUERY_DATASET=$DATASET_NAME"
elif [[ "$ENVIRONMENT" == "development" ]]; then
    log_info "Deploying to DEVELOPMENT environment"
    ENV_VARS="ENVIRONMENT=development,LOG_LEVEL=DEBUG,BIGQUERY_DATASET=$DATASET_NAME"
else
    log_info "Deploying to $ENVIRONMENT environment"
    ENV_VARS="ENVIRONMENT=$ENVIRONMENT,BIGQUERY_DATASET=$DATASET_NAME"
fi

# Add GCP project ID to environment variables
ENV_VARS="$ENV_VARS,GCP_PROJECT_ID=$PROJECT_ID"

# Check for .env file with additional environment variables
if [[ -f ".env.${ENVIRONMENT}" ]]; then
    log_info "Loading environment variables from .env.${ENVIRONMENT}"
    # Note: You'll need to manually add these to ENV_VARS since gcloud doesn't support .env files directly
    log_warn "Please ensure sensitive environment variables are set through gcloud secrets or environment variables"
fi

# Validate required files
log_info "Validating required files..."
required_files=("main.py" "requirements.txt" "config.py" "bigquery_client.py" "unifi_protect_client.py")

for file in "${required_files[@]}"; do
    if [[ ! -f "$file" ]]; then
        log_error "Required file $file not found"
        exit 1
    fi
done

log_info "All required files found"

# Deploy the function
log_info "Deploying Cloud Function: $FUNCTION_NAME"

gcloud functions deploy "$FUNCTION_NAME" \
    --gen2 \
    --runtime="$RUNTIME" \
    --region="$REGION" \
    --source=. \
    --entry-point=license_plate_webhook \
    --trigger-http \
    --allow-unauthenticated \
    --memory="$MEMORY" \
    --timeout="$TIMEOUT" \
    --set-env-vars="$ENV_VARS" \
    --max-instances=10 \
    --min-instances=0

# Get the function URL
FUNCTION_URL=$(gcloud functions describe "$FUNCTION_NAME" --region="$REGION" --format="value(serviceConfig.uri)")

log_info "Deployment completed successfully!"
log_info "Function URL: $FUNCTION_URL"
log_info "Function Name: $FUNCTION_NAME"
log_info "Region: $REGION"
log_info "Environment: $ENVIRONMENT"

# Test the function
log_info "Testing function health endpoint..."
if curl -s -f "${FUNCTION_URL}/health" > /dev/null; then
    log_info "Health check passed!"
else
    log_warn "Health check failed. The function might still be starting up."
fi

# Display next steps
echo ""
log_info "Next steps:"
echo "1. Configure UniFi Protect webhooks to point to: $FUNCTION_URL"
echo "2. Set environment variables for UniFi Protect connection:"
echo "   - UNIFI_PROTECT_HOST"
echo "   - UNIFI_PROTECT_USERNAME"
echo "   - UNIFI_PROTECT_PASSWORD"
echo "   - WEBHOOK_SECRET (recommended)"
echo "3. Test the integration by triggering a license plate detection"
echo ""
echo "To view logs: gcloud functions logs read $FUNCTION_NAME --region=$REGION"
echo "To update environment variables: gcloud functions deploy $FUNCTION_NAME --update-env-vars KEY=VALUE --region=$REGION"
