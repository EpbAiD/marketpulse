# Auto Mode Guide - Market Regime Forecasting System

**Last Updated**: 2026-01-24

---

## Overview

Auto Mode is the intelligent, hands-off way to run the Market Regime Forecasting System. It automatically:
1. **Detects** if models exist and are fresh
2. **Decides** whether to train, retrain, or just run inference
3. **Executes** the appropriate workflow
4. **Updates** the dashboard with latest forecasts

---

## Quick Start

### One-Line Command
```bash
python run_pipeline.py --workflow auto
```

Or use the convenience script:
```bash
./run_auto_inference.sh
```

That's it! The system will:
- ✅ Check if all 22 feature models exist
- ✅ Verify models are not stale (< 90 days for daily, < 180 for weekly, < 365 for monthly)
- ✅ Run inference if models are ready
- ✅ Trigger training if models are missing/stale
- ✅ Update BigQuery with forecasts
- ✅ Refresh dashboard automatically

---

## How Auto Mode Works

### Intelligent Decision Logic

Auto mode uses the **Intelligent Model Checker** to make decisions:

```python
from orchestrator.intelligent_model_checker import get_intelligent_recommendation

recommendation = get_intelligent_recommendation()

if recommendation['workflow'] == 'inference':
    # All models fresh → Run inference only (2-3 minutes)
    run_inference_workflow()

elif recommendation['workflow'] == 'partial_train':
    # Some models stale → Retrain specific features (varies)
    run_partial_training(features_to_train)

else:  # 'train'
    # Core models missing or most features stale → Full retrain (5-6 hours)
    run_full_workflow()
```

### Model Freshness Thresholds

Different feature cadences have different retraining schedules:

| Cadence | Threshold | Reasoning |
|---------|-----------|-----------|
| **Daily** (18 features) | 90 days (3 months) | ~90 new data points accumulated |
| **Weekly** (1 feature) | 180 days (6 months) | ~26 new data points accumulated |
| **Monthly** (3 features) | 365 days (1 year) | 12 new data points accumulated |

**Core models** (HMM, Classifier): 90 days (fast to retrain, only ~20 seconds)

---

## Workflows Comparison

| Mode | When to Use | Duration | What It Does |
|------|-------------|----------|--------------|
| **`auto`** ⭐ | Daily operations, production | Variable | Smart: decides train vs infer |
| `inference` | Models exist and fresh | 2-3 minutes | Generate forecasts only |
| `training` | Need to retrain models | 5-6 hours | Train all models (no inference) |
| `full` | First-time setup | 5-6 hours | Train all + generate forecasts |

---

## Step-by-Step: What Happens in Auto Mode

### Phase 1: Model Detection (5 seconds)

```
🔍 AUTO MODE: Detecting required workflow...

📦 Core Models:
   ✅ HMM Model
   ✅ Regime Classifier
   ✅ Cluster Assignments
   ⏰ Age: 34 days

📊 Feature Models: 22 total
   ✅ Fresh: 22 features
      • COPPER, CPI, DFF, DGS10, DGS2...

💡 Workflow Recommendation: INFERENCE
📝 Reason: All 22 features are fresh and ready
```

### Phase 2: Execute Recommended Workflow

**If Inference:**
1. Fetch latest market data (90 seconds)
2. Load all 22 pre-trained models (instant)
3. Generate forecasts for next 10 days (30 seconds)
4. Engineer features from forecasts (5 seconds)
5. Predict regime for each day (1 second)
6. Save to BigQuery (5 seconds)
7. Dashboard auto-refreshes (cache: 5 minutes)

**Total: ~2-3 minutes** ⚡

**If Training:**
1. Fetch data → Engineer → Select → Cluster → Classify (10 minutes)
2. Train 22 feature models sequentially (5 hours)
3. Run inference (2 minutes)
4. Save everything to BigQuery

**Total: ~5-6 hours** 🐢

---

## Production Deployment

### GitHub Actions (Recommended)

Auto mode is perfect for scheduled workflows:

```yaml
name: Daily Forecast

on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM EST daily
  workflow_dispatch:

jobs:
  forecast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run Auto Mode
        env:
          GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GCP_CREDENTIALS }}
        run: python run_pipeline.py --workflow auto
```

**Benefits**:
- ✅ Runs daily at 6 AM automatically
- ✅ Uses intelligent detection (skips training if not needed)
- ✅ Fast when models are fresh (2-3 min)
- ✅ Self-healing: retrains if models get stale
- ✅ Zero maintenance required

### Local Cron Job

For local development/testing:

```bash
# Add to crontab (crontab -e)
0 6 * * * cd /path/to/RFP && ./run_auto_inference.sh >> logs/auto_inference.log 2>&1
```

---

## Dashboard Auto-Refresh

The Streamlit dashboard automatically loads the latest forecast from BigQuery:

### How It Works

1. **Cache TTL**: Dashboard caches data for 5 minutes
2. **Auto-reload**: When cache expires, fetches latest from BigQuery
3. **Freshness indicator**: Shows "Last Update" with color-coded age
   - 🟢 Green: < 24 hours old
   - 🟡 Orange: 24-48 hours old
   - 🔴 Red: > 48 hours old

### Accessing Dashboard

```bash
# Start dashboard
streamlit run dashboard/app.py

# Open browser to:
http://localhost:8501
```

The dashboard will automatically show:
- ✅ 10-day market regime forecast
- ✅ Confidence levels per day
- ✅ Historical regime analysis
- ✅ Risk-return profiles
- ✅ Market volatility insights
- ✅ Alert notifications (if regime shifts detected)

---

## Advanced Usage

### Check Model Status Without Running

