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
# Number of latent market regimes. Increased 3 → 5 to capture finer
# structure: empirically a 5-regime HMM separates pre-drawdown days from
# bulk-of-the-time calm days much better than 3 (worst-cluster drawdown
# rate jumps from 10% to 14%, approaching the 200-day MA's 17%). The
# label spectrum (`_LABEL_SPECTRUM_BY_K`) defines names for k=2..7.
N_REGIMES = 5
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


# Spectrum of names for k regimes, ordered from safest (lowest drawdown rate)
# to riskiest (highest drawdown rate). The first and last must be "Bull Market"
# and "Bear Market" because downstream consumers (dashboard color rules,
# investment-recommendation branches) match on those words.
_LABEL_SPECTRUM_BY_K = {
    2: ["Bull Market", "Bear Market"],
    3: ["Bull Market", "Transitional", "Bear Market"],
    4: ["Bull Market", "Calm", "Caution", "Bear Market"],
    5: ["Bull Market", "Calm", "Transitional", "Caution", "Bear Market"],
    6: ["Bull Market", "Calm", "Transitional", "Caution", "Stress", "Bear Market"],
    7: ["Bull Market", "Calm", "Steady", "Transitional", "Caution", "Stress", "Bear Market"],
}


def _forward_drawdown_rate(
    states: np.ndarray,
    state_index: pd.DatetimeIndex,
    raw_price: pd.Series,
    horizon_days: int = 21,
    drawdown_threshold_pct: float = 5.0,
) -> dict:
    """Per-cluster fraction of days where the close `horizon_days` ahead is
    more than `drawdown_threshold_pct` below today's close. (Point-to-point
    sustained drawdown — the user-intuitive notion of a 'Bear' period.)

    An alternative definition is "any close within the window dropped >X%
    from today" (any-drop-in-window). That measure tags high-vol clusters
    even when the market recovers by the end of the window, which is not
    typically what an investor calls a Bear regime. Point-to-point captures
    sustained declines.

    Returns: {cluster_id (int) → drawdown_rate (float in [0,1])}.
    Forward-realized data within the training window only; no test leakage.
    """
    s = pd.Series(states, index=state_index)
    px = raw_price.reindex(state_index).dropna()
    s = s.reindex(px.index)

    fwd_pct = (px.shift(-horizon_days) / px - 1) * 100
    had_drawdown = (fwd_pct < -drawdown_threshold_pct).astype(int)

    df = pd.concat([s.rename("regime"), had_drawdown.rename("dd")], axis=1).dropna()
    rates = df.groupby("regime")["dd"].mean().to_dict()
    return {int(k): float(v) for k, v in rates.items()}


