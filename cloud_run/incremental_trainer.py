#!/usr/bin/env python3
"""
Incremental Training Script for Cloud Run
==========================================
Trains features one at a time with immediate git commits after each completes.
This ensures that even if the job times out, completed work is preserved.

Features:
- Commits models to GitHub immediately after each feature completes
- Skips features that already have models in the repo (resume capability)
- Avoids lightning_logs conflicts by training sequentially
- Supports feature subsets for parallel job splitting
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from datetime import datetime
import yaml

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


def run_git_command(cmd, cwd=None):
    """Run a git command and return success status."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            print(f"  ⚠️ Git command failed: {' '.join(cmd)}")
            print(f"     stderr: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ Git command timed out: {' '.join(cmd)}")
        return False
    except Exception as e:
        print(f"  ⚠️ Git error: {e}")
        return False


def commit_and_push_feature(feature_name, repo_dir):
    """Commit and push a single feature's models to GitHub."""
    print(f"\n📤 Committing {feature_name} models to GitHub...")

    model_dir = os.path.join(repo_dir, "outputs", "forecasting", "models", feature_name)
    metrics_dir = os.path.join(repo_dir, "outputs", "forecasting", "metrics")

    # Check if model directory exists
    if not os.path.exists(model_dir):
        print(f"  ⚠️ No model directory found for {feature_name}")
        return False

    # Stage feature-specific files
    files_to_add = []

    # Add model directory
    if os.path.exists(model_dir):
        files_to_add.append(f"outputs/forecasting/models/{feature_name}/")

    # Add metrics files for this feature
    if os.path.exists(metrics_dir):
        for f in os.listdir(metrics_dir):
            if f.startswith(feature_name):
                files_to_add.append(f"outputs/forecasting/metrics/{f}")

    if not files_to_add:
        print(f"  ℹ️ No files to commit for {feature_name}")
        return True

    # Git add
    for f in files_to_add:
        run_git_command(["git", "add", f], cwd=repo_dir)

    # Check if there are staged changes
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=repo_dir,
        capture_output=True
    )

    if result.returncode == 0:
        print(f"  ℹ️ No changes to commit for {feature_name}")
        return True

    # Commit
    commit_msg = f"chore: trained {feature_name} model [Cloud Run] [skip ci]"
    if not run_git_command(["git", "commit", "-m", commit_msg], cwd=repo_dir):
        return False

    # Pull and push with retries
    for attempt in range(3):
        # Pull with rebase
        run_git_command(["git", "pull", "--rebase", "origin", "main"], cwd=repo_dir)

        # Push
        if run_git_command(["git", "push", "origin", "main"], cwd=repo_dir):
            print(f"  ✅ {feature_name} models pushed to GitHub!")
            return True

        print(f"  ⚠️ Push failed, retrying ({attempt + 1}/3)...")

    print(f"  ❌ Failed to push {feature_name} after 3 attempts")
    return False


def check_feature_exists_in_repo(feature_name, repo_dir):
    """Check if a feature already has completed models in the repo."""
    model_dir = os.path.join(repo_dir, "outputs", "forecasting", "models", feature_name)
    metadata_path = os.path.join(model_dir, f"{feature_name}_version_metadata.json")

    if not os.path.exists(metadata_path):
        return False

    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # Check if there's a completed version
        completed = [v for v in metadata.get("versions", []) if v.get("status") == "completed"]
        if completed:
            latest = max(completed, key=lambda v: v["version"])
            print(f"  ✅ {feature_name} v{latest['version']} already exists (completed)")
            return True
    except Exception as e:
        print(f"  ⚠️ Error checking {feature_name} metadata: {e}")

    return False


def get_features_to_train(config_path, feature_subset=None):
    """Get list of features to train from config."""
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        features = config.get(cadence, {}).get('features', [])
        all_features.extend(features)

    # Remove duplicates while preserving order
    seen = set()
    unique_features = []
    for f in all_features:
        if f not in seen:
            seen.add(f)
            unique_features.append(f)

    # Filter to subset if specified
    if feature_subset:
        subset_list = [f.strip() for f in feature_subset.split(',')]
        unique_features = [f for f in unique_features if f in subset_list]

    return unique_features


