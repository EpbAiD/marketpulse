#!/usr/bin/env python3
"""
Forecast Validation Module

Validates forecasts by comparing forecasted FEATURE VALUES vs actual FEATURE VALUES
using SMAPE (Symmetric Mean Absolute Percentage Error).

This prevents false retraining triggers that occur when comparing regime labels directly.
"""

import os
import glob
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from .storage import get_storage


# SMAPE thresholds per feature — expert-informed, based on published forecasting benchmarks.
#
# Anchors:
#   Lewis (1982) universal scale: <10% highly accurate, 10-20% good, 20-50% reasonable, >50% inaccurate.
#   Asset-class benchmarks from peer-reviewed literature (published models achieve the low end;
#   we set our alarm at roughly 2-3x that so we fire only on genuine degradation, not on noise):
#     - S&P 500 / equity indices: deep-learning benchmarks reach 3-5% MAPE → threshold 10%
#     - Gold: LSTM/ARIMA best-in-class 3.7-4.9% → threshold 10%
#     - Crude oil: top models 1.5-5.5% (monthly up to 12%) → threshold 15%
#     - 10Y Treasury yield: ML benchmarks typically <5% → threshold 10%
#     - DXY dollar index: ML models 0.55-3% → threshold 8%
#     - VIX-family / short-vol: best diffusion ~4%, but 15-30% typical in practice due to
#         noise floor of implied vol → threshold 30% (VIX9D 40% — 9-day vol is noisier)
#     - Yield spreads: near-zero denominators inflate SMAPE → threshold 40%
#     - Financial-conditions indexes (NFCI): weekly, coarse-grained → threshold 30%
#     - Macro monthly (CPI, INDPRO, UNRATE): near-zero-noise series → threshold 10%
#
# Refresh policy (SR 11-7 aligned): retrain triggered when SMAPE exceeds threshold for
# 3 consecutive validations (event-based) OR annual mandatory refresh (time-based).
SMAPE_THRESHOLDS = {
    # Equity indices
    'GSPC': 10.0,
    'IXIC': 10.0,
    # Volatility complex
    'VIX': 30.0,
    'VIX9D': 40.0,
    'VIX3M': 25.0,
    # Rates
    'DGS10': 10.0,
    'TNX': 10.0,
    'DGS2': 10.0,
    'DGS3MO': 10.0,
    'DFF': 10.0,
    'T10Y2Y': 40.0,
    # Credit
    'HY_YIELD': 10.0,
    'IG_YIELD': 10.0,
    # Commodities
    'GOLD': 10.0,
    'COPPER': 12.0,
    'OIL': 15.0,
    # Currency
    'DXY': 8.0,
    'UUP': 8.0,
    # Financial conditions
    'NFCI': 30.0,
    # Macro (monthly)
    'CPI': 10.0,
    'INDPRO': 10.0,
    'UNRATE': 10.0,
    # Fallback
    '_default': 20.0,
}


def calculate_smape(actual: float, forecast: float) -> float:
    """
    Calculate SMAPE (Symmetric Mean Absolute Percentage Error)

    SMAPE = 100 * |actual - forecast| / ((|actual| + |forecast|) / 2)

    Returns:
        SMAPE value between 0-200
    """
    if pd.isna(actual) or pd.isna(forecast):
        return np.nan

    denominator = (abs(actual) + abs(forecast)) / 2.0

    if denominator == 0:
        return 0.0 if actual == forecast else 200.0

    smape = 100.0 * abs(actual - forecast) / denominator
    return min(smape, 200.0)


def load_forecasted_features(forecast_id: str) -> pd.DataFrame:
    """
    Load forecasted feature values from raw_forecasts_*.parquet file

    Args:
        forecast_id: Forecast identifier (e.g., 'forecast_20251219_001228')

    Returns:
        DataFrame with columns: date, feature, forecast_value
    """
    timestamp_str = forecast_id.replace('forecast_', '')

    # Try exact match first
    parquet_file = f"outputs/inference/raw_forecasts_{timestamp_str}.parquet"

    if not os.path.exists(parquet_file):
        # Fuzzy match (same date/hour/minute, ±5 seconds)
        date_hour_min = timestamp_str[:13]  # YYYYMMDD_HHMM
        pattern = f"outputs/inference/raw_forecasts_{date_hour_min}*.parquet"
        matches = glob.glob(pattern)

        if matches:
            parquet_file = matches[0]
        else:
            return pd.DataFrame()

    # Load parquet (format: ds, feature, forecast_value)
    df = pd.read_parquet(parquet_file)
    df['date'] = pd.to_datetime(df['ds']).dt.date

    return df[['date', 'feature', 'forecast_value']]


