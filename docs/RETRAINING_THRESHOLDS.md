# Retraining Thresholds — Expert-Informed

This document records the sources and rationale for the per-feature SMAPE
thresholds in `data_agent/validator.py::SMAPE_THRESHOLDS` and the age-based
thresholds in `orchestrator/intelligent_model_checker.py::get_retraining_threshold`.

## Governing principle

Federal Reserve SR 11-7 (Supervisory Guidance on Model Risk Management) requires
that material models be validated at least annually and that out-of-cycle
retraining be triggered by significant performance events rather than rigid
schedules. Our two-gate design implements exactly this:

1. **Event gate (primary)**: SMAPE breach — retrain the moment a feature's
   forecast error crosses its per-feature threshold for 3 consecutive
   validations. This is the responsive part.
2. **Age gate (safety net)**: annual (daily), 18-month (weekly),
   24-month (monthly). This catches slow drift that never trips SMAPE.

## SMAPE threshold references

### Lewis (1982) universal scale — the standard citation

| MAPE | Interpretation |
|---|---|
| < 10% | Highly accurate |
| 10 – 20% | Good forecast |
| 20 – 50% | Reasonable forecast |
| > 50% | Inaccurate |

Source: Lewis, C.D. (1982). *Industrial and Business Forecasting Methods*.
Butterworth Scientific, London.

We set most thresholds at the top of "highly accurate" (10%) or the top of
"good" (15-20%) depending on the feature's known noise floor.

### Per-asset-class published benchmarks

Threshold = the level at which "the model is now materially worse than what
peer-reviewed published models achieve." Set at roughly 2-3× the best-in-class
MAPE so that we fire only on genuine degradation, not on natural noise.

| Feature group | Best published MAPE | Our threshold | Source pointer |
|---|---|---|---|
| S&P 500 / equity indices (GSPC, IXIC) | 3-5% (deep learning) | **10%** | [arXiv 2103.14080 — Forecasting with Deep Learning: S&P 500](https://arxiv.org/abs/2103.14080) |
| Gold (GOLD) | 3.7-4.9% (LSTM, ARIMA) | **10%** | [IJSAT hybrid econometric gold](https://www.ijsat.org/papers/2025/4/9204.pdf) |
| Copper (COPPER) | ~5-6% | **12%** | Ensemble commodity studies |
| Crude oil (OIL) | 1.5-5.5% (top hybrid models), 12% monthly | **15%** | [Springer Reservoir Computing oil](https://link.springer.com/article/10.1007/s10614-024-10797-w) |
| Treasury yields (DGS10, TNX, DGS2, DGS3MO, DFF) | <5% (ML benchmarks) | **10%** | [MDPI ML for short-term Treasury yields](https://www.mdpi.com/2076-3417/15/12/6903) |
| Yield spread (T10Y2Y) | Denominator near zero inflates % errors | **40%** | Analytic — small-base problem |
| Credit yields (HY_YIELD, IG_YIELD) | ~5% (ML) | **10%** | Rate-adjacent extrapolation |
| Dollar index (DXY, UUP) | 0.55-3% (ML) | **8%** | [ResearchGate ML DXY comparison](https://www.researchgate.net/publication/371852609) |
| VIX (30-day implied vol) | 4.1% (best PSO transfer function), 15-30% typical in practice | **30%** | [Nature — multi-model VIX PSO](https://www.nature.com/articles/s41598-024-74456-8) |
| VIX9D (9-day implied vol) | Noisier than 30-day due to gamma exposure | **40%** | Analytic — short-vol high-noise regime |
| VIX3M (3-month implied vol) | ~5-8% | **25%** | Same family as VIX |
| NFCI (weekly financial conditions) | Weekly, coarse-grained | **30%** | Chicago Fed NFCI documentation |
| Macro monthly (CPI, INDPRO, UNRATE) | Near-noise-free series | **10%** | Lewis "highly accurate" cutoff |

### Refresh-cadence practitioner precedent

One published policy referenced in industry write-ups:
> "Mandatory full retraining every quarter AND automatic retraining triggered
> if SMAPE exceeds 15% for three consecutive weeks."

Source: [42Signals — Forecast Accuracy: MAPE, SMAPE & Model Drift Monitoring](https://www.42signals.com/blog/forecast-accuracy-and-model-drift-monitoring/)

We adopt the 3-consecutive-breach trigger, but relax the mandatory refresh from
quarterly to annual because our features are macroeconomic (structural) not
consumer-behavior (fast-drifting). Quarterly refresh of a 10-year Treasury
model is overkill; annual matches SR 11-7 material-model expectations.

## Age-threshold references

| Cadence | Threshold | Why |
|---|---|---|
| Daily | 365 days | SR 11-7 annual material-model validation cycle |
| Weekly | 540 days | ~78 weekly datapoints between refreshes — sufficient for a meaningful retrain |
| Monthly | 730 days | 24 monthly datapoints — monthly macro series need long context to change meaningfully |

Source: [Federal Reserve SR 11-7 revised guidance](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf)

## What this replaces

The prior thresholds were derived from historical coefficient-of-variation of
the input series (e.g., "S&P 500 CV=79% → threshold=40%"). That approach
confused input-series volatility with acceptable forecast error — a highly
volatile input can still be forecast well and vice versa. The expert-informed
thresholds above key off *forecast* error benchmarks published in
peer-reviewed literature, which is what the threshold is actually supposed to
measure.

## Verification

To sanity-check a threshold change, run:

```bash
python -c "
from google.cloud import bigquery
c = bigquery.Client(project='marketpulse-forecasting')
q = '''
SELECT feature, APPROX_QUANTILES(avg_smape,100)[OFFSET(50)] p50,
       APPROX_QUANTILES(avg_smape,100)[OFFSET(95)] p95
FROM \`marketpulse-forecasting.marketpulse_data.feature_validations\`
WHERE validation_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  AND avg_smape < 199.9
GROUP BY feature
'''
for r in c.query(q):
    print(f'{r.feature:12} p50={r.p50:.2f}%  p95={r.p95:.2f}%')
"
```

If p95 for a feature is regularly exceeding its threshold on non-degraded runs,
the threshold is too tight. If p95 is far below threshold and the model has
never triggered a retrain, the threshold may be too loose (compare against the
published-benchmark column above to confirm).
