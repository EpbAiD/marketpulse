#!/bin/bash
set -e

echo "=============================================="
echo "🚀 Cloud Run Training Job"
echo "=============================================="
echo "Mode: ${MODE:-auto}"
echo "Features: ${FEATURES:-all}"
echo "Force Retrain: ${FORCE_RETRAIN:-false}"
echo "=============================================="

# Check if GPU/CPU
python -c "import torch; print(f'GPU Available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')" || echo "PyTorch not available, using CPU"

# Clone repo fresh (container doesn't have .git)
REPO_DIR=""
if [ -n "$GITHUB_TOKEN" ]; then
    echo "📥 Cloning repository..."
    cd /tmp
    git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git" repo
    cd repo
    git config user.email "cloud-run-bot@marketpulse.ai"
    git config user.name "Cloud Run Training Bot"
    REPO_DIR="/tmp/repo"
    export PYTHONPATH=/app:$PYTHONPATH
fi

# =============================================================================
# CLOUD RUN ONLY DOES TRAINING - NOT THE FULL PIPELINE
# GitHub Actions handles: data fetch, engineering, selection, clustering,
# classification, inference, monitoring
# Cloud Run handles: ONLY model training (memory-intensive neural networks)
# =============================================================================

# Build feature argument
FEATURE_ARG=""
if [ -n "$FEATURES" ] && [ "$FEATURES" != "all" ]; then
    FEATURE_ARG="--features $FEATURES"
fi

# Build force retrain argument
FORCE_ARG=""
if [ "${FORCE_RETRAIN:-false}" = "true" ] || [ "${FORCE_RETRAIN:-false}" = "True" ]; then
    FORCE_ARG="--force-retrain"
fi

# All modes use the same incremental training approach for memory efficiency
# The only difference is how features are determined:
# - auto: Uses intelligent_model_checker to detect which features need training
# - train: Uses FEATURES env var (or all if not specified)
# - inference: Should not be called on Cloud Run (handled by GitHub Actions)

case "${MODE}" in
    "auto")
        echo "🤖 Auto mode: Detecting features that need training..."

        # Run intelligent model checker to get features that need training
        FEATURES_TO_TRAIN=$(python -c "
import sys
sys.path.insert(0, '/tmp/repo')
from orchestrator.intelligent_model_checker import get_intelligent_recommendation
rec = get_intelligent_recommendation()
features = rec.get('features_to_train', [])
if features:
    print(','.join(features))
else:
    print('')
" 2>/dev/null || echo "")

        if [ -z "$FEATURES_TO_TRAIN" ]; then
            echo "✅ All models are fresh! No training needed."
            exit 0
        fi

        echo "🎯 Features to train: $FEATURES_TO_TRAIN"
        FEATURE_ARG="--features $FEATURES_TO_TRAIN"
        ;;
    "train")
        echo "🏋️ Train mode: Using specified features..."
        # FEATURE_ARG already set above from FEATURES env var
        ;;
    "inference")
        echo "⚠️ Inference mode should be handled by GitHub Actions, not Cloud Run."
        echo "Cloud Run is for training only. Exiting."
        exit 0
        ;;
    *)
        echo "Unknown mode: ${MODE}"
        exit 1
        ;;
esac

# Run incremental training - trains one feature at a time and commits immediately
# This ensures:
# 1. Memory is freed after each feature
# 2. Progress is saved even if job times out
# 3. Other features can continue from where we left off
echo ""
echo "=============================================="
echo "🏋️ Starting Incremental Training"
echo "=============================================="
echo "Training approach: One feature at a time with immediate commits"
echo ""

python cloud_run/incremental_trainer.py \
    --config configs/features_config.yaml \
    --repo-dir "$REPO_DIR" \
    $FEATURE_ARG \
    $FORCE_ARG

echo "=============================================="
echo "✅ Cloud Run training job completed!"
echo "=============================================="
