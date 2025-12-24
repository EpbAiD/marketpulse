#!/usr/bin/env python3
"""
Backtest Inference Validation
Simulates forecasting from an earlier date to validate against known actual data
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from data_agent.engineer import engineer_forecasted_features
from classification_agent.classifier import predict_regimes_from_forecast
from neuralforecast import NeuralForecast

def simulate_forecast_from_date(cutoff_date, horizon=10):
    """
    Simulate forecasting as if we're at cutoff_date
    Load models and historical data up to cutoff_date, then forecast
    """
    print("\n" + "="*70)
    print(f"SIMULATING FORECAST FROM {cutoff_date.date()}")
    print("="*70)
    print(f"Horizon: {horizon} business days")
    print()

    import yaml

    # Load feature configuration
    config_path = BASE_DIR / "configs" / "features_config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Collect all features
    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        features = config[cadence].get('features', [])
        for feature in features:
            all_features.append({
                'name': feature,
                'cadence': cadence,
                'horizon': config[cadence]['horizon']
            })

    print(f"Features to forecast: {len(all_features)}")

    all_forecasts = []

    for idx, feature_info in enumerate(all_features, 1):
        feature = feature_info['name']
        cadence = feature_info['cadence']

        print(f"\n[{idx}/{len(all_features)}] Forecasting {feature} ({cadence})...")

        try:
            # Load model
            model_dir = BASE_DIR / "outputs" / "forecasting" / "models" / feature
            nf_bundle_path = model_dir / "nf_bundle_v1"

            if not nf_bundle_path.exists():
                print(f"  ⚠️  Model not found, skipping...")
                continue

            # Load historical data UP TO cutoff_date
            data_path = BASE_DIR / "outputs" / "fetched" / "cleaned" / f"{feature}.parquet"
            df_raw = pd.read_parquet(data_path)

            # Standardize format
            if isinstance(df_raw.index, pd.DatetimeIndex):
                df_raw = df_raw.reset_index()
                date_col = df_raw.columns[0]
                value_col = df_raw.columns[1] if len(df_raw.columns) > 1 else feature
            else:
                date_col = 'date' if 'date' in df_raw.columns else 'ds'
                value_col = feature if feature in df_raw.columns else 'value'

            df = df_raw.rename(columns={date_col: "ds", value_col: "y"})
            df["unique_id"] = feature
            df["ds"] = pd.to_datetime(df["ds"])
            df = df[["unique_id", "ds", "y"]].dropna().sort_values("ds").reset_index(drop=True)

            # Filter to cutoff date
            df = df[df['ds'] <= cutoff_date].copy()

            if len(df) == 0:
                print(f"  ⚠️  No data before cutoff date, skipping...")
                continue

            last_date = df['ds'].max()
            print(f"  Historical data through: {last_date.date()}")

            # Forward-fill to cutoff_date if needed (for monthly/weekly)
            if last_date < cutoff_date and cadence in ['monthly', 'weekly']:
                print(f"  📅 Forward-filling from {last_date.date()} to {cutoff_date.date()}")

                last_value = df['y'].iloc[-1]
                fill_dates = pd.date_range(
                    start=last_date + pd.Timedelta(days=1),
                    end=cutoff_date,
                    freq='B'
                )

                for fill_date in fill_dates:
                    df = pd.concat([df, pd.DataFrame({
                        'unique_id': [feature],
                        'ds': [fill_date],
                        'y': [last_value]
                    })], ignore_index=True)

                df = df.sort_values('ds').reset_index(drop=True)

            # Load and run model
            nf = NeuralForecast.load(path=str(nf_bundle_path))
            forecast = nf.predict(df=df)

            # Extract median forecasts
            forecast_cols = [col for col in forecast.columns if 'median' in col.lower()]

            if forecast_cols:
                median_preds = forecast[forecast_cols].mean(axis=1).values

                # Generate forecast dates (business days)
                forecast_dates = pd.date_range(
                    start=cutoff_date + pd.Timedelta(days=1),
                    periods=horizon,
                    freq='B'
                )

                # Store forecasts
                for date, value in zip(forecast_dates[:horizon], median_preds[:horizon]):
                    all_forecasts.append({
                        'ds': date,
                        'feature': feature,
                        'forecast_value': value
                    })

                print(f"  ✅ Generated {len(forecast_dates[:horizon])} forecasts")
            else:
                print(f"  ⚠️  No median predictions found")

        except Exception as e:
            print(f"  ❌ Error: {e}")
            continue

    if not all_forecasts:
        print("\n❌ No forecasts generated")
        return None

    forecast_df = pd.DataFrame(all_forecasts)
    print(f"\n✅ Simulated forecast complete: {len(forecast_df)} forecast points")
    print(f"   Features: {forecast_df['feature'].nunique()}")
    print(f"   Date range: {forecast_df['ds'].min().date()} to {forecast_df['ds'].max().date()}")

    return forecast_df


def load_actual_data_for_period(start_date, end_date):
    """
    Load actual raw feature values for a date range
    """
    print("\n" + "="*70)
    print(f"LOADING ACTUAL DATA: {start_date.date()} to {end_date.date()}")
    print("="*70)
    print()

    actual_features = []
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

        # Filter to date range
        df_filtered = df[(df['ds'] >= start_date) & (df['ds'] <= end_date)].copy()

        if len(df_filtered) > 0:
            df_filtered['feature'] = feature_name
            actual_features.append(df_filtered[['ds', 'feature', 'value']])
            print(f"  {feature_name}: {len(df_filtered)} data points")

    if not actual_features:
        return None

    actual_df = pd.concat(actual_features, ignore_index=True)
    print(f"\n✅ Loaded {len(actual_df)} actual feature values")
    print(f"   Features: {actual_df['feature'].nunique()}")

    return actual_df


def engineer_and_predict(raw_features_df, label="Data"):
    """
    Engineer features and predict regimes
    """
    print("\n" + "="*70)
    print(f"ENGINEERING & PREDICTING FROM {label.upper()}")
    print("="*70)
    print()

    # Engineer features
    engineered_df = engineer_forecasted_features(raw_features_df)

    print(f"✅ Engineered features: {len(engineered_df)} rows")
    print(f"   Feature columns: {len(engineered_df.columns) - 1}")
    print(f"   Dates: {engineered_df['ds'].nunique()}")

    # Predict regimes
    regime_df = predict_regimes_from_forecast(engineered_df)

    print(f"✅ Regime predictions: {len(regime_df)} rows")

    return engineered_df, regime_df


def compare_predictions(actual_regimes, forecast_regimes):
    """
    Compare regime predictions
    """
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
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
        print("❌ No overlapping dates")
        return None

    comparison['match'] = (comparison['regime_actual'] == comparison['regime_forecast'])
    accuracy = comparison['match'].mean() * 100

    print(f"Validation Set: {len(comparison)} overlapping dates")
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
        print()

    return comparison


def main():
    print("\n" + "="*70)
    print("BACKTEST INFERENCE VALIDATION")
    print("Simulating forecast from earlier date to validate against actual data")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Choose a cutoff date where we have data after it for validation
    # Let's use November 1, 2025 as cutoff, and validate Nov 2 - Nov 30
    cutoff_date = pd.Timestamp('2025-11-01')
    horizon = 10

    print(f"\nSimulation setup:")
    print(f"  Cutoff date: {cutoff_date.date()}")
    print(f"  Forecast horizon: {horizon} business days")
    print(f"  We will compare forecasts vs actual data for dates after cutoff")

    # Step 1: Simulate forecast from cutoff date
    forecast_df = simulate_forecast_from_date(cutoff_date, horizon=horizon)

    if forecast_df is None:
        print("\n❌ Failed to generate forecasts")
        return

    # Step 2: Load actual data for the forecast period
    forecast_start = forecast_df['ds'].min()
    forecast_end = forecast_df['ds'].max()

    actual_df = load_actual_data_for_period(forecast_start, forecast_end)

    if actual_df is None:
        print("\n❌ Failed to load actual data")
        return

    # Step 3: Engineer & predict from actual data
    actual_engineered, actual_regimes = engineer_and_predict(actual_df, label="Actual Data")

    # Step 4: Engineer & predict from forecast data
    forecast_engineered, forecast_regimes = engineer_and_predict(forecast_df, label="Forecasted Data")

    # Step 5: Compare predictions
    comparison = compare_predictions(actual_regimes, forecast_regimes)

    # Save results
    if comparison is not None:
        output_dir = BASE_DIR / "outputs" / "inference"
        output_path = output_dir / f"backtest_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        comparison.to_csv(output_path, index=False)
        print(f"📁 Results saved to: {output_path}")

    print("\n" + "="*70)
    print("BACKTEST VALIDATION COMPLETE")
    print("="*70)
    print()


if __name__ == "__main__":
    main()
