#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nodes.py
LangGraph Nodes for RFP Pipeline
=============================================================
Each node wraps an existing agent and updates the shared state.
Nodes are stateless functions that take state and return updated state.
=============================================================
"""

import os
import time
import shutil
from typing import Dict, Any
from datetime import datetime

from orchestrator.state import PipelineState
from utils.realtime_logger import get_logger


# ============================================================
# UTILITY: Cleanup Logic
# ============================================================
def cleanup_node(state: PipelineState) -> PipelineState:
    """
    Clean workspace before pipeline run.
    Removes old outputs/logs but preserves code and configs.
    """
    if state.get("skip_cleanup", False):
        print("⚙️  Skipping workspace cleanup (--no-clean flag set)\n")
        return state

    print("\n🧹 Cleaning workspace before fresh run...")
    base_dirs = ["outputs", "logs", "lightning_logs"]
    preserved_ext = {".py", ".yaml", ".yml"}

    for base in base_dirs:
        if not os.path.exists(base):
            continue

        for root, dirs, files in os.walk(base):
            for file in files:
                path = os.path.join(root, file)
                _, ext = os.path.splitext(file)
                if ext not in preserved_ext:
                    try:
                        os.remove(path)
                    except Exception:
                        pass

            # Remove empty directories
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

    print("✅ Workspace cleaned successfully.\n")
    return state


# ============================================================
# NODE 1: Data Fetching
# ============================================================
def fetch_node(state: PipelineState) -> PipelineState:
    """
    Fetch raw data from Yahoo Finance and FRED.
    Wraps data_agent.fetcher.run_fetcher()
    """
    if state.get("skip_fetch", False):
        print("⏭️  Skipping data fetch (--skip-fetch flag set)\n")
        state["fetch_status"] = {"skipped": True}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 1: Data Fetching")
    print("=" * 70 + "\n")

    # Real-time logging
    logger = get_logger()
    logger.stage("Data Fetching")

    start_time = time.time()

    try:
        from data_agent.fetcher import run_fetcher

        # Run the fetcher with BigQuery enabled (always use BigQuery in production)
        use_bigquery = not state.get("use_local_storage", False)
        logger.info(f"Starting data fetch (BigQuery: {use_bigquery})")
        run_fetcher(use_bigquery=use_bigquery)

        # Small delay to ensure BigQuery updates are committed
        if use_bigquery:
            print("⏳ Waiting for BigQuery to commit updates...")
            time.sleep(2)  # 2 second delay

        # Update state with success
        elapsed = time.time() - start_time
        state["fetch_status"] = {
            "success": True,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["cleaned_data_path"] = "outputs/fetched/cleaned"

        print(f"✅ Data fetching completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Data fetch completed ({elapsed:.1f}s) - Saved to BigQuery")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "fetch",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["fetch_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Data fetching failed: {e}\n")
        logger.error(f"Data fetch FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state


# ============================================================
# NODE 2: Feature Engineering
# ============================================================
def engineer_node(state: PipelineState) -> PipelineState:
    """
    Generate derived features from raw data.
    Wraps data_agent.engineer.engineer_features()
    """
    if state.get("skip_engineer", False):
        print("⏭️  Skipping feature engineering (--skip-engineer flag set)\n")
        state["engineer_status"] = {"skipped": True}
        return state

    # Check if previous stage succeeded
    if not state.get("fetch_status", {}).get("success", False) and not state.get("skip_fetch", False):
        print("⚠️  Cannot engineer features: data fetching failed or was skipped\n")
        state["engineer_status"] = {"success": False, "error": "Dependency failed"}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 2: Feature Engineering")
    print("=" * 70 + "\n")

    # Real-time logging
    logger = get_logger()
    logger.stage("Feature Engineering")

    start_time = time.time()

    try:
        from data_agent.engineer import engineer_features

        # Run feature engineering
        # Always use BigQuery in production (GitHub Actions always has BigQuery credentials)
        logger.info("Starting feature engineering (BigQuery: True)")
        engineer_features(use_bigquery=True)

        # Update state
        elapsed = time.time() - start_time
        state["engineer_status"] = {
            "success": True,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["engineered_data_path"] = "outputs/engineered"

        print(f"✅ Feature engineering completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Feature engineering completed ({elapsed:.1f}s) - Saved to BigQuery")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "engineer",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["engineer_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Feature engineering failed: {e}\n")
        logger.error(f"Feature engineering FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state


# ============================================================
# NODE 3: Feature Selection
# ============================================================
def select_node(state: PipelineState) -> PipelineState:
    """
    Align and select features using PCA + correlation + mRMR.
    Wraps data_agent.selector.run_selector()
    """
    if state.get("skip_select", False):
        print("⏭️  Skipping feature selection (--skip-select flag set)\n")
        state["select_status"] = {"skipped": True}
        return state

    # Check dependencies
    if not state.get("engineer_status", {}).get("success", False) and not state.get("skip_engineer", False):
        print("⚠️  Cannot select features: engineering failed or was skipped\n")
        state["select_status"] = {"success": False, "error": "Dependency failed"}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 3: Feature Selection")
    print("=" * 70 + "\n")

    # Real-time logging
    logger = get_logger()
    logger.stage("Feature Selection")

    start_time = time.time()

    try:
        from data_agent.selector import run_selector

        # Run feature selection
        # Always use BigQuery in production
        logger.info("Starting feature selection (PCA + correlation + mRMR, BigQuery: True)")
        run_selector(use_bigquery=True)

        # Update state
        elapsed = time.time() - start_time
        state["select_status"] = {
            "success": True,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["selected_features_path"] = "outputs/selected/aligned_dataset.parquet"

        print(f"✅ Feature selection completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Feature selection completed ({elapsed:.1f}s) - Selected features saved to BigQuery")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "select",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["select_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Feature selection failed: {e}\n")
        logger.error(f"Feature selection FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state


# ============================================================
# NODE 4: Clustering (HMM Regime Detection)
# ============================================================
def cluster_node(state: PipelineState) -> PipelineState:
    """
    Run HMM clustering to identify market regimes.
    Wraps clustering_agent.clustering.run_hmm_clustering()
    """
    if state.get("skip_cluster", False):
        print("⏭️  Skipping clustering (--skip-cluster flag set)\n")
        state["cluster_status"] = {"skipped": True}
        return state

    # Check dependencies
    if not state.get("select_status", {}).get("success", False) and not state.get("skip_select", False):
        print("⚠️  Cannot run clustering: feature selection failed or was skipped\n")
        state["cluster_status"] = {"success": False, "error": "Dependency failed"}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 4: Regime Clustering (HMM)")
    print("=" * 70 + "\n")

    # Real-time logging
    logger = get_logger()
    logger.stage("Regime Clustering (HMM)")

    start_time = time.time()

    try:
        from clustering_agent.clustering import run_hmm_clustering
        from clustering_agent.validate import visualize_regimes

        # Run HMM clustering
        # Always use BigQuery in production
        logger.info("Starting HMM clustering (BigQuery: True)")
        df_out, stats = run_hmm_clustering(use_bigquery=True)

        # Visualize regimes (optional - skip if files not available)
        try:
            print("\n📈 Generating regime visualization...")
            visualize_regimes(feature_for_overlay="ret_GSPC")
            logger.info("Regime visualization generated successfully")
        except FileNotFoundError as e:
            print(f"⚠️  Skipping visualization (files not available): {e}")
            logger.warning(f"Skipping visualization: {e}")

        # Update state
        elapsed = time.time() - start_time
        n_regimes = len(stats) if stats is not None else 3
        state["cluster_status"] = {
            "success": True,
            "n_regimes": n_regimes,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["cluster_assignments_path"] = "outputs/clustering/cluster_assignments.parquet"

        print(f"✅ Clustering completed successfully in {elapsed:.2f}s\n")
        logger.success(f"HMM clustering completed ({elapsed:.1f}s) - {n_regimes} regimes detected, saved to BigQuery")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "cluster",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["cluster_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Clustering failed: {e}\n")
        logger.error(f"HMM clustering FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state


# ============================================================
# NODE 5: Classification (Regime Prediction)
# ============================================================
def classify_node(state: PipelineState) -> PipelineState:
    """
    Train Random Forest classifier to predict regimes.
    Wraps classification_agent.classifier.train_regime_classifier()
    """
    if state.get("skip_classify", False):
        print("⏭️  Skipping classification (--skip-classify flag set)\n")
        state["classify_status"] = {"skipped": True}
        return state

    # Check dependencies (needs both selection and clustering)
    if not state.get("cluster_status", {}).get("success", False) and not state.get("skip_cluster", False):
        print("⚠️  Cannot train classifier: clustering failed or was skipped\n")
        state["classify_status"] = {"success": False, "error": "Dependency failed"}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 5: Regime Classification")
    print("=" * 70 + "\n")

    # Real-time logging
    logger = get_logger()
    logger.stage("Regime Classification")

    start_time = time.time()

    try:
        from classification_agent.classifier import train_regime_classifier

        # Train classifier
        # Always use BigQuery in production
        logger.info("Starting Random Forest classifier training (BigQuery: True)")
        train_regime_classifier(use_bigquery=True)

        # Update state
        elapsed = time.time() - start_time
        state["classify_status"] = {
            "success": True,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["classifier_model_path"] = "outputs/models/regime_classifier.joblib"

        print(f"✅ Classification completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Regime classifier trained ({elapsed:.1f}s) - Model saved")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "classify",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["classify_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Classification failed: {e}\n")
        logger.error(f"Regime classification FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state


# ============================================================
# NODE 6: Forecasting (Time Series Prediction)
# ============================================================
def forecast_node(state: PipelineState) -> PipelineState:
    """
    Run ensemble forecasting on selected features.
    Wraps forecasting_agent.forecaster.run_forecasting_agent()
    """
    if state.get("skip_forecast", False):
        print("⏭️  Skipping forecasting (--skip-forecast flag set)\n")
        state["forecast_status"] = {"skipped": True}
        return state

    # Check dependencies (needs cleaned data at minimum)
    if not state.get("fetch_status", {}).get("success", False) and not state.get("skip_fetch", False):
        print("⚠️  Cannot run forecasting: data fetching failed or was skipped\n")
        state["forecast_status"] = {"success": False, "error": "Dependency failed"}
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 6: Time Series Forecasting")
    print("=" * 70 + "\n")

    start_time = time.time()

    try:
        import sys
        from forecasting_agent import forecaster
        from orchestrator.intelligent_model_checker import get_intelligent_recommendation

        # Real-time logging
        logger = get_logger()
        logger.stage("Forecasting - Intelligent Model Check")

        # Get intelligent recommendation for selective training
        recommendation = get_intelligent_recommendation()

        print(f"\n🧠 Intelligent Model Checker Results:")
        print(f"   Workflow: {recommendation['workflow']}")
        print(f"   Reason: {recommendation['reason']}")

        logger.info(f"Intelligent Decision: {recommendation['workflow']}")
        logger.info(f"Reason: {recommendation['reason']}")

        # Determine if we should train forecasting models
        if recommendation['workflow'] == 'inference':
            # All models fresh - skip forecasting training
            print("✅ All forecasting models are fresh. Skipping forecasting stage.\n")
            state["forecast_status"] = {
                "success": True,
                "skipped": True,
                "reason": "All models fresh",
                "elapsed_seconds": 0,
                "timestamp": datetime.now().isoformat(),
            }
            return state

        # Determine config path
        config_path = "configs/features_config.yaml"
        if not os.path.exists(config_path):
            config_path = "configs/features_config.yml"

        # Run forecasting with mode from state or intelligent recommendation
        mode = state.get("forecast_mode", "all")
        single_daily = state.get("single_daily")
        single_weekly = state.get("single_weekly")
        single_monthly = state.get("single_monthly")

        # Use selective features if partial training recommended
        selective_features = None
        if recommendation['workflow'] == 'partial_train' and recommendation['features_to_train']:
            selective_features = recommendation['features_to_train']
            print(f"🎯 Partial training mode: {len(selective_features)} features need training\n")
            logger.info(f"Partial training: {len(selective_features)} features ({', '.join(selective_features[:5])}...)")

        print(f"📄 Using config: {config_path}")
        print(f"🎯 Forecast mode: {mode}\n")

        logger.stage(f"Forecasting - Training Models")

        forecaster.run_forecasting_agent(
            mode=mode,
            config_path=config_path,
            single_daily=single_daily,
            single_weekly=single_weekly,
            single_monthly=single_monthly,
            use_bigquery=True,  # Always use BigQuery in production
            force_retrain=False,  # Let auto-detection decide
            selective_features=selective_features  # Train only needed features
        )

        # Update state
        elapsed = time.time() - start_time
        state["forecast_status"] = {
            "success": True,
            "mode": mode,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["forecast_output_path"] = "outputs/forecasting"

        print(f"✅ Forecasting completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Forecasting completed ({elapsed:.1f}s) - Models trained and saved")
        logger.commit_to_github()  # Commit log immediately after stage completes

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "forecast",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["forecast_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Forecasting failed: {e}\n")
        logger.error(f"Forecasting FAILED: {e}")
        logger.commit_to_github()  # Commit log even on failure

    return state
