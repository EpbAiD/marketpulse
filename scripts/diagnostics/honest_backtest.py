"""
Honest backtest: HMM regime allocation vs VIX-threshold rule vs buy-and-hold.

Caveat: HMM regimes here come from cluster_assignments.parquet which was fit
on the entire 2011-2025 history (in-sample / look-ahead bias). The HMM thus
has an unfair advantage. If it STILL doesn't beat a simple VIX threshold rule
that's available point-in-time, the multivariate machinery isn't adding value.

Run from the repo root:
    python -m scripts.diagnostics.honest_backtest
or directly:
    python scripts/diagnostics/honest_backtest.py
"""
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

# 1. Load HMM regime assignments (in-sample, 2011-2025)
ca = pd.read_parquet(CA_PATH)
ca.index = pd.to_datetime(ca.index).normalize()
ca = ca[['regime', 'VIX_value']].sort_index()

print(f"HMM regimes: {len(ca)} days, {ca.index.min().date()} → {ca.index.max().date()}")

# 2. Load raw VIX (we need it daily for the threshold rule even outside HMM-aligned dates)
vix = yf.download('^VIX', start='2010-01-01', end='2026-04-29', progress=False, auto_adjust=True)['Close'].squeeze()
vix.index = pd.to_datetime(vix.index).normalize()

# 3. Pull asset prices
print("Fetching SPY, QQQ, TLT...")
prices = yf.download(['SPY', 'QQQ', 'TLT'],
                     start='2010-12-01', end='2026-04-29',
                     progress=False, auto_adjust=True)['Close']
prices.index = pd.to_datetime(prices.index).normalize()

# Daily simple returns
rets = prices.pct_change().dropna()
print(f"Asset returns: {len(rets)} days")

# 4. Define allocations
# HMM regime → portfolio (matching backtest_strategy.py current allocations
# AND the corrected label_map: regime 0=Bull, 1=Bear, 2=Transitional)
hmm_allocations = {
    0: {'SPY': 0.70, 'QQQ': 0.20, 'TLT': 0.00},  # Bull: equity-heavy, 10% cash
    1: {'SPY': 0.20, 'QQQ': 0.10, 'TLT': 0.70},  # Bear: bonds-heavy
    2: {'SPY': 0.40, 'QQQ': 0.20, 'TLT': 0.40},  # Transitional: balanced
}

# VIX threshold rule (no model, just numbers)
def vix_to_alloc(v):
    if v < 17:
        return {'SPY': 0.70, 'QQQ': 0.20, 'TLT': 0.00}  # calm → Bull
    elif v > 25:
        return {'SPY': 0.20, 'QQQ': 0.10, 'TLT': 0.70}  # fear → Bear
    else:
        return {'SPY': 0.40, 'QQQ': 0.20, 'TLT': 0.40}  # middle → Transitional


# 5. Compute strategy returns day-by-day
# We hold yesterday's regime for today's return (avoid trivial look-ahead within the strategy)
def portfolio_returns(daily_alloc, asset_rets):
    """daily_alloc: DataFrame indexed by date, columns SPY/QQQ/TLT (weights summing ≤ 1)
       Cash gets weight = 1 - sum, returns 0."""
    # Shift allocations by 1 day so we use yesterday's regime to allocate today
    shifted = daily_alloc.shift(1).dropna(how='all')
    aligned = shifted.join(asset_rets, how='inner', rsuffix='_ret')
    aligned = aligned.dropna()
    weighted = (aligned[['SPY', 'QQQ', 'TLT']].values *
                aligned[['SPY_ret', 'QQQ_ret', 'TLT_ret']].values).sum(axis=1)
    return pd.Series(weighted, index=aligned.index, name='daily_ret')


# Build allocation DataFrames
hmm_alloc_rows = []
for date, row in ca.iterrows():
    alloc = hmm_allocations[int(row['regime'])]
    hmm_alloc_rows.append({'date': date, **alloc})
