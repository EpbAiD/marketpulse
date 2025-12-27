# Market Regime Forecasting System - Usage Guide

**LangGraph-Orchestrated Multi-Agent System**

---

## Quick Start

### ⭐ Recommended: Smart Auto Mode

```bash
# First time or anytime - system auto-detects what to do
python run_daily_update.py
```

**What it does:**
- ✅ **No models?** → Trains models, then generates predictions
- ✅ **Models too old?** → Retrains models, then generates predictions
- ✅ **Models ready?** → Generates predictions only
- ✅ **Performance degraded?** → Automatically retrains during monitoring

**This is the simplest and smartest way to run the system!**

---

## How Auto-Detection Works

The system checks:

1. **Do model files exist?**
   - `outputs/models/hmm_model.pkl`
   - `outputs/models/regime_classifier.pkl`
   - `outputs/models/forecasting_models.pkl`
   - `outputs/clustering/cluster_assignments.parquet`

2. **Are models fresh enough?**
   - Default: Models older than 30 days → Retrain
   - Configurable: `--max-model-age N`

3. **Recommendation:**
   - **Missing models** → Run full workflow (train + infer)
   - **Old models** → Run full workflow (retrain + infer)
   - **Fresh models** → Run inference only

---

## Usage Scenarios

### 1. First Time Setup

```bash
# Auto mode (recommended)
python run_daily_update.py

# OR explicit full workflow
python run_pipeline.py --workflow full
```

**LangGraph Flow:**
```
cleanup → fetch → engineer → select → cluster → classify → forecast
          (TRAINING - builds all models)
                ↓
          inference → alerts → validation → monitoring
          (INFERENCE - generates predictions & monitors performance)
```

**Output:**
- Trained models in `outputs/models/`
- Cluster assignments in `outputs/clustering/`
- Regime forecasts in `outputs/inference/`
- Performance metrics in monitoring results

---

### 2. Daily Operations (Production)

```bash
# Smart mode (recommended) - auto-detects if retraining needed
python run_daily_update.py

# Or use run_pipeline.py directly
python run_pipeline.py --workflow auto
```

**LangGraph Flow (if models exist):**
```
cleanup → inference → alerts → validation → monitoring
          (INFERENCE WORKFLOW)
                ↓
          Monitoring checks: needs_retraining?
                ↓
          If YES → loops back to fetch (retrains)
          If NO → END
```

**When Retraining Triggers:**
1. Validation SMAPE exceeds thresholds
2. Accuracy trending down over time
3. Recent performance below acceptable level

---

### 3. Force Retraining

```bash
# Train models without running inference
python run_pipeline.py --workflow training

# Train + inference
python run_pipeline.py --workflow full
```

**Use cases:**
- New market data sources added
- Feature engineering logic changed
- Want to rebuild all models from scratch

---

### 4. Inference Only (No Training)

```bash
# Disable auto-detection
python run_daily_update.py --no-auto

# Or directly
python run_pipeline.py --workflow inference
```

**Note:** This will fail if models don't exist. Use auto mode instead!

---

## Command Reference

### Main Pipeline

```bash
python run_pipeline.py [OPTIONS]
```

**Workflow Options:**
- `--workflow auto` ⭐ **Recommended** - Smart detection
- `--workflow full` - Train + Infer + Monitor
- `--workflow training` - Training only
- `--workflow inference` - Inference only

**Auto Mode Options:**
- `--max-model-age N` - Max model age in days (default: 30)

**Training Skip Flags:**
- `--skip-fetch` - Skip data fetching
- `--skip-engineer` - Skip feature engineering
- `--skip-select` - Skip feature selection
- `--skip-cluster` - Skip clustering
- `--skip-classify` - Skip classification
- `--skip-forecast` - Skip forecasting model training

**Inference Skip Flags:**
- `--skip-inference` - Skip inference
- `--skip-alerts` - Skip alert detection
- `--skip-validation` - Skip validation
- `--skip-monitoring` - Skip monitoring

**Other:**
- `--no-clean` - Don't clean outputs before running

### Daily Update Wrapper

```bash
python run_daily_update.py [OPTIONS]
```

**Options:**
- `--local` - Use local files instead of BigQuery
- `--no-auto` - Disable auto-detection (inference only)
- `--retrain-if-needed` - (Legacy, kept for compatibility)

