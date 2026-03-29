#!/bin/bash
# Deploy POM Testing Agent to Cloud Run with Docker
# Service: pom-manager-testingv5
set -e # Exit on error
# Configuration
PROJECT_ID="np-sc-inventory-execution"
SERVICE_NAME="pom-manager-testingv5"
REGION="us-central1"
SERVICE_ACCOUNT="ai-pom-po@np-sc-inventory-execution.iam.gserviceaccount.com"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
IMAGE_TAG="${IMAGE_NAME}:${TIMESTAMP}"
IMAGE_LATEST="${IMAGE_NAME}:latest"
echo "=========================================================================="
echo "Deploying POM Testing Agent to Cloud Run"
echo "Service Name: ${SERVICE_NAME}"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Service Account: ${SERVICE_ACCOUNT}"
echo "Image: ${IMAGE_TAG}"
echo "=========================================================================="
# Step 1: Ensure we're in the right directory
cd "$(dirname "$0")"
echo "Step 1/5: Authenticating with Google Cloud..."
gcloud config set project ${PROJECT_ID}
# Step 2: Build Docker image using Cloud Build (no local Docker required)
echo ""
echo "Step 2/5: Building Docker image with Cloud Build..."
gcloud builds submit --tag ${IMAGE_TAG} --timeout=20m .
# Step 3: Deploy to Cloud Run
echo ""
echo "Step 3/5: Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
--image=${IMAGE_TAG} \
--platform=managed \
--region=${REGION} \
--service-account=${SERVICE_ACCOUNT} \
--memory=2Gi \
--cpu=2 \
--timeout=300 \
--concurrency=80 \
--min-instances=0 \
--max-instances=10 \
--port=8080 \
--allow-unauthenticated \
--set-env-vars="PYTHONUNBUFFERED=1" \
--quiet
# Step 4: Get service URL
echo ""
echo "Step 4/5: Getting service URL..."
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format='value(status.url)')
echo "=========================================================================="
echo "✅ Deployment Complete!"
echo "Service URL: ${SERVICE_URL}"
echo "Service Name: ${SERVICE_NAME}"
echo "Image: ${IMAGE_TAG}"
echo ""
echo "Test the service:"
echo "curl ${SERVICE_URL}/health"
echo ""
echo "API endpoint:"
echo "${SERVICE_URL}/apps/pom_testing_agent/"
echo "=========================================================================="