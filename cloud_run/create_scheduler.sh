#!/bin/bash
# ============================================
# Create Cloud Scheduler for Daily Training
# ============================================

set -e

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="us-central1"
JOB_NAME="marketpulse-training"
SCHEDULER_NAME="marketpulse-daily-training"
SERVICE_ACCOUNT="marketpulse-training"

echo "============================================"
echo "⏰ Creating Cloud Scheduler"
echo "============================================"

# Check if PROJECT_ID is set
if [ "$PROJECT_ID" = "your-project-id" ]; then
    echo "❌ Error: Please set GCP_PROJECT_ID environment variable"
    exit 1
fi

SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

# Delete existing scheduler if exists
gcloud scheduler jobs delete $SCHEDULER_NAME \
    --location=$REGION \
    --quiet 2>/dev/null || true

# Create Cloud Scheduler job
# Runs at 6:00 AM EST (11:00 UTC) every day
echo "📅 Creating scheduler job..."
gcloud scheduler jobs create http $SCHEDULER_NAME \
    --location=$REGION \
    --schedule="0 11 * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${JOB_NAME}:run" \
    --http-method=POST \
    --oauth-service-account-email=$SA_EMAIL \
    --description="Daily MarketPulse model training (auto mode)"

echo ""
echo "============================================"
echo "✅ Scheduler created!"
echo "============================================"
echo ""
echo "Schedule: Daily at 6:00 AM EST (11:00 UTC)"
echo ""
echo "To trigger manually:"
echo "  gcloud scheduler jobs run $SCHEDULER_NAME --location=$REGION"
echo ""
echo "To view status:"
echo "  gcloud scheduler jobs describe $SCHEDULER_NAME --location=$REGION"
echo ""
