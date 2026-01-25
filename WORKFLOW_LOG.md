# Workflow Execution Log

**Started**: 2026-01-25 14:05:11 UTC

---

**[14:05:11]** (0.0min) 📍 **STAGE**: Starting stage: Data Fetching

**[14:05:14]** (0.0min) ℹ️ **INFO**: Starting data fetch (BigQuery: True)

**[14:06:00]** (0.8min) ✅ **SUCCESS**: Data fetch completed (48.6s) - Saved to BigQuery

**[14:06:01]** (0.8min) 📍 **STAGE**: Starting stage: Feature Engineering

**[14:06:01]** (0.8min) ℹ️ **INFO**: Starting feature engineering (BigQuery: True)

**[14:07:14]** (2.1min) ✅ **SUCCESS**: Feature engineering completed (73.0s) - Saved to BigQuery

**[14:07:15]** (2.1min) 📍 **STAGE**: Starting stage: Feature Selection

**[14:07:15]** (2.1min) ℹ️ **INFO**: Starting feature selection (PCA + correlation + mRMR, BigQuery: True)

**[14:11:09]** (6.0min) ✅ **SUCCESS**: Feature selection completed (233.9s) - Selected features saved to BigQuery

**[14:11:10]** (6.0min) 📍 **STAGE**: Starting stage: Regime Clustering (HMM)

**[14:11:10]** (6.0min) ℹ️ **INFO**: Starting HMM clustering (BigQuery: True)

**[14:11:21]** (6.2min) ⚠️ **WARNING**: Skipping visualization: Aligned dataset not found → /home/runner/work/marketpulse/marketpulse/outputs/selected/aligned_dataset.parquet

**[14:11:21]** (6.2min) ✅ **SUCCESS**: HMM clustering completed (11.8s) - 3 regimes detected, saved to BigQuery

**[14:11:22]** (6.2min) 📍 **STAGE**: Starting stage: Regime Classification

**[14:11:22]** (6.2min) ℹ️ **INFO**: Starting Random Forest classifier training (BigQuery: True)

**[14:11:29]** (6.3min) ✅ **SUCCESS**: Regime classifier trained (7.2s) - Model saved

**[14:11:30]** (6.3min) 📍 **STAGE**: Starting stage: Forecasting

**[14:11:30]** (6.3min) ℹ️ **INFO**: Selective training: 6 features (VIX9D, DGS2, NFCI, CPI, UNRATE...)

**[14:11:30]** (6.3min) 📍 **STAGE**: Starting stage: Forecasting - Training Models

