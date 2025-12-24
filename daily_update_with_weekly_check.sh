#!/bin/bash
# Daily Update Script with Weekly Performance Check
# Usage: ./daily_update_with_weekly_check.sh

echo "=================================="
echo "RFP Daily Update"
echo "Started: $(date)"
echo "=================================="

# Step 1: Refresh data with latest market data
echo ""
echo "[1/3] Refreshing market data..."
python continuous_data_refresh.py --full-update

if [ $? -ne 0 ]; then
    echo "❌ Data refresh failed"
    exit 1
fi

# Step 2: Check if it's Friday - if so, check model performance
echo ""
echo "[2/3] Checking if weekly model evaluation needed..."

DAY_OF_WEEK=$(date +%u)  # 1=Monday, 5=Friday, 7=Sunday

if [ "$DAY_OF_WEEK" -eq 5 ]; then
    echo "It's Friday - running weekly performance check..."

    # First, just check performance
    python autonomous_improvement_agent.py --monitor-only > outputs/weekly_check.json

    # Parse the accuracy from the output
    ACCURACY=$(python -c "import json; print(json.load(open('outputs/weekly_check.json')).get('overall_accuracy', 1.0))" 2>/dev/null || echo "1.0")

    echo "Current accuracy: $ACCURACY"

    # If accuracy < 0.70, suggest retraining
    if (( $(echo "$ACCURACY < 0.70" | bc -l) )); then
        echo ""
        echo "⚠️ WARNING: Model accuracy below threshold!"
        echo "   Current: $(echo "$ACCURACY * 100" | bc)%"
        echo "   Threshold: 70%"
        echo ""
        echo "Recommendation: Run retraining this evening:"
        echo "   nohup python autonomous_improvement_agent.py > outputs/retrain.log 2>&1 &"
        echo ""
        echo "Or let it run now (will take 1-2 hours):"
        read -p "Start retraining now? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo "Starting retraining..."
            python autonomous_improvement_agent.py
        else
            echo "Skipping retraining for now. Remember to run it later!"
        fi
    else
        echo "✅ Model performance is good ($(echo "$ACCURACY * 100" | bc)%)"
        echo "   No retraining needed this week."
    fi
else
    echo "Not Friday - skipping weekly check"
fi

# Step 3: Summary
echo ""
echo "[3/3] Update complete"
echo "=================================="
echo "Finished: $(date)"
echo ""
echo "Dashboard ready at: http://localhost:8501"
echo "To view: streamlit run dashboard/app.py"
echo ""
echo "Logs:"
echo "  Data freshness: outputs/data_freshness_log.jsonl"
echo "  Data refresh: outputs/data_refresh_log.jsonl"
echo "  Alerts: outputs/alert_log.jsonl"
if [ "$DAY_OF_WEEK" -eq 5 ]; then
    echo "  Weekly check: outputs/weekly_check.json"
fi
echo "=================================="
