# Daily Update Script Fixes - December 25, 2024

## Issues Found

### Issue 1: Wrong Filename Pattern
**Problem:** Script was looking for `regime_predictions_*.parquet` files
**Actual files:** `regime_forecast_*.parquet`
**Impact:** Caused "N/A" values in metrics display

### Issue 2: Outdated Local Files
**Problem:** Recent runs (Dec 23-25) didn't generate local `regime_forecast_*.parquet` files
**Latest local file:** Dec 20, 2024
**Impact:** Metrics showed stale data even when script could find files

### Issue 3: Wrong Column Name
**Problem:** Script tried to access `predicted_date` column
**Actual column:** `ds`
**Impact:** Would fail even if files were found

### Issue 4: Wrong Data Source
**Problem:** Script read from local parquet files instead of BigQuery
**Reality:** The pipeline stores all data in BigQuery, local files are inconsistently generated
**Impact:** Displayed outdated or missing data

## Root Cause

The pipeline architecture changed:
- **Old approach:** Save predictions to local parquet files, read from files
- **Current approach:** Save predictions to BigQuery, read from BigQuery
- **Problem:** daily_update.sh was still using the old approach

## Solutions Implemented

### Fix 1: Use BigQuery as Primary Data Source
Changed both metric extraction points in `daily_update.sh` to read from BigQuery:

**Before:**
```bash
files = sorted(glob.glob('outputs/inference/regime_predictions_*.parquet'))
if files:
    df = pd.read_parquet(files[-1])
    print(df['ds'].max().strftime('%B %d, %Y'))
```

**After:**
```bash
from data_agent.storage import get_storage
storage = get_storage()
if hasattr(storage, 'get_latest_forecasts'):
    latest_forecasts = storage.get_latest_forecasts(limit=1)
    if len(latest_forecasts) > 0:
        forecast_id = latest_forecasts.iloc[0]['forecast_id']
        predictions = storage.get_forecast_by_id(forecast_id)
        latest_date = pd.to_datetime(predictions['ds']).max()
        print(latest_date.strftime('%B %d, %Y'))
```

### Fix 2: Better Error Messages
Added descriptive error messages so users know what failed:
- "N/A - No forecasts in BigQuery"
- "N/A - BigQuery not available"
- "Error: {message}" with truncated error details

### Fix 3: Consistent with log_daily_predictions.py
Made daily_update.sh use the same data access pattern as log_daily_predictions.py, which was already working correctly.

## Verification

### Test 1: Latest Forecast Date
```bash
$ python -c "... BigQuery code ..."
January 03, 2026
```
✅ Working - Shows forecast extends to Jan 3, 2026

### Test 2: Days Forecasted
```bash
$ python -c "... BigQuery code ..."
12 days forecasted
```
✅ Working - Shows 12 days of predictions

### Test 3: Data Freshness
Latest forecast ID: `forecast_20251225_130357` (December 25, 2024)
✅ Current - Generated today

## Files Modified

1. **daily_update.sh** - Lines 76-95 (latest forecast date)
2. **daily_update.sh** - Lines 114-130 (validation metrics)

## Lessons Learned

1. **Keep scripts synchronized**: When architecture changes (local files → BigQuery), update ALL scripts that depend on it
2. **Use single source of truth**: BigQuery is the production database, always read from there
3. **Test the full pipeline**: Don't just test that files are created, test that they're read correctly
4. **Better error messages**: "N/A" is confusing, "N/A - No forecasts in BigQuery" is actionable
5. **Document data flow**: Make it clear where data is stored and how it's accessed

## Related Files

- `log_daily_predictions.py` - Already using BigQuery correctly
- `orchestrator/inference.py` - Generates `regime_forecast_*.parquet` (when run)
- `data_agent/storage.py` - BigQuery storage interface
- `DAILY_PREDICTIONS.md` - Updated correctly by log_daily_predictions.py

## Status

✅ **FIXED** - All "N/A" issues resolved
✅ **TESTED** - Both metric extraction points verified working
✅ **DOCUMENTED** - This file explains the issues and fixes
