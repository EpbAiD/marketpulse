"""
Active reallocator backtest — what the system is actually for.

This is the right test for MarketPulse. Earlier backtests measured long-
horizon Sharpe vs SPY (wrong: this is for active reallocators, not buy-and-
hold) or 21-day directional accuracy (wrong: the user wants per-day
environment, not a single label per 21 days).

Use case: a tactical allocator who reallocates capital DAILY across SPY/
QQQ/TLT based on each day's regime forecast. The forecast tells them
whether to be aggressive (Bull → 70% equity), neutral (Transitional →
40/40 balanced), or defensive (Bear → 70% bonds), with smooth gradations
in between.

The right test:

  For each historical day t in the OOS walk-forward window:
    1. The model classifies day t into a regime, using only data
       available BEFORE day t (walk-forward HMM trained yearly)
    2. Allocator looks up the regime → allocation table
    3. Portfolio earns next-day return based on that allocation
    4. Repeat daily for 12.3 years (2014-2026)

Compare:
  - HMM regime allocation (the system being tested)
  - 60/40 static (the boring baseline; what most allocators default to)
  - 200dMA-driven flip (50/50 above 200dMA, 20/80 below — single-indicator alternative)
  - Buy-and-hold SPY

For each strategy, report:
  - Annualized return + volatility + Sharpe
  - Max drawdown + worst 21-day drawdown (the active allocator cares about
    short-period losses, not just the all-time worst)
  - Distribution of daily returns (does the strategy avoid bad days?)
  - PER-REGIME stats: when system says X, what was the actual realized
    return distribution that day? Does Caution truly underperform Bull?

Run from repo root:
    python scripts/diagnostics/active_reallocator_backtest.py

CAVEAT: For computational tractability, this uses SAME-DAY HMM
classification (walk-forward trained, but classifying t with t's features)
as a proxy for "the model's t-day forecast made at t-N". The full
production system additionally forecasts the indicators 10 days out and
classifies each forecasted day; that adds forecast error which would
modestly degrade these numbers. The result here is an UPPER BOUND on the
production system's edge.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

N_REGIMES = 5  # bumped to match production
HMM_MAX_ITER = 1000
HMM_RANDOM_STATE = 42
TRAIN_START = pd.Timestamp("2011-01-03")
WALK_START_YEAR = 2014
WALK_END_YEAR = 2026

# Allocations matching backtest_strategy.py production table.
# Spectrum: lowest drawdown → highest drawdown.
ALLOC = {
    "Bull Market":   {"SPY": 0.70, "QQQ": 0.20, "TLT": 0.00},  # +10% cash
    "Calm":          {"SPY": 0.65, "QQQ": 0.20, "TLT": 0.05},
    "Steady":        {"SPY": 0.55, "QQQ": 0.20, "TLT": 0.15},
    "Transitional":  {"SPY": 0.40, "QQQ": 0.20, "TLT": 0.40},
    "Caution":       {"SPY": 0.30, "QQQ": 0.15, "TLT": 0.55},
    "Stress":        {"SPY": 0.25, "QQQ": 0.10, "TLT": 0.65},
    "Bear Market":   {"SPY": 0.20, "QQQ": 0.10, "TLT": 0.70},
}

LABEL_SPECTRUM = {
    3: ["Bull Market", "Transitional", "Bear Market"],
    5: ["Bull Market", "Calm", "Transitional", "Caution", "Bear Market"],
}


def label_clusters_by_drawdown(states, state_index, raw_price, k):
    """Rank clusters by P(>5% close-to-close drop in next 21d), assign
    the spectrum: lowest drawdown rate → 'Bull Market', highest → 'Bear Market'.
    """
    s = pd.Series(states, index=state_index)
    px = raw_price.reindex(state_index).dropna()
    s = s.reindex(px.index).dropna()
    fwd_pct = (px.shift(-21) / px - 1) * 100
    had_dd = (fwd_pct < -5).astype(int)

    df = pd.concat([s.rename("regime"), had_dd.rename("dd")], axis=1).dropna()
    rates = df.groupby("regime")["dd"].mean().sort_values()
    sorted_ids = list(rates.index.astype(int))

    # Pad spectrum if k is unusual (drop intermediate names symmetrically)
    spectrum = LABEL_SPECTRUM.get(k)
    if spectrum is None or len(spectrum) != k:
        spectrum = ["Bull Market"] + ["Transitional"] * (k - 2) + ["Bear Market"]

    return {int(rid): spectrum[i] for i, rid in enumerate(sorted_ids)}


def walk_forward_hmm(ca, raw_price, k=N_REGIMES):
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
        hmm = GaussianHMM(n_components=k, covariance_type="full",
                          n_iter=HMM_MAX_ITER, random_state=HMM_RANDOM_STATE)
        hmm.fit(Xtr)
        train_states = hmm.predict(Xtr)
        label_map = label_clusters_by_drawdown(train_states, train.index, raw_price, k)
        test_states = hmm.predict(Xte)
        for date, st in zip(test.index, test_states):
            rows.append({"date": date, "label": label_map.get(int(st), "Transitional")})
    return pd.DataFrame(rows).set_index("date").sort_index()


def to_alloc_df(label_series):
    """Map a series of regime names → DataFrame of {SPY, QQQ, TLT} weights."""
    rows = label_series.map(ALLOC).apply(pd.Series).fillna(0)
    return rows


def strategy_returns(alloc_df, asset_rets):
    """Yesterday's allocation drives today's return — no intraday leakage."""
    a = alloc_df.shift(1).dropna(how="all")
    j = a.join(asset_rets, how="inner", rsuffix="_ret").dropna()
    weighted = (j[["SPY", "QQQ", "TLT"]].values *
                j[["SPY_ret", "QQQ_ret", "TLT_ret"]].values).sum(axis=1)
    return pd.Series(weighted, index=j.index, name="ret")


def metrics(ret, name):
    cum = (1 + ret).cumprod()
    n_years = len(ret) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1
    ann_vol = ret.std() * np.sqrt(252)
    sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
    max_dd = ((cum - cum.cummax()) / cum.cummax()).min()
    # Worst 21-day rolling drawdown — what an active allocator most fears
    rolling_21d = ret.rolling(21).sum()
    worst_21d = rolling_21d.min() * 100  # in %
    # Distribution of daily returns
    p_loss_2pct = (ret < -0.02).mean() * 100  # how often >2% daily loss
    return {
        "Strategy": name,
        "CAGR": f"{cagr*100:.2f}%",
        "Ann Vol": f"{ann_vol*100:.2f}%",
        "Sharpe": f"{sharpe:.3f}",
        "Max DD": f"{max_dd*100:.2f}%",
        "Worst 21d": f"{worst_21d:.2f}%",
        "Days >2% loss": f"{p_loss_2pct:.2f}%",
        "Final $1 →": f"${cum.iloc[-1]:.2f}",
    }


def main():
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()

    print("Fetching market data...")
    spy_close = yf.download("^GSPC", start="2010-01-01", end="2026-04-29",
                            progress=False, auto_adjust=True)["Close"].squeeze()
    spy_close.index = pd.to_datetime(spy_close.index).normalize()

    prices = yf.download(["SPY", "QQQ", "TLT"],
                         start="2010-12-01", end="2026-04-29",
                         progress=False, auto_adjust=True)["Close"]
    prices.index = pd.to_datetime(prices.index).normalize()
    rets = prices.pct_change().dropna()

    # --- Run walk-forward HMM with 5 regimes ---
    print(f"Running walk-forward HMM with k={N_REGIMES} regimes...")
    hmm_labels_5 = walk_forward_hmm(ca, spy_close, k=5)["label"]
    print(f"  {len(hmm_labels_5)} day-labels produced "
          f"({hmm_labels_5.index.min().date()} → {hmm_labels_5.index.max().date()})")
    print(f"  Distribution:\n{hmm_labels_5.value_counts().to_string()}\n")

    # --- Also test the 3-regime version for comparison (production current) ---
    print("Running walk-forward HMM with k=3 regimes (for comparison)...")
    hmm_labels_3 = walk_forward_hmm(ca, spy_close, k=3)["label"]
    print(f"  Distribution:\n{hmm_labels_3.value_counts().to_string()}\n")

    # --- Strategy 1: HMM 5-regime allocation ---
    hmm5_ret = strategy_returns(to_alloc_df(hmm_labels_5), rets)

    # --- Strategy 2: HMM 3-regime allocation ---
    hmm3_ret = strategy_returns(to_alloc_df(hmm_labels_3), rets)

    # --- Strategy 3: 60/40 static (the boring baseline) ---
    static_60_40 = pd.DataFrame({
        "SPY": 0.60, "QQQ": 0.00, "TLT": 0.40,
    }, index=rets.index)
    static_ret = strategy_returns(static_60_40, rets)

    # --- Strategy 4: 200dMA flip (single-indicator alternative) ---
    ma200 = spy_close.rolling(200).mean()
    above_ma = (spy_close > ma200).reindex(rets.index, method="ffill").fillna(True)
    ma200_alloc = pd.DataFrame(index=rets.index, columns=["SPY", "QQQ", "TLT"], dtype=float)
    ma200_alloc[above_ma] = [0.50, 0.20, 0.30]   # above MA → equity-tilted
    ma200_alloc[~above_ma] = [0.20, 0.10, 0.70]  # below MA → bond-tilted
    ma200_ret = strategy_returns(ma200_alloc, rets)

    # --- Strategy 5: Buy-and-hold SPY ---
    bh_ret = rets["SPY"]

    # Align all to common window
    common = hmm5_ret.index
    for s in [hmm3_ret, static_ret, ma200_ret, bh_ret]:
        common = common.intersection(s.index)
    print(f"Common evaluation window: {common.min().date()} → {common.max().date()}, "
          f"{len(common)} days, {len(common)/252:.1f} years\n")

    print("=" * 110)
    print(" ACTIVE-REALLOCATOR BACKTEST RESULTS")
    print("=" * 110)
    print(" The user reallocates DAILY across SPY/QQQ/TLT based on each day's regime.")
    print(" 'Worst 21d' = worst rolling 21-day drawdown (active allocator's main pain point).")
    print(" 'Days >2% loss' = how often the strategy lost more than 2% in a single day.\n")
    res = pd.DataFrame([
        metrics(hmm5_ret.loc[common], "HMM 5-regime (production target)"),
        metrics(hmm3_ret.loc[common], "HMM 3-regime (production current)"),
        metrics(ma200_ret.loc[common], "200dMA flip"),
        metrics(static_ret.loc[common], "60/40 static"),
        metrics(bh_ret.loc[common], "Buy-and-hold SPY"),
    ])
    print(res.to_string(index=False))
    print()

    # =========================================================================
    # PER-REGIME conditional return analysis
    # =========================================================================
    print("=" * 110)
    print(" PER-REGIME CONDITIONAL RETURNS (5-regime model)")
    print("=" * 110)
    print(" When the system says X, what does today's actual SPY return look like?")
    print(" If the spectrum makes sense, mean returns should grade Bull > Calm > ... > Bear.\n")
    spy_daily = rets["SPY"]
    df = pd.concat([hmm_labels_5.rename("label"), spy_daily.rename("ret")], axis=1).dropna()
    grouped = df.groupby("label")["ret"].agg(["count", "mean", "std", "min", "max"])
    grouped["mean_pct"] = grouped["mean"] * 100
    grouped["std_pct"] = grouped["std"] * 100
    grouped["min_pct"] = grouped["min"] * 100
    grouped["max_pct"] = grouped["max"] * 100
    grouped["p_loss_2pct"] = (df.groupby("label")["ret"].apply(lambda x: (x < -0.02).mean() * 100))
    # Order rows by spectrum (bull → bear)
    spectrum = LABEL_SPECTRUM.get(5, [])
    ordered = [s for s in spectrum if s in grouped.index]
    print(grouped.loc[ordered, ["count", "mean_pct", "std_pct", "min_pct", "max_pct", "p_loss_2pct"]].round(3).to_string())
    print()

    # =========================================================================
    # FORWARD signal — what about NEXT day's return?
    # =========================================================================
    print("=" * 110)
    print(" PER-REGIME NEXT-DAY RETURN (does the regime predict tomorrow?)")
    print("=" * 110)
    df["next_ret"] = df["ret"].shift(-1)
    grouped_fwd = df.dropna().groupby("label")["next_ret"].agg(["count", "mean", "std"])
    grouped_fwd["mean_pct"] = grouped_fwd["mean"] * 100
    grouped_fwd["std_pct"] = grouped_fwd["std"] * 100
    print(grouped_fwd.loc[ordered, ["count", "mean_pct", "std_pct"]].round(3).to_string())
    print()
    print("Interpretation:")
    print("  - If Bull regime's NEXT-DAY mean return is meaningfully positive and Bear's")
    print("    is negative or near zero, the regime IS forecasting near-term direction.")
    print("  - If all regimes have similar next-day returns, the regime describes the")
    print("    CURRENT environment but doesn't forecast what's coming.")


if __name__ == "__main__":
    main()
