"""
Trend / direction prediction test.

The honest claim of MarketPulse is NOT "predict the exact value of S&P
in 10 days" (no one can). The claim is "predict the market regime /
trend direction." This script tests precisely that.

Test design:
  For each day t in the walk-forward OOS period (2014-2026):
    - The HMM (trained on data up to t-1) labels day t as Bull/Bear/Trans
    - We then compute the ACTUAL S&P 500 return over [t+1, t+11] (next
      10 trading days)
    - Score:
        Bull predicted   → expect positive 10d return  (UP)
        Bear predicted   → expect negative 10d return  (DOWN)
        Transitional     → expect small/sideways move  (FLAT)

We compare against three baselines:
  - Random (33% per class) — must beat this convincingly
  - Persistence (whatever happened the past 10d will keep happening) — naive but
    common benchmark
  - VIX threshold rule — does multivariate beat 1 feature?

Metrics reported:
  - Directional accuracy: did the predicted regime match the actual outcome?
  - Conditional mean return: average actual return when each regime is predicted
  - Hit rate on Bull and Bear specifically (the two actionable calls)

Run:
    python scripts/diagnostics/trend_accuracy_test.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

# Walk-forward config
N_REGIMES = 3
HMM_MAX_ITER = 1000
HMM_RANDOM_STATE = 42
TRAIN_START = pd.Timestamp("2011-01-03")
WALK_START_YEAR = 2014
WALK_END_YEAR = 2026
HORIZON = 10  # trading days

# What counts as "up" / "down" / "flat" for the actual outcome
# 10-day moves smaller than this threshold are called "flat"
FLAT_THRESHOLD_PCT = 0.5  # absolute % move


def label_clusters_by_vix(states: np.ndarray, vix: pd.Series) -> dict:
    """Bull = lowest VIX cluster; Bear = highest; middle = Transitional."""
    s = pd.Series(states, index=vix.index)
    df = pd.concat([s.rename("regime"), vix.rename("vix")], axis=1).dropna()
    means = df.groupby("regime")["vix"].mean().sort_values()
    ids = list(means.index)
    out = {int(ids[0]): "Bull", int(ids[-1]): "Bear"}
    if len(ids) >= 3:
        out[int(ids[1])] = "Transitional"
    return out


def actual_direction(forward_pct: float) -> str:
    if forward_pct > FLAT_THRESHOLD_PCT:
        return "UP"
    if forward_pct < -FLAT_THRESHOLD_PCT:
        return "DOWN"
    return "FLAT"


def expected_direction_from_regime(regime_label: str) -> str:
    if regime_label == "Bull":
        return "UP"
    if regime_label == "Bear":
        return "DOWN"
    return "FLAT"


def main():
    # ---- Load engineered features (already computed for the existing HMM) ----
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()
    feature_cols = [c for c in ca.columns if c != "regime"]
    print(f"Loaded {len(ca)} days, {len(feature_cols)} features")

    # ---- Walk-forward: refit HMM each year and predict OOS ----
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
        label_map = label_clusters_by_vix(train_states, train["VIX_value"])

        test_states = hmm.predict(Xte)
        for date, s in zip(test.index, test_states):
            walk_predictions.append({
                "date": date,
                "hmm_label": label_map.get(int(s), "Transitional"),
            })

    pred_df = pd.DataFrame(walk_predictions).set_index("date").sort_index()
    print(f"Walk-forward predictions: {len(pred_df)} days "
          f"({pred_df.index.min().date()} → {pred_df.index.max().date()})")

    # ---- Pull S&P 500 (raw) and compute forward 10-day returns ----
    spy = yf.download("^GSPC", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    spy.index = pd.to_datetime(spy.index).normalize()
    fwd = (spy.shift(-HORIZON) / spy - 1) * 100  # forward 10d % return
    fwd = fwd.rename("fwd_10d_pct")

    # ---- VIX baseline (point-in-time) ----
    vix = yf.download("^VIX", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    vix.index = pd.to_datetime(vix.index).normalize()

    def vix_label(v):
        if v < 17:
            return "Bull"
        if v > 25:
            return "Bear"
        return "Transitional"

    vix_pred = vix.dropna().apply(vix_label).rename("vix_label")

    # ---- Persistence baseline: trailing 10d return decides direction ----
    trail = (spy / spy.shift(HORIZON) - 1) * 100  # past 10d return
    persist = trail.apply(lambda r: "Bull" if r > FLAT_THRESHOLD_PCT
                                       else ("Bear" if r < -FLAT_THRESHOLD_PCT else "Transitional"))
    persist = persist.rename("persist_label")

    # ---- Combine ----
    df = pd.concat([pred_df["hmm_label"], vix_pred, persist, fwd], axis=1).dropna()
    df["actual"] = df["fwd_10d_pct"].apply(actual_direction)
    print(f"\nEvaluation rows (after dropping NaNs): {len(df)}")

    # ---- Score each predictor ----
    print("\n" + "=" * 100)
    print(" DIRECTIONAL ACCURACY (predicted regime → expected direction matched actual?)")
    print("=" * 100)

    for col, name in [("hmm_label", "HMM Walk-Forward"),
                      ("vix_label", "VIX Threshold Rule"),
                      ("persist_label", "Persistence (trailing 10d)")]:
        df["expected"] = df[col].apply(expected_direction_from_regime)
        hit = (df["expected"] == df["actual"]).mean()
        # Random baseline for 3-class is 1/3 = 33.3%
        # But class balance matters; the actual class distribution is what matters
        actual_dist = df["actual"].value_counts(normalize=True)
        # If predictor always picked actual's mode:
        always_mode = df["actual"].value_counts(normalize=True).max()
        print(f"\n{name}:")
        print(f"  Overall hit rate:  {hit*100:.1f}%   (baseline always-pick-mode = {always_mode*100:.1f}%)")
        # Per-prediction breakdown: when we said X, what actually happened?
        for label in ["Bull", "Bear", "Transitional"]:
            mask = df[col] == label
            n = mask.sum()
            if n == 0:
                continue
            mean_ret = df.loc[mask, "fwd_10d_pct"].mean()
            up_pct = (df.loc[mask, "actual"] == "UP").mean() * 100
            down_pct = (df.loc[mask, "actual"] == "DOWN").mean() * 100
            print(f"    Predicted {label:12s} ({n:4d} days):  "
                  f"avg actual fwd 10d return = {mean_ret:+.2f}%  | "
                  f"UP {up_pct:5.1f}%  DOWN {down_pct:5.1f}%")

    print("\n" + "=" * 100)
    print(" ACTUAL OUTCOME DISTRIBUTION (over the OOS window)")
    print("=" * 100)
    print(df["actual"].value_counts())
    print()
    print(f"Mean fwd 10d return across all days: {df['fwd_10d_pct'].mean():+.2f}%")
    print(f"Std  fwd 10d return:                 {df['fwd_10d_pct'].std():+.2f}%")

    # ---- The most actionable question ----
    print("\n" + "=" * 100)
    print(" MOST ACTIONABLE QUESTION: When the model says BEAR, does the market actually fall?")
    print("=" * 100)
    for col, name in [("hmm_label", "HMM"), ("vix_label", "VIX rule"),
                      ("persist_label", "Persistence")]:
        bear = df[df[col] == "Bear"]
        if len(bear) == 0:
            print(f"\n{name}: never predicted Bear")
            continue
        n_down = (bear["actual"] == "DOWN").sum()
        n_total = len(bear)
        mean_ret = bear["fwd_10d_pct"].mean()
        print(f"\n{name} ({n_total} Bear predictions): ")
        print(f"  Actual market DOWN: {n_down}/{n_total} = {n_down/n_total*100:.1f}%")
        print(f"  Mean fwd 10d return when Bear predicted: {mean_ret:+.2f}%")
        print(f"  (Compare to baseline DOWN frequency on all days: "
              f"{(df['actual']=='DOWN').mean()*100:.1f}%)")


if __name__ == "__main__":
    main()
