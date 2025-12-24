#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
📈 ForecastingAgent Main Entrypoint (YAML-Driven, Diagnostics-Ready)
===========================================================
Runs per-feature ensemble forecasting pipeline automatically
based on cadence definitions in configs/features_config.yml or .yaml.

Enhancements:
- Reads ensemble weighting configuration (mae|rmse|smape) from YAML.
- Supports mode handling: "all" or "single" (auto one per cadence or custom)
- Optional cleanup flag to keep past runs or perform partial cleanup.
- Prints post-run summary with metrics and diagnostic plot directories.
===========================================================
"""

import sys
import os
import shutil
import yaml
import argparse
from datetime import datetime

# Ensure relative imports work
sys.path.append(os.path.dirname(__file__))
from forecasting_agent import forecaster


# ===========================================================
# 🧹 CLEANUP
# ===========================================================
def clean_old_outputs(skip_large=False):
    """
    Remove old forecasting outputs before running new jobs.
    If skip_large=True, keep plots/metrics but clear temp logs and models.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_base = os.path.join(base_dir, "outputs", "forecasting")

    print("🧹 Cleaning old forecasting outputs...")
    if not os.path.exists(out_base):
        print(f"⚠️ Directory not found: {out_base}")
        return

    for item in os.listdir(out_base):
        path = os.path.join(out_base, item)
        try:
            if skip_large and item in {"plots", "metrics"}:
                continue
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except Exception as e:
            print(f"⚠️ Could not remove {path}: {e}")

    print("✅ Forecasting output directories cleaned.\n")


# ===========================================================
# ⚙️ CONFIG LOADER (lightweight pre-check)
# ===========================================================
def preview_yaml_settings(config_path):
    """Quickly display ensemble weighting configuration for sanity check."""
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f) or {}
        print("📘 YAML Config Summary:")
        for cadence, data in cfg.items():
            if not isinstance(data, dict):
                continue
            ens = data.get("ensemble", {})
            metric = ens.get("weight_metric", "mae")
            print(f"   • {cadence:<8} → ensemble weight_metric: {metric}")
        print()
    except Exception as e:
        print(f"⚠️ Could not preview YAML: {e}\n")


# ===========================================================
# 🚀 MAIN LOGIC
# ===========================================================
def main(clean=True, skip_large=False):
    """Main entrypoint for the forecasting agent."""
    parser = argparse.ArgumentParser(description="Forecasting Agent Runner")
    parser.add_argument("--mode", type=str, default="all", choices=["all", "single"],
                        help="Run mode: 'all' (all features) or 'single' (one per cadence)")
    parser.add_argument("--single-daily", type=str, default=None, help="Run only this daily feature")
    parser.add_argument("--single-weekly", type=str, default=None, help="Run only this weekly feature")
    parser.add_argument("--single-monthly", type=str, default=None, help="Run only this monthly feature")
    parser.add_argument("--skip-large", action="store_true", help="Skip cleaning large directories")
    parser.add_argument("--no-clean", action="store_true", help="Skip full cleanup")
    args = parser.parse_args()

    ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("===========================================================")
    print("🧠  Columbia Market Intelligence — Forecasting Agent")
    print(f"⏱  Launch Time: {ts_now}")
    print("===========================================================\n")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    config_dir = os.path.join(base_dir, "configs")

    # Step 1: Cleanup
    if not args.no_clean:
        clean_old_outputs(skip_large=args.skip_large)
    else:
        print("⚙️  Skipping cleanup (using existing outputs).\n")

    # Step 2: Locate YAML config
    yml_path = os.path.join(config_dir, "features_config.yml")
    yaml_path = os.path.join(config_dir, "features_config.yaml")
    if os.path.exists(yml_path):
        config_path = yml_path
    elif os.path.exists(yaml_path):
        config_path = yaml_path
    else:
        raise FileNotFoundError(
            f"❌ Config file not found in {config_dir}. Expected one of:\n"
            f"   - features_config.yml\n"
            f"   - features_config.yaml"
        )

    # Step 3: Preview ensemble config
    preview_yaml_settings(config_path)

    # Step 4: Run forecasting agent
    try:
        print(f"📄 Using config file → {config_path}\n")
        print(f"🎯 Mode Selected → {args.mode}\n")

        forecaster.run_forecasting_agent(
            mode=args.mode,
            config_path=config_path,
            single_daily=args.single_daily,
            single_weekly=args.single_weekly,
            single_monthly=args.single_monthly,
        )
    except Exception as e:
        print(f"\n❌ Forecasting agent failed: {e}")
        raise

    # Step 5: Summary
    out_base = os.path.join(base_dir, "outputs", "forecasting")
    plot_dir = os.path.join(out_base, "plots")
    metric_dir = os.path.join(out_base, "metrics")
    print("\n===========================================================")
    print("✅ All forecasting runs complete.")
    print(f"📊 Metrics directory → {metric_dir}")
    print(f"🖼️ Diagnostic plots → {plot_dir}")
    print("===========================================================")


# ===========================================================
# 🧭 ENTRYPOINT
# ===========================================================
if __name__ == "__main__":
    main()