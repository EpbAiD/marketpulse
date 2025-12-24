#!/usr/bin/env python3
"""
Pipeline Status Checker
Verifies data, features, and models are complete and ready
"""

import os
import yaml
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "configs" / "features_config.yaml"

def check_data():
    """Check raw data availability"""
    print("\n" + "="*70)
    print("📊 CHECKING RAW DATA")
    print("="*70)

    cleaned_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        features = config[cadence].get('features', [])
        all_features.extend([(f, cadence) for f in features])

    print(f"\nConfigured features: {len(all_features)}")

    missing = []
    present = []

    for feature, cadence in all_features:
        file_path = cleaned_dir / f"{feature}.parquet"
        if file_path.exists():
            df = pd.read_parquet(file_path)
            present.append((feature, cadence, len(df)))
            print(f"  ✅ {feature:12s} [{cadence:7s}] - {len(df):,} rows")
        else:
            missing.append((feature, cadence))
            print(f"  ❌ {feature:12s} [{cadence:7s}] - MISSING")

    print(f"\n✅ Present: {len(present)}/{len(all_features)}")
    if missing:
        print(f"❌ Missing: {len(missing)}")
        for f, c in missing:
            print(f"   - {f} [{c}]")

    return all_features, missing

def check_engineered_features():
    """Check engineered features"""
    print("\n" + "="*70)
    print("🔧 CHECKING ENGINEERED FEATURES")
    print("="*70)

    eng_dir = BASE_DIR / "outputs" / "engineered"

    if not eng_dir.exists():
        print("❌ Engineered directory doesn't exist")
        return []

    eng_files = list(eng_dir.glob("*.parquet"))
    print(f"\nEngineered feature files: {len(eng_files)}")

    for f in sorted(eng_files)[:10]:  # Show first 10
        df = pd.read_parquet(f)
        print(f"  ✅ {f.stem:12s} - {len(df.columns)} features, {len(df):,} rows")

    if len(eng_files) > 10:
        print(f"  ... and {len(eng_files) - 10} more")

    return eng_files

def check_models():
    """Check trained forecasting models"""
    print("\n" + "="*70)
    print("🤖 CHECKING FORECASTING MODELS")
    print("="*70)

    models_dir = BASE_DIR / "outputs" / "forecasting" / "models"

    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        features = config[cadence].get('features', [])
        all_features.extend([(f, cadence) for f in features])

    trained = []
    missing = []

    for feature, cadence in all_features:
        feature_dir = models_dir / feature
        version_file = models_dir / f"{feature}_versions.json"

        if version_file.exists():
            import json
            with open(version_file) as f:
                versions = json.load(f)

            active_version = versions.get('active_version')
            if active_version:
                trained.append((feature, cadence, active_version))
                print(f"  ✅ {feature:12s} [{cadence:7s}] - v{active_version}")
            else:
                missing.append((feature, cadence))
                print(f"  ⚠️  {feature:12s} [{cadence:7s}] - no active version")
        else:
            missing.append((feature, cadence))
            print(f"  ❌ {feature:12s} [{cadence:7s}] - NO MODELS")

    print(f"\n✅ Trained: {len(trained)}/{len(all_features)}")
    if missing:
        print(f"❌ Missing: {len(missing)}")
        print("\nFeatures needing training:")
        for f, c in missing:
            print(f"   - {f} [{c}]")

    return trained, missing

def check_classifier():
    """Check regime classifier"""
    print("\n" + "="*70)
    print("🎯 CHECKING REGIME CLASSIFIER")
    print("="*70)

    classifier_path = BASE_DIR / "outputs" / "models" / "regime_classifier.joblib"
    selected_features_path = BASE_DIR / "outputs" / "selected" / "features_selected.csv"
    cluster_assignments_path = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"

    issues = []

    if classifier_path.exists():
        print(f"  ✅ Classifier model exists")
    else:
        print(f"  ❌ Classifier model MISSING")
        issues.append("classifier")

    if selected_features_path.exists():
        df = pd.read_csv(selected_features_path)
        print(f"  ✅ Selected features: {len(df)} features")
    else:
        print(f"  ❌ Selected features list MISSING")
        issues.append("selected_features")

    if cluster_assignments_path.exists():
        df = pd.read_parquet(cluster_assignments_path)
        print(f"  ✅ Cluster assignments: {len(df)} samples")
        print(f"     Regime distribution:")
        for regime, count in df['regime'].value_counts().sort_index().items():
            print(f"       Regime {regime}: {count:,} samples")
    else:
        print(f"  ❌ Cluster assignments MISSING")
        issues.append("clusters")

    return issues

def main():
    print("\n" + "="*70)
    print("🔍 REGIME FORECASTING PIPELINE - STATUS CHECK")
    print("="*70)

    # Check each component
    all_features, missing_data = check_data()
    eng_files = check_engineered_features()
    trained_models, missing_models = check_models()
    classifier_issues = check_classifier()

    # Summary
    print("\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)

    total_features = len(all_features)

    print(f"\n1. Raw Data:")
    print(f"   ✅ {total_features - len(missing_data)}/{total_features} features available")
    if missing_data:
        print(f"   ❌ Need to fetch: {', '.join([f for f, _ in missing_data])}")

    print(f"\n2. Engineered Features:")
    print(f"   ✅ {len(eng_files)} files generated")
    if len(eng_files) < total_features:
        print(f"   ⚠️  Expected {total_features}, may need regeneration")

    print(f"\n3. Forecasting Models:")
    print(f"   ✅ {len(trained_models)}/{total_features} features trained")
    if missing_models:
        print(f"   ❌ Need to train: {len(missing_models)} features")
        print(f"      {', '.join([f for f, _ in missing_models[:5]])}{'...' if len(missing_models) > 5 else ''}")

    print(f"\n4. Regime Classifier:")
    if not classifier_issues:
        print(f"   ✅ All components ready")
    else:
        print(f"   ❌ Missing: {', '.join(classifier_issues)}")

    # Recommendations
    print("\n" + "="*70)
    print("💡 RECOMMENDATIONS")
    print("="*70)

    steps = []

    if missing_data:
        steps.append("1. Fetch missing raw data: python -m data_agent.fetcher")

    if len(eng_files) < total_features:
        steps.append("2. Regenerate engineered features: python -m data_agent.engineer")

    if missing_models:
        steps.append(f"3. Train forecasting models ({len(missing_models)} features):")
        steps.append("   python -m forecasting_agent.forecaster --mode all")

    if 'selected_features' in classifier_issues or 'clusters' in classifier_issues:
        steps.append("4. Run feature selection: python -m data_agent.selector")
        steps.append("5. Run clustering: python -m clustering_agent.clustering")

    if 'classifier' in classifier_issues:
        steps.append("6. Train classifier: python -m classification_agent.classifier")

    if steps:
        print("\nTo complete the pipeline, run these commands in order:\n")
        for step in steps:
            print(f"  {step}")
    else:
        print("\n✅ Pipeline is complete! Ready for inference.")
        print("\nTo run inference:")
        print("  python -m orchestrator.inference --horizon 10")

    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
