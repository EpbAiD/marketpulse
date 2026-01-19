# Workflow Execution Log

**Started**: 2026-01-19 13:47:08 UTC

---

**[13:47:08]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[13:47:13]** (0.1min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[13:48:12]** (1.1min) ✅ **SUCCESS**: Data fetch completed (63.8s) - Saved to BigQuery

**[13:48:12]** (1.1min) 📍 **STAGE**: Starting stage: Feature Engineering

**[13:48:12]** (1.1min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[13:49:34]** (2.4min) ✅ **SUCCESS**: Feature engineering completed (82.2s) - Saved to BigQuery

**[13:49:35]** (2.5min) 📍 **STAGE**: Starting stage: Feature Selection

**[13:49:36]** (2.5min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[13:53:34]** (6.4min) ✅ **SUCCESS**: Feature selection completed (238.5s) - Selected features saved to BigQuery

**[13:53:34]** (6.4min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[13:53:34]** (6.4min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[13:53:47]** (6.7min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[13:53:47]** (6.7min) ✅ **SUCCESS**: HMM clustering completed (13.2s) - 3 regimes detected, saved to BigQuery

**[13:53:48]** (6.7min) 📍 **STAGE**: Starting stage: Regime Classification

**[13:53:48]** (6.7min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[13:53:55]** (6.8min) ✅ **SUCCESS**: Regime classifier trained (7.0s) - Model saved

**[13:53:56]** (6.8min) 📍 **STAGE**: Starting stage: Forecasting - Intelligent Model Check

**[13:53:56]** (6.8min) ℹ️ **INFO**: Intelligent Decision: train

**[13:53:56]** (6.8min) ℹ️ **INFO**: Reason: Core models (HMM/classifier) are missing or stale

