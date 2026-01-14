#!/bin/bash
# Upload local trained models as GitHub artifact
# This creates the initial "trained-models" artifact for GitHub Actions to download

echo "=================================================="
echo "📦 Uploading Local Models as GitHub Artifact"
echo "=================================================="
echo ""

# Check if models exist
if [ ! -d "outputs/models" ] || [ ! -f "outputs/models/hmm_model.joblib" ]; then
    echo "❌ Error: Models not found in outputs/models/"
    echo "Please train models first by running: python run_pipeline.py --workflow full"
    exit 1
fi

if [ ! -d "outputs/clustering" ] || [ ! -f "outputs/clustering/cluster_assignments.parquet" ]; then
    echo "❌ Error: Cluster assignments not found in outputs/clustering/"
    echo "Please train models first by running: python run_pipeline.py --workflow full"
    exit 1
fi

echo "✓ Models found:"
ls -lh outputs/models/*.joblib
echo ""
echo "✓ Cluster assignments found:"
ls -lh outputs/clustering/*.parquet
echo ""

# Create temporary directory for artifact
ARTIFACT_DIR="trained-models-artifact"
rm -rf "$ARTIFACT_DIR"
mkdir -p "$ARTIFACT_DIR/outputs/models"
mkdir -p "$ARTIFACT_DIR/outputs/clustering"
mkdir -p "$ARTIFACT_DIR/outputs/forecasting/models"

# Copy model files
echo "📋 Copying model files to artifact directory..."
cp outputs/models/*.joblib "$ARTIFACT_DIR/outputs/models/" 2>/dev/null || true
cp outputs/clustering/*.parquet "$ARTIFACT_DIR/outputs/clustering/" 2>/dev/null || true

# Copy forecasting models (NeuralForecast bundles)
if [ -d "outputs/forecasting/models" ]; then
    echo "📋 Copying forecasting models..."
    for feature_dir in outputs/forecasting/models/*/; do
        feature_name=$(basename "$feature_dir")
        mkdir -p "$ARTIFACT_DIR/outputs/forecasting/models/$feature_name"

        # Copy nf_bundle directories
        if ls "$feature_dir"nf_bundle_v* 1> /dev/null 2>&1; then
            cp -r "$feature_dir"nf_bundle_v* "$ARTIFACT_DIR/outputs/forecasting/models/$feature_name/"
            echo "  ✓ Copied $feature_name forecasting models"
        fi
    done
fi

echo ""
echo "📊 Artifact contents:"
du -sh "$ARTIFACT_DIR"
echo ""

# Create tarball for manual upload
TARBALL="trained-models.tar.gz"
tar -czf "$TARBALL" -C "$ARTIFACT_DIR" .
echo "✅ Created tarball: $TARBALL ($(du -h "$TARBALL" | cut -f1))"
echo ""

# Use GitHub CLI to upload as artifact
echo "🚀 Uploading to GitHub Actions..."
echo ""
echo "Note: To upload this artifact, you need to:"
echo "  1. Trigger a manual workflow run"
echo "  2. Or run this from within a GitHub Actions workflow"
echo ""
echo "For now, manually trigger the workflow from GitHub Actions tab:"
echo "  https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions/workflows/daily-forecast.yml"
echo ""
echo "The workflow will train models from scratch on first run,"
echo "then persist them for future runs."
echo ""

# Clean up
rm -rf "$ARTIFACT_DIR"

echo "=================================================="
echo "✅ Preparation complete!"
echo "=================================================="
