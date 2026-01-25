#!/usr/bin/env python3
"""
Unified LangGraph Pipeline Entry Point
=============================================================
Single command to run the entire Market Regime Forecasting System:
- Training workflow: Fetch data → Engineer → Select → Cluster → Classify → Train forecasters
- Inference workflow: Generate forecasts → Engineer → Predict regimes
- Monitoring workflow: Validate → Alert → Performance check

LangGraph orchestrates all agents with proper state management.
=============================================================
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from orchestrator.state import create_initial_state
from orchestrator.graph import build_complete_graph


def run_training_workflow(args):
    """Run training workflow: data → models"""
    print("\n" + "=" * 80)
    print("🚀 TRAINING WORKFLOW")
    print("=" * 80 + "\n")

    # Create initial state
    state = create_initial_state(
        workflow_type="training",
        skip_cleanup=args.no_clean,
        skip_fetch=args.skip_fetch,
        skip_engineer=args.skip_engineer,
        skip_select=args.skip_select,
        skip_cluster=args.skip_cluster,
        skip_classify=args.skip_classify,
        skip_forecast=args.skip_forecast,
        forecast_mode=args.mode,
        single_daily=args.single_daily,
        single_weekly=args.single_weekly,
        single_monthly=args.single_monthly,
    )

    # Build and run graph
    graph = build_complete_graph(enable_human_review=False)
    config = {"configurable": {"thread_id": state["run_id"]}}

    print(f"Run ID: {state['run_id']}\n")

    # Execute workflow
    result = graph.invoke(state, config)

    print("\n" + "=" * 80)
    print("✅ TRAINING WORKFLOW COMPLETE")
    print("=" * 80 + "\n")

    return result


def run_inference_workflow(args):
    """Run inference workflow: forecasts → regimes → monitoring"""
    print("\n" + "=" * 80)
    print("🔮 INFERENCE WORKFLOW")
    print("=" * 80 + "\n")

    # Create initial state
    state = create_initial_state(
        workflow_type="inference",
        skip_cleanup=args.no_clean,
        skip_inference=args.skip_inference,
        skip_alerts=args.skip_alerts,
        skip_validation=args.skip_validation,
        skip_monitoring=args.skip_monitoring,
    )

    # Build and run graph
    graph = build_complete_graph(enable_human_review=False)
    config = {"configurable": {"thread_id": state["run_id"]}}

    print(f"Run ID: {state['run_id']}\n")

    # Execute workflow
    result = graph.invoke(state, config)

    print("\n" + "=" * 80)
    print("✅ INFERENCE WORKFLOW COMPLETE")
    print("=" * 80 + "\n")

    # Print summary
    if result.get("regime_forecast_id"):
        print(f"📊 Forecast ID: {result['regime_forecast_id']}")

    if result.get("alerts_status", {}).get("alert_triggered"):
        print(f"⚠️  {result['alerts_status']['shifts_detected']} regime shift(s) detected")

    if result.get("validation_status", {}).get("avg_smape"):
        print(f"📈 Avg SMAPE: {result['validation_status']['avg_smape']:.2f}%")

    if result.get("needs_retraining"):
        print(f"🔄 Retraining recommended: {result['monitoring_status'].get('retrain_reason')}")

    print()

    return result


def run_full_workflow(args):
    """Run complete workflow: training + inference + monitoring"""
    print("\n" + "=" * 80)
    print("🌐 FULL WORKFLOW (Training + Inference + Monitoring)")
    print("=" * 80 + "\n")

    # Create initial state
    state = create_initial_state(
        workflow_type="full",
        skip_cleanup=args.no_clean,
        # Training flags
        skip_fetch=args.skip_fetch,
        skip_engineer=args.skip_engineer,
        skip_select=args.skip_select,
        skip_cluster=args.skip_cluster,
        skip_classify=args.skip_classify,
        skip_forecast=args.skip_forecast,
        # Inference flags
        skip_inference=args.skip_inference,
        skip_alerts=args.skip_alerts,
        skip_validation=args.skip_validation,
        skip_monitoring=args.skip_monitoring,
        # Forecasting config
        forecast_mode=args.mode,
        single_daily=args.single_daily,
        single_weekly=args.single_weekly,
        single_monthly=args.single_monthly,
        # Intelligent auto-mode flags (from auto mode detection)
        selective_features=getattr(args, 'selective_features', None),
        retrain_core=getattr(args, 'retrain_core', True),
    )

    # Build and run graph
    graph = build_complete_graph(enable_human_review=False)
    config = {"configurable": {"thread_id": state["run_id"]}}

    print(f"Run ID: {state['run_id']}\n")

    # Execute workflow
    result = graph.invoke(state, config)

    print("\n" + "=" * 80)
    print("✅ FULL WORKFLOW COMPLETE")
    print("=" * 80 + "\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Market Regime Forecasting System - LangGraph Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Workflow Types:
  auto        - ⭐ Smart mode: Detects if models exist/outdated and runs appropriate workflow
  training    - Train all models (fetch → engineer → select → cluster → classify → forecast)
  inference   - Generate regime predictions (forecast features → engineer → predict → monitor)
  full        - Complete workflow (training + inference + monitoring)

Examples:
  # ⭐ RECOMMENDED: Auto-detect workflow (smart mode)
  python run_pipeline.py --workflow auto

  # First time setup (train + infer)
  python run_pipeline.py --workflow full

  # Daily operations (inference only)
  python run_pipeline.py --workflow inference

  # Train models only
  python run_pipeline.py --workflow training

  # Skip specific stages
  python run_pipeline.py --skip-fetch --skip-engineer

  # Custom model age threshold for auto mode
  python run_pipeline.py --workflow auto --max-model-age 7
        """
    )

    # Workflow selection
    parser.add_argument(
        "--workflow",
        choices=["training", "inference", "full", "auto"],
        default="full",
        help="Workflow to run (default: full, auto=detect based on model availability)"
    )

    parser.add_argument(
        "--max-model-age",
        type=int,
        default=30,
        help="Maximum model age in days for auto mode (default: 30)"
    )

    # Training stage skip flags
    parser.add_argument("--skip-fetch", action="store_true", help="Skip data fetching")
    parser.add_argument("--skip-engineer", action="store_true", help="Skip feature engineering")
    parser.add_argument("--skip-select", action="store_true", help="Skip feature selection")
    parser.add_argument("--skip-cluster", action="store_true", help="Skip clustering")
    parser.add_argument("--skip-classify", action="store_true", help="Skip classification")
    parser.add_argument("--skip-forecast", action="store_true", help="Skip forecasting")

    # Inference stage skip flags
    parser.add_argument("--skip-inference", action="store_true", help="Skip inference")
    parser.add_argument("--skip-alerts", action="store_true", help="Skip alert detection")
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation")
    parser.add_argument("--skip-monitoring", action="store_true", help="Skip monitoring")

    # Other flags
    parser.add_argument("--no-clean", action="store_true", help="Skip cleanup before run")

    # Forecasting mode
    parser.add_argument(
        "--mode",
        choices=["all", "single"],
        default="all",
        help="Forecast all features or single feature (default: all)"
    )
    parser.add_argument("--single-daily", type=str, help="Single daily feature to forecast")
    parser.add_argument("--single-weekly", type=str, help="Single weekly feature to forecast")
    parser.add_argument("--single-monthly", type=str, help="Single monthly feature to forecast")

    args = parser.parse_args()

    # Auto-detect workflow if requested
    if args.workflow == "auto":
        from orchestrator.intelligent_model_checker import get_intelligent_recommendation, print_intelligent_status

        print("\n" + "=" * 80)
        print("🔍 AUTO MODE: Detecting required workflow...")
        print("=" * 80)

        recommendation = print_intelligent_status()

        # Store recommendation for use by state/nodes
        args.selective_features = recommendation.get('features_to_train') or None
        args.retrain_core = recommendation.get('retrain_core', True)

        if recommendation['workflow'] == 'inference':
            # All models fresh - just run inference
            print(f"✅ All models ready! Running inference workflow...\n")
            args.workflow = "inference"
            args.selective_features = None
            args.retrain_core = False

        elif recommendation['workflow'] == 'partial_train':
            # Partial train: Core models (HMM/RF) are fresh, only some feature models need training
            print(f"🎯 Partial training: {len(recommendation['features_to_train'])} features need training")
            print(f"   Core models (HMM/RF) are fresh - skipping core retraining")
            print(f"   Features to train: {', '.join(sorted(recommendation['features_to_train']))}\n")
            args.workflow = "full"
            args.retrain_core = False
            # Skip select/cluster/classify since core models are fresh
            args.skip_select = True
            args.skip_cluster = True
            args.skip_classify = True

        else:  # 'train' - core models need retraining
            # Core models (HMM/RF) are missing or stale (> 30 days old)
            print(f"🔄 Core models need retraining (HMM/RF > 30 days old or missing)")
            if recommendation['features_to_train']:
                print(f"   Also training {len(recommendation['features_to_train'])} feature models")
                print(f"   Features: {', '.join(sorted(recommendation['features_to_train']))}\n")
            else:
                print(f"   All feature models are fresh - only retraining core\n")
            args.workflow = "full"
            args.retrain_core = True
            # Don't skip any core stages - need full pipeline for HMM/RF

    # Route to appropriate workflow
    try:
        if args.workflow == "training":
            result = run_training_workflow(args)
        elif args.workflow == "inference":
            result = run_inference_workflow(args)
        else:  # full
            result = run_full_workflow(args)

        # Show errors if any
        if result.get("errors"):
            print("\n⚠️  Errors encountered:")
            for error in result["errors"]:
                print(f"   [{error['stage']}] {error['error']}")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Pipeline interrupted by user\n")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
