#!/usr/bin/env python3
"""
Validate Inference Accuracy
Compares forecasted raw features vs actual values, then checks regime predictions
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

def load_forecast_data():
    """Load the most recent forecast run"""
    forecast_dir = BASE_DIR / "outputs" / "inference"

    # Get most recent raw forecasts
    raw_files = sorted(forecast_dir.glob("raw_forecasts_*.parquet"))
    if not raw_files:
        print("❌ No forecast files found")
        return None

    latest_raw = raw_files[-1]
    print(f"Loading forecasts from: {latest_raw.name}")
    return pd.read_parquet(latest_raw)

def load_actual_data(feature_name):
    """Load actual fetched data for a feature"""
    data_path = BASE_DIR / "outputs" / "fetched" / "cleaned" / f"{feature_name}.parquet"

    if not data_path.exists():
        return None

    df = pd.read_parquet(data_path)

    # Standardize format
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.reset_index()
        date_col = df.columns[0]
        value_col = df.columns[1] if len(df.columns) > 1 else feature_name
    else:
        date_col = 'date' if 'date' in df.columns else 'ds'
        value_col = feature_name if feature_name in df.columns else 'value'

    df = df.rename(columns={date_col: "ds", value_col: "value"})
    df = df[["ds", "value"]].dropna().sort_values("ds")

    return df

def compare_forecasts_vs_actuals(forecast_df):
    """Compare forecasted values vs actual values for overlapping dates"""

    print("\n" + "="*70)
    print("FORECAST ACCURACY ANALYSIS")
    print("="*70)
    print()

    # Get unique features and dates
    features = forecast_df['feature'].unique()

    comparison_results = []

    for feature in features:
        # Get forecasts for this feature
        feature_forecasts = forecast_df[forecast_df['feature'] == feature].copy()

        # Get actual data
        actual_df = load_actual_data(feature)

        if actual_df is None:
            continue

        # Find overlapping dates
        feature_forecasts['ds'] = pd.to_datetime(feature_forecasts['ds'])
        actual_df['ds'] = pd.to_datetime(actual_df['ds'])

        # Merge on date
        merged = feature_forecasts.merge(
            actual_df,
            on='ds',
            how='inner',
            suffixes=('_forecast', '_actual')
        )

        if len(merged) == 0:
            continue

        # Calculate errors
        merged['error'] = merged['forecast_value'] - merged['value']
        merged['pct_error'] = (merged['error'] / merged['value'].abs()) * 100
        merged['abs_pct_error'] = merged['pct_error'].abs()

        # Store results
        for _, row in merged.iterrows():
            comparison_results.append({
                'feature': feature,
                'date': row['ds'],
                'forecast': row['forecast_value'],
                'actual': row['value'],
                'error': row['error'],
                'pct_error': row['pct_error'],
                'abs_pct_error': row['abs_pct_error']
            })

    if not comparison_results:
        print("❌ No overlapping dates found between forecasts and actuals")
        return None

    results_df = pd.DataFrame(comparison_results)

    # Display summary
    print(f"Total validation points: {len(results_df)}")
    print(f"Features validated: {results_df['feature'].nunique()}")
    print(f"Date range: {results_df['date'].min().date()} to {results_df['date'].max().date()}")
    print()

    # Accuracy by feature
    print("FORECAST ACCURACY BY FEATURE:")
    print("-" * 70)

    feature_stats = results_df.groupby('feature').agg({
        'abs_pct_error': ['mean', 'median', 'min', 'max'],
        'date': 'count'
    }).round(2)

    feature_stats.columns = ['Mean APE %', 'Median APE %', 'Min APE %', 'Max APE %', 'N Points']
    feature_stats = feature_stats.sort_values('Mean APE %')

    print(feature_stats.to_string())
    print()

    # Overall statistics
    print("OVERALL FORECAST ACCURACY:")
    print("-" * 70)
    print(f"Mean Absolute Percentage Error: {results_df['abs_pct_error'].mean():.2f}%")
    print(f"Median Absolute Percentage Error: {results_df['abs_pct_error'].median():.2f}%")
    print(f"Features with APE < 5%: {(feature_stats['Mean APE %'] < 5).sum()} / {len(feature_stats)}")
    print(f"Features with APE < 10%: {(feature_stats['Mean APE %'] < 10).sum()} / {len(feature_stats)}")
    print()

    # Show worst predictions
    print("WORST PREDICTIONS (Top 10):")
    print("-" * 70)
    worst = results_df.nlargest(10, 'abs_pct_error')[['date', 'feature', 'forecast', 'actual', 'pct_error']]
    worst['date'] = worst['date'].dt.date
    worst['pct_error'] = worst['pct_error'].round(2)
    print(worst.to_string(index=False))
    print()

    return results_df

def validate_regime_predictions():
    """Compare regime predictions vs actual cluster assignments"""

    print("\n" + "="*70)
    print("REGIME PREDICTION VALIDATION")
    print("="*70)
    print()

    # Load regime forecasts
    forecast_dir = BASE_DIR / "outputs" / "inference"
    regime_files = sorted(forecast_dir.glob("regime_forecast_*.csv"))

    if not regime_files:
        print("❌ No regime forecast files found")
        return

    latest_regime = regime_files[-1]
    regime_forecast = pd.read_csv(latest_regime)
    regime_forecast['ds'] = pd.to_datetime(regime_forecast['ds'])

    print(f"Loaded regime forecasts from: {latest_regime.name}")

    # Load actual cluster assignments
    cluster_path = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"

    if not cluster_path.exists():
        print("❌ Cluster assignments not found")
        return

    actual_clusters = pd.read_parquet(cluster_path)

    # Index is the date
    if isinstance(actual_clusters.index, pd.DatetimeIndex):
        actual_clusters = actual_clusters.reset_index()
        actual_clusters.rename(columns={'index': 'ds'}, inplace=True)

    actual_clusters['ds'] = pd.to_datetime(actual_clusters['ds'])

    print(f"Actual regimes available through: {actual_clusters['ds'].max().date()}")
    print()

    # Find overlapping dates
    merged = regime_forecast.merge(
        actual_clusters[['ds', 'regime']],
        on='ds',
        how='inner',
        suffixes=('_forecast', '_actual')
    )

    if len(merged) == 0:
        print("❌ No overlapping dates between forecasts and actuals")
        return

    # Calculate accuracy
    merged['correct'] = (merged['regime_forecast'] == merged['regime_actual'])
    accuracy = merged['correct'].mean() * 100

    print(f"VALIDATION SET: {len(merged)} overlapping dates")
    print("-" * 70)
    print()

    for _, row in merged.iterrows():
        status = "✅" if row['correct'] else "❌"
        conf = row['regime_probability'] * 100
        print(f"{row['ds'].date()}: Predicted={row['regime_forecast']} ({conf:.1f}%), "
              f"Actual={row['regime_actual']} {status}")

    print()
    print(f"Validation Accuracy: {accuracy:.1f}% ({merged['correct'].sum()}/{len(merged)} correct)")
    print()

    # Confusion analysis
    if not merged['correct'].all():
        print("MISCLASSIFICATIONS:")
        print("-" * 70)
        misclass = merged[~merged['correct']]

        for _, row in misclass.iterrows():
            print(f"  {row['ds'].date()}: Predicted Regime {row['regime_forecast']} "
                  f"(conf: {row['regime_probability']*100:.1f}%) → "
                  f"Actually Regime {row['regime_actual']}")
        print()

def main():
    print("\n" + "="*70)
    print("INFERENCE VALIDATION SUITE")
    print("Comparing Forecasted vs Actual Data")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Compare raw feature forecasts vs actuals
    forecast_df = load_forecast_data()

    if forecast_df is not None:
        comparison_df = compare_forecasts_vs_actuals(forecast_df)

    # Step 2: Validate regime predictions
    validate_regime_predictions()

    print("="*70)
    print("VALIDATION COMPLETE")
    print("="*70)
    print()

if __name__ == "__main__":
    main()