def derive_regime_label_map(
    X_raw: pd.DataFrame,
    states: np.ndarray,
    raw_price_for_drawdown: pd.Series = None,
    horizon_days: int = 21,
    drawdown_threshold_pct: float = 5.0,
    fallback_vix_col: str = "VIX_value",
) -> dict:
    """Assign labels (Bull / ... / Bear) to numeric HMM regime IDs based on
    each cluster's empirical forward-drawdown rate within the training window.

    HMMs have a label-switching property: each retrain may converge to the
    same latent regimes but assign them arbitrary integer IDs. To keep
    downstream display consistent across retrains, we derive labels from
    each cluster's *empirical* propensity to precede a >X% drawdown over
    the next N days.

    Ordering (lowest drawdown rate → highest drawdown rate):
      "Bull Market" → ... → "Bear Market"

    Cluster-count-specific names (Calm, Caution, Stress, ...) come from
    `_LABEL_SPECTRUM_BY_K`. The first and last names are always
    "Bull Market" and "Bear Market" so dashboard color/branch rules
    (which match on those words) keep working.

    If `raw_price_for_drawdown` is not provided, fall back to ranking by
    mean VIX as a coarse proxy. This is strictly worse — VIX-mean ranks
    high-vol-recovery clusters as "Bear" when they actually precede recoveries,
    not declines — but it's better than no labeling.

    Returns: {str(cluster_id) → name, "_meta": {...}}.
    """
    unique_states = sorted({int(s) for s in states})
    k = len(unique_states)

    if k not in _LABEL_SPECTRUM_BY_K:
        # Unsupported cluster count — fall back to numeric labels
        return {
            "_meta": {"warning": f"k={k} clusters not in label spectrum; using identity"},
            **{str(i): f"Regime {i}" for i in unique_states},
        }

    spectrum = _LABEL_SPECTRUM_BY_K[k]

    # Decide rank metric: drawdown rate (preferred) or VIX mean (fallback).
    if raw_price_for_drawdown is not None:
        per_regime_dd = _forward_drawdown_rate(
            states, X_raw.index, raw_price_for_drawdown,
            horizon_days=horizon_days,
            drawdown_threshold_pct=drawdown_threshold_pct,
        )
        # Sort cluster ids ascending by drawdown rate (lowest = Bull, highest = Bear)
        sorted_ids = sorted(unique_states, key=lambda c: per_regime_dd.get(c, 0.0))
        rank_metric = {
            "rule": (f"forward-{horizon_days}d drawdown rate (>{drawdown_threshold_pct}%): "
                     "lowest→Bull, highest→Bear"),
            "drawdown_rate_per_cluster": {str(c): round(per_regime_dd.get(c, 0.0), 4)
                                          for c in unique_states},
        }
    elif fallback_vix_col in X_raw.columns:
        vix_per = {int(s): float(X_raw.loc[states == s, fallback_vix_col].mean())
                   for s in unique_states}
        # NOTE: VIX-mean ranking is a coarse proxy. It typically labels the
        # HIGH-VIX (panic-recovery) cluster as Bear, even though that cluster
        # has POSITIVE forward returns historically. Use it only when no
        # forward-price series is available.
        sorted_ids = sorted(unique_states, key=lambda c: vix_per[c])
        rank_metric = {
            "rule": "VIX-mean fallback: lowest→Bull, highest→Bear",
            "vix_mean_per_cluster": {str(c): round(vix_per[c], 2) for c in unique_states},
            "warning": "Using VIX-mean fallback — rank-by-drawdown is preferred",
        }
    else:
        return {
            "_meta": {"warning": f"No price or {fallback_vix_col} available; identity labels"},
            **{str(i): f"Regime {i}" for i in unique_states},
        }

    label_map = {str(rid): spectrum[i] for i, rid in enumerate(sorted_ids)}
    per_regime_n = {str(s): int((states == s).sum()) for s in unique_states}
    label_map["_meta"] = {
        **rank_metric,
        "n_days_per_cluster": per_regime_n,
        "spectrum_used": spectrum,
    }
    return label_map


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

    # Derive labels from this run's regime IDs (HMM IDs are arbitrary across
    # retrains — see label-switching). Save next to the model so dashboard/
    # alerts/log_daily_predictions load it instead of hardcoding numeric →
    # name mappings that drift on retrain.
    #
    # Ranking rule: each cluster's empirical forward-21d-drawdown rate within
    # the training window. Lowest drawdown rate → "Bull Market", highest →
    # "Bear Market". This is strictly better than VIX-mean ranking, which
    # mistakenly labels post-crisis recovery clusters as "Bear" since they
    # are high-vol but precede positive returns. To compute this we need raw
    # GSPC prices, which selector dropped from the engineered set.
    raw_gspc = None
    try:
        storage_for_gspc = get_storage(use_bigquery=use_bigquery)
        gspc_df = storage_for_gspc.load_raw_feature("GSPC", "daily")
        if gspc_df is not None and not gspc_df.empty:
            # load_raw_feature returns a DataFrame with a value column
            if isinstance(gspc_df, pd.DataFrame):
                # Pick the first numeric column as the price series
                num_cols = gspc_df.select_dtypes(include=[np.number]).columns
                if len(num_cols) > 0:
                    raw_gspc = gspc_df[num_cols[0]]
                    raw_gspc.index = pd.to_datetime(raw_gspc.index).normalize()
            else:
                raw_gspc = pd.Series(gspc_df)
        if raw_gspc is None or raw_gspc.empty:
            print("⚠️  Could not load raw GSPC for drawdown labeling — falling back to VIX-mean")
    except Exception as _e:
        print(f"⚠️  Raw GSPC fetch for labeling failed ({_e}) — falling back to VIX-mean")

    label_map = derive_regime_label_map(
        X.loc[X_scaled.index], states,
        raw_price_for_drawdown=raw_gspc,
    )
    label_map_path = os.path.join(MODEL_DIR, "regime_label_map.json")
    import json as _json
    with open(label_map_path, "w") as _f:
        _json.dump(label_map, _f, indent=2)
    semantic_summary = ", ".join(
        f"{rid}={label}" for rid, label in label_map.items() if not rid.startswith("_")
    )
    print(f"💾 Saved regime label map → {label_map_path}  ({semantic_summary})")

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