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
# Number of latent market regimes. Set to 3 (Bull / Transitional / Bear).
# This matches the empirical sweet spot in the regime-detection literature
# (Ang & Timmermann 2012 and follow-ups) and the majority of institutional
# TAA practice. BIC on our feature set also favours 3 over 5. A 5-regime
# variant was tested and marginally improved worst-21d drawdown, but was
# harder to defend against over-fitting and less explainable to allocators.
# The label spectrum (`_LABEL_SPECTRUM_BY_K`) still supports k=2..7 for
# future experimentation.
N_REGIMES = 3
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


# Spectrum of names for k regimes, ordered from safest (lowest composite risk)
# to riskiest (highest composite risk). The first and last must be "Bull Market"
# and "Bear Market" because downstream consumers (dashboard color rules,
# investment-recommendation branches) match on those words. "Crisis Event" is
# used off-spectrum for small outlier clusters that fall below the population
# threshold — see derive_regime_label_map().
_LABEL_SPECTRUM_BY_K = {
    2: ["Bull Market", "Bear Market"],
    3: ["Bull Market", "Transitional", "Bear Market"],
    4: ["Bull Market", "Calm", "Caution", "Bear Market"],
    5: ["Bull Market", "Calm", "Transitional", "Caution", "Bear Market"],
    6: ["Bull Market", "Calm", "Transitional", "Caution", "Stress", "Bear Market"],
    7: ["Bull Market", "Calm", "Steady", "Transitional", "Caution", "Stress", "Bear Market"],
}
_OUTLIER_LABEL = "Crisis Event"

# Labeler tunables — a cluster containing fewer than MIN_POPULATION_PCT of days
# is treated as an outlier event, not a regular regime, and gets _OUTLIER_LABEL
# instead of a spectrum slot. This catches transient panic clusters (e.g., the
# COVID-2020 window) that would otherwise get spurious names by ranking rules.
MIN_POPULATION_PCT = 0.05

# Composite risk-score weights. Sum to 1.0. Higher weight → more influence
# on the safest→riskiest ranking of regular clusters.
COMPOSITE_WEIGHTS = {
    "drawdown": 0.50,   # forward-21d drawdown propensity — primary signal
    "realized_vol": 0.30,  # regime-conditional realized volatility of the index
    "vix": 0.20,        # VIX level — cross-check on volatility perception
}


def _forward_drawdown_rate(
    states: np.ndarray,
    state_index: pd.DatetimeIndex,
    raw_price: pd.Series,
    horizon_days: int = 21,
    drawdown_threshold_pct: float = 5.0,
) -> dict:
    """Per-cluster fraction of days where the close `horizon_days` ahead is
    more than `drawdown_threshold_pct` below today's close. Point-to-point
    sustained drawdown (the intuitive notion of a Bear period).

    Returns: {cluster_id (int) → drawdown_rate (float in [0,1])}.
    """
    s = pd.Series(states, index=state_index)
    px = raw_price.reindex(state_index).dropna()
    s = s.reindex(px.index)

    fwd_pct = (px.shift(-horizon_days) / px - 1) * 100
    had_drawdown = (fwd_pct < -drawdown_threshold_pct).astype(int)

    df = pd.concat([s.rename("regime"), had_drawdown.rename("dd")], axis=1).dropna()
    rates = df.groupby("regime")["dd"].mean().to_dict()
    return {int(k): float(v) for k, v in rates.items()}


def _per_cluster_stat(states: np.ndarray, X_raw: pd.DataFrame, col: str) -> dict:
    """Return {cluster_id → mean of column `col` on cluster's days}, or {} if
    column absent. Ignores NaNs cleanly."""
    if col not in X_raw.columns:
        return {}
    out = {}
    for s in sorted({int(x) for x in states}):
        vals = X_raw.loc[states == s, col].dropna()
        if len(vals) > 0:
            out[int(s)] = float(vals.mean())
    return out


