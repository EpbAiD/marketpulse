#!/usr/bin/env python3
"""
Model Availability Checker
===========================
Checks if all required models are trained and available for inference.
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


BASE_DIR = Path(__file__).parent.parent


def check_models_exist() -> Dict[str, bool]:
    """
    Check if all required model files exist.

    Returns:
        Dict with model names and their availability status
    """
    models_dir = BASE_DIR / "outputs" / "models"
    forecasting_dir = BASE_DIR / "outputs" / "forecasting" / "models"

    # Check for actual file extensions used by the system
    required_models = {
        "hmm_model": models_dir / "hmm_model.joblib",
        "classifier": models_dir / "regime_classifier.joblib",
        "forecasting_models": forecasting_dir  # Directory with feature models
    }

    status = {}
    for model_name, model_path in required_models.items():
        if model_name == "forecasting_models":
            # Check if forecasting directory exists and has models
            if model_path.exists():
                # Check if there are any feature model directories
                feature_dirs = list(model_path.glob("*/nf_bundle_v*"))
                status[model_name] = len(feature_dirs) > 0
            else:
                status[model_name] = False
        else:
            status[model_name] = model_path.exists()

    return status


def check_cluster_assignments_exist() -> bool:
    """Check if cluster assignments (historical regimes) exist."""
    cluster_file = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
    return cluster_file.exists()


def check_models_age() -> Optional[int]:
    """
    Check age of models in days.

    Returns:
        Age in days, or None if models don't exist
    """
    models_dir = BASE_DIR / "outputs" / "models"

    # Check the most critical model file (using actual extension)
    classifier_path = models_dir / "regime_classifier.joblib"

    if not classifier_path.exists():
        return None

    # Get modification time
    mtime = datetime.fromtimestamp(classifier_path.stat().st_mtime)
    age_days = (datetime.now() - mtime).days

    return age_days


def are_models_ready_for_inference(max_age_days: int = 30) -> Dict[str, any]:
    """
    Comprehensive check if models are ready for inference.

    Args:
        max_age_days: Maximum acceptable model age in days

    Returns:
        Dict with:
            - ready: bool - True if models are ready
            - reason: str - Explanation
            - models_status: Dict - Status of each model
            - age_days: int - Age of models in days (if available)
            - recommendation: str - What to do
    """
    models_status = check_models_exist()
    cluster_exists = check_cluster_assignments_exist()
    age_days = check_models_age()

    # Check if all models exist
    all_models_exist = all(models_status.values()) and cluster_exists

    if not all_models_exist:
        missing = [name for name, exists in models_status.items() if not exists]
        if not cluster_exists:
            missing.append("cluster_assignments")

        return {
            "ready": False,
            "reason": f"Missing required models: {', '.join(missing)}",
            "models_status": models_status,
            "cluster_exists": cluster_exists,
            "age_days": age_days,
            "recommendation": "train"
        }

    # Check if models are too old
    if age_days is not None and age_days > max_age_days:
        return {
            "ready": False,
            "reason": f"Models are {age_days} days old (max: {max_age_days} days)",
            "models_status": models_status,
            "cluster_exists": cluster_exists,
            "age_days": age_days,
            "recommendation": "retrain"
        }

    # All good!
    return {
        "ready": True,
        "reason": f"All models present and fresh ({age_days} days old)",
        "models_status": models_status,
        "cluster_exists": cluster_exists,
        "age_days": age_days,
        "recommendation": "inference"
    }


def print_model_status(max_age_days: int = 30):
    """Print a human-readable model status report."""
    status = are_models_ready_for_inference(max_age_days)

    print("\n" + "=" * 70)
    print("📊 MODEL AVAILABILITY CHECK")
    print("=" * 70)

    print(f"\n✅ Ready for inference: {'YES' if status['ready'] else 'NO'}")
    print(f"📝 Reason: {status['reason']}")

    print("\n📦 Model Status:")
    for model_name, exists in status['models_status'].items():
        icon = "✅" if exists else "❌"
        print(f"   {icon} {model_name}: {'Present' if exists else 'Missing'}")

    cluster_icon = "✅" if status['cluster_exists'] else "❌"
    print(f"   {cluster_icon} cluster_assignments: {'Present' if status['cluster_exists'] else 'Missing'}")

    if status['age_days'] is not None:
        print(f"\n⏰ Model Age: {status['age_days']} days (max: {max_age_days} days)")

    print(f"\n💡 Recommendation: {status['recommendation'].upper()}")
    print("=" * 70 + "\n")

    return status


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check model availability for inference")
    parser.add_argument("--max-age", type=int, default=30,
                       help="Maximum model age in days (default: 30)")
    args = parser.parse_args()

    status = print_model_status(max_age_days=args.max_age)

    # Exit code: 0 if ready, 1 if not ready
    exit(0 if status['ready'] else 1)