### Model Status Check

```bash
# Check if models are ready
python orchestrator/model_checker.py

# Custom age threshold
python orchestrator/model_checker.py --max-age 7
```

**Exit codes:**
- `0` - Models ready for inference
- `1` - Models missing or too old

---

## Workflow Decision Tree

```
START: python run_daily_update.py
  │
  ▼
Check: --no-auto flag?
  │
  ├─ NO (default) ─────────────────────┐
  │                                    │
  │                              Check models
  │                                    │
  │                    ┌───────────────┼───────────────┐
  │                    │               │               │
  │              Models exist?   Models old?    Models missing?
  │                    │               │               │
  │                   YES              │              YES
  │                    │               │               │
  │                    ▼               ▼               ▼
  │              INFERENCE         RETRAIN          TRAIN
  │                 ONLY          + INFER         + INFER
  │                    │               │               │
  │                    └───────────────┴───────────────┘
  │                                    │
  └─ YES ─────────────────────┐        │
                              │        │
                              ▼        ▼
                         INFERENCE WORKFLOW
                              │
                              ▼
                      inference → alerts
                              │
                              ▼
                      validation → monitoring
                              │
                    ┌─────────┴─────────┐
                    │                   │
            needs_retraining?          │
                    │                   │
                   YES                 NO
                    │                   │
                    ▼                   ▼
            Loop to TRAINING          END
```

---

## LangGraph Architecture

All workflows are orchestrated by LangGraph in [orchestrator/graph.py](orchestrator/graph.py).

### Single Orchestrator

```python
from orchestrator.graph import build_complete_graph

# One function builds ALL workflows
graph = build_complete_graph(workflow_type="auto")
```

### Conditional Routing

Based on `workflow_type` in state:
- `training` → Training nodes only
- `inference` → Inference nodes only
- `full` → Training → Inference → (optional retrain loop)
- `auto` → Detects and sets to `inference` or `full`

### State Management

All state flows through `PipelineState`:
```python
{
    "workflow_type": "auto",
    "needs_retraining": False,
    "fetch_status": {...},
    "inference_status": {...},
    "validation_status": {...},
    "monitoring_status": {...}
}
```

---

## Auto-Retraining Logic

### Trigger Conditions (checked by monitoring node)

1. **SMAPE Thresholds Exceeded**
   ```python
   # In data_agent/validator.py
   SMAPE_THRESHOLDS = {
       'GSPC': 40.0,
       'VIX': 20.0,
       'DGS10': 23.0,
       ...
   }
   ```

2. **Accuracy Trending Down**
   - Compares last 7 days vs last 30 days
   - Triggers if 7-day avg SMAPE > 30-day avg SMAPE + threshold

3. **Recent Poor Performance**
   - Last 7 days avg SMAPE > critical threshold
   - Triggers immediate retraining

### Retraining Flow

```
monitoring_node sets: state['needs_retraining'] = True
         ↓
LangGraph routes: monitoring → fetch (restart training)
         ↓
Training workflow: fetch → engineer → select → cluster → classify → forecast
         ↓
Back to inference: inference → alerts → validation → monitoring
```

---

## Examples

### Example 1: First Time User

```bash
# Just run this - system handles everything
python run_daily_update.py
```

**Output:**
```
======================================================================
🔍 AUTO MODE: Detecting required workflow...
======================================================================

✅ Ready for inference: NO
📝 Reason: Missing required models: hmm_model, classifier, forecasting_models

💡 Recommendation: TRAIN

🆕 No models found! Running full workflow (train + inference)...

🚀 TRAINING WORKFLOW
Run ID: rfp-20241219-120000

✅ fetch complete
✅ engineer complete
✅ select complete
✅ cluster complete
✅ classify complete
✅ forecast complete

🔮 INFERENCE WORKFLOW

✅ inference complete
✅ alerts complete
✅ validation complete
✅ monitoring complete

✅ FULL WORKFLOW COMPLETE
```

### Example 2: Daily Update (Models Exist)

```bash
python run_daily_update.py
```

**Output:**
```
======================================================================
🔍 AUTO MODE: Detecting required workflow...
======================================================================

✅ Ready for inference: YES
📝 Reason: All models present and fresh (5 days old)

💡 Recommendation: INFERENCE

✅ Models ready! Running inference workflow...

🔮 INFERENCE WORKFLOW

✅ inference complete (10-day forecast generated)
✅ alerts complete (no regime shifts detected)
✅ validation complete (avg SMAPE: 18.5%)
✅ monitoring complete (performance within acceptable range)

✅ INFERENCE WORKFLOW COMPLETE
```

