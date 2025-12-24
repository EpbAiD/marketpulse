#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pipeline_dummy.py
Test LangGraph pipeline with dummy data
=============================================================
Creates minimal dummy data to test pipeline flow without
waiting for full data processing.
=============================================================
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import create_initial_state, build_pipeline_graph


# ============================================================
# CREATE DUMMY DATA
# ============================================================

def create_dummy_data():
    """Create minimal dummy data for testing"""
    print("Creating dummy data...")

    # Create directories
    os.makedirs("outputs/fetched/cleaned", exist_ok=True)
    os.makedirs("outputs/engineered", exist_ok=True)
    os.makedirs("outputs/selected", exist_ok=True)

    # Create date range (100 days only for speed)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='D')

    # Create dummy daily feature (GSPC)
    df_gspc = pd.DataFrame({
        'GSPC': 4000 + np.random.randn(100).cumsum() * 10
    }, index=dates)
    df_gspc.to_parquet("outputs/fetched/cleaned/GSPC.parquet")
    print("  ✓ Created GSPC (daily)")

    # Create dummy weekly feature (NFCI)
    dates_weekly = pd.date_range(end=datetime.now(), periods=50, freq='W')
    df_nfci = pd.DataFrame({
        'NFCI': np.random.randn(50)
    }, index=dates_weekly)
    df_nfci.to_parquet("outputs/fetched/cleaned/NFCI.parquet")
    print("  ✓ Created NFCI (weekly)")

    # Create dummy monthly feature (CPI)
    dates_monthly = pd.date_range(end=datetime.now(), periods=24, freq='ME')
    df_cpi = pd.DataFrame({
        'CPI': 200 + np.arange(24) * 0.5
    }, index=dates_monthly)
    df_cpi.to_parquet("outputs/fetched/cleaned/CPI.parquet")
    print("  ✓ Created CPI (monthly)")

    # Create dummy engineered features (minimal)
    for feature in ['GSPC', 'NFCI', 'CPI']:
        src_path = f"outputs/fetched/cleaned/{feature}.parquet"
        if os.path.exists(src_path):
            df = pd.read_parquet(src_path)
            # Add some dummy engineered columns
            col_name = df.columns[0]
            df[f'ret_{col_name}'] = df[col_name].pct_change()
            df[f'ret_{col_name}_5d'] = df[col_name].pct_change(5)
            df.to_parquet(f"outputs/engineered/{col_name}.parquet")
    print("  ✓ Created engineered features")

    # Create dummy selected features (aligned dataset)
    df_aligned = pd.DataFrame({
        'GSPC': 4000 + np.random.randn(100).cumsum() * 10,
        'ret_GSPC': np.random.randn(100) * 0.01,
        'NFCI': np.random.randn(100),
    }, index=dates)
    df_aligned.to_parquet("outputs/selected/aligned_dataset.parquet")
    print("  ✓ Created aligned dataset")

    # Create dummy feature list (use 'selected_feature' column name expected by clustering agent)
    pd.DataFrame({
        'selected_feature': ['GSPC', 'ret_GSPC', 'NFCI']
    }).to_csv("outputs/selected/features_selected.csv", index=False)
    print("  ✓ Created features_selected.csv")

    print("✅ Dummy data created successfully\n")


# ============================================================
# TEST PIPELINE WITH DUMMY DATA
# ============================================================

def test_pipeline_with_dummy_data():
    """Test full pipeline with dummy data"""
    print("=" * 70)
    print("TESTING PIPELINE WITH DUMMY DATA")
    print("=" * 70)

    # Create dummy data first
    create_dummy_data()

    # Create initial state - skip data prep stages since we have dummy data
    initial_state = create_initial_state(
        run_id="test-dummy-pipeline",
        skip_fetch=True,        # Use existing dummy data
        skip_engineer=True,     # Use existing dummy engineered
        skip_select=True,       # Use existing dummy selected
        skip_cleanup=True,      # Don't delete dummy data
        skip_cluster=False,     # Test clustering
        skip_classify=False,    # Test classification
        skip_forecast=False,    # Test forecasting (THIS IS WHERE MEMORY ISSUES OCCUR)
    )

    # Build graph without human review for automated testing
    graph = build_pipeline_graph(enable_human_review=False)

    # Run pipeline
    config = {"configurable": {"thread_id": "test-dummy"}}

    print("\nExecuting pipeline nodes...\n")

    try:
        final_state = None
        for event in graph.stream(initial_state, config):
            for node_name, state in event.items():
                if node_name not in ["__start__", "__end__"]:
                    status_icon = "🔄"
                    if node_name in state and isinstance(state.get(f"{node_name}_status"), dict):
                        if state[f"{node_name}_status"].get("success"):
                            status_icon = "✅"
                        elif state[f"{node_name}_status"].get("error"):
                            status_icon = "❌"
                    print(f"{status_icon} Executed: {node_name}")
                final_state = state

        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)

        # Check each stage
        stages = ['cluster', 'classify', 'forecast']
        for stage in stages:
            status = final_state.get(f"{stage}_status", {})
            if status.get("success"):
                print(f"✅ {stage.capitalize()}: SUCCESS")
            elif status.get("skipped"):
                print(f"⏭️  {stage.capitalize()}: SKIPPED")
            elif status.get("error"):
                print(f"❌ {stage.capitalize()}: FAILED - {status.get('error')}")
            else:
                print(f"⚪ {stage.capitalize()}: NOT RUN")

        # Check for errors
        if final_state.get("errors"):
            print(f"\n⚠️  Errors encountered: {len(final_state['errors'])}")
            for error in final_state["errors"]:
                print(f"   - [{error['stage']}] {error['error']}")

        print("=" * 70)

        # Return success status
        return not final_state.get("errors")

    except Exception as e:
        print(f"\n❌ Pipeline execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# CLEANUP DUMMY DATA
# ============================================================

def cleanup_dummy_data():
    """Remove dummy data after test"""
    import shutil

    print("\nCleaning up dummy data...")
    dirs_to_clean = [
        "outputs/fetched",
        "outputs/engineered",
        "outputs/selected",
        "outputs/clustering",
        "outputs/models",
        "outputs/forecasting",
    ]

    for dir_path in dirs_to_clean:
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                print(f"  ✓ Removed {dir_path}")
            except Exception as e:
                print(f"  ⚠️  Could not remove {dir_path}: {e}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test pipeline with dummy data")
    parser.add_argument("--keep-data", action="store_true", help="Keep dummy data after test")
    args = parser.parse_args()

    try:
        success = test_pipeline_with_dummy_data()

        if success:
            print("\n✅ Pipeline test PASSED with dummy data")
            exit_code = 0
        else:
            print("\n❌ Pipeline test FAILED with dummy data")
            exit_code = 1

    finally:
        if not args.keep_data:
            cleanup_dummy_data()
        else:
            print("\n📁 Keeping dummy data (--keep-data flag set)")

    sys.exit(exit_code)
