# System Architecture - LangGraph Orchestration

## Overview

The Market Regime Forecasting System uses **LangGraph as the central orchestrator** for all workflows. Every operation flows through a unified state graph with conditional routing.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    ENTRY POINTS                                  │
├─────────────────────────────────────────────────────────────────┤
│  run_pipeline.py          │  run_daily_update.py                │
│  (training/inference/full)│  (daily operations)                 │
└──────────────┬────────────┴──────────────┬──────────────────────┘
               │                            │
               └──────────┬─────────────────┘
                          │
                          ▼
         ┌────────────────────────────────────────┐
         │   orchestrator/graph.py                │
         │   build_complete_graph()               │
         │                                        │
         │   SINGLE LANGGRAPH ORCHESTRATOR        │
         │   (All workflows route through here)   │
         └────────────────┬───────────────────────┘
                          │
         ┌────────────────┴───────────────────┐
         │                                    │
         │   LangGraph StateGraph             │
         │   - Unified state management       │
         │   - Conditional routing            │
         │   - Error aggregation              │
         │   - Status tracking                │
         │                                    │
         └────────────────┬───────────────────┘
                          │
         ┌────────────────┴───────────────────┐
         │                                    │
    ┌────▼────┐                         ┌────▼────┐
    │ TRAINING│                         │INFERENCE│
    │ WORKFLOW│                         │WORKFLOW │
    └────┬────┘                         └────┬────┘
         │                                    │
         ▼                                    ▼
  ┌──────────────┐                    ┌──────────────┐
  │   cleanup    │                    │   cleanup    │
  └──────┬───────┘                    └──────┬───────┘
         │                                    │
  ┌──────▼───────┐                    ┌──────▼───────┐
  │    fetch     │                    │  inference   │
  └──────┬───────┘                    └──────┬───────┘
         │                                    │
  ┌──────▼───────┐                    ┌──────▼───────┐
  │   engineer   │                    │    alerts    │
  └──────┬───────┘                    └──────┬───────┘
         │                                    │
  ┌──────▼───────┐                    ┌──────▼───────┐
  │    select    │                    │  validation  │
  └──────┬───────┘                    └──────┬───────┘
         │                                    │
  ┌──────▼───────┐                    ┌──────▼───────┐
  │   cluster    │                    │  monitoring  │
  └──────┬───────┘                    └──────┬───────┘
         │                                    │
  ┌──────▼───────┐                           │
  │   classify   │                    ┌──────▼───────┐
  └──────┬───────┘                    │ needs_retrain│
         │                             │   == true?   │
  ┌──────▼───────┐                    └──────┬───────┘
  │   forecast   │                           │
  └──────┬───────┘                    ┌──────▼───────┐
         │                             │   → fetch    │
         │                             │  (retrain)   │
  ┌──────▼───────┐                    └──────────────┘
  │  → inference │
  │ (if full wf) │
  └──────────────┘
```

## Core Components

### 1. Centralized Orchestrator

**File:** [orchestrator/graph.py](orchestrator/graph.py:380)

**Function:** `build_complete_graph()`

**Responsibilities:**
- Build unified StateGraph with ALL nodes (training + inference)
- Define conditional routing logic
- Manage workflow transitions
- Handle retraining loops

**Key Features:**
- Single source of truth for workflow definitions
- Supports 3 workflow types: training, inference, full
- Automatic routing based on state
- Checkpointing for state persistence

### 2. Unified State Schema

**File:** [orchestrator/state.py](orchestrator/state.py:37)

**Class:** `PipelineState` (TypedDict)

**State Fields:**
```python
# Workflow control
workflow_type: "training" | "inference" | "full"

# Training stages
skip_fetch, skip_engineer, skip_select, skip_cluster, skip_classify, skip_forecast

# Inference stages
skip_inference, skip_alerts, skip_validation, skip_monitoring

# Status tracking (per stage)
fetch_status, engineer_status, select_status, ...
inference_status, alerts_status, validation_status, monitoring_status

# Routing flags
needs_retraining, abort_pipeline, retry_stage

# Results
regime_forecast_id, alert_result, validation_result, monitoring_result
```

### 3. Training Workflow Nodes

**File:** [orchestrator/nodes.py](orchestrator/nodes.py:1)

**Nodes:**
1. `cleanup_node` - Clean workspace
2. `fetch_node` - Fetch latest market data (data_agent.fetcher)
3. `engineer_node` - Engineer features (data_agent.engineer)
4. `select_node` - Select features via PCA+mRMR (data_agent.selector)
5. `cluster_node` - HMM regime clustering (clustering_agent)
6. `classify_node` - Train regime classifier (classification_agent)
7. `forecast_node` - Train forecasting models (forecasting_agent)

### 4. Inference/Monitoring Workflow Nodes

**File:** [orchestrator/inference_nodes.py](orchestrator/inference_nodes.py:1)

**Nodes:**
1. `inference_node` - Generate regime predictions (orchestrator.inference)
2. `alerts_node` - Detect regime shifts (orchestrator.alerts)
3. `validation_node` - SMAPE-based validation (data_agent.validator)
4. `monitoring_node` - Performance monitoring (orchestrator.monitoring)

### 5. Entry Points

#### Main Pipeline

**File:** [run_pipeline.py](run_pipeline.py:1)

**Usage:**
```bash
# Training only
python run_pipeline.py --workflow training

# Inference only
python run_pipeline.py --workflow inference

# Complete workflow (training + inference + monitoring)
python run_pipeline.py --workflow full

