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
    Smart cleanup that preserves models that don't need retraining.

    Uses intelligent_model_checker to determine what to preserve:
    - Core models (HMM/RF) are preserved if fresh (< 30 days old)
    - Feature models are preserved if not in selective_features list
    - Always clean: logs, lightning_logs, temporary files
    """
    if state.get("skip_cleanup", False):
        print("⚙️  Skipping workspace cleanup (--no-clean flag set)\n")
        return state

    print("\n🧹 Smart cleanup (preserving fresh models)...")

    # Import intelligent model checker to determine what needs retraining
    from orchestrator.intelligent_model_checker import check_core_models_status

    core_status = check_core_models_status()
    selective_features = state.get("selective_features", None)

    # Directories/files to always preserve
    preserved_ext = {".py", ".yaml", ".yml"}

    # Paths to preserve based on model freshness
    preserved_paths = set()

    # Check if core models are fresh (don't need retraining)
    core_needs_training = core_status['needs_training']
    if not core_needs_training:
        # Preserve core models (HMM, classifier, cluster assignments)
        preserved_paths.add("outputs/models/hmm_model.joblib")
        preserved_paths.add("outputs/models/regime_classifier.joblib")
        preserved_paths.add("outputs/clustering/cluster_assignments.parquet")
        print(f"   📦 Preserving core models (fresh, {core_status.get('age_days', '?')} days old < {core_status.get('threshold_days', 30)} day threshold)")

    if selective_features is not None:
        # Preserve feature models NOT in selective_features list
        forecasting_models_dir = "outputs/forecasting/models"
        if os.path.exists(forecasting_models_dir):
            for feature_dir in os.listdir(forecasting_models_dir):
                feature_path = os.path.join(forecasting_models_dir, feature_dir)
                # Check if it's a feature directory (not a json file)
                if os.path.isdir(feature_path) and feature_dir not in (selective_features or []):
                    # Preserve this feature's model directory
                    preserved_paths.add(feature_path)
                # Also preserve version json files for features not being retrained
                if feature_dir.endswith("_versions.json"):
                    feature_name = feature_dir.replace("_versions.json", "")
                    if feature_name not in (selective_features or []):
                        preserved_paths.add(os.path.join(forecasting_models_dir, feature_dir))

        if selective_features:
            print(f"   🎯 Preserving {22 - len(selective_features)} fresh feature models")
        else:
            print("   📊 Preserving all feature models (none need retraining)")

    # Clean logs and lightning_logs (always)
    for base in ["logs", "lightning_logs"]:
        if os.path.exists(base):
            for root, dirs, files in os.walk(base):
                for file in files:
                    path = os.path.join(root, file)
                    _, ext = os.path.splitext(file)
                    if ext not in preserved_ext:
                        try:
                            os.remove(path)
                        except Exception:
                            pass

    # Clean outputs directory (selectively)
    base = "outputs"
    if os.path.exists(base):
        for root, dirs, files in os.walk(base, topdown=False):
            for file in files:
                path = os.path.join(root, file)
                _, ext = os.path.splitext(file)

                # Check if this path should be preserved
                should_preserve = ext in preserved_ext

                # Check against preserved paths
                for pp in preserved_paths:
                    if path.startswith(pp) or path == pp:
                        should_preserve = True
                        break

                if not should_preserve:
                    try:
                        os.remove(path)
                    except Exception:
                        pass

            # Remove empty directories (but not preserved model directories)
            for d in dirs:
                dir_path = os.path.join(root, d)
                # Don't remove if it's a preserved path
                if dir_path in preserved_paths:
                    continue
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

    print("✅ Smart cleanup completed.\n")
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

    Uses intelligent model detection to decide whether to train or use existing:
    - If HMM model exists AND is fresh (< 30 days old): use existing model
    - If HMM model missing OR stale (> 30 days old): train new model

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

    # Import intelligent model checker to determine if HMM needs training
    from orchestrator.intelligent_model_checker import check_core_models_status

    core_status = check_core_models_status()
    hmm_exists = core_status['hmm_exists']
    hmm_age_days = core_status.get('hmm_age_days')
    threshold = core_status.get('threshold_days', 30)

    # Determine if HMM needs training: missing OR stale (> threshold days)
    hmm_needs_training = not hmm_exists or (hmm_age_days is not None and hmm_age_days > threshold)

    if not hmm_needs_training:
        print("\n" + "=" * 70)
        print("🚀 STAGE 4: Regime Clustering (HMM) - USING EXISTING MODEL")
        print("=" * 70 + "\n")
        print(f"📦 HMM model is fresh ({hmm_age_days} days old, threshold: {threshold} days)")
        print(f"✅ Using existing HMM model: outputs/models/hmm_model.joblib\n")

        logger = get_logger()
        logger.info(f"Using existing HMM model ({hmm_age_days} days old < {threshold} day threshold)")
        logger.commit_to_github()

        state["cluster_status"] = {
            "success": True,
            "used_existing": True,
            "model_age_days": hmm_age_days,
            "threshold_days": threshold,
            "model_path": "outputs/models/hmm_model.joblib",
            "timestamp": datetime.now().isoformat(),
        }
        state["cluster_assignments_path"] = "outputs/clustering/cluster_assignments.parquet"
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 4: Regime Clustering (HMM) - TRAINING NEW MODEL")
    print("=" * 70 + "\n")
    if not hmm_exists:
        print("📦 HMM model does not exist - training new model")
    else:
        print(f"📦 HMM model is stale ({hmm_age_days} days old > {threshold} day threshold)")
    print()

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

    Uses intelligent model detection to decide whether to train or use existing:
    - If RF classifier exists AND is fresh (< 30 days old): use existing model
    - If RF classifier missing OR stale (> 30 days old): train new model

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

    # Import intelligent model checker to determine if classifier needs training
    from orchestrator.intelligent_model_checker import check_core_models_status

    core_status = check_core_models_status()
    classifier_exists = core_status['classifier_exists']
    classifier_age_days = core_status.get('classifier_age_days')
    threshold = core_status.get('threshold_days', 30)

    # Determine if classifier needs training: missing OR stale (> threshold days)
    classifier_needs_training = not classifier_exists or (classifier_age_days is not None and classifier_age_days > threshold)

    if not classifier_needs_training:
        print("\n" + "=" * 70)
        print("🚀 STAGE 5: Regime Classification - USING EXISTING MODEL")
        print("=" * 70 + "\n")
        print(f"📦 RF classifier is fresh ({classifier_age_days} days old, threshold: {threshold} days)")
        print(f"✅ Using existing classifier: outputs/models/regime_classifier.joblib\n")

        logger = get_logger()
        logger.info(f"Using existing RF classifier ({classifier_age_days} days old < {threshold} day threshold)")
        logger.commit_to_github()

        state["classify_status"] = {
            "success": True,
            "used_existing": True,
            "model_age_days": classifier_age_days,
            "threshold_days": threshold,
            "model_path": "outputs/models/regime_classifier.joblib",
            "timestamp": datetime.now().isoformat(),
        }
        state["classifier_model_path"] = "outputs/models/regime_classifier.joblib"
        return state

    print("\n" + "=" * 70)
    print("🚀 STAGE 5: Regime Classification - TRAINING NEW MODEL")
    print("=" * 70 + "\n")
    if not classifier_exists:
        print("📦 RF classifier does not exist - training new model")
    else:
        print(f"📦 RF classifier is stale ({classifier_age_days} days old > {threshold} day threshold)")
    print()

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

    Uses selective_features from state (set by auto mode) to train only
    the features that need training, not all 22.
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
        from forecasting_agent import forecaster

        # Real-time logging
        logger = get_logger()
        logger.stage("Forecasting")

        # Get selective features from state (set by auto mode in run_pipeline.py)
        # If None, train all features; if list, train only those features
        selective_features = state.get("selective_features", None)

        # Determine config path
        config_path = "configs/features_config.yaml"
        if not os.path.exists(config_path):
            config_path = "configs/features_config.yml"

        # Run forecasting with mode from state
        mode = state.get("forecast_mode", "all")
        single_daily = state.get("single_daily")
        single_weekly = state.get("single_weekly")
        single_monthly = state.get("single_monthly")

        # Log what we're doing
        if selective_features:
            print(f"🎯 Selective training: {len(selective_features)} features")
            print(f"   Features: {', '.join(sorted(selective_features))}\n")
            logger.info(f"Selective training: {len(selective_features)} features ({', '.join(selective_features[:5])}{'...' if len(selective_features) > 5 else ''})")
        elif selective_features == []:
            # Empty list means no features need training
            print("✅ All forecasting models are fresh. Skipping forecasting stage.\n")
            logger.success("All forecasting models are fresh - Skipping training")
            logger.commit_to_github()
            state["forecast_status"] = {
                "success": True,
                "skipped": True,
                "reason": "All models fresh",
                "elapsed_seconds": 0,
                "timestamp": datetime.now().isoformat(),
            }
            return state
        else:
            print("📊 Training all feature models\n")
            logger.info("Training all feature models")

        print(f"📄 Using config: {config_path}")
        print(f"🎯 Forecast mode: {mode}\n")

        logger.stage("Forecasting - Training Models")
        logger.commit_to_github()

        forecaster.run_forecasting_agent(
            mode=mode,
            config_path=config_path,
            single_daily=single_daily,
            single_weekly=single_weekly,
            single_monthly=single_monthly,
            use_bigquery=True,  # Always use BigQuery in production
            force_retrain=False,  # Let auto-detection decide
            selective_features=selective_features  # Train only needed features (None = all)
        )

        # Update state
        elapsed = time.time() - start_time
        state["forecast_status"] = {
            "success": True,
            "mode": mode,
            "selective_features": selective_features,
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["forecast_output_path"] = "outputs/forecasting"

        print(f"✅ Forecasting completed successfully in {elapsed:.2f}s\n")
        logger.success(f"Forecasting completed ({elapsed:.1f}s) - Models trained and saved")
        logger.commit_to_github()

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
        logger.commit_to_github()

    return state
