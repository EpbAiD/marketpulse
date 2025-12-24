#!/usr/bin/env python3
"""
Daily Predictions Logger
Logs daily regime predictions to a markdown file for tracking
"""

import os
import pandas as pd
from datetime import datetime
from pathlib import Path


def log_daily_predictions(output_file="DAILY_PREDICTIONS.md"):
    """
    Log today's regime predictions to markdown file

    Args:
        output_file: Path to output markdown file
    """
    print(f"📝 Logging daily predictions...")

    try:
        # Try to load from BigQuery first
        from data_agent.storage import get_storage
        storage = get_storage()

        if hasattr(storage, 'get_latest_forecasts'):
            # Get latest forecast from BigQuery
            latest_forecasts = storage.get_latest_forecasts(limit=1)

            if len(latest_forecasts) > 0:
                forecast_id = latest_forecasts.iloc[0]['forecast_id']
                predictions = storage.get_forecast_by_id(forecast_id)
                predictions = predictions.rename(columns={'predicted_date': 'ds', 'predicted_regime': 'regime'})
                source = "BigQuery"
            else:
                raise ValueError("No forecasts in BigQuery")
        else:
            raise ValueError("BigQuery not available")

    except Exception as e:
        # Fallback to local parquet files
        print(f"   ℹ️  Loading from local files: {e}")
        import glob

        forecast_files = sorted(
            glob.glob('outputs/forecasting/inference/regime_predictions_*.parquet'),
            key=os.path.getmtime,
            reverse=True
        )

        if not forecast_files:
            print("   ❌ No prediction files found")
            return False

        predictions = pd.read_parquet(forecast_files[0])
        source = "Local"

    # Convert date column
    predictions['ds'] = pd.to_datetime(predictions['ds'])

    # Generate log entry
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"\n## {timestamp}\n\n"
    log_entry += f"**Source:** {source}\n\n"
    log_entry += f"**Forecast Period:** {predictions['ds'].min().date()} to {predictions['ds'].max().date()}\n\n"
    log_entry += f"**Total Days:** {len(predictions)}\n\n"

    # Regime distribution
    log_entry += "### Regime Distribution\n\n"
    regime_names = {0: "Bull Market", 1: "Bear Market", 2: "Transitional"}

    for regime_id in sorted(predictions['regime'].unique()):
        count = (predictions['regime'] == regime_id).sum()
        pct = count / len(predictions) * 100
        avg_prob = predictions[predictions['regime'] == regime_id]['regime_probability'].mean()
        regime_name = regime_names.get(regime_id, f"Regime {regime_id}")

        log_entry += f"- **{regime_name}**: {count} days ({pct:.1f}%) - Avg confidence: {avg_prob:.3f}\n"

    # Daily breakdown
    log_entry += "\n### Daily Predictions\n\n"
    log_entry += "| Date | Regime | Confidence |\n"
    log_entry += "|------|--------|------------|\n"

    for _, row in predictions.iterrows():
        date_str = row['ds'].strftime("%Y-%m-%d")
        regime_name = regime_names.get(row['regime'], f"Regime {row['regime']}")
        conf = row['regime_probability']
        log_entry += f"| {date_str} | {regime_name} | {conf:.3f} |\n"

    log_entry += "\n---\n"

    # Append to file
    output_path = Path(output_file)

    if output_path.exists():
        with open(output_path, 'r') as f:
            existing_content = f.read()
    else:
        existing_content = "# Daily Market Regime Predictions Log\n\n"
        existing_content += "This file tracks daily regime forecasts from the MarketPulse system.\n"

    with open(output_path, 'w') as f:
        f.write(existing_content + log_entry)

    print(f"   ✅ Logged {len(predictions)} predictions to {output_file}")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Log daily predictions")
    parser.add_argument("--output", default="DAILY_PREDICTIONS.md", help="Output markdown file")

    args = parser.parse_args()

    success = log_daily_predictions(args.output)

    if success:
        print(f"\n✅ Daily predictions logged successfully!")
    else:
        print(f"\n❌ Failed to log daily predictions")
        exit(1)
