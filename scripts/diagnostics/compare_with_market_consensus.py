#!/usr/bin/env python3
"""
Compare Regime Forecasts with Market Consensus
Analyzes whether our regime predictions align with current market sentiment
and professional forecasts from financial institutions
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import sys

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


def load_our_regime_forecasts():
    """
    Load our most recent regime forecasts
    """
    print("\n" + "="*70)
    print("LOADING OUR REGIME FORECASTS")
    print("="*70)
    print()

    forecast_dir = BASE_DIR / "outputs" / "inference"
    regime_files = sorted(forecast_dir.glob("regime_forecast_*.csv"))

    if not regime_files:
        print("❌ No regime forecast files found")
        return None

    latest_file = regime_files[-1]
    regime_df = pd.read_csv(latest_file)
    regime_df['ds'] = pd.to_datetime(regime_df['ds'])

    print(f"✅ Loaded forecasts from: {latest_file.name}")
    print(f"   Forecast period: {regime_df['ds'].min().date()} to {regime_df['ds'].max().date()}")
    print(f"   Total days: {len(regime_df)}")
    print()

    # Load raw forecast values for context
    raw_files = sorted(forecast_dir.glob("raw_forecasts_*.parquet"))
    if raw_files:
        raw_df = pd.read_parquet(raw_files[-1])
        raw_df['ds'] = pd.to_datetime(raw_df['ds'])
        raw_pivot = raw_df.pivot(index='ds', columns='feature', values='forecast_value')
        regime_df = regime_df.merge(raw_pivot, on='ds', how='left')

    return regime_df


def interpret_our_regimes(regime_df):
    """
    Interpret what our regime predictions mean in market terms
    """
    print("\n" + "="*70)
    print("OUR REGIME INTERPRETATION")
    print("="*70)
    print()

    # Load historical regime characteristics
    cluster_path = BASE_DIR / "outputs" / "clustering" / "cluster_assignments.parquet"
    cluster_df = pd.read_parquet(cluster_path)

    if isinstance(cluster_df.index, pd.DatetimeIndex):
        cluster_df = cluster_df.reset_index()
        cluster_df.rename(columns={'index': 'ds'}, inplace=True)

    regime_counts = cluster_df['regime'].value_counts()
    total_days = len(cluster_df)

    print("Historical Regime Prevalence:")
    print("-" * 70)
    for regime in sorted(cluster_df['regime'].unique()):
        count = regime_counts.get(regime, 0)
        pct = (count / total_days) * 100
        print(f"  Regime {int(regime)}: {pct:.1f}% of historical days ({count}/{total_days})")
    print()

    # Characterize each regime based on historical data
    print("Regime Characteristics (from historical analysis):")
    print("-" * 70)

    # Load historical features with regimes
    raw_dir = BASE_DIR / "outputs" / "fetched" / "cleaned"

    # Load VIX for volatility proxy
    vix_df = pd.read_parquet(raw_dir / "VIX.parquet")
    if isinstance(vix_df.index, pd.DatetimeIndex):
        vix_df = vix_df.reset_index()
        vix_df.columns = ['ds', 'VIX']
    vix_df['ds'] = pd.to_datetime(vix_df['ds'])

    # Merge with regimes
    vix_regime = vix_df.merge(cluster_df[['ds', 'regime']], on='ds', how='inner')

    for regime in sorted(cluster_df['regime'].unique()):
        regime_data = vix_regime[vix_regime['regime'] == regime]
        avg_vix = regime_data['VIX'].mean()

        print(f"\nRegime {int(regime)}:")
        print(f"  Average VIX: {avg_vix:.2f}")

        if avg_vix < 15:
            market_condition = "Low Volatility / Calm Markets"
        elif avg_vix < 20:
            market_condition = "Moderate Volatility / Normal Markets"
        elif avg_vix < 30:
            market_condition = "Elevated Volatility / Uncertain Markets"
        else:
            market_condition = "High Volatility / Stressed Markets"

        print(f"  Market Condition: {market_condition}")

    print()

    # Summarize our forecast
    print("OUR CURRENT FORECAST:")
    print("-" * 70)

    forecast_regime_counts = regime_df['regime'].value_counts()
    print(f"Forecast period: {regime_df['ds'].min().date()} to {regime_df['ds'].max().date()}")
    print(f"Predicted regimes:")

    for regime in sorted(regime_df['regime'].unique()):
        count = forecast_regime_counts.get(regime, 0)
        pct = (count / len(regime_df)) * 100
        avg_conf = regime_df[regime_df['regime'] == regime]['regime_probability'].mean() * 100
        print(f"  Regime {int(regime)}: {count}/{len(regime_df)} days ({pct:.1f}%) - avg confidence: {avg_conf:.1f}%")

    # Get average forecasted values
    if 'VIX' in regime_df.columns:
        avg_vix_forecast = regime_df['VIX'].mean()
        print(f"\nForecasted average VIX: {avg_vix_forecast:.2f}")

        if avg_vix_forecast < 15:
            forecast_condition = "LOW VOLATILITY - Calm, stable markets expected"
        elif avg_vix_forecast < 20:
            forecast_condition = "MODERATE VOLATILITY - Normal market conditions expected"
        elif avg_vix_forecast < 30:
            forecast_condition = "ELEVATED VOLATILITY - Uncertain markets expected"
        else:
            forecast_condition = "HIGH VOLATILITY - Stressed markets expected"

        print(f"Market condition forecast: {forecast_condition}")

    print()


def compare_with_market_indicators(regime_df):
    """
    Compare our forecasts with current market indicators and sentiment
    """
    print("\n" + "="*70)
    print("COMPARISON WITH CURRENT MARKET INDICATORS")
    print("="*70)
    print()

    print("Current Market Context (as of December 2025):")
    print("-" * 70)

    # Analyze our forecasted values
    if 'VIX' in regime_df.columns:
        vix_forecast = regime_df['VIX'].mean()
        print(f"Our VIX Forecast: {vix_forecast:.2f}")

    if 'GSPC' in regime_df.columns:
        sp500_forecast = regime_df['GSPC'].mean()
        print(f"Our S&P 500 Forecast: {sp500_forecast:.2f}")

    if 'DGS10' in regime_df.columns and 'DGS2' in regime_df.columns:
        yield_curve = (regime_df['DGS10'] - regime_df['DGS2']).mean()
        print(f"Our Yield Curve Forecast (10Y-2Y): {yield_curve:.2f}%")

    print()

    # Market interpretation
    print("MARKET INTERPRETATION:")
    print("-" * 70)

    dominant_regime = regime_df['regime'].mode()[0]
    regime_pct = (regime_df['regime'] == dominant_regime).sum() / len(regime_df) * 100

    print(f"\nDominant Predicted Regime: Regime {int(dominant_regime)} ({regime_pct:.0f}% of forecast period)")
    print()

    if 'VIX' in regime_df.columns:
        vix_avg = regime_df['VIX'].mean()

        print("Our Market Outlook:")
        print("-" * 70)

        if vix_avg < 15 and dominant_regime == 2:
            outlook = """
