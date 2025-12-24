#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validation_nodes.py
Enhanced Human Validation Nodes with Agentic Suggestions
=============================================================
These nodes provide intelligent recommendations and allow
humans to validate/override key decision points:
- Clustering parameters (n_regimes, regime labels)
- Classification hyperparameters (n_estimators, test_size)
- Forecasting configuration (retraining periods, horizons)
- Feature selection thresholds (PCA, correlation, mRMR)
=============================================================
"""

import os
import json
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from orchestrator.state import PipelineState


# ============================================================
# VALIDATION 1: Feature Selection Configuration
# ============================================================
def validate_feature_selection_config(state: PipelineState) -> PipelineState:
    """
    Allow human to configure feature selection thresholds BEFORE selection runs.
    Agentic suggestion based on data dimensionality.
    """
    if state.get("skip_select", False):
        return state

    print("\n" + "=" * 70)
    print("🎯 VALIDATION: Feature Selection Configuration")
    print("=" * 70)

    # Load engineered data to understand dimensionality
    eng_dir = "outputs/engineered"
    if os.path.exists(eng_dir):
        n_features = len([f for f in os.listdir(eng_dir) if f.endswith(".parquet")])
        print(f"\n📊 Current Status:")
        print(f"   • Total engineered features: {n_features}")

        # Agentic suggestion
        suggested_pca_variance = 0.97
        suggested_corr_threshold = 0.85
        suggested_mrmr_k = min(25, n_features // 2)

        print(f"\n🤖 Agent Suggestions (based on {n_features} features):")
        print(f"   • PCA variance threshold: {suggested_pca_variance} (keep 97% variance)")
        print(f"   • Correlation threshold: {suggested_corr_threshold} (group highly correlated)")
        print(f"   • mRMR top-k: {suggested_mrmr_k} (half of features)")

    print("\n🔍 Configuration Options:")
    print("   1. Use agent suggestions (recommended)")
    print("   2. Customize thresholds")
    print("   3. Skip this validation\n")

    response = input("Select option [1/2/3]: ").strip()

    if response == "2":
        pca_var = input(f"  PCA variance threshold [0.97]: ").strip()
        corr_thresh = input(f"  Correlation threshold [0.85]: ").strip()
        mrmr_k = input(f"  mRMR top-k features [25]: ").strip()

        state["feature_selection_config"] = {
            "pca_variance": float(pca_var) if pca_var else 0.97,
            "correlation_threshold": float(corr_thresh) if corr_thresh else 0.85,
            "mrmr_k": int(mrmr_k) if mrmr_k else 25,
        }
        print(f"\n✅ Custom configuration saved: {state['feature_selection_config']}\n")

    elif response == "1" or response == "":
        state["feature_selection_config"] = {
            "pca_variance": 0.97,
            "correlation_threshold": 0.85,
            "mrmr_k": min(25, n_features // 2) if os.path.exists(eng_dir) else 25,
        }
        print("\n✅ Using agent suggestions\n")

    return state


# ============================================================
# VALIDATION 2: Clustering Configuration & Regime Labeling
# ============================================================
def validate_clustering_config(state: PipelineState) -> PipelineState:
    """
    Configure clustering parameters and label regimes with meaningful names.
    This is a KEY validation point for domain expertise.
    """
    if state.get("skip_cluster", False):
        return state

    print("\n" + "=" * 70)
    print("🎯 VALIDATION: Clustering Configuration")
    print("=" * 70)

    # Agentic suggestion based on financial domain knowledge
    print(f"\n🤖 Agent Suggestions:")
    print(f"   • Number of regimes: 3 (Bull, Bear, Neutral)")
    print(f"   • HMM iterations: 2000 (converges well for financial data)")
    print(f"   • Covariance type: 'full' (capture regime correlations)")

    print("\n🔍 Configuration:")
    n_regimes_input = input("  Number of regimes [3]: ").strip()
    n_regimes = int(n_regimes_input) if n_regimes_input else 3

    max_iter_input = input("  Max HMM iterations [2000]: ").strip()
    max_iter = int(max_iter_input) if max_iter_input else 2000

    state["clustering_config"] = {
        "n_regimes": n_regimes,
        "max_iter": max_iter,
        "covariance_type": "full",
        "random_state": 42,
    }

    # Pre-assign regime labels (can be updated post-clustering)
    print(f"\n🏷️  Pre-assign regime labels (will be validated post-clustering):")
    regime_labels = {}
    default_labels = ["Bull Market", "Bear Market", "Neutral/Sideways"]

    for i in range(n_regimes):
        default = default_labels[i] if i < len(default_labels) else f"Regime {i}"
        label = input(f"  Regime {i} label [{default}]: ").strip()
        regime_labels[i] = label if label else default

    state["regime_labels"] = regime_labels
    print(f"\n✅ Clustering config: {state['clustering_config']}")
    print(f"   Regime labels: {regime_labels}\n")

    return state


def validate_regime_labeling(state: PipelineState) -> PipelineState:
    """
    Post-clustering: Review regime statistics and assign/update meaningful labels.
    This allows domain experts to validate regime interpretation.
    """
    if state.get("skip_cluster", False) or not state.get("cluster_status", {}).get("success"):
        return state

    print("\n" + "=" * 70)
    print("🏷️  VALIDATION: Regime Labeling & Interpretation")
    print("=" * 70)

    # Load cluster statistics
    stats_path = "outputs/clustering/cluster_stats.csv"
    if os.path.exists(stats_path):
        stats = pd.read_csv(stats_path)
        print("\n📊 Regime Statistics Summary:")
        print(stats.to_string(index=False))
        print()

        # Agent interpretation suggestions
        print("🤖 Agent Interpretation Suggestions:")
        print("   (Analyze mean returns, volatility, and other features per regime)")
        # TODO: Add logic to suggest labels based on statistics

    # Review current labels
    current_labels = state.get("regime_labels", {})
    print(f"\n🏷️  Current Regime Labels:")
    for regime, label in current_labels.items():
        print(f"   • Regime {regime}: {label}")

    print("\n🔍 Options:")
    print("   1. Keep current labels")
    print("   2. Update regime labels")
    print("   3. Export labels to config file\n")

    response = input("Select option [1/2/3]: ").strip()

    if response == "2":
        new_labels = {}
        for regime in current_labels.keys():
            new_label = input(f"  New label for Regime {regime} [{current_labels[regime]}]: ").strip()
            new_labels[regime] = new_label if new_label else current_labels[regime]
        state["regime_labels"] = new_labels
        print(f"\n✅ Updated regime labels: {new_labels}\n")

    elif response == "3":
        # Save to JSON
        labels_path = "outputs/clustering/regime_labels.json"
        with open(labels_path, "w") as f:
            json.dump(state["regime_labels"], f, indent=2)
        print(f"\n✅ Regime labels saved to: {labels_path}\n")

    return state


# ============================================================
# VALIDATION 3: Classification Hyperparameters
# ============================================================
def validate_classification_config(state: PipelineState) -> PipelineState:
    """
    Configure Random Forest hyperparameters for regime classification.
    Allow tuning based on accuracy requirements.
    """
    if state.get("skip_classify", False):
        return state

    print("\n" + "=" * 70)
    print("🎯 VALIDATION: Classification Configuration")
    print("=" * 70)

    # Agentic suggestions
    print(f"\n🤖 Agent Suggestions:")
    print(f"   • n_estimators: 500 (good balance of accuracy vs speed)")
    print(f"   • max_depth: None (let trees grow fully)")
    print(f"   • test_size: 0.2 (80/20 train-test split)")
    print(f"   • class_weight: 'balanced_subsample' (handle regime imbalance)")

    print("\n🔍 Configuration:")
    response = input("  Use agent suggestions? [Y/n/customize]: ").strip().lower()

    if response == "customize":
        n_est = input("  Number of trees [500]: ").strip()
        max_d = input("  Max depth [None]: ").strip()
        test_sz = input("  Test size ratio [0.2]: ").strip()

        state["classification_config"] = {
            "n_estimators": int(n_est) if n_est else 500,
            "max_depth": int(max_d) if max_d and max_d.lower() != "none" else None,
            "test_size": float(test_sz) if test_sz else 0.2,
            "class_weight": "balanced_subsample",
            "random_state": 42,
        }
        print(f"\n✅ Custom config: {state['classification_config']}\n")
    else:
        state["classification_config"] = {
            "n_estimators": 500,
            "max_depth": None,
            "test_size": 0.2,
            "class_weight": "balanced_subsample",
            "random_state": 42,
        }
        print("\n✅ Using agent suggestions\n")

    return state


# ============================================================
# VALIDATION 4: Forecasting Configuration (Retraining Periods)
# ============================================================
def validate_forecasting_config(state: PipelineState) -> PipelineState:
    """
    Configure forecasting parameters: retraining windows, horizons, model selection.
    This is CRITICAL for forecast quality and computational cost.
    """
    if state.get("skip_forecast", False):
        return state

    print("\n" + "=" * 70)
    print("🎯 VALIDATION: Forecasting Configuration")
    print("=" * 70)

    # Load current config
    config_path = "configs/features_config.yaml"
    import yaml
    with open(config_path, "r") as f:
        current_config = yaml.safe_load(f)

    # Display current settings
    print(f"\n📋 Current Configuration:")
    for cadence in ["daily", "weekly", "monthly"]:
        if cadence in current_config:
            cfg = current_config[cadence]
            print(f"\n  {cadence.upper()}:")
            print(f"    • Horizon: {cfg.get('horizon')}")
            print(f"    • Validation window: {cfg.get('val_size')}")
            print(f"    • Test size: {cfg.get('test_size', 'auto')}")

    # Agentic suggestions
    print(f"\n\n🤖 Agent Suggestions:")
    print(f"   DAILY (high frequency, short horizon):")
    print(f"     • Horizon: 10 days (2 weeks)")
    print(f"     • Val window: 90 days (3 months for validation)")
    print(f"     • Test size: 30 days")
    print(f"   WEEKLY (medium frequency):")
    print(f"     • Horizon: 4 weeks (1 month)")
    print(f"     • Val window: 26 weeks (6 months)")
    print(f"     • Test size: 8 weeks")
    print(f"   MONTHLY (low frequency, long horizon):")
    print(f"     • Horizon: 3 months (1 quarter)")
    print(f"     • Val window: 12 months (1 year)")
    print(f"     • Test size: 6 months")

    print("\n🔍 Options:")
    print("   1. Use current configuration")
    print("   2. Use agent suggestions")
    print("   3. Customize per cadence\n")

    response = input("Select option [1/2/3]: ").strip()

    if response == "2":
        state["forecasting_config"] = {
            "daily": {"horizon": 10, "val_size": 90, "test_size": 30},
            "weekly": {"horizon": 4, "val_size": 26, "test_size": 8},
            "monthly": {"horizon": 3, "val_size": 12, "test_size": 6},
        }
        print("\n✅ Using agent suggestions\n")

    elif response == "3":
        custom_config = {}
        for cadence in ["daily", "weekly", "monthly"]:
            print(f"\n  Configure {cadence.upper()}:")
            horizon = input(f"    Horizon: ").strip()
            val_size = input(f"    Validation window: ").strip()
            test_size = input(f"    Test size: ").strip()

            custom_config[cadence] = {
                "horizon": int(horizon) if horizon else current_config[cadence]["horizon"],
                "val_size": int(val_size) if val_size else current_config[cadence]["val_size"],
                "test_size": int(test_size) if test_size else current_config[cadence].get("test_size"),
            }

        state["forecasting_config"] = custom_config
        print(f"\n✅ Custom config saved: {custom_config}\n")

    else:
        state["forecasting_config"] = current_config
        print("\n✅ Using current configuration from YAML\n")

    return state


# ============================================================
# VALIDATION 5: Post-Forecast Model Selection & Ensemble Weights
# ============================================================
def validate_forecast_results(state: PipelineState) -> PipelineState:
    """
    Review forecast performance and optionally override ensemble weights.
    Allows disabling underperforming models.
    """
    if state.get("skip_forecast", False) or not state.get("forecast_status", {}).get("success"):
        return state

    print("\n" + "=" * 70)
    print("📊 VALIDATION: Forecast Results & Ensemble Weights")
    print("=" * 70)

    # Load forecast metrics
    metrics_dir = "outputs/forecasting/metrics"
    if os.path.exists(metrics_dir):
        metric_files = [f for f in os.listdir(metrics_dir) if f.endswith(".json")]

        print(f"\n📈 Forecast Performance Summary:")
        print(f"   • Total features forecast: {len(metric_files)}")

        # Aggregate metrics
        all_mae, all_rmse = [], []
        for mfile in metric_files[:5]:  # Show first 5
            with open(os.path.join(metrics_dir, mfile), "r") as f:
                metrics = json.load(f)
                mae = metrics.get("test_mae", 0)
                rmse = metrics.get("test_rmse", 0)
                all_mae.append(mae)
                all_rmse.append(rmse)
                print(f"   • {mfile.replace('.json', '')}: MAE={mae:.4f}, RMSE={rmse:.4f}")

        if all_mae:
            print(f"\n   Average MAE: {np.mean(all_mae):.4f}")
            print(f"   Average RMSE: {np.mean(all_rmse):.4f}")

    print("\n🔍 Options:")
    print("   1. Approve results")
    print("   2. Review detailed metrics")
    print("   3. Override ensemble weights (advanced)\n")

    response = input("Select option [1/2/3]: ").strip()

    if response == "2":
        print(f"\n📂 Detailed metrics available at: {os.path.abspath(metrics_dir)}")
        print(f"   Plots available at: outputs/forecasting/plots/")
        input("   Press Enter to continue...")

    elif response == "3":
        print("\n⚠️  Advanced: Override ensemble weights")
        print("   Current: Auto-learned from validation performance")
        # TODO: Implement ensemble weight override
        print("   Feature coming soon...\n")

    state["forecast_approved"] = True
    return state
