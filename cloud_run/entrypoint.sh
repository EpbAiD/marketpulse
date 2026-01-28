#!/bin/bash
set -e

echo "=============================================="
echo "🚀 Cloud Run GPU Training Job"
echo "=============================================="
echo "Mode: ${MODE:-auto}"
echo "Features: ${FEATURES:-all}"
echo "Force Retrain: ${FORCE_RETRAIN:-false}"
echo "Incremental Commits: ${INCREMENTAL_COMMITS:-true}"
echo "=============================================="

# Verify GPU is available
python -c "import torch; print(f'GPU Available: {torch.cuda.is_available()}'); print(f'GPU Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

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
    # Copy over the installed packages symlink approach won't work, so we use the cloned repo
    export PYTHONPATH=/app:$PYTHONPATH
fi

# Function to commit and push changes (used for final push if not incremental)
commit_and_push() {
    if [ -n "$GITHUB_TOKEN" ] && [ -n "$REPO_DIR" ]; then
        echo "📤 Pushing results to GitHub..."
        cd "$REPO_DIR"

        git add outputs/forecasting/models/ 2>/dev/null || true
        git add outputs/clustering/ 2>/dev/null || true
        git add outputs/classification/ 2>/dev/null || true

        if git diff --staged --quiet; then
            echo "No changes to commit"
        else
            git commit -m "chore: update models from Cloud Run training [skip ci]"
            git pull --rebase origin main || true
            git push origin main
            echo "✅ Results pushed to GitHub!"
        fi
    fi
}

# Run based on mode
case "${MODE}" in
    "auto")
        echo "🤖 Running intelligent auto mode..."
        python run_pipeline.py --workflow auto
        commit_and_push
        ;;
    "train")
        echo "🏋️ Running training..."

        # Check if incremental commits are enabled (default: true)
        if [ "${INCREMENTAL_COMMITS:-true}" = "true" ] && [ -n "$REPO_DIR" ]; then
            echo "📝 Using incremental training with immediate commits..."

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

            # Run incremental trainer
            python cloud_run/incremental_trainer.py \
                --config configs/features_config.yaml \
                --repo-dir "$REPO_DIR" \
                $FEATURE_ARG \
                $FORCE_ARG
        else
            # Original training approach (batch commit at end)
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
            commit_and_push
        fi
        ;;
    "inference")
        echo "🔮 Running inference only..."
        python run_pipeline.py --workflow inference
        commit_and_push
        ;;
    *)
        echo "Unknown mode: ${MODE}"
        exit 1
        ;;
esac

echo "=============================================="
echo "✅ Cloud Run job completed successfully!"
echo "=============================================="
