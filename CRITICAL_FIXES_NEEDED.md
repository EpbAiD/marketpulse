# Critical System Fixes Required

**Date:** December 23, 2025
**Status:** 🔴 CRITICAL - System Not Working Properly

---

## Issue 1: Forecast Period Not Updating ❌

**Problem:**
- Dec 20 run: Forecast period 2025-12-19 to 2025-12-29
- Dec 22 run: Forecast period 2025-12-19 to 2025-12-29
- Dec 23 run: Forecast period 2025-12-19 to 2025-12-29

**Expected:**
- Dec 20 run: 2025-12-20 to 2025-12-30
- Dec 22 run: 2025-12-22 to 2026-01-01
- Dec 23 run: 2025-12-23 to 2026-01-02

**Root Cause:**
Even though we fixed the LangGraph workflow to fetch data, the inference pipeline is not using the LATEST date from fetched data. It's using cached/old data.

**Fix Needed:**
1. Check `orchestrator/inference.py` - ensure it loads LATEST data after fetch
2. Check `forecasting_agent/forecaster.py` - ensure it starts forecast from TODAY, not from last training date
3. BigQuery query should filter: `WHERE date > (SELECT MAX(date) FROM raw_features)`

---

## Issue 2: Predictions Are Identical Across Days ❌

**Problem:**
All three runs (Dec 20, 22, 23) show EXACTLY the same predictions:
- Same dates (Dec 19-29)
- Same confidence scores (0.742, 0.752, 0.746...)
- Same regime (all Transitional)

**Root Cause:**
The system is returning cached forecasts instead of generating new ones.

**Fix Needed:**
1. Check if inference is actually running or just reading old parquet files
2. Ensure forecast_id is unique per run (should include timestamp)
3. BigQuery should INSERT new forecasts, not UPDATE existing ones

---

## Issue 3: Alert Detection Logic is COMPLETELY WRONG ❌

**Current Logic (WRONG):**
```python
def get_dominant_regime_by_period(forecast_df, period_days=7):
    # Groups forecasts into 7-day periods
    # Compares Period 1 (Day 1-7) vs Period 1 (Day 1-7)
    # This doesn't make sense for detecting shifts!
```

**Correct Logic:**
```python
def detect_regime_shifts_by_date(previous_forecast, latest_forecast):
    """
    Example:
    - Dec 22 forecast: Dec 22-Jan 1 (10 days)
    - Dec 23 forecast: Dec 23-Jan 2 (10 days)
    - Overlapping dates: Dec 23-Jan 1 (9 days)

    For each overlapping date:
      if previous_forecast[date].regime != latest_forecast[date].regime:
          SHIFT DETECTED for that specific date
    """
    # Merge on date
    merged = pd.merge(
        previous_forecast,
        latest_forecast,
        on='ds',
        suffixes=('_prev', '_latest')
    )

    # Find shifts
    shifts = merged[merged['regime_prev'] != merged['regime_latest']]

    return shifts
```

**Example:**
```
Dec 22 Forecast:
  Dec 23: Transitional
  Dec 24: Transitional
  Dec 25: Bull
  Dec 26: Bull

Dec 23 Forecast:
  Dec 23: Transitional  ← No shift (Transitional → Transitional)
  Dec 24: Bull          ← SHIFT! (Transitional → Bull)
  Dec 25: Bull          ← No shift (Bull → Bull)
  Dec 26: Bear          ← SHIFT! (Bull → Bear)

Result: 2 shifts detected on Dec 24 and Dec 26
```

**Fix Needed:**
Completely rewrite `orchestrator/alerts.py`:
- Remove `get_dominant_regime_by_period()`
- Remove `compare_periods()`
- Add `detect_shifts_by_date()` that does date-by-date comparison

---

## Issue 4: SMAPE Always the Same ❌

**Problem:**
SMAPE validation requires:
1. Forecast from Day N
2. Wait for actual data to arrive
3. Compare forecast vs actual
4. Calculate SMAPE

**Current Issue:**
System runs validation immediately after inference (same day), so there's no actual data to compare against yet.

**Fix Needed:**
1. SMAPE validation should run AFTER actual data is available (not same day)
2. Store forecasts in BigQuery with forecast_date and predicted_date
3. Validation runs: "Get all forecasts where predicted_date <= TODAY and not yet validated"
4. Calculate SMAPE only for dates where actual data exists

