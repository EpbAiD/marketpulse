#!/usr/bin/env python3
"""
Validate Regime Forecasts Against Historical Evidence
Compares forecasted regime characteristics vs historical regime statistics
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


def load_historical_regime_data():
    """
    Load historical cluster assignments and raw features
    """
    print("\n" + "="*70)
    print("LOADING HISTORICAL REGIME DATA")
    print("="*70)
    print()

    # Load cluster assignments (historical regime labels)
    cluster_path = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
    cluster_df = pd.read_parquet(cluster_path)

    if isinstance(cluster_df.index, pd.DatetimeIndex):
        cluster_df = cluster_df.reset_index()
        cluster_df.rename(columns={'index': 'ds'}, inplace=True)

    cluster_df['ds'] = pd.to_datetime(cluster_df['ds'])

    print(f"✅ Historical regimes: {len(cluster_df)} days")
    print(f"   Date range: {cluster_df['ds'].min().date()} to {cluster_df['ds'].max().date()}")
    print(f"   Regime distribution:")
    regime_counts = cluster_df['regime'].value_counts().sort_index()
    for regime, count in regime_counts.items():
        pct = (count / len(cluster_df)) * 100
        print(f"      Regime {int(regime)}: {count} days ({pct:.1f}%)")
    print()

    # Load raw features (historical)
    print("Loading raw features from cleaned data...")
    raw_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"

    all_features = []
    for feature_file in raw_dir.glob("*.parquet"):
        feature_name = feature_file.stem

        df = pd.read_parquet(feature_file)

        # Standardize format
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index()
            date_col = df.columns[0]
            value_col = df.columns[1] if len(df.columns) > 1 else feature_name
        else:
            date_col = 'date' if 'date' in df.columns else 'ds'
            value_col = feature_name if feature_name in df.columns else 'value'

        df = df.rename(columns={date_col: "ds", value_col: feature_name})
        df['ds'] = pd.to_datetime(df['ds'])
        df = df[['ds', feature_name]]

        all_features.append(df)

    # Merge all features
    features_df = all_features[0]
    for df in all_features[1:]:
        features_df = features_df.merge(df, on='ds', how='outer')

    features_df = features_df.sort_values('ds').reset_index(drop=True)

    print(f"✅ Historical raw features: {len(features_df)} days")
    print(f"   Feature columns: {len(features_df.columns) - 1}")
    print()

    # Merge regime labels with features
    historical_df = features_df.merge(cluster_df[['ds', 'regime']], on='ds', how='inner')

    print(f"✅ Combined historical data: {len(historical_df)} days with regime labels and features")
    print()

    return historical_df


def compute_regime_statistics(historical_df):
    """
    Compute comprehensive statistics for each historical regime
    """
    print("\n" + "="*70)
    print("COMPUTING HISTORICAL REGIME STATISTICS")
    print("="*70)
    print()

    # Key raw features to analyze
    key_features = [
        'VIX', 'VIX3M', 'VIX9D',
        'DXY', 'UUP',
        'GSPC', 'IXIC',
        'DGS10', 'DGS2', 'DGS3MO', 'T10Y2Y', 'TNX', 'DFF',
        'HY_YIELD', 'IG_YIELD',
        'NFCI',
        'UNRATE', 'CPI', 'INDPRO',
        'GOLD', 'OIL', 'COPPER'
    ]

    # Filter to available features
    available_features = [f for f in key_features if f in historical_df.columns]

    print(f"Analyzing {len(available_features)} key features:")
    for f in available_features:
        print(f"  - {f}")
    print()

    regime_stats = {}

    for regime in sorted(historical_df['regime'].unique()):
        regime_data = historical_df[historical_df['regime'] == regime]

        print(f"\n{'='*70}")
        print(f"REGIME {int(regime)} STATISTICS ({len(regime_data)} days)")
        print(f"{'='*70}")
        print()

        stats = {
            'regime': int(regime),
            'n_days': len(regime_data),
            'percentage': (len(regime_data) / len(historical_df)) * 100,
            'features': {}
        }

        print(f"{'Feature':<20} {'Mean':>12} {'Std':>12} {'Min':>12} {'Max':>12}")
        print("-" * 70)

        for feature in available_features:
            if feature in regime_data.columns:
                feature_data = regime_data[feature].dropna()

                if len(feature_data) > 0:
                    feature_stats = {
                        'mean': feature_data.mean(),
                        'std': feature_data.std(),
                        'median': feature_data.median(),
                        'min': feature_data.min(),
                        'max': feature_data.max(),
                        'q25': feature_data.quantile(0.25),
                        'q75': feature_data.quantile(0.75)
                    }

                    stats['features'][feature] = feature_stats

                    print(f"{feature:<20} {feature_stats['mean']:>12.3f} {feature_stats['std']:>12.3f} "
                          f"{feature_stats['min']:>12.3f} {feature_stats['max']:>12.3f}")

        regime_stats[int(regime)] = stats

    return regime_stats, available_features


def load_forecast_regime_data():
    """
    Load most recent regime forecasts
    """
    print("\n" + "="*70)
    print("LOADING REGIME FORECASTS")
    print("="*70)
    print()

    forecast_dir = BASE_DIR / "outputs" / "inference"

    # Load regime forecasts
    regime_files = sorted(forecast_dir.glob("regime_forecast_*.csv"))
    if not regime_files:
        print("❌ No regime forecast files found")
        return None, None

    latest_regime_file = regime_files[-1]
    regime_forecast_df = pd.read_csv(latest_regime_file)
    regime_forecast_df['ds'] = pd.to_datetime(regime_forecast_df['ds'])

    print(f"✅ Loaded regime forecasts from: {latest_regime_file.name}")
    print(f"   Forecast period: {regime_forecast_df['ds'].min().date()} to {regime_forecast_df['ds'].max().date()}")
    print(f"   Total days: {len(regime_forecast_df)}")
    print()

    # Load raw forecasts to compute feature values
    raw_forecast_files = sorted(forecast_dir.glob("raw_forecasts_*.parquet"))
    if not raw_forecast_files:
        print("❌ No raw forecast files found")
        return regime_forecast_df, None

    latest_raw_file = raw_forecast_files[-1]
    raw_forecast_df = pd.read_parquet(latest_raw_file)
    raw_forecast_df['ds'] = pd.to_datetime(raw_forecast_df['ds'])

    print(f"✅ Loaded raw feature forecasts from: {latest_raw_file.name}")
    print(f"   Features: {raw_forecast_df['feature'].nunique()}")
    print()

    # Pivot to wide format for easier analysis
    forecast_features_wide = raw_forecast_df.pivot(
        index='ds',
        columns='feature',
        values='forecast_value'
    ).reset_index()

    print(f"✅ Forecast features pivoted: {len(forecast_features_wide)} days × {len(forecast_features_wide.columns)-1} features")
    print()

    return regime_forecast_df, forecast_features_wide


def compare_forecast_vs_historical_regimes(regime_forecast_df, forecast_features_df, regime_stats, available_features):
    """
    Compare forecasted regime characteristics against historical regime statistics
    """
    print("\n" + "="*70)
    print("COMPARING FORECAST VS HISTORICAL REGIME CHARACTERISTICS")
    print("="*70)
    print()

    if forecast_features_df is None:
        print("⚠️  No forecast feature data available for comparison")
        return None

    results = []

    for _, forecast_row in regime_forecast_df.iterrows():
        forecast_date = forecast_row['ds']
        predicted_regime = int(forecast_row['regime'])
        confidence = forecast_row['regime_probability']

        print(f"\n{forecast_date.date()}: Predicted Regime {predicted_regime} (confidence: {confidence*100:.1f}%)")
        print("-" * 70)

        # Get forecasted feature values for this date
        if forecast_date not in forecast_features_df['ds'].values:
            print("  ⚠️  No forecast features available for this date")
            continue

        forecast_features = forecast_features_df[forecast_features_df['ds'] == forecast_date].iloc[0]

        # Get historical statistics for predicted regime
        if predicted_regime not in regime_stats:
            print(f"  ⚠️  No historical statistics for Regime {predicted_regime}")
            continue

        historical_stats = regime_stats[predicted_regime]

        # Compare each feature
        alignment_scores = []
        feature_comparisons = []

        for feature in available_features:
            if feature not in forecast_features.index or pd.isna(forecast_features[feature]):
                continue

            if feature not in historical_stats['features']:
                continue

            forecast_value = forecast_features[feature]
            hist_stats = historical_stats['features'][feature]

            # Calculate z-score: how many standard deviations from historical mean
            if hist_stats['std'] > 0:
                z_score = (forecast_value - hist_stats['mean']) / hist_stats['std']
            else:
                z_score = 0

            # Check if forecast value is within historical range
            within_range = hist_stats['min'] <= forecast_value <= hist_stats['max']

            # Check if within 1 std of mean (68% of historical data)
            within_1std = abs(z_score) <= 1.0

            # Check if within 2 std of mean (95% of historical data)
            within_2std = abs(z_score) <= 2.0

            # Alignment score: 1.0 if within 1std, 0.5 if within 2std, 0.0 otherwise
            if within_1std:
                alignment = 1.0
            elif within_2std:
                alignment = 0.5
            else:
                alignment = 0.0

            alignment_scores.append(alignment)

            feature_comparisons.append({
                'feature': feature,
                'forecast_value': forecast_value,
                'historical_mean': hist_stats['mean'],
                'historical_std': hist_stats['std'],
                'z_score': z_score,
                'within_range': within_range,
                'alignment': alignment
            })

            # Print notable deviations
            if abs(z_score) > 2.0:
                print(f"  ⚠️  {feature}: {forecast_value:.3f} (historical: {hist_stats['mean']:.3f} ± {hist_stats['std']:.3f}, z={z_score:.2f})")

        # Overall alignment score
        if alignment_scores:
            overall_alignment = np.mean(alignment_scores)
            print(f"\n  Overall Alignment: {overall_alignment*100:.1f}%")
            print(f"  Features analyzed: {len(alignment_scores)}")
            print(f"  Within 1σ: {sum(1 for s in alignment_scores if s == 1.0)}/{len(alignment_scores)}")
            print(f"  Within 2σ: {sum(1 for s in alignment_scores if s >= 0.5)}/{len(alignment_scores)}")

            results.append({
                'date': forecast_date,
                'predicted_regime': predicted_regime,
                'confidence': confidence,
                'overall_alignment': overall_alignment,
                'n_features_analyzed': len(alignment_scores),
                'features_within_1std': sum(1 for s in alignment_scores if s == 1.0),
                'features_within_2std': sum(1 for s in alignment_scores if s >= 0.5),
                'feature_comparisons': feature_comparisons
            })
        else:
            print("  ⚠️  No features available for comparison")

    return results


def generate_validation_summary(results, regime_stats):
    """
    Generate summary of validation results
    """
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    print()

    if not results:
        print("❌ No validation results available")
        return

    results_df = pd.DataFrame([{
        'date': r['date'],
        'predicted_regime': r['predicted_regime'],
        'confidence': r['confidence'],
        'alignment': r['overall_alignment'],
        'n_features': r['n_features_analyzed']
    } for r in results])

    print(f"Total forecasts validated: {len(results_df)}")
    print()

    print("Overall Statistics:")
    print("-" * 70)
    print(f"Mean alignment score: {results_df['alignment'].mean()*100:.1f}%")
    print(f"Median alignment score: {results_df['alignment'].median()*100:.1f}%")
    print(f"Min alignment score: {results_df['alignment'].min()*100:.1f}%")
    print(f"Max alignment score: {results_df['alignment'].max()*100:.1f}%")
    print()

    print("Alignment Score Distribution:")
    print("-" * 70)
    excellent = (results_df['alignment'] >= 0.8).sum()
    good = ((results_df['alignment'] >= 0.6) & (results_df['alignment'] < 0.8)).sum()
    moderate = ((results_df['alignment'] >= 0.4) & (results_df['alignment'] < 0.6)).sum()
    poor = (results_df['alignment'] < 0.4).sum()

    total = len(results_df)
    print(f"Excellent (≥80%): {excellent}/{total} ({excellent/total*100:.1f}%)")
    print(f"Good (60-80%):    {good}/{total} ({good/total*100:.1f}%)")
    print(f"Moderate (40-60%): {moderate}/{total} ({moderate/total*100:.1f}%)")
    print(f"Poor (<40%):      {poor}/{total} ({poor/total*100:.1f}%)")
    print()

    print("By Predicted Regime:")
    print("-" * 70)
    for regime in sorted(results_df['predicted_regime'].unique()):
        regime_results = results_df[results_df['predicted_regime'] == regime]
        print(f"Regime {int(regime)}: {len(regime_results)} forecasts, "
              f"mean alignment: {regime_results['alignment'].mean()*100:.1f}%")
    print()

    # Interpretation
    print("="*70)
    print("INTERPRETATION")
    print("="*70)
    print()

    mean_alignment = results_df['alignment'].mean()

    if mean_alignment >= 0.8:
        print("✅ EXCELLENT: Forecasted regime characteristics strongly match historical patterns")
        print("   The predicted regimes are well-supported by historical evidence.")
    elif mean_alignment >= 0.6:
        print("✅ GOOD: Forecasted regime characteristics reasonably match historical patterns")
        print("   The predicted regimes are generally consistent with historical behavior.")
    elif mean_alignment >= 0.4:
        print("⚠️  MODERATE: Some divergence from historical regime patterns")
        print("   Predicted regimes show partial consistency with historical behavior.")
    else:
        print("❌ POOR: Forecasted regime characteristics significantly differ from historical patterns")
        print("   Predicted regimes may not be reliable based on historical evidence.")

    print()

    # Save detailed results
    output_dir = BASE_DIR / "outputs" / "inference"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save summary
    summary_path = output_dir / f"regime_validation_summary_{timestamp}.csv"
    results_df.to_csv(summary_path, index=False)
    print(f"📁 Summary saved to: {summary_path}")

    # Save detailed comparisons
    detailed_results = []
    for r in results:
        for fc in r['feature_comparisons']:
            detailed_results.append({
                'date': r['date'],
                'predicted_regime': r['predicted_regime'],
                'confidence': r['confidence'],
                'feature': fc['feature'],
                'forecast_value': fc['forecast_value'],
                'historical_mean': fc['historical_mean'],
                'historical_std': fc['historical_std'],
                'z_score': fc['z_score'],
                'alignment': fc['alignment']
            })

    if detailed_results:
        detailed_df = pd.DataFrame(detailed_results)
        detailed_path = output_dir / f"regime_validation_detailed_{timestamp}.csv"
        detailed_df.to_csv(detailed_path, index=False)
        print(f"📁 Detailed comparison saved to: {detailed_path}")

    print()


def main():
    print("\n" + "="*70)
    print("REGIME FORECAST VALIDATION AGAINST HISTORICAL EVIDENCE")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Load historical regime data
    historical_df = load_historical_regime_data()

    # Step 2: Compute historical regime statistics
    regime_stats, available_features = compute_regime_statistics(historical_df)

    # Step 3: Load forecast regime data
    regime_forecast_df, forecast_features_df = load_forecast_regime_data()

    if regime_forecast_df is None:
        print("\n❌ Validation failed: No forecast data available")
        return

    # Step 4: Compare forecasts against historical statistics
    results = compare_forecast_vs_historical_regimes(
        regime_forecast_df,
        forecast_features_df,
        regime_stats,
        available_features
    )

    # Step 5: Generate validation summary
    if results:
        generate_validation_summary(results, regime_stats)
    else:
        print("\n❌ Validation failed: No results generated")

    print("="*70)
    print("VALIDATION COMPLETE")
    print("="*70)
    print()


if __name__ == "__main__":
    main()
