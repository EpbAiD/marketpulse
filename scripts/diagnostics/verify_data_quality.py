#!/usr/bin/env python3
"""
Data Quality Verification Script
Checks all raw and engineered features for quality issues before training
"""

import os
import pandas as pd
import numpy as np
import yaml
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

def check_raw_data_quality():
    """Check quality of raw cleaned features"""
    print("\n" + "="*70)
    print("STEP 3: DATA QUALITY VERIFICATION - RAW FEATURES")
    print("="*70)

    cleaned_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"

    # Load config to know what features we need
    with open(BASE_DIR / "configs" / "features_config.yaml") as f:
        config = yaml.safe_load(f)

    all_features = []
    for cadence in ['daily', 'weekly', 'monthly']:
        features = config[cadence].get('features', [])
        all_features.extend([(f, cadence) for f in features])

    issues = []
    passed = []

    for feature, cadence in all_features:
        file_path = cleaned_dir / f"{feature}.parquet"

        if not file_path.exists():
            issues.append(f"MISSING: {feature} - file does not exist")
            continue

        try:
            df = pd.read_parquet(file_path)

            # Check 1: Has data
            if len(df) == 0:
                issues.append(f"EMPTY: {feature} - no rows")
                continue

            # Check 2: Has date information (either as column or index)
            has_date_col = 'date' in df.columns or 'ds' in df.columns
            has_date_index = df.index.name in ['Date', 'date', 'ds'] or isinstance(df.index, pd.DatetimeIndex)

            if not has_date_col and not has_date_index:
                issues.append(f"NO DATE: {feature} - missing date column or index")
                continue

            # Check 3: Has value information (either as 'value' column or feature-named column)
            if 'value' not in df.columns and feature not in df.columns and len(df.columns) == 0:
                issues.append(f"NO VALUE: {feature} - missing value data")
                continue

            # Standardize: reset index if date is in index
            if has_date_index and not has_date_col:
                df = df.reset_index()
                if df.columns[0] in ['Date', 'date', 'ds']:
                    date_col = df.columns[0]
                else:
                    date_col = 'date'
                    df.rename(columns={df.columns[0]: 'date'}, inplace=True)
            else:
                date_col = 'date' if 'date' in df.columns else 'ds'

            # Standardize: get value column
            if 'value' in df.columns:
                value_col = 'value'
            elif feature in df.columns:
                value_col = feature
            else:
                # Assume first non-date column is the value
                value_col = [c for c in df.columns if c != date_col][0]

            # Check 4: Date range
            df[date_col] = pd.to_datetime(df[date_col])
            min_date = df[date_col].min()
            max_date = df[date_col].max()
            days_span = (max_date - min_date).days

            # Check 5: Missing values
            missing_pct = (df[value_col].isna().sum() / len(df)) * 100

            # Check 6: Infinite values
            inf_count = np.isinf(df[value_col]).sum()

            # Check 7: Constant values (all same)
            is_constant = df[value_col].nunique() == 1

            # Check 7: Sufficient data for training
            min_required = {
                'daily': 500,    # Need at least 500 days
                'weekly': 100,   # Need at least 100 weeks
                'monthly': 60    # Need at least 60 months
            }

            sufficient = len(df) >= min_required[cadence]

            # Determine if passed
            has_issues = False
            feature_issues = []

            if missing_pct > 10:
                feature_issues.append(f">10% missing ({missing_pct:.1f}%)")
                has_issues = True

            if inf_count > 0:
                feature_issues.append(f"{inf_count} infinite values")
                has_issues = True

            if is_constant:
                feature_issues.append("all values are identical")
                has_issues = True

            if not sufficient:
                feature_issues.append(f"only {len(df)} rows, need {min_required[cadence]}")
                has_issues = True

            if has_issues:
                issues.append(f"ISSUES: {feature} - {'; '.join(feature_issues)}")
            else:
                passed.append({
                    'feature': feature,
                    'cadence': cadence,
                    'rows': len(df),
                    'date_range': f"{min_date.date()} to {max_date.date()}",
                    'days_span': days_span,
                    'missing_pct': f"{missing_pct:.2f}%"
                })
                print(f"  ✅ {feature:12s} [{cadence:7s}] - {len(df):5d} rows, {days_span:5d} days, {missing_pct:.1f}% missing")

        except Exception as e:
            issues.append(f"ERROR: {feature} - {str(e)}")

    return passed, issues

