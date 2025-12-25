#!/usr/bin/env python3
"""
Daily Workflow Diagnostic Test
Tests all components of the daily automation to prevent future issues
"""

import os
import sys
from pathlib import Path

def test_file_existence():
    """Test that all required files exist"""
    print("=" * 70)
    print("TEST 1: File Existence")
    print("=" * 70)

    required_files = [
        "daily_update.sh",
        "run_daily_update.py",
        "log_daily_predictions.py",
        "capture_dashboard_screenshot.py",
        "run_pipeline.py",
        "orchestrator/inference.py",
        "orchestrator/inference_nodes.py",
        "classification_agent/classifier.py",
        "forecasting_agent/forecaster.py",
        "data_agent/storage.py",
    ]

    all_exist = True
    for file in required_files:
        if Path(file).exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} MISSING")
            all_exist = False

    return all_exist


def test_directories():
    """Test that all required directories exist and are writable"""
    print("\n" + "=" * 70)
    print("TEST 2: Directory Permissions")
    print("=" * 70)

    required_dirs = [
        "outputs",
        "outputs/inference",
        "outputs/forecasting",
        "outputs/forecasting/inference",
        "dashboard_screenshots",
    ]

    all_good = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            if os.access(path, os.W_OK):
                print(f"  ✅ {dir_path} (writable)")
            else:
                print(f"  ⚠️  {dir_path} (not writable)")
                all_good = False
        else:
            print(f"  ℹ️  {dir_path} (will be created)")

    return all_good


def test_bigquery_connection():
    """Test BigQuery connection and operations"""
    print("\n" + "=" * 70)
    print("TEST 3: BigQuery Connection")
    print("=" * 70)

    try:
        from data_agent.storage import get_storage
        print("  ✅ storage module imported")

        storage = get_storage()
        print("  ✅ storage instance created")

        if hasattr(storage, 'get_latest_forecasts'):
            print("  ✅ get_latest_forecasts() method exists")

            latest = storage.get_latest_forecasts(limit=1)
            print(f"  ✅ Retrieved {len(latest)} forecast(s)")

            if len(latest) > 0:
                forecast_id = latest.iloc[0]['forecast_id']
                predictions = storage.get_forecast_by_id(forecast_id)
                print(f"  ✅ Retrieved {len(predictions)} predictions for {forecast_id}")
                return True
            else:
                print("  ⚠️  No forecasts in database (might be expected)")
                return True
        else:
            print("  ❌ get_latest_forecasts() method missing")
            return False

    except Exception as e:
        print(f"  ❌ BigQuery test failed: {e}")
        return False


def test_local_files():
    """Test that local forecast files exist and are accessible"""
    print("\n" + "=" * 70)
    print("TEST 4: Local Forecast Files")
    print("=" * 70)

    import glob

    # Check forecasting/inference directory (primary)
    forecasting_files = sorted(glob.glob('outputs/forecasting/inference/regime_predictions_*.parquet'))
    print(f"  outputs/forecasting/inference/: {len(forecasting_files)} files")
    if forecasting_files:
        print(f"    Latest: {Path(forecasting_files[-1]).name}")

    # Check inference directory (legacy)
    inference_files = sorted(glob.glob('outputs/inference/regime_forecast_*.parquet'))
    print(f"  outputs/inference/: {len(inference_files)} files")
    if inference_files:
        print(f"    Latest: {Path(inference_files[-1]).name}")

    # At least one location should have files
    if forecasting_files or inference_files:
        print("  ✅ Local forecast files exist")
        return True
    else:
        print("  ⚠️  No local forecast files (might be BigQuery-only)")
        return True


def test_python_dependencies():
    """Test that all required Python modules can be imported"""
    print("\n" + "=" * 70)
    print("TEST 5: Python Dependencies")
    print("=" * 70)

    required_modules = [
        ("pandas", "pandas"),
        ("google.cloud.bigquery", "BigQuery"),
        ("playwright.sync_api", "Playwright"),
        ("streamlit", "Streamlit"),
        ("langgraph", "LangGraph"),
        ("sklearn", "scikit-learn"),
    ]

    all_imported = True
    for module_name, display_name in required_modules:
        try:
            __import__(module_name)
            print(f"  ✅ {display_name}")
        except ImportError:
            print(f"  ❌ {display_name} not installed")
            all_imported = False

    return all_imported


def test_daily_update_script():
    """Test that daily_update.sh has correct content"""
    print("\n" + "=" * 70)
    print("TEST 6: daily_update.sh Configuration")
    print("=" * 70)

    try:
        with open('daily_update.sh', 'r') as f:
            content = f.read()

        checks = [
            ("BigQuery data source", "from data_agent.storage import get_storage"),
            ("Git author verification", "git config user.name"),
            ("Forecast date extraction", "get_latest_forecasts"),
            ("Validation metrics", "get_forecast_by_id"),
        ]

        all_good = True
        for check_name, check_string in checks:
            if check_string in content:
                print(f"  ✅ {check_name}")
            else:
                print(f"  ❌ {check_name} missing")
                all_good = False

        return all_good

    except Exception as e:
        print(f"  ❌ Error reading daily_update.sh: {e}")
        return False


def test_dashboard_app():
    """Test that dashboard app exists and is valid"""
    print("\n" + "=" * 70)
    print("TEST 7: Dashboard Application")
    print("=" * 70)

    dashboard_path = Path("dashboard/app.py")
    if dashboard_path.exists():
        print(f"  ✅ dashboard/app.py exists")

        # Check if it imports streamlit
        try:
            with open(dashboard_path, 'r') as f:
                content = f.read()
            if "import streamlit" in content:
                print("  ✅ Streamlit imported")
                return True
            else:
                print("  ⚠️  Streamlit not imported (unexpected)")
                return False
        except Exception as e:
            print(f"  ⚠️  Could not read dashboard file: {e}")
            return False
    else:
        print("  ❌ dashboard/app.py missing")
        return False


def run_all_tests():
    """Run all diagnostic tests"""
    print("\n" + "🔍 " * 20)
    print("DAILY WORKFLOW DIAGNOSTIC TESTS")
    print("🔍 " * 20 + "\n")

    tests = [
        ("File Existence", test_file_existence),
        ("Directory Permissions", test_directories),
        ("BigQuery Connection", test_bigquery_connection),
        ("Local Forecast Files", test_local_files),
        ("Python Dependencies", test_python_dependencies),
        ("daily_update.sh Config", test_daily_update_script),
        ("Dashboard App", test_dashboard_app),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n  ❌ {test_name} crashed: {e}")
            results[test_name] = False

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 70 + "\n")

    if passed == total:
        print("🎉 All tests passed! Daily workflow should run smoothly.")
        return 0
    else:
        print("⚠️  Some tests failed. Review issues above before running daily updates.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
