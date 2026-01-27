#!/bin/bash
# ============================================
# Cloud Run GPU Training Setup Script
# ============================================
# This script sets up Cloud Run Jobs with GPU for model training.
# Run this once to configure your GCP project.
#
# Prerequisites:
# - gcloud CLI installed and authenticated
# - Docker installed
# - GCP project with billing enabled
# ============================================

set -e

# Configuration - UPDATE THESE
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="us-central1"
REPO_NAME="marketpulse"
JOB_NAME="marketpulse-training"
SERVICE_ACCOUNT="marketpulse-training"

echo "============================================"
echo "🚀 Setting up Cloud Run GPU Training"
echo "============================================"
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "============================================"

# Check if PROJECT_ID is set
if [ "$PROJECT_ID" = "your-project-id" ]; then
    echo "❌ Error: Please set GCP_PROJECT_ID environment variable"
    echo "   export GCP_PROJECT_ID=your-actual-project-id"
    exit 1
fi

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "📦 Enabling required APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    cloudscheduler.googleapis.com

# Create Artifact Registry repository
echo "📦 Creating Artifact Registry repository..."
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="MarketPulse ML training images" \
    2>/dev/null || echo "Repository already exists"

# Create service account
echo "👤 Creating service account..."
gcloud iam service-accounts create $SERVICE_ACCOUNT \
    --display-name="MarketPulse Training Service Account" \
    2>/dev/null || echo "Service account already exists"

# Grant permissions
echo "🔐 Granting permissions..."
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

# BigQuery access (for data fetching)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/bigquery.dataViewer" \
    --quiet

# Secret Manager access
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

# Cloud Run invoker (for scheduler)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.invoker" \
    --quiet

# Create secrets
echo "🔑 Creating secrets..."

# GitHub token secret (you'll need to add this manually)
gcloud secrets create github-token \
    --replication-policy="automatic" \
    2>/dev/null || echo "Secret github-token already exists"

echo ""
echo "⚠️  IMPORTANT: Add your GitHub token to the secret:"
echo "   echo 'YOUR_GITHUB_TOKEN' | gcloud secrets versions add github-token --data-file=-"
echo ""

# GCP credentials secret (copy from existing)
gcloud secrets create gcp-credentials \
    --replication-policy="automatic" \
    2>/dev/null || echo "Secret gcp-credentials already exists"

echo ""
echo "⚠️  IMPORTANT: Add your GCP credentials to the secret:"
echo "   gcloud secrets versions add gcp-credentials --data-file=/path/to/credentials.json"
echo ""

# Configure Docker for Artifact Registry
echo "🐳 Configuring Docker..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

echo ""
echo "============================================"
echo "✅ Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Add secrets (see above)"
echo "2. Build and push image: ./cloud_run/deploy.sh"
echo "3. Create scheduler: ./cloud_run/create_scheduler.sh"
echo ""