hmm_alloc_df = pd.DataFrame(hmm_alloc_rows).set_index('date').sort_index()

vix_alloc_rows = []
for date, v in vix.dropna().items():
    if v is None or pd.isna(v):
        continue
    alloc = vix_to_alloc(float(v))
    vix_alloc_rows.append({'date': date, **alloc})
vix_alloc_df = pd.DataFrame(vix_alloc_rows).set_index('date').sort_index()

# Restrict to a common period: 2011-01-04 (HMM start +1) → 2026-04-22
common_start = max(hmm_alloc_df.index.min(), vix_alloc_df.index.min(), rets.index.min())
common_end = min(hmm_alloc_df.index.max(), vix_alloc_df.index.max(), rets.index.max())
print(f"Common backtest period: {common_start.date()} → {common_end.date()}")

hmm_alloc_df = hmm_alloc_df.loc[common_start:common_end]
vix_alloc_df = vix_alloc_df.loc[common_start:common_end]
rets_window = rets.loc[common_start:common_end]

hmm_ret = portfolio_returns(hmm_alloc_df, rets_window)
vix_ret = portfolio_returns(vix_alloc_df, rets_window)
bh_ret = rets_window['SPY']  # 100% SPY buy-and-hold

# Align to the intersection of all three
common_idx = hmm_ret.index.intersection(vix_ret.index).intersection(bh_ret.index)
hmm_ret = hmm_ret.loc[common_idx]
vix_ret = vix_ret.loc[common_idx]
bh_ret = bh_ret.loc[common_idx]

print(f"\nAll three strategies aligned: {len(common_idx)} trading days")
print(f"  Years: {len(common_idx) / 252:.1f}\n")


# 6. Metrics
def metrics(ret_series, name):
    cum = (1 + ret_series).cumprod()
    n_years = len(ret_series) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1
    ann_vol = ret_series.std() * np.sqrt(252)
    sharpe = ret_series.mean() / ret_series.std() * np.sqrt(252) if ret_series.std() > 0 else 0
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    max_dd = drawdown.min()
    final = cum.iloc[-1]
    return {
        'Strategy': name,
        'CAGR': f'{cagr*100:.2f}%',
        'Ann Vol': f'{ann_vol*100:.2f}%',
        'Sharpe': f'{sharpe:.3f}',
        'Max DD': f'{max_dd*100:.2f}%',
        'Final $1 →': f'${final:.2f}',
        'Total Return': f'{(final-1)*100:.1f}%',
    }


print("=" * 100)
print(" BACKTEST RESULTS")
print("=" * 100)

results = pd.DataFrame([
    metrics(hmm_ret, 'HMM Regimes (in-sample)'),
    metrics(vix_ret, 'VIX Threshold Rule'),
    metrics(bh_ret, 'Buy-and-Hold SPY'),
])
print(results.to_string(index=False))

print()
print("=" * 100)
print(" ALLOCATION AGREEMENT")
print("=" * 100)

# How often do HMM and VIX-threshold pick the same allocation?
def alloc_to_label(spy_w):
    if spy_w >= 0.65: return 'Bull'
    if spy_w <= 0.25: return 'Bear'
    return 'Transitional'

hmm_lbl = hmm_alloc_df['SPY'].apply(alloc_to_label).reindex(common_idx).dropna()
vix_lbl = vix_alloc_df['SPY'].apply(alloc_to_label).reindex(common_idx).dropna()
both = pd.concat([hmm_lbl.rename('HMM'), vix_lbl.rename('VIX')], axis=1).dropna()
agree = (both['HMM'] == both['VIX']).mean()
print(f"HMM and VIX-threshold agree on regime: {agree*100:.1f}% of days")
print()
print("Confusion (rows=HMM, cols=VIX):")
print(pd.crosstab(both['HMM'], both['VIX'], margins=True))
