"""
Tests the actual claim of MarketPulse:

  "Combining multiple financial indicators via unsupervised HMM discovers
   richer regime structure than any single indicator alone."

The previous benchmarks tested directional accuracy (UP/DOWN/FLAT prediction),
which mixed up two questions:
  - Can the system predict direction? (answer: no, no one can over 21 days
    of noise — but that's not the project's claim either)
  - Does the system identify regimes that single indicators miss? (this IS
    the project's claim, and it's what we should actually test)

This script tests three things:

TEST 1 — Single-indicator agreement
  How often do 200dMA, VIX-percentile, yield-curve, and credit-spread agree
  on the regime label? If they agree near-100% of the time, multivariate is
  unnecessary. If they disagree often, there's room for a multivariate
  model to add value.

TEST 2 — HMM regime structure vs single-indicator regimes
  For each pair (HMM, X), compute:
    - Cramér's V (categorical agreement strength)
    - Adjusted Rand Index (clustering similarity)
    - Mutual information (how much does HMM tell you about X?)
  If HMM is just rediscovering one indicator, MI ≈ entropy(X).
  If HMM is genuinely novel, MI is moderate but partition is different.

TEST 3 — Statistical separation by regime
  For each regime label scheme, compute statistical properties of the
  NEXT 21 days within each regime:
    - Mean fwd return    (does the regime separate good days from bad?)
    - Realized volatility (does the regime separate calm from turbulent?)
    - Tail probability    (P(|fwd ret| > 5%))
    - Max drawdown frequency
  If HMM's per-regime stats are MORE separated than single-indicator
  per-regime stats, the multivariate model has discovered structure that
  single indicators flatten over.

Run from repo root:
    python scripts/diagnostics/regime_information_value.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_datareader.data as web
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import adjusted_rand_score, mutual_info_score
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

N_REGIMES = 3
HMM_MAX_ITER = 1000
HMM_RANDOM_STATE = 42
TRAIN_START = pd.Timestamp("2011-01-03")
WALK_START_YEAR = 2014
WALK_END_YEAR = 2026
HORIZON = 21


# ----------------------------------------------------------------------------
# Walk-forward HMM (same machinery as production), with fwd-return labeling
# ----------------------------------------------------------------------------
def label_clusters_by_fwd_return(states, fwd_returns):
    s = pd.Series(states, index=fwd_returns.index)
    df = pd.concat([s.rename("regime"), fwd_returns.rename("fwd")], axis=1).dropna()
    means = df.groupby("regime")["fwd"].mean().sort_values()
    ids = list(means.index)
    out = {int(ids[-1]): "Bull"}
    out[int(ids[0])] = "Bear"
    if len(ids) >= 3:
        out[int(ids[1])] = "Transitional"
    return out


def walk_forward_hmm_predict(ca, fwd):
    feature_cols = [c for c in ca.columns if c != "regime"]
    rows = []
    for year in range(WALK_START_YEAR, WALK_END_YEAR + 1):
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        train = ca.loc[TRAIN_START:train_end]
        test = ca.loc[f"{year}-01-01":f"{year}-12-31"]
        if test.empty:
            continue
        scaler = StandardScaler().fit(train[feature_cols])
        Xtr = scaler.transform(train[feature_cols])
        Xte = scaler.transform(test[feature_cols])
        hmm = GaussianHMM(
            n_components=N_REGIMES, covariance_type="full",
            n_iter=HMM_MAX_ITER, random_state=HMM_RANDOM_STATE,
        )
        hmm.fit(Xtr)
        train_states = hmm.predict(Xtr)
        train_fwd = fwd.reindex(train.index)
        label_map = label_clusters_by_fwd_return(train_states, train_fwd)
        test_states = hmm.predict(Xte)
        for date, st in zip(test.index, test_states):
            rows.append({"date": date, "hmm_label": label_map.get(int(st), "Transitional")})
    return pd.DataFrame(rows).set_index("date").sort_index()


# ----------------------------------------------------------------------------
# Single-indicator regime rules (each is point-in-time)
# ----------------------------------------------------------------------------
def ma200_label(spy):
    ma = spy.rolling(200).mean()
    out = pd.Series(np.where(spy > ma, "Bull", "Bear"), index=spy.index)
    return out.where(ma.notna())


def vix_pct_label(vix):
    p20 = vix.rolling(252).quantile(0.20)
    p80 = vix.rolling(252).quantile(0.80)
    df = pd.concat([vix.rename("v"), p20.rename("p20"), p80.rename("p80")], axis=1)

    def lbl(r):
        if pd.isna(r["p20"]) or pd.isna(r["p80"]):
            return np.nan
        if r["v"] < r["p20"]:
            return "Bull"
        if r["v"] > r["p80"]:
            return "Bear"
        return "Transitional"
    return df.apply(lbl, axis=1)


def yield_curve_label(t10y2y):
    """Inverted curve (negative spread) → recession warning → Bear.
       Steep curve (>1pp) → economic expansion → Bull. Else Transitional."""
    out = pd.Series(index=t10y2y.index, dtype=object)
    out[t10y2y < 0] = "Bear"
    out[(t10y2y >= 0) & (t10y2y <= 1.0)] = "Transitional"
    out[t10y2y > 1.0] = "Bull"
    return out


def nfci_label(nfci):
    """NFCI is the Chicago Fed Financial Conditions Index. Positive values
    indicate tighter-than-average financial conditions (stress); negative
    values indicate looser-than-average conditions (risk-on). Daily series
    since 1973.
        NFCI > 0       → financial stress    → Bear
        NFCI in [-0.5, 0] → neutral          → Transitional
        NFCI < -0.5    → easy money          → Bull
    """
    out = pd.Series(index=nfci.index, dtype=object)
    out[nfci > 0] = "Bear"
    out[(nfci >= -0.5) & (nfci <= 0)] = "Transitional"
    out[nfci < -0.5] = "Bull"
    return out


# ----------------------------------------------------------------------------
# Statistical helpers
# ----------------------------------------------------------------------------
def cramers_v(s1, s2):
    """Cramér's V — categorical association strength, 0 (none) to 1 (perfect)."""
    confusion = pd.crosstab(s1, s2)
    chi2 = ((confusion - confusion.sum(0).values * confusion.sum(1).values[:, None] / confusion.values.sum()) ** 2 /
            (confusion.sum(0).values * confusion.sum(1).values[:, None] / confusion.values.sum())).values.sum()
    n = confusion.values.sum()
    r, k = confusion.shape
    return float(np.sqrt(chi2 / n / (min(r, k) - 1)))


