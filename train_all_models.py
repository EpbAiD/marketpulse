#!/usr/bin/env python3
"""
Batch Training Script for All Forecasting Models
Trains all 22 features with smart batching, progress tracking, and error handling
"""

import os
import sys
import yaml
import time
import gc
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add project root to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from forecasting_agent.forecaster import train_forecaster_for_feature, get_latest_completed_version


def load_feature_config():
    """Load features configuration"""
    config_path = BASE_DIR / "configs" / "features_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_training_queue(config, skip_completed=True):
    """
    Build training queue from config

    Returns:
        List of dicts with feature info: {name, cadence, horizon, val_size, ...}
    """
    queue = []

    for cadence in ['daily', 'weekly', 'monthly']:
        features = config[cadence].get('features', [])
        horizon = config[cadence]['horizon']
        val_size = config[cadence]['val_size']
        nf_loss = config[cadence].get('nf_loss', 'mae')

        for feature in features:
            # Check if already completed
            if skip_completed:
                latest = get_latest_completed_version(feature)
                if latest:
                    print(f"  ⏭️  Skipping {feature} - already trained (v{latest['version']})")
                    continue

            queue.append({
                'name': feature,
                'cadence': cadence,
                'horizon': horizon,
                'val_size': val_size,
                'nf_loss': nf_loss
            })

    return queue


def train_feature_with_retry(feature_info, max_retries=2):
    """
    Train a single feature with retry logic

    Args:
        feature_info: Dict with feature configuration
        max_retries: Number of retry attempts on failure

    Returns:
        (success: bool, metrics: dict or None, error: str or None)
    """
    feature = feature_info['name']
    cadence = feature_info['cadence']

    # Determine file path
    cleaned_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"
    feature_path = cleaned_dir / f"{feature}.parquet"

    if not feature_path.exists():
        return False, None, f"File not found: {feature_path}"

    for attempt in range(max_retries + 1):
        try:
            print(f"\n{'='*70}")
            print(f"Training: {feature} [{cadence}]")
            if attempt > 0:
                print(f"  (Retry attempt {attempt}/{max_retries})")
            print(f"{'='*70}")

            start_time = time.time()

            # Train the feature
            metrics = train_forecaster_for_feature(
                feature_path=str(feature_path),
                cadence=cadence,
                horizon=feature_info['horizon'],
                val_size=feature_info['val_size'],
                force_cpu=True,
                quiet=False,
                test_size=None,  # Auto-calculated: test_size = horizon (industry standard)
                nf_loss=feature_info['nf_loss'].upper(),
                arima_cfg={'order': (1, 0, 0)},  # Default ARIMA
                prophet_cfg={},
                multi_backtest={'rolling_years': 1},
                ens_cfg={},
                use_bigquery=False,
                feature_name=feature,
                force_retrain=False
            )

            elapsed = time.time() - start_time
            print(f"\n✅ {feature} completed in {elapsed/60:.1f} minutes")

            # Force garbage collection to free memory
            gc.collect()

            return True, metrics, None

        except Exception as e:
            elapsed = time.time() - start_time
            error_msg = str(e)
            print(f"\n❌ {feature} failed after {elapsed/60:.1f} minutes: {error_msg}")

            # Force garbage collection
            gc.collect()

            if attempt < max_retries:
                print(f"  Retrying in 5 seconds...")
                time.sleep(5)
            else:
                return False, None, error_msg

    return False, None, "Max retries exceeded"


