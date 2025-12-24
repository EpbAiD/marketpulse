#!/usr/bin/env python3
"""
Proper Inference Validation
Compares regime predictions from actual data vs forecasted data
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from data_agent.engineer import engineer_features
from classification_agent.classifier import predict_regimes_from_forecast

def load_actual_raw_features(validation_dates):
    """
    Load actual raw feature values for validation dates
    Returns dataframe in same format as forecast data
    """
    print("\n" + "="*70)
    print("LOADING ACTUAL RAW FEATURES")
    print("="*70)
    print()

    actual_features = []

    # Get list of all raw features
    raw_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"

    for feature_file in raw_dir.glob("*.parquet"):
        feature_name = feature_file.stem

        df = pd.read_parquet(feature_file)

        # Standardize format
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            date_col = df.columns[0]
            value_col = df.columns[1] if len(df.columns) > 1 else feature_name
        else:
            date_col = 'date' if 'date' in df.columns else 'ds'
            value_col = feature_name if feature_name in df.columns else 'value'

        df = df.rename(columns={date_col: "ds", value_col: "value"})
        df['ds'] = pd.to_datetime(df['ds'])

        # Filter to validation dates
        df_filtered = df[df['ds'].isin(validation_dates)].copy()

        if len(df_filtered) > 0:
            df_filtered['feature'] = feature_name
            actual_features.append(df_filtered[['ds', 'feature', 'value']])
            print(f"  {feature_name}: {len(df_filtered)} validation points")

    if not actual_features:
        return None

    actual_df = pd.concat(actual_features, ignore_index=True)
    print(f"\n✅ Loaded {len(actual_df)} actual feature values")
    print(f"   Features: {actual_df['feature'].nunique()}")
    print(f"   Date range: {actual_df['ds'].min().date()} to {actual_df['ds'].max().date()}")

    return actual_df


def load_forecasted_raw_features(validation_dates):
    """
    Load forecasted raw feature values for validation dates
    """
    print("\n" + "="*70)
    print("LOADING FORECASTED RAW FEATURES")
    print("="*70)
    print()

    forecast_dir = BASE_DIR / "outputs" / "inference"
    raw_files = sorted(forecast_dir.glob("raw_forecasts_*.parquet"))

    if not raw_files:
        print("❌ No forecast files found")
        return None

    latest_raw = raw_files[-1]
    print(f"Loading forecasts from: {latest_raw.name}")

    forecast_df = pd.read_parquet(latest_raw)
    forecast_df['ds'] = pd.to_datetime(forecast_df['ds'])

    # Filter to validation dates
    forecast_df = forecast_df[forecast_df['ds'].isin(validation_dates)].copy()

    # Rename to match actual data format
    forecast_df = forecast_df.rename(columns={'forecast_value': 'value'})

    print(f"✅ Loaded {len(forecast_df)} forecasted feature values")
    print(f"   Features: {forecast_df['feature'].nunique()}")
    print(f"   Date range: {forecast_df['ds'].min().date()} to {forecast_df['ds'].max().date()}")

    return forecast_df


def engineer_and_predict(raw_features_df, label="Actual"):
    """
    Engineer features from raw data and predict regimes
    """
    print("\n" + "="*70)
    print(f"ENGINEERING FEATURES FROM {label.upper()} DATA")
    print("="*70)
    print()

    # Engineer features
    from data_agent.engineer import engineer_forecasted_features

    engineered_df = engineer_forecasted_features(raw_features_df)

    print(f"✅ Engineered {len(engineered_df)} feature rows")
    print(f"   Features: {len(engineered_df.columns) - 1} (excluding 'ds')")
    print(f"   Dates: {engineered_df['ds'].nunique()}")
    print(f"   NaN percentage: {engineered_df.isna().sum().sum() / (engineered_df.shape[0] * engineered_df.shape[1]) * 100:.2f}%")

    # Predict regimes
    print(f"\nPredicting regimes from {label.lower()} features...")
    regime_df = predict_regimes_from_forecast(engineered_df)

    print(f"✅ Regime predictions generated: {len(regime_df)} rows")

    return engineered_df, regime_df


def compare_regime_predictions(actual_regimes, forecast_regimes):
    """
    Compare regime predictions from actual vs forecasted data
    """
    print("\n" + "="*70)
    print("COMPARING REGIME PREDICTIONS")
    print("="*70)
    print()

    # Merge on date
    comparison = actual_regimes.merge(
        forecast_regimes,
        on='ds',
        how='inner',
        suffixes=('_actual', '_forecast')
    )

    if len(comparison) == 0:
        print("❌ No overlapping dates found")
        return None

    # Compare regimes
    comparison['match'] = (comparison['regime_actual'] == comparison['regime_forecast'])
    accuracy = comparison['match'].mean() * 100

    print(f"VALIDATION SET: {len(comparison)} overlapping dates")
    print("-" * 70)
    print()

    print("DATE       | ACTUAL           | FORECAST         | MATCH")
    print("-" * 70)

    for _, row in comparison.iterrows():
        status = "✅" if row['match'] else "❌"
        actual_conf = row.get('regime_probability_actual', 0) * 100
        forecast_conf = row.get('regime_probability_forecast', 0) * 100

        print(f"{row['ds'].date()} | Regime {int(row['regime_actual'])} ({actual_conf:.1f}%) | "
              f"Regime {int(row['regime_forecast'])} ({forecast_conf:.1f}%) | {status}")

    print()
    print(f"VALIDATION ACCURACY: {accuracy:.1f}% ({comparison['match'].sum()}/{len(comparison)} correct)")
    print()

    # Analyze mismatches
    if not comparison['match'].all():
        print("MISMATCHES:")
        print("-" * 70)
        mismatches = comparison[~comparison['match']]

        for _, row in mismatches.iterrows():
            print(f"  {row['ds'].date()}: Actual Regime {int(row['regime_actual'])} "
                  f"→ Forecast predicted Regime {int(row['regime_forecast'])}")
            print(f"    Actual confidence: {row.get('regime_probability_actual', 0)*100:.1f}%")
            print(f"    Forecast confidence: {row.get('regime_probability_forecast', 0)*100:.1f}%")
        print()

    return comparison


def compare_engineered_features(actual_features, forecast_features, top_n=10):
    """
    Compare engineered features from actual vs forecasted data
    """
    print("\n" + "="*70)
    print("COMPARING ENGINEERED FEATURES")
    print("="*70)
    print()

    # Get common dates and features
    common_dates = set(actual_features['ds']).intersection(set(forecast_features['ds']))
    common_features = set(actual_features.columns).intersection(set(forecast_features.columns))
    common_features.discard('ds')

    print(f"Common dates: {len(common_dates)}")
    print(f"Common features: {len(common_features)}")
    print()

    # Calculate differences for each feature
    feature_diffs = []

    for feature in common_features:
        actual_vals = actual_features[actual_features['ds'].isin(common_dates)].set_index('ds')[feature]
        forecast_vals = forecast_features[forecast_features['ds'].isin(common_dates)].set_index('ds')[feature]

        # Align by date
        aligned = pd.DataFrame({
            'actual': actual_vals,
            'forecast': forecast_vals
        }).dropna()

        if len(aligned) > 0:
            mae = (aligned['actual'] - aligned['forecast']).abs().mean()
            mape = ((aligned['actual'] - aligned['forecast']).abs() / aligned['actual'].abs().replace(0, np.nan)).mean() * 100

            feature_diffs.append({
                'feature': feature,
                'mae': mae,
                'mape': mape,
                'n_points': len(aligned)
            })

    if not feature_diffs:
        print("❌ No comparable features found")
        return None

    diff_df = pd.DataFrame(feature_diffs).sort_values('mae', ascending=False)

    print(f"TOP {top_n} FEATURES WITH LARGEST DIFFERENCES:")
    print("-" * 70)
    print(diff_df.head(top_n).to_string(index=False))
    print()

    print(f"OVERALL STATISTICS:")
    print(f"  Mean MAE: {diff_df['mae'].mean():.4f}")
    print(f"  Median MAE: {diff_df['mae'].median():.4f}")
    print(f"  Mean MAPE: {diff_df['mape'].mean():.2f}%")
    print(f"  Features with MAPE < 5%: {(diff_df['mape'] < 5).sum()} / {len(diff_df)}")
    print()

    return diff_df


def main():
    print("\n" + "="*70)
    print("PROPER INFERENCE VALIDATION")
    print("Actual Data vs Forecasted Data Regime Prediction Comparison")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Determine validation dates (dates where we have both actual and forecast)
    forecast_dir = BASE_DIR / "outputs" / "inference"
    raw_files = sorted(forecast_dir.glob("raw_forecasts_*.parquet"))

    if not raw_files:
        print("\n❌ No forecast files found")
        return

    forecast_df_temp = pd.read_parquet(raw_files[-1])
    forecast_df_temp['ds'] = pd.to_datetime(forecast_df_temp['ds'])
    forecast_dates = set(forecast_df_temp['ds'].unique())

    # Check which dates we have actual data for
    vix_df = pd.read_parquet(BASE_DIR / "outputs" / "fetched" / "cleaned" / "VIX.parquet")
    if isinstance(vix_df.index, pd.DatetimeIndex):
        actual_dates = set(vix_df.index)
    else:
        actual_dates = set(pd.to_datetime(vix_df['ds'] if 'ds' in vix_df.columns else vix_df['date']))

    validation_dates = sorted(forecast_dates.intersection(actual_dates))

    print(f"\nValidation dates (where we have both actual and forecast): {len(validation_dates)}")
    for date in validation_dates:
        print(f"  - {date.date()}")

    if not validation_dates:
        print("\n❌ No overlapping dates between actual and forecast data")
        print("   This is expected if forecasts are for future dates only")
        return

    # Step 2: Load actual raw features for validation dates
    actual_raw = load_actual_raw_features(validation_dates)

    if actual_raw is None:
        print("\n❌ Failed to load actual raw features")
        return

    # Step 3: Load forecasted raw features for validation dates
    forecast_raw = load_forecasted_raw_features(validation_dates)

    if forecast_raw is None:
        print("\n❌ Failed to load forecasted raw features")
        return

    # Step 4: Engineer features and predict regimes from ACTUAL data
    actual_engineered, actual_regimes = engineer_and_predict(actual_raw, label="Actual")

    # Step 5: Engineer features and predict regimes from FORECAST data
    forecast_engineered, forecast_regimes = engineer_and_predict(forecast_raw, label="Forecast")

    # Step 6: Compare engineered features (skip if error - not critical for validation)
    try:
        feature_comparison = compare_engineered_features(actual_engineered, forecast_engineered)
    except Exception as e:
        print(f"\n⚠️  Skipping feature comparison due to error: {e}")
        feature_comparison = None

    # Step 7: Compare regime predictions
    regime_comparison = compare_regime_predictions(actual_regimes, forecast_regimes)

    # Save results
    if regime_comparison is not None:
        output_path = BASE_DIR / "outputs" / "inference" / f"validation_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        regime_comparison.to_csv(output_path, index=False)
        print(f"📁 Validation results saved to: {output_path}")

    print("\n" + "="*70)
    print("VALIDATION COMPLETE")
    print("="*70)
    print()


if __name__ == "__main__":
    main()