BULLISH / LOW VOLATILITY REGIME
- Very low implied volatility (VIX < 15)
- Market complacency or strong confidence
- Typical of bull market conditions with low uncertainty
- Risk: Potential complacency before volatility spike
"""
        elif 15 <= vix_avg < 20 and dominant_regime == 0:
            outlook = """
NEUTRAL / MODERATE VOLATILITY REGIME
- Normal volatility levels (VIX 15-20)
- Balanced market conditions
- Typical of stable growth periods
- Moderate risk environment
"""
        elif 15 <= vix_avg < 20 and dominant_regime == 1:
            outlook = """
BULLISH / RECOVERY REGIME
- Moderate volatility but positive momentum
- Market showing resilience
- Typical of post-correction recovery phases
- Risk appetite returning to markets
"""
        elif vix_avg >= 20:
            outlook = """
CAUTIOUS / ELEVATED VOLATILITY REGIME
- Elevated uncertainty (VIX ≥ 20)
- Market stress or heightened risk perception
- Typical of uncertain economic/political environment
- Defensive positioning may be warranted
"""
        else:
            outlook = """
MIXED SIGNALS
- Market showing transitional characteristics
- Uncertainty about near-term direction
"""

        print(outlook)

    # Yield curve interpretation
    if 'DGS10' in regime_df.columns and 'DGS2' in regime_df.columns:
        yield_curve_avg = (regime_df['DGS10'] - regime_df['DGS2']).mean()

        print("\nYield Curve Signal:")
        print("-" * 70)

        if yield_curve_avg < -0.2:
            yc_signal = "DEEPLY INVERTED - Strong recession warning signal"
        elif -0.2 <= yield_curve_avg < 0:
            yc_signal = "INVERTED - Recession risk elevated"
        elif 0 <= yield_curve_avg < 0.3:
            yc_signal = "FLAT - Economic uncertainty"
        elif 0.3 <= yield_curve_avg < 0.6:
            yc_signal = "NORMAL - Healthy economic conditions"
        else:
            yc_signal = "STEEP - Strong growth expectations or Fed easing"

        print(f"10Y-2Y Spread: {yield_curve_avg:.2f}%")
        print(f"Signal: {yc_signal}")
        print()


def consensus_comparison_framework():
    """
    Provide framework for comparing with professional forecasts
    """
    print("\n" + "="*70)
    print("COMPARISON WITH PROFESSIONAL FORECASTS")
    print("="*70)
    print()

    print("Market Consensus Indicators to Check:")
    print("-" * 70)
    print("""
