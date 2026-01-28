#!/bin/bash
# Check Status of Training Jobs
# ==============================

REGION="us-central1"
PROJECT_ID="${PROJECT_ID:-coms-452404}"

echo "=============================================="
echo "📊 Training Job Status"
echo "=============================================="
echo ""

# Function to check a job
check_job() {
    local job_name=$1
    local features=$2

    echo "🔹 ${job_name}"
    echo "   Features: ${features}"

    # Get latest execution
    EXEC=$(gcloud run jobs executions list --job ${job_name} --region ${REGION} --limit 1 --format="value(name)" 2>/dev/null || echo "")

    if [ -z "$EXEC" ]; then
        echo "   Status: No executions found"
        echo ""
        return
    fi

    # Get execution details
    STATUS=$(gcloud run jobs executions describe ${EXEC} --region ${REGION} --format="value(status.conditions[0].type,status.succeededCount,status.failedCount,status.runningCount)" 2>/dev/null || echo "Unknown")

    # Parse status
    COMPLETED=$(echo $STATUS | cut -d' ' -f1)
    SUCCEEDED=$(echo $STATUS | cut -d' ' -f2)
    FAILED=$(echo $STATUS | cut -d' ' -f3)
    RUNNING=$(echo $STATUS | cut -d' ' -f4)

    if [ "$RUNNING" = "1" ]; then
        echo "   Status: 🏃 RUNNING"
    elif [ "$SUCCEEDED" = "1" ]; then
        echo "   Status: ✅ SUCCEEDED"
    elif [ "$FAILED" = "1" ]; then
        echo "   Status: ❌ FAILED"
    else
        echo "   Status: ⏳ ${COMPLETED}"
    fi
    echo ""
}

# Check main job
echo "📌 Main Job (all features)"
check_job "marketpulse-training" "all 22 features"

# Check split jobs
echo "📌 Split Jobs (parallel batches)"
check_job "marketpulse-training-batch1" "GSPC,IXIC,VIX,VIX3M,VIX9D,TNX,DXY,UUP"
check_job "marketpulse-training-batch2" "DFF,DGS10,DGS2,DGS3MO,T10Y2Y,HY_YIELD,IG_YIELD,NFCI"
check_job "marketpulse-training-batch3" "GOLD,OIL,COPPER,CPI,INDPRO,UNRATE"

echo "=============================================="
echo ""
echo "To view logs for a specific job:"
echo "  gcloud logging read 'resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"JOB_NAME\"' --limit 50 --project ${PROJECT_ID}"
echo ""
