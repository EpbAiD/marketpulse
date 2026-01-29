#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===========================================================
classification_agent/train_classifier.py
===========================================================
Train a supervised model (RandomForest) to predict market
regimes using labeled data from the HMM clustering agent.
===========================================================
"""

import os
import joblib
import json
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    accuracy_score,
    f1_score,
    confusion_matrix,
)
import matplotlib.pyplot as plt
from pandas.tseries.offsets import CustomBusinessDay
from pandas.tseries.holiday import USFederalHolidayCalendar

# -----------------------------------------------------------
# PATH CONFIGURATION
# -----------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_PATH = os.path.join(BASE_DIR, "outputs", "selected", "aligned_dataset.parquet")
LABEL_PATH = os.path.join(BASE_DIR, "outputs", "clustering", "cluster_assignments.parquet")
MODEL_PATH = os.path.join(BASE_DIR, "outputs", "models", "regime_classifier.joblib")
DIAG_DIR = os.path.join(BASE_DIR, "outputs", "diagnostics", "classification")
os.makedirs(DIAG_DIR, exist_ok=True)

REPORT_PATH = os.path.join(DIAG_DIR, "metrics_report.json")
IMPORTANCE_PLOT = os.path.join(DIAG_DIR, "feature_importances.png")

# -----------------------------------------------------------
# TRADING DAY FILTER
# -----------------------------------------------------------
def filter_trading_days(df, target_trading_days=10):
    """
    Ensure forecast contains exactly N trading days.
    Excludes weekends and US federal holidays (NYSE calendar).

    If fewer than N trading days after filtering, returns what's available.
    This handles the case where calendar-day forecasts don't produce enough
    trading days (e.g., holiday weeks).

    Args:
        df: DataFrame with 'ds' column containing forecast dates
        target_trading_days: Target number of trading days (default: 10)

    Returns:
        DataFrame with only trading days
    """
    print(f"🗓️  Filtering to trading days (target: {target_trading_days})...")
    original_count = len(df)

    # Ensure ds is datetime
    df['ds'] = pd.to_datetime(df['ds'])

    # Remove weekends (Saturday=5, Sunday=6)
    df = df[df['ds'].dt.dayofweek < 5].copy()

    # Remove federal holidays
    holidays = USFederalHolidayCalendar().holidays(
        start=df['ds'].min(),
        end=df['ds'].max()
    )
    df = df[~df['ds'].isin(holidays)].copy()

    filtered_count = original_count - len(df)
    trading_days_count = len(df)

    if filtered_count > 0:
        print(f"   ⚠️  Filtered out {filtered_count} non-trading days ({filtered_count/original_count*100:.1f}%)")

    if trading_days_count < target_trading_days:
        print(f"   ⚠️  Only {trading_days_count} trading days available (target: {target_trading_days})")
        print(f"   💡 Holiday/weekend heavy period - consider increasing calendar horizon")
    elif trading_days_count == target_trading_days:
        print(f"   ✅ Perfect: {trading_days_count} trading days")
    else:
        print(f"   ✅ {trading_days_count} trading days (truncating to {target_trading_days})")
        # Take only first N trading days to match target
        df = df.head(target_trading_days)

    return df

# -----------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------
def train_regime_classifier(random_state: int = 42, test_size: float = 0.2, use_bigquery: bool = False):
    print("===========================================================")
    print("🚀 Starting Regime Classifier Training")
    print("===========================================================")

    # --------------------------
    # Load feature & label data
    # --------------------------
    if use_bigquery:
        # Load from BigQuery
        import sys
        sys.path.insert(0, BASE_DIR)
        from data_agent.storage import get_storage

        storage = get_storage(use_bigquery=True)
        X = storage.load_aligned_dataset()
        y = storage.load_cluster_assignments()["regime"]

        if X is None or y is None:
            raise ValueError("Failed to load data from BigQuery")

        print(f"📦 Loaded dataset from BigQuery → X={X.shape}, y={y.shape}")
    else:
        # Load from local files
        if not os.path.exists(DATA_PATH):
            raise FileNotFoundError(f"Feature data not found → {DATA_PATH}")
        if not os.path.exists(LABEL_PATH):
            raise FileNotFoundError(f"Label data not found → {LABEL_PATH}")

        X = pd.read_parquet(DATA_PATH)
        y = pd.read_parquet(LABEL_PATH)["regime"]
        print(f"📦 Loaded dataset from local files → X={X.shape}, y={y.shape}")

    # Ensure index alignment
    X, y = X.align(y, join="inner", axis=0)
    print(f"📦 Aligned dataset → X={X.shape}, y={y.shape}")

    # --------------------------
    # Train/test split
    # --------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    # --------------------------
    # Train model
    # --------------------------
    clf = RandomForestClassifier(
        n_estimators=500,
        max_depth=None,
        random_state=random_state,
        class_weight="balanced_subsample",
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    print("✅ Random Forest training completed.")

    # --------------------------
    # Evaluate model
    # --------------------------
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred, average="weighted")

    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)

    print(f"📊 Accuracy: {acc:.3f} | Weighted F1: {f1:.3f}")
    print("Confusion Matrix:")
    print(cm)

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(f"💾 Saved metrics report → {REPORT_PATH}")

    # --------------------------
    # Feature importances
    # --------------------------
    importances = pd.Series(clf.feature_importances_, index=X.columns)
    importances.sort_values(ascending=False).head(25).plot(kind="bar", figsize=(10, 5))
    plt.title("Top 25 Feature Importances (Random Forest)")
    plt.tight_layout()
    plt.savefig(IMPORTANCE_PLOT, dpi=200)
    plt.close()
    print(f"📈 Saved feature importance plot → {IMPORTANCE_PLOT}")

    # --------------------------
    # Save model
    # --------------------------
    joblib.dump(clf, MODEL_PATH)
    print(f"💾 Saved trained model → {MODEL_PATH}")

    print("===========================================================")
    print("✅ Regime Classifier Training Complete")
    print("===========================================================")
    return clf, report


# -----------------------------------------------------------
# INFERENCE: Predict regimes from engineered forecasted features
# -----------------------------------------------------------
def predict_regimes_from_forecast(
    engineered_features_df: pd.DataFrame,
    selected_features_path: str = None
) -> pd.DataFrame:
    """
    Predict market regimes from engineered forecasted features.

    Args:
        engineered_features_df: DataFrame with columns ['ds', 'feature_name', 'feature_value']
                               from engineer_forecasted_features()
        selected_features_path: Path to features_selected.csv (default: outputs/selected/features_selected.csv)

    Returns:
        DataFrame with columns: ['ds', 'regime', 'regime_probability']
        where each row is a forecasted day with its predicted regime
    """
    print(f"\n{'='*60}")
    print(f"🎯 REGIME PREDICTION FROM FORECASTED FEATURES")
    print(f"{'='*60}\n")

    # Load trained classifier
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"❌ Trained classifier not found → {MODEL_PATH}")

    clf = joblib.load(MODEL_PATH)
    print(f"✅ Loaded trained classifier from {MODEL_PATH}")

    # Use the classifier's own feature names as the source of truth
    # This ensures we match exactly what the model was trained on
    model_features = list(clf.feature_names_in_)
    print(f"✅ Classifier expects {len(model_features)} features")

    # Pivot engineered features to wide format (one row per date)
    print("  🔄 Pivoting engineered features to wide format...")
    pivot_df = engineered_features_df.pivot(
        index='ds',
        columns='feature_name',
        values='feature_value'
    ).reset_index()

    print(f"  📊 Pivoted shape: {pivot_df.shape}")
    print(f"  📅 Date range: {pivot_df['ds'].min()} to {pivot_df['ds'].max()}")

    # Check which features from the model are available in the forecast data
    available_features = [f for f in model_features if f in pivot_df.columns]
    missing_features = [f for f in model_features if f not in pivot_df.columns]

    print(f"  ✅ Found {len(available_features)}/{len(model_features)} features in forecast data")

    if missing_features:
        print(f"  ⚠️ Missing {len(missing_features)} features (will be filled with 0):")
        for f in missing_features[:5]:
            print(f"     - {f}")
        if len(missing_features) > 5:
            print(f"     ... and {len(missing_features) - 5} more")

    # Build feature matrix with exactly the columns the model expects
    X = pd.DataFrame(index=pivot_df.index)

    for feat in model_features:
        if feat in pivot_df.columns:
            X[feat] = pivot_df[feat].values
        else:
            # Fill missing features with 0 (neutral value)
            X[feat] = 0.0

    # Handle any NaN values
    X = X.fillna(0.0)

    print(f"  📊 Feature matrix shape: {X.shape}")

    # Predict regimes
    print("  🔮 Predicting regimes...")
    predicted_regimes = clf.predict(X)
    regime_probabilities = clf.predict_proba(X)

    # Get max probability for each prediction
    max_probabilities = regime_probabilities.max(axis=1)

    # Create results dataframe
    results_df = pd.DataFrame({
        'ds': pivot_df['ds'],
        'regime': predicted_regimes,
        'regime_probability': max_probabilities
    })

    # Add individual class probabilities
    n_classes = regime_probabilities.shape[1]
    for i in range(n_classes):
        results_df[f'regime_{i}_prob'] = regime_probabilities[:, i]

    # ============================================================
    # 🗓️ FILTER TO TRADING DAYS ONLY (exclude weekends + holidays)
    # ============================================================
    results_df = filter_trading_days(results_df)

    # Save results
    output_dir = os.path.join(BASE_DIR, "outputs", "forecasting", "inference")
    os.makedirs(output_dir, exist_ok=True)

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"regime_predictions_{timestamp}.parquet")

    results_df.to_parquet(output_path)

    print(f"\n{'='*60}")
    print(f"✅ Regime prediction complete")
    print(f"   📅 Forecasted {len(results_df)} days")
    print(f"   🎯 Regime distribution:")
    for regime_id in results_df['regime'].unique():
        count = (results_df['regime'] == regime_id).sum()
        pct = count / len(results_df) * 100
        print(f"      Regime {regime_id}: {count} days ({pct:.1f}%)")
    print(f"   📁 Saved to: {output_path}")
    print(f"{'='*60}\n")

    return results_df


# -----------------------------------------------------------
# CLI
# -----------------------------------------------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Train regime classifier")
    parser.add_argument("--use-bigquery", action="store_true", help="Load data from BigQuery")
    args = parser.parse_args()

    train_regime_classifier(use_bigquery=args.use_bigquery)