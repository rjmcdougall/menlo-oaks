#!/bin/bash

# Deployment script for License Plate Detection Map Cloud Function
#
# This script deploys the Cloud Function that serves the interactive map interface
# for viewing license plate detection events.

set -e  # Exit on any error

# Configuration
FUNCTION_NAME="detection-map"
REGION="us-central1"
RUNTIME="python311"
ENTRY_POINT="detection_map"
MEMORY="512MB"
TIMEOUT="60s"
MAX_INSTANCES="10"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Deploying License Plate Detection Map Cloud Function...${NC}"

# Check if required environment variables are set
if [[ -z "$GCP_PROJECT_ID" ]]; then
    echo -e "${RED}❌ Error: GCP_PROJECT_ID environment variable is not set${NC}"
    echo "Please set it with: export GCP_PROJECT_ID=your-project-id"
    exit 1
fi

if [[ -z "$BIGQUERY_DATASET" ]]; then
    echo -e "${YELLOW}⚠️  Warning: BIGQUERY_DATASET not set, defaulting to 'license_plates'${NC}"
    export BIGQUERY_DATASET="license_plates"
fi

if [[ -z "$MAPBOX_ACCESS_TOKEN" ]]; then
    echo -e "${YELLOW}⚠️  Warning: MAPBOX_ACCESS_TOKEN not set. The map will not work properly.${NC}"
    echo "Please get a Mapbox token from https://www.mapbox.com/ and set it with:"
    echo "export MAPBOX_ACCESS_TOKEN=your-mapbox-token"
fi

echo -e "${GREEN}📋 Configuration:${NC}"
echo "  Function Name: $FUNCTION_NAME"
echo "  Project ID: $GCP_PROJECT_ID"
echo "  Dataset: $BIGQUERY_DATASET"
echo "  Region: $REGION"
echo "  Runtime: $RUNTIME"
echo "  Memory: $MEMORY"
echo "  Timeout: $TIMEOUT"

echo ""
echo -e "${GREEN}🔄 Deploying Cloud Function...${NC}"

# Deploy the function
gcloud functions deploy $FUNCTION_NAME \
    --gen2 \
    --runtime=$RUNTIME \
    --region=$REGION \
    --source=. \
    --entry-point=$ENTRY_POINT \
    --trigger-http \
    --allow-unauthenticated \
    --memory=$MEMORY \
    --timeout=$TIMEOUT \
    --max-instances=$MAX_INSTANCES \
    --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,BIGQUERY_DATASET=$BIGQUERY_DATASET,MAPBOX_ACCESS_TOKEN=$MAPBOX_ACCESS_TOKEN" \
    --project=$GCP_PROJECT_ID

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    
    # Get the function URL
    FUNCTION_URL=$(gcloud functions describe $FUNCTION_NAME --region=$REGION --project=$GCP_PROJECT_ID --format="value(serviceConfig.uri)")
    
    echo ""
    echo -e "${GREEN}🌐 Your map is now available at:${NC}"
    echo "   $FUNCTION_URL"
    echo ""
    echo -e "${GREEN}📍 API endpoints:${NC}"
    echo "   Detections: $FUNCTION_URL/api/detections"
    echo "   Cameras: $FUNCTION_URL/api/cameras"
    echo ""
    echo -e "${GREEN}💡 Usage tips:${NC}"
    echo "   • Use date range filters to query specific time periods"
    echo "   • Click markers to see detection details and thumbnails"
    echo "   • Use Cmd+R (Mac) or Ctrl+R (Windows/Linux) to refresh data"
    echo "   • Use Cmd+F (Mac) or Ctrl+F (Windows/Linux) to toggle filters"
    
else
    echo -e "${RED}❌ Deployment failed!${NC}"
    exit 1
fi
