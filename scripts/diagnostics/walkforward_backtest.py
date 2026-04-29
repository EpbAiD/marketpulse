"""
Walk-forward backtest: HMM regime allocation refit yearly (no look-ahead).

This is the rigorous test. The original honest_backtest used regime
assignments from a single HMM fit on the entire 2011-2025 history — every
day's regime label was informed by the future. That's look-ahead bias.

Here we instead do this:
  For each year Y from 2014 onward:
    1. Train an HMM on 2011-01-01 through year (Y-1) end
    2. Predict regimes for year Y (truly out-of-sample)
    3. Allocate using regime → portfolio table for that year
  Concatenate year-by-year predictions and compute strategy returns.

Cluster labels (Bull/Bear/Transitional) are derived per retrain by the
mean-VIX-per-cluster rule — same logic as production, so a regime-ID
permutation between years doesn't break the strategy.

If walk-forward HMM ≥ buy-and-hold Sharpe, the multivariate machinery is
adding real out-of-sample value. If it drops to ~SPY's Sharpe, the model
is essentially indistinguishable from passive holding once look-ahead is
removed.

Run from repo root:
    python -m scripts.diagnostics.walkforward_backtest
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

# ---- Config ----
N_REGIMES = 3
HMM_MAX_ITER = 1000
HMM_RANDOM_STATE = 42
TRAIN_START = pd.Timestamp("2011-01-03")
WALK_START_YEAR = 2014  # first year we predict out-of-sample
WALK_END_YEAR = 2026  # last year (incl. partial)


# ---- Allocations (same as honest_backtest.py) ----
ALLOC = {
    "Bull":         {"SPY": 0.70, "QQQ": 0.20, "TLT": 0.00},  # +10% cash
    "Bear":         {"SPY": 0.20, "QQQ": 0.10, "TLT": 0.70},
    "Transitional": {"SPY": 0.40, "QQQ": 0.20, "TLT": 0.40},
}


def label_clusters_by_vix(states: np.ndarray, vix: pd.Series) -> dict:
    """Map numeric regime IDs → 'Bull'/'Bear'/'Transitional' using mean VIX.

    Lowest mean VIX → Bull, highest → Bear, middle → Transitional. Same
    rule as production (clustering_agent.clustering.derive_regime_label_map).
    """
    aligned = pd.Series(states, index=vix.index).rename("regime")
    df = pd.concat([aligned, vix.rename("vix")], axis=1).dropna()
    means = df.groupby("regime")["vix"].mean().sort_values()
    ids_sorted = list(means.index)
    label_map = {}
    label_map[int(ids_sorted[0])] = "Bull"
    label_map[int(ids_sorted[-1])] = "Bear"
    if len(ids_sorted) >= 3:
        label_map[int(ids_sorted[1])] = "Transitional"
    return label_map


def main():
    # ---- Load engineered feature set + raw VIX from existing cluster_assignments ----
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()

    feature_cols = [c for c in ca.columns if c != "regime"]
    print(f"Loaded {len(ca)} days, {len(feature_cols)} engineered features")
    print(f"Date range: {ca.index.min().date()} → {ca.index.max().date()}")

    # ---- Walk forward: refit HMM each year, predict next year out-of-sample ----
    walk_predictions = []  # list of (date, regime_label)

    for year in range(WALK_START_YEAR, WALK_END_YEAR + 1):
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = pd.Timestamp(f"{year}-12-31")

        train_window = ca.loc[TRAIN_START:train_end]
        test_window = ca.loc[test_start:test_end]
        if test_window.empty:
            continue

        X_train = train_window[feature_cols]
        X_test = test_window[feature_cols]

        # Standardize using training statistics only
        scaler = StandardScaler().fit(X_train)
        X_train_z = scaler.transform(X_train)
        X_test_z = scaler.transform(X_test)

        hmm = GaussianHMM(
            n_components=N_REGIMES,
            covariance_type="full",
            n_iter=HMM_MAX_ITER,
            random_state=HMM_RANDOM_STATE,
        )
        hmm.fit(X_train_z)

        # Label clusters using training-window VIX
        train_states = hmm.predict(X_train_z)
        train_vix = train_window["VIX_value"]
        label_map = label_clusters_by_vix(train_states, train_vix)

        # Predict on test window
        test_states = hmm.predict(X_test_z)
        for date, state in zip(test_window.index, test_states):
            walk_predictions.append({"date": date, "regime_label": label_map.get(int(state), "Transitional")})

        print(f"  {year}: train {len(X_train)}d → test {len(X_test)}d  | label_map={label_map}")

    walk_df = pd.DataFrame(walk_predictions).set_index("date").sort_index()
    print(f"\nWalk-forward predictions: {len(walk_df)} days, "
          f"{walk_df.index.min().date()} → {walk_df.index.max().date()}\n")

    # ---- Build allocation DataFrames for each strategy ----
    # 1. Walk-forward HMM
    walk_alloc = walk_df["regime_label"].map(ALLOC).apply(pd.Series)
    walk_alloc = walk_alloc.fillna(0)

    # 2. VIX threshold rule (already point-in-time, same logic as honest_backtest)
    vix = yf.download("^VIX", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).normalize()

    def vix_alloc(v):
        if v < 17:
            return ALLOC["Bull"]
        if v > 25:
            return ALLOC["Bear"]
        return ALLOC["Transitional"]

    vix_rows = pd.DataFrame([vix_alloc(float(v)) for v in vix], index=vix.index)
    vix_rows = vix_rows.fillna(0)

    # 3. Asset prices for return computation
    print("Fetching SPY, QQQ, TLT prices...")
    prices = yf.download(
        ["SPY", "QQQ", "TLT"], start="2010-12-01", end="2026-04-29",
        progress=False, auto_adjust=True,
    )["Close"]
    prices.index = pd.to_datetime(prices.index).normalize()
    rets = prices.pct_change().dropna()

    # ---- Compute strategy returns ----
    def strategy_returns(alloc_df: pd.DataFrame, asset_rets: pd.DataFrame) -> pd.Series:
        """Yesterday's allocation drives today's return (no intra-day look-ahead)."""
        a = alloc_df.shift(1).dropna(how="all")
        joined = a.join(asset_rets, how="inner", rsuffix="_ret").dropna()
        weighted = (
            joined[["SPY", "QQQ", "TLT"]].values *
            joined[["SPY_ret", "QQQ_ret", "TLT_ret"]].values
        ).sum(axis=1)
        return pd.Series(weighted, index=joined.index, name="ret")

    walk_ret = strategy_returns(walk_alloc, rets)
    vix_ret = strategy_returns(vix_rows, rets)
    bh_ret = rets["SPY"]

    # Restrict all three to walk_ret's window (the strict out-of-sample period)
    common = walk_ret.index.intersection(vix_ret.index).intersection(bh_ret.index)
    walk_ret = walk_ret.loc[common]
    vix_ret = vix_ret.loc[common]
    bh_ret = bh_ret.loc[common]
    print(f"Strict OOS evaluation window: {common.min().date()} → {common.max().date()}, "
          f"{len(common)} days, {len(common)/252:.1f} years\n")

    # ---- Metrics ----
    def metrics(ret: pd.Series, name: str) -> dict:
        cum = (1 + ret).cumprod()
        n_years = len(ret) / 252
        cagr = cum.iloc[-1] ** (1 / n_years) - 1
        ann_vol = ret.std() * np.sqrt(252)
        sharpe = ret.mean() / ret.std() * np.sqrt(252) if ret.std() > 0 else 0
        max_dd = ((cum - cum.cummax()) / cum.cummax()).min()
        return {
            "Strategy": name,
            "CAGR": f"{cagr*100:.2f}%",
            "Ann Vol": f"{ann_vol*100:.2f}%",
            "Sharpe": f"{sharpe:.3f}",
            "Max DD": f"{max_dd*100:.2f}%",
            "Final $1 →": f"${cum.iloc[-1]:.2f}",
            "Total Return": f"{(cum.iloc[-1]-1)*100:.1f}%",
        }

    print("=" * 100)
    print(" WALK-FORWARD BACKTEST RESULTS (out-of-sample, HMM refit yearly)")
    print("=" * 100)
    res = pd.DataFrame([
        metrics(walk_ret, "HMM Walk-Forward (OOS)"),
        metrics(vix_ret, "VIX Threshold Rule"),
        metrics(bh_ret, "Buy-and-Hold SPY"),
    ])
    print(res.to_string(index=False))
    print()

    # ---- Distribution of regime labels and crash-period detail ----
    print("=" * 100)
    print(" REGIME DISTRIBUTION (walk-forward, OOS)")
    print("=" * 100)
    print(walk_df["regime_label"].value_counts())
    print()

    # ---- Year-by-year breakdown ----
    print("=" * 100)
    print(" YEAR-BY-YEAR PERFORMANCE")
    print("=" * 100)
    yearly = pd.DataFrame({
        "HMM Walk-Forward": walk_ret.groupby(walk_ret.index.year).apply(
            lambda r: ((1 + r).cumprod().iloc[-1] - 1) * 100
        ),
        "VIX Rule": vix_ret.groupby(vix_ret.index.year).apply(
            lambda r: ((1 + r).cumprod().iloc[-1] - 1) * 100
        ),
        "SPY": bh_ret.groupby(bh_ret.index.year).apply(
            lambda r: ((1 + r).cumprod().iloc[-1] - 1) * 100
        ),
    }).round(2)
    yearly.columns = [f"{c} (%)" for c in yearly.columns]
    print(yearly.to_string())


if __name__ == "__main__":
    main()
