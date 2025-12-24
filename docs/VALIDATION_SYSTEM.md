# SMAPE-Based Feature Validation System

**Intelligent forecast validation that prevents false retraining triggers**

---

## Overview

The validation system compares forecasted **feature values** vs actual **feature values** using SMAPE (Symmetric Mean Absolute Percentage Error), instead of comparing regime labels.

### Why SMAPE Instead of Regime Accuracy?

**Problem with Regime Labels:**
```
VIX forecasted: 15.5
VIX actual: 14.5
Error: 6.7% (excellent forecast!)

BUT if regime boundary at VIX=15:
- Predicted regime: 1 (VIX > 15)
- Actual regime: 0 (VIX < 15)
- Regime accuracy: 0% (WRONG)
- Decision: RETRAIN ❌ (false trigger)
```

**Solution with SMAPE:**
```
VIX forecasted: 15.5
VIX actual: 14.5
SMAPE: 6.7%
Threshold: 20%

Result: 6.7% < 20% → GOOD ✅
Decision: NO RETRAIN (correct)
```

---

## SMAPE Formula

```
SMAPE = 100 * |actual - forecast| / ((|actual| + |forecast|) / 2)
```

**Interpretation:**
- 0-10%: Excellent forecast
- 10-20%: Good forecast  
- 20-40%: Acceptable forecast
- >40%: Poor forecast

**Advantages:**
- Continuous metric (not binary)
- Scale-independent
- Symmetric (treats over/under predictions equally)
- Directly measures forecast error magnitude

---

## Feature-Specific Thresholds

Thresholds based on historical coefficient of variation (CV = stddev/mean):

| Feature | Mean | StdDev | CV | SMAPE Threshold |
|---------|------|--------|-----|-----------------|
| GSPC    | 1813 | 1434   | 79% | 40% |
| VIX     | 19.5 | 7.8    | 40% | 20% |
| DGS10   | 4.25 | 1.94   | 46% | 23% |
| DGS2    | 3.24 | 2.27   | 70% | 35% |
| T10Y2Y  | 1.01 | 0.92   | 91% | 45% |
| DFF     | 2.88 | 2.35   | 82% | 41% |
| Default | -    | -      | -   | 30% |

**Methodology:** Threshold = 50% of coefficient of variation
- Higher volatility features get looser thresholds
- Lower volatility features get stricter thresholds

---

## Validation Process

### 1. Load Forecasted Features

```python
# From raw_forecasts_YYYYMMDD_HHMMSS.parquet
forecasted_df = load_forecasted_features(forecast_id)
# Returns: [date, feature, forecast_value]
```

### 2. Load Actual Features

```python
# From BigQuery raw_features table
actual_df = load_actual_features(start_date, end_date)
# Returns: [date, feature, actual_value]
```

### 3. Calculate SMAPE

```python
# Merge on (date, feature)
merged = forecasted_df.merge(actual_df, on=['date', 'feature'])

# Calculate SMAPE per feature
for feature in merged['feature'].unique():
    feature_data = merged[merged['feature'] == feature]
    smapes = [calculate_smape(row['actual'], row['forecast']) 
              for row in feature_data]
    feature_errors[feature] = np.mean(smapes)
```

### 4. Identify Critical Features

```python
critical_features = []
for feature, smape in feature_errors.items():
    threshold = smape_thresholds.get(feature, 30.0)
    if smape > threshold:
        critical_features.append(feature)
```

### 5. Retraining Decision

```python
needs_retraining = len(critical_features) / len(feature_errors) > 0.3
# Retrain if >30% of features exceed thresholds
```

---

## Current Performance

```
Total Forecasts Validated: 8
Average SMAPE: 2.94%
Retraining Decision: NO RETRAIN ✅
```

### Per-Feature Results

| Feature | Avg SMAPE | Threshold | Status |
|---------|-----------|-----------|--------|
| VIX9D   | 10.93%    | 10%       | ⚠️ Critical |
| T10Y2Y  | 10.91%    | 45%       | ✅ Good |
| VIX     | 6.55%     | 20%       | ✅ Good |
| OIL     | 6.03%     | 10%       | ✅ Acceptable |
| VIX3M   | 5.83%     | 10%       | ✅ Good |
| DFF     | 3.93%     | 41%       | ✅ Excellent |
| GOLD    | 1.93%     | 10%       | ✅ Excellent |
| DGS10   | 1.77%     | 23%       | ✅ Excellent |
| GSPC    | 0.92%     | 40%       | ✅ Excellent |

**Analysis:** Only VIX9D exceeds threshold (10.93% > 10%). Since 1/9 features (11%) is below 30% threshold, no retraining triggered.

---

## Comparison: Old vs New

| Metric | Regime-Based | SMAPE-Based |
|--------|--------------|-------------|
| Validation Method | Compare regime labels | Compare feature values |
| Result | 52.8% accuracy | 2.94% avg SMAPE |
| Retraining Decision | RETRAIN | NO RETRAIN |
| Problem | ❌ False triggers | ✅ True accuracy |
| Granularity | 36 regime comparisons | 120 feature comparisons |

---

## Retraining Triggers

The autonomous improvement agent triggers retraining when:

### 1. Direct Signal (Primary)
```python
if validator_result['needs_retraining']:
    retrain()  # >30% features exceed thresholds
```

### 2. Global Threshold
```python
if avg_smape > 30.0:
    retrain()  # Overall poor performance
```

### 3. Trend Degradation
```python
baseline_smape = mean(last_10_validations)
if current_smape - baseline_smape > 10.0:
    retrain()  # SMAPE degraded by 10pp
```

---

## Usage

### Run Validation

```bash
python bigquery_feature_validator.py
```

### Query Results

```sql
-- Overall metrics
SELECT
    AVG(overall_avg_smape) as avg_smape,
    MAX(needs_retraining) as needs_retraining
FROM `regime01.forecasting_pipeline.feature_validations`;

-- Per-feature SMAPE
SELECT
    feature_name,
    AVG(avg_smape) as avg_smape,
    AVG(smape_threshold) as threshold
FROM `regime01.forecasting_pipeline.feature_validations`
GROUP BY feature_name
ORDER BY avg_smape DESC;

-- Critical features
SELECT feature_name, avg_smape, smape_threshold
FROM `regime01.forecasting_pipeline.feature_validations`
WHERE exceeds_threshold = TRUE;
```

---

## Files

- **[bigquery_feature_validator.py](../bigquery_feature_validator.py)** - Main validation engine
- **[autonomous_improvement_agent.py](../autonomous_improvement_agent.py)** - Retraining orchestrator
- **[continuous_data_refresh.py](../continuous_data_refresh.py)** - Daily workflow integration

---

**Last Updated:** December 19, 2025
**Status:** ✅ Operational (2.94% avg SMAPE)