```bash
# View detailed model status
python orchestrator/intelligent_model_checker.py

# Get JSON output for scripting
python orchestrator/intelligent_model_checker.py --json
```

**Exit codes**:
- `0`: All models ready for inference
- `1`: Training needed

### Force Training Even If Models Exist

```bash
# Run full training workflow (ignores auto detection)
python run_pipeline.py --workflow training
```

### Skip Specific Stages

```bash
# Auto mode but skip validation/monitoring (faster)
python run_pipeline.py --workflow auto --skip-validation --skip-monitoring
```

---

## Troubleshooting

### "No trained models found"

**Cause**: Model files or version metadata missing

**Solution**:
1. Check if models exist: `ls outputs/forecasting/models/*/nf_bundle_v1/`
2. Check version files: `ls outputs/forecasting/models/*_versions.json`
3. If models exist but versions missing, recreate metadata:
   ```python
   python -c "
   import json
   from pathlib import Path
   for feature_dir in Path('outputs/forecasting/models').iterdir():
       if (feature_dir / 'nf_bundle_v1').exists():
           version_file = feature_dir.parent / f'{feature_dir.name}_versions.json'
           if not version_file.exists():
               metadata = {
                   'versions': [{'version': 1, 'status': 'completed'}],
                   'active_version': 1
               }
               version_file.write_text(json.dumps(metadata, indent=2))
               print(f'Created {feature_dir.name}_versions.json')
   "
   ```

### "Models are stale, retraining needed"

**Expected behavior**: Models older than threshold trigger retraining

**To check age**:
```bash
python orchestrator/intelligent_model_checker.py
```

**To update threshold**:
```python
# In orchestrator/intelligent_model_checker.py
def get_retraining_threshold(cadence: str) -> int:
    thresholds = {
        'daily': 90,      # Change to 180 for 6 months
        'weekly': 180,    # Change to 365 for 1 year
        'monthly': 365    # Change as needed
    }
    return thresholds.get(cadence, 90)
```

### Dashboard shows "No forecast data available"

**Cause**: Inference hasn't run yet or BigQuery connection issue

**Solution**:
1. Run inference: `python run_pipeline.py --workflow auto`
2. Check BigQuery connection:
   ```bash
   python -c "from data_agent.storage import get_storage; storage = get_storage(); print(storage)"
   ```
3. Verify forecast table exists:
   ```bash
   bq ls regime01:forecasting_data
   ```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| [run_pipeline.py](../run_pipeline.py) | Main entry point, implements auto mode |
| [run_auto_inference.sh](../run_auto_inference.sh) | Convenience wrapper script |
| [orchestrator/intelligent_model_checker.py](../orchestrator/intelligent_model_checker.py) | Model detection & recommendations |
| [dashboard/app.py](../dashboard/app.py) | Streamlit dashboard with auto-refresh |
| [orchestrator/inference.py](../orchestrator/inference.py) | Inference pipeline orchestrator |
| [forecasting_agent/forecaster.py](../forecasting_agent/forecaster.py) | Model loading & forecasting logic |

---

## Performance Metrics

### Inference Mode (All Models Fresh)

| Stage | Duration |
|-------|----------|
| Model detection | 1s |
| Data fetching | 90s |
| Model loading | 5s |
| Forecasting (22 features) | 30s |
| Feature engineering | 5s |
| Regime prediction | 1s |
| BigQuery upload | 5s |
| **Total** | **~2-3 minutes** ⚡ |

### Training Mode (Full Retrain)

| Stage | Duration |
|-------|----------|
| Data → Feature selection | 10min |
| Training 22 feature models | 5 hours |
| Inference | 2min |
| **Total** | **~5-6 hours** |

---

## Best Practices

### 1. Use Auto Mode for Production

✅ **DO**: `python run_pipeline.py --workflow auto`
- Smart detection
- Fast when models are fresh
- Self-healing

❌ **DON'T**: `python run_pipeline.py --workflow full` (always retrains)
- Wastes time retraining fresh models
- No intelligent decision making

### 2. Schedule Daily at Low-Activity Hours

```bash
# GitHub Actions: 6 AM EST (11 AM UTC)
cron: '0 11 * * *'

# Local cron: 6 AM
0 6 * * * cd /path/to/RFP && ./run_auto_inference.sh
```

**Why**: Fresh data from previous trading day, low server load

### 3. Monitor Dashboard Freshness

Check the dashboard's "Last Update" indicator daily:
- 🟢 **< 24 hours**: System running normally
- 🟡 **24-48 hours**: Check logs, might have failed
- 🔴 **> 48 hours**: Immediate attention required

### 4. Version Control for Models

```bash
# Backup trained models to cloud storage
gsutil -m cp -r outputs/forecasting/models gs://your-bucket/models/$(date +%Y%m%d)/

# Or use Git LFS for versioning
git lfs track "outputs/forecasting/models/**/*.pth"
git lfs track "outputs/forecasting/models/**/nf_bundle_v*/**"
```

---

## Conclusion

Auto Mode provides a **zero-maintenance, production-ready** forecasting system:

- 🧠 **Intelligent**: Decides train vs infer automatically
- ⚡ **Fast**: 2-3 minutes when models are fresh
- 🔄 **Self-healing**: Retrains when models get stale
- 📊 **Reliable**: Updates dashboard with latest forecasts
- 🎯 **Simple**: One command does everything

**For daily operations, always use**:
```bash
python run_pipeline.py --workflow auto
```

---

**Questions?** Check the main [COMPLETE_SYSTEM_DOCUMENTATION.md](COMPLETE_SYSTEM_DOCUMENTATION.md) or [INTERVIEW_READY_GUIDE.md](INTERVIEW_READY_GUIDE.md)