### Example 3: Models Outdated

```bash
python run_daily_update.py --max-model-age 7
```

**Output:**
```
======================================================================
🔍 AUTO MODE: Detecting required workflow...
======================================================================

✅ Ready for inference: NO
📝 Reason: Models are 15 days old (max: 7 days)

💡 Recommendation: RETRAIN

🔄 Models outdated! Running full workflow (retrain + inference)...

[Training workflow runs...]
[Inference workflow runs...]

✅ FULL WORKFLOW COMPLETE
```

### Example 4: Check Model Status Only

```bash
python orchestrator/model_checker.py
```

**Output:**
```
======================================================================
📊 MODEL AVAILABILITY CHECK
======================================================================

✅ Ready for inference: YES
📝 Reason: All models present and fresh (12 days old)

📦 Model Status:
   ✅ hmm_model: Present
   ✅ classifier: Present
   ✅ forecasting_models: Present
   ✅ cluster_assignments: Present

⏰ Model Age: 12 days (max: 30 days)

💡 Recommendation: INFERENCE
======================================================================
```

---

## Storage Backends

The system supports both BigQuery and local storage transparently.

### BigQuery (Default for Production)

```yaml
# configs/bigquery_config.yaml
bigquery:
  enabled: true
  project_id: "your-project"
  dataset_id: "market_regime"
  credentials_path: "path/to/credentials.json"
```

### Local Files (Development/Testing)

Set `enabled: false` in BigQuery config, or just don't provide credentials.

**All code uses unified storage:**
```python
from data_agent.storage import get_storage

storage = get_storage()  # Auto-detects BigQuery or local
storage.save_forecast(predictions)
```

---

## Dashboard

```bash
streamlit run dashboard/app.py
```

Dashboard automatically:
- Uses storage layer (BigQuery or local)
- Uses consolidated alert system
- Shows validation metrics
- Updates in real-time

---

## Best Practices

### 1. Use Auto Mode by Default
```bash
python run_daily_update.py  # Let system decide
```

### 2. Set Appropriate Model Age Threshold
```bash
# Conservative (retrain weekly)
python run_daily_update.py --max-model-age 7

# Relaxed (retrain monthly)
python run_daily_update.py --max-model-age 30
```

### 3. Monitor Performance
```bash
# Check model status before running
python orchestrator/model_checker.py

# Then run
python run_daily_update.py
```

### 4. Schedule Daily Runs
```bash
# Cron job (daily at 6 AM)
0 6 * * * cd /path/to/RFP && python run_daily_update.py >> logs/daily_update.log 2>&1
```

---

## Troubleshooting

### Models Not Found

```bash
# Check status
python orchestrator/model_checker.py

# Force training
python run_pipeline.py --workflow training
```

### Inference Fails

```bash
# Use auto mode to detect issue
python run_pipeline.py --workflow auto

# Or run full workflow
python run_pipeline.py --workflow full
```

### BigQuery Errors

```bash
# Use local storage
python run_daily_update.py --local

# Or disable in config
# configs/bigquery_config.yaml: enabled: false
```

### Performance Degradation

The system auto-detects this in monitoring! Just run:
```bash
python run_daily_update.py
# Monitoring will trigger retraining automatically
```

---

## Summary

### ✅ Simplest Workflow (Recommended)

```bash
python run_daily_update.py
```

This single command:
- ✅ Detects if models exist
- ✅ Checks if models are fresh
- ✅ Trains if needed
- ✅ Generates predictions
- ✅ Monitors performance
- ✅ Auto-retrains if degraded

### ✅ LangGraph Orchestrates Everything

- Single graph builder: `orchestrator/graph.py::build_complete_graph()`
- All workflows route through LangGraph
- Conditional routing based on state
- Automatic retraining loops
- Zero subprocess calls

### ✅ Production Ready

The system is fully consolidated, tested, and ready for production deployment!

---

**For more details:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [FINAL_STATUS.md](FINAL_STATUS.md) - Production readiness status
- [TEST_RESULTS.md](TEST_RESULTS.md) - Test verification