---

## Issue 5: Data Fetch Not Working ❌

**Problem:**
Even though we fixed LangGraph routing, the forecast period is still stale (Dec 19).

**Possible Root Causes:**
1. Fetcher is running but BigQuery update is failing silently
2. Inference is reading from local cache instead of BigQuery
3. Forecast start date is hardcoded somewhere
4. Data fetcher is using wrong date range (not including latest days)

**Fix Needed:**
1. Add verbose logging to see what date range fetcher is using
2. Check BigQuery after fetch to verify new rows were added
3. Ensure inference reads: `SELECT MAX(date) FROM raw_features` to get latest date
4. Start forecast from: `latest_date + 1 day`

---

## Immediate Action Plan

### Step 1: Fix Data Fetch & Start Date

**File:** `orchestrator/inference.py`

```python
# After running forecaster, check what date we're starting from
print(f"Latest data available: {latest_date}")
print(f"Starting forecast from: {latest_date + 1 day}")
```

### Step 2: Fix Alert Detection

**File:** `orchestrator/alerts.py`

Replace entire logic with:

```python
def detect_shifts_by_date(self, previous_id: str, latest_id: str) -> List[Dict]:
    """Compare forecasts date-by-date for overlapping period"""

    # Get forecasts
    prev_df = self.get_forecast_predictions(previous_id)
    latest_df = self.get_forecast_predictions(latest_id)

    # Merge on date to find overlaps
    merged = pd.merge(
        prev_df[['ds', 'regime', 'regime_probability']],
        latest_df[['ds', 'regime', 'regime_probability']],
        on='ds',
        suffixes=('_prev', '_latest'),
        how='inner'  # Only overlapping dates
    )

    # Detect shifts
    shifts = []
    for _, row in merged.iterrows():
        if row['regime_prev'] != row['regime_latest']:
            shifts.append({
                'date': str(row['ds'].date()),
                'previous_regime': int(row['regime_prev']),
                'latest_regime': int(row['regime_latest']),
                'previous_confidence': float(row['regime_probability_prev']),
                'latest_confidence': float(row['regime_probability_latest'])
            })

    return shifts
```

### Step 3: Fix SMAPE Validation

**File:** `data_agent/validator.py`

```python
def run_validation_analysis():
    """
    Validate forecasts where actual data is now available

    Logic:
    1. Get all forecasts where predicted_date <= TODAY
    2. For each forecast, get actual regime for that date
    3. Calculate SMAPE between forecast and actual
    4. Mark forecast as validated
    """

    today = pd.Timestamp.now().date()

    # Query: forecasts with predicted_date in the past
    query = f"""
    SELECT * FROM regime_forecasts
    WHERE predicted_date <= '{today}'
    AND validation_status IS NULL
    """

    # For each forecast, compare to actual
    # Calculate SMAPE
    # Update validation_status
```

### Step 4: Add Debugging

**Run this to diagnose:**

```bash
# Check what data is in BigQuery
python -c "
from data_agent.storage import get_storage
storage = get_storage(use_bigquery=True)

# Check latest date in raw_features
import pandas as pd
query = 'SELECT MAX(timestamp) as latest FROM regime01.forecasting_pipeline.raw_features'
result = storage.client.query(query).to_dataframe()
print(f'Latest data in BigQuery: {result.iloc[0][\"latest\"]}')

# Check latest forecast
query = 'SELECT forecast_generated_at, forecast_start_date, forecast_end_date FROM regime01.forecasting_pipeline.regime_forecasts ORDER BY forecast_generated_at DESC LIMIT 5'
result = storage.client.query(query).to_dataframe()
print('\\nLatest forecasts:')
print(result)
"
```

---

## Summary

**Critical Issues:**
1. ❌ Forecast period not updating (stuck at Dec 19-29)
2. ❌ Predictions identical across all runs (caching issue)
3. ❌ Alert logic is completely wrong (using 7-day periods instead of date-by-date)
4. ❌ SMAPE validation running too early (no actual data to compare)
5. ❌ Data fetch not incorporating latest data properly

**All 5 issues must be fixed for the system to work correctly.**

---

**Next Steps:**
1. Run the debugging script to see what's actually in BigQuery
2. Fix the alert detection logic (highest priority)
3. Fix the forecast start date logic
4. Fix SMAPE validation to run asynchronously
5. Test end-to-end with verbose logging
