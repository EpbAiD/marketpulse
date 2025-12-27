#!/usr/bin/env python3
"""
Regime Shift Alert System

Detects regime shifts by comparing consecutive forecasts (Day N vs Day N+1).
Storage-agnostic - works with BigQuery or local files.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pandas as pd
from datetime import datetime
from collections import Counter
from typing import Optional, Dict, List
from data_agent.storage import get_storage


# Regime names for display
REGIME_NAMES = {
    0: "Consolidation",
    1: "Expansion",
    2: "Compression"
}


class AlertSystem:
    """Detect regime shifts between consecutive forecasts"""

    def __init__(self, storage=None):
        """Initialize alert system with storage backend"""
        self.storage = storage if storage else get_storage()

    def get_latest_two_forecasts(self) -> tuple:
        """
        Get the two most recent forecasts

        Returns:
            (previous_forecast_id, latest_forecast_id) or (None, None)
        """
        try:
            # Check if storage has the method (BigQuery)
            if hasattr(self.storage, 'get_latest_forecasts'):
                latest_forecasts = self.storage.get_latest_forecasts(limit=2)
                if len(latest_forecasts) < 2:
                    return None, None

                return (
                    latest_forecasts.iloc[1]['forecast_id'],  # Previous (older)
                    latest_forecasts.iloc[0]['forecast_id']   # Latest (newer)
                )
            else:
                # Local storage - check CSV files
                import glob
                forecast_files = sorted(
                    glob.glob('outputs/inference/regime_forecast_*.csv'),
                    key=os.path.getmtime,
                    reverse=True
                )
                if len(forecast_files) < 2:
                    return None, None

                # Use filenames as IDs
                from pathlib import Path
                return (
                    Path(forecast_files[1]).stem,  # Previous
                    Path(forecast_files[0]).stem   # Latest
                )
        except Exception as e:
            print(f"  ⚠️ Could not get latest forecasts: {e}")
            return None, None

    def get_forecast_predictions(self, forecast_id: str) -> Optional[pd.DataFrame]:
        """Get all predictions for a given forecast"""
        try:
            if hasattr(self.storage, 'get_forecast_by_id'):
                return self.storage.get_forecast_by_id(forecast_id)
            else:
                # Local storage - read CSV file
                csv_path = f'outputs/inference/{forecast_id}.csv'
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path)
                    df['ds'] = pd.to_datetime(df['ds'])
                    return df
                return None
        except Exception as e:
            print(f"  ⚠️ Could not load forecast {forecast_id}: {e}")
            return None

    def detect_shifts_by_date(
        self,
        previous_df: pd.DataFrame,
        latest_df: pd.DataFrame
    ) -> List[Dict]:
        """
        Compare forecasts date-by-date for overlapping dates

        Logic:
        - Day N forecast: Predicts Day N to Day N+9 (10 days)
        - Day N+1 forecast: Predicts Day N+1 to Day N+10 (10 days)
        - Overlapping dates: Day N+1 to Day N+9 (9 days)
        - For each overlapping date, check if regime changed

        Args:
            previous_df: Previous day's forecast
            latest_df: Latest day's forecast

        Returns:
            List of shifts detected with date-specific information
        """
        # Ensure date columns are datetime
        previous_df = previous_df.copy()
        latest_df = latest_df.copy()
        previous_df['ds'] = pd.to_datetime(previous_df['ds'])
        latest_df['ds'] = pd.to_datetime(latest_df['ds'])

        # Merge on date to find overlapping dates
        merged = pd.merge(
            previous_df[['ds', 'regime', 'regime_probability']],
            latest_df[['ds', 'regime', 'regime_probability']],
            on='ds',
            suffixes=('_prev', '_latest'),
            how='inner'  # Only overlapping dates
        )

        # Detect shifts (where regime changed for same date)
        shifts = []
        for _, row in merged.iterrows():
            if int(row['regime_prev']) != int(row['regime_latest']):
                shifts.append({
                    'date': str(row['ds'].date()),
                    'previous_regime': int(row['regime_prev']),
                    'latest_regime': int(row['regime_latest']),
                    'previous_confidence': float(row['regime_probability_prev']),
                    'latest_confidence': float(row['regime_probability_latest'])
                })

        return shifts, len(merged)  # Return shifts and overlap count

    def check_for_alerts(
        self,
        min_confidence: float = 0.6
    ) -> Dict:
        """
        Check for regime shift alerts by comparing consecutive forecasts date-by-date

        Args:
            min_confidence: Minimum confidence to trigger alert

        Returns:
            Dict with alert status and details
        """
        # Get latest two forecasts
        previous_id, latest_id = self.get_latest_two_forecasts()

        if not previous_id or not latest_id:
            return {
                'alert': False,
                'message': 'Insufficient forecasts for comparison',
                'shifts': []
            }

        # Get predictions
        previous_forecast = self.get_forecast_predictions(previous_id)
        latest_forecast = self.get_forecast_predictions(latest_id)

        if previous_forecast is None or latest_forecast is None:
            return {
                'alert': False,
                'message': 'Could not load forecast data',
                'shifts': []
            }

        # Detect shifts date-by-date
        shifts, overlap_count = self.detect_shifts_by_date(
            previous_forecast,
            latest_forecast
        )

        # Filter by confidence
        significant_shifts = [
            s for s in shifts
            if s['latest_confidence'] >= min_confidence
        ]

        result = {
            'alert': len(significant_shifts) > 0,
            'message': f"{'Regime shift detected' if significant_shifts else 'No regime shifts'} (date-by-date comparison)",
            'shifts': significant_shifts,
            'previous_forecast_id': previous_id,
            'latest_forecast_id': latest_id,
            'min_confidence': min_confidence,
            'overlapping_dates': overlap_count,
            'timestamp': datetime.now().isoformat()
        }

        return result


def run_alert_check(period: str = 'daily', quiet: bool = False) -> Dict:
    """
    Run alert check and optionally print results

    Args:
        period: 'daily' (date-by-date comparison) - legacy parameter kept for compatibility
        quiet: If True, suppress output

    Returns:
        Dict with alert results
    """
    system = AlertSystem()
    result = system.check_for_alerts()

    if not quiet:
        print("\n" + "=" * 80)
        print(f"REGIME SHIFT ALERT SYSTEM (DATE-BY-DATE)")
        print("=" * 80)
        print(f"\nTimestamp: {result['timestamp']}")
        print(f"Overlapping dates analyzed: {result.get('overlapping_dates', 0)}")

        if result['alert']:
            print(f"\n⚠️  REGIME SHIFT DETECTED")
            print(f"\n{len(result['shifts'])} shift(s) found:")
            for shift in result['shifts']:
                prev_name = REGIME_NAMES.get(shift['previous_regime'], 'Unknown')
                new_name = REGIME_NAMES.get(shift['latest_regime'], 'Unknown')

                print(f"\n  Date: {shift['date']}")
                print(f"  Change: {prev_name} → {new_name}")
                print(f"  Previous confidence: {shift['previous_confidence']:.1%}")
                print(f"  Latest confidence: {shift['latest_confidence']:.1%}")
        else:
            print(f"\n✓ No regime shifts detected")

        print("\n" + "=" * 80 + "\n")

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Check for regime shift alerts')
    parser.add_argument('--period', choices=['weekly', 'biweekly'], default='weekly')
    parser.add_argument('--quiet', action='store_true')
    args = parser.parse_args()

    result = run_alert_check(period=args.period, quiet=args.quiet)
