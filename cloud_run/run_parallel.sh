#!/bin/bash
# Run All Training Batches in Parallel
# =====================================
# Executes all 3 batch jobs simultaneously for maximum speed.
# Each job commits models immediately, so even if one times out, progress is saved.

set -e

REGION="us-central1"

echo "=============================================="
echo "🚀 Starting Parallel Training (3 batches)"
echo "=============================================="

# Execute all batches asynchronously
echo ""
echo "🔹 Starting Batch 1 (GSPC, IXIC, VIX, VIX3M, VIX9D, TNX, DXY, UUP)..."
gcloud run jobs execute marketpulse-training-batch1 --region ${REGION} --async

echo "🔹 Starting Batch 2 (DFF, DGS10, DGS2, DGS3MO, T10Y2Y, HY_YIELD, IG_YIELD, NFCI)..."
gcloud run jobs execute marketpulse-training-batch2 --region ${REGION} --async

echo "🔹 Starting Batch 3 (GOLD, OIL, COPPER, CPI, INDPRO, UNRATE)..."
gcloud run jobs execute marketpulse-training-batch3 --region ${REGION} --async

echo ""
echo "=============================================="
echo "✅ All batches started!"
echo "=============================================="
echo ""
echo "Monitor progress with:"
echo "  ./cloud_run/check_status.sh"
echo ""
echo "Or check individual batches:"
echo "  gcloud run jobs executions list --job marketpulse-training-batch1 --region ${REGION} --limit 1"
echo "  gcloud run jobs executions list --job marketpulse-training-batch2 --region ${REGION} --limit 1"
echo "  gcloud run jobs executions list --job marketpulse-training-batch3 --region ${REGION} --limit 1"
echo ""
