# Workflow Execution Log

**Started**: 2026-01-25 03:24:16 UTC

---

**[03:24:16]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[03:24:19]** (0.0min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[03:25:35]** (1.3min) ✅ **SUCCESS**: Data fetch completed (79.0s) - Saved to BigQuery

**[03:25:36]** (1.3min) 📍 **STAGE**: Starting stage: Feature Engineering

**[03:25:36]** (1.3min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[03:26:56]** (2.7min) ✅ **SUCCESS**: Feature engineering completed (79.8s) - Saved to BigQuery

**[03:26:57]** (2.7min) 📍 **STAGE**: Starting stage: Feature Selection

**[03:26:58]** (2.7min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[03:30:57]** (6.7min) ✅ **SUCCESS**: Feature selection completed (239.4s) - Selected features saved to BigQuery

**[03:30:58]** (6.7min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[03:30:58]** (6.7min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[03:31:11]** (6.9min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[03:31:11]** (6.9min) ✅ **SUCCESS**: HMM clustering completed (13.3s) - 3 regimes detected, saved to BigQuery

**[03:31:12]** (6.9min) 📍 **STAGE**: Starting stage: Regime Classification

**[03:31:12]** (6.9min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[03:31:20]** (7.1min) ✅ **SUCCESS**: Regime classifier trained (7.7s) - Model saved

**[03:31:21]** (7.1min) 📍 **STAGE**: Starting stage: Forecasting - Intelligent Model Check

**[03:31:21]** (7.1min) ℹ️ **INFO**: Intelligent Decision: train

**[03:31:21]** (7.1min) ℹ️ **INFO**: Reason: Core models (HMM/classifier) missing or stale + 6 features need training

**[03:31:22]** (7.1min) ℹ️ **INFO**: Full training: All 22 features need training

**[03:31:22]** (7.1min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

