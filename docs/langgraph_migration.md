# LangGraph Migration Complete

## Overview

The system has been migrated to a **unified LangGraph orchestration architecture**. All workflows are now coordinated through stateful graphs instead of subprocess calls.

## New Entry Points

### 1. `run_pipeline.py` - Main Orchestrator
**Unified entry point for all workflows**

```bash
# Full workflow (training + inference + monitoring)
python run_pipeline.py

# Training only (fetch → engineer → select → cluster → classify → forecast models)
python run_pipeline.py --workflow training

# Inference only (forecast features → engineer → predict regimes → monitor)
python run_pipeline.py --workflow inference

# Skip specific stages
python run_pipeline.py --skip-fetch --skip-engineer

# Single feature training
python run_pipeline.py --workflow training --mode single --single-daily GSPC
```

### 2. `run_daily_update.py` - Daily Operations
**Simplified daily workflow for production use**

```bash
# Daily update (fetch latest data → forecast → alerts → validate → monitor)
python run_daily_update.py

# With automatic retraining if performance degrades
python run_daily_update.py --retrain-if-needed
```

## Architecture Changes

### Before (Subprocess-based)
```
continuous_data_refresh.py
├── subprocess: data_agent.fetcher
├── subprocess: run_full_inference.py
├── subprocess: orchestrator.alerts
├── subprocess: data_agent.validator
└── subprocess: orchestrator.monitoring
```

### After (LangGraph-based)
```
run_pipeline.py / run_daily_update.py
└── LangGraph StateGraph
    ├── Node: fetch_node (data_agent.fetcher)
    ├── Node: engineer_node (data_agent.engineer)
    ├── Node: select_node (data_agent.selector)
    ├── Node: cluster_node (clustering_agent)
    ├── Node: classify_node (classification_agent)
    ├── Node: forecast_node (forecasting_agent)
    ├── Node: inference_node (orchestrator.inference)
    ├── Node: alerts_node (orchestrator.alerts)
    ├── Node: validation_node (data_agent.validator)
    └── Node: monitoring_node (orchestrator.monitoring)
```

## New Orchestrator Structure

```
orchestrator/
├── state.py                 # Shared state schema (training + inference)
├── graph.py                 # Training workflow graph
├── nodes.py                 # Training workflow nodes (fetch, engineer, select, cluster, classify, forecast)
├── inference_nodes.py       # Inference/monitoring nodes (inference, alerts, validation, monitoring)
├── inference.py             # Inference pipeline wrapper (forecast features → regimes)
├── alerts.py                # Regime shift alert system
├── monitoring.py            # Performance monitoring & retraining agent
├── human_nodes.py           # Human-in-the-loop review nodes
└── validation_nodes.py      # Validation checkpoint nodes
```

## Workflow Types

### 1. Training Workflow
**Purpose:** Train all models from scratch

**Stages:**
1. Cleanup - Clear old outputs
2. Fetch - Download latest market data
3. Engineer - Create derived features
4. Select - PCA + correlation + mRMR selection
5. Cluster - HMM regime detection
6. Classify - Random Forest regime classifier
7. Forecast - Train ensemble forecasters (Prophet, ARIMA, XGBoost, NeuralForecast)

**When to use:**
- Initial setup
- Major model updates
- Performance degradation detected

**Command:**
```bash
python run_pipeline.py --workflow training
```

### 2. Inference Workflow
**Purpose:** Generate regime predictions and monitor performance

**Stages:**
1. Inference - Forecast raw features → engineer → predict regimes
2. Alerts - Check for regime shift alerts
3. Validation - SMAPE-based feature validation
4. Monitoring - Performance check & retraining decision

**When to use:**
- Daily operations
- After training to test predictions

**Command:**
```bash
python run_pipeline.py --workflow inference
# OR
python run_daily_update.py
```

### 3. Full Workflow
**Purpose:** Complete end-to-end training + inference

**Stages:**
- All training stages (1-7)
- All inference stages (1-4)
- Conditional routing: retrains if performance degrades

**When to use:**
- Development/testing
- Automated CI/CD pipelines

**Command:**
```bash
python run_pipeline.py --workflow full
```

## Key Benefits

### 1. Unified State Management
- All stages share `PipelineState` TypedDict
- Status tracking across all nodes
- Conditional routing based on state
- Error aggregation and reporting

### 2. Modularity
- Each agent is a standalone node
- Easy to skip/enable stages
- Human-in-the-loop support ready
- Parallel execution possible

### 3. Observability
- Real-time progress tracking
- Stage-by-stage metrics
- Error handling per node
- Complete execution history

### 4. Simplicity
- Single entry point (`run_pipeline.py`)
- Single daily command (`run_daily_update.py`)
- No subprocess management
- No shell script dependencies

## Deprecated Files

The following files are now **obsolete** and can be removed:

### Root Level
- `continuous_data_refresh.py` - Replaced by `run_daily_update.py`
- `run_full_inference.py` - Logic moved to `orchestrator/inference.py`

### Scripts Folder
- `scripts/run_pipeline.py` - Old test version, use root `run_pipeline.py`

**Do NOT remove:**
- `train_all_models.py` - Still useful for standalone model training

## Storage Integration

### BigQuery Integration
All modules use storage abstraction:

```python
from data_agent.storage import get_storage

storage = get_storage()  # Returns BigQueryStorage or LocalStorage
```

**Modules with BigQuery support:**
- `orchestrator/inference.py` - Saves forecasts to BigQuery
- `orchestrator/alerts.py` - Reads forecasts from storage
- `data_agent/validator.py` - Validates forecasts from storage
- `orchestrator/monitoring.py` - Monitors metrics from storage

## Migration Checklist

- [x] Create unified state schema (`orchestrator/state.py`)
- [x] Add inference/monitoring nodes (`orchestrator/inference_nodes.py`)
- [x] Update inference module for BigQuery (`orchestrator/inference.py`)
- [x] Create main entry point (`run_pipeline.py`)
- [x] Create daily workflow (`run_daily_update.py`)
- [x] Update README with Quick Start
- [x] Document LangGraph architecture
- [ ] Test full workflow end-to-end
- [ ] Remove obsolete files
- [ ] Update CI/CD to use new entry points

## Next Steps

1. **Test the system:**
   ```bash
   # Test inference workflow
   python run_daily_update.py
   ```

2. **Update automation:**
   - Replace `continuous_data_refresh.py` with `run_daily_update.py` in cron/scheduler
   - Update deployment scripts

3. **Clean up:**
   ```bash
   # Remove obsolete files
   rm continuous_data_refresh.py
   rm run_full_inference.py
   rm scripts/run_pipeline.py
   ```

## Support

For issues or questions:
- Check `orchestrator/state.py` for available state fields
- See `orchestrator/nodes.py` and `orchestrator/inference_nodes.py` for node implementations
- Run with `--help` for command-line options