def validate_forecast(forecast_id: str, forecast_time, storage=None) -> Optional[Dict]:
    """
    Validate a single forecast by comparing feature values using SMAPE

    Args:
        forecast_id: Forecast identifier
        forecast_time: When forecast was generated
        storage: Storage backend (defaults to configured storage)

    Returns:
        Dict with validation metrics or None if validation fails
    """
    if storage is None:
        storage = get_storage()

    # Check if storage supports validation (BigQuery only for now)
    if not hasattr(storage, 'dataset_id'):
        print("  ⚠️ Validation only supported with BigQuery storage")
        return None

    # Load forecasted features from parquet
    forecasted_df = load_forecasted_features(forecast_id)

    if forecasted_df.empty:
        return None

    # Filter out future dates — actuals won't exist yet
    today = datetime.now().date()
    forecasted_df = forecasted_df[forecasted_df['date'] <= today]

    if forecasted_df.empty:
        print(f"  ℹ️ Skipping {forecast_id}: all predicted dates are in the future")
        return None

    # Get date range
    start_date = forecasted_df['date'].min()
    end_date = forecasted_df['date'].max()

    # Load actual features from storage
    query = f"""
        SELECT
            DATE(timestamp) as date,
            feature_name as feature,
            value as actual_value
        FROM `{storage.dataset_id}.raw_features`
        WHERE DATE(timestamp) BETWEEN '{start_date}' AND '{end_date}'
    """

    try:
        actual_df = storage._execute_query(query)
    except:
        return None

    if actual_df.empty:
        print(f"  ℹ️ Skipping {forecast_id}: no actual data available for forecasted date range")
        return None

    # Merge on (date, feature) — only keeps rows where both forecast and actual exist
    merged = forecasted_df.merge(actual_df, on=['date', 'feature'], how='inner')

    if merged.empty:
        print(f"  ℹ️ Skipping {forecast_id}: no overlapping dates between forecast and actuals")
        return None

    # Calculate SMAPE per feature
    feature_errors = {}
    feature_comparisons = {}

    for feature in merged['feature'].unique():
        feature_data = merged[merged['feature'] == feature]

        smapes = []
        for _, row in feature_data.iterrows():
            smape = calculate_smape(row['actual_value'], row['forecast_value'])
            if not pd.isna(smape):
                smapes.append(smape)

        if smapes:
            feature_errors[feature] = np.mean(smapes)
            feature_comparisons[feature] = len(smapes)

    if not feature_errors:
        return None

    # Calculate overall metrics
    avg_smape = np.mean(list(feature_errors.values()))

    # Identify critical features (exceed thresholds)
    critical_features = []
    for feature, smape in feature_errors.items():
        threshold = SMAPE_THRESHOLDS.get(feature, SMAPE_THRESHOLDS['_default'])
        if smape > threshold:
            critical_features.append({
                'feature': feature,
                'smape': smape,
                'threshold': threshold,
                'comparisons': feature_comparisons[feature]
            })

    # Retraining decision: >30% features exceed thresholds
    needs_retraining = len(critical_features) / len(feature_errors) > 0.3 if feature_errors else False

    return {
        'forecast_id': forecast_id,
        'forecast_generated_at': forecast_time,
        'total_comparisons': len(merged),
        'features_validated': len(feature_errors),
        'avg_smape': avg_smape,
        'feature_errors': feature_errors,
        'feature_comparisons': feature_comparisons,
        'critical_features': critical_features,
        'needs_retraining': needs_retraining
    }


