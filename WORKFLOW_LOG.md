# Workflow Execution Log

**Started**: 2026-01-22 11:26:23 UTC

---

**[11:26:23]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[11:26:26]** (0.1min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[11:28:24]** (2.0min) ✅ **SUCCESS**: Data fetch completed (120.7s) - Saved to BigQuery

**[11:28:24]** (2.0min) 📍 **STAGE**: Starting stage: Feature Engineering

**[11:28:24]** (2.0min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[11:30:47]** (4.4min) ✅ **SUCCESS**: Feature engineering completed (142.3s) - Saved to BigQuery

**[11:30:47]** (4.4min) 📍 **STAGE**: Starting stage: Feature Selection

**[11:30:48]** (4.4min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[11:35:00]** (8.6min) ✅ **SUCCESS**: Feature selection completed (252.9s) - Selected features saved to BigQuery

**[11:35:01]** (8.6min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[11:35:01]** (8.6min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[11:35:13]** (8.8min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[11:35:13]** (8.8min) ✅ **SUCCESS**: HMM clustering completed (11.8s) - 3 regimes detected, saved to BigQuery

**[11:35:14]** (8.8min) 📍 **STAGE**: Starting stage: Regime Classification

**[11:35:14]** (8.9min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[11:35:21]** (9.0min) ✅ **SUCCESS**: Regime classifier trained (6.9s) - Model saved

**[11:35:21]** (9.0min) 📍 **STAGE**: Starting stage: Forecasting - Intelligent Model Check

**[11:35:21]** (9.0min) ℹ️ **INFO**: Intelligent Decision: train

**[11:35:21]** (9.0min) ℹ️ **INFO**: Reason: Core models (HMM/classifier) are missing or stale

