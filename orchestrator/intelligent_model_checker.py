#!/usr/bin/env python3
"""
Intelligent Per-Feature Model Checker
======================================
Granular model availability checking with per-feature age thresholds.

Key Features:
- Per-feature model existence and age checking
- Different retraining thresholds for daily/weekly/monthly features
- Smart recommendations: only retrain what's needed
- Reads feature cadences from features_config.yaml
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import yaml
import json


BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "configs" / "features_config.yaml"


def load_feature_config() -> Dict:
    """Load features configuration from YAML."""
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)


def get_feature_cadence_map() -> Dict[str, str]:
    """
    Create a mapping of feature name to cadence (daily/weekly/monthly).

    Returns:
        Dict mapping feature name to cadence
    """
    config = load_feature_config()
    feature_map = {}

    for cadence in ['daily', 'weekly', 'monthly']:
        if cadence in config and 'features' in config[cadence]:
            for feature in config[cadence]['features']:
                # Remove comments if present
                feature_name = feature.split('#')[0].strip()
                feature_map[feature_name] = cadence

    return feature_map


def get_retraining_threshold(cadence: str) -> int:
    """
    Get the retraining threshold in days for a given cadence.

    Daily features: Retrain every 3 months (90 days) - ~90 new data points
    Weekly features: Retrain every 6 months (180 days) - ~26 new data points
    Monthly features: Retrain yearly (365 days) - 12 new data points

    Models need significant new data to learn meaningful patterns.

    Args:
        cadence: 'daily', 'weekly', or 'monthly'

    Returns:
        Threshold in days
    """
    thresholds = {
        'daily': 90,      # Retrain if older than 90 days (3 months)
        'weekly': 180,    # Retrain if older than 180 days (6 months)
        'monthly': 365    # Retrain if older than 365 days (1 year)
    }
    return thresholds.get(cadence, 90)  # Default to 90 days if unknown


def check_feature_model_status(feature_name: str, cadence: str) -> Dict:
    """
    Check the status of a specific feature's model.

    CRITICAL: A feature model is only considered valid if ALL required files exist:
    - nf_bundle_v{version}/ directory (NeuralForecast models)
    - {feature}_ensemble_v{version}.json (ensemble weights for inference)

    Without the ensemble weights file, inference will FAIL even if nf_bundle exists.

    Args:
        feature_name: Name of the feature (e.g., 'GSPC', 'CPI')
        cadence: Feature cadence ('daily', 'weekly', 'monthly')

    Returns:
        Dict with:
            - exists: bool - ALL required model files exist
            - age_days: int or None - Age in days
            - needs_training: bool - Whether retraining is needed
            - reason: str - Explanation
            - missing_files: List[str] - Which required files are missing
    """
    forecasting_dir = BASE_DIR / "outputs" / "forecasting" / "models" / feature_name
    models_base_dir = BASE_DIR / "outputs" / "forecasting" / "models"

    # Check version metadata first to get the active version
    version_metadata_path = models_base_dir / f"{feature_name}_versions.json"

    if not version_metadata_path.exists():
        return {
            'exists': False,
            'age_days': None,
            'needs_training': True,
            'reason': 'Version metadata does not exist',
            'missing_files': ['version_metadata']
        }

    try:
        with open(version_metadata_path, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        return {
            'exists': False,
            'age_days': None,
            'needs_training': True,
            'reason': f'Failed to read version metadata: {e}',
            'missing_files': ['version_metadata']
        }

    active_version = metadata.get('active_version')
    if active_version is None:
        # Try to get from completed versions
        completed = [v for v in metadata.get('versions', []) if v.get('status') == 'completed']
        if completed:
            active_version = max(completed, key=lambda v: v['version'])['version']
        else:
            return {
                'exists': False,
                'age_days': None,
                'needs_training': True,
                'reason': 'No active or completed version found',
                'missing_files': ['completed_version']
            }

    # Check for ALL required model files for this version
    nf_bundle_path = forecasting_dir / f"nf_bundle_v{active_version}"
    ensemble_path = forecasting_dir / f"{feature_name}_ensemble_v{active_version}.json"

    missing_files = []
    if not nf_bundle_path.exists():
        missing_files.append(f"nf_bundle_v{active_version}")
    if not ensemble_path.exists():
        missing_files.append(f"{feature_name}_ensemble_v{active_version}.json")

    # Model is ONLY valid if ALL required files exist
    if missing_files:
        return {
            'exists': False,
            'age_days': None,
            'needs_training': True,
            'reason': f'Missing required files: {", ".join(missing_files)}',
            'missing_files': missing_files
        }

    # All files exist - check age
    # Get age from version metadata
    for version_info in metadata.get('versions', []):
        if version_info.get('version') == active_version:
            timestamp_str = version_info.get('created_at') or version_info.get('timestamp')
            if timestamp_str:
                try:
                    mtime = datetime.fromisoformat(timestamp_str)
                    age_days = (datetime.now() - mtime).days
                    threshold = get_retraining_threshold(cadence)
                    needs_training = age_days > threshold

                    return {
                        'exists': True,
                        'age_days': age_days,
                        'needs_training': needs_training,
                        'reason': f'{age_days} days old (threshold: {threshold} days for {cadence})',
                        'missing_files': []
                    }
                except Exception:
                    pass

    # Fallback: use ensemble file modification time (most accurate for training completion)
    mtime = datetime.fromtimestamp(ensemble_path.stat().st_mtime)
    age_days = (datetime.now() - mtime).days
    threshold = get_retraining_threshold(cadence)
    needs_training = age_days > threshold

    return {
        'exists': True,
        'age_days': age_days,
        'needs_training': needs_training,
        'reason': f'{age_days} days old (threshold: {threshold} days for {cadence})',
        'missing_files': []
    }


def check_all_features() -> Dict[str, Dict]:
    """
    Check status of all features defined in config.

    Returns:
        Dict mapping feature name to status dict
    """
    feature_map = get_feature_cadence_map()
    results = {}

    for feature_name, cadence in feature_map.items():
        results[feature_name] = check_feature_model_status(feature_name, cadence)
        results[feature_name]['cadence'] = cadence

    return results


def get_features_needing_training() -> List[str]:
    """
    Get list of features that need training (missing or too old).

    Returns:
        List of feature names that need training
    """
    all_status = check_all_features()
    return [
        feature_name
        for feature_name, status in all_status.items()
        if status['needs_training']
    ]


def get_core_model_threshold() -> int:
    """
    Get the retraining threshold in days for core models (HMM, RF classifier).

    Core models (HMM + Random Forest) should be retrained every 30 days because:
    - They use daily market data which changes frequently
    - Regime patterns can shift over time
    - 30 days provides ~20 new trading data points for learning
    - Training is fast (~20 seconds total)

    Returns:
        Threshold in days (30)
    """
    return 30


def check_core_models_status() -> Dict:
    """
    Check status of core models (HMM, classifier).

    Returns:
        Dict with status of core models including:
        - Existence of each model
        - Age of each model in days
        - Whether retraining is needed (missing or > 30 days old)
    """
    models_dir = BASE_DIR / "outputs" / "models"

    hmm_path = models_dir / "hmm_model.joblib"
    classifier_path = models_dir / "regime_classifier.joblib"
    cluster_path = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"

    hmm_exists = hmm_path.exists()
    classifier_exists = classifier_path.exists()
    cluster_exists = cluster_path.exists()

    # Check age of each core model
    hmm_age_days = None
    classifier_age_days = None

    if hmm_path.exists():
        mtime = datetime.fromtimestamp(hmm_path.stat().st_mtime)
        hmm_age_days = (datetime.now() - mtime).days

    if classifier_path.exists():
        mtime = datetime.fromtimestamp(classifier_path.stat().st_mtime)
        classifier_age_days = (datetime.now() - mtime).days

    # Use the older of the two for the age_days field
    age_days = None
    if hmm_age_days is not None and classifier_age_days is not None:
        age_days = max(hmm_age_days, classifier_age_days)
    elif hmm_age_days is not None:
        age_days = hmm_age_days
    elif classifier_age_days is not None:
        age_days = classifier_age_days

    # Core models need training if ANY are missing
    needs_training = not (hmm_exists and classifier_exists and cluster_exists)

    # Core models should be retrained every 30 days
    threshold = get_core_model_threshold()
    if age_days is not None and age_days > threshold:
        needs_training = True

    return {
        'hmm_exists': hmm_exists,
        'classifier_exists': classifier_exists,
        'cluster_exists': cluster_exists,
        'hmm_age_days': hmm_age_days,
        'classifier_age_days': classifier_age_days,
        'age_days': age_days,
        'threshold_days': threshold,
        'needs_training': needs_training
    }


def get_intelligent_recommendation() -> Dict:
    """
    Get intelligent recommendation based on all model statuses.

    Returns:
        Dict with:
            - workflow: 'inference' | 'train' | 'partial_train'
            - features_to_train: List of feature names
            - retrain_core: bool - Whether to retrain HMM/classifier
            - reason: str - Explanation
            - details: Dict - Detailed status
    """
    core_status = check_core_models_status()
    features_status = check_all_features()
    features_needing_training = get_features_needing_training()

    # Detailed breakdown
    missing_features = [f for f, s in features_status.items() if not s['exists']]
    stale_features = [f for f, s in features_status.items() if s['exists'] and s['needs_training']]
    fresh_features = [f for f, s in features_status.items() if s['exists'] and not s['needs_training']]

    # Decision logic
    if core_status['needs_training']:
        # Core models missing or stale - retrain core + only missing/stale features
        # DON'T retrain all 22 features if they already exist!
        return {
            'workflow': 'train',
            'features_to_train': features_needing_training,  # Only train missing/stale features, NOT all 22!
            'retrain_core': True,
            'reason': f'Core models (HMM/classifier) missing or stale + {len(features_needing_training)} features need training',
            'details': {
                'core_status': core_status,
                'total_features': len(features_status),
                'missing_features': missing_features,
                'stale_features': stale_features,
                'fresh_features': fresh_features
            }
        }

    if not features_needing_training:
        # All models fresh - just run inference
        return {
            'workflow': 'inference',
            'features_to_train': [],
            'retrain_core': False,
            'reason': f'All {len(features_status)} features are fresh and ready',
            'details': {
                'core_status': core_status,
                'total_features': len(features_status),
                'fresh_features': fresh_features
            }
        }

    # Some features need training - partial retrain
    return {
        'workflow': 'partial_train',
        'features_to_train': features_needing_training,
        'retrain_core': False,
        'reason': f'{len(features_needing_training)} features need training ({len(missing_features)} missing, {len(stale_features)} stale)',
        'details': {
            'core_status': core_status,
            'total_features': len(features_status),
            'missing_features': missing_features,
            'stale_features': stale_features,
            'fresh_features': fresh_features
        }
    }


def print_intelligent_status():
    """Print comprehensive intelligent status report."""
    recommendation = get_intelligent_recommendation()

    print("\n" + "=" * 80)
    print("🧠 INTELLIGENT MODEL STATUS CHECKER")
    print("=" * 80)

    # Core models status
    core = recommendation['details']['core_status']
    threshold = core.get('threshold_days', 30)
    print(f"\n📦 Core Models (threshold: {threshold} days):")
    hmm_age = f" ({core.get('hmm_age_days', '?')} days)" if core.get('hmm_age_days') is not None else ""
    rf_age = f" ({core.get('classifier_age_days', '?')} days)" if core.get('classifier_age_days') is not None else ""
    print(f"   {'✅' if core['hmm_exists'] else '❌'} HMM Model{hmm_age}")
    print(f"   {'✅' if core['classifier_exists'] else '❌'} Regime Classifier{rf_age}")
    print(f"   {'✅' if core['cluster_exists'] else '❌'} Cluster Assignments")
    if core['age_days'] is not None:
        status = "🔴 STALE" if core['age_days'] > threshold else "🟢 FRESH"
        print(f"   ⏰ Age: {core['age_days']} days {status}")

    # Feature models status
    details = recommendation['details']
    print(f"\n📊 Feature Models: {details['total_features']} total")

    if details.get('fresh_features'):
        print(f"   ✅ Fresh: {len(details['fresh_features'])} features")
        for feature in sorted(details['fresh_features'])[:5]:
            print(f"      • {feature}")
        if len(details['fresh_features']) > 5:
            print(f"      ... and {len(details['fresh_features']) - 5} more")

    if details.get('stale_features'):
        print(f"   ⏰ Stale: {len(details['stale_features'])} features")
        for feature in sorted(details['stale_features']):
            status = check_all_features()[feature]
            print(f"      • {feature} ({status['cadence']}, {status['age_days']} days old)")

    if details.get('missing_features'):
        print(f"   ❌ Missing/Incomplete: {len(details['missing_features'])} features")
        all_features_status = check_all_features()
        for feature in sorted(details['missing_features']):
            status = all_features_status[feature]
            missing_info = ""
            if status.get('missing_files'):
                missing_info = f" - missing: {', '.join(status['missing_files'])}"
            print(f"      • {feature} ({status['cadence']}){missing_info}")

    # Recommendation
    print(f"\n💡 Workflow Recommendation: {recommendation['workflow'].upper()}")
    print(f"📝 Reason: {recommendation['reason']}")

    if recommendation['features_to_train']:
        print(f"\n🔧 Features to Train ({len(recommendation['features_to_train'])}):")
        for feature in sorted(recommendation['features_to_train']):
            print(f"   • {feature}")

    if recommendation['retrain_core']:
        print("\n🔄 Core models will be retrained")

    print("=" * 80 + "\n")

    return recommendation


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Intelligent model status checker")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.json:
        import json
        recommendation = get_intelligent_recommendation()
        print(json.dumps(recommendation, indent=2))
    else:
        recommendation = print_intelligent_status()

    # Exit code: 0 if inference ready, 1 if training needed
    exit(0 if recommendation['workflow'] == 'inference' else 1)