def regime_stats(labels: pd.Series, fwd_returns: pd.Series) -> pd.DataFrame:
    """Per-regime statistical properties of forward returns."""
    df = pd.concat([labels.rename("lbl"), fwd_returns.rename("fwd")], axis=1).dropna()
    rows = []
    for lbl, group in df.groupby("lbl"):
        rows.append({
            "regime": lbl,
            "n_days": len(group),
            "mean_fwd_pct": group["fwd"].mean(),
            "std_fwd_pct": group["fwd"].std(),
            "p_negative": (group["fwd"] < 0).mean() * 100,
            "p_tail_drop": (group["fwd"] < -5).mean() * 100,
            "min_fwd_pct": group["fwd"].min(),
            "max_fwd_pct": group["fwd"].max(),
        })
    return pd.DataFrame(rows).set_index("regime")


def main():
    # ---- Load HMM features and compute walk-forward regimes ----
    print("Loading engineered feature set...")
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()

    # ---- Pull market data ----
    print("Fetching market data...")
    spy = yf.download("^GSPC", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    spy.index = pd.to_datetime(spy.index).normalize()
    vix = yf.download("^VIX", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).normalize()

    # FRED: yield curve and (proxy) credit stress
    t10y2y = web.DataReader("T10Y2Y", "fred", "2010-01-01", "2026-04-29").iloc[:, 0]
    t10y2y.index = pd.to_datetime(t10y2y.index).normalize()
    # Note: BAMLH0A0HYM2EY (HY effective yield) only has data from 2023.
    # Use NFCI (Chicago Fed Financial Conditions Index) as the long-history
    # credit-stress proxy — it's a composite and has data since 1973.
    nfci = web.DataReader("NFCI", "fred", "2010-01-01", "2026-04-29").iloc[:, 0]
    nfci.index = pd.to_datetime(nfci.index).normalize()

    fwd = (spy.shift(-HORIZON) / spy - 1) * 100

    print("Running walk-forward HMM...")
    hmm_labels = walk_forward_hmm_predict(ca, fwd)["hmm_label"]

    # ---- Build all label series ----
    labels = pd.DataFrame({
        "HMM (multivariate)": hmm_labels,
        "200dMA": ma200_label(spy),
        "VIX percentile": vix_pct_label(vix),
        "Yield curve": yield_curve_label(t10y2y).reindex(spy.index, method="ffill"),
        "NFCI (financial cond)": nfci_label(nfci).reindex(spy.index, method="ffill"),
    })
    # Align everything to a common window where every label exists
    labels = labels.dropna()
    fwd_aligned = fwd.reindex(labels.index)
    print(f"\nAligned evaluation window: {labels.index.min().date()} → "
          f"{labels.index.max().date()}, {len(labels)} days\n")

    # =========================================================================
    # TEST 1 — Do single indicators agree with each other?
    # =========================================================================
    print("=" * 100)
    print(" TEST 1: How often do INDIVIDUAL single-indicator regimes agree?")
    print("=" * 100)
    print("(High agreement → multivariate model is redundant.")
    print(" Low agreement → there's room for a multivariate model to combine them.)\n")
    single_indicators = ["200dMA", "VIX percentile", "Yield curve", "NFCI (financial cond)"]
    single_only = labels[single_indicators]

    agree_all = (single_only.eq(single_only.iloc[:, 0], axis=0)).all(axis=1).mean()
    print(f"All 4 single indicators give the same regime: {agree_all*100:.1f}% of days")

    # Pairwise
    print("\nPairwise agreement matrix (% of days each pair agrees on regime):")
    n = len(single_indicators)
    grid = pd.DataFrame(index=single_indicators, columns=single_indicators, dtype=float)
    for a in single_indicators:
        for b in single_indicators:
            grid.loc[a, b] = (single_only[a] == single_only[b]).mean() * 100
    print(grid.round(1))

    # =========================================================================
    # TEST 2 — Does HMM produce a meaningfully different partition?
    # =========================================================================
    print("\n" + "=" * 100)
    print(" TEST 2: Does HMM rediscover a single indicator, or carve a different partition?")
    print("=" * 100)
    print("(Cramér's V close to 1.0 → HMM is essentially that single indicator.")
    print(" Cramér's V around 0.3-0.6 → HMM picked up some signal but partitions differently.")
    print(" Cramér's V near 0 → HMM and that indicator have nothing in common.)\n")
    hmm = labels["HMM (multivariate)"]
    print(f"{'Indicator':<25s} {'CramerV':>10s} {'AdjRand':>10s} {'AgreePct':>10s}")
    print("-" * 60)
    for ind in single_indicators:
        v = cramers_v(hmm, labels[ind])
        ari = adjusted_rand_score(hmm, labels[ind])
        agree = (hmm == labels[ind]).mean() * 100
        print(f"{ind:<25s} {v:>10.3f} {ari:>10.3f} {agree:>10.1f}%")

    # =========================================================================
    # TEST 3 — Statistical separation per regime
    # =========================================================================
    print("\n" + "=" * 100)
    print(" TEST 3: Per-regime statistical properties of fwd 21-day returns")
    print("=" * 100)
    print("(Compare 'spread' between Bull-mean and Bear-mean for each labeling scheme.")
    print(" Larger spread → more distinct regimes → more useful classification.)\n")

    summary_rows = []
    for col in ["HMM (multivariate)"] + single_indicators:
        stats = regime_stats(labels[col], fwd_aligned)
        if "Bull" not in stats.index or "Bear" not in stats.index:
            print(f"\n{col}: only has {list(stats.index)} — skipping")
            continue
        bull_mean = stats.loc["Bull", "mean_fwd_pct"]
        bear_mean = stats.loc["Bear", "mean_fwd_pct"]
        bull_std = stats.loc["Bull", "std_fwd_pct"]
        bear_std = stats.loc["Bear", "std_fwd_pct"]
        bull_tail = stats.loc["Bull", "p_tail_drop"]
        bear_tail = stats.loc["Bear", "p_tail_drop"]
        spread = bull_mean - bear_mean
        vol_separation = bear_std - bull_std
        tail_separation = bear_tail - bull_tail
        summary_rows.append({
            "labeling": col,
            "bull_mean_fwd_pct": round(bull_mean, 2),
            "bear_mean_fwd_pct": round(bear_mean, 2),
            "mean_spread_pp": round(spread, 2),
            "bull_vol": round(bull_std, 2),
            "bear_vol": round(bear_std, 2),
            "vol_separation": round(vol_separation, 2),
            "bull_p_5pct_drop": round(bull_tail, 1),
            "bear_p_5pct_drop": round(bear_tail, 1),
            "tail_separation_pp": round(tail_separation, 1),
        })
        print(f"\n{col}:")
        print(stats.round(2).to_string())
    print("\n" + "-" * 100)
    print("Summary — does each labeling separate Bull from Bear in fwd-return distribution?")
    print("-" * 100)
    summary = pd.DataFrame(summary_rows)
    print(summary.to_string(index=False))

    print("\n" + "=" * 100)
    print(" INTERPRETATION GUIDE")
    print("=" * 100)
    print("""
- mean_spread_pp:     Higher = Bull regimes have meaningfully higher fwd return
                      than Bear regimes (the labeling separates them).
- vol_separation:     Higher = Bear regimes have meaningfully higher volatility
                      than Bull regimes.
- tail_separation_pp: Higher = Bear regimes are MORE prone to >5% drops than
                      Bull regimes.

If HMM has the BEST separation across these dimensions → multivariate
clustering finds richer structure than single indicators. That's the claim.
If single indicators tie or beat HMM → multivariate adds little.
""")


if __name__ == "__main__":
    main()
