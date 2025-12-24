#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RFP DataAgent Pipeline Runner
=============================================================
Executes the complete data preparation flow:

    1️⃣ Data Fetching      → outputs/fetched/raw & cleaned
    2️⃣ Feature Engineering → outputs/engineered
    3️⃣ Feature Selection   → outputs/selected

Each step logs diagnostics and summary stats in real time
(using utilities). Steps can be toggled independently via CLI.

🧹 Now automatically cleans old logs, diagnostics, and outputs
before every fresh run, preserving code and configs.
=============================================================
"""

import argparse
import time
import sys
import os
import shutil

from data_agent.fetcher import run_fetcher
from data_agent.engineer import engineer_features
from data_agent.selector import run_selector


# ============================================================
# 🧹 CLEANUP LOGIC
# ============================================================
def clean_workspace():
    """
    Deletes all generated outputs, logs, and diagnostics before a new run.
    Keeps code files (.py, .yaml, .yml) and project structure intact.
    """
    print("\n🧹 Cleaning workspace before fresh run...")

    base_dirs = ["outputs", "logs"]
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

            # Remove empty directories after cleaning
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

    print("✅ Workspace cleaned successfully.\n")


# ============================================================
# ⚙️ Utility helpers
# ============================================================
def divider(title: str):
    print("\n" + "=" * 70)
    print(f"🚀 {title}")
    print("=" * 70)


# ============================================================
# 🚀 Pipeline Runner
# ============================================================
def run_pipeline(run_fetch=True, run_engineer=True, run_selector_step=True):
    start = time.time()
    divider("RFP DataAgent – Full Pipeline Start")

    try:
        # 🔹 Clean workspace first
        clean_workspace()

        # -----------------------------------------------------
        if run_fetch:
            divider("STEP 1: Fetching Raw Data")
            run_fetcher()
            print("✅ Data fetching completed successfully.\n")

        # -----------------------------------------------------
        if run_engineer:
            divider("STEP 2: Feature Engineering")
            engineer_features()
            print("✅ Feature engineering completed successfully.\n")

        # -----------------------------------------------------
        if run_selector_step:
            divider("STEP 3: Feature Alignment & Selection")
            run_selector()
            print("✅ Feature selection completed successfully.\n")

        divider("✅ PIPELINE COMPLETED")
        elapsed = (time.time() - start) / 60
        print(f"⏱️ Total runtime: {elapsed:.2f} min")

    except KeyboardInterrupt:
        print("\n⚠️ Pipeline interrupted by user.")
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ Pipeline error: {type(e).__name__}: {e}")
        sys.exit(1)


# ============================================================
# 🧭 CLI Entry
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run RFP DataAgent pipeline.")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip data fetching step.")
    parser.add_argument("--skip-engineer", action="store_true", help="Skip feature engineering step.")
    parser.add_argument("--skip-selector", action="store_true", help="Skip feature selection step.")
    parser.add_argument("--no-clean", action="store_true", help="Skip workspace cleanup.")
    args = parser.parse_args()

    # Allow manual override to skip cleaning
    if not args.no_clean:
        clean_workspace()

    run_pipeline(
        run_fetch=not args.skip_fetch,
        run_engineer=not args.skip_engineer,
        run_selector_step=not args.skip_selector
    )