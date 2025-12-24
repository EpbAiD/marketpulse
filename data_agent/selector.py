#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selector.py
Feature Selection & Alignment Module for RFP

- Loads engineered feature Parquets (one per raw feature)
- Aligns them by latest common available date
- Runs PCA (variance-based), correlation clustering, and mRMR
- Produces final aligned dataset and selected feature list for modeling

Outputs:
  • outputs/selected/features_selected.csv
  • outputs/selected/aligned_dataset.parquet
  • outputs/diagnostics/selector/*
"""

import os
import sys
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.feature_selection import mutual_info_regression
from sklearn.cluster import AgglomerativeClustering
import matplotlib.pyplot as plt
import seaborn as sns

from data_agent.utils import ensure_dir, summarize_feature

# Import storage layer
from data_agent.storage import get_storage

# --------------------------------------------------------------
# PATHS (robust to CWD) + safe writers
# --------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENGINEERED_DIR = os.path.join(BASE_DIR, "outputs", "engineered")
OUT_DIR       = os.path.join(BASE_DIR, "outputs", "selected")
DIAG_ROOT     = os.path.join(BASE_DIR, "outputs", "diagnostics")
DIAG_DIR      = os.path.join(DIAG_ROOT, "selector")

def _ensure_all_dirs():
    for d in [ENGINEERED_DIR, OUT_DIR, DIAG_ROOT, DIAG_DIR]:
        ensure_dir(d)

def _safe_write_csv(df: pd.DataFrame, path: str, **kwargs):
    ensure_dir(os.path.dirname(path))
    df.to_csv(path, **kwargs)

def _safe_savefig(path: str, **kwargs):
    ensure_dir(os.path.dirname(path))
    plt.savefig(path, **kwargs)

def _safe_to_parquet(df: pd.DataFrame, path: str, **kwargs):
    ensure_dir(os.path.dirname(path))
    df.to_parquet(path, **kwargs)

# --------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------
VAR_THRESHOLD = 0.97
CORR_THRESHOLD = 0.85
MRMR_TOP = 25
REDUNDANCY_WEIGHT = 0.5

# --------------------------------------------------------------
# LOAD AND ALIGN FEATURES
# --------------------------------------------------------------
def load_engineered_features(use_bigquery=False):
    dfs = {}

    if use_bigquery:
        # Load from BigQuery
        storage = get_storage(use_bigquery=True)

        # Get list of all feature names
        from google.cloud import bigquery
        client = bigquery.Client()
        query = f"""
            SELECT DISTINCT base_feature
            FROM `{storage.dataset_id}.engineered_features`
            ORDER BY base_feature
        """
        result = client.query(query).to_dataframe()
        feature_names = result['base_feature'].tolist()
        print(f"📂 Found {len(feature_names)} engineered features in BigQuery")

        # Load each feature
        for feature_name in feature_names:
            df = storage.load_engineered_features(feature_name)
            if df is not None:
                # Prefix columns with base_feature name to avoid collisions
                df.columns = [f"{feature_name}_{col}" for col in df.columns]
                dfs[feature_name] = df
                summarize_feature(df, feature_name)
    else:
        # Load from local parquet files
        files = [f for f in os.listdir(ENGINEERED_DIR) if f.endswith(".parquet")]
        print(f"📂 Found {len(files)} engineered feature files")

        for fname in files:
            fpath = os.path.join(ENGINEERED_DIR, fname)
            df = pd.read_parquet(fpath)
            feature_name = fname.replace(".parquet", "")
            # Prefix columns with feature name to avoid collisions
            df.columns = [f"{feature_name}_{col}" for col in df.columns]
            dfs[feature_name] = df
            summarize_feature(df, fname)

    # Latest common start date
    start_dates = {k: v.index.min() for k, v in dfs.items()}
    max_start = max(start_dates.values())
    print(f"📅 Common alignment start date → {max_start.date()}")

    # Align & merge
    aligned = [df.loc[df.index >= max_start] for df in dfs.values()]
    master = pd.concat(aligned, axis=1).sort_index()
    # No need to remove duplicates anymore since we prefixed columns
    # master = master.loc[:, ~master.columns.duplicated()]

    print(f"✅ Aligned master dataset shape → {master.shape}")
    return master, max_start

# --------------------------------------------------------------
# DIAGNOSTIC (log-only; no mutation)
# --------------------------------------------------------------
def check_for_invalids(df: pd.DataFrame, stage: str = "pre-scaling"):
    non_finite_mask = ~np.isfinite(df)
    invalid_cols = df.columns[non_finite_mask.any()]
    if len(invalid_cols) > 0:
        print(f"\n⚠️ Non-finite or extreme values detected during {stage}:")
        report = []
        for col in invalid_cols:
            n_inf = np.isinf(df[col]).sum()
            n_nan = df[col].isna().sum()
            max_val = df[col].abs().max()
            report.append((col, int(n_inf), int(n_nan), float(max_val)))
        rep_df = pd.DataFrame(report, columns=["feature", "inf_count", "nan_count", "max_abs_value"])
        rep_path = os.path.join(DIAG_DIR, f"invalid_values_{stage}.csv")
        _safe_write_csv(rep_df, rep_path, index=False)
        print(rep_df.head())
        return rep_df
    else:
        print(f"✅ No non-finite or extreme values detected during {stage}.")
        return pd.DataFrame(columns=["feature", "inf_count", "nan_count", "max_abs_value"])

# --------------------------------------------------------------
# FEATURE SELECTION STAGES
# --------------------------------------------------------------
def dynamic_pca(X: pd.DataFrame, var_threshold=VAR_THRESHOLD):
    print(f"🔍 Running PCA (threshold={var_threshold:.2f}) ...")
    pca_full = PCA(n_components=None)
    pca_full.fit(X)

    cum_var = np.cumsum(pca_full.explained_variance_ratio_)
    n_opt = np.argmax(cum_var >= var_threshold) + 1
    print(f"✅ Retained {n_opt} components explaining {cum_var[n_opt-1]*100:.2f}% variance")

    plt.figure(figsize=(7, 4))
    plt.plot(cum_var, marker="o")
    plt.axhline(y=var_threshold, color="r", linestyle="--")
    plt.title("Cumulative Explained Variance")
    plt.xlabel("Component")
    plt.ylabel("Cumulative Variance")
    plt.tight_layout()
    _safe_savefig(os.path.join(DIAG_DIR, "pca_scree.png"), dpi=200)
    plt.close()

    return n_opt, pca_full

def correlation_clustering(X: pd.DataFrame, corr_threshold=CORR_THRESHOLD):
    print("🔗 Performing correlation clustering ...")
    corr = X.corr().fillna(0.0)
    dist = 1 - np.abs(corr)
    model = AgglomerativeClustering(
        linkage="average",
        metric="precomputed",
        n_clusters=None,
        distance_threshold=(1 - corr_threshold),
    )
    model.fit(dist)

    labels = model.labels_
    clusters = pd.DataFrame({"feature": X.columns, "cluster": labels}).sort_values("cluster")

    reps = []
    for cluster_id in sorted(clusters["cluster"].unique()):
        members = clusters.loc[clusters["cluster"] == cluster_id, "feature"].tolist()
        subcorr = corr.loc[members, members].mean().sort_values(ascending=False)
        reps.append(subcorr.index[0])

    plt.figure(figsize=(10, 8))
    sns.heatmap(corr, cmap="coolwarm", center=0)
    plt.title("Absolute Correlation Heatmap")
    plt.tight_layout()
    _safe_savefig(os.path.join(DIAG_DIR, "corr_heatmap.png"), dpi=200)
    plt.close()

    return reps, clusters

def mrmr_selection(X: pd.DataFrame, y: pd.Series, k=MRMR_TOP, redundancy_weight=REDUNDANCY_WEIGHT):
    print(f"🧮 Running mRMR (top {k}) ...")
    relevance = mutual_info_regression(X.values, y.values, random_state=42)
    rel_map = dict(zip(X.columns, relevance))
    mi_cache = {}

    def pair_mi(a, b):
        key = tuple(sorted((a, b)))
        if key in mi_cache:
            return mi_cache[key]
        val = mutual_info_regression(X[[a]].values, X[b].values, random_state=42)[0]
        mi_cache[key] = val
        return val

    selected, candidates, scores = [], set(X.columns), []
    for _ in range(min(k, len(X.columns))):
        best, best_score = None, -np.inf
        for f in candidates:
            rel = rel_map[f]
            if not selected:
                score = rel
            else:
                red = np.mean([pair_mi(f, s) for s in selected])
                score = rel - redundancy_weight * red
            if score > best_score:
                best, best_score = f, score
        selected.append(best)
        candidates.remove(best)
        scores.append((best, best_score, rel_map[best]))

    return pd.DataFrame(scores, columns=["feature", "mrmr_score", "relevance_MI"])

# --------------------------------------------------------------
# MAIN
# --------------------------------------------------------------
def run_selector(use_bigquery=False):
    _ensure_all_dirs()

    print("===========================================================")
    print("🚀 Starting Feature Selection & Alignment Stage")
    print("===========================================================")

    master, common_start = load_engineered_features(use_bigquery=use_bigquery)
    master = master.dropna(axis=1, how="all").ffill().bfill()

    check_for_invalids(master, stage="pre-scaling")

    X = master.select_dtypes(include=[np.number])
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), index=X.index, columns=X.columns)

    check_for_invalids(X_scaled, stage="post-scaling")

    # --- PCA (two-pass: detect n_opt → refit with that count)
    n_opt, _ = dynamic_pca(X_scaled)
    pca_model = PCA(n_components=n_opt)
    X_pca = pca_model.fit_transform(X_scaled)

    loadings = pd.DataFrame(
        pca_model.components_.T,
        index=X_scaled.columns,
        columns=[f"PC{i+1}" for i in range(n_opt)],
    )
    _safe_write_csv(loadings, os.path.join(DIAG_DIR, "pca_loadings.csv"), index=True)

    # --- Correlation clustering
    corr_reps, clusters = correlation_clustering(X_scaled)
    _safe_write_csv(clusters, os.path.join(DIAG_DIR, "corr_clusters.csv"), index=False)
    _safe_write_csv(pd.DataFrame({"representative_feature": corr_reps}),
                    os.path.join(DIAG_DIR, "corr_representatives.csv"),
                    index=False)

    # --- mRMR (target = PC1)
    pc1 = pd.Series(pca_model.transform(X_scaled)[:, 0], index=X.index, name="PC1")
    mrmr_df = mrmr_selection(X_scaled, pc1, MRMR_TOP, REDUNDANCY_WEIGHT)
    _safe_write_csv(mrmr_df, os.path.join(DIAG_DIR, "mrmr_features.csv"), index=False)

    # --- Combine selections
    pca_top = set(loadings.abs().mean(axis=1).nlargest(MRMR_TOP).index)
    corr_top = set(corr_reps)
    mrmr_top = set(mrmr_df.head(MRMR_TOP)["feature"])
    final = sorted(list((pca_top & corr_top) | (corr_top & mrmr_top) | (pca_top & mrmr_top)))

    _safe_write_csv(pd.DataFrame({"selected_feature": final}),
                    os.path.join(OUT_DIR, "features_selected.csv"),
                    index=False)

    # Save aligned dataset using storage layer
    aligned_dataset_path = os.path.join(OUT_DIR, "aligned_dataset.parquet")
    aligned_df = master[final]

    # Save using storage layer
    storage = get_storage(use_bigquery=use_bigquery)
    storage.save_aligned_dataset(aligned_df)

    print("-----------------------------------------------------------")
    print(f"🎯 Final selected features: {len(final)}")
    print(f"📅 Data starts from: {common_start.date()}")
    print(f"💾 Saved aligned dataset & selected features → {OUT_DIR}")
    print("===========================================================")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run feature selection and alignment")
    parser.add_argument("--use-bigquery", action="store_true", help="Sync aligned dataset to BigQuery")
    args = parser.parse_args()
    run_selector(use_bigquery=args.use_bigquery)