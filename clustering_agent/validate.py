#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
Visualize HMM Regimes
===========================================================
Visualizes HMM-inferred market regimes over time on top of a
selected feature (e.g., VIX, yield spread, or equity return).
Uses:
    - outputs/selected/aligned_dataset.parquet
    - outputs/clustering/cluster_assignments.parquet
Saves:
    - outputs/diagnostics/clustering/regime_timeline.png
===========================================================
"""

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ------------------------------------------------------------
# PATHS (aligned with hmm_cluster.py)
# ------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(BASE_DIR, "outputs", "selected", "aligned_dataset.parquet")
ASSIGNMENTS_PATH = os.path.join(BASE_DIR, "outputs", "clustering", "cluster_assignments.parquet")
OUT_PATH = os.path.join(BASE_DIR, "outputs", "diagnostics", "clustering", "regime_timeline.png")


def visualize_regimes(feature_for_overlay="ret_GSPC"):
    """
    Visualizes HMM regimes over time for a selected feature.

    Args:
        feature_for_overlay (str): Name of the feature to plot
    """
    print("===========================================================")
    print("📊 Starting HMM Regime Visualization")
    print("===========================================================")

    # --------------------------------------------------------
    # ✅ Load Data
    # --------------------------------------------------------
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Aligned dataset not found → {DATA_PATH}")
    if not os.path.exists(ASSIGNMENTS_PATH):
        raise FileNotFoundError(f"Cluster assignments not found → {ASSIGNMENTS_PATH}")

    df_data = pd.read_parquet(DATA_PATH)
    df_regimes = pd.read_parquet(ASSIGNMENTS_PATH)

    # Ensure consistent index
    df = df_data.join(df_regimes[["regime"]], how="inner")

    # --------------------------------------------------------
    # 🧠 Auto-detect overlay feature if missing
    # --------------------------------------------------------
    if feature_for_overlay not in df.columns:
        print(f"⚠️ Feature '{feature_for_overlay}' not found. Auto-selecting best overlay feature...")

        # Priority order for representative macro/market indicators
        fallback_candidates = [
            "VIX", "VIX_yoy", "T10Y2Y_yoy", "BAMLC0A0CM_yoy",
            "ret_DGS3MO_10d", "ret_DFF", "dd_T10Y2Y_63d"
        ]

        feature_for_overlay = next((f for f in fallback_candidates if f in df.columns), None)
        if feature_for_overlay is None:
            # fallback to first numeric column
            feature_for_overlay = df.select_dtypes(include="number").columns[0]

        print(f"✅ Using fallback feature → {feature_for_overlay}")

    # --------------------------------------------------------
    # 📈 Plot
    # --------------------------------------------------------
    df = df.sort_index()
    fig, ax = plt.subplots(figsize=(16, 6))
    df[feature_for_overlay].plot(ax=ax, lw=1.2, color="black", alpha=0.8, label=feature_for_overlay)

    # Regime color coding
    regime_colors = {0: "#f94144", 1: "#43aa8b", 2: "#577590"}  # bear, bull, neutral
    ymin, ymax = df[feature_for_overlay].min(), df[feature_for_overlay].max()

    for regime, color in regime_colors.items():
        mask = df["regime"] == regime
        if mask.any():
            ax.fill_between(df.index, ymin, ymax, where=mask, color=color, alpha=0.2, label=f"Regime {regime}")

    # --------------------------------------------------------
    # 🎨 Styling
    # --------------------------------------------------------
    ax.set_title("HMM-Inferred Market Regimes", fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel(feature_for_overlay)
    ax.legend(loc="upper left")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    plt.savefig(OUT_PATH, dpi=200)
    plt.close()

    print(f"📊 Saved regime timeline plot → {OUT_PATH}")
    print("✅ Visualization complete.")


# ------------------------------------------------------------
# 🧭 CLI Entry
# ------------------------------------------------------------
if __name__ == "__main__":
    visualize_regimes(feature_for_overlay="ret_GSPC")