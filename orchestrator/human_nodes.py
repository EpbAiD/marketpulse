#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
human_nodes.py
Human-in-the-Loop Intervention Nodes
=============================================================
These nodes pause execution and wait for human approval or input.
They display relevant diagnostics and allow users to override
default behavior or provide guidance.
=============================================================
"""

import os
import pandas as pd
from typing import Dict, Any
from orchestrator.state import PipelineState


# ============================================================
# HELPER: Display state summary
# ============================================================
def display_stage_summary(stage_name: str, status: Dict[str, Any]):
    """Pretty-print stage status for human review."""
    print("\n" + "=" * 70)
    print(f"📋 {stage_name} Summary")
    print("=" * 70)

    for key, value in status.items():
        if key == "elapsed_seconds":
            print(f"   ⏱️  Runtime: {value:.2f}s")
        elif key == "timestamp":
            print(f"   🕐 Completed: {value}")
        elif key == "success":
            icon = "✅" if value else "❌"
            print(f"   {icon} Success: {value}")
        else:
            print(f"   • {key}: {value}")
    print("=" * 70 + "\n")


# ============================================================
# HUMAN NODE 1: Review Fetch Results
# ============================================================
def review_fetch_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after data fetching.
    Shows missingness reports and allows imputation override.
    """
    if state.get("skip_fetch", False) or not state.get("fetch_status", {}).get("success", False):
        # Skip review if fetch was skipped or failed
        state["fetch_approved"] = True
        return state

    display_stage_summary("Data Fetching", state["fetch_status"])

    # Show missingness diagnostics if available
    diag_dir = "outputs/diagnostics/fetcher"
    if os.path.exists(diag_dir):
        print("📊 Missingness diagnostics available at:", diag_dir)
        print("   Review heatmaps and null counts before proceeding.\n")

    # Prompt for approval
    print("🔍 Review the fetched data quality:")
    print("   1. Check missingness heatmaps in outputs/diagnostics/fetcher/")
    print("   2. Review outputs/fetched/cleaned/ for cleaned data\n")

    response = input("Approve data fetching results? [Y/n/review]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["fetch_approved"] = True
        print("✅ Fetch results approved. Proceeding...\n")

    elif response == "review":
        print("\n📂 Opening diagnostics directory...")
        print(f"   Please review: {os.path.abspath(diag_dir)}")
        print("   Press Enter when ready to approve...")
        input()
        state["fetch_approved"] = True

    else:
        print("❌ Fetch results not approved. Pipeline will abort.")
        state["fetch_approved"] = False
        state["abort_pipeline"] = True

    return state


# ============================================================
# HUMAN NODE 2: Review Engineering Results
# ============================================================
def review_engineer_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after feature engineering.
    Shows feature summary and allows exclusions.
    """
    if state.get("skip_engineer", False) or not state.get("engineer_status", {}).get("success", False):
        state["engineer_approved"] = True
        return state

    display_stage_summary("Feature Engineering", state["engineer_status"])

    # Count engineered features
    eng_dir = "outputs/engineered"
    if os.path.exists(eng_dir):
        n_features = len([f for f in os.listdir(eng_dir) if f.endswith(".parquet")])
        print(f"📊 Total engineered feature sets: {n_features}")
        print(f"   Location: {os.path.abspath(eng_dir)}\n")

    # Show diagnostics
    diag_dir = "outputs/diagnostics/engineer"
    if os.path.exists(diag_dir):
        print(f"📊 Engineering diagnostics: {os.path.abspath(diag_dir)}\n")

    print("🔍 Review the engineered features:")
    print("   1. Check feature distributions and nulls")
    print("   2. Verify sanitization (inf/NaN handling)\n")

    response = input("Approve engineered features? [Y/n/exclude]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["engineer_approved"] = True
        print("✅ Engineered features approved. Proceeding...\n")

    elif response == "exclude":
        print("\nEnter feature names to exclude (comma-separated):")
        exclusions = input("Features to exclude: ").strip()
        if exclusions:
            state["feature_exclusions"] = [f.strip() for f in exclusions.split(",")]
            print(f"🚫 Will exclude: {state['feature_exclusions']}\n")
        state["engineer_approved"] = True

    else:
        print("❌ Engineered features not approved. Pipeline will abort.")
        state["engineer_approved"] = False
        state["abort_pipeline"] = True

    return state


# ============================================================
# HUMAN NODE 3: Review Feature Selection
# ============================================================
def review_select_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after feature selection.
    Shows selected features and allows manual adjustments.
    """
    if state.get("skip_select", False) or not state.get("select_status", {}).get("success", False):
        state["select_approved"] = True
        return state

    display_stage_summary("Feature Selection", state["select_status"])

    # Load and display selected features
    selected_path = "outputs/selected/features_selected.csv"
    if os.path.exists(selected_path):
        df = pd.read_csv(selected_path)
        print("📋 Selected Features:")
        print(df.to_string(index=False))
        print(f"\n   Total features selected: {len(df)}\n")
    else:
        print("⚠️  No features_selected.csv found\n")

    # Show diagnostics
    diag_dir = "outputs/diagnostics/selector"
    if os.path.exists(diag_dir):
        print(f"📊 Selection diagnostics: {os.path.abspath(diag_dir)}")
        print("   Review PCA plots, correlation heatmaps, and mRMR rankings\n")

    print("🔍 Review the feature selection:")
    print("   1. Verify selected features make domain sense")
    print("   2. Check PCA variance explained")
    print("   3. Review correlation structure\n")

    response = input("Approve feature selection? [Y/n/modify]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["select_approved"] = True
        print("✅ Feature selection approved. Proceeding...\n")

    elif response == "modify":
        print("\nManual feature adjustments:")
        additions = input("  Force include features (comma-separated, or Enter to skip): ").strip()
        removals = input("  Force exclude features (comma-separated, or Enter to skip): ").strip()

        if additions:
            state["manual_feature_additions"] = [f.strip() for f in additions.split(",")]
            print(f"  ➕ Will add: {state['manual_feature_additions']}")

        if removals:
            state["manual_feature_removals"] = [f.strip() for f in removals.split(",")]
            print(f"  ➖ Will remove: {state['manual_feature_removals']}")

        state["select_approved"] = True
        print("\n✅ Feature selection approved with modifications.\n")

    else:
        print("❌ Feature selection not approved. Pipeline will abort.")
        state["select_approved"] = False
        state["abort_pipeline"] = True

    return state


# ============================================================
# HUMAN NODE 4: Review Clustering Results
# ============================================================
def review_cluster_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after regime clustering.
    Shows regime statistics and timeline visualization.
    """
    if state.get("skip_cluster", False) or not state.get("cluster_status", {}).get("success", False):
        state["cluster_approved"] = True
        return state

    display_stage_summary("Regime Clustering", state["cluster_status"])

    # Show cluster statistics
    stats_path = "outputs/clustering/cluster_stats.csv"
    if os.path.exists(stats_path):
        df = pd.read_csv(stats_path)
        print("📊 Regime Statistics:")
        print(df.to_string(index=False))
        print()

    # Show visualization
    viz_path = "outputs/diagnostics/clustering/hmm_sequence.png"
    if os.path.exists(viz_path):
        print(f"📈 Regime timeline visualization: {os.path.abspath(viz_path)}\n")

    print("🔍 Review the regime clustering:")
    print("   1. Check if regimes are distinct and meaningful")
    print("   2. Review regime transitions over time")
    print("   3. Verify cluster statistics\n")

    response = input("Approve clustering results? [Y/n/retune]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["cluster_approved"] = True
        print("✅ Clustering results approved. Proceeding...\n")

    elif response == "retune":
        print("\nClustering parameters:")
        n_regimes = input("  Number of regimes (default 3): ").strip()

        if n_regimes and n_regimes.isdigit():
            state["regime_override"] = int(n_regimes)
            state["retry_stage"] = "cluster"
            print(f"  🔄 Will retry clustering with {n_regimes} regimes\n")
        else:
            print("  ⚠️  Invalid input, keeping current results\n")

        state["cluster_approved"] = True

    else:
        print("❌ Clustering results not approved. Pipeline will abort.")
        state["cluster_approved"] = False
        state["abort_pipeline"] = True

    return state


# ============================================================
# HUMAN NODE 5: Review Classification Results
# ============================================================
def review_classify_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after regime classification.
    Shows confusion matrix and feature importance.
    """
    if state.get("skip_classify", False) or not state.get("classify_status", {}).get("success", False):
        state["classify_approved"] = True
        return state

    display_stage_summary("Regime Classification", state["classify_status"])

    # Show metrics
    metrics_path = "outputs/diagnostics/classification/metrics_report.json"
    if os.path.exists(metrics_path):
        import json
        with open(metrics_path, "r") as f:
            metrics = json.load(f)
        print("📊 Classification Metrics:")
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"   • {key}: {value:.4f}")
            else:
                print(f"   • {key}: {value}")
        print()

    # Show diagnostics paths
    diag_dir = "outputs/diagnostics/classification"
    if os.path.exists(diag_dir):
        print(f"📊 Classification diagnostics: {os.path.abspath(diag_dir)}")
        print("   - Confusion matrix")
        print("   - Feature importances\n")

    print("🔍 Review the classification results:")
    print("   1. Check accuracy and F1 scores")
    print("   2. Review confusion matrix for misclassifications")
    print("   3. Verify feature importances make sense\n")

    response = input("Approve classification results? [Y/n]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["classify_approved"] = True
        print("✅ Classification results approved. Proceeding...\n")

    else:
        print("❌ Classification results not approved. Pipeline will abort.")
        state["classify_approved"] = False
        state["abort_pipeline"] = True

    return state


# ============================================================
# HUMAN NODE 6: Review Forecast Results
# ============================================================
def review_forecast_node(state: PipelineState) -> PipelineState:
    """
    Human checkpoint after forecasting.
    Shows forecast metrics and diagnostic plots.
    """
    if state.get("skip_forecast", False) or not state.get("forecast_status", {}).get("success", False):
        state["forecast_approved"] = True
        return state

    display_stage_summary("Time Series Forecasting", state["forecast_status"])

    # Show metrics directory
    metrics_dir = "outputs/forecasting/metrics"
    if os.path.exists(metrics_dir):
        n_metrics = len([f for f in os.listdir(metrics_dir) if f.endswith(".json")])
        print(f"📊 Forecast metrics: {n_metrics} features")
        print(f"   Location: {os.path.abspath(metrics_dir)}\n")

    # Show plots directory
    plots_dir = "outputs/forecasting/plots"
    if os.path.exists(plots_dir):
        print(f"📈 Forecast plots: {os.path.abspath(plots_dir)}\n")

    print("🔍 Review the forecast results:")
    print("   1. Check MAE/RMSE/MAPE metrics")
    print("   2. Review forecast vs actual plots")
    print("   3. Examine residual diagnostics\n")

    response = input("Approve forecast results? [Y/n]: ").strip().lower()

    if response in ["y", "yes", ""]:
        state["forecast_approved"] = True
        print("✅ Forecast results approved. Pipeline complete!\n")

    else:
        print("❌ Forecast results not approved.")
        state["forecast_approved"] = False

    return state
