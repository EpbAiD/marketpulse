#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
clustering_agent/hmm_cluster.py
===========================================================
Hidden Markov Model (HMM)–based Regime Clustering for RFP
-----------------------------------------------------------
1️⃣ Loads the aligned + selected features:
        outputs/selected/aligned_dataset.parquet
        outputs/selected/features_selected.csv
2️⃣ Fits a GaussianHMM to statistically identify regimes
3️⃣ Saves:
        • outputs/clustering/cluster_assignments.parquet
        • outputs/clustering/cluster_stats.csv
        • outputs/models/hmm_model.joblib
        • outputs/diagnostics/clustering/hmm_sequence.png
===========================================================
"""

import os
import sys
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

# Import storage layer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from data_agent.storage import get_storage

# -----------------------------------------------------------
# 🔧 PATH CONFIGURATION (auto-detect root)
# -----------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SELECTED_DATA = os.path.join(BASE_DIR, "outputs", "selected", "aligned_dataset.parquet")
FEATURE_LIST = os.path.join(BASE_DIR, "outputs", "selected", "features_selected.csv")

CLUSTER_DIR = os.path.join(BASE_DIR, "outputs", "clustering")
MODEL_DIR = os.path.join(BASE_DIR, "outputs", "models")
DIAG_DIR = os.path.join(BASE_DIR, "outputs", "diagnostics", "clustering")

for d in [CLUSTER_DIR, MODEL_DIR, DIAG_DIR]:
    os.makedirs(d, exist_ok=True)

ASSIGNMENTS_PATH = os.path.join(CLUSTER_DIR, "cluster_assignments.parquet")
STATS_PATH = os.path.join(CLUSTER_DIR, "cluster_stats.csv")
MODEL_PATH = os.path.join(MODEL_DIR, "hmm_model.joblib")
PLOT_PATH = os.path.join(DIAG_DIR, "hmm_sequence.png")

# -----------------------------------------------------------
# ⚙️ CONFIGURATION
# -----------------------------------------------------------
N_REGIMES = 3           # number of latent market regimes
RANDOM_STATE = 42
MAX_ITER = 2000

# -----------------------------------------------------------
# 🧭 HELPER FUNCTIONS
# -----------------------------------------------------------
def sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure numeric-only, finite, and fully aligned data."""
    df = df.select_dtypes(include=[np.number]).copy()
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.ffill(inplace=True)
    df.bfill(inplace=True)
    df.dropna(how="any", inplace=True)
    return df


def compute_cluster_stats(X_scaled: pd.DataFrame, states: np.ndarray) -> pd.DataFrame:
    """Aggregate mean/std/min/max stats per regime."""
    stats = X_scaled.copy()
    stats["regime"] = states
    summary = stats.groupby("regime").agg(["mean", "std", "min", "max"])
    summary.index.name = "Regime"
    return summary


def plot_regime_sequence(index, states, n_regimes: int, out_path: str):
    """Save a timeline plot of HMM regime sequence."""
    plt.figure(figsize=(15, 4))
    plt.title("HMM Regime Sequence")
    plt.plot(index, states, color="black", lw=1)
    plt.yticks(range(n_regimes))
    plt.xlabel("Date")
    plt.ylabel("Regime")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()

# -----------------------------------------------------------
# 🚀 MAIN ROUTINE
# -----------------------------------------------------------
def run_hmm_clustering(use_bigquery=False):
    print("===========================================================")
    print("🚀 Starting HMM-based Regime Clustering Agent")
    print("===========================================================")

    # -------------------------------------------------------
    # 📦 Load dataset & features
    # -------------------------------------------------------
    if use_bigquery:
        # Load from BigQuery
        storage = get_storage(use_bigquery=True)
        df = storage.load_aligned_dataset()
        if df is None:
            raise ValueError("❌ Aligned dataset not found in BigQuery")
        print(f"📦 Loaded aligned dataset from BigQuery: {df.shape}")
    else:
        # Load from local file
        if not os.path.exists(SELECTED_DATA):
            raise FileNotFoundError(f"Aligned dataset not found → {SELECTED_DATA}")
        df = pd.read_parquet(SELECTED_DATA)
        print(f"📦 Loaded aligned dataset: {df.shape}")

    if os.path.exists(FEATURE_LIST):
        features = pd.read_csv(FEATURE_LIST)["selected_feature"].tolist()
        features = [f for f in features if f in df.columns]
        print(f"🧩 Using {len(features)} selected features from selector")
    else:
        features = df.columns.tolist()
        print("⚠️ Feature list missing → using all numeric columns")

    X = df[features].copy()
    X = sanitize_data(X)

    if X.empty:
        raise ValueError("❌ No valid numeric data available for HMM fitting.")

    print(f"✅ Data sanitized → {X.shape[0]} rows, {X.shape[1]} features")

    # -------------------------------------------------------
    # ⚖️ Standardization
    # -------------------------------------------------------
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(
        scaler.fit_transform(X),
        index=X.index,
        columns=X.columns
    )

    print("⚙️ Data scaled successfully.")

    # -------------------------------------------------------
    # 🤖 Fit HMM
    # -------------------------------------------------------
    hmm = GaussianHMM(
        n_components=N_REGIMES,
        covariance_type="full",
        n_iter=MAX_ITER,
        random_state=RANDOM_STATE,
        verbose=False
    )

    print(f"🔧 Fitting GaussianHMM (n_regimes={N_REGIMES}, n_iter={MAX_ITER}) ...")
    hmm.fit(X_scaled)
    states = hmm.predict(X_scaled)
    print("✅ HMM training completed.")

    # -------------------------------------------------------
    # 📊 Compute regime stats
    # -------------------------------------------------------
    stats = compute_cluster_stats(X_scaled, states)
    stats.to_csv(STATS_PATH)
    print(f"💾 Saved cluster stats → {STATS_PATH}")

    # -------------------------------------------------------
    # 💾 Save outputs
    # -------------------------------------------------------
    model_obj = {
        "model": hmm,
        "scaler": scaler,
        "features": features,
        "params": {
            "n_regimes": N_REGIMES,
            "random_state": RANDOM_STATE,
            "max_iter": MAX_ITER
        }
    }
    joblib.dump(model_obj, MODEL_PATH)
    print(f"💾 Saved HMM model → {MODEL_PATH}")

    df_out = df.loc[X_scaled.index].copy()
    df_out["regime"] = states

    # Save using storage layer
    storage = get_storage(use_bigquery=use_bigquery)
    storage.save_cluster_assignments(df_out)

    # -------------------------------------------------------
    # 📈 Diagnostics
    # -------------------------------------------------------
    plot_regime_sequence(df_out.index, states, N_REGIMES, PLOT_PATH)
    print(f"📈 Saved regime timeline plot → {PLOT_PATH}")

    print("===========================================================")
    print("✅ HMM Clustering Agent finished successfully.")
    print("===========================================================")
    return df_out, stats


# -----------------------------------------------------------
# 🧭 CLI Entry
# -----------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run HMM regime clustering")
    parser.add_argument("--use-bigquery", action="store_true", help="Sync cluster assignments to BigQuery")
    args = parser.parse_args()
    df_out, stats = run_hmm_clustering(use_bigquery=args.use_bigquery)