# Workflow Execution Log

**Started**: 2026-01-23 11:24:18 UTC

---

**[11:24:18]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[11:24:22]** (0.1min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[11:26:19]** (2.0min) ✅ **SUCCESS**: Data fetch completed (121.1s) - Saved to BigQuery

**[11:26:20]** (2.0min) 📍 **STAGE**: Starting stage: Feature Engineering

**[11:26:20]** (2.0min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[11:29:03]** (4.7min) ✅ **SUCCESS**: Feature engineering completed (162.7s) - Saved to BigQuery

**[11:29:04]** (4.8min) 📍 **STAGE**: Starting stage: Feature Selection

**[11:29:05]** (4.8min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[11:33:22]** (9.1min) ✅ **SUCCESS**: Feature selection completed (258.5s) - Selected features saved to BigQuery

**[11:33:23]** (9.1min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[11:33:23]** (9.1min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[11:33:35]** (9.3min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[11:33:35]** (9.3min) ✅ **SUCCESS**: HMM clustering completed (11.5s) - 3 regimes detected, saved to BigQuery

**[11:33:35]** (9.3min) 📍 **STAGE**: Starting stage: Regime Classification

**[11:33:35]** (9.3min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[11:33:43]** (9.4min) ✅ **SUCCESS**: Regime classifier trained (7.7s) - Model saved

**[11:33:44]** (9.4min) 📍 **STAGE**: Starting stage: Forecasting - Intelligent Model Check

**[11:33:44]** (9.4min) ℹ️ **INFO**: Intelligent Decision: train

**[11:33:44]** (9.4min) ℹ️ **INFO**: Reason: Core models (HMM/classifier) are missing or stale

**[11:33:45]** (9.4min) ℹ️ **INFO**: Full training: All 22 features need training

**[11:33:45]** (9.4min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

