#!/bin/bash
# ============================================
# Build and Deploy Cloud Run Job
# ============================================

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="us-central1"
REPO_NAME="marketpulse"
JOB_NAME="marketpulse-training"
IMAGE_TAG="${1:-latest}"

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/training:${IMAGE_TAG}"

echo "============================================"
echo "🚀 Deploying Cloud Run GPU Job"
echo "============================================"
echo "Image: $IMAGE_URI"
echo "============================================"

# Check if PROJECT_ID is set
if [ "$PROJECT_ID" = "your-project-id" ]; then
    echo "❌ Error: Please set GCP_PROJECT_ID environment variable"
    exit 1
fi

# Build the Docker image
echo "🔨 Building Docker image..."
cd "$(dirname "$0")/.."
docker build -f cloud_run/Dockerfile -t $IMAGE_URI .

# Push to Artifact Registry
echo "📤 Pushing to Artifact Registry..."
docker push $IMAGE_URI

# Update job.yaml with actual project ID
echo "📝 Updating job configuration..."
sed "s/PROJECT_ID/${PROJECT_ID}/g" cloud_run/job.yaml > /tmp/job-deploy.yaml

# Deploy the job
echo "🚀 Deploying Cloud Run Job..."
gcloud run jobs replace /tmp/job-deploy.yaml \
    --region=$REGION

echo ""
echo "============================================"
echo "✅ Deployment complete!"
echo "============================================"
echo ""
echo "To run the job manually:"
echo "  gcloud run jobs execute $JOB_NAME --region=$REGION"
echo ""
echo "To run with specific features:"
echo "  gcloud run jobs execute $JOB_NAME --region=$REGION --update-env-vars MODE=train,FEATURES=GSPC,VIX"
echo ""