1. VIX LEVEL & FORECAST
   - Our forecast vs. current VIX futures curve
   - Compare with options market implied volatility

2. EQUITY MARKET SENTIMENT
   - S&P 500 price targets from major banks (Goldman, JPM, Morgan Stanley)
   - AAII Sentiment Survey (bullish/bearish %)
   - CNN Fear & Greed Index

3. VOLATILITY REGIME
   - Compare our regime with CBOE volatility classifications
   - Cross-reference with volatility-based hedge fund strategies

4. ECONOMIC INDICATORS
   - Fed dot plot vs. our interest rate forecasts
   - Bloomberg Economics consensus
   - Economic Policy Uncertainty Index

5. RISK SENTIMENT
   - MOVE Index (bond volatility) - compare with our fixed income signals
   - High Yield spreads vs. our HY_YIELD forecast
   - Put/Call ratio vs. our VIX forecast

6. INSTITUTIONAL POSITIONING
   - CFTC Commitment of Traders (speculator positioning)
   - BofA Global Fund Manager Survey
   - Deutsche Bank Risk Appetite Index
""")

    print("\nHow to Validate Our Predictions:")
    print("-" * 70)
    print("""
To determine if our predictions align with market consensus:

1. CHECK CURRENT VIX:
   - If VIX is currently 15-18 and we forecast similar → ALIGNED
   - If VIX is 25+ and we forecast 18 → CONTRARIAN (flag for review)

2. CHECK SELL-SIDE TARGETS:
   - Compare our S&P 500 forecast with average year-end targets
   - Look at dispersion - high dispersion = high uncertainty

3. CHECK SENTIMENT SURVEYS:
   - If we forecast Regime 1 (bullish), check if AAII bullish % > 40%
   - If we forecast Regime 2 (low vol), check if Fear & Greed > 60

4. CHECK VOLATILITY CURVE:
   - Look at VIX futures term structure
   - Contango = low vol expectations (aligns with Regime 2)
   - Backwardation = elevated vol expectations (aligns with Regime 0/1)

5. CHECK FED EXPECTATIONS:
   - Our rate forecasts vs. Fed Funds futures
   - Our yield curve forecast vs. economist consensus
