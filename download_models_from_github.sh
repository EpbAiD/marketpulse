#!/usr/bin/env bash
###############################################################################
# Download Trained Models from GitHub Actions Artifacts
###############################################################################
# This script downloads all trained model artifacts from successful GitHub
# Actions workflow runs and copies them to the local outputs directory.
###############################################################################

set -e

echo "================================================================================"
echo "📥 Downloading Trained Models from GitHub Actions Artifacts"
echo "================================================================================"
echo ""

# Create temp directory
TEMP_DIR="/tmp/rfp_model_download"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Model output directory
MODELS_DIR="outputs/forecasting/models"
mkdir -p "$MODELS_DIR"

echo "📍 Temp directory: $TEMP_DIR"
echo "📍 Models directory: $MODELS_DIR"
echo ""

# Download Group A (features 1-7: daily)
echo "================================================================================
"
echo "📦 Downloading Group A (GSPC, IXIC, DXY, UUP, VIX, VIX3M)"
echo "================================================================================"
A_RUN=$(gh run list --workflow=train-parallel-a.yml --limit 5 --json databaseId,conclusion | jq -r '.[] | select(.conclusion=="success") | .databaseId' | head -1)
if [ -n "$A_RUN" ]; then
    echo "Run ID: $A_RUN"
    gh run download "$A_RUN" --dir "$TEMP_DIR/A"
    echo "✅ Downloaded Group A"
else
    echo "⚠️ No successful Group A run found"
fi

# Download Group B (features 8-14: daily)
echo ""
echo "================================================================================"
echo "📦 Downloading Group B (TNX, DGS10, DGS3MO, HY_YIELD, IG_YIELD, T10Y2Y)"
echo "================================================================================"
B_RUN=$(gh run list --workflow=train-parallel-b.yml --limit 5 --json databaseId,conclusion | jq -r '.[] | select(.conclusion=="success") | .databaseId' | head -1)
if [ -n "$B_RUN" ]; then
    echo "Run ID: $B_RUN"
    gh run download "$B_RUN" --dir "$TEMP_DIR/B"
    echo "✅ Downloaded Group B"
else
    echo "⚠️ No successful Group B run found"
fi

# Download Group C1 (features 15-18: daily)
echo ""
echo "================================================================================"
echo "📦 Downloading Group C1 (DFF, GOLD, OIL, COPPER)"
echo "================================================================================"
C1_RUN=$(gh run list --workflow=train-parallel-c1.yml --limit 5 --json databaseId,conclusion | jq -r '.[] | select(.conclusion=="success") | .databaseId' | head -1)
if [ -n "$C1_RUN" ]; then
    echo "Run ID: $C1_RUN"
    gh run download "$C1_RUN" --dir "$TEMP_DIR/C1"
    echo "✅ Downloaded Group C1"
else
    echo "⚠️ No successful Group C1 run found"
fi

# Download individual features (VIX9D, DGS2, NFCI, CPI, UNRATE, INDPRO)
echo ""
echo "================================================================================"
echo "📦 Downloading Individual Features (VIX9D, DGS2, NFCI, CPI, UNRATE, INDPRO)"
echo "================================================================================"

for feature in VIX9D DGS2 NFCI CPI UNRATE INDPRO; do
    RUN=$(gh run list --workflow=train-single-feature.yml --limit 20 --json databaseId,conclusion,createdAt | jq -r '.[] | select(.conclusion=="success") | .databaseId' | while read run_id; do
        # Check if this run trained the specific feature
        if gh run view "$run_id" --log 2>&1 | grep -q "python -m forecasting_agent.forecaster.*$feature"; then
            echo "$run_id"
            break
        fi
    done | head -1)

    if [ -n "$RUN" ]; then
        echo "  $feature: Run ID $RUN"
        gh run download "$RUN" --dir "$TEMP_DIR/$feature"
        echo "  ✅ Downloaded $feature"
    else
        echo "  ⚠️  No successful run found for $feature"
    fi
done

# Copy all models to outputs directory
echo ""
echo "================================================================================"
echo "📂 Copying Models to $MODELS_DIR"
echo "================================================================================"

# Function to copy models from artifact directory
copy_models() {
    local source_dir=$1
    local artifact_name=$2

    if [ -d "$source_dir/$artifact_name" ]; then
        # Find all feature directories and version files
        for item in "$source_dir/$artifact_name"/*; do
            if [ -e "$item" ]; then
                basename=$(basename "$item")
                echo "  Copying $basename..."
                cp -r "$item" "$MODELS_DIR/" 2>/dev/null || echo "  (already exists, skipping)"
            fi
        done
    fi
}

# Copy from each group
copy_models "$TEMP_DIR/A" "trained-models-parallel-a"
copy_models "$TEMP_DIR/B" "trained-models-parallel-b"
copy_models "$TEMP_DIR/C1" "trained-models-parallel-c1"

# Copy individual features
for feature in VIX9D DGS2 NFCI CPI UNRATE INDPRO; do
    copy_models "$TEMP_DIR/$feature" "trained-model-$feature"
done

# Verify what we have
echo ""
echo "================================================================================"
echo "✅ Verifying Downloaded Models"
echo "================================================================================"

# Count model bundles
BUNDLE_COUNT=$(find "$MODELS_DIR" -name "nf_bundle_v*" -type d | wc -l | tr -d ' ')
VERSION_COUNT=$(find "$MODELS_DIR" -name "*_versions.json" -type f | wc -l | tr -d ' ')

echo "📊 Model bundles found: $BUNDLE_COUNT"
echo "📊 Version files found: $VERSION_COUNT"
echo ""

# List features with models
echo "Features with models:"
for dir in "$MODELS_DIR"/*/; do
    if [ -d "$dir" ]; then
        feature=$(basename "$dir")
        if [ -d "$dir/nf_bundle_v1" ]; then
            echo "  ✅ $feature"
        fi
    fi
done

# Check for missing features
echo ""
echo "Checking for missing features..."
python3 << 'PYEOF'
import yaml
from pathlib import Path

with open('configs/features_config.yaml', 'r') as f:
    config = yaml.safe_load(f)

all_features = (
    config['daily']['features'] +
    config['weekly']['features'] +
    config['monthly']['features']
)

models_dir = Path('outputs/forecasting/models')
missing = []

for feature in all_features:
    nf_bundle = models_dir / feature / "nf_bundle_v1"
    if not nf_bundle.exists():
        missing.append(feature)

if missing:
    print(f"⚠️  Missing {len(missing)} features:")
    for f in missing:
        print(f"  ❌ {f}")
else:
    print("✅ All 22 features have trained models!")
PYEOF

echo ""
echo "================================================================================"
echo "🎉 Model Download Complete!"
echo "================================================================================"
echo ""
echo "Next steps:"
echo "  1. Test auto mode: python run_pipeline.py --workflow auto"
echo "  2. Run inference: python run_pipeline.py --workflow inference"
echo "  3. View dashboard: streamlit run dashboard/app.py"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"
