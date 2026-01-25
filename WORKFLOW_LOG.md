# Workflow Execution Log

**Started**: 2026-01-25 13:52:30 UTC

---

**[13:52:30]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[13:52:33]** (0.1min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[13:53:50]** (1.3min) ✅ **SUCCESS**: Data fetch completed (80.7s) - Saved to BigQuery

**[13:53:52]** (1.4min) 📍 **STAGE**: Starting stage: Feature Engineering

**[13:53:52]** (1.4min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[13:55:06]** (2.6min) ✅ **SUCCESS**: Feature engineering completed (74.3s) - Saved to BigQuery

**[13:55:07]** (2.6min) 📍 **STAGE**: Starting stage: Feature Selection

**[13:55:07]** (2.6min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[13:59:03]** (6.6min) ✅ **SUCCESS**: Feature selection completed (236.7s) - Selected features saved to BigQuery

**[13:59:04]** (6.6min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[13:59:04]** (6.6min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[13:59:18]** (6.8min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[13:59:18]** (6.8min) ✅ **SUCCESS**: HMM clustering completed (14.1s) - 3 regimes detected, saved to BigQuery

**[13:59:19]** (6.8min) 📍 **STAGE**: Starting stage: Regime Classification

**[13:59:19]** (6.8min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[13:59:27]** (7.0min) ✅ **SUCCESS**: Regime classifier trained (7.5s) - Model saved

**[13:59:28]** (7.0min) 📍 **STAGE**: Starting stage: Forecasting

**[13:59:28]** (7.0min) ℹ️ **INFO**: Selective training: 6 features (VIX9D, DGS2, NFCI, CPI, UNRATE...)

**[13:59:28]** (7.0min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

