# Empirical Validation of MarketPulse

This document records what walk-forward backtests and head-to-head benchmarks
actually show about the MarketPulse system. It exists so any future reader
(or interviewer) can see the honest picture, including where the system
underperforms simple alternatives.

All results are from `scripts/diagnostics/`:
- `honest_backtest.py` — in-sample HMM allocation vs SPY vs VIX rule
- `walkforward_backtest.py` — yearly-refit HMM (out-of-sample) vs SPY/VIX rule
- `trend_accuracy_test.py` — directional accuracy on fwd-10d returns
- `trend_vs_industry.py` — directional accuracy vs 200dMA / persistence / VIX percentile
- `regime_information_value.py` — multivariate regime structure vs single indicators

## TL;DR

| Question | Answer |
|---|---|
| Does the HMM beat buy-and-hold SPY on risk-adjusted return? | **No.** Walk-forward Sharpe 0.81 vs SPY 0.82 |
| Does it beat a 200-day moving average rule at predicting crashes? | **No.** 200dMA flags 16.8% of "Bear" days as actual >5% drops; HMM flags only 6.8% |
| Does it discover regime structure that single indicators miss? | **Yes.** Single indicators (200dMA, VIX %ile, yield curve, NFCI) agree on the regime label only 7.5% of days; HMM has Cramér's V < 0.21 with each — its partition is structurally novel |
| Does the engineering work end-to-end in production? | **Yes.** Daily GitHub Actions + Kaggle GPU + BigQuery + Streamlit, autonomous retraining, label-switching robust |

The defensible claim is **about the engineering and the multivariate
characterization**, not about market timing or alpha generation.

---

## 1. Allocation Backtest (Walk-Forward)

`scripts/diagnostics/walkforward_backtest.py`

Setup:
- Yearly HMM refit on prior data only (no look-ahead from 2014 onward)
- 70/20/10 cash allocation in "Bull", 20/10/70 TLT in "Bear", 40/20/40 in "Transitional"
- Compared against SPY buy-and-hold and a VIX threshold rule

Result over 12.3 years (2014-2026):

| Strategy | CAGR | Sharpe | Max DD | Final $1 → |
|---|---|---|---|---|
| Buy-and-Hold SPY | **13.47%** | 0.819 | -33.72% | **$4.72** |
| HMM Walk-Forward | 10.20% | 0.811 | **-27.37%** | $3.30 |
| VIX Threshold Rule | 7.87% | 0.731 | -33.73% | $2.54 |

**Read**: HMM gives up ~3pp of CAGR for ~6pp lower drawdown. Sharpe is
roughly indistinguishable from passive holding. This is a risk-management
profile, not an alpha edge.

## 2. Directional Accuracy (Bull/Bear/Transitional → UP/DOWN/FLAT)

`scripts/diagnostics/trend_vs_industry.py` — predicting fwd-21-day direction:

| Predictor | Hit rate | When says Bear, P(>5% drop) | Lift over baseline |
|---|---|---|---|
| 200-day MA | **51.0%** | **16.8%** | **+11pp** |
| 21-day Persistence | 40.8% | 9.7% | +4pp |
| Fear & Greed (VIX %ile) | 30.5% | 8.8% | +3pp |
| HMM Walk-Forward | 24.2% | 6.8% | +1pp |
| Always-pick-mode baseline | 56.1% | 5.9% | — |

**Read**: A textbook 200-day moving average rule outperforms the HMM at
flagging actual drawdowns. The HMM's "Bear" regime preferentially captures
post-stress mean-reversion zones (where forward returns average +1.4%),
not the start of new declines. Calling these "Bear" misleads the user.

## 3. Multivariate Information Value

`scripts/diagnostics/regime_information_value.py` — does combining
indicators discover structure single indicators miss?

### Test 3a: Single indicator agreement
| Pair | Days agree on regime |
|---|---|
| 200dMA ↔ VIX percentile | 37.1% |
| 200dMA ↔ Yield curve | 30.8% |
| 200dMA ↔ NFCI | 51.1% |
| **All 4 agree** | **7.5%** |

The four canonical regime indicators are largely independent of each other.
There IS room for a multivariate model to add value by combining them.

### Test 3b: HMM partition vs single-indicator partitions

| Single indicator | Cramér's V w/ HMM | Adjusted Rand | Day agreement |
|---|---|---|---|
| 200dMA | 0.065 | 0.019 | 16.5% |
| VIX percentile | 0.140 | 0.016 | 39.3% |
| Yield curve | 0.201 | -0.025 | 33.6% |
| NFCI | 0.158 | 0.024 | 42.9% |

Cramér's V values all well below the 0.3 "moderate similarity" threshold.
**The HMM is not rediscovering any single indicator — it carves the state
space along a different dimension.**

### Test 3c: Statistical separation per regime
| Labeling | Bull tail risk | Bear tail risk | Tail separation |
|---|---|---|---|
| 200dMA | 5.9% | **16.8%** | **+10.8pp** |
| VIX percentile | 3.2% | 8.8% | +5.6pp |
| HMM | 12.9% | 6.8% | **−6.1pp (inverted)** |

The HMM separates regimes by **volatility regime and recovery patterns**,
not by tail risk. Its "Bear" cluster captures post-crash high-vol
recovery zones, not pre-decline warning zones.

---

## What This Means For Project Framing

**Don't claim**: "Predicts trend / direction / regime 10 days ahead with high accuracy."

**Do claim**:
1. **Engineering**: production multi-agent ML pipeline (data fetch → feature
   engineering → unsupervised clustering → supervised classification →
   forecast → live dashboard), autonomous daily orchestration via LangGraph,
   automated retraining via Kaggle GPU, BigQuery storage, all running daily.

2. **Multivariate characterization**: empirically demonstrated that single-
   indicator regime rules disagree 92.5% of days, and that the HMM's
   unsupervised clustering produces a structurally novel partition (not
   redundant with any single indicator). This is the methodological win.

3. **Risk profile, not alpha**: walk-forward HMM allocation reduces max
   drawdown (-27% vs -34% for SPY) at the cost of CAGR. Useful as a
   risk-aware overlay, not as a market-beating signal.

4. **Acknowledged limitation**: a single 200-day moving average rule
   outperforms the HMM at the specific task of flagging upcoming
   drawdowns. The HMM's clusters describe current conditions, not
   forecast direction.

This framing is bulletproof against any technical interviewer because the
numbers — both the wins and the losses — are reproducible from the scripts
in `scripts/diagnostics/`.