def run_validation_analysis(storage=None) -> Dict:
    """
    Run complete validation analysis on all pending forecasts

    Args:
        storage: Storage backend (defaults to configured storage)

    Returns:
        Dict with metrics and validation results
    """
    if storage is None:
        storage = get_storage()

    # Check if storage supports validation (BigQuery only for now)
    if not hasattr(storage, 'dataset_id'):
        print("  ⚠️ Validation only supported with BigQuery storage")
        return {
            'metrics': {
                'total_forecasts': 0,
                'validated_forecasts': 0,
                'avg_smape': 0.0
            },
            'validation_results': []
        }

    # Get pending forecasts from storage
    # Only validate forecasts whose predicted dates have passed (actuals available)
    # Limit to last 30 days to avoid re-validating stale backlog
    query = f"""
        SELECT DISTINCT
            forecast_id,
            forecast_generated_at,
            MIN(predicted_date) as first_predicted_date,
            MAX(predicted_date) as last_predicted_date
        FROM `{storage.dataset_id}.regime_forecasts`
        WHERE validation_status IN ('PENDING', 'PARTIAL')
          AND predicted_date <= CURRENT_DATE()
          AND forecast_generated_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY forecast_id, forecast_generated_at
        HAVING MAX(predicted_date) <= CURRENT_DATE()
        ORDER BY forecast_generated_at DESC
        LIMIT 50
    """

    try:
        pending_forecasts = storage._execute_query(query)
    except:
        return {
            'metrics': {
                'total_forecasts': 0,
                'avg_smape': 0.0,
                'needs_retraining': False
            },
            'validations': []
        }

    if pending_forecasts.empty:
        return {
            'metrics': {
                'total_forecasts': 0,
                'avg_smape': 0.0,
                'needs_retraining': False
            },
            'validations': []
        }

    # Validate each forecast
    validation_results = []

    for _, forecast_row in pending_forecasts.iterrows():
        result = validate_forecast(
            forecast_row['forecast_id'],
            forecast_row['forecast_generated_at'],
            storage
        )
        if result:
            validation_results.append(result)

    if not validation_results:
        print(f"  ℹ️ No forecasts could be validated (all predicted dates may still be in the future)")
        return {
            'metrics': {
                'total_forecasts': 0,
                'avg_smape': 0.0,
                'needs_retraining': False
            },
            'validations': []
        }

    # Calculate aggregate metrics
    overall_avg_smape = np.mean([r['avg_smape'] for r in validation_results])
    forecasts_need_retraining = sum(1 for r in validation_results if r['needs_retraining'])
    needs_retraining = forecasts_need_retraining / len(validation_results) > 0.5

    # Save validation results to storage
    validation_data = []
    for result in validation_results:
        for feature, smape in result['feature_errors'].items():
            threshold = SMAPE_THRESHOLDS.get(feature, SMAPE_THRESHOLDS['_default'])
            validation_data.append({
                'validation_id': f"val_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(validation_data)}",
                'validation_timestamp': datetime.now(),
                'forecast_id': result['forecast_id'],
                'forecast_generated_at': result['forecast_generated_at'],
                'feature_name': feature,
                'avg_smape': smape,
                'smape_threshold': threshold,
                'exceeds_threshold': smape > threshold,
                'comparisons': result['feature_comparisons'][feature],
                'overall_avg_smape': overall_avg_smape,
                'needs_retraining': needs_retraining
            })

    if validation_data:
        storage.save_validation_results(validation_data)

    return {
        'metrics': {
            'total_forecasts': len(validation_results),
            'avg_smape': overall_avg_smape,
            'forecasts_need_retraining': forecasts_need_retraining,
            'needs_retraining': needs_retraining
        },
        'validations': validation_results
    }


if __name__ == "__main__":
    # Run validation when called directly
    print("\n" + "=" * 80)
    print("FORECAST VALIDATION (SMAPE-Based)")
    print("=" * 80 + "\n")

    result = run_validation_analysis()

    print(f"Total Forecasts Validated: {result['metrics']['total_forecasts']}")
    print(f"Average SMAPE: {result['metrics']['avg_smape']:.2f}%")
    print(f"Retraining Needed: {'YES' if result['metrics']['needs_retraining'] else 'NO'}")
    print("\n" + "=" * 80 + "\n")
