#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engineer.py
Feature Engineering Module for RFP
=============================================================
- Reads cleaned raw feature Parquets (from fetcher)
- For each raw feature: generates *all* derived metrics 
  (returns, volatility, z-score, drawdown, etc.)
- Cleans infinities/NaNs via utils.sanitize_numerics()
- Stores everything in a single Parquet per feature
  (under outputs/engineered/)
- Calls utils for validation and diagnostics at each key step
=============================================================
"""

import os
import sys
import yaml
import pandas as pd
import numpy as np
from tqdm import tqdm

from data_agent.utils import (
    ensure_dir,
    summarize_feature,
    detect_missingness,
    impute,
    sanitize_numerics,
)

# Import storage layer
from data_agent.storage import get_storage

# ---------------------------------------------------------------------
# Rolling feature computation helpers
# ---------------------------------------------------------------------
def compute_returns(s: pd.Series, window: int = 1):
    return s.pct_change(window)

def compute_realized_vol(s: pd.Series, window: int):
    return s.pct_change().rolling(window).std()

def compute_zscore(s: pd.Series, window: int):
    return (s - s.rolling(window).mean()) / s.rolling(window).std()

def compute_drawdown(s: pd.Series, window: int):
    rolling_max = s.rolling(window, min_periods=1).max()
    return (s - rolling_max) / rolling_max


# ---------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------
def load_yaml(path: str):
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------
# Core Engineering Logic
# ---------------------------------------------------------------------
def engineer_features(cfg_path="configs/feature_policy.yaml", use_bigquery=False):
    cfg = load_yaml(cfg_path)
    roll = cfg["rolling_windows"]
    yoy_window = cfg["yoy_window"]
    mom_window = cfg["mom_window"]

    cleaned_dir = "outputs/fetched/cleaned"
    out_dir = "outputs/engineered"
    diag_dir = "outputs/diagnostics/engineer"
    ensure_dir(out_dir)
    ensure_dir(diag_dir)

    policy = cfg.get("missingness_policy", {"imputation_method": "ffill_bfill"})
    imp_method = policy["imputation_method"]

    # Initialize storage layer
    storage = get_storage(use_bigquery=use_bigquery)

    # Get list of features to process
    if use_bigquery:
        # Query BigQuery for distinct feature names
        from google.cloud import bigquery
        client = bigquery.Client()
        query = f"""
            SELECT DISTINCT feature_name
            FROM `{storage.dataset_id}.raw_features`
            ORDER BY feature_name
        """
        result = client.query(query).to_dataframe()
        feature_names = result['feature_name'].tolist()
        print(f"📂 Found {len(feature_names)} features in BigQuery")
    else:
        # Use local parquet files
        files = sorted([f for f in os.listdir(cleaned_dir) if f.endswith(".parquet")])
        feature_names = [f.replace(".parquet", "") for f in files]
        print(f"📂 Found {len(feature_names)} cleaned feature files")

    for idx, feature_name in enumerate(tqdm(feature_names, desc="Engineering features")):
        # Load data from BigQuery or local
        if use_bigquery:
            # Get cadence for this feature
            from data_agent.fetcher import get_cadence_from_config
            cadence = get_cadence_from_config(feature_name)

            # Load from BigQuery
            df = storage.load_raw_feature(feature_name, cadence)
            if df is None:
                print(f"⚠️  Skipping {feature_name} - not found in BigQuery")
                continue
        else:
            # Load from local file
            fpath = os.path.join(cleaned_dir, f"{feature_name}.parquet")
            df = pd.read_parquet(fpath)

        col = df.columns[0]
        s = df[col].copy()

        summarize_feature(df, f"{col}_input")
        detect_missingness(df, col, diag_dir)

        feat_df = pd.DataFrame({col: s})  # include base column itself

        # Returns (multi-horizon)
        feat_df[f"ret_{col}"] = compute_returns(s, 1)
        for w in [5, 10, 21, 63]:
            feat_df[f"ret_{col}_{w}d"] = compute_returns(s, w)

        # Realized volatility
        for w in roll["volatility"]:
            feat_df[f"rv_{col}_{w}d"] = compute_realized_vol(s, w)

        # Z-scores
        for w in roll["zscore"]:
            feat_df[f"z_{col}_{w}d"] = compute_zscore(s, w)

        # Drawdowns
        for w in roll["drawdown"]:
            feat_df[f"dd_{col}_{w}d"] = compute_drawdown(s, w)

        # YOY and MOM where applicable
        if yoy_window:
            feat_df[f"{col}_yoy"] = compute_returns(s, yoy_window)
        if mom_window:
            feat_df[f"{col}_mom"] = compute_returns(s, mom_window)

        # Drop expected leading NaNs from rolling windows
        feat_df = feat_df.dropna(how="all")

        # Impute internal missing if any irregularities remain
        feat_df = impute(feat_df, method=imp_method)

        # 🧼 Sanitize numeric anomalies (inf/-inf → NaN, fill if needed)
        feat_df = sanitize_numerics(
            feat_df, fill=True, report=True, outdir=diag_dir, name=col
        )

        summarize_feature(feat_df, f"{col}_engineered")
        detect_missingness(feat_df, col, diag_dir)

        # ✅ Save using storage layer (BigQuery or local)
        storage.save_engineered_features(
            feat_df,
            feature_name,  # Use actual feature name, not column name
            incremental=True  # Only sync new rows
        )

    print("✅ All raw features engineered successfully (1 Parquet per feature).")


# ---------------------------------------------------------------------
# INFERENCE: Engineer features from forecasted raw values
# ---------------------------------------------------------------------
def engineer_forecasted_features(
    forecasted_raw_df: pd.DataFrame,
    cfg_path: str = "configs/feature_policy.yaml",
    lookback_days: int = 252,
    use_bigquery: bool = True
) -> pd.DataFrame:
    """
    Apply feature engineering to forecasted raw feature values.

    IMPORTANT: This function combines historical data with forecasts to enable
    proper rolling window calculations. Without historical data, rolling windows
    cannot be computed accurately from sparse forecast points.

    Args:
        forecasted_raw_df: DataFrame with columns ['ds', 'feature', 'forecast_value']
                          from forecasting agent inference
        cfg_path: Path to feature_policy.yaml for rolling windows config
        lookback_days: Number of historical days to load for rolling windows (default: 252)
        use_bigquery: Whether to use BigQuery for historical data (default: True)

    Returns:
        DataFrame with columns: ['ds', 'feature_name', 'feature_value']
        where feature_name is the engineered feature (e.g., 'VIX_ret_value')
        and feature_value is the computed value (only for forecast dates)
    """
    from pathlib import Path
    import pandas as pd

    print(f"\n{'='*60}")
    print(f"🔧 ENGINEERING FORECASTED FEATURES (WITH HISTORICAL CONTEXT)")
    print(f"{'='*60}\n")

    # Try to initialize BigQuery storage for historical data
    bq_storage = None
    feature_cadences = {}
    if use_bigquery:
        try:
            from data_agent.storage import get_storage
            bq_storage = get_storage()
            print("  ✅ BigQuery storage available for historical data")

            # Load feature cadences from config
            try:
                features_cfg = load_yaml("configs/features_config.yaml")
                for cadence in ['daily', 'weekly', 'monthly']:
                    if cadence in features_cfg:
                        for feat in features_cfg[cadence].get('features', []):
                            feature_cadences[feat] = cadence
                print(f"  📋 Loaded cadence mapping for {len(feature_cadences)} features")
            except Exception as e:
                print(f"  ⚠️ Could not load feature cadences: {e}")
        except Exception as e:
            print(f"  ⚠️ BigQuery not available: {e}")

    cfg = load_yaml(cfg_path)
    roll = cfg["rolling_windows"]
    yoy_window = cfg["yoy_window"]
    mom_window = cfg["mom_window"]

    # Get max lookback needed for rolling windows
    max_window = max([
        max(roll.get("returns", [0])),
        max(roll.get("volatility", [0])),
        max(roll.get("zscore", [0])),
        max(roll.get("drawdown", [0])),
        yoy_window if yoy_window else 0,
        mom_window if mom_window else 0
    ])
    lookback_days = max(lookback_days, max_window + 10)  # Add buffer

    all_engineered = []
    base_dir = Path("outputs/fetched/cleaned")

    # Group by feature
    for feature_name, forecast_group in forecasted_raw_df.groupby('feature'):
        print(f"  🔧 Engineering {feature_name}...")

        # Get forecast dates (what we actually want to predict for)
        forecast_dates = forecast_group['ds'].unique()
        min_forecast_date = forecast_group['ds'].min()

        # Load historical data - try local file first, then BigQuery
        hist_df = None
        hist_file = base_dir / f"{feature_name}.parquet"

        # Try local parquet file first
        if hist_file.exists():
            try:
                hist_df = pd.read_parquet(hist_file)

                # Standardize historical data format
                if isinstance(hist_df.index, pd.DatetimeIndex):
                    hist_df = hist_df.reset_index()
                    date_col = hist_df.columns[0]
                    value_col = hist_df.columns[1] if len(hist_df.columns) > 1 else feature_name
                else:
                    # Find date and value columns
                    date_col = 'date' if 'date' in hist_df.columns else 'Date' if 'Date' in hist_df.columns else 'ds'
                    value_cols = [c for c in hist_df.columns if c != date_col]
                    value_col = value_cols[0] if value_cols else feature_name

                hist_df = hist_df.rename(columns={date_col: 'ds', value_col: 'value'})
                hist_df = hist_df[['ds', 'value']].copy()
                hist_df['ds'] = pd.to_datetime(hist_df['ds'])
                print(f"    📂 Loaded from local parquet")
            except Exception as e:
                print(f"    ⚠️ Error loading local parquet: {e}")
                hist_df = None

        # Try BigQuery if local file doesn't exist or failed
        if hist_df is None and bq_storage is not None:
            try:
                cadence = feature_cadences.get(feature_name, 'daily')  # Default to daily
                bq_df = bq_storage.load_raw_feature(feature_name, cadence)

                if bq_df is not None and not bq_df.empty:
                    # Convert from index to columns
                    hist_df = bq_df.reset_index()
                    hist_df.columns = ['ds', 'value']
                    hist_df['ds'] = pd.to_datetime(hist_df['ds'])
                    print(f"    ☁️ Loaded from BigQuery ({cadence})")
            except Exception as e:
                print(f"    ⚠️ Error loading from BigQuery: {e}")

        # Skip if no historical data available
        if hist_df is None or hist_df.empty:
            print(f"    ⚠️ No historical data found, skipping...")
            continue

        try:
            # Filter to lookback period
            cutoff_date = min_forecast_date - pd.Timedelta(days=lookback_days)
            hist_df = hist_df[hist_df['ds'] >= cutoff_date].copy()
            hist_df = hist_df[hist_df['ds'] < min_forecast_date].copy()  # Exclude forecast dates

        except Exception as e:
            print(f"    ⚠️ Error filtering historical data: {e}")
            continue

        # Combine historical + forecast data
        forecast_group = forecast_group.sort_values('ds').reset_index(drop=True)

        # Handle both 'forecast_value' and 'value' column names
        value_col = 'forecast_value' if 'forecast_value' in forecast_group.columns else 'value'
        forecast_df = forecast_group[['ds', value_col]].copy()
        forecast_df = forecast_df.rename(columns={value_col: 'value'})

        # Concatenate: historical first, then forecasts
        combined_df = pd.concat([hist_df, forecast_df], ignore_index=True)
        combined_df = combined_df.sort_values('ds').reset_index(drop=True)
        combined_df = combined_df.drop_duplicates(subset=['ds'], keep='last')

        print(f"    📊 Combined data: {len(hist_df)} historical + {len(forecast_df)} forecast points")

        # Create series for engineering
        s = combined_df['value'].copy()

        # Create engineered features dataframe
        feat_df = pd.DataFrame({
            'ds': combined_df['ds'],
            'value': s  # base value
        })

        # Compute ALL engineered features (with historical context for rolling windows)
        # 1-step returns
        feat_df['ret_value'] = s.pct_change(1)

        # Multi-step returns if we have enough points
        if len(s) >= 5:
            feat_df['ret_value_5d'] = s.pct_change(5)
        if len(s) >= 10:
            feat_df['ret_value_10d'] = s.pct_change(10)
        if len(s) >= 21:
            feat_df['ret_value_21d'] = s.pct_change(21)
        if len(s) >= 63:
            feat_df['ret_value_63d'] = s.pct_change(63)

        # Realized volatility (rolling std of returns)
        returns = s.pct_change()
        for w in roll.get("volatility", []):
            if len(s) >= w:
                feat_df[f'rv_value_{w}d'] = returns.rolling(w).std()

        # Z-scores (rolling)
        for w in roll.get("zscore", []):
            if len(s) >= w:
                feat_df[f'z_value_{w}d'] = compute_zscore(s, w)

        # Drawdowns (rolling)
        for w in roll.get("drawdown", []):
            if len(s) >= w:
                feat_df[f'dd_value_{w}d'] = compute_drawdown(s, w)

        # YOY and MOM if we have enough points
        if yoy_window and len(s) >= yoy_window:
            feat_df['value_yoy'] = s.pct_change(yoy_window)
        if mom_window and len(s) >= mom_window:
            feat_df['value_mom'] = s.pct_change(mom_window)

        # Sanitize numerics
        feat_df = sanitize_numerics(feat_df, fill=True, report=False)

        # IMPORTANT: Only keep forecast dates (not historical data used for computation)
        feat_df = feat_df[feat_df['ds'].isin(forecast_dates)].copy()

        if len(feat_df) == 0:
            print(f"    ⚠️  No data for forecast dates after engineering")
            continue

        # Reshape to long format: each row is (ds, feature_name, feature_value)
        for col in feat_df.columns:
            if col == 'ds':
                continue

            # Create feature names matching the training convention:
            # - 'value' column -> feature_name (e.g., 'VIX_value' or just 'VIX')
            # - Other columns -> feature_name + column (e.g., 'DFF_ret_value_5d')
            if col == 'value':
                engineered_feature_name = f"{feature_name}_value"
            else:
                engineered_feature_name = f"{feature_name}_{col}"

            for idx, row in feat_df.iterrows():
                all_engineered.append({
                    'ds': row['ds'],
                    'feature_name': engineered_feature_name,
                    'feature_value': row[col]
                })

        print(f"    ✅ Generated {len(feat_df.columns)-1} engineered features for {len(feat_df)} forecast dates")

    # Combine all engineered features
    if not all_engineered:
        print("\n❌ No engineered features generated")
        return pd.DataFrame(columns=['ds', 'feature_name', 'feature_value'])

    result_df = pd.DataFrame(all_engineered)

    # Remove rows with NaN values
    initial_rows = len(result_df)
    result_df = result_df.dropna(subset=['feature_value'])
    dropped_rows = initial_rows - len(result_df)

    if dropped_rows > 0:
        print(f"\n  ⚠️  Dropped {dropped_rows} rows with NaN values ({dropped_rows/initial_rows*100:.1f}%)")

    print(f"\n{'='*60}")
    print(f"✅ Engineering complete: {result_df['feature_name'].nunique()} unique features")
    print(f"   Total rows: {len(result_df)} (across {result_df['ds'].nunique()} dates)")
    print(f"{'='*60}\n")

    return result_df


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Engineer features from raw data")
    parser.add_argument("--use-bigquery", action="store_true", help="Sync engineered features to BigQuery")
    args = parser.parse_args()
    engineer_features(use_bigquery=args.use_bigquery)