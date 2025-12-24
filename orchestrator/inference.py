#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
Inference Orchestrator for Regime Forecasting Pipeline
===========================================================
Coordinates the full inference pipeline:
1. Forecast raw features for next N days (forecasting_agent)
2. Engineer features from forecasted values (data_agent.engineer)
3. Predict regimes from engineered features (classification_agent)

Output: Daily regime predictions for the forecasted horizon
===========================================================
"""

import os
import sys
import argparse
import yaml
from datetime import datetime
import pandas as pd

# Add project root to path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

from forecasting_agent.forecaster import run_inference_for_features
from data_agent.engineer import engineer_forecasted_features
from classification_agent.classifier import predict_regimes_from_forecast


def run_inference_pipeline(
    horizon_days: int = 10,
    use_bigquery: bool = True,
    features_config_path: str = None,
    output_format: str = "bigquery"
):
    """
    Run the complete inference pipeline to generate regime forecasts.

    Args:
        horizon_days: Number of days to forecast into the future
        use_bigquery: Whether to load latest data from BigQuery
        features_config_path: Path to features_config.yaml
        output_format: Output format ('parquet', 'csv', or 'both')

    Returns:
        DataFrame with regime predictions per day
    """
    print("\n" + "=" * 70)
    print("🚀 REGIME FORECASTING INFERENCE PIPELINE")
    print("=" * 70)
    print(f"  📅 Forecast horizon: {horizon_days} days")
    print(f"  💾 Data source: {'BigQuery' if use_bigquery else 'Local files'}")
    print("=" * 70 + "\n")

    # Load configuration to get feature list
    if features_config_path is None:
        features_config_path = os.path.join(BASE_DIR, "configs", "features_config.yaml")

    with open(features_config_path, "r") as f:
        features_cfg = yaml.safe_load(f)

    # Collect all features from config
    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        all_features.extend(features_cfg[cadence].get('features', []))

    print(f"📊 Features to forecast: {len(all_features)} raw features")
    print(f"   {', '.join(all_features[:10])}{'...' if len(all_features) > 10 else ''}\n")

    # ===================================================================
    # STEP 1: Forecast raw features
    # ===================================================================
    print("\n" + "=" * 70)
    print("STEP 1/3: Forecasting Raw Features")
    print("=" * 70 + "\n")

    try:
        forecasted_raw = run_inference_for_features(
            feature_names=all_features,
            horizon_days=horizon_days,
            use_bigquery=use_bigquery,
            config_path=features_config_path,
            force_cpu=True
        )

        if forecasted_raw.empty:
            raise ValueError("No raw forecasts generated")

        print(f"\n✅ Step 1 complete: {len(forecasted_raw)} raw feature-day combinations")

    except Exception as e:
        print(f"\n❌ Step 1 failed: {e}")
        raise

    # ===================================================================
    # STEP 2: Engineer features from forecasts
    # ===================================================================
    print("\n" + "=" * 70)
    print("STEP 2/3: Engineering Features from Forecasts")
    print("=" * 70 + "\n")

    try:
        engineered_features = engineer_forecasted_features(
            forecasted_raw_df=forecasted_raw,
            cfg_path=os.path.join(BASE_DIR, "configs", "feature_policy.yaml")
        )

        if engineered_features.empty:
            raise ValueError("No engineered features generated")

        print(f"\n✅ Step 2 complete: {len(engineered_features)} engineered feature-day combinations")

    except Exception as e:
        print(f"\n❌ Step 2 failed: {e}")
        raise

    # ===================================================================
    # STEP 3: Predict regimes
    # ===================================================================
    print("\n" + "=" * 70)
    print("STEP 3/3: Predicting Regimes")
    print("=" * 70 + "\n")

    try:
        regime_predictions = predict_regimes_from_forecast(
            engineered_features_df=engineered_features
        )

        if regime_predictions.empty:
            raise ValueError("No regime predictions generated")

        print(f"\n✅ Step 3 complete: {len(regime_predictions)} daily regime predictions")

    except Exception as e:
        print(f"\n❌ Step 3 failed: {e}")
        raise

    # ===================================================================
    # Save final results
    # ===================================================================
    print("\n" + "=" * 70)
    print("💾 Saving Final Results")
    print("=" * 70 + "\n")

    output_dir = os.path.join(BASE_DIR, "outputs", "inference")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"regime_forecast_{timestamp}"
    forecast_id = None

    # Save to BigQuery (PRIMARY) if enabled
    try:
        from data_agent.storage import get_storage
        storage = get_storage()

        # Check if BigQuery is enabled
        if hasattr(storage, 'save_forecast'):
            print("  💾 Saving to BigQuery...")
            forecast_id = storage.save_forecast(regime_predictions, model_version=1)
            print(f"  ✅ Saved to BigQuery: {forecast_id}")
        else:
            print("  ℹ️  BigQuery not available, saving locally only")
    except Exception as e:
        print(f"  ⚠️  BigQuery save failed (falling back to local): {e}")

    # Save locally (BACKUP or PRIMARY if BigQuery unavailable)
    if output_format in ["parquet", "both"]:
        parquet_path = os.path.join(output_dir, f"{base_filename}.parquet")
        regime_predictions.to_parquet(parquet_path, index=False)
        print(f"  ✅ Saved Parquet: {parquet_path}")

    if output_format in ["csv", "both"]:
        csv_path = os.path.join(output_dir, f"{base_filename}.csv")
        regime_predictions.to_csv(csv_path, index=False)
        print(f"  ✅ Saved CSV: {csv_path}")

    # Save raw forecasts for validation
    raw_parquet_path = os.path.join(output_dir, f"raw_forecasts_{timestamp}.parquet")
    forecasted_raw.to_parquet(raw_parquet_path, index=False)
    print(f"  ✅ Saved raw forecasts: {raw_parquet_path}")

    # ===================================================================
    # Print summary
    # ===================================================================
    print("\n" + "=" * 70)
    print("📊 INFERENCE PIPELINE SUMMARY")
    print("=" * 70)
    print(f"  📅 Forecast period: {regime_predictions['ds'].min()} to {regime_predictions['ds'].max()}")
    print(f"  📈 Total days forecasted: {len(regime_predictions)}")
    print(f"\n  🎯 Predicted Regime Distribution:")

    for regime_id in sorted(regime_predictions['regime'].unique()):
        count = (regime_predictions['regime'] == regime_id).sum()
        pct = count / len(regime_predictions) * 100
        avg_prob = regime_predictions[regime_predictions['regime'] == regime_id]['regime_probability'].mean()
        print(f"     Regime {regime_id}: {count:3d} days ({pct:5.1f}%) - Avg confidence: {avg_prob:.3f}")

    print("\n  📁 Output location: outputs/inference/")
    if forecast_id:
        print(f"  🔑 BigQuery forecast ID: {forecast_id}")
    print("=" * 70 + "\n")

    # Return result with metadata for LangGraph node
    return {
        "forecast_id": forecast_id or f"forecast_{timestamp}",
        "predictions_count": int(len(regime_predictions)),
        "start_date": str(regime_predictions['ds'].min().isoformat()),
        "end_date": str(regime_predictions['ds'].max().isoformat()),
        "regime_distribution": {
            int(regime): int(count)
            for regime, count in regime_predictions['regime'].value_counts().items()
        }
    }


# ===================================================================
# CLI
# ===================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run inference pipeline to forecast market regimes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Forecast next 10 days from local data
  python -m orchestrator.inference --horizon 10

  # Forecast next 30 days from BigQuery
  python -m orchestrator.inference --horizon 30 --use-bigquery

  # Forecast with both CSV and Parquet output
  python -m orchestrator.inference --horizon 14 --output both
        """
    )

    parser.add_argument(
        "--horizon",
        type=int,
        default=10,
        help="Number of days to forecast (default: 10)"
    )

    parser.add_argument(
        "--use-bigquery",
        action="store_true",
        default=True,
        help="Load latest data from BigQuery (default: enabled)"
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to features_config.yaml (default: configs/features_config.yaml)"
    )

    parser.add_argument(
        "--output",
        choices=["parquet", "csv", "both", "bigquery"],
        default="bigquery",
        help="Output format (default: bigquery)"
    )

    args = parser.parse_args()

    # Run inference pipeline
    try:
        results = run_inference_pipeline(
            horizon_days=args.horizon,
            use_bigquery=args.use_bigquery,
            features_config_path=args.config,
            output_format=args.output
        )

        print("✅ Inference pipeline completed successfully!\n")

    except Exception as e:
        print(f"\n❌ Inference pipeline failed: {e}\n")
        sys.exit(1)
