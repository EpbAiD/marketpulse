#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inference_nodes.py
Additional LangGraph Nodes for Inference & Monitoring
=============================================================
Extends the base pipeline with production inference nodes:
- Inference (regime prediction from forecasts)
- Alert detection (regime shift alerts)
- Validation (SMAPE-based feature validation)
- Monitoring (performance tracking & retraining decisions)
=============================================================
"""

import time
from datetime import datetime
from orchestrator.state import PipelineState


# ============================================================
# NODE: Inference (Generate New Regime Predictions)
# ============================================================
def inference_node(state: PipelineState) -> PipelineState:
    """
    Run full inference pipeline: forecast raw features → engineer → predict regimes
    Wraps orchestrator.inference module
    """
    if state.get("skip_inference", False):
        print("⏭️  Skipping inference (--skip-inference flag set)\n")
        state["inference_status"] = {"skipped": True}
        return state

    print("\n" + "=" * 70)
    print("🚀 INFERENCE: Regime Prediction")
    print("=" * 70 + "\n")

    start_time = time.time()

    try:
        from orchestrator.inference import run_inference_pipeline

        # Run inference pipeline
        # Generate 16 calendar days to ensure 10 trading days (accounts for weekends + holidays)
        result = run_inference_pipeline(horizon_days=16)

        # Update state
        elapsed = time.time() - start_time
        state["inference_status"] = {
            "success": True,
            "forecast_id": result.get("forecast_id"),
            "predictions": result.get("predictions_count", 0),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["regime_forecast_id"] = result.get("forecast_id")

        print(f"✅ Inference completed successfully in {elapsed:.2f}s\n")

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "inference",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["inference_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Inference failed: {e}\n")

    return state


# ============================================================
# NODE: Alert Detection (Regime Shift Alerts)
# ============================================================
def alerts_node(state: PipelineState) -> PipelineState:
    """
    Check for regime shift alerts between consecutive forecasts
    Wraps orchestrator.alerts module
    """
    if state.get("skip_alerts", False):
        print("⏭️  Skipping alert detection (--skip-alerts flag set)\n")
        state["alerts_status"] = {"skipped": True}
        return state

    print("\n" + "=" * 70)
    print("🚀 ALERTS: Regime Shift Detection")
    print("=" * 70 + "\n")

    start_time = time.time()

    try:
        from orchestrator.alerts import run_alert_check

        # Run alert check
        result = run_alert_check(period='weekly', quiet=False)

        # Update state
        elapsed = time.time() - start_time
        state["alerts_status"] = {
            "success": True,
            "alert_triggered": result.get("alert", False),
            "shifts_detected": len(result.get("shifts", [])),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["alert_result"] = result

        if result.get("alert"):
            print(f"⚠️  {len(result['shifts'])} regime shift(s) detected!\n")
        else:
            print(f"✅ No regime shifts detected\n")

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "alerts",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["alerts_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Alert detection failed: {e}\n")

    return state


# ============================================================
# NODE: Validation (SMAPE Feature Validation)
# ============================================================
def validation_node(state: PipelineState) -> PipelineState:
    """
    Validate forecasts using SMAPE-based feature validation
    Wraps data_agent.validator module
    """
    if state.get("skip_validation", False):
        print("⏭️  Skipping validation (--skip-validation flag set)\n")
        state["validation_status"] = {"skipped": True}
        return state

    print("\n" + "=" * 70)
    print("🚀 VALIDATION: Forecast Quality (SMAPE)")
    print("=" * 70 + "\n")

    start_time = time.time()

    try:
        from data_agent.validator import run_validation_analysis

        # Run validation
        result = run_validation_analysis()

        # Update state
        elapsed = time.time() - start_time
        state["validation_status"] = {
            "success": True,
            "avg_smape": float(result["metrics"].get("avg_smape", 0)),
            "forecasts_validated": int(result["metrics"].get("total_forecasts", 0)),
            "needs_retraining": bool(result["metrics"].get("needs_retraining", False)),
            "elapsed_seconds": float(elapsed),
            "timestamp": str(datetime.now().isoformat()),
        }

        print(f"✅ Validation complete: avg SMAPE {result['metrics'].get('avg_smape', 0):.2f}%\n")

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "validation",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["validation_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Validation failed: {e}\n")

    return state


# ============================================================
# NODE: Monitoring (Performance & Retraining Decision)
# ============================================================
def monitoring_node(state: PipelineState) -> PipelineState:
    """
    Monitor performance and decide if retraining is needed
    Wraps orchestrator.monitoring module
    """
    if state.get("skip_monitoring", False):
        print("⏭️  Skipping monitoring (--skip-monitoring flag set)\n")
        state["monitoring_status"] = {"skipped": True}
        return state

    print("\n" + "=" * 70)
    print("🚀 MONITORING: Performance Analysis")
    print("=" * 70 + "\n")

    start_time = time.time()

    try:
        from orchestrator.monitoring import RetrainingAgent

        # Run monitoring check
        agent = RetrainingAgent()
        result = agent.run_check()

        # Update state
        elapsed = time.time() - start_time
        state["monitoring_status"] = {
            "success": True,
            "should_retrain": result.get("should_retrain", False),
            "retrain_reason": result.get("reason", ""),
            "elapsed_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
        }
        state["monitoring_result"] = result

        if result.get("should_retrain"):
            print(f"⚠️  Retraining recommended: {result.get('reason')}\n")
            # Set flag for conditional routing
            state["needs_retraining"] = True
        else:
            print(f"✅ No retraining needed: {result.get('reason')}\n")
            state["needs_retraining"] = False

    except Exception as e:
        elapsed = time.time() - start_time
        error_info = {
            "stage": "monitoring",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
        state.setdefault("errors", []).append(error_info)
        state["monitoring_status"] = {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }
        print(f"❌ Monitoring failed: {e}\n")

    return state
