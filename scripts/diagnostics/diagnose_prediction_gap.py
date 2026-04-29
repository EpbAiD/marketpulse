"""
Diagnose: HMM identifies novel multivariate structure (Cramér's V < 0.21
vs all single indicators), yet fails at predicting fwd-21d drawdowns
relative to a 200-day MA rule. Why?

Tests four hypotheses:

H1: We're picking the wrong cluster as "Bear".
    Currently we label by mean forward return. But the highest-VIX cluster
    has the HIGHEST mean forward return (post-crash bounce). What if we
    instead label by "cluster most associated with future drawdowns"?

H2: Features are backward-looking — they characterize the current state
    but contain little forward signal.
    Test: how much does each engineered feature category correlate with
    fwd-21d return? If correlations are near zero, feature engineering is
    the bottleneck.

H3: The HMM's regime transitions are predictive but unused.
    Test: instead of using the predicted current regime, use the most-
    probable NEXT regime from the HMM transition matrix.

H4: 3 regimes is too few. Compress hides structure.
    Test: refit with 5 regimes and see if drawdown separation improves.

Run from repo root:
    python scripts/diagnostics/diagnose_prediction_gap.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.preprocessing import StandardScaler
from hmmlearn.hmm import GaussianHMM


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CA_PATH = REPO_ROOT / "outputs" / "clustering" / "cluster_assignments.parquet"

HMM_RANDOM_STATE = 42
HORIZON = 21


def main():
    ca = pd.read_parquet(CA_PATH)
    ca.index = pd.to_datetime(ca.index).normalize()
    ca = ca.sort_index()
    feature_cols = [c for c in ca.columns if c != "regime"]

    spy = yf.download("^GSPC", start="2010-01-01", end="2026-04-29",
                      progress=False, auto_adjust=True)["Close"].squeeze()
    spy.index = pd.to_datetime(spy.index).normalize()

    fwd = (spy.shift(-HORIZON) / spy - 1) * 100
    drop = (fwd < -5).astype(int).rename("drop_in_21d")  # binary: did >5% drop occur?
    cum_min_fwd = (spy.rolling(HORIZON).min().shift(-HORIZON) / spy - 1) * 100
    cum_min_fwd = cum_min_fwd.rename("worst_fwd_pt")  # worst point reached in next 21d

    df = ca.join(fwd.rename("fwd_21d_pct"), how="inner")
    df = df.join(drop, how="inner")
    df = df.join(cum_min_fwd, how="inner").dropna()
    print(f"Aligned: {len(df)} days")

    # =========================================================================
    # H1: Try multiple labeling rules, compare which best identifies drawdowns
    # =========================================================================
    print("\n" + "=" * 100)
    print(" H1 — Which labeling rule best identifies upcoming drawdowns?")
    print("=" * 100)

    # Use the existing HMM regimes (in-sample, 3 states)
    print(f"\nUsing existing HMM with {df['regime'].nunique()} clusters")
    print(f"Cluster distribution: {df['regime'].value_counts().to_dict()}\n")

    # For each cluster, what fraction of its days had a >5% drop in next 21d?
    print("Per cluster — what predicts drawdowns:")
    summary = df.groupby("regime").agg(
        n_days=("fwd_21d_pct", "count"),
        mean_vix=("VIX_value", "mean"),
        mean_fwd=("fwd_21d_pct", "mean"),
        std_fwd=("fwd_21d_pct", "std"),
        worst_pt_mean=("worst_fwd_pt", "mean"),
        p_drop_5pct=("drop_in_21d", "mean"),
    ).round(3)
    summary["p_drop_5pct_pct"] = (summary["p_drop_5pct"] * 100).round(1)
    summary = summary.drop(columns=["p_drop_5pct"])
    print(summary)
    print()

    # Find which cluster has the HIGHEST drawdown probability — this is what
    # a "Bear / pre-drop warning" label SHOULD be assigned to.
    drawdown_per_cluster = df.groupby("regime")["drop_in_21d"].mean()
    bear_should_be = int(drawdown_per_cluster.idxmax())
    bull_should_be = int(drawdown_per_cluster.idxmin())
    print(f"Cluster MOST associated with future drawdowns: {bear_should_be} "
          f"(drawdown rate {drawdown_per_cluster[bear_should_be]*100:.1f}%)")
    print(f"Cluster LEAST associated with future drawdowns: {bull_should_be} "
          f"(drawdown rate {drawdown_per_cluster[bull_should_be]*100:.1f}%)")
    print()

    # Compare three labeling rules:
    print("Comparison of 3 labeling rules (which cluster gets called 'Bear'):")
    print(f"  Rule A — by VIX: highest VIX cluster = Bear (cluster {df.groupby('regime')['VIX_value'].mean().idxmax()})")
    print(f"  Rule B — by fwd return: lowest fwd return cluster = Bear (cluster {df.groupby('regime')['fwd_21d_pct'].mean().idxmin()})")
    print(f"  Rule C — by drawdown: highest drawdown rate cluster = Bear (cluster {bear_should_be})")
    print()

    # =========================================================================
    # H2: Are features backward-looking? Correlation with fwd return
    # =========================================================================
    print("=" * 100)
    print(" H2 — Do engineered features carry forward signal?")
    print("=" * 100)
    print("Spearman correlation between each feature and fwd-21d return")
    print("(|ρ| > 0.10 → feature has some forward signal; near 0 → backward-only)\n")

    corr_with_fwd = df[feature_cols].apply(lambda c: c.corr(df["fwd_21d_pct"], method="spearman"))
    corr_with_fwd = corr_with_fwd.abs().sort_values(ascending=False)
    print("Top 10 features by |correlation with fwd 21d return|:")
    print(corr_with_fwd.head(10).round(4).to_string())
    print(f"\nMedian |correlation| across all {len(feature_cols)} features: "
          f"{corr_with_fwd.median():.4f}")
    print(f"Features with |corr| > 0.10: {(corr_with_fwd > 0.10).sum()}/{len(feature_cols)}")
    print(f"Features with |corr| > 0.05: {(corr_with_fwd > 0.05).sum()}/{len(feature_cols)}")
    print()

    # Compare to a known-predictive baseline: SPY return over past 21 days
    # (the 200dMA rule essentially uses this)
    trail21 = (spy / spy.shift(21) - 1) * 100
    trail21_df = pd.DataFrame({"trail": trail21, "fwd": fwd}).dropna()
    print(f"For comparison: |Spearman corr(trailing 21d ret, fwd 21d ret)| = "
          f"{abs(trail21_df['trail'].corr(trail21_df['fwd'], method='spearman')):.4f}")
    print()

    # =========================================================================
    # H3: HMM transition probabilities — predictive on their own?
    # =========================================================================
    print("=" * 100)
    print(" H3 — Does the HMM transition matrix carry predictive info?")
    print("=" * 100)
    # Train an HMM on the full set so we can inspect the transition matrix
    scaler = StandardScaler().fit(df[feature_cols])
    Xz = scaler.transform(df[feature_cols])
    hmm = GaussianHMM(n_components=3, covariance_type="full", n_iter=1000,
                      random_state=HMM_RANDOM_STATE).fit(Xz)
    transmat = pd.DataFrame(hmm.transmat_,
                            index=[f"from {i}" for i in range(3)],
                            columns=[f"to {j}" for j in range(3)])
    print("Transition matrix P(next state | current state):")
    print(transmat.round(3))
    print()
    # If diagonal is ~1, regimes are sticky and transitions add nothing.
    # If off-diagonal is meaningful, knowing the current state genuinely
    # constrains the next.
    diag = float(np.diag(hmm.transmat_).mean())
    print(f"Mean diagonal probability (regime stickiness): {diag:.3f}")
    if diag > 0.95:
        print("→ Regimes are very sticky. Transition matrix adds little info beyond current label.")
    else:
        print(f"→ ~{(1-diag)*100:.0f}% chance of switching states each step. Transition info is non-trivial.")
    print()

    # =========================================================================
    # H4: Does 5 regimes separate drawdowns better than 3?
    # =========================================================================
    print("=" * 100)
    print(" H4 — Does increasing regime count improve drawdown separation?")
    print("=" * 100)
    for k in [3, 5, 7]:
        hmm_k = GaussianHMM(n_components=k, covariance_type="full",
                            n_iter=1000, random_state=HMM_RANDOM_STATE).fit(Xz)
        states_k = hmm_k.predict(Xz)
        df_k = df.copy()
        df_k["k_regime"] = states_k
        rates = df_k.groupby("k_regime")["drop_in_21d"].mean() * 100
        rates = rates.sort_values(ascending=False)
        print(f"\nWith k={k} regimes — drawdown rate per cluster (sorted high→low):")
        for rid, rate in rates.items():
            n = (df_k["k_regime"] == rid).sum()
            print(f"  Cluster {rid}: {rate:.1f}% drawdown rate ({n} days)")
        # Best/worst spread
        spread = rates.max() - rates.min()
        print(f"  → Spread (worst − best): {spread:.1f}pp "
              f"(higher is better separation)")


if __name__ == "__main__":
    main()
