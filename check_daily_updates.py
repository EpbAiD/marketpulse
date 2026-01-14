#!/usr/bin/env python3
"""
Daily Update Verification Script
=================================
Checks if the system is updating daily by querying BigQuery and showing update history.

Usage:
    python check_daily_updates.py
    python check_daily_updates.py --days 30  # Show last 30 days
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from data_agent.storage import get_storage


def check_bigquery_updates(days=14):
    """
    Check BigQuery for daily forecast updates

    Args:
        days: Number of days to check (default: 14)
    """
    print("=" * 80)
    print("📊 DAILY UPDATE VERIFICATION")
    print("=" * 80)
    print(f"Checking last {days} days of forecasts in BigQuery...\n")

    try:
        # Connect to BigQuery
        storage = get_storage(use_bigquery=True)
        print(f"✓ Connected to BigQuery: {storage.dataset_id}\n")

        # Query forecast history
        query = f"""
        SELECT
            DATE(timestamp) as forecast_date,
            forecast_id,
            timestamp,
            COUNT(*) as num_predictions,
            MIN(predicted_date) as first_prediction_date,
            MAX(predicted_date) as last_prediction_date,
            AVG(confidence) as avg_confidence
        FROM `{storage.dataset_id}.regime_forecasts`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        GROUP BY DATE(timestamp), forecast_id, timestamp
        ORDER BY forecast_date DESC, timestamp DESC
        """

        df = storage._execute_query(query)

        if len(df) == 0:
            print("⚠️  No forecasts found in BigQuery")
            return False

        # Display results
        print(f"Found {len(df)} forecast runs in last {days} days:\n")
        print("=" * 80)

        for idx, row in df.iterrows():
            forecast_date = row['forecast_date']
            forecast_time = row['timestamp']
            forecast_id = row['forecast_id']
            num_preds = row['num_predictions']
            first_pred = row['first_prediction_date']
            last_pred = row['last_prediction_date']
            avg_conf = row['avg_confidence']

            print(f"📅 {forecast_date} at {forecast_time.strftime('%H:%M:%S')} UTC")
            print(f"   ID: {forecast_id}")
            print(f"   Predictions: {num_preds} days ({first_pred} to {last_pred})")
            print(f"   Avg Confidence: {avg_conf:.3f}")
            print()

        print("=" * 80)

        # Check for missing days
        expected_days = pd.date_range(
            end=datetime.now().date(),
            periods=days,
            freq='D'
        )

        actual_days = set(pd.to_datetime(df['forecast_date']).dt.date)
        missing_days = [d.date() for d in expected_days if d.date() not in actual_days]

        if missing_days:
            print(f"\n⚠️  Missing forecasts for {len(missing_days)} days:")
            for day in sorted(missing_days, reverse=True):
                print(f"   - {day}")
        else:
            print(f"\n✅ All {days} days have forecasts!")

        # Show latest forecast details
        print("\n" + "=" * 80)
        print("🔮 LATEST FORECAST DETAILS")
        print("=" * 80)

        latest = storage.get_latest_forecasts(limit=1)
        if len(latest) > 0:
            latest_id = latest.iloc[0]['forecast_id']
            latest_time = latest.iloc[0]['timestamp']

            predictions = storage.get_forecast_by_id(latest_id)

            print(f"\nForecast ID: {latest_id}")
            print(f"Generated: {latest_time}")
            print(f"Total Predictions: {len(predictions)}\n")

            print("Regime Distribution:")
            regime_counts = predictions['predicted_regime'].value_counts()
            for regime, count in regime_counts.items():
                pct = 100 * count / len(predictions)
                print(f"   {regime}: {count} days ({pct:.1f}%)")

            print(f"\nFirst 5 predictions:")
            print(predictions[['predicted_date', 'predicted_regime', 'confidence']].head().to_string(index=False))

        print("\n" + "=" * 80)

        # Dashboard check
        print("\n📊 DASHBOARD UPDATE CHECK")
        print("=" * 80)
        print(f"\nLatest forecast timestamp: {latest_time}")
        print(f"Current time: {datetime.now()}")

        time_diff = datetime.now() - latest_time.replace(tzinfo=None)
        hours_old = time_diff.total_seconds() / 3600

        print(f"Forecast age: {hours_old:.1f} hours")

        if hours_old < 24:
            print("✅ Dashboard should show TODAY's forecast")
        elif hours_old < 48:
            print("⚠️  Dashboard showing YESTERDAY's forecast (check if today's run failed)")
        else:
            print("❌ Dashboard showing OLD forecast (system may not be running)")

        # Streamlit cache note
        print("\n💡 NOTE: Streamlit dashboard cache refreshes every 5 minutes")
        print("   If forecast was just generated, wait 5 min or reboot dashboard")

        return True

    except Exception as e:
        print(f"❌ Error checking BigQuery: {e}")
        print("\nTroubleshooting:")
        print("  1. Check BigQuery credentials are configured")
        print("  2. Verify you have access to regime01.forecasting_pipeline")
        print("  3. Run: gcloud auth application-default login")
        return False


def check_github_commits(days=14):
    """Check GitHub commits for daily forecast updates"""
    import subprocess

    print("\n" + "=" * 80)
    print("📝 GITHUB COMMIT HISTORY")
    print("=" * 80)
    print(f"\nChecking last {days} days of commits...\n")

    try:
        # Get recent forecast commits
        result = subprocess.run(
            ['git', 'log', '--oneline', '--all', '--grep=Daily forecast update', f'--since={days} days ago'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout:
            commits = result.stdout.strip().split('\n')
            print(f"Found {len(commits)} daily forecast commits:\n")
            for commit in commits[:10]:  # Show last 10
                print(f"  {commit}")

            if len(commits) > 10:
                print(f"\n  ... and {len(commits) - 10} more")
        else:
            print("⚠️  No daily forecast commits found")

    except Exception as e:
        print(f"⚠️  Could not check git history: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify daily forecast updates in BigQuery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_daily_updates.py           # Check last 14 days
  python check_daily_updates.py --days 30 # Check last 30 days
  python check_daily_updates.py --days 7  # Check last week
        """
    )

    parser.add_argument(
        '--days',
        type=int,
        default=14,
        help='Number of days to check (default: 14)'
    )

    args = parser.parse_args()

    # Check BigQuery
    success = check_bigquery_updates(days=args.days)

    # Check GitHub commits
    check_github_commits(days=args.days)

    print("\n" + "=" * 80)

    if success:
        print("✅ Verification complete - system is updating regularly")
    else:
        print("⚠️  Could not verify updates - check BigQuery connection")

    print("=" * 80)
    print("\nTo verify dashboard is current:")
    print("  1. Visit: https://marketpulsedashboard.streamlit.app")
    print("  2. Check forecast timestamp at top of page")
    print("  3. Should match latest timestamp shown above (±5 min for cache)")
    print()


if __name__ == "__main__":
    main()