def check_engineered_features():
    """Check quality of engineered features"""
    print("\n" + "="*70)
    print("ENGINEERED FEATURES QUALITY")
    print("="*70)

    eng_dir = BASE_DIR / "outputs" / "engineered"

    if not eng_dir.exists():
        return [], ["Engineered directory does not exist"]

    eng_files = list(eng_dir.glob("*.parquet"))

    issues = []
    passed = []

    for file_path in eng_files:
        try:
            df = pd.read_parquet(file_path)

            if len(df) == 0:
                issues.append(f"EMPTY: {file_path.stem}")
                continue

            # Check for features
            n_features = len(df.columns)

            # Check for infinities across all columns
            inf_cols = [col for col in df.columns if np.isinf(df[col]).any()]

            # Check for high missing percentage
            high_missing_cols = []
            for col in df.columns:
                missing_pct = (df[col].isna().sum() / len(df)) * 100
                if missing_pct > 50:
                    high_missing_cols.append(f"{col}({missing_pct:.0f}%)")

            has_issues = False
            feature_issues = []

            if inf_cols:
                feature_issues.append(f"{len(inf_cols)} cols with inf")
                has_issues = True

            if high_missing_cols:
                feature_issues.append(f"{len(high_missing_cols)} cols >50% missing")
                has_issues = True

            if has_issues:
                issues.append(f"ISSUES: {file_path.stem} - {'; '.join(feature_issues)}")
            else:
                passed.append({
                    'feature': file_path.stem,
                    'rows': len(df),
                    'features': n_features
                })
                print(f"  ✅ {file_path.stem:12s} - {len(df):5d} rows, {n_features:2d} features")

        except Exception as e:
            issues.append(f"ERROR: {file_path.stem} - {str(e)}")

    return passed, issues

def main():
    print("\n" + "="*70)
    print("DATA QUALITY VERIFICATION FOR REGIME FORECASTING PIPELINE")
    print("="*70)

    # Check raw data
    raw_passed, raw_issues = check_raw_data_quality()

    # Check engineered features
    eng_passed, eng_issues = check_engineered_features()

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION SUMMARY")
    print("="*70)

    print(f"\nRaw Features:")
    print(f"  ✅ Passed quality checks: {len(raw_passed)}")
    print(f"  ❌ Issues found: {len(raw_issues)}")

    if raw_issues:
        print("\n  Issues:")
        for issue in raw_issues:
            print(f"    - {issue}")

    print(f"\nEngineered Features:")
    print(f"  ✅ Passed quality checks: {len(eng_passed)}")
    print(f"  ❌ Issues found: {len(eng_issues)}")

    if eng_issues:
        print("\n  Issues:")
        for issue in eng_issues:
            print(f"    - {issue}")

    # Recommendations
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)

    if raw_issues or eng_issues:
        print("\n⚠️  Data quality issues detected. Recommended actions:")

        if any("MISSING" in issue for issue in raw_issues):
            print("\n  1. Re-fetch missing features:")
            print("     python -m data_agent.fetcher")

        if any("EMPTY" in issue or "insufficient" in issue.lower() for issue in raw_issues):
            print("\n  2. Check data sources for features with insufficient data")

        if any("ISSUES" in issue for issue in raw_issues + eng_issues):
            print("\n  3. Review and fix data quality issues before training")

        if eng_issues:
            print("\n  4. Regenerate engineered features:")
            print("     python -m data_agent.engineer")

        print("\n⚠️  Fix these issues before proceeding to training!")
        return False
    else:
        print("\n✅ All data quality checks passed!")
        print("\n   Next steps:")
        print("   1. Review the batch training script")
        print("   2. Start training all models")
        return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
