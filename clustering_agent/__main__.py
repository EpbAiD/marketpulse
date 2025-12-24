#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
ClusteringAgent Entrypoint
===========================================================
Runs HMM clustering and visualization pipeline.
===========================================================
"""

from .clustering import run_hmm_clustering
from .validate import visualize_regimes

if __name__ == "__main__":
    print("===========================================")
    print("🏗️  Running ClusteringAgent: HMM Pipeline")
    print("===========================================")
    df_out, stats = run_hmm_clustering()
    print("✅ HMM Clustering finished successfully.")

    print("===========================================")
    print("📈  Generating Regime Visualization")
    print("===========================================")
    visualize_regimes(feature_for_overlay="ret_GSPC")
    print("✅ Visualization completed.")