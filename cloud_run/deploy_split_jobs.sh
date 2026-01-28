#!/bin/bash
# Deploy Split Training Jobs to Cloud Run
# ========================================
# Creates 3 separate jobs that can run in parallel, each training a subset of features.
# Each job commits models immediately after training, so progress is preserved even on timeout.

set -e

PROJECT_ID="${PROJECT_ID:-coms-452404}"
REGION="us-central1"
IMAGE="us-central1-docker.pkg.dev/${PROJECT_ID}/marketpulse/training:latest"
SERVICE_ACCOUNT="marketpulse-training@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=============================================="
echo "🚀 Deploying Split Training Jobs"
echo "=============================================="
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE}"
echo "=============================================="

# Build and push the latest image first
echo ""
echo "📦 Building and pushing Docker image..."
gcloud builds submit --config cloud_run/cloudbuild.yaml --project ${PROJECT_ID}

# Common job settings
COMMON_ARGS="
    --region ${REGION}
    --cpu 4
    --memory 16Gi
    --task-timeout 14400
    --max-retries 1
    --service-account ${SERVICE_ACCOUNT}
    --set-secrets=GITHUB_TOKEN=github-token:latest
    --set-env-vars=GITHUB_REPO=EpbAiD/marketpulse,MODE=train,INCREMENTAL_COMMITS=true
    --set-env-vars=GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp/credentials.json
"

echo ""
echo "📋 Creating/updating split training jobs..."

# Batch 1: Daily features (high frequency)
echo ""
echo "🔹 Batch 1: Daily features (GSPC, IXIC, VIX, VIX3M, VIX9D, TNX, DXY, UUP)"
gcloud run jobs create marketpulse-training-batch1 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=GSPC,IXIC,VIX,VIX3M,VIX9D,TNX,DXY,UUP \
    2>/dev/null || \
gcloud run jobs update marketpulse-training-batch1 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=GSPC,IXIC,VIX,VIX3M,VIX9D,TNX,DXY,UUP

# Batch 2: Rates and spreads
echo ""
echo "🔹 Batch 2: Rates and spreads (DFF, DGS10, DGS2, DGS3MO, T10Y2Y, HY_YIELD, IG_YIELD, NFCI)"
gcloud run jobs create marketpulse-training-batch2 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=DFF,DGS10,DGS2,DGS3MO,T10Y2Y,HY_YIELD,IG_YIELD,NFCI \
    2>/dev/null || \
gcloud run jobs update marketpulse-training-batch2 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=DFF,DGS10,DGS2,DGS3MO,T10Y2Y,HY_YIELD,IG_YIELD,NFCI

# Batch 3: Commodities and macro
echo ""
echo "🔹 Batch 3: Commodities and macro (GOLD, OIL, COPPER, CPI, INDPRO, UNRATE)"
gcloud run jobs create marketpulse-training-batch3 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=GOLD,OIL,COPPER,CPI,INDPRO,UNRATE \
    2>/dev/null || \
gcloud run jobs update marketpulse-training-batch3 \
    --image ${IMAGE} \
    ${COMMON_ARGS} \
    --set-env-vars=FEATURES=GOLD,OIL,COPPER,CPI,INDPRO,UNRATE

echo ""
echo "=============================================="
echo "✅ Split jobs deployed successfully!"
echo "=============================================="
echo ""
echo "To run all jobs in parallel:"
echo "  gcloud run jobs execute marketpulse-training-batch1 --region ${REGION} --async"
echo "  gcloud run jobs execute marketpulse-training-batch2 --region ${REGION} --async"
echo "  gcloud run jobs execute marketpulse-training-batch3 --region ${REGION} --async"
echo ""
echo "To monitor:"
echo "  gcloud run jobs executions list --job marketpulse-training-batch1 --region ${REGION}"
echo "  gcloud run jobs executions list --job marketpulse-training-batch2 --region ${REGION}"
echo "  gcloud run jobs executions list --job marketpulse-training-batch3 --region ${REGION}"
echo ""
