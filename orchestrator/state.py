#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
state.py
LangGraph State Schema for RFP Pipeline
=============================================================
Defines the shared state that flows through all graph nodes.
This state is accessible and modifiable by all nodes in the
pipeline, enabling coordination and human intervention.
=============================================================
"""

from typing import TypedDict, Literal, Optional, Dict, List, Any
from datetime import datetime


class PipelineState(TypedDict, total=False):
    """
    Shared state for the entire RFP pipeline.

    All fields are optional (total=False) to support incremental
    state building as the pipeline progresses.
    """

    # ============================================================
    # CONFIGURATION & METADATA
    # ============================================================
    run_id: str  # Unique identifier for this pipeline run
    timestamp: str  # ISO format timestamp of pipeline start
    config_dir: str  # Path to configs directory
    output_dir: str  # Path to outputs directory

    # ============================================================
    # EXECUTION FLAGS (from CLI args)
    # ============================================================
    # Workflow type
    workflow_type: Literal["training", "inference", "full"]  # training=train models, inference=predict regimes, full=both

    # Training stages
    skip_fetch: bool
    skip_engineer: bool
    skip_select: bool
    skip_cluster: bool
    skip_classify: bool
    skip_forecast: bool
    skip_cleanup: bool

    # Inference/monitoring stages
    skip_inference: bool
    skip_alerts: bool
    skip_validation: bool
    skip_monitoring: bool

    # Forecasting mode flags
    forecast_mode: Literal["all", "single"]
    single_daily: Optional[str]
    single_weekly: Optional[str]
    single_monthly: Optional[str]

    # Intelligent auto-mode flags (from intelligent_model_checker)
    selective_features: Optional[List[str]]  # Features that need training (None = train all)
    retrain_core: bool  # Whether to retrain HMM/RF classifier

    # ============================================================
    # STAGE STATUS TRACKING
    # ============================================================
    # Training stages
    fetch_status: Dict[str, Any]  # {success: bool, files_created: int, errors: []}
    engineer_status: Dict[str, Any]  # {success: bool, features_engineered: int}
    select_status: Dict[str, Any]  # {success: bool, features_selected: int}
    cluster_status: Dict[str, Any]  # {success: bool, n_regimes: int, model_path: str}
    classify_status: Dict[str, Any]  # {success: bool, accuracy: float, model_path: str}
    forecast_status: Dict[str, Any]  # {success: bool, features_forecast: int}

    # Inference/monitoring stages
    inference_status: Dict[str, Any]  # {success: bool, forecast_id: str, predictions: int}
    alerts_status: Dict[str, Any]  # {success: bool, alert_triggered: bool, shifts_detected: int}
    validation_status: Dict[str, Any]  # {success: bool, avg_smape: float, needs_retraining: bool}
    monitoring_status: Dict[str, Any]  # {success: bool, should_retrain: bool, retrain_reason: str}

    # ============================================================
    # HUMAN DECISION POINTS
    # ============================================================
    # Post-fetch decisions
    fetch_approved: bool
    missingness_override: Optional[Dict[str, str]]  # {feature: imputation_method}

    # Post-engineer decisions
    engineer_approved: bool
    feature_exclusions: Optional[List[str]]  # Features to exclude from selection

    # Post-select decisions
    select_approved: bool
    manual_feature_additions: Optional[List[str]]  # Force include these features
    manual_feature_removals: Optional[List[str]]  # Force exclude these features

    # Post-cluster decisions
    cluster_approved: bool
    regime_override: Optional[int]  # Override number of regimes

    # Post-classify decisions
    classify_approved: bool
    retrain_classifier: bool  # If accuracy is low, retrain with different params

    # Post-forecast decisions
    forecast_approved: bool
    ensemble_weight_override: Optional[Dict[str, float]]  # Override model weights

    # ============================================================
    # INTERMEDIATE ARTIFACTS (paths to generated files)
    # ============================================================
    raw_data_path: Optional[str]
    cleaned_data_path: Optional[str]
    engineered_data_path: Optional[str]
    selected_features_path: Optional[str]
    cluster_assignments_path: Optional[str]
    classifier_model_path: Optional[str]
    forecast_output_path: Optional[str]

    # ============================================================
    # DIAGNOSTICS & METRICS
    # ============================================================
    diagnostics: Dict[str, Any]  # Collected diagnostics from all stages
    performance_metrics: Dict[str, Any]  # Runtime metrics per stage

    # ============================================================
    # ERROR HANDLING
    # ============================================================
    errors: List[Dict[str, Any]]  # {stage: str, error: str, timestamp: str}
    warnings: List[Dict[str, Any]]  # {stage: str, warning: str}

    # ============================================================
    # CONDITIONAL ROUTING FLAGS
    # ============================================================
    needs_human_review: bool  # Set to True to trigger human intervention
    retry_stage: Optional[str]  # Which stage to retry (if any)
    abort_pipeline: bool  # Emergency stop flag
    needs_retraining: bool  # Set by monitoring to trigger retraining

    # Results from inference/monitoring
    regime_forecast_id: Optional[str]  # Forecast ID from inference
    alert_result: Optional[Dict[str, Any]]  # Alert check results
    validation_result: Optional[Dict[str, Any]]  # Validation results
    monitoring_result: Optional[Dict[str, Any]]  # Monitoring results


def create_initial_state(
    run_id: Optional[str] = None,
    workflow_type: str = "full",
    skip_fetch: bool = False,
    skip_engineer: bool = False,
    skip_select: bool = False,
    skip_cluster: bool = False,
    skip_classify: bool = False,
    skip_forecast: bool = False,
    skip_inference: bool = False,
    skip_alerts: bool = False,
    skip_validation: bool = False,
    skip_monitoring: bool = False,
    skip_cleanup: bool = False,
    forecast_mode: str = "all",
    single_daily: Optional[str] = None,
    single_weekly: Optional[str] = None,
    single_monthly: Optional[str] = None,
    selective_features: Optional[List[str]] = None,
    retrain_core: bool = True,
) -> PipelineState:
    """
    Factory function to create initial pipeline state.

    Args:
        run_id: Unique identifier for this run (auto-generated if None)
        workflow_type: "training" (train models), "inference" (predict regimes), or "full" (both)
        skip_*: Flags to skip specific pipeline stages
        forecast_mode: "all" or "single"
        single_*: Specific features to forecast (if mode="single")

    Returns:
        PipelineState with initial values
    """
    if run_id is None:
        run_id = f"rfp-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    return PipelineState(
        # Metadata
        run_id=run_id,
        timestamp=datetime.now().isoformat(),
        config_dir="configs",
        output_dir="outputs",
        workflow_type=workflow_type,

        # Training execution flags
        skip_fetch=skip_fetch,
        skip_engineer=skip_engineer,
        skip_select=skip_select,
        skip_cluster=skip_cluster,
        skip_classify=skip_classify,
        skip_forecast=skip_forecast,
        skip_cleanup=skip_cleanup,

        # Inference/monitoring execution flags
        skip_inference=skip_inference,
        skip_alerts=skip_alerts,
        skip_validation=skip_validation,
        skip_monitoring=skip_monitoring,

        # Forecasting config
        forecast_mode=forecast_mode,
        single_daily=single_daily,
        single_weekly=single_weekly,
        single_monthly=single_monthly,

        # Intelligent auto-mode flags
        selective_features=selective_features,
        retrain_core=retrain_core,

        # Initialize training status dicts
        fetch_status={},
        engineer_status={},
        select_status={},
        cluster_status={},
        classify_status={},
        forecast_status={},

        # Initialize inference/monitoring status dicts
        inference_status={},
        alerts_status={},
        validation_status={},
        monitoring_status={},

        # Human decisions (default to auto-approve)
        fetch_approved=False,
        engineer_approved=False,
        select_approved=False,
        cluster_approved=False,
        classify_approved=False,
        forecast_approved=False,

        # Artifacts
        raw_data_path=None,
        cleaned_data_path=None,
        engineered_data_path=None,
        selected_features_path=None,
        cluster_assignments_path=None,
        classifier_model_path=None,
        forecast_output_path=None,

        # Diagnostics
        diagnostics={},
        performance_metrics={},

        # Error tracking
        errors=[],
        warnings=[],

        # Control flags
        needs_human_review=False,
        retry_stage=None,
        abort_pipeline=False,
        needs_retraining=False,

        # Results
        regime_forecast_id=None,
        alert_result=None,
        validation_result=None,
        monitoring_result=None,

        # Overrides (None by default)
        missingness_override=None,
        feature_exclusions=None,
        manual_feature_additions=None,
        manual_feature_removals=None,
        regime_override=None,
        retrain_classifier=False,
        ensemble_weight_override=None,
    )
