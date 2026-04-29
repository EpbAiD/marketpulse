"""
Trend prediction: walk-forward HMM vs industry-standard regime indicators.

Two important changes from earlier tests:

1) HMM cluster labels are now derived from FORWARD-LOOKING returns within
   the training window only (no test-period look-ahead): the cluster with
   the highest mean fwd-21d return on training data → "Bull"; lowest → "Bear".
   This fixes the misleading VIX-mean labeling, which mistakenly labeled
   high-VIX panic-bottom clusters as "Bear" when their forward returns are
   actually positive.

2) We benchmark against widely-published regime indicators that any
   investor can look up — not against our own ad hoc rules:
     - 200-day moving average rule (textbook technical trend signal)
     - 21-day persistence (momentum carries forward)
     - VIX-percentile rule (Fear & Greed-style: VIX in top quintile of
       trailing year = "Bear / fear", bottom quintile = "Bull / greed")

Question: does the multivariate HMM beat these benchmarks at predicting
fwd 21-day direction (UP / DOWN / FLAT)?

Run from repo root:
    python scripts/diagnostics/trend_vs_industry.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

N_REGIMES = 3
HMM_MAX_ITER = 1000
HMM_RANDOM_STATE = 42
TRAIN_START = pd.Timestamp("2011-01-03")
WALK_START_YEAR = 2014
WALK_END_YEAR = 2026

HORIZON = 21       # forward window for "trend" — 1 month is the conventional horizon
FLAT_THRESHOLD_PCT = 1.0  # |fwd return| ≤ 1% over 21d → FLAT


def label_clusters_by_fwd_return(states: np.ndarray, fwd_returns: pd.Series) -> dict:
    """Train-window-only label assignment.

    Cluster with highest mean fwd-21d return → 'Bull'.
    Cluster with lowest mean fwd-21d return → 'Bear'.
    Middle → 'Transitional'.
    Uses ONLY training data outcomes — no test peek.
    """
    s = pd.Series(states, index=fwd_returns.index)
    df = pd.concat([s.rename("regime"), fwd_returns.rename("fwd")], axis=1).dropna()
    means = df.groupby("regime")["fwd"].mean().sort_values()
    ids = list(means.index)
    out = {int(ids[-1]): "Bull"}
    out[int(ids[0])] = "Bear"
    if len(ids) >= 3:
        out[int(ids[1])] = "Transitional"
    return out


def actual_direction(fwd_pct: float) -> str:
    if fwd_pct > FLAT_THRESHOLD_PCT:
        return "UP"
    if fwd_pct < -FLAT_THRESHOLD_PCT:
        return "DOWN"
    return "FLAT"


def expected_direction_from_label(label: str) -> str:
    if label in ("Bull", "UP"):
        return "UP"
    if label in ("Bear", "DOWN"):
        return "DOWN"
    return "FLAT"


def main():
    # ---- Load engineered features (already computed for the existing HMM) ----
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()
    feature_cols = [c for c in ca.columns if c != "regime"]
    print(f"Loaded {len(ca)} days, {len(feature_cols)} features")

    # ---- Pull SPY + VIX ----
    print("Fetching ^GSPC (S&P 500) and ^VIX...")
    spy = yf.download("^GSPC", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    spy.index = pd.to_datetime(spy.index).normalize()
    vix = yf.download("^VIX", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).normalize()

    fwd = (spy.shift(-HORIZON) / spy - 1) * 100
    fwd = fwd.rename("fwd_pct")

    # ---- Walk-forward HMM with forward-return-based labeling ----
    walk_predictions = []
    for year in range(WALK_START_YEAR, WALK_END_YEAR + 1):
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = pd.Timestamp(f"{year}-12-31")
        train = ca.loc[TRAIN_START:train_end]
        test = ca.loc[test_start:test_end]
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

        # Use ONLY training-window forward returns to label clusters.
        # The fwd return at date t requires data at t+21 — but t and t+21 are
        # BOTH inside the training window when we're labeling. There's no
        # test-period leakage.
        train_fwd = fwd.reindex(train.index)
        # For the last 21 days of training, fwd is NaN — that's fine (dropna in helper)
        label_map = label_clusters_by_fwd_return(train_states, train_fwd)

        test_states = hmm.predict(Xte)
        for date, s in zip(test.index, test_states):
            walk_predictions.append({
                "date": date,
                "hmm_label": label_map.get(int(s), "Transitional"),
            })
        print(f"  {year}: train {len(train)}d → test {len(test)}d  | label_map={label_map}")

    pred_df = pd.DataFrame(walk_predictions).set_index("date").sort_index()
    print(f"\nWalk-forward predictions: {len(pred_df)} days "
          f"({pred_df.index.min().date()} → {pred_df.index.max().date()})")

    # ---- Industry-standard benchmarks ----
    # 1. 200-day moving average rule (textbook trend rule)
    ma200 = spy.rolling(200).mean()
    ma200_label = pd.Series(
        np.where(spy > ma200, "Bull", "Bear"),
        index=spy.index, name="ma200_label",
    )

    # 2. 21-day persistence: trailing 21d return decides direction
    trail21 = (spy / spy.shift(21) - 1) * 100
    persist_label = trail21.apply(
        lambda r: "Bull" if r > FLAT_THRESHOLD_PCT
        else ("Bear" if r < -FLAT_THRESHOLD_PCT else "Transitional")
    ).rename("persist_label")

    # 3. VIX-percentile (Fear & Greed style):
    #    VIX > 80th percentile of trailing 252 days → "Bear" (fear)
    #    VIX < 20th percentile → "Bull" (greed/complacency)
    #    middle → Transitional
    vix_p20 = vix.rolling(252).quantile(0.20)
    vix_p80 = vix.rolling(252).quantile(0.80)

    def fg_label(row):
        v, p20, p80 = row["vix"], row["p20"], row["p80"]
        if pd.isna(p20) or pd.isna(p80):
            return np.nan
        if v < p20:
            return "Bull"
        if v > p80:
            return "Bear"
        return "Transitional"

    fg_df = pd.concat([vix.rename("vix"), vix_p20.rename("p20"), vix_p80.rename("p80")], axis=1)
    fg_label_series = fg_df.apply(fg_label, axis=1).rename("fg_label").dropna()

    # ---- Combine into a single eval frame ----
    df = pd.concat([pred_df["hmm_label"], ma200_label, persist_label,
                    fg_label_series, fwd], axis=1).dropna()
    df["actual"] = df["fwd_pct"].apply(actual_direction)

    print(f"\nEvaluation rows: {len(df)}  (after aligning all four predictors)")
    print(f"Window: {df.index.min().date()} → {df.index.max().date()}")

    # ---- Score each predictor ----
    print("\n" + "=" * 100)
    print(" DIRECTIONAL ACCURACY (predicted regime → actual fwd-21d direction match?)")
    print("=" * 100)

    for col, name in [
        ("hmm_label", "HMM Walk-Forward (fwd-return-labeled)"),
        ("ma200_label", "200-day Moving Average (textbook trend)"),
        ("persist_label", "21-day Persistence"),
        ("fg_label", "Fear & Greed (VIX percentile rule)"),
    ]:
        df["expected"] = df[col].apply(expected_direction_from_label)
        hit = (df["expected"] == df["actual"]).mean()
        always_mode = df["actual"].value_counts(normalize=True).max()
        print(f"\n{name}:")
        print(f"  Overall hit rate:  {hit*100:.1f}%   "
              f"(always-pick-mode baseline = {always_mode*100:.1f}%)")
        for label in ["Bull", "Bear", "Transitional"]:
            mask = df[col] == label
            n = mask.sum()
            if n == 0:
                continue
            mean_ret = df.loc[mask, "fwd_pct"].mean()
            up_pct = (df.loc[mask, "actual"] == "UP").mean() * 100
            down_pct = (df.loc[mask, "actual"] == "DOWN").mean() * 100
            print(f"    Predicted {label:12s} ({n:4d} days):  "
                  f"avg actual fwd 21d = {mean_ret:+.2f}%  | "
                  f"UP {up_pct:5.1f}%  DOWN {down_pct:5.1f}%")

    # ---- Specifically: when each says BEAR, does market actually fall? ----
    print("\n" + "=" * 100)
    print(" KEY QUESTION: When predictor says BEAR, what actually happens?")
    print("=" * 100)
    baseline_down = (df["actual"] == "DOWN").mean() * 100
    print(f"Baseline DOWN frequency on all days: {baseline_down:.1f}%\n")
    for col, name in [
        ("hmm_label", "HMM"),
        ("ma200_label", "200dMA"),
        ("persist_label", "Persistence"),
        ("fg_label", "Fear & Greed"),
    ]:
        bear = df[df[col] == "Bear"]
        if len(bear) == 0:
            print(f"{name}: never says Bear")
            continue
        n = len(bear)
        n_down = (bear["actual"] == "DOWN").sum()
        mean_ret = bear["fwd_pct"].mean()
        lift = n_down/n*100 - baseline_down
        print(f"{name:14s} ({n:4d} Bear): {n_down/n*100:5.1f}% DOWN  "
              f"(lift {lift:+.1f}pp)  | mean fwd ret {mean_ret:+.2f}%")

    print("\n" + "=" * 100)
    print(" KEY QUESTION: When predictor says BULL, does market actually rise?")
    print("=" * 100)
    baseline_up = (df["actual"] == "UP").mean() * 100
    print(f"Baseline UP frequency on all days: {baseline_up:.1f}%\n")
    for col, name in [
        ("hmm_label", "HMM"),
        ("ma200_label", "200dMA"),
        ("persist_label", "Persistence"),
        ("fg_label", "Fear & Greed"),
    ]:
        bull = df[df[col] == "Bull"]
        if len(bull) == 0:
            continue
        n = len(bull)
        n_up = (bull["actual"] == "UP").sum()
        mean_ret = bull["fwd_pct"].mean()
        lift = n_up/n*100 - baseline_up
        print(f"{name:14s} ({n:4d} Bull): {n_up/n*100:5.1f}% UP  "
              f"(lift {lift:+.1f}pp)  | mean fwd ret {mean_ret:+.2f}%")


if __name__ == "__main__":
    main()