def main():
    parser = argparse.ArgumentParser(
        description="Train all forecasting models in batches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train all features (skip already completed)
  python train_all_models.py

  # Force retrain all features
  python train_all_models.py --force

  # Train specific cadences only
  python train_all_models.py --daily-only
  python train_all_models.py --weekly-only
  python train_all_models.py --monthly-only
        """
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='Force retrain even if models already exist'
    )

    parser.add_argument(
        '--daily-only',
        action='store_true',
        help='Train only daily features'
    )

    parser.add_argument(
        '--weekly-only',
        action='store_true',
        help='Train only weekly features'
    )

    parser.add_argument(
        '--monthly-only',
        action='store_true',
        help='Train only monthly features'
    )

    parser.add_argument(
        '--max-retries',
        type=int,
        default=2,
        help='Maximum retry attempts per feature (default: 2)'
    )

    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt and start training immediately'
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("🚀 BATCH TRAINING - ALL FORECASTING MODELS")
    print("="*70)
    print(f"  Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Force retrain: {args.force}")
    print(f"  Max retries: {args.max_retries}")
    print("="*70 + "\n")

    # Load configuration
    config = load_feature_config()

    # Filter by cadence if specified
    if args.daily_only:
        config = {'daily': config['daily']}
    elif args.weekly_only:
        config = {'weekly': config['weekly']}
    elif args.monthly_only:
        config = {'monthly': config['monthly']}

    # Build training queue
    print("Building training queue...")
    queue = get_training_queue(config, skip_completed=not args.force)

    if not queue:
        print("\n✅ All features already trained! Use --force to retrain.")
        return

    print(f"\n📋 Training queue: {len(queue)} features")
    for i, f in enumerate(queue, 1):
        print(f"  {i:2d}. {f['name']:12s} [{f['cadence']:7s}]")

    # Confirm before starting
    if not args.yes:
        print("\n" + "="*70)
        response = input("Start training? [y/N]: ")
        if response.lower() != 'y':
            print("Training cancelled.")
            return

    # Track results
    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }

    start_time = time.time()

    # Process queue
    for i, feature_info in enumerate(queue, 1):
        feature = feature_info['name']

        print(f"\n{'='*70}")
        print(f"Progress: {i}/{len(queue)} ({i/len(queue)*100:.1f}%)")
        print(f"{'='*70}")

        # Train feature
        success, metrics, error = train_feature_with_retry(
            feature_info,
            max_retries=args.max_retries
        )

        if success:
            results['success'].append(feature)
        else:
            results['failed'].append((feature, error))

        # Estimate time remaining
        elapsed = time.time() - start_time
        avg_time_per_feature = elapsed / i
        remaining_features = len(queue) - i
        estimated_remaining = avg_time_per_feature * remaining_features

        print(f"\n⏱️  Elapsed: {elapsed/60:.1f} min | Estimated remaining: {estimated_remaining/60:.1f} min")

    # Final summary
    total_elapsed = time.time() - start_time

    print("\n" + "="*70)
    print("📊 TRAINING SUMMARY")
    print("="*70)
    print(f"  Total time: {total_elapsed/60:.1f} minutes ({total_elapsed/3600:.2f} hours)")
    print(f"  End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n  ✅ Successful: {len(results['success'])}/{len(queue)}")

    if results['success']:
        for f in results['success']:
            print(f"     - {f}")

    print(f"\n  ❌ Failed: {len(results['failed'])}/{len(queue)}")

    if results['failed']:
        for f, err in results['failed']:
            print(f"     - {f}: {err[:80]}...")

    print("\n" + "="*70)

    # Save summary to file
    summary_path = BASE_DIR / "outputs" / "training_summary.txt"
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(summary_path, 'w') as f:
        f.write(f"Training Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n")
        f.write(f"Total time: {total_elapsed/60:.1f} minutes\n")
        f.write(f"Successful: {len(results['success'])}/{len(queue)}\n")
        f.write(f"Failed: {len(results['failed'])}/{len(queue)}\n\n")

        f.write("Successful:\n")
        for feature in results['success']:
            f.write(f"  - {feature}\n")

        f.write("\nFailed:\n")
        for feature, error in results['failed']:
            f.write(f"  - {feature}: {error}\n")

    print(f"📝 Summary saved to: {summary_path}\n")

    # Exit code
    if results['failed']:
        sys.exit(1)
    else:
        print("✅ All models trained successfully!\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
