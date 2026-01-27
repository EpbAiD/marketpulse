#!/bin/bash
set -e

echo "=============================================="
echo "🚀 Cloud Run GPU Training Job"
echo "=============================================="
echo "Mode: ${MODE:-auto}"
echo "Features: ${FEATURES:-all}"
echo "Force Retrain: ${FORCE_RETRAIN:-false}"
echo "=============================================="

# Verify GPU is available
python -c "import torch; print(f'GPU Available: {torch.cuda.is_available()}'); print(f'GPU Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

# Set up Git for pushing results
if [ -n "$GITHUB_TOKEN" ]; then
    git config --global user.email "cloud-run-bot@marketpulse.ai"
    git config --global user.name "Cloud Run Training Bot"
    git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"
    git fetch origin main
    git checkout main
    git pull origin main
fi

# Run based on mode
case "${MODE}" in
    "auto")
        echo "🤖 Running intelligent auto mode..."
        python run_pipeline.py --mode auto --retrain-if-needed
        ;;
    "train")
        echo "🏋️ Running full training..."
        if [ -n "$FEATURES" ] && [ "$FEATURES" != "all" ]; then
            echo "Training selective features: $FEATURES"
            python -c "
from forecasting_agent import forecaster
features = '${FEATURES}'.split(',')
forecaster.run_forecasting_agent(
    mode='all',
    config_path='configs/features_config.yaml',
    use_bigquery=True,
    force_retrain=${FORCE_RETRAIN:-False},
    selective_features=features
)
"
        else
            echo "Training all features..."
            python -c "
from forecasting_agent import forecaster
forecaster.run_forecasting_agent(
    mode='all',
    config_path='configs/features_config.yaml',
    use_bigquery=True,
    force_retrain=${FORCE_RETRAIN:-False}
)
"
        fi
        ;;
    "inference")
        echo "🔮 Running inference only..."
        python run_pipeline.py --mode inference
        ;;
    *)
        echo "Unknown mode: ${MODE}"
        exit 1
        ;;
esac

# Push results to GitHub
if [ -n "$GITHUB_TOKEN" ]; then
    echo "📤 Pushing results to GitHub..."
    git add outputs/forecasting/models/ 2>/dev/null || true
    git add outputs/clustering/ 2>/dev/null || true
    git add outputs/classification/ 2>/dev/null || true

    if git diff --staged --quiet; then
        echo "No changes to commit"
    else
        git commit -m "chore: update models from Cloud Run GPU training [skip ci]"
        git pull --rebase origin main
        git push origin main
        echo "✅ Results pushed to GitHub!"
    fi
fi

echo "=============================================="
echo "✅ Cloud Run job completed successfully!"
echo "=============================================="
