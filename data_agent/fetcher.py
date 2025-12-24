#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetcher
=============================================================
→ Fetch each feature individually using configs/data_sources.yaml
→ Call utils for missingness detection, imputation, and quick summary
→ Uses universal lexical normalization for all feature names
→ Integrated with BigQuery storage layer
=============================================================
"""

import os
import sys
import yaml
import pandas as pd
import yfinance as yf
from pandas_datareader import data as pdr
from datetime import datetime

from data_agent.utils import (
    ensure_dir,
    detect_missingness,
    impute,
    summarize_feature,
    normalize_symbol,
    normalize_columns,
    enforce_string_columns,
)

# Import storage layer
from data_agent.storage import get_storage

# ============================================================
# 🔧 Config Loader
# ============================================================
def load_yaml(path: str):
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ============================================================
# 🧭 Helper: Get cadence from config
# ============================================================
def get_cadence_from_config(feature_name: str) -> str:
    """Determine cadence for a feature from features_config.yaml"""
    try:
        with open("configs/features_config.yaml", "r") as f:
            config = yaml.safe_load(f)

        for cadence in ['daily', 'weekly', 'monthly']:
            features = config.get(cadence, {}).get('features', [])
            # Check both original and normalized names
            if feature_name in features or feature_name.upper() in features:
                return cadence

        return 'daily'  # Default
    except Exception:
        return 'daily'


# ============================================================
# 📈 Fetching Helpers
# ============================================================
def fetch_yahoo(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch data from Yahoo Finance.
    Returns a DataFrame with a single normalized column for consistency.
    """
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
    except Exception as e:
        print(f"⚠️  Failed to fetch {symbol} from Yahoo: {e}")
        return pd.DataFrame()

    # Handle MultiIndex (some Yahoo versions return tuples)
    df = normalize_columns(df)

    # Standardize column selection
    if "CLOSE" in df.columns:
        df = df[["CLOSE"]]
    elif "ADJ_CLOSE" in df.columns:
        df = df[["ADJ_CLOSE"]]
    else:
        # Fallback to last numeric column if no close column found
        df = df.select_dtypes(include="number").iloc[:, :1]

    # Normalize the column name to a canonical symbol
    clean_name = normalize_symbol(symbol)
    df = df.rename(columns={df.columns[0]: clean_name})
    df.index = pd.to_datetime(df.index)
    df = enforce_string_columns(df)
    return df


def fetch_fred(code: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch data from FRED (macro + rates + credit).
    Returns a DataFrame with a single normalized column.
    """
    try:
        df = pdr.DataReader(code, "fred", start, end)
        if df.empty:
            return pd.DataFrame()
    except Exception as e:
        print(f"⚠️  Failed to fetch {code} from FRED: {e}")
        return pd.DataFrame()

    df.index = pd.to_datetime(df.index)
    df = normalize_columns(df)
    clean_name = normalize_symbol(code)
    df = df.rename(columns={df.columns[0]: clean_name})
    df = enforce_string_columns(df)
    return df


# ============================================================
# 🚀 Fetch Runner
# ============================================================
def run_fetcher(cfg_path="configs/data_sources.yaml", use_bigquery=False):
    cfg = load_yaml(cfg_path)
    start = cfg["start_date"]
    end = cfg["end_date"] or datetime.today().strftime("%Y-%m-%d")

    out_raw = cfg["output_dirs"]["raw_features"]
    out_clean = cfg["output_dirs"]["cleaned_features"]
    diag_dir = cfg["output_dirs"]["diagnostics"]
    ensure_dir(out_raw)
    ensure_dir(out_clean)
    ensure_dir(diag_dir)

    # Initialize storage layer
    storage = get_storage(use_bigquery=use_bigquery)

    yahoo = cfg["yahoo_finance"]
    fred = cfg["fred"]
    policy = cfg["missingness_policy"]
    method = policy["imputation_method"]

    for src, mapping, fetch_fn in [("Yahoo", yahoo, fetch_yahoo), ("FRED", fred, fetch_fred)]:
        for name, code in mapping.items():
            print(f"\n==============================")
            print(f"🔍 Fetching {name} ({src})")

            try:
                df = fetch_fn(code, start, end)
            except Exception as e:
                print(f"❌ Error fetching {name}: {e}")
                continue

            if df.empty:
                print(f"⚠️ No data for {name}")
                continue

            clean_name = normalize_symbol(name)
            df = normalize_columns(df)
            df = enforce_string_columns(df)

            # Diagnostics
            detect_missingness(df, clean_name, diag_dir)
            summarize_feature(df, f"{clean_name} (raw)")

            # Imputation
            df_clean = impute(df, method)
            summarize_feature(df_clean, f"{clean_name} (cleaned)")

            # Save outputs
            raw_path = os.path.join(out_raw, f"{clean_name}.parquet")
            clean_path = os.path.join(out_clean, f"{clean_name}.parquet")

            # Save raw (local only - for diagnostics) - skip if using BigQuery
            if not use_bigquery:
                df.to_parquet(raw_path)

            # Save cleaned using storage layer (BigQuery or local)
            cadence = get_cadence_from_config(clean_name)
            storage.save_raw_feature(
                df_clean,
                clean_name,
                cadence,
                incremental=True
            )

    print("\n✅ All features fetched and cleaned successfully.")


# ============================================================
# 🧭 CLI Entry
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch and clean features")
    parser.add_argument("--use-bigquery", action="store_true", help="Sync data to BigQuery")
    args = parser.parse_args()

    run_fetcher(use_bigquery=args.use_bigquery)
