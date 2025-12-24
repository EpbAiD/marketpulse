#!/bin/bash
# Daily Automated Update Script
# Runs full pipeline: inference → predictions log → dashboard screenshot → git push
# Usage: ./daily_update.sh

set -e  # Exit on any error

echo "================================================================================"
echo "📊 MarketPulse Daily Automation"
echo "Started: $(date)"
echo "================================================================================"

# Ensure correct git author configuration (prevent accidental Claude/other contributor)
echo ""
echo "[0/5] Verifying git configuration..."
git config user.name "EpbAiD"
git config user.email "eeshanpbhanap@gmail.com"
echo "   ✅ Git author: $(git config user.name) <$(git config user.email)>"

# Step 1: Run daily inference pipeline
echo ""
echo "[1/5] Running inference pipeline..."
python run_daily_update.py

if [ $? -ne 0 ]; then
    echo "❌ Inference pipeline failed"
    exit 1
fi

# Step 2: Log predictions to markdown
echo ""
echo "[2/5] Logging daily predictions..."
python log_daily_predictions.py

if [ $? -ne 0 ]; then
    echo "❌ Prediction logging failed"
    exit 1
fi

# Step 3: Start dashboard in background and capture screenshot
echo ""
echo "[3/5] Capturing dashboard screenshot..."

# Check if streamlit is already running on port 8501
if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "   ℹ️  Dashboard already running on port 8501"
else
    # Start dashboard in background
    echo "   🚀 Starting dashboard..."
    nohup streamlit run dashboard/app.py --server.headless true > /dev/null 2>&1 &
    DASHBOARD_PID=$!
    echo "   ⏳ Waiting for dashboard to initialize..."
    sleep 10
fi

# Capture screenshot
python capture_dashboard_screenshot.py

SCREENSHOT_STATUS=$?

# Kill dashboard if we started it
if [ ! -z "$DASHBOARD_PID" ]; then
    echo "   🛑 Stopping dashboard..."
    kill $DASHBOARD_PID 2>/dev/null || true
fi

if [ $SCREENSHOT_STATUS -ne 0 ]; then
    echo "   ⚠️  Screenshot capture failed (continuing anyway)"
fi

# Step 4: Update README with latest metrics
echo ""
echo "[4/5] Updating README with latest metrics..."

# Get latest forecast date
LATEST_FORECAST=$(python -c "
import pandas as pd
from pathlib import Path
import glob

files = sorted(glob.glob('outputs/inference/regime_predictions_*.parquet'))
if files:
    df = pd.read_parquet(files[-1])
    print(df['ds'].max().strftime('%B %d, %Y'))
else:
    print('N/A')
" 2>/dev/null)

echo "   ✅ Latest forecast: $LATEST_FORECAST"

# Step 5: Commit and push to GitHub
echo ""
echo "[5/5] Committing and pushing to GitHub..."

# Check if there are changes to commit
if [ -n "$(git status --porcelain)" ]; then
    # Stage all changes
    git add -A

    # Create commit message with timestamp
    COMMIT_MSG="Daily update $(date +%Y-%m-%d)

- Regime predictions for next 10 days
- Latest forecast: $LATEST_FORECAST
- Dashboard updated with current market data
- Validation metrics: $(python -c "
import pandas as pd
import glob
files = sorted(glob.glob('outputs/inference/regime_predictions_*.parquet'))
if files:
    df = pd.read_parquet(files[-1])
    print(f'{len(df)} days forecasted')
else:
    print('N/A')
" 2>/dev/null)"

    # Commit
    git commit -m "$COMMIT_MSG"

    # Verify commit author is correct (safety check)
    COMMIT_AUTHOR=$(git log -1 --format="%an <%ae>")
    if [[ "$COMMIT_AUTHOR" != "EpbAiD <eeshanpbhanap@gmail.com>" ]]; then
        echo "   ⚠️  WARNING: Commit author mismatch!"
        echo "   Expected: EpbAiD <eeshanpbhanap@gmail.com>"
        echo "   Got: $COMMIT_AUTHOR"
        echo "   ❌ Aborting push - please check git config"
        exit 1
    fi

    # Push to remote
    git push origin main

    echo "   ✅ Changes committed and pushed to GitHub"
    echo "   ✅ Verified: Commit author is EpbAiD <eeshanpbhanap@gmail.com>"
else
    echo "   ℹ️  No changes to commit"
fi

# Summary
echo ""
echo "================================================================================"
echo "✅ Daily automation complete!"
echo "================================================================================"
echo ""
echo "📊 Results:"
echo "   - Inference pipeline: ✅ Complete"
echo "   - Predictions logged: ✅ DAILY_PREDICTIONS.md updated"
echo "   - Dashboard screenshot: $([ $SCREENSHOT_STATUS -eq 0 ] && echo '✅ Captured' || echo '⚠️  Failed')"
echo "   - GitHub sync: ✅ Pushed to remote"
echo ""
echo "🌐 Dashboard: http://localhost:8501"
echo "   To view: streamlit run dashboard/app.py"
echo ""
echo "📁 Files updated:"
echo "   - DAILY_PREDICTIONS.md"
echo "   - dashboard_screenshots/dashboard_$(date +%Y%m%d)_*.png"
echo "   - outputs/inference/ (latest predictions)"
echo ""
echo "Finished: $(date)"
echo "================================================================================"
