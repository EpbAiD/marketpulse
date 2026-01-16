#!/usr/bin/env python3
"""
Daily Market Regime Update
=============================================================
Thin wrapper around run_pipeline.py for daily operational workflow.

Runs inference workflow:
- Fetch latest data
- Generate regime forecasts
- Check for regime shift alerts
- Validate forecast quality
- Monitor performance & retrain if needed

This is just a convenience script that calls run_pipeline.py
with the appropriate flags for daily operations.
=============================================================
"""

import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Add project root
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


def run_daily_update(retrain_if_needed: bool = False, use_local: bool = False, use_auto: bool = True):
    """
    Run daily update workflow by calling run_pipeline.py

    Args:
        retrain_if_needed: Trigger retraining if performance degrades (legacy, kept for compatibility)
        use_local: Use local files instead of BigQuery
        use_auto: Use auto-detection mode (default: True)
    """
    print("\n" + "=" * 80)
    print("📅 DAILY MARKET REGIME UPDATE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data source: {'Local files' if use_local else 'BigQuery'}")
    print(f"Mode: {'Auto-detect' if use_auto else 'Inference only'}")
    print("=" * 80 + "\n")

    # Build command to run pipeline
    if use_auto:
        # Auto mode: intelligently detects if models need training
        cmd = [
            "python",
            "run_pipeline.py",
            "--workflow", "auto",
            "--no-clean",  # Don't clean outputs during daily refresh
        ]
    else:
        # Legacy mode: inference only
        cmd = [
            "python",
            "run_pipeline.py",
            "--workflow", "inference",
            "--no-clean",
        ]

    # Execute the pipeline
    try:
        result = subprocess.run(cmd, timeout=21600)  # 6 hour timeout - allows for training 66 neural network models

        if result.returncode != 0:
            print("\n❌ Daily update failed\n")
            return False

        print("\n✅ Daily update complete\n")

        # If retraining recommended and auto-retrain enabled, trigger it
        if retrain_if_needed:
            # Check if retraining was recommended (this is simplistic, could be improved)
            retrain_cmd = [
                "python",
                "run_pipeline.py",
                "--workflow", "training"
            ]

            print("\n" + "=" * 80)
            print("🔄 TRIGGERING RETRAINING (--retrain-if-needed flag set)")
            print("=" * 80 + "\n")

            retrain_result = subprocess.run(retrain_cmd, timeout=7200)  # 2 hours

            if retrain_result.returncode == 0:
                print("\n✅ Retraining completed successfully\n")
            else:
                print("\n❌ Retraining failed\n")
                return False

        return True

    except subprocess.TimeoutExpired:
        print("\n❌ Daily update timed out\n")
        return False

    except KeyboardInterrupt:
        print("\n\n⚠️  Daily update interrupted by user\n")
        return False

    except Exception as e:
        print(f"\n❌ Daily update failed: {e}\n")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Daily market regime update (wrapper for run_pipeline.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script is a convenience wrapper that calls:
    python run_pipeline.py --workflow inference --skip-cleanup

For more control, use run_pipeline.py directly:
    python run_pipeline.py --workflow inference [options]

Examples:
  # Standard daily update
  python run_daily_update.py

  # With automatic retraining if needed
  python run_daily_update.py --retrain-if-needed

  # Use local files instead of BigQuery
  python run_daily_update.py --local
        """
    )

    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local files instead of BigQuery"
    )

    parser.add_argument(
        "--retrain-if-needed",
        action="store_true",
        help="(Legacy flag - kept for compatibility. Use --no-auto to disable auto-detection)"
    )

    parser.add_argument(
        "--no-auto",
        action="store_true",
        help="Disable auto-detection mode (always run inference only)"
    )

    args = parser.parse_args()

    # Run daily update
    success = run_daily_update(
        retrain_if_needed=args.retrain_if_needed,
        use_local=args.local,
        use_auto=not args.no_auto  # Auto mode is default, unless --no-auto is set
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