# With stage skipping
python run_pipeline.py --workflow training --skip-fetch --skip-engineer
```

**How it works:**
1. Creates initial state with `create_initial_state(workflow_type=...)`
2. Calls `build_complete_graph()` to get unified LangGraph
3. Invokes graph with state
4. LangGraph routes through nodes based on `workflow_type` in state

#### Daily Operations

**File:** [run_daily_update.py](run_daily_update.py:1)

**Usage:**
```bash
# Daily update workflow
python run_daily_update.py

# With automatic retraining
python run_daily_update.py --retrain-if-needed
```

**How it works:**
1. Creates state with `workflow_type="inference"`
2. Uses same `build_complete_graph()` as main pipeline
3. LangGraph automatically routes to inference workflow
4. Monitors performance and recommends retraining if needed

## Workflow Routing Logic

### Conditional Routing

**After cleanup:**
```python
if workflow_type == "training":
    → fetch (start training workflow)
elif workflow_type == "inference":
    → inference (start inference workflow)
else:  # full
    → fetch (training first, then inference)
```

**After training (forecast node):**
```python
if workflow_type == "full":
    → inference (continue to inference workflow)
else:
    → END
```

**After monitoring:**
```python
if needs_retraining and workflow_type == "full":
    → fetch (restart training workflow)
else:
    → END
```

## Storage Integration

All modules use storage abstraction:

```python
from data_agent.storage import get_storage

storage = get_storage()  # Auto-detects BigQuery or local
```

**Storage-aware modules:**
- `orchestrator/inference.py` - Saves forecasts to BigQuery
- `orchestrator/alerts.py` - Reads forecasts from storage
- `data_agent/validator.py` - Validates against actual data in storage
- `orchestrator/monitoring.py` - Reads validation metrics from storage

## Workflow Examples

### Example 1: Daily Operations

```bash
python run_daily_update.py
```

**Execution flow:**
1. Entry: `run_daily_update.py`
2. Creates state: `workflow_type="inference"`, `skip_cleanup=True`
3. LangGraph routes: cleanup → inference → alerts → validation → monitoring
4. Monitoring checks performance, sets `needs_retraining` flag if needed
5. LangGraph routes: → END (prints retraining recommendation)

### Example 2: Full Training + Inference

```bash
python run_pipeline.py --workflow full
```

**Execution flow:**
1. Entry: `run_pipeline.py`
2. Creates state: `workflow_type="full"`
3. LangGraph routes: cleanup → fetch → engineer → select → cluster → classify → forecast
4. After forecast: routes to inference (because workflow_type == "full")
5. LangGraph continues: inference → alerts → validation → monitoring
6. Monitoring checks: if `needs_retraining=True`, routes back to fetch
7. Otherwise: → END

### Example 3: Training Only

```bash
python run_pipeline.py --workflow training --skip-fetch
```

**Execution flow:**
1. Entry: `run_pipeline.py`
2. Creates state: `workflow_type="training"`, `skip_fetch=True`
3. LangGraph routes: cleanup → fetch (skipped) → engineer → ... → forecast
4. After forecast: → END (no inference because workflow_type != "full")

## Key Benefits

### 1. Single Source of Truth
- One graph definition in `orchestrator/graph.py`
- All entry points use the same graph builder
- Consistent routing logic across all workflows

### 2. Transparent Orchestration
- LangGraph handles ALL workflow coordination
- No subprocess calls
- No shell script dependencies
- Clean state management

### 3. Flexibility
- Easy to add new nodes
- Simple to skip stages
- Conditional routing based on state
- Human-in-the-loop ready (nodes exist, just need to enable)

### 4. Observability
- Real-time state tracking
- Status per stage
- Error aggregation
- Complete execution history via checkpointer

### 5. Natural Integration
- Storage (BigQuery/local) is transparent
- Each agent wrapped as a node
- No "bigquery_" prefix pollution
- Clean, modular architecture

## File Organization

```
orchestrator/
├── graph.py                 # ⭐ CENTRAL ORCHESTRATOR
│   └── build_complete_graph()  # Single graph builder for ALL workflows
├── state.py                 # Unified state schema
├── nodes.py                 # Training workflow nodes
├── inference_nodes.py       # Inference/monitoring nodes
├── inference.py             # Inference pipeline logic
├── alerts.py                # Regime shift alerts
├── monitoring.py            # Performance monitoring
├── human_nodes.py           # Human-in-the-loop nodes (optional)
└── validation_nodes.py      # Validation checkpoints (optional)

# Entry points (both use orchestrator/graph.py)
run_pipeline.py              # Main entry point (training/inference/full)
run_daily_update.py          # Daily operations (inference workflow)

# Legacy (moved, not deleted)
scripts/legacy_workflows/
├── continuous_data_refresh.py    # Old subprocess-based workflow
├── run_full_inference.py         # Old inference script
└── old_run_pipeline.py           # Old test pipeline
```

## Summary

**Yes, LangGraph is the main orchestrator for everything.**

- ✅ All workflows go through `orchestrator/graph.py::build_complete_graph()`
- ✅ Unified state management via `PipelineState`
- ✅ Conditional routing based on `workflow_type` in state
- ✅ No subprocess calls, no shell scripts
- ✅ Single entry point: `run_pipeline.py` (or `run_daily_update.py` for daily ops)
- ✅ All agents wrapped as LangGraph nodes
- ✅ Storage abstraction transparent throughout

**The system achieves your goal:**
> "have a code run all the system when triggered which triggers langgraph to run each agent as intended"

LangGraph orchestrates ALL agents through unified workflows. 🎯