def train_single_feature(feature_name, config_path, use_bigquery=True, force_retrain=False):
    """Train a single feature's models."""
    print(f"\n{'='*60}")
    print(f"🏋️ Training: {feature_name}")
    print(f"{'='*60}")

    try:
        from forecasting_agent import forecaster

        # Train just this feature
        forecaster.run_forecasting_agent(
            mode='all',
            config_path=config_path,
            use_bigquery=use_bigquery,
            force_retrain=force_retrain,
            selective_features=[feature_name]
        )

        print(f"✅ {feature_name} training completed!")
        return True

    except Exception as e:
        print(f"❌ {feature_name} training failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_incremental_training(
    config_path="configs/features_config.yaml",
    feature_subset=None,
    use_bigquery=True,
    force_retrain=False,
    repo_dir=None,
    skip_existing=True
):
    """
    Run incremental training with immediate commits after each feature.

    Args:
        config_path: Path to features_config.yaml
        feature_subset: Comma-separated list of features to train (None = all)
        use_bigquery: Whether to use BigQuery for data
        force_retrain: Whether to force retraining even if models exist
        repo_dir: Git repository directory (for commits)
        skip_existing: Whether to skip features that already have models
    """
    print("\n" + "=" * 70)
    print("🚀 INCREMENTAL TRAINING WITH IMMEDIATE COMMITS")
    print("=" * 70)
    print(f"Config: {config_path}")
    print(f"Feature subset: {feature_subset or 'all'}")
    print(f"Skip existing: {skip_existing}")
    print(f"Force retrain: {force_retrain}")
    print("=" * 70 + "\n")

    # Get features to train
    features = get_features_to_train(config_path, feature_subset)
    print(f"📋 Features to process: {len(features)}")
    for i, f in enumerate(features, 1):
        print(f"   {i:2d}. {f}")

    # Track results
    results = {
        "completed": [],
        "skipped": [],
        "failed": [],
        "start_time": datetime.now().isoformat()
    }

    # Process each feature
    for i, feature_name in enumerate(features, 1):
        print(f"\n{'#'*70}")
        print(f"# Feature {i}/{len(features)}: {feature_name}")
        print(f"{'#'*70}")

        # Check if we should skip
        if skip_existing and not force_retrain and repo_dir:
            if check_feature_exists_in_repo(feature_name, repo_dir):
                print(f"⏭️  Skipping {feature_name} (already exists)")
                results["skipped"].append(feature_name)
                continue

        # Train the feature
        success = train_single_feature(
            feature_name=feature_name,
            config_path=config_path,
            use_bigquery=use_bigquery,
            force_retrain=force_retrain
        )

        if success:
            results["completed"].append(feature_name)

            # Immediately commit and push
            if repo_dir:
                commit_and_push_feature(feature_name, repo_dir)
        else:
            results["failed"].append(feature_name)

    # Final summary
    results["end_time"] = datetime.now().isoformat()

    print("\n" + "=" * 70)
    print("📊 TRAINING SUMMARY")
    print("=" * 70)
    print(f"✅ Completed: {len(results['completed'])} features")
    for f in results['completed']:
        print(f"   - {f}")

    if results['skipped']:
        print(f"\n⏭️  Skipped: {len(results['skipped'])} features (already exist)")
        for f in results['skipped']:
            print(f"   - {f}")

    if results['failed']:
        print(f"\n❌ Failed: {len(results['failed'])} features")
        for f in results['failed']:
            print(f"   - {f}")

    print("=" * 70 + "\n")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Incremental trainer with immediate commits")
    parser.add_argument("--config", default="configs/features_config.yaml", help="Config file path")
    parser.add_argument("--features", help="Comma-separated feature subset (e.g., 'VIX,GSPC,DXY')")
    parser.add_argument("--no-bigquery", action="store_true", help="Don't use BigQuery")
    parser.add_argument("--force-retrain", action="store_true", help="Force retraining all")
    parser.add_argument("--repo-dir", help="Git repo directory for commits")
    parser.add_argument("--no-skip", action="store_true", help="Don't skip existing models")

    args = parser.parse_args()

    results = run_incremental_training(
        config_path=args.config,
        feature_subset=args.features,
        use_bigquery=not args.no_bigquery,
        force_retrain=args.force_retrain,
        repo_dir=args.repo_dir,
        skip_existing=not args.no_skip
    )

    # Exit with error if any failed
    if results['failed']:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