def _min_max_norm(d: dict) -> dict:
    """Rescale a {id: value} dict to [0, 1]. If all values equal, returns 0.5."""
    if not d:
        return {}
    values = list(d.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-12:
        return {k: 0.5 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def derive_regime_label_map(
    X_raw: pd.DataFrame,
    states: np.ndarray,
    raw_price_for_drawdown: pd.Series = None,
    horizon_days: int = 21,
    drawdown_threshold_pct: float = 5.0,
    fallback_vix_col: str = "VIX_value",
    realized_vol_col: str = "GSPC_rv_value_10d",
) -> dict:
    """Content-based labeler that assigns Bull/.../Bear (plus off-spectrum
    "Crisis Event") to numeric HMM cluster IDs.

    HMMs exhibit label switching: each retrain may recover the same latent
    regimes under different integer IDs. This function decides regime identity
    from the actual statistics of each cluster, so labels stay meaningful
    across retrains.

    Ranking is a composite of THREE independent risk signals (weights in
    COMPOSITE_WEIGHTS above):
        1. Forward-21d drawdown propensity (primary — captures "does this
           precede real losses?")
        2. Regime-conditional realized volatility of the equity index
           (prevents a high-vol cluster being labeled Bull just because its
           forward drawdown happens to be low)
        3. Mean VIX level (independent cross-check on turbulence perception)

    Population filter: any cluster with fewer than MIN_POPULATION_PCT of total
    days is labeled "Crisis Event" and removed from spectrum assignment. This
    catches transient panic clusters (e.g. COVID-2020) that would otherwise
    receive misleading spectrum names.

    Ordering after the filter: lowest composite risk → "Bull Market", highest
    → "Bear Market", middle names from `_LABEL_SPECTRUM_BY_K[k_remaining]`.

    If a signal source is unavailable at labelling time (no price series, no
    VIX column, etc.) the function degrades gracefully: it drops the missing
    signal from the composite and renormalises the remaining weights. As long
    as at least one signal is present, ranking still works.

    Returns: {str(cluster_id) → label, "_meta": {...composite diagnostics...}}.
    """
    unique_states = sorted({int(s) for s in states})
    total_days = len(states)
    per_regime_n = {int(s): int((states == s).sum()) for s in unique_states}

    # --- Step 1: split clusters into "regular" vs "outlier" by population ---
    min_days = max(1, int(round(MIN_POPULATION_PCT * total_days)))
    regular_ids = [s for s in unique_states if per_regime_n[s] >= min_days]
    outlier_ids = [s for s in unique_states if per_regime_n[s] < min_days]

    # --- Step 2: compute per-cluster statistics we can use ---
    dd_per: dict = {}
    if raw_price_for_drawdown is not None:
        dd_per = _forward_drawdown_rate(
            states, X_raw.index, raw_price_for_drawdown,
            horizon_days=horizon_days,
            drawdown_threshold_pct=drawdown_threshold_pct,
        )
    vol_per = _per_cluster_stat(states, X_raw, realized_vol_col)
    vix_per = _per_cluster_stat(states, X_raw, fallback_vix_col)

    # --- Step 3: build composite risk score for REGULAR clusters only ---
    #    (outliers already get Crisis Event; no need to score them)
    dd_reg = {k: v for k, v in dd_per.items() if k in regular_ids}
    vol_reg = {k: v for k, v in vol_per.items() if k in regular_ids}
    vix_reg = {k: v for k, v in vix_per.items() if k in regular_ids}

    dd_norm = _min_max_norm(dd_reg)
    vol_norm = _min_max_norm(vol_reg)
    vix_norm = _min_max_norm(vix_reg)

    available_signals = {}
    if dd_norm:
        available_signals["drawdown"] = dd_norm
    if vol_norm:
        available_signals["realized_vol"] = vol_norm
    if vix_norm:
        available_signals["vix"] = vix_norm

    warning = None
    if not available_signals:
        warning = ("No risk signals available (no price, no realized-vol, no VIX). "
                   "Falling back to identity labels for regular clusters.")

    # Renormalise weights to only the available signals so total = 1.
    total_w = sum(COMPOSITE_WEIGHTS[k] for k in available_signals) or 1.0
    effective_w = {k: COMPOSITE_WEIGHTS[k] / total_w for k in available_signals}

    composite: dict = {}
    for rid in regular_ids:
        score = 0.0
        for sig_name, sig_norm in available_signals.items():
            score += effective_w[sig_name] * sig_norm.get(rid, 0.5)
        composite[rid] = round(score, 4)

    # --- Step 4: assign labels ---
    label_map: dict = {}
    k_reg = len(regular_ids)
    if k_reg == 0:
        # Pathological: everything is an outlier
        for rid in unique_states:
            label_map[str(rid)] = _OUTLIER_LABEL
    elif k_reg in _LABEL_SPECTRUM_BY_K and composite:
        spectrum = _LABEL_SPECTRUM_BY_K[k_reg]
        # Rank regular clusters by composite (ascending = safest → riskiest)
        sorted_regular = sorted(regular_ids, key=lambda c: composite.get(c, 0.5))
        for i, rid in enumerate(sorted_regular):
            label_map[str(rid)] = spectrum[i]
        for rid in outlier_ids:
            label_map[str(rid)] = _OUTLIER_LABEL
    else:
        # k_reg not in spectrum table, OR composite empty (no signals). Identity.
        for rid in regular_ids:
            label_map[str(rid)] = f"Regime {rid}"
        for rid in outlier_ids:
            label_map[str(rid)] = _OUTLIER_LABEL
        warning = warning or f"k_reg={k_reg} not in label spectrum table"

    # --- Step 5: attach diagnostic meta ---
    label_map["_meta"] = {
        "rule": (
            f"composite risk score (weights: drawdown={COMPOSITE_WEIGHTS['drawdown']:.2f}, "
            f"realized_vol={COMPOSITE_WEIGHTS['realized_vol']:.2f}, "
            f"vix={COMPOSITE_WEIGHTS['vix']:.2f}); "
            f"clusters with population < {MIN_POPULATION_PCT*100:.0f}% get "
            f"'{_OUTLIER_LABEL}' off-spectrum."
        ),
        "min_population_pct": MIN_POPULATION_PCT,
        "regular_cluster_ids": [int(x) for x in regular_ids],
        "outlier_cluster_ids": [int(x) for x in outlier_ids],
        "n_days_per_cluster": {str(k): v for k, v in per_regime_n.items()},
        "composite_score_per_cluster": {str(k): v for k, v in composite.items()},
        "drawdown_rate_per_cluster": {str(k): round(v, 4) for k, v in dd_per.items()},
        "realized_vol_per_cluster": {str(k): round(v, 6) for k, v in vol_per.items()},
        "vix_mean_per_cluster": {str(k): round(v, 2) for k, v in vix_per.items()},
        "signals_used": list(available_signals.keys()),
        "effective_weights": {k: round(v, 3) for k, v in effective_w.items()},
        "spectrum_used": _LABEL_SPECTRUM_BY_K.get(k_reg, []),
    }
    if warning:
        label_map["_meta"]["warning"] = warning

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
    from datetime import datetime as _dt
    fit_timestamp = _dt.utcnow().isoformat() + "Z"
    model_obj = {
        "model": hmm,
        "scaler": scaler,
        "features": features,
        "params": {
            "n_regimes": N_REGIMES,
            "random_state": RANDOM_STATE,
            "max_iter": MAX_ITER
        },
        "fit_timestamp": fit_timestamp,
    }
    joblib.dump(model_obj, MODEL_PATH)
    # Also write a sidecar JSON so the age checker doesn't have to load the
    # full joblib to read the fit timestamp.
    sidecar = os.path.join(MODEL_DIR, "hmm_fit_metadata.json")
    with open(sidecar, "w") as _f:
        _json.dump({
            "fit_timestamp": fit_timestamp,
            "n_regimes": N_REGIMES,
            "n_training_days": int(len(states)),
        }, _f, indent=2)
    print(f"💾 Saved HMM model → {MODEL_PATH}  (fit_timestamp={fit_timestamp})")

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