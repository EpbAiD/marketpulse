# Workflow Execution Log

**Started**: 2026-01-24 13:39:09 UTC

---

**[13:39:09]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[13:39:10]** (0.0min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[13:39:59]** (0.8min) ✅ **SUCCESS**: Data fetch completed (50.3s) - Saved to BigQuery

**[13:40:00]** (0.9min) 📍 **STAGE**: Starting stage: Feature Engineering

**[13:40:00]** (0.9min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[13:41:22]** (2.2min) ✅ **SUCCESS**: Feature engineering completed (82.2s) - Saved to BigQuery

**[13:41:23]** (2.2min) 📍 **STAGE**: Starting stage: Feature Selection

**[13:41:24]** (2.3min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[13:43:30]** (4.3min) ✅ **SUCCESS**: Feature selection completed (126.5s) - Selected features saved to BigQuery

**[13:43:30]** (4.4min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[13:43:31]** (4.4min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[13:43:39]** (4.5min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /Users/eeshanbhanap/Desktop/RFP/outputs/selected/aligned_dataset.parquet

**[13:43:39]** (4.5min) ✅ **SUCCESS**: HMM clustering completed (8.5s) - 3 regimes detected, saved to BigQuery

**[13:43:40]** (4.5min) 📍 **STAGE**: Starting stage: Regime Classification

**[13:43:40]** (4.5min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[13:43:45]** (4.6min) ✅ **SUCCESS**: Regime classifier trained (5.0s) - Model saved

**[13:43:45]** (4.6min) 📍 **STAGE**: Starting stage: Forecasting - Intelligent Model Check

**[13:43:45]** (4.6min) ℹ️ **INFO**: Intelligent Decision: train

**[13:43:45]** (4.6min) ℹ️ **INFO**: Reason: Core models (HMM/classifier) are missing or stale

**[13:43:46]** (4.6min) ℹ️ **INFO**: Full training: All 22 features need training

**[13:43:46]** (4.6min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