""")

    print()


def generate_validation_report(regime_df):
    """
    Generate actionable validation report
    """
    print("\n" + "="*70)
    print("VALIDATION ACTION ITEMS")
    print("="*70)
    print()

    print("To verify our forecasts are aligned with market consensus:")
    print("-" * 70)
    print()

    # Specific checks based on our forecast
    dominant_regime = regime_df['regime'].mode()[0]

    if 'VIX' in regime_df.columns:
        vix_forecast = regime_df['VIX'].mean()

        print(f"1. VIX CHECK (Our forecast: {vix_forecast:.2f})")
        print(f"   → Visit: https://www.cboe.com/tradable_products/vix/")
        print(f"   → Check if current VIX is within ±3 points of {vix_forecast:.2f}")
        print(f"   → Check VIX futures curve for next 2 weeks")
        print()

    if 'GSPC' in regime_df.columns:
        sp500_forecast = regime_df['GSPC'].mean()

        print(f"2. S&P 500 CHECK (Our forecast: {sp500_forecast:.0f})")
        print(f"   → Search: 'S&P 500 price targets December 2025'")
        print(f"   → Compare with Goldman Sachs, JPMorgan, Morgan Stanley targets")
        print(f"   → Check if our forecast is within consensus range")
        print()

    print(f"3. SENTIMENT CHECK (Our regime: {int(dominant_regime)})")
    print(f"   → AAII Sentiment Survey: https://www.aaii.com/sentimentsurvey")
    print(f"   → CNN Fear & Greed Index: https://www.cnn.com/markets/fear-and-greed")

    if dominant_regime == 2:
        print(f"   → Expected: Fear & Greed Index > 60 (Greed)")
        print(f"   → Expected: AAII Bullish % > 40%")
    elif dominant_regime == 1:
        print(f"   → Expected: Fear & Greed Index 50-70 (Neutral-Greed)")
        print(f"   → Expected: AAII Bullish % 35-45%")
    else:
        print(f"   → Expected: Fear & Greed Index < 50 (Fear)")
        print(f"   → Expected: AAII Bullish % < 35%")
    print()

    if 'DGS10' in regime_df.columns and 'DGS2' in regime_df.columns:
        yield_curve = (regime_df['DGS10'] - regime_df['DGS2']).mean()

        print(f"4. YIELD CURVE CHECK (Our forecast: {yield_curve:.2f}%)")
        print(f"   → Visit: https://www.treasury.gov/resource-center/data-chart-center/interest-rates/")
        print(f"   → Compare 10Y-2Y spread with our forecast")
        print(f"   → Check Bloomberg Economics consensus for rate expectations")
        print()

    print("5. RISK APPETITE CHECK")
    print("   → Check High Yield (HY) spreads on FRED")
    print("   → Compare with our HY_YIELD forecast")
    print("   → Narrowing spreads = risk-on (aligns with Regime 1/2)")
    print("   → Widening spreads = risk-off (aligns with Regime 0)")
    print()

    # Save validation checklist
    output_dir = BASE_DIR / "outputs" / "inference"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    checklist_path = output_dir / f"market_consensus_checklist_{timestamp}.txt"

    with open(checklist_path, 'w') as f:
        f.write("="*70 + "\n")
        f.write("MARKET CONSENSUS VALIDATION CHECKLIST\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")

        f.write(f"Our Forecast Summary:\n")
        f.write(f"  Forecast Period: {regime_df['ds'].min().date()} to {regime_df['ds'].max().date()}\n")
        f.write(f"  Dominant Regime: Regime {int(dominant_regime)}\n")

        if 'VIX' in regime_df.columns:
            f.write(f"  Avg VIX Forecast: {regime_df['VIX'].mean():.2f}\n")
        if 'GSPC' in regime_df.columns:
            f.write(f"  Avg S&P 500 Forecast: {regime_df['GSPC'].mean():.0f}\n")

        f.write("\n" + "="*70 + "\n")
        f.write("VALIDATION CHECKLIST:\n")
        f.write("="*70 + "\n\n")
        f.write("[ ] Check current VIX level\n")
        f.write("[ ] Check S&P 500 analyst targets\n")
        f.write("[ ] Check AAII Sentiment Survey\n")
        f.write("[ ] Check CNN Fear & Greed Index\n")
        f.write("[ ] Check Treasury yield curve\n")
        f.write("[ ] Check High Yield spreads\n")
        f.write("[ ] Check VIX futures term structure\n")
        f.write("[ ] Check Fed Funds futures\n")
        f.write("[ ] Check sell-side research notes\n")
        f.write("[ ] Compare with Bloomberg consensus\n")

    print(f"📁 Validation checklist saved to: {checklist_path}")
    print()


def main():
    print("\n" + "="*70)
    print("MARKET CONSENSUS COMPARISON ANALYSIS")
    print("Do Our Regime Forecasts Align with Professional Market Views?")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load our forecasts
    regime_df = load_our_regime_forecasts()

    if regime_df is None:
        print("\n❌ Analysis failed: No forecast data available")
        return

    # Interpret our regimes
    interpret_our_regimes(regime_df)

    # Compare with market indicators
    compare_with_market_indicators(regime_df)

    # Provide consensus comparison framework
    consensus_comparison_framework()

    # Generate validation report
    generate_validation_report(regime_df)

    print("="*70)
    print("ANALYSIS COMPLETE")
    print("="*70)
    print()
    print("Next Steps:")
    print("  1. Review the validation checklist above")
    print("  2. Check each source to verify alignment")
    print("  3. Document any significant deviations")
    print("  4. Consider if deviations represent contrarian opportunities")
    print()


if __name__ == "__main__":
    main()
