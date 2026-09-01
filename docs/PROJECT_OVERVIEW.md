# MarketPulse — Project Overview

A single-document reference to what this project is, what it does, what has been
built, what has been fixed, and where it stands today. Written to be the single
place a future reader (or interviewer) can go to understand the whole system
without having to piece together the codebase.

Last updated: 2026-07-13.

---

## Table of Contents

1. [What The System Does](#what-the-system-does)
2. [Who The System Is For](#who-the-system-is-for)
3. [Architecture](#architecture)
4. [The 22 Macro Features](#the-22-macro-features)
5. [Regime Labeling — The Composite Scorer](#regime-labeling--the-composite-scorer)
6. [Retraining Policy — Two-Gate Design](#retraining-policy--two-gate-design)
7. [The Dashboard (v2 Institutional)](#the-dashboard-v2-institutional)
8. [Backtest Results — Honest Reality](#backtest-results--honest-reality)
9. [Operational History (Apr–Jul 2026)](#operational-history-apr-jul-2026)
10. [Key Files And Where To Find Things](#key-files-and-where-to-find-things)
11. [Interview-Defensible Claims](#interview-defensible-claims)
12. [Open Items And Known Limitations](#open-items-and-known-limitations)

---

## What The System Does

MarketPulse produces, every trading day before US market open, a per-day
regime forecast for the next 10 trading days. Each day is classified as one of
three regimes plus an off-spectrum "Crisis Event" label for outlier
environments. Alongside the classification, the system publishes:

- A probability distribution across all regimes for each of the 10 forecast days
- The confidence with which today's regime call is made
- An illustrative asset allocation across SPY / QQQ / TLT / cash that the
  underlying strategy would use given the current regime read
- A 21-day rolling drawdown reference vs a passive SPY hold
- A per-regime historical risk profile (annualized realized volatility, mean
  VIX, and days losing more than 2%)

The system is a **risk-environment classifier**, not a directional price
forecaster. It answers "what is the current market environment and where is it
likely to go over the next two weeks?" It does not answer "will SPY be up or
down tomorrow?"

---

## Who The System Is For

The dashboard is designed for a professional tactical allocator handling other
people's money day-to-day in the tactical macro overlay space. Concretely:

- Registered Investment Advisors (RIAs) running tactical models for client
  portfolios
- Multi-family and single-family office CIOs / analysts
- Boutique wealth managers with discretion over client assets
- Quant researchers at asset managers benchmarking their own regime work
- Small hedge fund PMs running macro overlays

The tone, disclaimer language, and level of methodological detail match
this middle-market institutional audience. It is not designed for retail
day-traders, and it is not trying to compete with Bloomberg Terminal or MSCI
Barra at the top-tier institutional level.

Reference commercial products in the same space that prove this user exists:
[RegimeForecast.com](https://regimeforecast.com/),
[Portfolio Visualizer](https://www.portfoliovisualizer.com/tactical-asset-allocation-model),
[Newfound Research](https://www.thinknewfound.com/),
[Ned Davis Research](https://www.ndr.com/).

---

## Architecture

Two-stage pipeline running as a set of orchestrated agents:

### Stage 1 — Regime Detection

Unsupervised Gaussian Hidden Markov Model over 22 engineered macro features.
Trained on ~5,600 trading days of history. Currently 3 latent regimes; the
model partitions historical days by the joint behavior of all 22 features, not
by any single indicator.

Empirically the HMM's partition of the state space is structurally distinct
from every single-indicator regime rule tested (200-day moving average, VIX
percentile, yield curve inversion, NFCI financial-conditions index). Cramér's V
between the HMM partition and each single-indicator rule is below 0.21, and
the four single-indicator rules agree on the regime label only 7.5% of days.

### Stage 2 — Feature Forecasting

For each of the 22 features, the system runs an ensemble of three
peer-reviewed neural forecasting architectures with per-feature weight
optimization. The ensemble projects each feature 10 trading days ahead.

This is the standard institutional forecasting stack — the same architecture
family underpins commercial forecasting platforms (Amazon Forecast, Nixtla's
commercial offerings, top M4/M5 competition entries).

### Stage 3 — Regime Prediction

Projected features are fed back through the Stage 1 HMM to produce a
probability distribution over regimes for each of the next 10 trading days.
These are what the dashboard displays as the stacked probability ribbon.

### Orchestration

Runs daily via GitHub Actions before US market open. Total wall-clock ~8
minutes in steady state (no retrain triggered), ~25 minutes when Kaggle GPU
retraining fires.

Data warehouse: BigQuery (project `marketpulse-forecasting`, dataset
`marketpulse_data`, 14 tables). Local dev falls back to parquet in `outputs/`.

Retraining GPU compute: Kaggle T4 (free tier), kernel
`eeshanprasadbhanap/marketpulse-training`, triggered when the intelligent
model checker recommends it.

Dashboard: Streamlit, deployed via Streamlit Cloud from `main` branch.

---

## The 22 Macro Features

| Category | Series |
|---|---|
| Equity indices | GSPC (S&P 500), IXIC (NASDAQ) |
| Volatility complex | VIX, VIX3M, VIX9D |
| Rates | DGS10, TNX, DGS2, DGS3MO, DFF (Fed funds) |
| Yield spread | T10Y2Y |
| Credit spreads | HY_YIELD, IG_YIELD |
| Commodities | GOLD, COPPER, OIL |
| Currencies | DXY, UUP |
| Financial conditions | NFCI (weekly) |
| Macro monthly | CPI, INDPRO, UNRATE |

Cadences (daily / weekly / monthly) configured in `configs/features_config.yaml`.
Each cadence has its own retraining age threshold — see the next section.

---

## Regime Labeling — The Composite Scorer

**Problem.** HMMs exhibit label switching. Every retrain assigns arbitrary
integer IDs to the same latent regimes. A hardcoded mapping like `{0: "Bull",
1: "Bear", 2: "Transitional"}` silently becomes wrong the moment the model
retrains and assigns different IDs to the same clusters.

Additionally, ranking clusters by a single statistic fails for outlier
clusters. Concrete example: the March–May 2020 COVID window formed a distinct
70-day HMM cluster in our data. Ranking by "forward 21-day drawdown rate"
alone would label this cluster "Bull Market" because it precedes a strong
market recovery, despite having 61% annualized realized volatility and mean
VIX of 47. That is obviously wrong for allocator use.

**Solution shipped 2026-07-13** in
[`clustering_agent/clustering.py::derive_regime_label_map`](../clustering_agent/clustering.py):

### Step 1 — Population Filter

Any cluster containing fewer than 5% of total days is treated as an
outlier event, not a regular regime, and receives the label
`"Crisis Event"`. It is removed from the Bull-to-Bear spectrum assignment.
This alone catches transient panic clusters like the COVID window.

Config: `MIN_POPULATION_PCT = 0.05` at top of `clustering.py`.

### Step 2 — Composite Risk Score

For each remaining ("regular") cluster, compute a composite risk score as the
min-max normalized weighted sum of three independent risk signals:

| Signal | Weight | What It Captures |
|---|---|---|
| Forward 21-day drawdown propensity | 50% | Does this cluster precede real losses? |
| Realized volatility of equity index | 30% | Is this a calm or turbulent period? |
| Mean VIX level | 20% | Cross-check on market's own turbulence assessment |

If any signal is unavailable at labeling time (e.g., no raw price series), the
weights renormalize across the remaining available signals so ranking still
works.

### Step 3 — Spectrum Assignment

Regular clusters sorted by composite ascending. Lowest → `"Bull Market"`.
Highest → `"Bear Market"`. Intermediate clusters get the appropriate names
from `_LABEL_SPECTRUM_BY_K` (`"Transitional"` in the 3-regime case).

### Step 4 — Diagnostic Meta

Every generated label map file includes composite scores, per-signal values,
effective weights, outlier cluster IDs, and the exact rule string — so any
label choice can be audited after the fact.

### Result On Current Production State

| Cluster | Days | Realized Vol | Mean VIX | Old Label | New Label |
|---|---|---|---|---|---|
| 0 | 3,110 (55.6%) | 12% ann. | 16.6 | Transitional | **Bull Market** |
| 1 | 70 (1.3%) | 61% ann. | 47.0 | Bull Market (wrong) | **Crisis Event** |
| 2 | 2,410 (43.1%) | 16% ann. | 19.3 | Bear Market | **Bear Market** |

### Related Fix — HMM Fit-Timestamp Sidecar

The HMM was silently stale for months because the CI workflow retrained only
the neural forecasters, but the resulting bundle commits re-touched
`hmm_model.joblib`, giving it fresh git commit dates. The age checker was
fooled.

Fix: `clustering_agent/clustering.py` now writes
`outputs/models/hmm_fit_metadata.json` at every actual HMM re-fit, and
`orchestrator/intelligent_model_checker.py` prefers this sidecar timestamp
over the git commit date.

### N_REGIMES = 3, Not 5

The literature and practice consensus is 2-3 regimes for institutional TAA
work (Ang & Timmermann 2012 and follow-ups). BIC on our feature set also
favors 3. A 5-regime variant was tested and had marginally better worst-21-day
drawdown (-12.6% vs -18.9%), but was harder to defend against overfitting
critiques and less explainable. Shipped configuration is 3 regimes.

---

## Retraining Policy — Two-Gate Design

Aligned with Federal Reserve
[SR 11-7](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf)
model-risk guidance: material models validated at least annually, with
out-of-cycle retraining triggered by performance events.

### Gate 1 — Event-Based (Primary)

Per-feature SMAPE breach for 3 consecutive validations triggers automatic
retraining of that specific feature.

Thresholds are anchored to Lewis (1982) MAPE interpretation scale and
per-asset-class published forecasting benchmarks. Documented in
[`docs/RETRAINING_THRESHOLDS.md`](RETRAINING_THRESHOLDS.md) and implemented
in [`data_agent/validator.py::SMAPE_THRESHOLDS`](../data_agent/validator.py):

| Feature Group | Threshold | Anchor |
|---|---|---|
| Equity indices (GSPC, IXIC) | 10% | Deep-learning benchmarks 3-5% |
| Rates, credit, dollar, gold | 8-10% | Lewis "highly accurate" band |
| Volatility complex (VIX/VIX3M/VIX9D) | 25-40% | Short-vol noise floor |
| Yield spread (T10Y2Y) | 40% | Small-denominator inflation |
| Oil | 15% | Top-model benchmarks 5-6% |
| Financial conditions (NFCI) | 30% | Weekly, coarse |
| Macro monthly (CPI, INDPRO, UNRATE) | 10% | Near-noise-free |
| Fallback | 20% | — |

### Gate 2 — Age-Based (Safety Net)

Mandatory refresh at annual (daily features), 18-month (weekly), or 24-month
(monthly) cadence — matching SR 11-7 material-model expectations.

Implemented in
[`orchestrator/intelligent_model_checker.py::get_retraining_threshold`](../orchestrator/intelligent_model_checker.py).

### Result

In production, the system now retrains when something is actually wrong,
not on a rigid calendar. Steady-state daily runs are ~8 minutes with no
Kaggle triggered. Kaggle only fires on genuine SMAPE breach or annual
refresh — the intended behavior.

---

## The Dashboard (v2 Institutional)

Shipped 2026-07-13 as [`dashboard/app.py`](../dashboard/app.py). Old dashboard
preserved as `dashboard/app_v1.py.bak` (gitignored local recovery).

### Design Principles

1. Answer "what should I do differently today?" in the first 5 seconds
2. Probability ribbons over hard regime labels — regimes are inherently
   uncertain and the display should show it
3. Every recommendation carries its confidence and source
4. System health lives in a thin footer, not the headline
5. No emojis, reserved two-tone palette, print-friendly
6. Direct address ("you", "your book") — never third-person ("an allocator
   would")
7. No internal code paths, filenames, or library names anywhere in
   user-facing text
8. Industry-standard credibility signals (SR 11-7, walk-forward, Sharpe,
   max drawdown) are welcome; internal jargon is not

### Layout

| Section | Content |
|---|---|
| Header strip | Today's environment (regime + confidence), delta vs prior session, as-of timestamp |
| Today's Read | Regime probability bars + illustrative positioning (SPY/QQQ/TLT/Cash % with deltas) |
| Ten-Day Trajectory | Stacked probability ribbon + transition matrix from current regime |
| Risk Profile | Per-regime same-day risk cards + rolling 21-day drawdown chart |
| How This Compares To What You Already Use | Walk-forward table vs 60/40, 200dMA, buy-and-hold |
| What Goes Into The Regime Read | Plain-language methodology |
| Footer strip | Forecast timestamp, model last updated (color-coded), update cadence |
| Global disclaimer | Institutional / illustrative framing |

Confidence <60% blends the illustrative allocation toward a neutral 60/40 to
reflect uncertainty. Above 80%, more decisive tilts.

### Graceful Degradation

The dashboard uses BigQuery when available (production, CI) and falls back
to local parquet files for local development. When SPY market data is
unavailable, the risk cards switch to annualized realized volatility and
mean VIX per regime — computed directly from
`outputs/clustering/cluster_assignments.parquet` which is always present.

---

## Backtest Results — Honest Reality

Walk-forward test, yearly HMM refit from 2014-01-02, no look-ahead. Full
out-of-sample window 2014-01-02 → 2026-04-23 (12.3 years, ~3,100 trading
days). Reproducibility:
[`scripts/diagnostics/active_reallocator_backtest.py`](../scripts/diagnostics/active_reallocator_backtest.py).

| Approach | CAGR | Sharpe | Max DD | Worst 21d | Days > 2% Loss |
|---|---|---|---|---|---|
| Regime-Timed Allocation | **8.81%** | 0.74 | -32.51% | **-18.96%** | 1.49% |
| 60/40 Static | 9.28% | 0.87 | -27.24% | -18.45% | 0.87% |
| 200-Day MA Flip | 8.66% | 0.81 | -35.62% | -19.21% | 0.87% |
| Buy-and-Hold SPY | 13.47% | 0.82 | -33.72% | -36.72% | 3.23% |

### What The System Does Well

- Bounds worst 21-day drawdown to roughly half of buy-and-hold SPY
- Reduces days losing more than 2% from 3.2% to 1.5%
- Regime read is empirically distinct from single-indicator rules

### What The System Does NOT Do

- Does not beat buy-and-hold SPY on raw CAGR (loses by ~5 pp/year)
- Does not beat a 200-day moving average rule at flagging drawdowns
  directionally
- Is not a directional forecaster — it classifies today's environment,
  it does not predict tomorrow's price
- Detailed limitations and reproducibility notes in
  [`docs/BACKTEST_FINDINGS.md`](BACKTEST_FINDINGS.md)

---

## Operational History (Apr–Jul 2026)

Chronological log of significant bugs and fixes. Included so future readers
understand what has been learned.

### Apr 29, 2026 — Regime Labeling Overhaul (Commit `bce0ccc`)

Switched labeling from VIX-mean ranking to forward-drawdown ranking. Also
bumped N_REGIMES 3 → 5 in code. But the persisted `regime_label_map.json`
was never regenerated after this change, and the HMM was never retrained —
so production ran on a 3-cluster model with an old label map until July.

### May 12–23, 2026 — 12-Day CI Failure Streak

Root cause: `git pull --rebase` in the commit-and-push step aborted on
unstaged working-tree changes.

Fix: added `git stash push -u` before rebase, `git stash pop` after.
Pattern: never rebase with a dirty working tree in automation.

### Late Jun 2026 — False "Ensemble Missing" Warning

Root cause: the health check compared 59 total historical `nf_bundle_v*`
directories against 23 `_ensemble_v*.json` files.

Fix: rewrote to check per-feature active version via `*_versions.json`
metadata. Pattern: never trust cardinality of glob-matched historical
files as a health signal.

### Jul 7, 2026 — Kaggle Re-Trigger Loop Identified

Two components using different definitions of "needs training":
`intelligent_model_checker` fired on 90-day age (18 features stale), then
`incremental_trainer` resumed all features with existing bundles and
produced zero new output.

Fix (part of Jul 7 threshold rewrite): relaxed daily age threshold to 365
days matching SR 11-7. Kaggle now only fires on genuine SMAPE breach.

### Jul 8, 2026 — Expert-Informed Threshold Rewrite (Commit `a785df4`)

Per-feature SMAPE thresholds moved from arbitrary CV-derived values (20-45%)
to expert-informed values anchored to published forecasting benchmarks (5-40%
per asset class). Age thresholds relaxed to SR 11-7 defaults. Result: 4
consecutive successful daily runs at ~8 min each vs 25 min previously.

### Jul 13, 2026 — Silent HMM Staleness Diagnosis

Discovered the HMM `.joblib` file had been silently stale for months because
CI bundle commits re-touched it during forecaster retrains. Age checker was
reporting "17 days old" while the actual clustering hadn't changed since
January.

Fix: added `outputs/models/hmm_fit_metadata.json` sidecar written only on
actual re-fit. Age checker prefers sidecar timestamp over git commit date.

### Jul 13, 2026 — Composite Regime Labeler Shipped

Replaced drawdown-only ranking with the composite scorer + population filter
described earlier. Regenerated label map on existing HMM state — COVID
window correctly relabeled from "Bull Market" to "Crisis Event."

### Jul 13, 2026 — Dashboard v2 Shipped (Commit `a82b12c`)

Full rewrite of `dashboard/app.py` for a professional tactical allocator
audience. 5-section institutional layout. All internal code artifacts
removed from user-facing text. Old app preserved as `app_v1.py.bak`.

### Recurring Lessons

**Lesson 1.** When two components disagree about the same concept (e.g. "is
this model stale?"), it is not a bug in either — it is a design flaw.
Reconcile the definitions explicitly.

**Lesson 2.** File mtimes and git commit dates lie about "when this
artifact was last regenerated" if a bundle commit touches multiple files.
Anything that matters needs an explicit sidecar or embedded timestamp.

**Lesson 3.** A single-metric ranking function is fragile against outlier
clusters. Multi-signal composite scoring plus a population filter is the
robust pattern.

---

## Key Files And Where To Find Things

| Purpose | File |
|---|---|
| Live Streamlit dashboard | [`dashboard/app.py`](../dashboard/app.py) |
| HMM training + composite labeler | [`clustering_agent/clustering.py`](../clustering_agent/clustering.py) |
| Regime label loader | [`clustering_agent/labels.py`](../clustering_agent/labels.py) |
| Per-feature SMAPE thresholds | [`data_agent/validator.py`](../data_agent/validator.py) |
| Retrain-decision logic | [`orchestrator/intelligent_model_checker.py`](../orchestrator/intelligent_model_checker.py) |
| Daily CI workflow | [`.github/workflows/daily-forecast.yml`](../.github/workflows/daily-forecast.yml) |
| Kaggle training kernel | [`kaggle/train_marketpulse.py`](../kaggle/train_marketpulse.py) |
| Walk-forward backtest | [`scripts/diagnostics/active_reallocator_backtest.py`](../scripts/diagnostics/active_reallocator_backtest.py) |
| Honest backtest writeup | [`docs/BACKTEST_FINDINGS.md`](BACKTEST_FINDINGS.md) |
| Threshold justification | [`docs/RETRAINING_THRESHOLDS.md`](RETRAINING_THRESHOLDS.md) |
| Regime label map (single source of truth) | `outputs/models/regime_label_map.json` |
| HMM fit-timestamp sidecar | `outputs/models/hmm_fit_metadata.json` |
| Feature configuration | `configs/features_config.yaml` |

---

## Interview-Defensible Claims

Each claim below is backed by scripts and files in this repo. All are safe
to make in a technical interview.

### On The System As A Whole

"An end-to-end production ML system that fetches 22 macro time series daily,
detects the current market regime via unsupervised HMM clustering, forecasts
each feature 10 trading days ahead with a neural ensemble, and produces a
daily allocation reference — all running autonomously on GitHub Actions with
Kaggle T4 GPU for retraining and BigQuery as the warehouse. Live Streamlit
dashboard for the end user."

### On The Regime Model

"I chose 3 regimes because that is what the peer-reviewed regime-detection
literature converges on (Ang & Timmermann 2012 and follow-ups) and BIC on
the feature set supports it. A 5-regime variant was tested and marginally
improved worst-21-day drawdown but was harder to defend against overfitting
concerns and less explainable to end users."

### On The Ensemble Approach

"The forecasting ensemble follows the standard institutional macro
forecasting pattern — the same architecture family used by Amazon Forecast,
Nixtla's commercial stack, and the top M4/M5 competition entries. The
novelty is not in the model choice; it is in the operational engineering
around it."

### On The Labeling Robustness Fix

"HMMs have a label-switching property — every retrain assigns arbitrary
integer IDs to the same latent regimes. Naive ranking by a single statistic
also fails on outlier clusters. I designed a composite scoring approach
that combines forward drawdown, realized volatility, and VIX level, with a
population filter that routes tiny outlier clusters to an off-spectrum
'Crisis Event' label. This specific failure mode was caught in production
when a 70-day COVID-2020 cluster was being labeled 'Bull Market' by the
drawdown-only ranker."

### On Model Monitoring

"Retraining is aligned with Federal Reserve SR 11-7 model-risk guidance —
event-based primary trigger on per-feature SMAPE breach for 3 consecutive
validations, plus an annual mandatory refresh as a safety net. Per-feature
SMAPE thresholds are anchored to Lewis (1982) forecast-accuracy
interpretation and published per-asset-class forecasting benchmarks. The
model retrains when performance actually degrades, not on a rigid
calendar."

### On The Backtest

"Twelve-year walk-forward test, yearly refit, no look-ahead. On worst
21-day drawdown, the regime-timed strategy reduces the loss from -37%
(buy-and-hold SPY) to -19%, roughly on par with 60/40 and the 200-day
moving average rule. Days losing more than 2% drop from 3.2% to 1.5%. The
trade-off is roughly 5 percentage points of CAGR versus passive equity —
this is a risk-management overlay, not an alpha engine. All numbers are
reproducible from `scripts/diagnostics/active_reallocator_backtest.py`."

### On What The System Does NOT Do

Never oversell. Explicit "we don't do this" positioning:

- Not a directional price forecaster
- Not a buy-and-hold beater on CAGR
- Not a 200-day moving average beater at drawdown timing

---

## Open Items And Known Limitations

**HMM has not been re-fit since January 2026.** The neural forecasters retrain
frequently via Kaggle; the HMM has been sitting still because the daily
workflow was designed to retrain forecasters but not the clustering itself.
Fix scaffolding is in place (fit-timestamp sidecar) so the next real re-fit
is tracked honestly. But the actual HMM re-fit still needs to happen.

**Local BigQuery credentials are broken.** They point at project `regime01`
which has permission issues; production/CI uses `marketpulse-forecasting`.
Dashboard's local fallback to parquet handles this gracefully but any
diagnostic query needing BigQuery locally will fail with a 403.

**Kaggle metadata file has a runtime placeholder.** `kaggle/kernel-metadata.json`
contains a `KAGGLE_USERNAME` placeholder that CI substitutes with `sed` at
runtime. This causes a persistent local diff — safe to ignore, but any
`git rebase` from a fresh working tree needs to stash first.

**Dashboard is Streamlit, not a hardened institutional platform.** No SOC 2,
no SLA, no enterprise SSO. Framed as an illustrative allocator tool, not a
commercial product. Adequate for the portfolio-project purpose.

**Backtest window covers 2014–2026.** Includes the 2015-16 selloff, 2018 Q4,
2020 COVID crash, and 2022 rates shock. Does not include a stagflationary
period (1970s-style). The regime-detection approach may or may not generalize
to environments not represented in training data.
