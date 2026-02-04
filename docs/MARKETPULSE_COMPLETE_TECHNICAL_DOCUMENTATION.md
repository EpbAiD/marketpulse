# MarketPulse: Complete Technical Documentation

**Version:** 1.0
**Last Updated:** January 30, 2026
**Authors:** Development Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Purpose & Value Proposition](#2-system-purpose--value-proposition)
3. [Architecture Overview](#3-architecture-overview)
4. [Component Deep Dive](#4-component-deep-dive)
5. [Data Flow & Pipeline](#5-data-flow--pipeline)
6. [Configuration Reference](#6-configuration-reference)
7. [Hybrid Cloud Architecture](#7-hybrid-cloud-architecture)
8. [Issues Encountered & Solutions](#8-issues-encountered--solutions)
9. [Technical Learnings](#9-technical-learnings)
10. [Deployment & Operations](#10-deployment--operations)
11. [Performance Metrics](#11-performance-metrics)
12. [Security & Credentials](#12-security--credentials)
13. [Future Enhancements](#13-future-enhancements)

---

## 1. Executive Summary

### What is MarketPulse?

MarketPulse is an **autonomous, multi-agent regime intelligence platform** that predicts market regime shifts up to 10 trading days in advance. It combines:

- **22 macroeconomic indicators** (equities, volatility, yields, commodities, macro data)
- **Neural ensemble forecasting** (NBEATSx, NHITS, PatchTST)
- **Hidden Markov Model clustering** for regime identification
- **Random Forest classification** for regime prediction
- **LangGraph orchestration** for intelligent workflow management

### Key Performance Metrics

| Metric | Value |
|--------|-------|
| Classification Accuracy | 98.4% |
| Average Forecast Error (SMAPE) | 3.38% |
| Daily Inference Time | <50 seconds |
| Training Time (full) | 75-90 minutes |
| Historical Data | 35 years (1990-2026) |

### System Highlights

- **Hybrid Architecture**: GitHub Actions for orchestration, Cloud Run for GPU training
- **Intelligent Retraining**: Auto-detects stale models and trains only what's needed
- **Incremental Training**: Memory-efficient one-feature-at-a-time training with immediate git commits
- **Production Ready**: Scheduled daily at 6 AM EST with full monitoring

---

## 2. System Purpose & Value Proposition

### 2.1 Who Is This For?

**Primary Users:**
- **Quantitative Analysts**: Use regime forecasts for portfolio allocation decisions
- **Risk Managers**: Monitor regime shifts for risk adjustment
- **Algorithmic Traders**: Incorporate regime signals into trading strategies
- **Financial Researchers**: Study market regime dynamics and transitions

**Secondary Users:**
- **Portfolio Managers**: High-level regime context for investment decisions
- **Market Strategists**: Understand current market environment

### 2.2 Problem Statement

Traditional market analysis often fails because:

1. **Reactive, not predictive**: Most tools identify regimes after they occur
2. **Single-indicator focus**: Miss the interplay of multiple factors
3. **Manual intervention required**: No automated detection of changing conditions
4. **Siloed data sources**: Difficulty integrating equities, volatility, yields, and macro data

### 2.3 Our Solution

MarketPulse addresses these challenges by:

1. **Predicting 10 days ahead**: Neural ensembles forecast raw features, then classify into regimes
2. **Multi-factor approach**: 22 indicators across 5 asset classes synthesized into regime signal
3. **Fully autonomous**: Scheduled daily execution with intelligent retraining
4. **Unified platform**: Single system integrating all data sources and models

### 2.4 Value Delivered

| Capability | Benefit |
|------------|---------|
| 10-day forward regime prediction | Time to adjust positions before regime shifts |
| 98.4% classification accuracy | High confidence in regime identification |
| Automated daily updates | No manual intervention needed |
| Regime shift alerts | Immediate notification of changing conditions |
| Historical analysis | Backtest strategies across regime types |

### 2.5 Market Regimes Identified

The system identifies **3 distinct market regimes**:

| Regime | Characteristics | Typical Strategy |
|--------|-----------------|------------------|
| **Bull Market (Expansion)** | Rising indices, low volatility, positive momentum | Risk-on, equity overweight |
| **Bear Market (Compression)** | Falling indices, high volatility, negative momentum | Risk-off, defensive positioning |
| **Transitional (Consolidation)** | Range-bound, moderate volatility, uncertain direction | Neutral, wait for clarity |

---

## 3. Architecture Overview

### 3.1 High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MARKETPULSE PLATFORM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐     │
│  │   Yahoo     │   │    FRED     │   │   BigQuery  │   │   GitHub    │     │
│  │  Finance    │   │    API      │   │   Storage   │   │    Repo     │     │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘     │
│         │                 │                 │                 │             │
│         └────────┬────────┴────────┬────────┴────────┬────────┘             │
│                  │                 │                 │                      │
│         ┌────────▼─────────────────▼─────────────────▼────────┐             │
│         │              DATA AGENT (Python)                     │             │
│         │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │             │
│         │  │ Fetcher  │ │ Engineer │ │ Selector │ │Validator│ │             │
│         │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │             │
│         └────────────────────────┬────────────────────────────┘             │
│                                  │                                          │
│         ┌────────────────────────▼────────────────────────────┐             │
│         │            ORCHESTRATOR (LangGraph)                  │             │
│         │  ┌──────────────────────────────────────────────┐   │             │
│         │  │  State Machine: Training → Inference → Monitor│   │             │
│         │  └──────────────────────────────────────────────┘   │             │
│         └───────────┬───────────────────────┬─────────────────┘             │
│                     │                       │                               │
│    ┌────────────────▼──────┐   ┌───────────▼────────────────┐              │
│    │   CLUSTERING AGENT    │   │   CLASSIFICATION AGENT     │              │
│    │   (Hidden Markov)     │   │   (Random Forest)          │              │
│    │   - 3 Regimes         │   │   - 500 Trees              │              │
│    │   - Regime Labels     │   │   - 98.4% Accuracy         │              │
│    └───────────────────────┘   └────────────────────────────┘              │
│                     │                       │                               │
│    ┌────────────────▼───────────────────────▼───────────────┐              │
│    │              FORECASTING AGENT                          │              │
│    │   ┌─────────┐  ┌─────────┐  ┌───────────┐              │              │
│    │   │ NBEATSx │  │  NHITS  │  │ PatchTST  │              │              │
│    │   └─────────┘  └─────────┘  └───────────┘              │              │
│    │   22 Feature Models × 3 Neural Networks Each            │              │
│    └────────────────────────────────────────────────────────┘              │
│                                  │                                          │
│         ┌────────────────────────▼────────────────────────────┐             │
│         │                  OUTPUT LAYER                        │             │
│         │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │             │
│         │  │Dashboard │ │BigQuery  │ │ Alerts   │ │Markdown │ │             │
│         │  │Streamlit │ │ Tables   │ │  System  │ │  Logs   │ │             │
│         │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │             │
│         └─────────────────────────────────────────────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Hybrid Cloud Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         GITHUB ACTIONS (Orchestration)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Daily @ 6 AM EST                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  1. Data Fetch      → Yahoo Finance, FRED API                        │   │
│  │  2. Model Check     → intelligent_model_checker.py                   │   │
│  │  3. IF training:    → Trigger Cloud Run GPU job                      │   │
│  │  4. Inference       → Forecast + Classify + Predict                  │   │
│  │  5. Commit Results  → DAILY_PREDICTIONS.md, BigQuery                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ (Only when training needed)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLOUD RUN (GPU Training)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Job: marketpulse-training (us-central1, coms-452404)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Resources: 8 CPUs, 32GB Memory                                      │   │
│  │  Mode: Auto (detects which features need training)                   │   │
│  │                                                                       │   │
│  │  Incremental Training Loop:                                          │   │
│  │    FOR each feature needing training:                                │   │
│  │      1. Train NBEATSx + NHITS + PatchTST ensemble                   │   │
│  │      2. Calculate ensemble weights                                   │   │
│  │      3. Git commit + push immediately                                │   │
│  │      4. Clear memory, continue to next                               │   │
│  │                                                                       │   │
│  │  Output: Models committed to GitHub repo                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Data Flow Pipeline

```
EXTERNAL DATA SOURCES
        │
        ├── Yahoo Finance (18 daily features)
        │   └── GSPC, IXIC, DXY, UUP, VIX, VIX3M, VIX9D, TNX, GOLD, OIL, COPPER...
        │
        ├── FRED API (4 weekly/monthly features)
        │   └── NFCI (weekly), CPI, UNRATE, INDPRO (monthly)
        │
        └── Historical: 35 years (1990-01-01 to present)
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                    DATA AGENT: FETCHER                         │
│  - Download from APIs                                          │
│  - Clean (forward-fill, backward-fill)                         │
│  - Save to BigQuery raw_features table                         │
│  Output: 22 raw feature time series                            │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                    DATA AGENT: ENGINEER                        │
│  Transform each raw feature into:                              │
│  - Returns (1, 5, 10, 21, 63 day)                             │
│  - Realized Volatility (10, 20, 60, 120, 252 day rolling)     │
│  - Z-Scores (63, 126, 252 day rolling)                        │
│  - Drawdowns (63, 126, 252 day from peak)                     │
│  - YoY (252 day), MoM (21 day)                                │
│  Output: 294 engineered features                               │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                    DATA AGENT: SELECTOR                        │
│  Three-method ensemble selection:                              │
│  1. PCA (97% variance threshold)                               │
│  2. Correlation Clustering (0.85 threshold)                    │
│  3. mRMR (top 25, redundancy weight 0.5)                      │
│  Final: Intersection of methods (2+ agreement)                 │
│  Output: 31 optimal features                                   │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                 CLUSTERING AGENT: HMM                          │
│  - GaussianHMM with 3 latent states                           │
│  - 2000 max iterations                                         │
│  - Input: 31 selected features (standardized)                  │
│  Output: Regime labels (0, 1, 2) for each historical date     │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│              CLASSIFICATION AGENT: RANDOM FOREST               │
│  - 500 trees, balanced class weights                           │
│  - Train on 80% historical data                                │
│  - Input: 31 features → Output: Regime prediction              │
│  Accuracy: 98.4% on test set                                   │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│              FORECASTING AGENT: NEURAL ENSEMBLE                │
│  For each of 22 raw features:                                  │
│    ├── NBEATSx (interpretable blocks)                         │
│    ├── NHITS (hierarchical interpolation)                     │
│    └── PatchTST (transformer patches)                         │
│  Ensemble: Weighted average (weights learned from validation) │
│  Output: 10-day ahead forecast per feature                     │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                    INFERENCE PIPELINE                          │
│  1. Forecast 22 raw features → 10 days ahead                  │
│  2. Engineer features from forecasts                           │
│  3. Predict regimes using Random Forest                        │
│  4. Filter to 10 trading days (exclude weekends/holidays)     │
│  Output: 10 trading day regime predictions + confidence        │
└───────────────────────────────────────────────────────────────┘
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│                    OUTPUT & MONITORING                         │
│  - BigQuery: regime_forecasts table                            │
│  - DAILY_PREDICTIONS.md: Human-readable log                    │
│  - Dashboard: Streamlit visualization                          │
│  - Alerts: Regime shift detection                              │
│  - Validation: SMAPE-based forecast accuracy                   │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. Component Deep Dive

### 4.1 Data Agent (`/data_agent/`)

#### 4.1.1 Fetcher Module

**File:** `data_agent/fetcher.py`

**Purpose:** Download and clean market data from external sources

**Key Functions:**
```python
def fetch_yahoo(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch equity/commodity prices from Yahoo Finance"""

def fetch_fred(code: str, start: str, end: str) -> pd.DataFrame:
    """Fetch macro indicators from FRED API"""

def run_fetcher(cfg_path: str, use_bigquery: bool) -> Dict:
    """Main execution - fetch all configured features"""
```

**Data Sources:**

| Source | Features | Cadence |
|--------|----------|---------|
| Yahoo Finance | GSPC, IXIC, DXY, UUP, VIX, VIX3M, VIX9D, TNX, GOLD, OIL, COPPER | Daily |
| FRED | DGS10, DGS2, DGS3MO, DFF, HY_YIELD, IG_YIELD, T10Y2Y | Daily |
| FRED | NFCI | Weekly |
| FRED | CPI, UNRATE, INDPRO | Monthly |

**Cleaning Pipeline:**
1. Download raw data
2. Forward-fill missing values
3. Backward-fill remaining NaN at start
4. Generate missingness diagnostics
5. Alert if >5% missing

#### 4.1.2 Engineer Module

**File:** `data_agent/engineer.py`

**Purpose:** Transform 22 raw features into 294 engineered features

**Transformations Applied:**

| Type | Windows | Formula | Count per Feature |
|------|---------|---------|-------------------|
| Raw Value | - | Close price | 1 |
| Returns | 1, 5, 10, 21, 63 | (P_t - P_{t-n}) / P_{t-n} | 5 |
| Realized Vol | 10, 20, 60, 120, 252 | Rolling std of returns | 5 |
| Z-Score | 63, 126, 252 | (x - rolling_mean) / rolling_std | 3 |
| Drawdown | 63, 126, 252 | (x - rolling_max) / rolling_max | 3 |
| YoY | 252 | Year-over-year change | 1 |
| MoM | 21 | Month-over-month change | 1 |

**Total:** ~13 derived features per raw feature × 22 features = 294 engineered features

**Key Implementation for Inference:**
```python
def engineer_forecasted_features(forecasted_raw_df, cfg_path, lookback_days=365):
    """
    Engineer features from forecasted raw values.

    Critical: Combines historical data (lookback) + forecasted values
    to enable proper rolling window calculations on forecast dates.
    """
    # Load historical data for each feature
    # Concatenate: historical + forecast
    # Apply same engineering transformations
    # Return only forecast date rows
```

#### 4.1.3 Selector Module

**File:** `data_agent/selector.py`

**Purpose:** Select optimal 31 features from 294 using ensemble methods

**Three-Method Selection:**

1. **PCA (Principal Component Analysis)**
   - Variance threshold: 97%
   - Typically retains 30-35 principal components
   - Returns features with highest PC loadings

2. **Correlation Clustering**
   - Distance: 1 - |correlation|
   - Linkage: Average
   - Threshold: 0.85
   - Selects representative from each cluster

3. **mRMR (Minimum Redundancy Maximum Relevance)**
   - Target: First principal component
   - Top K: 25 features
   - Redundancy weight: 0.5
   - Balances predictive power vs redundancy

**Final Selection Logic:**
```python
final_features = (pca_set & corr_set) | (corr_set & mrmr_set) | (pca_set & mrmr_set)
# Features must be selected by at least 2 methods
```

### 4.2 Clustering Agent (`/clustering_agent/`)

**File:** `clustering_agent/clustering.py`

**Purpose:** Identify market regimes using Hidden Markov Models

**Model Configuration:**
```python
hmm_model = GaussianHMM(
    n_components=3,      # 3 market regimes
    covariance_type='full',
    n_iter=2000,
    random_state=42
)
```

**Regimes Identified:**

| Regime ID | Name | Characteristics |
|-----------|------|-----------------|
| 0 | Bull Market | High returns, low volatility, positive momentum |
| 1 | Bear Market | Negative returns, high volatility, risk-off |
| 2 | Transitional | Range-bound, moderate volatility, uncertain |

**Output:** Regime label for each historical date in `cluster_assignments.parquet`

### 4.3 Classification Agent (`/classification_agent/`)

**File:** `classification_agent/classifier.py`

**Purpose:** Train Random Forest to predict regimes from features

**Model Configuration:**
```python
classifier = RandomForestClassifier(
    n_estimators=500,
    class_weight='balanced_subsample',
    random_state=42,
    n_jobs=-1
)
```

**Training Process:**
1. Load aligned dataset (31 selected features)
2. Load regime labels from HMM
3. Split 80/20 stratified train/test
4. Train Random Forest
5. Evaluate accuracy (target: >95%)

**Key Function - Trading Day Filter:**
```python
def filter_trading_days(df, target_trading_days=10):
    """
    Filter predictions to trading days only.
    Removes weekends and US Federal holidays.
    """
    # Remove Saturday (5) and Sunday (6)
    df = df[df['ds'].dt.dayofweek < 5]

    # Remove US Federal holidays
    holidays = USFederalHolidayCalendar().holidays(...)
    df = df[~df['ds'].isin(holidays)]

    return df.head(target_trading_days)
```

### 4.4 Forecasting Agent (`/forecasting_agent/`)

**File:** `forecasting_agent/forecaster.py`

**Purpose:** Forecast each raw feature 10 days ahead using neural ensemble

**Neural Models (per feature):**

| Model | Description | Strengths |
|-------|-------------|-----------|
| NBEATSx | Basis expansion with exogenous variables | Interpretable, handles seasonality |
| NHITS | Hierarchical interpolation sampling | Multi-scale patterns, efficient |
| PatchTST | Transformer with patched time series | Long-range dependencies, robust |

**Ensemble Weighting:**
```python
def calculate_ensemble_weights(predictions, actuals, metric='smape'):
    """
    Calculate ensemble weights from validation performance.

    1. Evaluate each model on validation set
    2. Convert errors to weights (inverse of error)
    3. Normalize to sum to 1.0
    """
    errors = {model: calculate_error(pred, actuals) for model, pred in predictions}
    weights = {model: 1/error for model, error in errors.items()}
    total = sum(weights.values())
    return {model: w/total for model, w in weights.items()}
```

**Training Configuration by Cadence:**

| Cadence | Horizon | Val Size | Loss | Weight Metric |
|---------|---------|----------|------|---------------|
| Daily | 10 days | 90 days | MAE | SMAPE |
| Weekly | 2 weeks | 26 weeks | MAE | MAE |
| Monthly | 2 months | 12 months | MAE | SMAPE |

**Memory Management (Critical for Cloud Run):**
```python
# After training each model
if torch.cuda.is_available():
    torch.cuda.empty_cache()
elif hasattr(torch.mps, 'empty_cache'):
    torch.mps.empty_cache()
gc.collect()
```

### 4.5 Storage Layer (`/data_agent/storage/`)

**Pattern:** Factory + Strategy

```python
from data_agent.storage import get_storage

# Returns BigQueryStorage or LocalStorage based on flag
storage = get_storage(use_bigquery=True)
```

**BigQuery Tables:**

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| raw_features | Raw market data | timestamp, feature_name, cadence, value |
| engineered_features | Derived features | timestamp, base_feature, column_name, value |
| regime_forecasts | Predictions | forecast_id, predicted_date, regime, confidence |
| model_versions | Model metadata | feature_name, version, training_date |

**Credential Priority Chain:**
1. Streamlit Cloud secrets
2. GitHub Actions `GCP_CREDENTIALS` env var
3. Cloud Run Application Default Credentials
4. Local credentials file

### 4.6 Orchestrator (`/orchestrator/`)

**Pattern:** LangGraph State Machine

**State Schema:**
```python
class PipelineState(TypedDict):
    run_id: str
    workflow_type: Literal["training", "inference", "full", "auto"]

    # Skip flags
    skip_fetch: bool
    skip_engineer: bool
    skip_forecast: bool
    # ... etc

    # Selective training
    selective_features: Optional[List[str]]

    # Status tracking
    fetch_status: Dict
    forecast_status: Dict
    # ... etc
```

**Graph Flow:**
```
START → cleanup → fetch → engineer → select → cluster → classify → forecast
                                                                      ↓
                                    END ← monitoring ← validation ← inference
```

**Intelligent Model Checker:**
```python
def get_intelligent_recommendation():
    """
    Determine which components need retraining.

    Returns:
        {
            "workflow": "inference" | "full" | "partial",
            "features_to_train": ["VIX", "CPI", ...]
        }
    """
    # Check core models (HMM, RF) - threshold: 30 days
    # Check each feature model - threshold varies by cadence
    # Return recommendation
```

---

## 5. Data Flow & Pipeline

### 5.1 Training Workflow (Monthly or On-Demand)

**Duration:** 75-90 minutes

```
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 1: CLEANUP (10 seconds)                                       │
│ - Remove stale temporary files                                      │
│ - Preserve fresh models (checked by age)                           │
│ - Clear lightning_logs directory                                    │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 2: FETCH (5 minutes)                                          │
│ - Download 22 features from Yahoo Finance + FRED                   │
│ - Clean and impute missing values                                   │
│ - Save to BigQuery raw_features table                              │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 3: ENGINEER (3 minutes)                                       │
│ - Generate 294 engineered features from 22 raw                     │
│ - Rolling windows for volatility, z-scores, drawdowns              │
│ - Save to BigQuery engineered_features table                       │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 4: SELECT (1 minute)                                          │
│ - Run PCA, Correlation Clustering, mRMR                            │
│ - Select 31 optimal features                                        │
│ - Create aligned dataset for training                               │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 5: CLUSTER (2 minutes)                                        │
│ - Fit GaussianHMM with 3 states                                    │
│ - Generate regime labels for all historical dates                  │
│ - Save HMM model to outputs/models/hmm_model.joblib                │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 6: CLASSIFY (1 minute)                                        │
│ - Train Random Forest on selected features + regime labels         │
│ - Evaluate accuracy (target: >95%)                                  │
│ - Save RF model to outputs/models/regime_classifier.joblib         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STAGE 7: FORECAST (60-90 minutes)                                   │
│ - For each of 22 features:                                          │
│   - Train NBEATSx, NHITS, PatchTST                                 │
│   - Calculate ensemble weights on validation                        │
│   - Save model bundle + weights                                     │
│   - Git commit + push (if on Cloud Run)                            │
│   - Clear memory                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 Inference Workflow (Daily, <50 seconds)

```
┌────────────────────────────────────────────────────────────────────┐
│ STEP 1: CHECK MODELS (5 seconds)                                    │
│ - Run intelligent_model_checker                                     │
│ - Determine if training needed                                      │
│ - If yes, trigger Cloud Run training first                         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STEP 2: FETCH LATEST DATA (10 seconds)                              │
│ - Download today's data from APIs                                   │
│ - Update BigQuery raw_features                                      │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STEP 3: FORECAST RAW FEATURES (20 seconds)                          │
│ - Load trained ensemble for each feature                           │
│ - Generate 16 calendar day forecasts (to get 10 trading days)     │
│ - Apply ensemble weights                                            │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STEP 4: ENGINEER FORECASTS (5 seconds)                              │
│ - Combine historical data + forecasted values                      │
│ - Apply same transformations as training                           │
│ - Extract engineered features for forecast dates only              │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STEP 5: PREDICT REGIMES (5 seconds)                                 │
│ - Load Random Forest classifier                                     │
│ - Predict regime for each forecast date                            │
│ - Filter to 10 trading days                                         │
│ - Save to BigQuery regime_forecasts                                 │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│ STEP 6: POST-PROCESSING (5 seconds)                                 │
│ - Detect regime shifts vs previous forecast                        │
│ - Validate forecasts (SMAPE)                                        │
│ - Update DAILY_PREDICTIONS.md                                       │
│ - Commit and push results                                           │
└────────────────────────────────────────────────────────────────────┘
```

---

## 6. Configuration Reference

### 6.1 features_config.yaml

```yaml
# Forecast configuration by cadence

daily:
  horizon: 10              # Forecast 10 days ahead
  val_size: 90             # 90-day validation window
  nf_loss: mae             # NeuralForecast training loss
  ensemble:
    weight_metric: smape   # Metric for ensemble weights
    tie_breaker: mae       # Tie-breaker metric
    learn_on: val_last_h   # Learn weights on last horizon of val
    normalize_weights: true
  features:
    - GSPC
    - IXIC
    - DXY
    - UUP
    - VIX
    - VIX3M
    - VIX9D
    - TNX
    - DGS10
    - DGS2
    - DGS3MO
    - HY_YIELD
    - IG_YIELD
    - T10Y2Y
    - DFF
    - GOLD
    - OIL
    - COPPER

weekly:
  horizon: 2               # Forecast 2 weeks
  val_size: 26             # 26-week validation
  nf_loss: mae
  ensemble:
    weight_metric: mae
    tie_breaker: rmse
    learn_on: val_last_h
    normalize_weights: true
  features:
    - NFCI

monthly:
  horizon: 2               # Forecast 2 months
  val_size: 12             # 12-month validation
  nf_loss: mae
  ensemble:
    weight_metric: smape
    tie_breaker: mae
    learn_on: val_last_h
    normalize_weights: true
  features:
    - CPI
    - UNRATE
    - INDPRO
```

### 6.2 feature_policy.yaml

```yaml
# Feature engineering configuration

rolling_windows:
  volatility: [10, 20, 60, 120, 252]    # Days for realized vol
  zscore: [63, 126, 252]                # Days for z-score
  drawdown: [63, 126, 252]              # Days for drawdown

yoy_window: 252    # Trading days in year (for YoY)
mom_window: 21     # Trading days in month (for MoM)

return_horizons: [1, 5, 10, 21, 63]    # Multi-horizon returns

missingness_policy:
  imputation_method: "ffill_bfill"
  visualize: true
  threshold_alert_%: 5.0
```

### 6.3 bigquery_config.yaml

```yaml
bigquery:
  project_id: "regime01"
  dataset_id: "forecasting_pipeline"
  credentials_path: "regime01-b5321d26c433.json"
  location: "us-central1"

  tables:
    raw_features: "raw_features"
    engineered_features: "engineered_features"
    selected_features: "selected_features"
    forecast_results: "forecast_results"
    regime_forecasts: "regime_forecasts"
    cluster_assignments: "cluster_assignments"
    model_metrics: "model_metrics"
    model_versions: "model_versions"
    validation: "validation"
    pipeline_runs: "pipeline_runs"

  batch_size: 1000
  query_timeout: 300
  enable_cache: true
  cache_ttl: 3600
```

---

## 7. Hybrid Cloud Architecture

### 7.1 Design Philosophy

**Problem:** Neural network training requires significant compute resources (GPU/high memory) that exceed GitHub Actions limits.

**Solution:** Hybrid architecture where:
- **GitHub Actions** handles orchestration, data fetch, inference, and lightweight tasks
- **Cloud Run** handles GPU-intensive model training when needed

### 7.2 Component Responsibilities

| Task | Platform | Why |
|------|----------|-----|
| Data Fetching | GitHub Actions | Low compute, API calls |
| Feature Engineering | GitHub Actions | Pandas operations, moderate memory |
| Feature Selection | GitHub Actions | Scikit-learn, fast |
| HMM Clustering | GitHub Actions | Small model, fast training |
| RF Classification | GitHub Actions | CPU-efficient, <1 minute |
| Neural Network Training | Cloud Run | High memory, GPU acceleration |
| Inference | GitHub Actions | Load pre-trained models only |
| Monitoring & Alerts | GitHub Actions | Lightweight processing |

### 7.3 Cloud Run Configuration

**Job Definition:**
```yaml
Job Name: marketpulse-training
Project: coms-452404
Region: us-central1
Resources:
  - CPUs: 8
  - Memory: 32Gi
  - Timeout: 3600s (1 hour)
```

**Entrypoint Script (`cloud_run/entrypoint.sh`):**
```bash
#!/bin/bash
set -e

# Clone repo for git operations
cd /tmp
git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git" repo
cd repo

# Auto mode: detect which features need training
FEATURES_TO_TRAIN=$(python -c "
from orchestrator.intelligent_model_checker import get_intelligent_recommendation
rec = get_intelligent_recommendation()
print(','.join(rec.get('features_to_train', [])))
")

# Incremental training with immediate commits
python cloud_run/incremental_trainer.py \
    --config configs/features_config.yaml \
    --repo-dir /tmp/repo \
    --features "$FEATURES_TO_TRAIN"
```

### 7.4 Incremental Training Strategy

**Problem:** Training all 22 features at once causes OOM (out of memory) errors.

**Solution:** Train one feature at a time with immediate git commits.

```python
# cloud_run/incremental_trainer.py

def run_incremental_training(features, repo_dir):
    for feature in features:
        print(f"Training {feature}...")

        # Train single feature
        train_single_feature(feature)

        # Create version metadata
        create_version_metadata(feature, repo_dir)

        # Commit and push immediately
        commit_and_push_feature(feature, repo_dir)

        # Clear memory
        gc.collect()
        torch.cuda.empty_cache()
```

**Benefits:**
- Memory freed after each feature
- Progress preserved even if job times out
- Git history shows individual feature updates
- Resume capability (skips already-trained features)

---

## 8. Issues Encountered & Solutions

### 8.1 Cloud Run OOM Failures (Exit Code 137)

**Problem:** Cloud Run job killed with exit code 137 (OOM) when training multiple neural models.

**Root Cause:** Training all 22 feature models simultaneously consumed more memory than the 16GB allocation.

**Solution:**
1. Increased memory from 16GB to 32GB
2. Implemented incremental training (one feature at a time)
3. Added explicit memory cleanup after each feature
4. Immediate git commit after each feature (preserve progress)

**Code Changes:**
```python
# Before: Train all at once
for feature in all_features:
    train_feature(feature)
# Then commit all

# After: Train + commit incrementally
for feature in features_to_train:
    train_feature(feature)
    create_version_metadata(feature)
    commit_and_push_feature(feature)
    gc.collect()
    torch.cuda.empty_cache()
```

### 8.2 Wrong Forecast Dates (Predicting Past Instead of Future)

**Problem:** Forecasts showed dates like "2025-11-03 to 2025-11-17" instead of future dates when run in January 2026.

**Root Cause (Part 1):** The inference pipeline loaded ALL features with `cadence='daily'`, but monthly features (CPI, UNRATE, INDPRO) were stored with `cadence='monthly'` in BigQuery. This caused either no data to be returned or wrong data.

**Solution (Part 1):** Determine correct cadence from config BEFORE loading data.

```python
# Before (buggy):
for fname in feature_names:
    df = storage.load_raw_feature(fname, cadence='daily')  # Wrong for monthly!

# After (fixed):
for fname in feature_names:
    # Determine correct cadence from config
    feature_cadence = 'daily'
    for cad_name in ['daily', 'weekly', 'monthly']:
        if fname in config[cad_name].get('features', []):
            feature_cadence = cad_name
            break

    df = storage.load_raw_feature(fname, cadence=feature_cadence)
```

**Root Cause (Part 2):** Monthly FRED indicators (CPI, UNRATE, INDPRO) are released with 1-2 month lag. When the code calculated `forecast_start = last_date + 1 day`, it used the stale data's last date (December 2025) instead of today (January 2026).

**Solution (Part 2):** Detect stale data and use today's date as forecast start.

```python
# Calculate data age
data_age_days = (today - last_date).days

# Staleness thresholds by cadence
thresholds = {'monthly': 35, 'weekly': 10, 'daily': 3}

if data_age_days > thresholds[cadence]:
    # Data is stale - use today as forecast start
    forecast_start = today
    print(f"Data is {data_age_days} days old, using today as forecast start")
else:
    forecast_start = last_date + pd.Timedelta(days=1)
```

### 8.3 Missing Version Metadata Files

**Problem:** `intelligent_model_checker` couldn't detect newly trained models because `{feature}_versions.json` files were missing.

**Root Cause:** The incremental trainer created model bundles but didn't create the version metadata files that the model checker looked for.

**Solution:** Add automatic version metadata creation in `incremental_trainer.py`.

```python
def create_version_metadata(feature_name, repo_dir):
    """Create version metadata file for a feature if it doesn't exist."""
    version_file = f"outputs/forecasting/models/{feature_name}_versions.json"

    if os.path.exists(version_file):
        return  # Already exists

    # Get timestamp from ensemble file
    ensemble_file = f"outputs/forecasting/models/{feature_name}/{feature_name}_ensemble_v1.json"
    timestamp = datetime.now().isoformat()

    if os.path.exists(ensemble_file):
        with open(ensemble_file) as f:
            ensemble_data = json.load(f)
        timestamp = ensemble_data.get('timestamp', timestamp)

    # Create metadata
    version_data = {
        "versions": [{
            "version": 1,
            "created_at": timestamp,
            "status": "completed",
            "updated_at": timestamp,
            "metrics": {}
        }],
        "active_version": 1
    }

    with open(version_file, 'w') as f:
        json.dump(version_data, f, indent=2)
```

### 8.4 GCP Project Configuration Confusion

**Problem:** Commands failed with "project not found" or "permission denied" errors.

**Root Cause:** System uses TWO GCP projects:
- `regime01`: BigQuery data storage
- `coms-452404`: Cloud Run job execution

**Solution:** Explicit project specification in all gcloud commands.

```yaml
# In workflow files:
gcloud run jobs execute marketpulse-training \
    --region=us-central1 \
    --project=coms-452404  # Not regime01!
```

### 8.5 NumPy Type Serialization Errors

**Problem:** LangGraph state serialization failed with "cannot serialize numpy.int64" errors.

**Root Cause:** NumPy types (np.int64, np.float32) are not JSON/msgpack serializable.

**Solution:** Convert to Python native types in all nodes.

```python
# Before:
state["count"] = numpy_array.sum()  # Returns np.int64

# After:
state["count"] = int(numpy_array.sum())  # Python int
state["metric"] = float(numpy_metric)     # Python float
```

### 8.6 PyTorch 2.6+ Model Loading Issues

**Problem:** Loading saved NeuralForecast models failed with "weights_only" errors on PyTorch 2.6+.

**Root Cause:** PyTorch 2.6 changed default `torch.load()` to `weights_only=True` for security.

**Solution:** Patch torch.load temporarily when loading legacy models.

```python
try:
    nf = NeuralForecast.load(path=bundle_path)
except Exception as e:
    if "weights_only" in str(e):
        # Patch for PyTorch 2.6+ compatibility
        original_load = torch.load
        def patched_load(*args, **kwargs):
            kwargs['weights_only'] = False
            return original_load(*args, **kwargs)
        torch.load = patched_load
        try:
            nf = NeuralForecast.load(path=bundle_path)
        finally:
            torch.load = original_load  # Restore original
    else:
        raise
```

---

## 9. Technical Learnings

### 9.1 Architecture Learnings

| Learning | Description |
|----------|-------------|
| **Hybrid is better than monolithic** | Splitting training to Cloud Run solved resource constraints without overcomplicating the system |
| **Incremental > batch** | Training one feature at a time with commits is more resilient than batch training |
| **State machine for workflows** | LangGraph provides clean orchestration with checkpoints and recovery |
| **Storage abstraction pays off** | BigQuery/local switching via factory pattern made development much easier |

### 9.2 ML Pipeline Learnings

| Learning | Description |
|----------|-------------|
| **Ensemble beats single model** | Weighted ensemble of NBEATSx+NHITS+PatchTST outperforms any single model |
| **Validation-based weights** | Learning ensemble weights from validation data produces better results than equal weighting |
| **Feature selection matters** | 31 selected features perform as well as 294, with much faster inference |
| **Cadence-aware processing** | Different data frequencies (daily/weekly/monthly) need different handling throughout pipeline |

### 9.3 Operations Learnings

| Learning | Description |
|----------|-------------|
| **Immediate commits are insurance** | Committing after each feature preserves progress if job fails |
| **Staleness detection is critical** | Auto-detecting stale data prevents wrong predictions |
| **Model versioning is essential** | Version metadata enables intelligent retraining decisions |
| **Memory management is non-trivial** | Explicit garbage collection and cache clearing prevents OOM |

### 9.4 Code Quality Learnings

| Learning | Description |
|----------|-------------|
| **Type serialization matters** | NumPy types break JSON serialization - always convert to Python natives |
| **Configuration over code** | YAML configs for features/cadences/thresholds enable easy modification |
| **Defensive coding for APIs** | External APIs (Yahoo, FRED) can fail - always have retry logic and fallbacks |
| **Logging is debugging** | Detailed logging (data dates, model ages, etc.) made issue diagnosis possible |

---

## 10. Deployment & Operations

### 10.1 GitHub Actions Workflows

**Daily Forecast (Scheduled):**
```yaml
name: Daily Market Regime Forecast

on:
  schedule:
    - cron: '0 11 * * *'  # 6 AM EST = 11 AM UTC
  workflow_dispatch:      # Manual trigger

jobs:
  forecast:
    runs-on: ubuntu-latest
    timeout-minutes: 360

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Check if training needed
        run: python -m orchestrator.intelligent_model_checker --json > status.json

      - name: Trigger Cloud Run (if needed)
        if: training_needed
        run: |
          gcloud run jobs execute marketpulse-training \
            --region=us-central1 \
            --project=coms-452404 \
            --update-env-vars="MODE=auto" \
            --wait
          git pull origin main  # Get newly trained models

      - name: Run inference
        run: python run_pipeline.py --workflow inference

      - name: Commit results
        run: |
          git add DAILY_PREDICTIONS.md
          git commit -m "Daily forecast update"
          git push
```

### 10.2 Local Development

```bash
# Clone and setup
git clone https://github.com/EpbAiD/marketpulse.git
cd marketpulse
pip install -r requirements.txt

# Set up credentials
export GOOGLE_APPLICATION_CREDENTIALS="path/to/credentials.json"

# Run full training
python run_pipeline.py --workflow training

# Run inference only
python run_pipeline.py --workflow inference

# Run auto mode (detect what's needed)
python run_pipeline.py --workflow auto

# Train specific features
python run_pipeline.py --workflow full --selective-features VIX,GSPC

# Skip stages
python run_pipeline.py --skip-fetch --skip-engineer
```

### 10.3 Model Storage

All models are stored in the GitHub repository:

```
outputs/
├── models/
│   ├── hmm_model.joblib           # HMM clustering model
│   └── regime_classifier.joblib   # Random Forest classifier
│
└── forecasting/
    └── models/
        ├── GSPC/
        │   ├── nf_bundle_v1/       # NeuralForecast bundle
        │   └── GSPC_ensemble_v1.json
        ├── GSPC_versions.json      # Version metadata
        ├── VIX/
        │   └── ...
        └── ...
```

**Why store in repo?**
- Version controlled with git history
- No artifact management needed
- Immediately available for inference
- Automatic backup

### 10.4 Dashboard

**URL:** https://marketpulsedashboard.streamlit.app

**Features:**
- Current regime + 10-day forecast
- Regime probability trends
- Feature contribution analysis
- Historical regime distribution

**Auto-updates** after each inference workflow

---

## 11. Performance Metrics

### 11.1 Model Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Classification Accuracy | 98.4% | On 15 years of data |
| Forecast Error (SMAPE) | 3.38% | Average across 18 daily features |
| Regime Confidence | 63-85% | Varies by market condition |

### 11.2 Runtime Performance

| Stage | Duration | Notes |
|-------|----------|-------|
| Data Fetch | 1-2 min | 22 features from APIs |
| Feature Engineering | 3 min | 294 derived features |
| Feature Selection | 1 min | PCA + mRMR + correlation |
| HMM Training | 2 min | 3-state model |
| RF Training | 1 min | 500 trees |
| Neural Training | 60-90 min | 22 features × 3 models |
| **Total Training** | **75-90 min** | |
| | | |
| **Daily Inference** | **<50 sec** | Load models + predict |

### 11.3 Data Volume

| Component | Size |
|-----------|------|
| Raw Features | ~155K rows (35 years × 22 features) |
| Engineered Features | ~655K rows |
| Model Files | ~5GB total |
| BigQuery Dataset | ~1GB |

---

## 12. Security & Credentials

### 12.1 Credential Management

**Priority Chain:**
1. Streamlit Cloud secrets (`st.secrets['gcp_service_account']`)
2. GitHub Actions secret (`GCP_CREDENTIALS` env var)
3. Cloud Run ADC (Application Default Credentials)
4. Local file (`regime01-b5321d26c433.json`)

**GitHub Actions Setup:**
```yaml
- name: Create credentials
  run: |
    echo '${{ secrets.GCP_CREDENTIALS }}' > /tmp/creds.json
    echo "GOOGLE_APPLICATION_CREDENTIALS=/tmp/creds.json" >> $GITHUB_ENV
```

### 12.2 Required Permissions

**BigQuery Service Account:**
- `bigquery.datasets.get`
- `bigquery.tables.get`
- `bigquery.tables.getData`
- `bigquery.tables.update`
- `bigquery.jobs.create`

**Cloud Run Service Account:**
- `run.jobs.run`
- `storage.objects.get` (for model artifacts)

### 12.3 Secrets Never Committed

The following are in `.gitignore`:
- `*.json` (credentials files)
- `.env`
- `.streamlit/secrets.toml`

---

## 13. Future Enhancements

### 13.1 Planned Improvements

| Enhancement | Description | Priority |
|-------------|-------------|----------|
| GPU Training | Use Cloud Run GPU instances for faster training | High |
| Regime Confidence Calibration | Improve probability estimates | Medium |
| Additional Features | Add more macro indicators (ISM, PMI) | Medium |
| Real-time Alerts | Push notifications for regime shifts | Medium |
| Backtesting Framework | Systematic strategy evaluation | Low |

### 13.2 Technical Debt

| Item | Description | Status |
|------|-------------|--------|
| Dashboard cadence fix | Load monthly features correctly | Pending |
| Test coverage | Add unit tests for all modules | Partial |
| Documentation | API documentation | Partial |
| Error recovery | More graceful failure handling | Ongoing |

### 13.3 Scalability Considerations

| Consideration | Current Limit | Mitigation |
|---------------|---------------|------------|
| GitHub Actions timeout | 6 hours | Cloud Run offloads training |
| BigQuery quota | 10TB/month | Incremental writes |
| Model storage | GitHub LFS limits | Compress models, archive old versions |

---

## Appendix A: File Structure

```
RFP/
├── data_agent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── fetcher.py            # Data fetching
│   ├── engineer.py           # Feature engineering
│   ├── selector.py           # Feature selection
│   ├── validator.py          # Forecast validation
│   ├── utils.py              # Utilities
│   └── storage/
│       ├── __init__.py       # get_storage() factory
│       ├── base.py           # Abstract interface
│       ├── bigquery_storage.py
│       └── local_storage.py
│
├── clustering_agent/
│   ├── __init__.py
│   ├── __main__.py
│   └── clustering.py         # HMM clustering
│
├── classification_agent/
│   ├── __init__.py
│   ├── __main__.py
│   └── classifier.py         # Random Forest
│
├── forecasting_agent/
│   ├── __init__.py
│   ├── __main__.py
│   └── forecaster.py         # Neural ensemble
│
├── orchestrator/
│   ├── __init__.py
│   ├── state.py              # LangGraph state
│   ├── graph.py              # Graph definition
│   ├── nodes.py              # Training nodes
│   ├── inference_nodes.py    # Inference nodes
│   ├── inference.py          # Inference pipeline
│   ├── alerts.py             # Alert detection
│   ├── monitoring.py         # Performance monitoring
│   └── intelligent_model_checker.py
│
├── cloud_run/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── incremental_trainer.py
│
├── dashboard/
│   ├── __init__.py
│   └── app.py                # Streamlit app
│
├── configs/
│   ├── features_config.yaml
│   ├── feature_policy.yaml
│   ├── data_sources.yaml
│   └── bigquery_config.yaml
│
├── .github/workflows/
│   ├── daily-forecast.yml
│   ├── trigger-cloud-run.yml
│   └── tests.yml
│
├── outputs/                   # Git-tracked model storage
│   ├── models/
│   └── forecasting/
│
├── run_pipeline.py            # Main entry point
├── log_daily_predictions.py
├── requirements.txt
└── README.md
```

---

## Appendix B: Quick Reference

### Common Commands

```bash
# Check model status
python -m orchestrator.intelligent_model_checker

# Run inference only
python run_pipeline.py --workflow inference

# Force retrain specific features
python run_pipeline.py --workflow full --selective-features VIX,CPI

# Trigger Cloud Run manually
gh workflow run "Trigger Cloud Run Training"

# Check latest predictions
cat DAILY_PREDICTIONS.md | tail -50
```

### Key URLs

| Resource | URL |
|----------|-----|
| GitHub Repo | https://github.com/EpbAiD/marketpulse |
| Dashboard | https://marketpulsedashboard.streamlit.app |
| BigQuery Console | https://console.cloud.google.com/bigquery?project=regime01 |
| Cloud Run Console | https://console.cloud.google.com/run/jobs?project=coms-452404 |
| Actions | https://github.com/EpbAiD/marketpulse/actions |

---

*Document generated: January 30, 2026*
*System Version: 1.0*
