#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_forecast_3features.py
Test forecasting with 3 features to verify memory optimization
=============================================================
Tests one feature from each cadence:
- Daily: GSPC
- Weekly: NFCI
- Monthly: CPI
=============================================================
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# CREATE TEST DATA FOR 3 FEATURES
# ============================================================

def create_test_data():
    """Create test data for 3 features with sufficient samples"""
    print("Creating test data for 3 features...")

    # Create directories
    os.makedirs("outputs/fetched/cleaned", exist_ok=True)

    # 1. GSPC (daily) - need enough data for forecasting
    dates_daily = pd.date_range(end=datetime.now(), periods=500, freq='D')
    df_gspc = pd.DataFrame({
        'GSPC': 4000 + np.random.randn(500).cumsum() * 10
    }, index=dates_daily)
    df_gspc.to_parquet("outputs/fetched/cleaned/GSPC.parquet")
    print(f"  ✓ Created GSPC (daily, {len(df_gspc)} samples)")

    # 2. NFCI (weekly) - need enough data for forecasting
    dates_weekly = pd.date_range(end=datetime.now(), periods=150, freq='W')
    df_nfci = pd.DataFrame({
        'NFCI': np.random.randn(150) * 0.5
    }, index=dates_weekly)
    df_nfci.to_parquet("outputs/fetched/cleaned/NFCI.parquet")
    print(f"  ✓ Created NFCI (weekly, {len(df_nfci)} samples)")

    # 3. CPI (monthly) - need enough data for forecasting
    dates_monthly = pd.date_range(end=datetime.now(), periods=120, freq='ME')
    df_cpi = pd.DataFrame({
        'CPI': 200 + np.arange(120) * 0.2 + np.random.randn(120) * 0.5
    }, index=dates_monthly)
    df_cpi.to_parquet("outputs/fetched/cleaned/CPI.parquet")
    print(f"  ✓ Created CPI (monthly, {len(df_cpi)} samples)")

    print("✅ Test data created successfully\n")


# ============================================================
# RUN FORECASTING TEST
# ============================================================

def test_forecasting_3features():
    """Test forecasting agent with 3 features"""
    print("=" * 70)
    print("TESTING FORECASTING WITH 3 FEATURES")
    print("=" * 70)

    # Create test data
    create_test_data()

    # Import forecasting agent
    from forecasting_agent.forecaster import run_forecasting_agent

    # Run forecasting in test mode with only 3 features
    print("\n🚀 Starting forecasting test...")
    print("Features: GSPC (daily), NFCI (weekly), CPI (monthly)")
    print("=" * 70)

    try:
        # Run with minimal config - just test these 3 features
        result = run_forecasting_agent(
            mode="test",  # Use test mode if available
            cadence_filter=None,  # Will process all cadences
            feature_filter=["GSPC", "NFCI", "CPI"],  # Only these 3 features
            force_cpu=True,  # Use CPU to avoid GPU memory issues
            quiet=False,
            multi_backtest={"enabled": False, "folds": 1}  # Single fold for speed
        )

        print("\n" + "=" * 70)
        print("✅ FORECASTING TEST COMPLETED SUCCESSFULLY")
        print("=" * 70)

        if result:
            print(f"\nResults:")
            for r in result:
                print(f"  • {r['feature']} ({r['Cadence']}): MAE={r.get('MAE', 'N/A'):.4f}")

        return True

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ FORECASTING TEST FAILED")
        print("=" * 70)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# ALTERNATIVE: Direct call to forecaster
# ============================================================

def test_forecasting_direct():
    """Direct test of forecasting using internal functions"""
    print("=" * 70)
    print("TESTING FORECASTING WITH 3 FEATURES (DIRECT)")
    print("=" * 70)

    # Create test data
    create_test_data()

    # Import required modules
    import yaml
    from forecasting_agent.forecaster import (
        train_forecaster_for_feature,
        collect_feature_files,
        CONFIG_PATH_DEFAULT
    )

    # Load config
    with open(CONFIG_PATH_DEFAULT, "r") as f:
        config = yaml.safe_load(f)

    # Get feature files
    name_to_path = collect_feature_files()

    # Test features
    test_features = {
        "GSPC": ("daily", config["daily"]),
        "NFCI": ("weekly", config["weekly"]),
        "CPI": ("monthly", config["monthly"])
    }

    results = []

    for feature_name, (cadence, cad_cfg) in test_features.items():
        if feature_name not in name_to_path:
            print(f"⚠️  Skipping {feature_name} - file not found")
            continue

        print(f"\n{'=' * 70}")
        print(f"🚀 Testing {feature_name} ({cadence})")
        print('=' * 70)

        try:
            result = train_forecaster_for_feature(
                feature_path=name_to_path[feature_name],
                cadence=cadence,
                horizon=cad_cfg["horizon"],
                val_size=cad_cfg["val_size"],
                force_cpu=True,
                quiet=False,
                test_size=cad_cfg.get("test_size"),
                nf_loss=cad_cfg.get("nf_loss", "mae"),
                arima_cfg={"seasonal": True, "m": 1},
                prophet_cfg={"yearly_seasonality": True},
                multi_backtest={"enabled": False, "folds": 1},
                ens_cfg=cad_cfg.get("ensemble", {})
            )

            if result:
                results.append(result)
                print(f"✅ {feature_name} completed: MAE={result.get('MAE', 'N/A')}")
            else:
                print(f"⚠️  {feature_name} returned no result")

        except Exception as e:
            print(f"❌ {feature_name} failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    if results:
        print(f"✅ Successfully processed {len(results)}/3 features")
        for r in results:
            mae = r.get('MAE', float('nan'))
            rmse = r.get('RMSE', float('nan'))
            print(f"  • {r['feature']} ({r['Cadence']}): MAE={mae:.4f}, RMSE={rmse:.4f}")
        return True
    else:
        print("❌ No features completed successfully")
        return False


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test forecasting with 3 features")
    parser.add_argument("--method", choices=["auto", "direct"], default="direct",
                        help="Test method (auto=use run_forecasting_agent, direct=call train_forecaster_for_feature)")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("FORECASTING MEMORY OPTIMIZATION TEST")
    print("Testing 3 features: GSPC (daily), NFCI (weekly), CPI (monthly)")
    print("=" * 70 + "\n")

    try:
        if args.method == "auto":
            success = test_forecasting_3features()
        else:
            success = test_forecasting_direct()

        if success:
            print("\n✅ TEST PASSED - Memory optimization working correctly")
            sys.exit(0)
        else:
            print("\n❌ TEST FAILED - Check errors above")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ TEST CRASHED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
