#!/usr/bin/env bash
###############################################################################
# Auto Inference Script - Market Regime Forecasting System
###############################################################################
# This script demonstrates the auto mode that:
# 1. Detects if models are available and fresh
# 2. Runs inference if models exist, or triggers training if needed
# 3. Updates dashboard with latest forecasts
#
# Usage:
#   ./run_auto_inference.sh
#
# Or manually:
#   python run_pipeline.py --workflow auto
###############################################################################

set -e  # Exit on error

echo "=============================================================================="
echo "🚀 AUTO INFERENCE MODE - Market Regime Forecasting"
echo "=============================================================================="
echo ""

# Check if models exist
echo "📊 Step 1: Checking model availability..."
python orchestrator/intelligent_model_checker.py

# Store exit code
MODEL_STATUS=$?

echo ""
echo "=============================================================================="

if [ $MODEL_STATUS -eq 0 ]; then
    echo "✅ All models ready! Running inference workflow..."
    echo "=============================================================================="
    echo ""

    # Run inference only (fast: ~2-3 minutes)
    python run_pipeline.py --workflow inference

    RESULT=$?

    if [ $RESULT -eq 0 ]; then
        echo ""
        echo "=============================================================================="
        echo "✅ AUTO INFERENCE COMPLETE"
        echo "=============================================================================="
        echo ""
        echo "📊 Forecast generated and saved to BigQuery"
        echo "🌐 Dashboard updated with latest predictions"
        echo ""
        echo "View dashboard at: http://localhost:8501"
        echo "Start dashboard: streamlit run dashboard/app.py"
        echo ""
    else
        echo ""
        echo "❌ Inference failed with exit code $RESULT"
        exit $RESULT
    fi

else
    echo "⚠️  Models missing or outdated! Running full training + inference..."
    echo "=============================================================================="
    echo ""

    # Run full workflow (slow: several hours depending on training needs)
    python run_pipeline.py --workflow auto

    RESULT=$?

    if [ $RESULT -eq 0 ]; then
        echo ""
        echo "=============================================================================="
        echo "✅ AUTO MODE COMPLETE (Training + Inference)"
        echo "=============================================================================="
        echo ""
        echo "🔧 Models trained successfully"
        echo "📊 Forecast generated and saved to BigQuery"
        echo "🌐 Dashboard updated with latest predictions"
        echo ""
        echo "View dashboard at: http://localhost:8501"
        echo "Start dashboard: streamlit run dashboard/app.py"
        echo ""
    else
        echo ""
        echo "❌ Auto mode failed with exit code $RESULT"
        exit $RESULT
    fi
fi

echo "=============================================================================="
echo "📝 Next Steps:"
echo "=============================================================================="
echo ""
echo "1. View forecasts in dashboard: streamlit run dashboard/app.py"
echo "2. Schedule daily runs: Add to cron or GitHub Actions"
echo "3. Check BigQuery for forecast history"
echo ""
echo "For manual control:"
echo "  - python run_pipeline.py --workflow inference   (daily operations)"
echo "  - python run_pipeline.py --workflow training    (retrain models)"
echo "  - python run_pipeline.py --workflow auto        (smart auto-detect)"
echo ""
